# HQ XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# HQ X
# HQ X   quippy: Python interface to QUIP atomistic simulation library
# HQ X
# HQ X   Copyright James Kermode 2010
# HQ X
# HQ X   These portions of the source code are released under the GNU General
# HQ X   Public License, version 2, http://www.gnu.org/copyleft/gpl.html
# HQ X
# HQ X   If you would like to license the source code under different terms,
# HQ X   please contact James Kermode, james.kermode@gmail.com
# HQ X
# HQ X   When using this software, please cite the following reference:
# HQ X
# HQ X   http://www.jrkermode.co.uk/quippy
# HQ X
# HQ XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

"""quippy package

James Kermode <james.kermode@kcl.ac.uk>

Contains python bindings to the libAtoms/QUIP Fortran 95 codes
<http://www.libatoms.org>. """

import sys
assert sys.version_info >= (2,4,0)

import atexit, os, numpy, logging
from ConfigParser import ConfigParser

# Read ${HOME}/.quippyrc config file if it exists
cfg = ConfigParser()
quippyrc = os.path.join(os.environ['HOME'],'.quippyrc')
if os.path.exists(quippyrc):
   cfg.read(quippyrc)

# Read config file given in ${QUIPPY_CFG} if it exists
if 'QUIPPY_CFG' in os.environ and os.path.exists(os.environ['QUIPPY_CFG']):
   cfg.read(os.environ['QUIPPY_CFG'])

if 'logging' in cfg.sections():
   if 'level' in cfg.options('logging'):
      logging.root.setLevel(getattr(logging, cfg.get('logging', 'level')))

disabled_modules = []
if 'modules' in cfg.sections():
   for name, value in cfg.items('modules'):
      if not int(value):
         disabled_modules.append(name)

# External dependencies
available_modules = []
unavailable_modules = []
for mod in ['netCDF4', 'pylab', 'scipy', 'ase', 'atomeye']:
   if mod in disabled_modules: continue
   try:
      __import__(mod)
      available_modules.append(mod)
   except ImportError:
      unavailable_modules.append(mod)

logging.debug('disabled_modules %r' % disabled_modules)
logging.debug('available_modules %r' % available_modules)
logging.debug('unavailable_modules %r' % unavailable_modules)

if 'netCDF4' in available_modules:
   from netCDF4 import Dataset
   netcdf_file = Dataset
else:
   from pupynere import netcdf_file

AtomsReaders = {}
AtomsWriters = {}

def atoms_reader(source, lazy=True):
   """Decorator to add a new reader"""
   def decorate(func):
      from quippy import AtomsReaders
      func.lazy = lazy
      if not source in AtomsReaders:
         AtomsReaders[source] = func
      return func
   return decorate

import _quippy

# Reference values of .true. and .false. from Fortran
QUIPPY_TRUE = _quippy.qp_reference_true()
QUIPPY_FALSE = _quippy.qp_reference_false()

from oo_fortran import FortranDerivedType, FortranDerivedTypes, fortran_class_prefix, wrap_all

# Read spec file generated by f90doc and construct wrappers for classes
# and routines found therein.

def quippy_cleanup():
   try:
      _quippy.qp_verbosity_pop()
      _quippy.qp_system_finalise()
   except AttributeError:
      pass

_quippy.qp_system_initialise(-1, qp_quippy_running=QUIPPY_TRUE)
_quippy.qp_verbosity_push(0)
atexit.register(quippy_cleanup)

from spec import spec
wrap_modules = spec['wrap_modules']
# Jointly wrap atoms_types, atoms and connection into the respective classes
del wrap_modules[wrap_modules.index('atoms_types')]
del wrap_modules[wrap_modules.index('atoms')]
del wrap_modules[wrap_modules.index('connection')]
del wrap_modules[wrap_modules.index('domaindecomposition')]
wrap_modules += [ [ 'atoms_types', 'atoms', 'connection', 'domaindecomposition' ] ]
###
classes, routines, params = wrap_all(_quippy, spec, wrap_modules, spec['short_names'], prefix='qp_')

QUIP_ROOT = spec['quip_root']
QUIP_ARCH = spec['quip_arch']
QUIP_MAKEFILE = spec['quip_makefile']

for name, cls in classes:
   setattr(sys.modules[__name__], name, cls)

for name, routine in routines:
   setattr(sys.modules[__name__], name, routine)

sys.modules[__name__].__dict__.update(params)

# Import custom sub classes
import atoms;           from atoms import Atoms, make_lattice, get_lattice_params
import dictionary;      from dictionary import Dictionary
import cinoutput;       from cinoutput import CInOutput, CInOutputReader, CInOutputWriter
import dynamicalsystem; from dynamicalsystem import DynamicalSystem
import potential;       from potential import Potential
import table;           from table import Table
import extendable_str;  from extendable_str import Extendable_str

for name, cls in classes:
   try:
      # For some Fortran types, we have customised subclasses written in Python
      new_cls = getattr(sys.modules[__name__], name[len(fortran_class_prefix):])
   except AttributeError:
      # For the rest, we make a dummy subclass which is equivalent to Fortran base class
      new_cls = type(object)(name[len(fortran_class_prefix):], (cls,), {})
      setattr(sys.modules[__name__], name[len(fortran_class_prefix):], new_cls)

   FortranDerivedTypes['type(%s)' % name[len(fortran_class_prefix):].lower()] = new_cls

del classes
del routines
del params
del wrap_all
del fortran_class_prefix
del spec

class QuippyWriter:
   def __init__(self, fortran_file):
      self.fortran_file = fortran_file
      self.saved_prefix = None
      
   def write(self, text):
      for line in text.splitlines(True):
         inoutput_print_string(line.strip(), file=self.fortran_file, nocr=not line.endswith('\n'))
         if self.saved_prefix is not None and line.endswith('\n'):
            self.fortran_file.prefix = self.saved_prefix
            self.saved_prefix = None
         if self.saved_prefix is None and not line.endswith('\n'):
            self.saved_prefix = self.fortran_file.prefix
            self.fortran_file.prefix = ''

# Create InOutput objects associated with stdout and stderr                
mainlog_ptr, errorlog_ptr = _quippy.qp_get_mainlog_errorlog_ptr()
mainlog = InOutput(fpointer=mainlog_ptr, finalise=False)
errorlog = InOutput(fpointer=errorlog_ptr, finalise=False)
del mainlog_ptr, errorlog_ptr

import farray;      from farray import *
import atomslist;   from atomslist import *
import periodic;    from periodic import *
import util;        from util import *

# Redirect Python stdout to Fortran mainlog so that prefix, verbosity, etc. work.
if not is_interactive_shell():
   sys.stdout = QuippyWriter(mainlog)


import sio2, povray, cube, xyz, netcdf

if 'ase' in available_modules:
   import aseinterface

try:
   import castep
except ImportError:
   logging.warning('quippy.castep import failed.')

if 'atomeye' in available_modules:
   import atomeye
   import atomeyewriter
