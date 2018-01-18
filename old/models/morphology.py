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

"""Morphology model"""

import codecs
import os
import hashlib
import pickle
from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from sqlalchemy.orm import relation
from .meta import Base, now
from old.lib.parser import MorphologyFST
import logging

log = logging.getLogger(__name__)

class Morphology(MorphologyFST, Base):

    __tablename__ = 'morphology'

    def __repr__(self):
        return '<Morphology (%s)>' % self.id

    id = Column(Integer, Sequence('morphology_seq_id', optional=True), primary_key=True)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    script_type = Column(Unicode(5))
    lexicon_corpus_id = Column(Integer, ForeignKey('corpus.id', ondelete='SET NULL'))
    lexicon_corpus = relation('Corpus', primaryjoin='Morphology.lexicon_corpus_id==Corpus.id')
    rules_corpus_id = Column(Integer, ForeignKey('corpus.id', ondelete='SET NULL'))
    rules_corpus = relation('Corpus', primaryjoin='Morphology.rules_corpus_id==Corpus.id')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='Morphology.enterer_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='Morphology.modifier_id==User.id')
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
    compile_succeeded = Column(Boolean, default=False)
    compile_message = Column(Unicode(255))
    compile_attempt = Column(Unicode(36)) # a UUID
    generate_attempt = Column(Unicode(36)) # a UUID
    extract_morphemes_from_rules_corpus = Column(Boolean, default=False)
    rules_generated = Column(UnicodeText) # word formation rules (i.e., strings of categories and delimiters) separated by spaces -- system-generated value
    rules = Column(UnicodeText) # word formation rules (i.e., strings of categories and delimiters) separated by spaces -- user-generated value
    rich_upper = Column(Boolean, default=False) # if True, the morphemes on the upper side of the tape are in <f|g|c> forma, else f format
    rich_lower = Column(Boolean, default=False) # if True, the morphemes on the lower side of the tape are in <f|g|c> forma, else f format
    include_unknowns = Column(Boolean, default=False) # if True, morphemes of unknown category will be added to lexicon.
    # NOTE: the include_unknowns attribute currently has no effect: it turned out to be a major complication!

    # These incidental attributes are initialized by the constructor.
    parent_directory = Column(Unicode(255))
    word_boundary_symbol = Column(Unicode(10))
    rare_delimiter = Column(Unicode(10))
    morpheme_delimiters = Column(Unicode(255))

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'name': self.name,
            'lexicon_corpus': self.get_mini_dict_for(self.lexicon_corpus),
            'rules_corpus': self.get_mini_dict_for(self.rules_corpus),
            'script_type': self.script_type,
            'description': self.description,
            'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.get_mini_user_dict(self.modifier),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'compile_succeeded': self.compile_succeeded,
            'compile_message': self.compile_message,
            'compile_attempt': self.compile_attempt,
            'generate_attempt': self.generate_attempt,
            'extract_morphemes_from_rules_corpus': self.extract_morphemes_from_rules_corpus,
            'rules': self.rules,
            'rules_generated': self.rules_generated,
            'rich_upper': self.rich_upper,
            'rich_lower': self.rich_lower,
            'include_unknowns': self.include_unknowns
        }

    def generate_rules_and_lexicon(self):
        try:
            return self._generate_rules_and_lexicon()
        except Exception as e:
            log.warn('GOT EXCEPTION TRYING TO GENERATE RULES AND LEXICON')
            log.warn(e)
            return [], {}

    def _generate_rules_and_lexicon(self):
        """Generate morphotactic rules and a lexicon for this morphology based on its corpora.

        :returns: 2-tuple: <rules, morphemes>

        """

        # Get a function that will split words into morphemes
        morpheme_splitter = self.morpheme_splitter
        # Get the unique morphemes from the lexicon corpus
        morphemes = {}
        if (self.lexicon_corpus and
            (not self.rules_corpus or
            self.lexicon_corpus.id != self.rules_corpus.id)):
            for form in self.lexicon_corpus.forms:
                new_morphemes = self._extract_morphemes_from_form(form, morpheme_splitter)
                for pos, data in new_morphemes:
                    morphemes.setdefault(pos, set()).add(data)
        # Get the pos sequences (and morphemes) from the user-specified ``rules`` string value or else from the 
        # words in the rules corpus.
        pos_sequences = set()
        if self.rules:
            for pos_sequence_string in self.rules.split():
                pos_sequence = tuple(morpheme_splitter(pos_sequence_string))
                pos_sequences.add(pos_sequence)
        else:
            for form in self.rules_corpus.forms:
                new_pos_sequences, new_morphemes = form.extract_word_pos_sequences(
                    self.unknown_category, morpheme_splitter,
                    self.extract_morphemes_from_rules_corpus)
                if new_pos_sequences:
                    pos_sequences |= new_pos_sequences
                    for pos, data in new_morphemes:
                        morphemes.setdefault(pos, set()).add(data)
        pos_sequences = self._filter_invalid_sequences(pos_sequences, morphemes)
        # sort and delistify the rules and lexicon
        pos_sequences = sorted(pos_sequences)
        morphemes = dict([(pos, sorted(data)) for pos, data in morphemes.items()])
        return pos_sequences, morphemes

    def _extract_morphemes_from_form(self, form, morpheme_splitter):
        """Return the morphemes in ``form`` as a list of tuples of the form (pos, (mb, mg)).

        """

        morphemes = []
        if not form.syntactic_category_string:
            return morphemes
        sc_words = form.syntactic_category_string.split()
        mb_words = form.morpheme_break.split()
        mg_words = form.morpheme_gloss.split()
        for sc_word, mb_word, mg_word in zip(sc_words, mb_words, mg_words):
            pos_sequence = morpheme_splitter(sc_word)[::2]
            morpheme_sequence = morpheme_splitter(mb_word)[::2]
            gloss_sequence = morpheme_splitter(mg_word)[::2]
            for pos, morpheme, gloss in zip(pos_sequence, morpheme_sequence, gloss_sequence):
                if pos != self.unknown_category:
                    morphemes.append((pos, (morpheme, gloss)))
        return morphemes

    def _filter_invalid_sequences(self, pos_sequences, morphemes):
        """Remove category sequences from pos_sequences if they contain categories not listed as 
        keys of the morphemes dict or if they contain delimiters not listed in self.delimiters.

        """

        if not morphemes:
            return pos_sequences
        if self.extract_morphemes_from_rules_corpus:
            return pos_sequences
        valid_elements = set(list(morphemes.keys()) + self.delimiters)
        new_pos_sequences = set()
        for pos_sequence in pos_sequences:
            pos_sequence_set = set(pos_sequence)
            if pos_sequence_set & valid_elements == pos_sequence_set:
                new_pos_sequences.add(pos_sequence)
        return new_pos_sequences

    def generate_dictionary(self, lexicon):
        """Return a dictionary of lexical items, i.e., a mapping from morpheme forms to lists of gloss, category 2-tuples.

        :param dict lexicon: keys are categories and values are lists of 2-tuples of the form <form, gloss>.

        This function need only be called if ``self.rich_upper`` is set to ``False``, in which case
        the morphology will parse, e.g., chien-s to chien-s and the dictionary will be needed
        to disambiguate the parse into richer representations, e.g.,
        ['chien|dog|N-s|PL|Num', 'chien|dog|N-s|plrl|Phi'].

        """
        dictionary = {}
        for category, data in lexicon.items():
            for form, gloss in data:
                dictionary.setdefault(form, []).append((gloss, category))
        return dictionary

    def write(self, unknown_category):
        """Write the files of the morphology (script, compiler, lexicon,
        dictionary) to disk.

        :param unicode unknown_category: what the system uses to mark morphemes
            without categories.
        :returns: None; side-effects: generates data structures, writes them to
            disk, specifies values of the morphology object.

        .. note::

            The foma script is not saved to the database as an attribute of the
            morphology model because it is potentially huge, i.e., tens to
            hundreds of MB.

        """

        self.unknown_category = unknown_category
        rules, lexicon = self.generate_rules_and_lexicon()
        self.rules_generated = u' '.join(map(u''.join, rules))
        pickle.dump(lexicon, open(self.get_file_path('lexicon'), 'wb'))
        if not self.rich_upper:
            dictionary = self.generate_dictionary(lexicon)
            pickle.dump(dictionary, open(self.get_file_path('dictionary'), 'wb'))
        script_path = self.get_file_path('script')
        binary_path = self.get_file_path('binary')
        compiler_path = self.get_file_path('compiler')
        with open(compiler_path, 'w') as f:
            if self.script_type == 'lexc':
                f.write('#!/bin/sh\nfoma -e "read lexc %s" -e "save stack %s" -e "quit"' % (
                        script_path, binary_path))
            else:
                f.write('#!/bin/sh\nfoma -e "source %s" -e "regex morphology;" '
                    '-e "save stack %s" -e "quit"' % (script_path, binary_path))
        os.chmod(compiler_path, 0o744)
        morphology_generator = self.get_morphology_generator(rules, lexicon)
        with codecs.open(script_path, 'w', 'utf8') as f:
            for line in morphology_generator:
                f.write(line)

    def get_morphology_generator(self, pos_sequences, morphemes):
        """Return a generator that yields lines of a foma morphology script.

        :param list pos_sequences: a sorte list of tuples containing sequences of categories and morpheme delimiters
        :param dict morphemes: keys are categories, values are lists of (form, gloss) 2-tuples
        :returns: generator object that yields lines of a foma morphology script

        """
        if self.script_type == 'lexc':
            return self._get_lexc_morphology_generator(morphemes, pos_sequences)
        else:
            return self._get_regex_morphology_generator(morphemes, pos_sequences)

    def _get_lexc_morphology_generator(self, morphemes, pos_sequences):
        """Return a generator that yields lines of a foma script representing the morphology using the lexc formalism,
        cf. https://code.google.com/p/foma/wiki/MorphologicalAnalysisTutorial.

        :param dict morphemes: a dict from category names to lists of (form, gloss) tuples.
        :param list pos_sequences: a sorted list of tuples containing category names and morpheme delimiters.
        :yields: lines of a lexc foma script

        The OLD generates the names for lexc lexica from category (POS) plus delimiter sequences by joining
        the categories and delimiters into a string and using that string to generate an MD5 hash.  Thus the
        category sequence ('Asp', '-', 'V', '-', 'Agr') would imply a root category MD5('Asp-V-Agr') as well
        as the following continuation classes MD5('-V-Agr') MD5('V-Agr') MD5('-Agr') MD5('Agr')

        """

        # If not rich_upper, remove homographs from morphemes
        if not self.rich_upper:
            morphemes = dict((pos, sorted(set((mb, None) for mb, mg in morph_list)))
                    for pos, morph_list in morphemes.items())
        roots = []
        continuation_classes = set()
        for sequence in pos_sequences:
            roots.append(self._pos_sequence2lexicon_name(sequence))
            for index in range(len(sequence)):
                continuation_classes.add(sequence[index:])
        continuation_classes = sorted(continuation_classes, key=len, reverse=True)
        yield u'LEXICON Root\n\n'
        for root in roots:
            yield '%s ;\n' % root
        yield u'\n\n'
        for continuation_class in continuation_classes:
            yield u'LEXICON %s\n\n' % self._pos_sequence2lexicon_name(continuation_class)
            for line in self._get_lexicon_entries_generator(continuation_class, morphemes):
                yield line

    def _pos_sequence2lexicon_name(self, pos_sequence):
        """Return a foma lexc lexicon name for the tuple of categories and delimiters; output is an MD5 hash."""
        return hashlib.md5(u''.join(pos_sequence).encode('utf8')).hexdigest()

    def _get_lexicon_entries_generator(self, pos_sequence, morphemes):
        """Return a generator that yields a line for each entry in a lexc LEXICON based on a POS sequence.

        :param tuple pos_sequence: something like ('N', '-', 'Ninf') or ('-', 'Ninf').
        :param dict morphemes: {'N': [(u'chien', u'dog'), (u'chat', u'cat'), ...], 'V': ...}
        :yields: lines that comprise the entries in a foma lexc LEXICON declaration.

        """
        if len(pos_sequence) == 1:
            next_class = u'#'
        else:
            next_class = self._pos_sequence2lexicon_name(pos_sequence[1:])
        first_element = pos_sequence[0]
        if first_element in self.delimiters:
            yield u'%s %s;\n' % (first_element, next_class)
        else:
            our_morphemes = morphemes.get(first_element, [])
            for form, gloss in our_morphemes:
                form = self.escape_foma_reserved_symbols(form)
                # Rich morphemes means m=<f|g|c>, impoverished means m=f
                if self.rich_upper or self.rich_lower:
                    gloss = self.escape_foma_reserved_symbols(gloss)
                    category_name = self.escape_foma_reserved_symbols(first_element)
                    if self.rich_upper and self.rich_lower:
                        yield u'%s %s;\n' % (self.rare_delimiter.join([form, gloss, category_name]), next_class)
                    elif self.rich_upper:
                        yield u'%s:%s %s;\n' % (
                            self.rare_delimiter.join([form, gloss, category_name]), form, next_class)
                    else:
                        yield u'%s:%s %s;\n' % (
                            form, self.rare_delimiter.join([form, gloss, category_name]), next_class)
                else:
                    yield u'%s %s;\n' % (form, next_class)
        yield u'\n\n'

    def _get_regex_morphology_generator(self, morphemes, pos_sequences):
        """Return a generator that yields lines of a foma script representing the morphology using standard regular expressions.
        Contrast this with the lexc approach utilized by ``get_lexc_morphology_generator``.

        :param dict morphemes: a dict from category names to lists of (form, gloss) tuples.
        :param list pos_sequences: a sorted list of tuples  whose elements are categories and morpheme delimiters.
        :yields: lines of a regex foma script

        """

        for line in self._get_lexicon_generator(morphemes):
            yield line
        yield u'\n\n'
        for line in self._get_word_formation_rules_generator(pos_sequences):
            yield line

    def _get_morpheme_representation(self, **kwargs):
        """Return a rich representation of the morpheme-as-FST (i.e., <f|g|c>:f) or an impoverished one (i.e., f:f).
        """
        form = kwargs['mb']
        if self.rich_upper or self.rich_lower:

            delimiter = kwargs['delimiter']
            gloss = kwargs['mg']
            category = kwargs['pos']
            if self.rich_upper and self.rich_lower:
                return u' '.join(map(self.escape_foma_reserved_symbols,
                                     list(delimiter.join([form, gloss, category]))))
            else:
                tmp = u'%s%s%s%s' % (delimiter, gloss, delimiter, category)
                if self.rich_upper:
                    return u'%s "%s":0' % (u' '.join(map(
                        self.escape_foma_reserved_symbols, list(form))), tmp)
                else:
                    return u'%s 0:"%s"' % (u' '.join(map(
                        self.escape_foma_reserved_symbols, list(form))), tmp)
        else:
            return u' '.join(map(self.escape_foma_reserved_symbols, list(form)))

    def _get_lexicon_generator(self, morphemes):
        """Return a generator that yields lines of a foma script defining a lexicon.

        :param morphemes: dict from category names to lists of (mb, mg) tuples.
        :yields: unicode object (lines) that comprise a valid foma script defining a lexicon.

        .. note::

            The presence of a form of category N with a morpheme break value of 'chien' and
            a morpheme gloss value of 'dog' will result in the regex defined as 'N' having
            'c h i e n "|dog|N":0' as one of its disjuncts.  This is a transducer that maps
            'chien|dog|N' to 'chien', i.e,. '"|dog|N"' is a multi-character symbol that is mapped
            to the null symbol, i.e., '0'.  Note also that the vertical bar '|' character is 
            not actually used -- the delimiter character is actually that defined in
            ``utils.rare_delimiter`` which, by default, is U+2980 'TRIPLE VERTICAL BAR
            DELIMITER'.

        """
        delimiter = self.rare_delimiter
        for pos, data in sorted(morphemes.items()):
            foma_regex_name = self._get_valid_foma_regex_name(pos)
            if foma_regex_name:
                yield u'define %s [\n' % foma_regex_name
                if data:
                    if not (self.rich_upper or self.rich_lower):
                        data = sorted(set((mb, None) for mb, mg in data))
                    for mb, mg in data[:-1]:
                        yield u'    %s |\n' % self._get_morpheme_representation(
                                mb=mb, mg=mg, pos=pos, delimiter=delimiter)
                    yield u'    %s \n' % self._get_morpheme_representation(
                            mb=data[-1][0], mg=data[-1][1], pos=pos, delimiter=delimiter)
                yield u'];\n\n'

    def _get_valid_foma_regex_name(self, candidate):
        """Return the candidate foma regex name with all reserved symbols removed and suffixed
        by "Cat".  This prevents conflicts between regex names and symbols in regexes.

        """
        if candidate == self.unknown_category:
            return 'unknownCat'
        name = self.delete_foma_reserved_symbols(candidate)
        if not name:
            return None
        return u'%sCat' % name

    def _pos_sequence2foma_disjunct(self, pos_sequence):
        """Return a foma disjunct representing a POS sequence.

        :param tuple pos_sequence: a tuple where the oddly indexed elements are 
            delimiters and the evenly indexed ones are category names.
        :returns: a unicode object representing a foma disjunct, e.g., u'AGR "-" V'

        """
        tmp = []
        for index, element in enumerate(pos_sequence):
            if index % 2 == 0:
                tmp.append(self._get_valid_foma_regex_name(element))
            else:
                tmp.append('"%s"' % element)
        if None in tmp:
            return None
        return u' '.join(tmp)

    def _get_word_formation_rules_generator(self, pos_sequences):
        """Return a generator that yields lines for a foma script defining morphological rules.

        :param list pos_sequences: tuples containing categories and delimiters
        :yields: unicode objects (lines) that comprise a valid foma script defining morphological rules

        """
        yield u'define morphology (\n'
        foma_disjuncts = list(
            filter(None, map(self._pos_sequence2foma_disjunct, pos_sequences)))
        if foma_disjuncts:
            for foma_disjunct in foma_disjuncts[:-1]:
                yield u'    (%s) |\n' % foma_disjunct
            yield u'    (%s) \n' % foma_disjuncts[-1]
        yield u');\n\n'
