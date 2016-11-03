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

"""Pylons application test package

This package assumes the Pylons environment is already loaded, such as
when this script is imported from the `nosetests --with-pylons=test.ini`
command.

This module initializes the application via ``websetup`` (`paster
setup-app`) and provides the base testing objects.
"""
import StringIO
import gzip
import os
import simplejson as json
from time import sleep
import webtest
from paste.deploy import appconfig
from unittest import TestCase
from paste.script.appinstall import SetupCommand
from pylons import url
from routes.util import URLGenerator
import pylons.test
import onlinelinguisticdatabase.lib.helpers as h
from paste.deploy.converters import asbool
from onlinelinguisticdatabase.model.meta import Session

__all__ = ['environ', 'url', 'TestController']

# Invoke websetup with the current config file
SetupCommand('setup-app').run([pylons.test.pylonsapp.config['__file__']])

environ = {}

class TestController(TestCase):

    def __init__(self, *args, **kwargs):
        wsgiapp = pylons.test.pylonsapp
        config = wsgiapp.config
        self.app = webtest.TestApp(wsgiapp)
        url._push_object(URLGenerator(config['routes.map'], environ))
        self.__setattrs__()
        self.__setcreateparams__()
        TestCase.__init__(self, *args, **kwargs)

    def __setattrs__(self):
        self.extra_environ_view = {'test.authentication.role': u'viewer'}
        self.extra_environ_contrib = {'test.authentication.role': u'contributor'}
        self.extra_environ_admin = {'test.authentication.role': u'administrator'}
        self.extra_environ_view_appset = {'test.authentication.role': u'viewer',
                                            'test.application_settings': True}
        self.extra_environ_contrib_appset = {'test.authentication.role': u'contributor',
                                            'test.application_settings': True}
        self.extra_environ_admin_appset = {'test.authentication.role': u'administrator',
                                            'test.application_settings': True}

        self.json_headers = {'Content-Type': 'application/json'}

        config = self.config = appconfig('config:test.ini', relative_to='.')
        self.here = config['here']
        self.files_path = h.get_OLD_directory_path('files', config=config)
        self.reduced_files_path = h.get_OLD_directory_path('reduced_files', config=config)
        self.test_files_path = os.path.join(self.here, 'onlinelinguisticdatabase', 'tests',
                             'data', 'files')
        self.create_reduced_size_file_copies = asbool(config.get(
            'create_reduced_size_file_copies', False))
        self.preferred_lossy_audio_format = config.get('preferred_lossy_audio_format', 'ogg')
        self.corpora_path = h.get_OLD_directory_path('corpora', config=config)
        self.test_datasets_path = os.path.join(self.here, 'onlinelinguisticdatabase',
                            'tests', 'data', 'datasets')
        self.test_scripts_path = os.path.join(self.here, 'onlinelinguisticdatabase',
                            'tests', 'scripts')
        self.loremipsum100_path = os.path.join(self.test_datasets_path, 'loremipsum_100.txt')
        self.loremipsum1000_path = os.path.join(self.test_datasets_path , 'loremipsum_1000.txt')
        self.loremipsum10000_path = os.path.join(self.test_datasets_path, 'loremipsum_10000.txt')
        self.users_path = h.get_OLD_directory_path('users', config=config)
        self.morphologies_path = h.get_OLD_directory_path('morphologies', config=config)
        self.morphological_parsers_path = h.get_OLD_directory_path('morphological_parsers', config=config)
        self.phonologies_path = h.get_OLD_directory_path('phonologies', config=config)
        self.morpheme_language_models_path = h.get_OLD_directory_path('morpheme_language_models', config=config)
        self.test_phonologies_path = os.path.join(self.here, 'onlinelinguisticdatabase',
                            'tests', 'data', 'phonologies')
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
        self.test_morphologies_path = os.path.join(self.here, 'onlinelinguisticdatabase',
                            'tests', 'data', 'morphologies')
        self.test_morphophonologies_path = os.path.join(self.here, 'onlinelinguisticdatabase',
                            'tests', 'data', 'morphophonologies')

    def __setcreateparams__(self):

        self.application_settings_create_params = {
            'object_language_name': u'',
            'object_language_id': u'',
            'metalanguage_name': u'',
            'metalanguage_id': u'',
            'metalanguage_inventory': u'',
            'orthographic_validation': u'None', # Value should be one of [u'None', u'Warning', u'Error']
            'narrow_phonetic_inventory': u'',
            'narrow_phonetic_validation': u'None',
            'broad_phonetic_inventory': u'',
            'broad_phonetic_validation': u'None',
            'morpheme_break_is_orthographic': u'',
            'morpheme_break_validation': u'None',
            'phonemic_inventory': u'',
            'morpheme_delimiters': u'',
            'punctuation': u'',
            'grammaticalities': u'',
            'unrestricted_users': [],        # A list of user ids
            'storage_orthography': u'',        # An orthography id
            'input_orthography': u'',          # An orthography id
            'output_orthography': u''         # An orthography id
        }
        self.collection_create_params = {
            'title': u'',
            'type': u'',
            'url': u'',
            'description': u'',
            'markup_language': u'',
            'contents': u'',
            'speaker': u'',
            'source': u'',
            'elicitor': u'',
            'enterer': u'',
            'date_elicited': u'',
            'tags': [],
            'files': []
        }
        self.corpus_create_params = {
            'name': u'',
            'description': u'',
            'content': u'',
            'form_search': u'',
            'tags': []
        }
        self.file_create_params = {
            'name': u'',
            'description': u'',
            'date_elicited': u'',    # mm/dd/yyyy
            'elicitor': u'',
            'speaker': u'',
            'utterance_type': u'',
            'embedded_file_markup': u'',
            'embedded_file_password': u'',
            'tags': [],
            'forms': [],
            'file': ''      # file data Base64 encoded
        }
        self.file_create_params_base64 = {
            'filename': u'',        # Will be filtered out on update requests
            'description': u'',
            'date_elicited': u'',    # mm/dd/yyyy
            'elicitor': u'',
            'speaker': u'',
            'utterance_type': u'',
            'tags': [],
            'forms': [],
            'base64_encoded_file': '' # file data Base64 encoded; will be filtered out on update requests
        }
        self.file_create_params_MPFD = {
            'filename': u'',        # Will be filtered out on update requests
            'description': u'',
            'date_elicited': u'',    # mm/dd/yyyy
            'elicitor': u'',
            'speaker': u'',
            'utterance_type': u'',
            'tags-0': u'',
            'forms-0': u''
        }
        self.file_create_params_sub_ref = {
            'parent_file': u'',
            'name': u'',
            'start': u'',
            'end': u'',
            'description': u'',
            'date_elicited': u'',    # mm/dd/yyyy
            'elicitor': u'',
            'speaker': u'',
            'utterance_type': u'',
            'tags': [],
            'forms': []
        }
        self.file_create_params_ext_host = {
            'url': u'',
            'name': u'',
            'password': u'',
            'MIME_type': u'',
            'description': u'',
            'date_elicited': u'',    # mm/dd/yyyy
            'elicitor': u'',
            'speaker': u'',
            'utterance_type': u'',
            'tags': [],
            'forms': []
        }
        self.form_create_params = {
            'transcription': u'',
            'phonetic_transcription': u'',
            'narrow_phonetic_transcription': u'',
            'morpheme_break': u'',
            'grammaticality': u'',
            'morpheme_gloss': u'',
            'translations': [],
            'comments': u'',
            'speaker_comments': u'',
            'elicitation_method': u'',
            'tags': [],
            'syntactic_category': u'',
            'speaker': u'',
            'elicitor': u'',
            'verifier': u'',
            'source': u'',
            'status': u'tested',
            'date_elicited': u'',     # mm/dd/yyyy
            'syntax': u'',
            'semantics': u''
        }
        self.form_search_create_params = {
            'name': u'',
            'search': u'',
            'description': u'',
            'searcher': u''
        }
        self.morpheme_language_model_create_params = {
            'name': u'',
            'description': u'',
            'corpus': u'',
            'vocabulary_morphology': u'',
            'toolkit': u'',
            'order': u'',
            'smoothing': u'',
            'categorial': False
        }
        self.morphology_create_params = {
            'name': u'',
            'description': u'',
            'lexicon_corpus': u'',
            'rules_corpus': u'',
            'script_type': u'lexc',
            'extract_morphemes_from_rules_corpus': False,
            'rules': u'',
            'rich_upper': True,
            'rich_lower': False,
            'include_unknowns': False
        }
        self.morphological_parser_create_params = {
            'name': u'',
            'phonology': u'',
            'morphology': u'',
            'language_model': u'',
            'description': u''
        }
        self.orthography_create_params = {
            'name': u'',
            'orthography': u'',
            'lowercase': False,
            'initial_glottal_stops': True
        }
        self.page_create_params = {
            'name': u'',
            'heading': u'',
            'markup_language': u'',
            'content': u'',
            'html': u''
        }
        self.phonology_create_params = {
            'name': u'',
            'description': u'',
            'script': u''
        }
        self.source_create_params = {
            'file': u'',
            'type': u'',
            'key': u'',
            'address': u'',
            'annote': u'',
            'author': u'',
            'booktitle': u'',
            'chapter': u'',
            'crossref': u'',
            'edition': u'',
            'editor': u'',
            'howpublished': u'',
            'institution': u'',
            'journal': u'',
            'key_field': u'',
            'month': u'',
            'note': u'',
            'number': u'',
            'organization': u'',
            'pages': u'',
            'publisher': u'',
            'school': u'',
            'series': u'',
            'title': u'',
            'type_field': u'',
            'url': u'',
            'volume': u'',
            'year': u'',
            'affiliation': u'',
            'abstract': u'',
            'contents': u'',
            'copyright': u'',
            'ISBN': u'',
            'ISSN': u'',
            'keywords': u'',
            'language': u'',
            'location': u'',
            'LCCN': u'',
            'mrnumber': u'',
            'price': u'',
            'size': u'',
        }
        self.speaker_create_params = {
            'first_name': u'',
            'last_name': u'',
            'page_content': u'',
            'dialect': u'dialect',
            'markup_language': u'reStructuredText'
        }
        self.syntactic_category_create_params = {
            'name': u'',
            'type': u'',
            'description': u''
        }
        self.user_create_params = {
            'username': u'',
            'password': u'',
            'password_confirm': u'',
            'first_name': u'',
            'last_name': u'',
            'email': u'',
            'affiliation': u'',
            'role': u'',
            'markup_language': u'',
            'page_content': u'',
            'input_orthography': None,
            'output_orthography': None
        }

    def tearDown(self, **kwargs):
        clear_all_tables = kwargs.get('clear_all_tables', False)
        dirs_to_clear = kwargs.get('dirs_to_clear', [])
        del_global_app_set = kwargs.get('del_global_app_set', False)
        dirs_to_destroy = kwargs.get('dirs_to_destroy', [])

        if clear_all_tables:
            h.clear_all_tables(['language'])
        else:
            h.clear_all_models()
        administrator = h.generate_default_administrator()
        contributor = h.generate_default_contributor()
        viewer = h.generate_default_viewer()
        Session.add_all([administrator, contributor, viewer])
        Session.commit()

        for dir_path in dirs_to_clear:
            h.clear_directory_of_files(getattr(self, dir_path))

        for dir_name in dirs_to_destroy:
            {
                'user': lambda: h.destroy_all_directories('users', 'test.ini'),
                'corpus': lambda: h.destroy_all_directories('corpora', 'test.ini'),
                'phonology': lambda: h.destroy_all_directories('phonologies', 'test.ini'),
                'morphology': lambda: h.destroy_all_directories('morphologies', 'test.ini'),
                'morphological_parser': lambda: h.destroy_all_directories('morphological_parsers', 'test.ini'),
                'morpheme_language_model': lambda: h.destroy_all_directories('morpheme_language_models', 'test.ini')
            }.get(dir_name, lambda: None)()

        if del_global_app_set:
            # Perform a vacuous GET just to delete app_globals.application_settings
            # to clean up for subsequent tests.
            self.app.get(url('new_form'), extra_environ=self.extra_environ_admin_appset)

    def _add_SEARCH_to_web_test_valid_methods(self):
        """Hack to prevent webtest from printing warnings when SEARCH method is used."""
        new_valid_methods = list(webtest.lint.valid_methods)
        new_valid_methods.append('SEARCH')
        new_valid_methods = tuple(new_valid_methods)
        webtest.lint.valid_methods = new_valid_methods

    def poll(self, requester, changing_attr, changing_attr_originally,
             log, wait=2, vocal=True, task_descr='task'):
        """Poll a resource by calling ``requester`` until the value of ``changing_attr`` no longer matches ``changing_attr_originally``.
        """
        seconds_elapsed = 0
        while True:
            response = requester()
            resp = json.loads(response.body)
            if changing_attr_originally != resp[changing_attr]:
                if vocal:
                    log.debug('Task terminated')
                break
            else:
                if vocal:
                    log.debug('Waiting for %s to terminate: %s' % (task_descr, h.human_readable_seconds(seconds_elapsed)))
            sleep(wait)
            seconds_elapsed = seconds_elapsed + wait
        return resp

def decompress_gzip_string(compressed_data):
    compressed_stream = StringIO.StringIO(compressed_data)
    gzip_file = gzip.GzipFile(fileobj=compressed_stream, mode="rb")
    return gzip_file.read()

def get_file_size(file_path):
    try:
        return os.path.getsize(file_path)
    except Exception:
        None

