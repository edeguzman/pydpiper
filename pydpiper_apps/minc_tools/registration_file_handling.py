#!/usr/bin/env python

import pydpiper.file_handling as fh
from os.path import abspath, join
from os import curdir

class RegistrationGroupedFiles():
    """A class to keep together all bits for a RegistrationPipeFH stage"""
    def __init__(self, inputVolume, mask=None):
        self.basevol = inputVolume
        self.labels = []
        self.inputLabels = []
        self.blurs = {}
        self.gradients = {}
        self.lastblur = None 
        self.lastgradient = None
        self.transforms = {}
        self.lastTransform = {}
        self.mask = mask
        
    def getBlur(self, fwhm=None, gradient=False):
        """returns file with specified blurring kernel
        If no blurring kernel is specified, return the last blur
        If gradient is specified, return gradient instead of blur
        If fwhm = -1, return basevol"""
        blurToReturn = None
        if fwhm == -1:
            blurToReturn = self.basevol
        else:
            if not fwhm:
                fwhm = self.lastblur
                if gradient:
                    fwhm = self.lastgradient
            if gradient:
                blurToReturn = self.gradients[fwhm]
            else:
                blurToReturn = self.blurs[fwhm]
        return(blurToReturn)

    def addBlur(self, filename, fwhm, gradient=None):
        """adds the blur with the specified kernel"""
        self.blurs[fwhm] = filename
        self.lastblur = fwhm
        if gradient:
            self.gradients[fwhm] = gradient
            self.lastgradient = fwhm

class RegistrationFHBase():
    """
        Base class for providing file-handling support to registration pipelines
    """
    def __init__(self, filename, mask=None, basedir=None):
        self.groupedFiles = [RegistrationGroupedFiles(filename, mask)]
        # We will always have only one group for the base class.
        self.currentGroupIndex = 0
        self.inputFileName = filename
        self.mask = mask
        self.basename = fh.removeBaseAndExtension(self.inputFileName)
        """basedir optional for base class.
           If not specified, we assume we just need to read files, 
           but don't need to write anything associated with them
           Need to specify a basedir if any output is needed
           If unspecified, set as current directory (but assume no writing)"""
        if basedir:
            self.basedir = fh.makedirsIgnoreExisting(basedir)
            """ only create a logDir if we plan on writing
            Overwritten classes should always do this """
            self.setupNames()
        else:
            """Set self.basedir and self.logDir, 
            but we shouldn't actually do any writing."""
            self.basedir = abspath(curdir)
            self.logDir = self.basedir
    
    def setupNames(self):
        self.logDir = fh.createLogDir(self.basedir)    
    def setMask(self, inputMask):
        self.groupedFiles[self.currentGroupIndex].mask = inputMask
    def getMask(self):
        return(self.groupedFiles[self.currentGroupIndex].mask) 
    def setLastXfm(self, targetFilename, xfm):
        self.groupedFiles[self.currentGroupIndex].lastTransform[targetFilename] = xfm
    def getLastBasevol(self):
        return(self.groupedFiles[self.currentGroupIndex].basevol)
    def setLastBasevol(self, newBaseVol):
        self.groupedFiles[self.currentGroupIndex].basevol = newBaseVol
    def setOutputDirectory(self, defaultDir):
        if not defaultDir:
            outputDir = abspath(curdir)
        else:
            outputDir = abspath(defaultDir)
        return(outputDir)
    
