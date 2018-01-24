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

"""Machinery for functional tests for the OLD Pyramid app."""

from io import StringIO, BytesIO
import gzip
import json
import logging
import os
import random
from time import sleep
from unittest import TestCase

import inflect
from paste.deploy.converters import asbool
from paste.deploy import appconfig
from pyramid import testing
from pyramid.paster import setup_logging
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import webtest

from old import main, db_session_factory_registry
import old.lib.helpers as h
from old.lib.dbutils import (
    get_model_names,
    DBUtils
)
from old.models.meta import Base
import old.models.modelbuilders as omb
from old.views.tags import Tags
import old.models as old_models


LOGGER = logging.getLogger(__name__)


__all__ = ['TestView', 'add_SEARCH_to_web_test_valid_methods', 'get_file_size']


def add_SEARCH_to_web_test_valid_methods():
    """Hack to prevent webtest from printing warnings when SEARCH method is
    used.
    """
    new_valid_methods = list(webtest.lint.valid_methods)
    new_valid_methods.append('SEARCH')
    webtest.lint.valid_methods = tuple(new_valid_methods)


CONFIG_FILE = 'test.ini'
SETTINGS = appconfig('config:{}'.format(CONFIG_FILE), relative_to='.')
CONFIG = {
    '__file__': SETTINGS['__file__'],
    'here': SETTINGS['here']
}
APP = webtest.TestApp(main(CONFIG, **SETTINGS))
dburl = SETTINGS['sqlalchemy.url']
Session = db_session_factory_registry.get_session(SETTINGS)


