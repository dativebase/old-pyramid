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

"""Morphological parser model

This model includes a lot of functionality related to the generation of
attribute values and files that are necessary for a parser to parse input
transcriptions effectively.

In particular, the morphological parser model replicates the files and
attribute values that are crucial to maintaining parsing functionality even
when the referenced language model, morphology and/or phonology models are
altered or deleted.  It takes a successful ``generate_and_compile`` request to
change the parsing behaviour of a parser.

This approach was taken so that updates to subordinate objects/models would not
silently change parsing functionality and in order to ensure that a parser's
cache is in accordance with its parsing functionality.  If a generate and
compile request results in the change of a crucial attribute value or file,
then the cache is cleared.

A persistent cache is implemented via the ``parse`` table which maps
transcriptions to parses, relative to a morphological parser model.  Each
parser has a one-to-many collection in ``self.parses``.  However, interaction
with the parser's cache is mediated via a ``Cache`` instance (see below) that
provides a standardized interface to cached parses (i.e., self.cache[k],
self.cache[k] = v, self.cache.get(k, default), self.cache.update() and
self.cache.clear()), cf. ``lib/parser.py`` for a pickle-based Cache class.

The following attributes are those crucial to parsing functionality. (Note
that the files that are crucial to a parser's parsing functionality are
``morphophonology.foma``, ``morpheme_language_model.pickle`` and (if needed)
``morphology_dictionary.pickle``.)

``word_boundary_symbol``

    The apply method of phonology and morphological parser objecs prefixes and
    postfixes this string to inputs and removes it from outputs transparently.
    The parser inherits this value from the phonology it references; it assumes
    that the writer of the phonology script has used this string to represent
    word boundaries.

``morphology_rare_delimiter``

    This is an attribute of both morphology and morphemelanguagemodel models.
    A parser can only be successfully created or updated if the
    ``rare_delimiter`` value of its morphology and its LM are identical
    (assuming the LM is not categorial; if it is, then the rare delimiter is
    irrelevant).  This string affects how *all* LM files come out as well as
    how the morphology foma scripts are generated.

``language_model_start_symbol`` & ``language_model_end_symbol``

    These values are used in the construction of LMs and a parser cannot parse
    without knowing the correct values.

``language_model_categorial``

    This is an attribute of LMs. It determines whether the LM returns
    probabilities for morpheme sequences or simply category sequences. A
    parser needs to know its value in order to parse.

``morphology_rich_upper``

    This is an attribute of morphology models. It determines whether the upper
    side of the tape of a morphology represents the morphemes in its lexicon as
    form|gloss|category triples or simply as form singletons; it affects
    whether a parser must perform disambiguation on the output of its
    morphophonology prior to candidate ranking.

``morphology_rich_lower``

    This is analog of ``morphology_rich_upper`` on the lower side of the tape.

``morphology_rules_generated``

    This is an attribute of the morphology model. It is a string of word
    formation rules (strings of categories and delimiters) separated by spaces.
    It is used in the parser to filter out morphologically invalid
    disambiguations.

``morpheme_delimiters``

    The parser requires knowledge of the delimiters assumed by the morphology
    in order to disambiguate the output of its morphophonology (if necessary)
    and to pass a suitable input to the ``get_most_probable`` method.

"""

from uuid import uuid4
import os
import re
import codecs
from hashlib import md5
from sqlalchemy import Column, Sequence, ForeignKey, engine_from_config
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from sqlalchemy.orm import relation, sessionmaker
from .meta import Base, now
from old.lib.parser import MorphologicalParser, LanguageModel, MorphologyFST, PhonologyFST
from shutil import copyfile
import logging
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import transaction

LOGGER = logging.getLogger(__name__)


def get_engine(settings, prefix='sqlalchemy.'):
    return engine_from_config(settings, prefix)


def get_session_factory(engine):
    factory = sessionmaker()
    factory.configure(bind=engine)
    return factory


LOGGER = logging.getLogger(__name__)

class Parse(Base):
    """A parse is a parser-specific mapping from a transcription to a parse.
    """

    __tablename__ = 'parse'

    def __repr__(self):
        return '<Parse (%s)>' % self.id

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    id = Column(Integer, Sequence('parse_seq_id', optional=True),
            primary_key=True)
    transcription = Column(Unicode(1000))
    parse = Column(UnicodeText)
    candidates = Column(UnicodeText)
    parser_id = Column(Integer, ForeignKey('morphologicalparser.id', ondelete='SET NULL'))
    datetime_modified = Column(DateTime, default=now)


