#!/usr/bin/env python

from pydpiper.application import AbstractApplication
from pydpiper.pipeline import CmdStage, InputFile, OutputFile, LogFile
import pydpiper.file_handling as fh
import atoms_and_modules.registration_functions as rf
import atoms_and_modules.registration_file_handling as rfh
import atoms_and_modules.minc_modules as mm
import atoms_and_modules.minc_parameters as mp
import atoms_and_modules.NLIN as nl
import atoms_and_modules.minc_atoms as ma
import atoms_and_modules.stats_tools as st
import atoms_and_modules.old_MBM_interface_functions as ombm
import Pyro
from optparse import OptionGroup
from datetime import date
from os.path import abspath, isdir, split, splitext
import logging
import sys

logger = logging.getLogger(__name__)

Pyro.config.PYRO_MOBILE_CODE=1 

class LongitudinalTwolevelNlin(AbstractApplication):
    def setup_options(self):
        helpString="""
twolevel_model_building

A pydpiper application designed to work with longitudinal data. LSQ12
and nonlinear registration is used to create a consensus average of
every subject. A second level of LSQ12 and nonlinear registrations is 
then used to bring all the consensus averages from each subject into
their own consensus average.

Some assumptions:
* at least two timepoints per subject 
  * future work should be able to extend this to allow single timepoint subjects
* all images must be similar enough to allow registration

The last point is particularly important: the consensus average building process
aligns every image from each subject to every other image from that subject. Early
developmental data or tumour data, where the first image in the series might not be
alignable to the last image in the series, is thus not suited for this approach.

Data is passed to the application through a CSV file. This file has one line per subject,
with each scan per subject listed on the same line and separated by a comma.
"""
        
        # own options go here
        nl.addNlinRegOptionGroup(self.parser)
        rf.addGenRegOptionGroup(self.parser)
        mp.addNLINOptionGroup(self.parser)
        st.addStatsOptions(self.parser)
        
        # TODO: better usage description (once I've figured out what the usage will be ...)
        self.parser.set_usage("%prog [options] input.csv")
        # set help - note that the format is messed up, something that can be fixed if we upgrade
        # from optparse to argparse.
        self.parser.set_description(helpString) 
        
    def setup_appName(self):
        appName = "twolevel_model_building"
        return appName
    
    def run(self):
        options = self.options
        args = self.args
        
        # Setup output directories for two-level model building (_processed and _nlin for now).        
        dirs = rf.setupDirectories(self.outputDir, options.pipeline_name, module="NLIN")
        
        # read in files from CSV
        subjects = rf.setupSubjectHash(self.args[0], dirs, self.options.mask_dir)
        
        # for the moment assume that all input files are in LSQ12 space
        # TODO: Add in LSQ6 and LSQ12 registrations if requested
        
        index = 0
        firstlevelNlins = [] # stores the per subject NLINs avgs
        subjStats = [] #used for storing first level stats, which will have to be resampled later
        ### first level of registrations: register within subject
        for i in range(len(subjects)):
            ### filename munging ###
            # takes the filename of the first file in the list and prepends FIRSTLEVEL- to it
            baseVol = subjects[i][0].getLastBasevol()
            subjBase = "FIRSTLEVEL-" + splitext(split(baseVol)[1])[0]
            # create an NLIN directory inside the main NLIN directory per subject
            firstNlinDirectory = fh.createSubDir(dirs.nlinDir, subjBase)
            # put the lsq12 averages in the processed directory for now
            lsq12AvgFile = abspath(dirs.processedDir) + "/" + subjBase + "-lsq12avg.mnc"
            lsq12FH = rfh.RegistrationPipeFH(lsq12AvgFile, basedir=dirs.nlinDir)
            ### step 1: create an average of all the input files per subject ###
            # TODO: optionally allow LSQ12 or LSQ6 + LSQ12 here rather than assume they come prealigned
            avg = ma.mincAverage(subjects[i], lsq12FH)
            lsq12FH.setLastBasevol(avg.outputFiles[0])
            self.pipeline.addStage(avg)
            ### step 2: run iterative ANTS model building for each subject
            NL = nl.initNLINModule(subjects[i], 
                                   lsq12FH, 
                                   firstNlinDirectory, 
                                   options.nlin_protocol, 
                                   options.reg_method)
            NL.iterate()
            self.pipeline.addPipeline(NL.p)
            # add the last NLIN average to the volumes that will proceed to step 2
            firstlevelNlins.append(NL.nlinAverages[-1])
            if options.calc_stats:
                finalNlin = NL.nlinAverages[-1]
                tmpStats=[]
                for s in subjects[i]:
                    stats = st.CalcStats(s, finalNlin, options.stats_kernels)
                    self.pipeline.addPipeline(stats.p)
                    tmpStats.append(stats)
                subjStats.append(tmpStats)
        ### second level of registrations: register across subjects
        ## start by averaging all the NLINs from the first level; 
        # TODO: This should actually be replaced by an LSQ12
        lsq12AvgFile = abspath(dirs.processedDir) + "/firstlevelNlins-lsq12avg.mnc"
        lsq12FH = rfh.RegistrationPipeFH(lsq12AvgFile, basedir=dirs.nlinDir)
        avg = ma.mincAverage(firstlevelNlins, lsq12FH)
        lsq12FH.setLastBasevol(avg.outputFiles[0])
        self.pipeline.addStage(avg)
        ## run iterative ANTS model building across the per subject averages
        # TODO: allow for a different protocol here.
        NL = nl.initNLINModule(firstlevelNlins, 
                               lsq12FH, 
                               dirs.nlinDir, 
                               options.nlin_protocol,
                               options.reg_method)
        NL.iterate()
        self.pipeline.addPipeline(NL.p)
        if options.calc_stats:
            finalNlin = NL.nlinAverages[-1]
            for s in firstlevelNlins:
                stats = st.CalcStats(s, finalNlin, options.stats_kernels)
                self.pipeline.addPipeline(stats.p)
                # now resample the stats files from the first level registration to the common space
                # created by the second level of registration
                for i in range(len(subjects)):
                    for s in range(len(subjects[i])):
                        # get the last xfm from the second level registrations
                        xfm = firstlevelNlins[i].getLastXfm(NL.nlinAverages[-1])
                        p = mm.resampleToCommon(xfm,
                                                subjects[i][s], 
                                                subjStats[i][s].statsGroup, 
                                                options.stats_kernels, 
                                                lsq12FH)
                        self.pipeline.addPipeline(p)
        
if __name__ == "__main__":
    application = LongitudinalTwolevelNlin()
    application.start()