class TestView(TestCase):
    """Base test view for testing OLD Pyramid views.

    Example usage within a method::

        res = self.app.get(
            '/forms', status=200,
            extra_environ={'test.authentication.role': 'viewer'})
    """

    inflect_p = inflect.engine()
    inflect_p.classical()

    @classmethod
    def tearDownClass(cls):
        Session.close_all()

    def setUp(self):
        self.default_setup()
        self.create_db()

    def tearDown(self, **kwargs):
        """Clean up after a test."""
        db = DBUtils(self.dbsession, self.settings)
        clear_all_tables = kwargs.get('clear_all_tables', False)
        dirs_to_clear = kwargs.get('dirs_to_clear', [])
        dirs_to_destroy = kwargs.get('dirs_to_destroy', [])
        if clear_all_tables:
            db.clear_all_tables(['language'])
        else:
            self.clear_all_models(self.dbsession)
        for dir_path in dirs_to_clear:
            h.clear_directory_of_files(getattr(self, dir_path))
        for dir_name in dirs_to_destroy:
            h.destroy_all_directories(self.inflect_p.plural(dir_name),
                                      self.settings)
        self.tear_down_dbsession()

    def tear_down_dbsession(self):
        self.dbsession.commit()
        Session.remove()

    def default_setup(self):
        self.settings = SETTINGS
        self.config = CONFIG
        self.Session = Session
        self.dbsession = Session()
        self.app = APP
        setup_logging('test.ini#loggers')
        self._setattrs()
        self._setcreateparams()

    def create_db(self):
        # Create the database tables
        h.create_OLD_directories(self.settings)
        languages = omb.get_language_objects(self.settings['here'],
                                             truncated=True)
        administrator = omb.generate_default_administrator(
            settings=self.settings)
        contributor = omb.generate_default_contributor(
            settings=self.settings)
        viewer = omb.generate_default_viewer(settings=self.settings)
        Base.metadata.drop_all(bind=self.dbsession.bind, checkfirst=True)
        self.dbsession.commit()
        Base.metadata.create_all(bind=self.dbsession.bind, checkfirst=True)
        self.dbsession.add_all(languages + [administrator, contributor, viewer])
        self.dbsession.commit()

    def clear_all_models(self, dbsession, retain=('Language',)):
        """Convenience function for removing all OLD models from the database.
        The retain parameter is a list of model names that should not be
        cleared.
        """
        for model_name in get_model_names():
            if model_name not in retain:
                model = getattr(old_models, model_name)
                if not issubclass(model, old_models.Model):
                    continue
                models = dbsession.query(model).all()
                for model in models:
                    dbsession.delete(model)
        dbsession.commit()

    def _setattrs(self):
        """Set a whole bunch of instance attributes that are useful in tests."""
        self.extra_environ_view = {'test.authentication.role': 'viewer'}
        self.extra_environ_contrib = {'test.authentication.role':
                                      'contributor'}
        self.extra_environ_admin = {'test.authentication.role':
                                    'administrator'}
        self.extra_environ_view_appset = {'test.authentication.role': 'viewer',
                                          'test.application_settings': True}
        self.extra_environ_contrib_appset = {
            'test.authentication.role': 'contributor',
            'test.application_settings': True}
        self.extra_environ_admin_appset = {
            'test.authentication.role': 'administrator',
            'test.application_settings': True}
        self.json_headers = {'Content-Type': 'application/json'}
        self.here = self.settings['here']
        self.files_path = h.get_old_directory_path(
            'files', settings=self.settings)
        self.reduced_files_path = h.get_old_directory_path(
            'reduced_files', settings=self.settings)
        self.test_files_path = os.path.join(
            self.here, 'old', 'tests', 'data', 'files')
        self.create_reduced_size_file_copies = asbool(self.settings.get(
            'create_reduced_size_file_copies', False))
        self.preferred_lossy_audio_format = self.settings.get(
            'preferred_lossy_audio_format', 'ogg')
        self.corpora_path = h.get_old_directory_path(
            'corpora', settings=self.settings)
        self.test_datasets_path = os.path.join(
            self.here, 'old', 'tests', 'data', 'datasets')
        self.test_scripts_path = os.path.join(
            self.here, 'old', 'tests', 'scripts')
        self.loremipsum100_path = os.path.join(
            self.test_datasets_path, 'loremipsum_100.txt')
        self.loremipsum1000_path = os.path.join(
            self.test_datasets_path, 'loremipsum_1000.txt')
        self.loremipsum10000_path = os.path.join(
            self.test_datasets_path, 'loremipsum_10000.txt')
        self.users_path = h.get_old_directory_path(
            'users', settings=self.settings)
        self.morphologies_path = h.get_old_directory_path(
            'morphologies', settings=self.settings)
        self.morphological_parsers_path = h.get_old_directory_path(
            'morphological_parsers', settings=self.settings)
        self.phonologies_path = h.get_old_directory_path(
            'phonologies', settings=self.settings)
        self.morpheme_language_models_path = h.get_old_directory_path(
            'morpheme_language_models', settings=self.settings)
        self.test_phonologies_path = os.path.join(
            self.here, 'old', 'tests', 'data', 'phonologies')
        self.test_phonology_script_path = os.path.join(
            self.test_phonologies_path, 'test_phonology.script')
        self.test_malformed_phonology_script_path = os.path.join(
            self.test_phonologies_path, 'test_phonology_malformed.script')
        self.test_phonology_no_phonology_script_path = os.path.join(
            self.test_phonologies_path, 'test_phonology_malformed.script')
        self.test_medium_phonology_script_path = os.path.join(
            self.test_phonologies_path, 'test_phonology_medium.script')
        self.test_large_phonology_script_path = os.path.join(
            self.test_phonologies_path, 'test_phonology_large.script')
        self.test_phonology_testless_script_path = os.path.join(
            self.test_phonologies_path, 'test_phonology_no_tests.script')
        self.test_morphologies_path = os.path.join(
            self.here, 'old', 'tests', 'data', 'morphologies')
        self.test_morphophonologies_path = os.path.join(
            self.here, 'old', 'tests', 'data', 'morphophonologies')

    def _setcreateparams(self):
        """Set a whole bunch of ``_create_params``-suffixed instance attributes
        that are useful for creating new resources within tests.
        """
        self.application_settings_create_params = {
            'object_language_name': '',
            'object_language_id': '',
            'metalanguage_name': '',
            'metalanguage_id': '',
            'metalanguage_inventory': '',
            'orthographic_validation': 'None', # Value should be one of ['None', 'Warning', 'Error']
            'narrow_phonetic_inventory': '',
            'narrow_phonetic_validation': 'None',
            'broad_phonetic_inventory': '',
            'broad_phonetic_validation': 'None',
            'morpheme_break_is_orthographic': '',
            'morpheme_break_validation': 'None',
            'phonemic_inventory': '',
            'morpheme_delimiters': '',
            'punctuation': '',
            'grammaticalities': '',
            'unrestricted_users': [],        # A list of user ids
            'storage_orthography': '',        # An orthography id
            'input_orthography': '',          # An orthography id
            'output_orthography': ''         # An orthography id
        }
        self.collection_create_params = {
            'title': '',
            'type': '',
            'url': '',
            'description': '',
            'markup_language': '',
            'contents': '',
            'speaker': '',
            'source': '',
            'elicitor': '',
            'enterer': '',
            'date_elicited': '',
            'tags': [],
            'files': []
        }
        self.corpus_create_params = {
            'name': '',
            'description': '',
            'content': '',
            'form_search': '',
            'tags': []
        }
        self.file_create_params = {
            'name': '',
            'description': '',
            'date_elicited': '',    # mm/dd/yyyy
            'elicitor': '',
            'speaker': '',
            'utterance_type': '',
            'embedded_file_markup': '',
            'embedded_file_password': '',
            'tags': [],
            'forms': [],
            'file': ''      # file data Base64 encoded
        }
        self.file_create_params_base64 = {
            'filename': '',        # Will be filtered out on update requests
            'description': '',
            'date_elicited': '',    # mm/dd/yyyy
            'elicitor': '',
            'speaker': '',
            'utterance_type': '',
            'tags': [],
            'forms': [],
            'base64_encoded_file': '' # file data Base64 encoded; will be
                                      # filtered out on update requests
        }
        self.file_create_params_MPFD = {
            'filename': '',        # Will be filtered out on update requests
            'description': '',
            'date_elicited': '',    # mm/dd/yyyy
            'elicitor': '',
            'speaker': '',
            'utterance_type': '',
            'tags-0': '',
            'forms-0': ''
        }
        self.file_create_params_sub_ref = {
            'parent_file': '',
            'name': '',
            'start': '',
            'end': '',
            'description': '',
            'date_elicited': '',    # mm/dd/yyyy
            'elicitor': '',
            'speaker': '',
            'utterance_type': '',
            'tags': [],
            'forms': []
        }
        self.file_create_params_ext_host = {
            'url': '',
            'name': '',
            'password': '',
            'MIME_type': '',
            'description': '',
            'date_elicited': '',    # mm/dd/yyyy
            'elicitor': '',
            'speaker': '',
            'utterance_type': '',
            'tags': [],
            'forms': []
        }
        self.form_create_params = {
            'transcription': '',
            'phonetic_transcription': '',
            'narrow_phonetic_transcription': '',
            'morpheme_break': '',
            'grammaticality': '',
            'morpheme_gloss': '',
            'translations': [],
            'comments': '',
            'speaker_comments': '',
            'elicitation_method': '',
            'tags': [],
            'syntactic_category': '',
            'speaker': '',
            'elicitor': '',
            'verifier': '',
            'source': '',
            'status': 'tested',
            'date_elicited': '',     # mm/dd/yyyy
            'syntax': '',
            'semantics': ''
        }
        self.form_search_create_params = {
            'name': '',
            'search': '',
            'description': '',
            'searcher': ''
        }
        self.morpheme_language_model_create_params = {
            'name': '',
            'description': '',
            'corpus': '',
            'vocabulary_morphology': '',
            'toolkit': '',
            'order': '',
            'smoothing': '',
            'categorial': False
        }
        self.morphology_create_params = {
            'name': '',
            'description': '',
            'lexicon_corpus': '',
            'rules_corpus': '',
            'script_type': 'lexc',
            'extract_morphemes_from_rules_corpus': False,
            'rules': '',
            'rich_upper': True,
            'rich_lower': False,
            'include_unknowns': False
        }
        self.morphological_parser_create_params = {
            'name': '',
            'phonology': '',
            'morphology': '',
            'language_model': '',
            'description': ''
        }
        self.orthography_create_params = {
            'name': '',
            'orthography': '',
            'lowercase': False,
            'initial_glottal_stops': True
        }
        self.page_create_params = {
            'name': '',
            'heading': '',
            'markup_language': '',
            'content': '',
            'html': ''
        }
        self.phonology_create_params = {
            'name': '',
            'description': '',
            'script': ''
        }
        self.source_create_params = {
            'file': '',
            'type': '',
            'key': '',
            'address': '',
            'annote': '',
            'author': '',
            'booktitle': '',
            'chapter': '',
            'crossref': '',
            'edition': '',
            'editor': '',
            'howpublished': '',
            'institution': '',
            'journal': '',
            'key_field': '',
            'month': '',
            'note': '',
            'number': '',
            'organization': '',
            'pages': '',
            'publisher': '',
            'school': '',
            'series': '',
            'title': '',
            'type_field': '',
            'url': '',
            'volume': '',
            'year': '',
            'affiliation': '',
            'abstract': '',
            'contents': '',
            'copyright': '',
            'ISBN': '',
            'ISSN': '',
            'keywords': '',
            'language': '',
            'location': '',
            'LCCN': '',
            'mrnumber': '',
            'price': '',
            'size': '',
        }
        self.speaker_create_params = {
            'first_name': '',
            'last_name': '',
            'page_content': '',
            'dialect': 'dialect',
            'markup_language': 'reStructuredText'
        }
        self.syntactic_category_create_params = {
            'name': '',
            'type': '',
            'description': ''
        }
        self.user_create_params = {
            'username': '',
            'password': '',
            'password_confirm': '',
            'first_name': '',
            'last_name': '',
            'email': '',
            'affiliation': '',
            'role': '',
            'markup_language': '',
            'page_content': '',
            'input_orthography': None,
            'output_orthography': None
        }

    def poll(self, requester, changing_attr, changing_attr_originally,
             log, wait=2, vocal=True, task_descr='task'):
        """Poll a resource by calling ``requester`` until the value of
        ``changing_attr`` no longer matches ``changing_attr_originally``.
        """
        seconds_elapsed = 0
        while True:
            response = requester()
            resp = response.json_body
            if changing_attr_originally != resp[changing_attr]:
                if vocal:
                    log.debug('Task terminated')
                break
            else:
                if vocal:
                    log.debug('Waiting for %s to terminate: %s', task_descr,
                              h.human_readable_seconds(seconds_elapsed))
            sleep(wait)
            seconds_elapsed = seconds_elapsed + wait
        return resp


def decompress_gzip_string(compressed_data):
    compressed_stream = BytesIO(compressed_data)
    gzip_file = gzip.GzipFile(fileobj=compressed_stream, mode="rb")
    return gzip_file.read()


def get_file_size(file_path):
    try:
        return os.path.getsize(file_path)
    except (OSError, TypeError):
        return None