class MorphologicalParser(MorphologicalParser, Base):

    __tablename__ = 'morphologicalparser'

    def __repr__(self):
        return '<MorphologicalParser (%s)>' % self.id

    id = Column(Integer, Sequence('morphologicalparser_seq_id', optional=True), primary_key=True)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    phonology_id = Column(Integer, ForeignKey('phonology.id', ondelete='SET NULL'))
    phonology = relation('Phonology')
    morphology_id = Column(Integer, ForeignKey('morphology.id', ondelete='SET NULL'))
    morphology = relation('Morphology')
    language_model_id = Column(Integer, ForeignKey('morphemelanguagemodel.id', ondelete='SET NULL'))
    language_model = relation('MorphemeLanguageModel')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='MorphologicalParser.enterer_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='MorphologicalParser.modifier_id==User.id')
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    compile_succeeded = Column(Boolean, default=False)
    compile_message = Column(Unicode(255))
    compile_attempt = Column(Unicode(36)) # a UUID
    generate_succeeded = Column(Boolean, default=False)
    generate_message = Column(Unicode(255))
    generate_attempt = Column(Unicode(36)) # a UUID

    # MorphologicalParser().parses is a collection of cached parse objects, i.e.,
    # a mapping from transcriptions to parses.
    parses = relation('Parse', backref='parser', cascade='all, delete, delete-orphan')

    # These incidental attributes are initialized by the constructor.
    parent_directory = Column(Unicode(255))
    persist_cache = Column(Boolean)

    # These attributes are valued when ``self.write`` and (as a result) ``self.replicate_attributes``
    # are called.  Their purpose is to preserve enough values from ``self.language_model``
    # and ``self.morphology`` to allow the parser to parse even when those referenced models have
    # been altered or deleted.
    word_boundary_symbol = Column(Unicode(10))
    morphology_rare_delimiter = Column(Unicode(10))
    morphology_rich_upper = Column(Boolean)
    morphology_rich_lower = Column(Boolean)
    morphology_rules_generated = Column(UnicodeText)
    language_model_start_symbol = Column(Unicode(10))
    language_model_end_symbol = Column(Unicode(10))
    language_model_categorial = Column(Boolean, default=False)
    morpheme_delimiters = Column(Unicode(255))

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'name': self.name,
            'phonology': self.get_mini_dict_for(self.phonology),
            'morphology': self.get_mini_dict_for(self.morphology),
            'language_model': self.get_mini_dict_for(self.language_model),
            'description': self.description,
            'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.get_mini_user_dict(self.modifier),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'compile_succeeded': self.compile_succeeded,
            'compile_message': self.compile_message,
            'compile_attempt': self.compile_attempt,
            'generate_succeeded': self.generate_succeeded,
            'generate_message': self.generate_message,
            'generate_attempt': self.generate_attempt,
            'morphology_rare_delimiter': self.morphology_rare_delimiter
        }

    def compile(self, timeout=30*60, verification_string=None):
        """A wrapper around the superclass's ``compile`` method which sets
        ``self.changed`` to ``True`` if the compile request results in a
        changed binary foma file.  Note that we only perform the (potentially
        expensive) test for a file change if ``self.changed`` is false.  This
        makes sense because if ``self.changed`` is ``True``, some previous test
        has already uncovered a change so there is no need to retest.

        """
        binary_path = self.get_file_path('binary')
        binary_existed = False
        pre_hash = None
        if not self.changed:
            if os.path.isfile(binary_path):
                binary_existed = True
                pre_hash = self.get_hash(binary_path)
        super(MorphologicalParser, self).compile(timeout, verification_string)
        if not self.changed:
            if binary_existed:
                post_hash = self.get_hash(binary_path)
                self.changed = pre_hash == post_hash
            else:
                if os.path.isfile(binary_path):
                    self.changed = True

    def write(self):
        """Write the parser's morphophonology files and copy select attribute values of LM & morphology.

        :returns: None; but writes files to disk and sets attribute values.  An overview:

        1. Generate and write to disk the morphophonology script
        2. Make copies of the phonology, morphology and LM attributes relevant to parsing behaviour
        3. Copy the language model's pickled trie file
        4. Copy the morphology's pickled dictionary file (if lacking rich morpheme representations)

        """

        self.generate_succeeded = False
        self.generate_message = u''
        try:
            self.write_morphophonology_script()
            self.replicate_attributes()
            self.replicate_lm()
            self.replicate_morphology()
            self.replicate_phonology()
            self.generate_succeeded = True
            self.generate_message = ''
        except Exception as error:
            LOGGER.debug('Error in write method of morphparser model: %s %s',
                error.__class__.__name__, error)
            pass
        self.generate_attempt = str(uuid4())

    def write_morphophonology_script(self):
        """Generate and write to disk the morphophonology script:

            a. load the lexc/regex morphology script, making sure that the 'morphology'
               regex is defined and is enclosed in word boundary symbols.
            b. copy in the phonology script, replacing 'define phonology ...' with
               'define morphophonology .o. morphology ...'.

        """

        script_path = self.get_file_path('script')
        binary_path = self.get_file_path('binary')
        compiler_path = self.get_file_path('compiler')
        with open(compiler_path, 'w') as f:
            f.write('#!/bin/sh\nfoma -e "source %s" -e "regex morphophonology;" '
                '-e "save stack %s" -e "quit"' % (script_path, binary_path))
        os.chmod(compiler_path, 0o744)
        # NOTE: the phonology script is taken from the script as written to disk.  This
        # is because it is only this version that has had its combining characters separated
        # from their base characters (the user-created script is stored unaltered in the db;
        # see the ``save_script`` and ``decombine`` methods of ``lib/parser.py`` as well as

        phonology_script = codecs.open(self.phonology.get_file_path('script'), 'r', 'utf8').read()
        morphophonology = self.generate_morphophonology(phonology_script)
        morphology_script_path = self.morphology.get_file_path('script')
        if morphophonology:
            with codecs.open(script_path, 'w', 'utf8') as f:
                if self.morphology.script_type == 'lexc':
                    f.write('read lexc %s\n\n' % morphology_script_path)
                    f.write('define morphology;\n\n')
                else:
                    f.write('source %s\n\n' % morphology_script_path)
                # f.write('define morphology "%s" morphology "%s";\n\n' % (
                #     self.word_boundary_symbol, self.word_boundary_symbol))
                f.write('%s\n' % morphophonology)
        else:
            with codecs.open(script_path, 'w', 'utf8') as f:
                # Default morphophonology is the identity function.
                f.write('define morphophonology ?*;\n')

    def replicate_lm(self):
        """Copy the parser's LM's trie pickle and ARPA files to the parser's directory.

        If this results in a new trie pickle or arpa file being written, set ``self.changed = True``.

        """

        trie_path = self.language_model.get_file_path('trie')
        arpa_path = self.language_model.get_file_path('arpa')
        my_language_model = LanguageModel(parent_directory=self.directory)
        replicated_trie_path = my_language_model.get_file_path('trie')
        replicated_arpa_path = my_language_model.get_file_path('arpa')
        self.copy_file(trie_path, replicated_trie_path)
        self.copy_file(arpa_path, replicated_arpa_path)

    def replicate_morphology(self):
        """Copy the parser's morphology's foma script and dictionary pickle files (if
        either exist) to the parser's directory.

        If this results in any new files being written, set ``self.changed = True``.

        """

        my_morphology = MorphologyFST(parent_directory=self.directory)

        if not self.morphology.rich_upper:
            dictionary_path = self.morphology.get_file_path('dictionary')
            if os.path.isfile(dictionary_path):
                replicated_dictionary_path = my_morphology.get_file_path('dictionary')
                self.copy_file(dictionary_path, replicated_dictionary_path)

        script_path = self.morphology.get_file_path('script')
        if os.path.isfile(script_path):
            replicated_script_path = my_morphology.get_file_path('script')
            self.copy_file(script_path, replicated_script_path)

    def replicate_phonology(self):
        """Copy the parser's phonology's foma script and binary files (if
        either exist) to the parser's directory.

        If this results in any new files being written, set ``self.changed = True``.

        """

        my_phonology = PhonologyFST(parent_directory=self.directory)

        script_path = self.phonology.get_file_path('script')
        if os.path.isfile(script_path):
            replicated_script_path = my_phonology.get_file_path('script')
            self.copy_file(script_path, replicated_script_path)

        binary_path = self.phonology.get_file_path('binary')
        if os.path.isfile(binary_path):
            replicated_binary_path = my_phonology.get_file_path('binary')
            self.copy_file(binary_path, replicated_binary_path)

    def copy_file(self, src, dst):
        """Copy the file at ``src`` to ``dst``.

        Set ``self.changed`` to ``True`` if the copying results in a change to the
        file at ``dst``.  Note that we only perform the (potentially expensive) check
        for a change to the destination file if ``self.changed`` is ``False``, i.e., if
        the core attributes of our parser have not yet changed.

        """
        dst_existed = False
        pre_hash = None
        if not self.changed:
            if os.path.isfile(dst):
                dst_existed = True
                pre_hash = self.get_hash(dst)
        copyfile(src, dst)
        if not self.changed:
            if dst_existed:
                post_hash = self.get_hash(dst)
                self.changed = pre_hash == post_hash
            else:
                if os.path.isfile(dst):
                    self.changed = True

    def get_hash(self, path):
        """Return the MD5 hash of the file at ``path`` or ``None`` if there is no file there.
        """
        try:
            with open(path, 'rb') as f:
                return md5(f.read()).hexdigest()
        except Exception:
            return None

    def replicate_attributes(self):
        """Make copies of attr values of referenced core objects.

        If the values of any of these attributes change from what they were
        previously, set ``self.changed`` to ``True``.  This information can be
        used to decide whether to clear the cache.
        """
        changed = False
        if getattr(self, 'phonology', None):
            changed = self.set_attr('word_boundary_symbol', self.phonology.word_boundary_symbol, changed)
        changed = self.set_attr('morpheme_delimiters', self.morphology.morpheme_delimiters, changed)
        changed = self.set_attr('morphology_rare_delimiter', self.morphology.rare_delimiter, changed)
        changed = self.set_attr('morphology_rich_upper', self.morphology.rich_upper, changed)
        changed = self.set_attr('morphology_rich_lower', self.morphology.rich_lower, changed)
        changed = self.set_attr('morphology_rules_generated', self.morphology.rules_generated, changed)
        changed = self.set_attr('language_model_start_symbol', self.language_model.start_symbol, changed)
        changed = self.set_attr('language_model_end_symbol', self.language_model.end_symbol, changed)
        changed = self.set_attr('language_model_categorial', self.language_model.categorial, changed)
        self.changed = changed

    def generate_morphophonology(self, phonology_script):
        """Generate a morphophonology script.

        Actually, this function returns a string representing the portion of the 
        morphophonology script that follows the definition of the "morphology" FST.
        Return the ``phonology_script`` with 'define phonology ...' replaced by
        'define morphophonology morphology .o. ...'

        """

        phonology_definition_patt = re.compile('define( )+phonology( )+.+?[^%"];', re.DOTALL)
        define_phonology_patt = re.compile('define( )+phonology')
        if phonology_definition_patt.search(phonology_script):
            return define_phonology_patt.sub('define morphophonology morphology .o. ', phonology_script)
        return None

    @property
    def my_morphology(self):
        """Here we override the default ``my_morphology`` property and provide
        one which defaults to a minimal Morphology instance generated on the
        fly using attribute values copied from ``self.morphology`` at parser
        create/update time.  Note that we construct this Morphology instance
        with only those attributes needed to successfully call ``self.parse``.
        """
        try:
            return self._my_morphology
        except AttributeError:
            self._my_morphology = MorphologyFST(
                parent_directory = self.directory,
                rare_delimiter = self.morphology_rare_delimiter,
                word_boundary_symbol = self.word_boundary_symbol,
                rules_generated = self.morphology_rules_generated,
                rich_upper = self.morphology_rich_upper,
                rich_lower = self.morphology_rich_lower,
                morpheme_delimiters = self.morpheme_delimiters
            )
            return self._my_morphology

    @property
    def my_language_model(self):
        """Here we override the default ``my_language_model`` property and provide one which
        defaults to a minimal LanguageModel instance generated on the fly using attribute
        values copied from ``self.language_model`` at parser create/update time.  Note that
        we construct this LM instance with only those attributes needed to successfully call
        ``self.get_most_probable`` (which is called by ``self.parse``).

        """
        try:
            return self._my_language_model
        except AttributeError:
            self._my_language_model = LanguageModel(
                parent_directory = self.directory,
                start_symbol = self.language_model_start_symbol,
                end_symbol = self.language_model_end_symbol,
                categorial = self.language_model_categorial
            )
            return self._my_language_model

    @property
    def cache(self):
        try:
            return self._cache
        except AttributeError:
            self._cache = Cache(self)
            return self._cache

    @cache.setter
    def cache(self, value):
        self._cache = value


