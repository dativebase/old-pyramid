# Copyright 2016 Joel Dunham
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Morphological parser repurposable functionality.

This module contains the core classes required for morphological parser
functionality.  These classes provide subprocess-mediated interfaces to the
foma program for finite-state transducer creation and interaction as well as to
the MITLM program for language model creation and interaction. The classes are:

    - Command                        -- general-purpose functionality for
                                        interfacing to a command-line program
    - FomaFST(Command)               -- interface to foma
    - Phonology(FomaFST)             -- phonology-specific interface to foma
    - Morphology(FomaFST)            -- morphology-specific interface to foma
    - LanguageModel(Command)         -- interface to LM toolkits (only MITLM at
                                        present)
    - MorphologicalParser(FomaFST)   -- basically a morphophonology foma FST
                                        that has a LM object

The last four classes are used as superclasses for the relevant OLD
(SQLAlchemy) model objects.  The model classes implement OLD-specific
functionality that generates the scripts, compilers, log files, corpus files,
vocabulary files, etc. of the FSTs and LMs.  The functionality implemented here
should be reusable in OLD-external programs.

"""

import codecs
import errno
from itertools import product
import logging
import os
import pickle
import re
from shutil import (
    copyfile,
    rmtree
)
from signal import SIGKILL
from subprocess import Popen, PIPE
import threading
import unicodedata
from uuid import uuid4

from . import simplelm


LOGGER = logging.getLogger(__name__)


class Parse:
    """Represents a parse of a word.

    Makes it easy to convert between string and list representations of a
    parse, e.g., from the string

        ``'chien|dog|N-s|PL|Num'``

    to the list

        ``['chien-s', 'dog-PL', 'N-Num']``

    Usage:

        >>> parse = Parse('chien|dog|N-s|PL|Num', morpheme_delimiters='-',
        >>>               rare_delimiter='|')
        >>> parse.parse
        'chien|dog|N-s|PL|Num'
        >>> parse.triplet
        ['chien-s', 'dog-PL', 'N-Num']

    """

    def __init__(self, parse, **kwargs):
        """Initialization requires a ``str`` representation of the parse,
        where such a representation consists of morphemes in f|g|c-f|g|c
        format, i.e., <*f*orm, *g*loss, *c*ategory> triples whose elements are
        delimited by ``self.rare_delimiter`` (represented by "|"), interleaved
        with items from the list of morpheme delimiters defined in the
        comma-separated string ``self.morpheme_delimiters``.
        """
        self.morpheme_delimiters = kwargs.get('morpheme_delimiters', '-')
        self.rare_delimiter = kwargs.get('rare_delimiter', '\u2980')
        if isinstance(parse, str):
            self.parse = parse
        else:
            if not parse:
                self._triplet = []
            else:
                self._triplet = parse
            self.parse = self.triplet2parse(parse)

    def __repr__(self):
        return self.parse.__repr__()

    @property
    def triplet(self):
        try:
            return self._triplet
        except AttributeError:
            self._triplet = self.parse2triplet(self.parse)
            return self._triplet

    @property
    def morphemes(self):
        """Return the parse as a list of morphemes where each morpheme is a
        string whose three parts are separated by ``self.rare_delimiter``.
        """
        try:
            return self._morphemes
        except AttributeError:
            self._morphemes = self.morpheme_only_splitter(self.parse)
            return self._morphemes

    def parse2triplet(self, parse):
        """Convert a string representation of the parse (i.e., ``parse``) to a
        list of three strings, i.e., forms, glosses, categories.  To
        illustrate, if ``parse`` is 'chien|dog|N-s|PL|Phi', output will be
        ['chien-s', 'dog-PL', 'N-Phi'].
        """
        triplet = []
        if not parse:
            return triplet
        for index, item in enumerate(self.morpheme_splitter(parse)):
            if index % 2 == 0:
                triplet.append(item.split(self.rare_delimiter))
            else:
                triplet.append([item, item, item])
        return [''.join(item) for item in zip(*triplet)]

    def triplet2parse(self, triplet):
        """Convert a list representation of a parse to a string one. E.g., if
        ``triplet`` is ['chien-s', 'dog-PL', 'N-Phi'], then ``parse`` will be
        'chien|dog|N-s|PL|Phi'.
        """
        parse = []
        if not triplet:
            return ''
        for index, item in enumerate(
                zip(*[self.morpheme_splitter(line) for line in triplet])):
            if index % 2 == 0:
                parse.append(self.rare_delimiter.join(item))
            else:
                parse.append(item[0])
        return ''.join(parse)

    def esc_re_meta_chars(self, string):
        """Escapes regex metacharacters in ``string``.

            >>> esc_re_meta_chars('-')
            '\\\-'

        """
        def esc(char):
            if char in '\\^$*+?{,}.|][()^-':
                return re.escape(char)
            return char
        return ''.join([esc(char) for char in string])

    @property
    def morpheme_splitter(self):
        """Return a function that will split words into morphemes and
        delimiters.
        """
        try:
            return self._morpheme_splitter
        except AttributeError:
            delimiters = self.delimiters
            # default, word is morpheme
            self._morpheme_splitter = lambda x: [x]
            if delimiters:
                self._morpheme_splitter = re.compile(
                    '([%s])' % ''.join([self.esc_re_meta_chars(d) for d in
                                        delimiters])).split
            return self._morpheme_splitter

    @property
    def morpheme_only_splitter(self):
        """Return a function that will split words into morphemes, excluding
        delimiters.
        """
        try:
            return self._morpheme_only_splitter
        except AttributeError:
            delimiters = self.delimiters
            # default, word is morpheme
            self._morpheme_only_splitter = lambda x: [x]
            if delimiters:
                self._morpheme_only_splitter = re.compile(
                    '[%s]' % ''.join(
                        [self.esc_re_meta_chars(d) for d in delimiters])).split
            return self._morpheme_only_splitter

    @property
    def delimiters(self):
        """Return a list of morpheme delimiters.

        Note: we generate the list ``self._delimiters`` from the unicode object
        ``self.morpheme_delimiters`` if the latter exists; the rationale for
        this is that SQLAlchemy-based FSTs cannot persist Python lists so the
        ``morpheme_delimiters`` attribute stores the string representing the
        list.
        """
        try:
            return self._delimiters
        except AttributeError:
            morpheme_delimiters = getattr(self, 'morpheme_delimiters', None)
            if morpheme_delimiters:
                self._delimiters = morpheme_delimiters.split(',')
            else:
                self._delimiters = []
            return self._delimiters


class Command:
    """Python subprocess interface to a command line program.

    Primary method is ``run`` which executes the input command ``cmd`` as a
    subprocess within a thread.  A ``timeout`` argument to :func:`run` causes
    the process running the input ``cmd`` to be terminated at the end of
    ``timeout`` seconds if it hasn't terminated on its own.

    Cf. http://stackoverflow.com/questions/1191374/subprocess-with-timeout

    """

    def __init__(self, parent_directory, **kwargs):
        self.parent_directory = parent_directory
        self.object_type = kwargs.pop('object_type', 'command')
        self.make_directory_safely(self.directory)
        for key, val in kwargs.items():
            setattr(self, key, val)

    @property
    def file_type2extension(self):
        return {'log': '.log'}

    @property
    def verification_string(self):
        return 'defined %s: ' % self.object_type

    tablename2object_type = {}

    @property
    def object_type(self):
        try:
            return self._object_type
        except AttributeError:
            if hasattr(self, '__tablename__'):
                self._object_type = self.tablename2object_type.get(
                    self.__tablename__, self.__tablename__)
                return self._object_type
            else:
                raise AttributeError("'%s' object has not attribute"
                                     "'object_type'" % self.__class__.__name__)

    @object_type.setter
    def object_type(self, value):
        """You can't set the object_type value of an SQLAlchemy model."""
        if hasattr(self, '__tablename__'):
            self._object_type = self.tablename2object_type.get(
                self.__tablename__, self.__tablename__)
        else:
            self._object_type = value

    @property
    def logpath(self):
        return self.get_file_path('log')

    def get_file_path(self, file_type=None):
        """Return the path to the instance's file of the given type.

        :param str file_type: descriptor of the type of file to return a path
            for.
        :returns: an absolute path to the file of the supplied type for the
            object given.
        """
        return os.path.join(self.directory,
                            '%s%s' % (self.file_name,
                                      self.file_type2extension.get(
                                          file_type, '')))

    @property
    def directory(self):
        """Return the path to this instance's directory."""
        if getattr(self, 'id', None):
            return os.path.join(self.parent_directory, '%s_%d' % (
                self.directory_name, self.id))
        else:
            # This is the (assumedly) non-SQLA/OLD case: we create all files in
            # parent_directory
            return self.parent_directory

    object_type2directory_name = {}
    object_type2file_name = {}

    @property
    def directory_name(self):
        object_type = self.object_type
        return self.object_type2directory_name.get(object_type, object_type)

    @property
    def file_name(self):
        object_type = self.object_type
        return self.object_type2file_name.get(object_type, object_type)

    def make_directory_safely(self, path):
        """Create a directory and avoid race conditions.
        http://stackoverflow.com/questions/273192/python-best-way-to-create-directory-if-it-doesnt-exist-for-file-write.
        """
        try:
            os.makedirs(path)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise

    def remove_directory(self):
        """Remove the directory of the FomaFST instance.

        :returns: an absolute path to the directory for the phonology.

        """
        try:
            rmtree(self.directory)
        except Exception:
            return None

    def run(self, cmd, timeout):
        """Run :func:`cmd` as a subprocess that is terminated within
        ``timeout`` seconds.

        :param list cmd: the command-line command as represeted as a list of
            strings.
        :param float timeout: time in seconds by which :func:`self.cmd` will be
            terminated.
        :return: 2-tuple: return code of process, stdout
        """
        def target():
            with open(self.logpath or os.devnull, "w") as logfile:
                self.process = Popen(cmd, stdout=logfile, stderr=logfile)
            self.process.communicate()
        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.kill_process(self.process)
            thread.join()
        try:
            stdout = open(self.logpath).read()
        except Exception:
            stdout = ''
        return self.process.returncode, stdout

    def kill_process(self, process):
        """Kill ``process`` and all its child processes."""
        pid = process.pid
        pids = [pid]
        pids.extend(self.get_process_children(pid))
        for pid in pids:
            try:
                os.kill(pid, SIGKILL)
            except OSError:
                pass

    def get_process_children(self, pid):
        """Return list of pids of child processes of ``pid``.

        Note that Linux and Mac use different ps interfaces, hence the fork.

        """
        if os.uname()[0] == 'Darwin':
            return self.get_process_children_mac(pid)
        else:
            return self.get_process_children_linux(pid)

    def get_process_children_mac(self, pid):
        """Return list of pids of child processes of ``pid`` on Mac."""
        process = Popen('ps -o pid -o ppid', shell=True,
                        stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        try:
            return [int(p) for p, pp in
                    [line.strip().split() for line in stdout.splitlines()[1:]]
                    if int(pp) == pid]
        except Exception:
            return []

    def get_process_children_linux(self, pid):
        """Return list of pids of child processes of ``pid`` on Linux."""
        process = Popen('ps --no-headers -o pid --ppid %d' % pid, shell=True,
                        stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        return [int(p) for p in stdout.split()]

    def executable_installed(self, name):
        """Check if executable ``name`` is in the user's PATH."""
        for path in os.environ['PATH'].split(os.pathsep):
            path = path.strip('"')
            program_path = os.path.join(path, name)
            if os.path.isfile(program_path) and os.access(
                    program_path, os.X_OK):
                return True
        return False

    def get_modification_time(self, path):
        """Return the modification time of the file or directory with
        ``path``.
        """
        try:
            return os.path.getmtime(path)
        except Exception:
            return None

    def copy_files(self, dst):
        """Copy all files in ``self.directory`` to ``dst``.
        """
        directory = self.directory
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                copyfile(path, os.path.join(dst, name))


class FomaFST(Command):
    """Represents a foma finite-state transducer.

    The FomaFST class is Python logic wrapping foma/flookup functionality;
    Really, this is just a very restricted interface to
    subprocess.Popen(['foma', ...]).

    This class is designed to be both a superclass to an OLD SQLAlchemy-based
    model (e.g., a phonology, morphology or morphophonology) as well as a
    factory for stand-alone foma-based objects.  The three main "public"
    methods are ``save_script``, ``compile``, ``apply`` (and its conveniences,
    ``applyup`` and ``applydown``).

    Usage:

        import time
        from onlinelinguisticdatabase.lib.parser import FomaFST
        parent_directory = '/home/dave/phonology'
        phonology = FomaFST(parent_directory, '#', 'phonology')
        phonology.script = 'define phonology a -> b || c _ d;'
        phonology.save_script()
        compile_attempt = phonology.compile_attempt
        phonology.compile()
        while phonology.compile_attempt == compile_attempt: time.sleep(2)
        print phonology.applyup('cbd')          # {'cbd': ['cbd', 'cad']
        print phonology.applydown('cad')        # {'cad': ['cbd']}
        print phonology.applyup(['cbd', 'dog']) # {'cbd': ['cbd', 'cad'],
                                                #  'dog': ['dog']}
        print phonology.applyup(['cad', 'dog']) # {'cad': ['cbd'],
                                                #  'dog': ['dog']}
    """

    def __init__(self, parent_directory, **kwargs):
        self.compile_attempt = None
        self.word_boundary_symbol = kwargs.pop(
            'word_boundary_symbol', self.default_word_boundary_symbol)
        kwargs['object_type'] = kwargs.get('object_type', 'foma_fst')
        super(FomaFST, self).__init__(parent_directory, **kwargs)

    @property
    def file_type2extension(self):
        """Extend the base class's property of the same name so that
        ``get_file_path`` works appropriately for this type of command.
        """
        if getattr(self, '_file_type2extension', None):
            return self._file_type2extension
        else:
            self._file_type2extension = super(
                FomaFST, self).file_type2extension.copy()
            self._file_type2extension.update({
                'script': '.script',
                'binary': '.foma',
                'compiler': '.sh'
            })
            return self._file_type2extension

    def generate_salt(self):
        return str(uuid4().hex)

    def applyup(self, input_, boundaries=None):
        return self.apply('up', input_)

    def applydown(self, input_, boundaries=None):
        return self.apply('down', input_)

    def apply(self, direction, input_, boundaries=None):
        """Foma-apply the inputs in the direction of ``direction``.

        The method used is to write two files -- inputs.txt containing a newline-delimited
        list thereof and apply.sh which is a shell script that invokes flookup on inputs.txt
        to create outputs.txt -- and then parse the foma/flookup-generated outputs.txt file
        and then delete the three temporary files.  A more efficient implementation might be
        possible.

        :param str direction: 'up' or 'down', i.e., the direction in which to use the transducer
        :param str/list input_: a transcription string or list thereof.
        :param bool boundaries: whether or not to add word boundary symbols to the inputs and remove
            them from the outputs.
        :returns: a dictionary: ``{input1: [output1, output2, ...], input2: [...], ...}``
        """
        boundaries = boundaries if boundaries is not None else getattr(
            self, 'boundaries', False)
        if isinstance(input_, str):
            inputs = [input_]
        elif isinstance(input_, (list, tuple)):
            inputs = list(input_)
        else:
            return None
        directory = self.directory
        random_string = self.generate_salt()
        inputs_file_path = os.path.join(
            directory, 'inputs_%s.txt' % random_string)
        outputs_file_path = os.path.join(
            directory, 'outputs_%s.txt' % random_string)
        apply_file_path = os.path.join(
            directory, 'apply_%s.sh' % random_string)
        binary_path = self.get_file_path('binary')
        # Write the inputs to an '\n'-delimited file
        with codecs.open(inputs_file_path, 'w', 'utf8') as f:
            if boundaries:
                f.write(
                    '\n'.join(
                        input_.join([self.word_boundary_symbol,
                                     self.word_boundary_symbol])
                        for input_ in inputs))
            else:
                f.write('\n'.join(inputs))
        # Write the shell script that pipes the input file into flookup
        with codecs.open(apply_file_path, 'w', 'utf8') as f:
            f.write('#!/bin/sh\ncat %s | flookup %s%s' % (
                inputs_file_path,
                {'up': '', 'down': '-i '}.get(direction, '-i '),
                binary_path))
        os.chmod(apply_file_path, 0o744)
        # Execute the shell script and pipe its output to the output file
        with open(os.devnull, 'w') as devnull:
            with codecs.open(outputs_file_path, 'w', 'utf8') as outfile:
                p = Popen(apply_file_path, shell=False, stdout=outfile, stderr=devnull)
        p.communicate()
        # Parse the output file, clean up and return the parsed outputs
        with codecs.open(outputs_file_path, 'r', 'utf8') as f:
            result = self.foma_output_file2dict(f, remove_word_boundaries=boundaries)
        os.remove(inputs_file_path)
        os.remove(outputs_file_path)
        os.remove(apply_file_path)
        return result

    def foma_output_file2dict(self, file_, remove_word_boundaries=True):
        """Return the output file of a flookup apply request into a dictionary.
        :param file file_: utf8-encoded file object with tab-delimited i/o
            pairs.
        :param bool remove_word_boundaries: toggles whether word boundaries are
            removed in the output
        :returns: dictionary of the form ``{i1: [01, 02, ...], i2: [...],
            ...}``.
        .. note::
            The flookup foma utility returns '+?' when there is no output for a
            given input -- hence the replacement of '+?' with None below.
        """
        def word_boundary_remover(x):
            if (x[0:1], x[-1:]) == (self.word_boundary_symbol,
                                    self.word_boundary_symbol):
                return x[1:-1]
            else:
                return x
        if remove_word_boundaries:
            remover = word_boundary_remover
        else:
            remover = lambda x: x
        result = {}
        for line in file_:
            line = line.strip()
            if line:
                try:
                    i, o = map(remover, line.split('\t')[:2])
                except:
                    i = o = line
                result.setdefault(i, []).append({self.flookup_no_output: None}.get(o, o))
        return dict((k, filter(None, v)) for k, v in result.items())

    # Cf. http://code.google.com/p/foma/wiki/RegularExpressionReference#Reserved_symbols
    foma_reserved_symbols = [
        '\u0021', '\u0022', '\u0023', '\u0024', '\u0025',
        '\u0026', '\u0028', '\u0029', '\u002A', '\u002B', '\u002C', '\u002D',
        '\u002E', '\u002F', '\u0030', '\u003A', '\u003B', '\u003C', '\u003E',
        '\u003F', '\u005B', '\u005C', '\u005D', '\u005E', '\u005F', '\u0060',
        '\u007B', '\u007C', '\u007D', '\u007E', '\u00AC', '\u00B9', '\u00D7',
        '\u03A3', '\u03B5', '\u207B', '\u2081', '\u2082', '\u2192', '\u2194',
        '\u2200', '\u2203', '\u2205', '\u2208', '\u2218', '\u2225', '\u2227',
        '\u2228', '\u2229', '\u222A', '\u2264', '\u2265', '\u227A', '\u227B'
    ]

    # This is the string that flookup returns when an input has no output.
    flookup_no_output = '+?'

    default_word_boundary_symbol = '#'

    foma_reserved_symbols_patt = re.compile('[%s]' % ''.join(foma_reserved_symbols))

    def escape_foma_reserved_symbols(self, string):
        """Prepend foma reserved symbols with % to escape them."""
        return self.foma_reserved_symbols_patt.sub(lambda m: '%' + m.group(0), string)

    def delete_foma_reserved_symbols(self, string):
        """Delete foma reserved symbols -- good for names of defined regexes."""
        return self.foma_reserved_symbols_patt.sub('', string)

    def compile(self, timeout=30*60, verification_string=None):
        """Compile the foma FST's script.

        The superclass's ``run`` method performs the compilation request and
        cancels it if it exceeds ``timeout`` seconds.

        :param float/int timeout: how long to wait before terminating the
            compile process.
        :param str verification_string]: a string that will be found in the
            stdout of a successful foma request.
        :returns: ``None``.  Attribute values of the Foma FST object are
            altered to reflect the success (or not) of the compilation.  If
            successful, ``self.get_file_path('binary')`` will be return the
            absolute path to the compiled foma FST.

        """
        verification_string = verification_string or self.verification_string
        compiler_path = self.get_file_path('compiler')
        binary_path = self.get_file_path('binary')
        binary_mod_time = self.get_modification_time(binary_path)
        self.compile_succeeded = False
        try:
            returncode, output = self.run([compiler_path], timeout)
            if verification_string in output:
                if returncode == 0:
                    if (    os.path.isfile(binary_path) and
                            binary_mod_time != self.get_modification_time(
                                binary_path)):
                        self.compile_succeeded = True
                        self.compile_message = (
                            'Compilation process terminated successfully and'
                            ' new binary file was written.')
                    else:
                        self.compile_message = (
                            'Compilation process terminated successfully yet no'
                            ' new binary file was written.')
                else:
                    self.compile_message = 'Compilation process failed.'
            else:
                self.compile_message = (
                    'Foma script is not a well-formed %s %s.' %
                    (self.object_type, output))[:255]
        except Exception:
            self.compile_message = 'Compilation attempt raised an error.'
        if self.compile_succeeded:
            os.chmod(binary_path, 0o744)
        else:
            try:
                os.remove(binary_path)
            except Exception:
                pass
        self.compile_attempt = str(uuid4())

    def decombine(self, string):
        """Alter a string so that any unicode combining characters it contains
        are separated from their base characters by a space.  This was found to
        be necessary in order to sidestep a bug (?) of foma wherein a
        morphophonology formed by the composition of (a) a morphology with
        space-separated base and combining characters and (b) a phonology with
        adjacent base and combining characters was not recognizing
        transcriptions containing such combining characters, despite the fact
        that the phonology and morphology would both individually recognize
        such strings.  Without first "decombining" the phonological rules it is
        possible to create a vacuous phonology that when used to create a
        morphophonology results in a transducer that is identical to the
        original morphology in terms of states and transitions but differs only
        in its sigma value, i.e., the elements of the alphabet, where the
        morphophonology will have base/combining multicharacter symbols in its
        sigma that (somehow) prevent the
        """
        string_list = []
        for c in string:
            if unicodedata.combining(c):
                string_list.extend(['  ', c])
            else:
                string_list.append(c)
        return ''.join(string_list)

    def save_script(self, decombine=False):
        """Save the unicode value of ``self.script`` to disk.
        Also create the compiler shell script which will be used to compile the
        script.
        :param bool decombine: if ``True``, the lines of the script will be
            "decombined", see ``self.decombine`` above.
        :returns: the absolute path to the newly created foma FST script file.
        """
        try:
            self.make_directory_safely(self.directory)
            script_path = self.get_file_path('script')
            binary_path = self.get_file_path('binary')
            compiler_path = self.get_file_path('compiler')
            with codecs.open(script_path, 'w', 'utf8') as f:
                if decombine:
                    for line in self.script.splitlines(True):
                        if not line.strip().startswith('#'):
                            f.write(self.decombine(line))
                        else:
                            f.write(line)
                else:
                    f.write(self.script)
            # The compiler shell script loads the foma script and compiles it
            # to binary form.
            with open(compiler_path, 'w') as f:
                f.write('#!/bin/sh\nfoma -e "source %s" -e "regex %s;" '
                        '-e "save stack %s" -e "quit"' % (
                            script_path, self.object_type, binary_path))
            os.chmod(compiler_path, 0o744)
            return script_path
        except Exception:
            return None

    def get_tests(self):
        """Return as a dictionary any tests defined in the script.
        By convention established here, a line in a foma script that begins with
        "#test " signifies a test.  After "#test " there should be a string of
        characters followed by "->" followed by another string of characters.
        The first string is the lower side of the tape and the second is the
        upper side.
        """
        try:
            result = {}
            test_lines = [l[6:] for l in self.script.splitlines()
                          if l[:6] == '#test ']
            for l in test_lines:
                try:
                    i, o = map(str.strip, l.split('->'))
                    result.setdefault(i, []).append(o)
                except ValueError:
                    pass
            return result
        except Exception:
            return None

    def run_tests(self):
        """Run all tests defined in the script and return a report.
        :returns: a dictionary representing the report on the tests.
        A line in a script that begins with "#test " signifies a
        test.  After "#test " there should be a string of characters followed by
        "->" followed by another string of characters.  The first string is the
        lower side of the tape and the second is the upper side.
        """
        tests = self.get_tests()
        if not tests:
            return None
        results = self.applydown(tests.keys())
        return {t: {'expected': tests[t], 'actual': results[t]} for t in tests}


class PhonologyFST(FomaFST):
    """Represents a foma-based phonology finite-state transducer.
    """

    def __init__(self, parent_directory, **kwargs):
        kwargs['object_type'] = kwargs.get('object_type', 'phonology')
        super(PhonologyFST, self).__init__(parent_directory, **kwargs)

    boundaries = False


class MorphologyFST(FomaFST, Parse):
    """Represents a foma-based morphology finite-state transducer.
    .. note::
        The second superclass ``Parse`` provides the ``morpheme_splitter``
        property.
    """

    def __init__(self, parent_directory, **kwargs):
        self.rare_delimiter = kwargs.pop('rare_delimiter', '\u2980')
        kwargs['object_type'] = kwargs.get('object_type', 'morphology')
        super(MorphologyFST, self).__init__(parent_directory, **kwargs)

    @property
    def verification_string(self):
        """The verification string of a morphology varies depending on whether
        the script is written using the lexc formalism or the regular
        expression one.
        """
        if getattr(self, '_verification_string', None):
            return self._verification_string
        if getattr(self, 'script_type', None) == 'lexc':
            self._verification_string =  'Done!'
        else:
            self._verification_string =  'defined %s: ' % self.object_type
        return self._verification_string

    @property
    def file_type2extension(self):
        if getattr(self, '_file_type2extension', None):
            return self._file_type2extension
        else:
            self._file_type2extension = super(
                MorphologyFST, self).file_type2extension.copy()
            self._file_type2extension.update({
                'lexicon': '.pickle',
                'dictionary': '_dictionary.pickle',
            })
            return self._file_type2extension


class LanguageModel(Command, Parse):
    """Represents ngram language model objects.
    This class assumes that the elements of the model are morphemes, not words.
    Basically an interface to an LM toolkit that is mediated by Python
    subprocess control.
    Primary read methods are ``get_probabilities`` and ``get_probability_one``.
    Primary write methods are ``write_arpa`` and ``generate_trie``, which
    should be called in that order and which assume appropriate values for
    ``self.n`` and ``self.smoothing`` as well as a corpus (and possibly a
    vocabulary) file written at ``self.get_file_path('corpus')`` (and at
    ``self.get_file_path('vocabulary')``).
    .. note::
        At present, only support for the MITLM toolkit is implemented.
    .. note::
        The second superclass ``Parse`` provides the ``morpheme_only_splitter`` property
    """

    def __init__(self, parent_directory, **kwargs):
        self.rare_delimiter = kwargs.pop('rare_delimiter', '\u2980')
        self.start_symbol = kwargs.pop('start_symbol', '<s>')
        self.end_symbol = kwargs.pop('end_symbol', '</s>')
        kwargs['object_type'] = kwargs.get(
            'object_type', 'morpheme_language_model')
        super(LanguageModel, self).__init__(parent_directory, **kwargs)

    toolkits = {
        'mitlm': {
            'executable': 'estimate-ngram',
            'smoothing_algorithms': [
                # cf. http://code.google.com/p/mitlm/wiki/Tutorial
                'ML', 'FixKN', 'FixModKN', 'FixKNn', 'KN', 'ModKN', 'KNn'],
            'verification_string_getter': lambda x: 'Saving LM to %s' % x
        }
    }

    object_type2directory_name = {'morphemelanguagemodel': 'morpheme_language_model'}
    object_type2file_name = {'morphemelanguagemodel': 'morpheme_language_model'}

    @property
    def verification_string(self):
        return self.toolkits[self.toolkit]['verification_string_getter'](
            self.get_file_path('arpa'))

    @property
    def executable(self):
        return self.toolkits[self.toolkit]['executable']

    @property
    def file_type2extension(self):
        if getattr(self, '_file_type2extension', None):
            return self._file_type2extension
        else:
            self._file_type2extension = super(LanguageModel, self).file_type2extension.copy()
            self._file_type2extension.update({
                'corpus': '.txt',
                'arpa': '.lm',
                'trie': '.pickle',
                'vocabulary': '.vocab'
            })
            return self._file_type2extension

    space_splitter = re.compile('\s+')

    def get_probabilities(self, input_):
        """Return the probability of each sequence of morphemes in ``input_``.
        :param str/list input_: a string of space-delimited morphemes or a list
            thereof. Word boundary symbols will be added automatically and
            should not be included.
        :returns: a dictionary with morpheme sequences as keys and log
            probabilities as values.
        """
        if isinstance(input_, str):
            morpheme_sequences = [input_]
        elif isinstance(input_, (list, tuple)):
            morpheme_sequences = input_
        else:
            return None
        splitter = self.space_splitter
        morpheme_sequences = [
            (morpheme_sequence,
             [self.start_symbol] + splitter.split(morpheme_sequence) +
             [self.end_symbol])
            for morpheme_sequence in morpheme_sequences]
        trie = self.trie
        return {morpheme_sequence:
                self.get_probability_one(morpheme_sequence_list, trie)
                for morpheme_sequence, morpheme_sequence_list in
                morpheme_sequences}

    def get_probability_one(self, morpheme_sequence_list, trie=None):
        """Return the log probability of the input list of morphemes.

        :param list morpheme_sequence_list: a list of strings/unicode obejcts, each
            representing a morpheme.
        :param instance trie: a simplelm.LMTree instance encoding the LM.
        :returns: the log prob of the morpheme sequence.

        """
        if not trie:
            trie = self.trie
        return simplelm.compute_sentence_prob(trie, morpheme_sequence_list)

    def write_arpa(self, timeout):
        """Write ARPA-formatted LM file to disk.

        :param int/float timeout: how many seconds to wait before canceling the write attempt.
        :returns: None; an exception is raised if ARPA file generation fails.

        .. note::

            This method assumes that the attributes ``order`` and ``smoothing`` are
            defined and that appropriate corpus (and possibly vocabulary) files have
            been written.

        """

        verification_string = self.verification_string
        arpa_path = self.get_file_path('arpa')
        arpa_mod_time = self.get_modification_time(arpa_path)
        cmd = self.write_arpa_command
        returncode, output = self.run(cmd, timeout)
        succeeded = (verification_string in output and
                     returncode == 0 and
                     os.path.isfile(arpa_path) and
                     arpa_mod_time != self.get_modification_time(arpa_path))
        if not succeeded:
            raise Exception('method write_arpa failed.')

    @property
    def write_arpa_command(self):
        """Returns a list of strings representing a command to generate an ARPA
        file using the toolkit.
        """
        cmd = []
        if self.toolkit == 'mitlm':
            order = str(self.order)
            smoothing = self.smoothing or 'ModKN'
            cmd = [self.executable, '-o', order, '-s', smoothing,
                   '-t', self.get_file_path('corpus'), '-wl',
                   self.get_file_path('arpa')]
            if self.vocabulary:
                cmd += ['-v', self.get_file_path('vocabulary')]
        return cmd

    @property
    def vocabulary(self):
        """Return ``True`` if we have a vocabulary file."""
        if os.path.isfile(self.get_file_path('vocabulary')):
            return True
        return False

    def generate_trie(self):
        """Load the contents of an ARPA-formatted LM file into a
        ``simplelm.LMTree`` instance and pickle it.
        :returns: None; if successful, ``self.get_file_path('trie')`` points to
            a pickled ``simplelm.LMTree`` instance.
        """
        self._trie = simplelm.load_arpa(self.get_file_path('arpa'), 'utf8')
        pickle.dump(self._trie, open(self.get_file_path('trie'), 'wb'))

    @property
    def trie(self):
        """Return the ``simplelm.LMTree`` instance representing a trie interface to the LM
        if one is available or can be generated.

        """
        if isinstance(getattr(self, '_trie', None), simplelm.LMTree):
            return self._trie
        else:
            try:
                self._trie = pickle.load(open(self.get_file_path('trie'), 'rb'))
                return self._trie
            except Exception:
                try:
                    self.generate_trie()
                    return self._trie
                except Exception:
                    return None


class Cache:
    """For caching parses; basically a dict with some conveniences and pickle-based persistence.

    A MorphologicalParser instance can be expected to access and set keys via the familiar Python
    dictionary interface as well as request that the cache be persisted, i.e., by calling
    ``cache.persist()``.  Thus this class implements the following interface:

    - ``__setitem__(k, v)``
    - ``__getitem__(k)``
    - ``get(k, default)``
    - ``persist()``

    """

    def __init__(self, path=None):
        self.updated = False # means that ``self._store`` is in sync with persistent cache
        self.path = path # without a path, pickle-based persistence is impossible
        self._store = {}
        if self.path and os.path.isfile(self.path):
            try:
                self._store = pickle.load(open(self.path, 'rb'))
                if not isinstance(self._store, dict):
                    self._store = {}
            except Exception:
                pass

    def __setitem__(self, k, v):
        if k not in self._store:
            self.updated = True
        self._store[k] = v

    def __getitem__(self, k):
        return self._store[k]

    def __len__(self):
        return len(self._store)

    def get(self, k, default=None):
        return self._store.get(k, default)

    def update(self, dict_, **kwargs):
        old_keys = self._store.keys()
        self._store.update(dict_, **kwargs)
        if set(old_keys) != set(self._store.keys()):
            self.updated = True

    def persist(self):
        """Update the persistence layer with the value of ``self._store``.
        """
        if self.updated and self.path:
            pickle.dump(self._store, open(self.path, 'wb'))
            self.updated = False

    def clear(self, persist=False):
        """Clear the cache and its persistence layer.
        """
        self._store = {}
        if persist:
            self.updated = True
            self.persist()


class MorphologicalParser(FomaFST, Parse):
    """Represents a morphological parser: a morphophonology FST filtered by an ngram LM.

    The primary read method is ``parse``.  In order to function correctly,
    a MorphologicalParser instance must have ``morphology``, ``phonology`` and ``language_model``
    attributes whose values are fully generated and compiled ``Morphology``, ``Phonology`` and
    ``LanguageModel`` instances, respectively.

    .. note::

        The second superclass ``Parse`` provides the ``morpheme_splitter`` property.

    """

    def __init__(self, parent_directory, **kwargs):
        kwargs['object_type'] = kwargs.get('object_type', 'morphologicalparser')
        self.cache = kwargs.pop('cache', Cache())
        self.persist_cache = kwargs.pop('persist_cache', True)
        super(MorphologicalParser, self).__init__(parent_directory, **kwargs)

    # parsers transparently/automatically wrap input transcriptions in word
    # boundary symbols
    boundaries = False
    object_type2directory_name = {'morphologicalparser': 'morphological_parser'}
    object_type2file_name = {'morphologicalparser': 'morphophonology'}

    @property
    def cache(self):
        try:
            return self._cache
        except AttributeError:
            self._cache = Cache()
            return self._cache

    @cache.setter
    def cache(self, value):
        self._cache = value

    @property
    def verification_string(self):
        return 'defined %s: ' % self.object_type2file_name.get(
            self.object_type, self.object_type)

    def pretty_parse(self, input_,):
        """A convenience interface to the ``parse`` method which returns
        triplet list representations of parse.
        """
        parses = self.parse(input_, parse_objects=True)
        return {transcription: parse.triplet
                for transcription, (parse, candidates) in parses.items()}

    def parse(self, transcriptions, parse_objects=False, max_candidates=10):
        """Parse the input transcriptions.

        :param list transcriptions: unicode strings representing transcriptions of words.
        :param bool parse_objects: if True, instances of Parse will be returned.
        :param int max_candidates: max number of candidates to return.
        :returns: a dict from transcriptions to (parse, candidates) tuples.

        """

        if isinstance(transcriptions, str):
            transcriptions = [transcriptions]
        transcriptions = list(set(transcriptions))
        parsed = {}
        unparsed = []
        for transcription in transcriptions:
            cached_parse, cached_candidates = self.cache.get(transcription, (False, False))
            if cached_parse is not False:
                parsed[transcription] = cached_parse, cached_candidates
            else:
                unparsed.append(transcription)
        unparsed = self.get_candidates(unparsed) # This is where the foma subprocess is enlisted.
        for transcription, candidates in unparsed.items():
            parse, sorted_candidates = self.get_most_probable(candidates)
            if max_candidates:
                sorted_candidates = sorted_candidates[:max_candidates]
            self.cache[transcription] = parsed[transcription] = parse, sorted_candidates
        if self.persist_cache:
            self.cache.persist()
        if parse_objects:
            return dict((transcription, (self.get_parse_object(parse),
                                         map(self.get_parse_object, candidates)))
                        for transcription, (parse, candidates) in parsed.items())
        return parsed

    def get_parse_object(self, parse_string):
        """Return a ``Parse`` instance representation of the parse string that is aware
        of the delimiters of the parser that generated the parse string.

        """

        return Parse(parse_string,
                     morpheme_delimiters = getattr(self, 'morpheme_delimiters', None),
                     rare_delimiter = self.my_morphology.rare_delimiter)

    def get_most_probable(self, candidates):
        """Uses ``self.my_language_model`` to return the most probable of a
        list of candidate parses.
        :param list candidates: list of unicode strings representing
            morphological parses. These must be in 'f|g|c-f|g|c' format, i.e.,
            morphemes are ``self.rare_delimiter``-delimited form/gloss/category
            triples delimited by morpheme delimiters.
        :returns: 2-tuple: (the most probable candidate, the sorted candidates).
        """
        if not candidates:
            return None, []
        temp = []
        for candidate in candidates:
            lm_input = self.morpheme_splitter(candidate)[::2]
            if self.my_language_model.categorial:
                lm_input = [morpheme.split(self.my_morphology.rare_delimiter)[2]
                            for morpheme in lm_input]
            lm_input = ([self.my_language_model.start_symbol] + lm_input +
                        [self.my_language_model.end_symbol])
            temp.append(
                (candidate,
                 self.my_language_model.get_probability_one(lm_input)))
        #return sorted(temp, key=lambda x: x[1])[-1][0]
        sorted_candidates = [
            c[0] for c in sorted(temp, key=lambda x: x[1], reverse=True)]
        return sorted_candidates[0], sorted_candidates

    def get_candidates(self, transcriptions):
        """Returns the morphophonologically valid parses of the input
        transcription.
        :param list transcriptions: surface transcriptions of words.
        :returns: a dict from transcriptions to lists of strings representing
            candidate parses in 'form|gloss|category' format.
        """
        candidates = self.applyup(transcriptions)
        if not self.my_morphology.rich_upper:
            candidates = self.disambiguate(candidates)
        return candidates

    def disambiguate(self, candidates):
        """Return parse candidates with rich representations, i.e.,
        disambiguated.
        Note that this is only necessary when
        ``self.my_morphology.rich_upper==False``.
        :param dict candidates: keys are transcriptions, values are lists of
            strings representing morphological parses.  Since they are being
            disambiguated, we should expect these lists to be morpheme forms
            delimited by the language's delimiters.
        :returns: a dict of the same form as the input where the values are
            lists of richly represented morphological parses, i.e., in f|g|c
            format.
        This converts something like {'chiens': 'chien-s'} to
        {'chiens': 'chien|dog|N-s|PL|Phi'}.
        """
        def get_category(morpheme):
            if isinstance(morpheme, list):
                return morpheme[2]
            return morpheme
        def get_morpheme(morpheme):
            if isinstance(morpheme, list):
                return self.my_morphology.rare_delimiter.join(morpheme)
            return morpheme
        rules = self.my_morphology.rules_generated.split()
        dictionary_path = self.my_morphology.get_file_path('dictionary')
        try:
            dictionary = pickle.load(open(dictionary_path, 'rb'))
            result = {}
            for transcription, candidate_list in candidates.items():
                new_candidates = set()
                for candidate in candidate_list:
                    temp = []
                    morphemes = self.morpheme_splitter(candidate)
                    for index, morpheme in enumerate(morphemes):
                        if index % 2 == 0:
                            homographs = [[morpheme, gloss, category]
                                          for gloss, category in
                                          dictionary[morpheme]]
                            temp.append(homographs)
                        else:
                            temp.append(morpheme) # it's really a delimiter
                    for candidate in product(*temp):
                        # Only add a disambiguated candidate if its category
                        # sequence accords with the morphology's rules
                        if ''.join(get_category(x) for x in candidate) in rules:
                            new_candidates.add(
                                ''.join(get_morpheme(x) for x in candidate))
                result[transcription] = list(new_candidates)
            return result
        except Exception as error:
            LOGGER.warning(
                'some kind of exception occured in morphologicalparsers.py'
                ' disambiguate_candidates: %s', error)
            return dict((k, []) for k in candidates)

    # A parser's morphology and language_model objects should always be
    # accessed via the ``my_``-prefixed properties defined below. These
    # properties abstract away the complication # that ``self.my_X`` may be a
    # copy of ``self.X``.  The rationale behind this is that in a multi-user,
    # multithreaded environment the updating of a referenced object (e.g., LM)
    # should not silently change the behaviour of a parser -- the parser must
    # be explicitly rewritten and re-compiled in order for changes to
    # percolate. This level of abstraction is important in the context of parse
    # caching: if changes to, say, a referenced LM object were to silently
    # change the parses of a parser, the parser's cache would not be cleared
    # and those changes would not # surface in parsing behaviour.
    @property
    def my_morphology(self):
        try:
            return self._my_morphology
        except AttributeError:
            self._my_morphology = self.morphology
            return self._my_morphology

    @my_morphology.setter
    def my_morphology(self, value):
        self._my_morphology = value

    @property
    def my_language_model(self):
        try:
            return self._my_language_model
        except AttributeError:
            self._my_language_model = self.language_model
            return self._my_language_model

    @my_language_model.setter
    def my_language_model(self, value):
        self._my_language_model = value

    def export(self):
        """Return a dictionary containing all of the core attribute/values of
        the parser.
        """
        return {
            'phonology': {
                'word_boundary_symbol': getattr(
                    self.phonology, 'word_boundary_symbol', '#')
            },
            'morphology': {
                'word_boundary_symbol': getattr(
                    self.my_morphology, 'word_boundary_symbol', '#'),
                'rare_delimiter': getattr(
                    self.my_morphology, 'rare_delimiter', '\u2980'),
                'rich_upper': getattr(self.my_morphology, 'rich_upper', True),
                'rich_lower': getattr(self.my_morphology, 'rich_lower', True),
                'rules_generated': getattr(
                    self.my_morphology, 'rules_generated', '')
            },
            'language_model': {
                'rare_delimiter': getattr(
                    self.my_language_model, 'rare_delimiter', '\u2980'),
                'start_symbol': getattr(
                    self.my_language_model, 'start_symbol', '<s>'),
                'end_symbol': getattr(
                    self.my_language_model, 'end_symbol', '</s>'),
                'categorial': getattr(
                    self.my_language_model, 'categorial', False)
            },
            'parser': {
                'word_boundary_symbol': getattr(
                    self, 'word_boundary_symbol', '#'),
                'morpheme_delimiters': getattr(
                    self, 'morpheme_delimiters', None)
            }
        }

    @property
    def file_type2extension(self):
        """Extend the base class's property of the same name so that
        ``get_file_path`` works appropriately for this type of command."""
        if getattr(self, '_file_type2extension', None):
            return self._file_type2extension
        else:
            self._file_type2extension = super(
                MorphologicalParser, self).file_type2extension.copy()
            self._file_type2extension.update({'cache': '_cache.pickle'})
            return self._file_type2extension
