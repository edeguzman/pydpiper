import errno
import os
#import os.path
import functools # type: ignore
from operator import add
from typing import List, Set, Tuple, TypeVar

from pydpiper.execution.pipeline import CmdStage

def raise_(err : BaseException):
    """`raise` is a keyword and `raise e` isn't an expression, so can't be used freely"""
    raise err

def explode(filename : str) -> Tuple[str, str, str]:
    # TODO should this be a namedtuple instead of a tuple? Probably...can still match against, etc.
    """Split a filename into a directory, 'base', and extension

    >>> explode('/path/to/some/file.ext')
    ('/path/to/some', 'file', '.ext')
    >>> explode('./relative_path_to/file.ext')
    ('./relative_path_to', 'file', '.ext')
    >>> explode('file')
    ('', 'file', '')
    """
    base, ext = os.path.splitext(filename)
    directory, name = os.path.split(base)
    return (directory, name, ext)

T = TypeVar('T')

def pairs(lst : List[T]) -> List[Tuple[T, T]]:
    return list(zip(lst[:-1], lst[1:]))

def flatten(*xs):
    return functools.reduce(add, xs, [])

class NotProvided(object):
    """To be used as a datatype indicating no argument with this name was supplied
    in the situation when None has another sensible meaning, e.g., when a sensible
    default file is available but None indicates *no* file should be used."""

class NoneError(ValueError): pass

def ensure_nonnull_return(f):
    def g(*args):
        result = f(*args)
        if result is None:
            raise NoneError
        else:
            return result
    return g

def output_directories(stages : Set[CmdStage]) -> Set[str]:
    """Directories to be created (currently rather redundant in the presence of subdirectories).
    No need to consider stage inputs - any input already exists or is also the output
    of some previous stage."""
    # TODO what about logfiles/logdirs?
    # What if an output file IS a directory - should there be a special
    # way of tagging this other than ending the path in a trailing "/"?
    return { os.path.dirname(o) for c in stages for o in c.outputFiles }

# this doesn't seem possible to do properly ... but we could turn a namespace into another type
# and use that as a default object, say
#def make_parser_and_class(**kwargs):
#    """Create both an argparser and a normal class with the same constraints"""
#    p = argparse.ArgumentParser(**kwargs)
#    fields = [v.... for v in p._option_store_actions.values()]
#    pass #TODO use p._option_string_actions ?