class Cache(object):
    """For caching parses; an interface to the MorphologicalParser().parses
    collection, a one-to-many relation.

    A MorphologicalParser instance can be expected to access and set "keys"
    (i.e,. transcriptions) via the familiar Python dictionary interface as well
    as request that the cache be persisted and cleared by calling ``persist()``
    and ``clear()``.  Thus this class implements the following interface:

    - ``__setitem__(k, v)``
    - ``__getitem__(k)``
    - ``get(k, default)``
    - ``persist()``
    - ``clear()``
    """

    def __init__(self, parser, settings, session_getter):
        # LOGGER.warn('DB CACHE CONSTRUCTED!')
        self.updated = False # means that ``self._store`` is in sync with persistent cache
        self.parser = parser
        self._store = {}
        self.settings = settings
        self.session_getter = session_getter

    def __setitem__(self, k, v):
        # LOGGER.warn('DB_CACHE[%s] = %s CALLED' % (k, v))
        if k not in self._store:
            self.updated = True
        self._store[k] = v

    def __getitem__(self, k):
        # LOGGER.warn('DB_CACHE.__getitem__(%s) CALLED' % k)
        try:
            return self._store[k]
        except KeyError as e:
            with transaction.manager:
                dbsession = self.session_getter(self.settings)
                parse = dbsession.query(Parse).filter(
                    Parse.parser_id==self.parser.id).filter(
                    Parse.transcription==k).first()
                if parse:
                    # LOGGER.warn('GOT %s FROM DB IN DB_CACHE' % k)
                    self._store[k] = parse.parse, json.loads(parse.candidates)
                    return self._store[k]
                else:
                    raise e

    def get(self, k, default=None):
        try:
            return self[k]
        except KeyError:
            # LOGGER.warn('DB_CACHE.get(%s, %s) RETURNED %s' % (k, default, default))
            return default

    def update(self, dict_, **kwargs):
        old_keys = self._store.keys()
        self._store.update(dict_, **kwargs)
        if set(old_keys) != set(self._store.keys()):
            self.updated = True

    def persist(self):
        """Update the persistence layer with the value of ``self._store``.
        """
        if self.updated:
            with transaction.manager:
                dbsession = self.session_getter(self.settings)
                persisted = [
                    parse.transcription for parse in dbsession.query(Parse).\
                    filter(Parse.parser_id==self.parser.id).\
                    filter(Parse.transcription.in_(self._store.keys())).all()]
                unpersisted = [Parse(transcription=transcription,
                                    parse=parse,
                                    candidates = self.json_dumps_candidates(candidates),
                                    parser=self.parser)
                            for transcription, (parse, candidates) in self._store.items()
                            if transcription not in persisted]
                dbsession.add_all(unpersisted)
                transaction.commit()
                # LOGGER.warn('DB_CACHE: PERSISTED %s' % u', '.join([p.transcription for p in unpersisted]))
                self.updated = False

    def json_dumps_candidates(self, candidates):
        candidates = json.dumps(candidates)
        if len(candidates) > 65000:
            return json.dumps(candidates[:500])
        else:
            return candidates

    def clear(self, persist=False):
        """Clear the cache and its persistence layer.
        This should be called if any of the attribute values or files that
        affect parsing functionality are altered. Currently,
        ``generate_and_compile_parser`` calls ``parser.cache.clear()`` if, in
        the course of generating and compiling the parser's files, the parser
        changes.
        """
        self._store = {}
        if persist:
            engine = create_engine(self.settings['sqlalchemy.url'])
            Session = sessionmaker(bind=engine)
            dbsession = Session()
            delete = Parse.__table__.delete().where(
                Parse.__table__.c.parser_id==self.parser.id)
            dbsession.execute(delete)
            dbsession.commit()

    def export(self):
        """Update the local store with the persistence layer and return the store.
        """
        with transaction.manager:
            dbsession = self.session_getter(self.settings)
            persisted = {p.transcription: (p.parse, json.loads(p.candidates))
                         for p in dbsession.query(Parse).filter(
                             Parse.parser_id==self.parser.id).all()}
            self._store.update(persisted)
            return self._store