class RegistrationPipeFH(RegistrationFHBase):
    """
        A class to provide file-handling support for registration pipelines.
        
        Inherits from RegistrationFHBase

        Each input file will have a separate directory underneath the
        specified base directory. This will in turn be populated by
        different output directories for transforms, resampled files,
        temporary files, etc. The final directory tree will look like the
        following:

        basedir/filenamebase/log -- log files
        basedir/filenamebase/resampled -- resampled files go here
        basedir/filenamebase/transforms -- transforms (xfms, grids, etc.) go here
        basedir/filenamebase/labels -- any resampled labels (if necessary) go here
        basedir/filenamebase/tmp -- intermediate temporary files go here

        The RegistrationPipeFH can be passed to different processing
        functions (minctracc, blur, etc.) which will use it to derive
        proper filenames. The RegistrationPipeFH can moreover group
        related files (blurs, transforms, resamples) by using the newGroup
        call.

    """
    def __init__(self, filename, mask=None, basedir=None):
        RegistrationFHBase.__init__(self, filename, mask, basedir)
        # NOTE: currentGroupIndex set to 0 in base class init...TEST!!!!
        # groups can be referred to by either name or index number
        self.groupNames = {'base' : 0}  
    
    def newGroup(self, inputVolume = None, mask = None, groupName = None):
        """create a new set of grouped files"""
        groupIndex = len(self.groupedFiles) + 1
        if not inputVolume:
            inputVolume = self.getLastBasevol()
        
        if not mask:
            mask = self.getMask()
        
        if not groupName:
            groupName = groupIndex

        self.groupedFiles.append(RegistrationGroupedFiles(inputVolume, mask))
        self.groupNames[groupName] = groupIndex
        self.currentGroupIndex = groupIndex

    def setupNames(self):
        """string munging to create necessary basenames and directories"""
        self.subjDir = fh.createSubDir(self.basedir, self.basename)
        self.logDir = fh.createLogDir(self.subjDir)
        self.resampledDir = fh.createSubDir(self.subjDir, "resampled")
        self.transformsDir = fh.createSubDir(self.subjDir, "transforms")
        self.labelsDir = fh.createSubDir(self.subjDir, "labels")
        self.tmpDir = fh.createSubDir(self.subjDir, "tmp")
        self.statsDir = fh.createSubDir(self.subjDir, "stats-volumes")

    def registerVolume(self, targetFH, arglist, regType="minctracc"):
        """create the filenames for a single registration call

        Two input arguments are required - a RegistrationPipeFH instance for the
        target volume and an argument list; the argument list is
        derived from function introspection in the minctracc or
        mincANTS calls and will be used to provide a unique filename.
        The registrationType argument defaults to minctracc but if it is
        mincANTS, will handle different types of arguments.

        """
        sourceFilename = fh.removeBaseAndExtension(self.getLastBasevol())
        targetFilename = fh.removeBaseAndExtension(targetFH.getLastBasevol())
        # check to make sure blurs match, otherwise throw error?
        # Go through argument list to build file name
        xfmFileName = [sourceFilename, "to", targetFilename]
        xfmFileName += [str(regType)]
        xfmOutputDir = self.tmpDir
        for k, l in arglist:
            if regType == "minctracc":
                if k == 'blur':
                    xfmFileName += [str(l) + "b"]
                elif k == 'gradient':
                    if l:
                        xfmFileName += ["dxyz"]
                elif k == 'linearparam':
                    xfmFileName += [l]
                elif k == 'iterations':
                    xfmFileName += ["i" + str(l)]
                elif k == 'step':
                    xfmFileName += ["s" + str(l)]
                elif k == 'defaultDir':
                    xfmOutputDir = self.setOutputDirectory(str(l))
            elif regType == "mincANTS":
                if k == 'similarity_metric':
                    xfmFileName += [str(len(l))]
                    for i in l:
                        xfmFileName += [str(i)]
                elif k == 'iterations':
                    xfmFileName += ["iter" + str(l)]
                elif k == 'defaultDir':
                    xfmOutputDir = self.setOutputDirectory(str(l))
                
        xfmFileWithExt = "_".join(xfmFileName) + ".xfm"
        outputXfm = fh.createBaseName(xfmOutputDir, xfmFileWithExt)
        self.addAndSetXfmToUse(targetFilename, outputXfm)
        return(outputXfm)
    
    def setOutputDirectory(self, defaultDir):
        """sets output directory based on defaults for each type of call
        allows for the possibility that an entirely new directory may be specified
        e.g. pipeline_name_nlin or pipeline_name_lsq6 that does not depend on 
        existing file handlers. Additional cases may be added in the future"""
        if not defaultDir:
            outputDir = abspath(curdir)
        elif defaultDir=="tmp":
            outputDir = self.tmpDir
        elif defaultDir=="resampled":
            outputDir = self.resampledDir
        elif defaultDir=="labels":
            outputDir = self.labelsDir
        elif defaultDir=="transforms":
            outputDir = self.transformsDir
        elif defaultDir=="stats":
            outputDir = self.statsDir
        else:
            outputDir = abspath(defaultDir)
        return(outputDir)
    
    #MF TODO: This code is getting a bit repetitive. Lets see if we can't
    # consolidate a bit.     
    def getBlur(self, fwhm=None, gradient=False): 
        return(self.groupedFiles[self.currentGroupIndex].getBlur(fwhm, gradient))
    def setBlurToUse(self, fwhm):
        self.groupedFiles[self.currentGroupIndex].lastblur = fwhm
    def getLastXfm(self, targetFilename):
        currGroup = self.groupedFiles[self.currentGroupIndex]
        lastXfm = None
        if targetFilename in currGroup.lastTransform:
            lastXfm = currGroup.lastTransform[targetFilename]
        return(lastXfm)
    def addAndSetXfmToUse(self, targetFilename, xfm):
        currGroup = self.groupedFiles[self.currentGroupIndex]
        if not targetFilename in currGroup.transforms:
            currGroup.transforms[targetFilename] = []
        if not xfm in currGroup.transforms[targetFilename]:
            currGroup.transforms[targetFilename].append(xfm)
        self.setLastXfm(targetFilename, xfm)
    def addLabels(self, newLabel, inputLabel=False):
        """Add labels to array."""
        labelArray = self.returnLabels(inputLabel)
        if not newLabel in labelArray:
            labelArray.append(newLabel)
    def returnLabels(self, inputLabel=False):
        """Return appropriate set of labels"""
        currGroup = self.groupedFiles[self.currentGroupIndex]
        if inputLabel:
            labelArray = currGroup.inputLabels
        else:
            labelArray = currGroup.labels
        return(labelArray)
    def clearLabels(self, inputLabel):
        currGroup = self.groupedFiles[self.currentGroupIndex]
        if inputLabel:
            del currGroup.inputLabels[:]
        else:
            del currGroup.labels[:]
    
    def blurFile(self, fwhm, gradient=False, defaultDir="tmp"):
        """create filename for a mincblur call

        Return a triplet of the basename, which mincblur needs as its
        input, the full filename, which mincblur will create after its done,
        and the log file"""
        
        #MF TODO: Error handling if there is no lastBaseVol
        lastBaseVol = self.getLastBasevol()
        outputbase = fh.removeBaseAndExtension(lastBaseVol)
        outputDir = self.setOutputDirectory(defaultDir)
        outputbase = "%s/%s_fwhm%g" % (outputDir, outputbase, fwhm)
        
        withext = "%s_blur.mnc" % outputbase     
        log = fh.logFromFile(self.logDir, withext)

        outlist = { "base" : outputbase,
                    "file" : withext,
                    "log"  : log }
        
        if gradient:
            gradWithExt = "%s_dxyz.mnc" % outputbase
            outlist["gradient"] = gradWithExt
        else:
            gradWithExt=None

        self.groupedFiles[self.currentGroupIndex].addBlur(withext, fwhm, gradWithExt)
        return(outlist)
