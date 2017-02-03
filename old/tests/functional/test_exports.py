# Copyright 2017 Joel Dunham
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

from base64 import encodestring, b64encode
from collections import namedtuple
from datetime import date, datetime, timedelta
import json
import logging
import os
import pprint
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc

from old.lib.introspectmodel import (
    add_html_to_old_schema,
    add_jsonld_to_old_schema,
    get_old_model_classes,
    get_old_schema,
    introspect_old_schema,
    write_schema_html_to_disk
)
from old.lib.dbutils import DBUtils
from old.lib.utils import camel_case2snake_case
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import Export, Form
from old.tests import TestView

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Export._url()
forms_url = Form._url()


# Global temporal objects -- useful for creating the data upon which to search
# and for formulating assertions about the results of those searches.
TODAY_TIMESTAMP = datetime.now()
DAY_DELTA = timedelta(1)
YESTERDAY_TIMESTAMP = TODAY_TIMESTAMP - DAY_DELTA
JAN1 = date(2012, 1, 1)
JAN2 = date(2012, 1, 2)
JAN3 = date(2012, 1, 3)
JAN4 = date(2012, 1, 4)

FormNT = namedtuple('Form', ['pt', 'ot', 'mb', 'mg', 'tl', 'cat'])

FORMS = (
    FormNT('', 's', 'z', 'PL', 'plural', 'Phi'),
    FormNT('', 'le', 'l\u0259', 'the', 'definite article, masculine', 'D'),
    FormNT('', 'la', 'l\u00e6', 'the', 'definite article, feminine', 'D'),
    FormNT('', 'chien', '\u0283j\u025b\u0303', 'dog', 'dog', 'N'),
    FormNT('', 'chat', '\u0283a', 'cat', 'cat', 'N'),
    FormNT('', 'mange', 'ma\u0303\u0292', 'eat', 'eat', 'V'),
    FormNT('', 'voi', 'vwa', 'see', 'see', 'V'),
    FormNT('', 'ent', '\u2205', '3PL', 'third person plural, present tense',
           'Agr'),
    FormNT(
        'le \u0283j\u025b\u0303 vwa le \u0283a',
        'Les chiens voient les chats.',
        'l\u0259-z \u0283j\u025b\u0303-z vwa-\u2205 l\u0259-z \u0283a-z',
        'the-PL dog-PL see-3PL the-PL cat-PL',
        'The dogs see the cats.',
        'S'
    ),
    FormNT(
        'le \u0283a ma\u0303\u0292',
        'Les chats mangent.',
        'l\u0259-z \u0283a-z ma\u0303\u0292-\u2205',
        'the-PL cat-PL eat-3PL',
        'The cats are eating.',
        'S'
    ),
)


class TestExportsView(TestView):

    n = 5

    def _create_test_data(self):
        # Add some test data to the database.
        application_settings = omb.generate_default_application_settings()
        self.dbsession.add(application_settings)
        self.dbsession.commit()
        users = self.db.get_users()
        contributor = [u for u in users if u.role == 'contributor'][0]
        self.contributor_id = contributor.id
        self._create_test_models()
        self._create_test_forms()
        self._create_test_corpus()

    def _create_test_corpus(self):
        forms = self.db.get_forms()
        form1 = [f for f in forms if f.transcription ==
                 'Les chiens voient les chats.'][0]
        form2 = [f for f in forms if f.transcription ==
                 'Les chats mangent.'][0]
        corpus = self.corpus_create_params.copy()
        corpus['name'] = 'Corpus of French Sentences'
        corpus['content'] = str(form1.id) + ',' + str(form2.id)
        url = old_models.Corpus._url()
        response = self.app.post(
            url('create'),
            json.dumps(corpus),
            self.json_headers,
            {'test.authentication.id': self.contributor_id})
        corpus_dict = response.json_body
        self.app.put(
            '/corpora/%d/writetofile' % corpus_dict['id'],
            json.dumps({'format': 'treebank'}),
            self.json_headers,
            {'test.authentication.id': self.contributor_id})

    def _create_test_models(self):
        self._add_test_models('Tag', self.n, ['name'])
        self._add_test_models('Speaker', self.n,
                              ['first_name', 'last_name', 'dialect'])
        self._add_test_models('Source', self.n, [])
        self._add_test_models('ElicitationMethod', self.n, ['name'])
        self._add_syntactic_categories()
        self._add_test_models('File', self.n, [])

    def _add_syntactic_categories(self):
        """Add the syntactic categories from ``FORMS``."""
        cats = set()
        for form in FORMS:
            if form.cat:
                cats.add(form.cat)
        for cat in cats:
            obj = self.syntactic_category_create_params.copy()
            obj['name'] = cat
            url = old_models.SyntacticCategory._url()('create')
            response = self.app.post(
                url,
                json.dumps(obj),
                self.json_headers,
                {'test.authentication.id': self.contributor_id})

    def _add_test_models(self, model_name, n, attrs):
        """Add some basic OLD models/resources."""
        for i in range(1, n + 1):
            attr = '{}_create_params'.format(
                camel_case2snake_case(model_name))
            obj = getattr(self, attr).copy()
            if model_name == 'Source':
                obj['type'] = 'article'
                obj['key'] = 'key%s' % i
                obj['author'] = 'Author No%s' % i
                obj['title'] = 'Title %s' % i
                obj['journal'] = 'Journal %s' % i
                obj['year'] = 2000
            if model_name == 'File':
                wav_file_path = os.path.join(
                    self.test_files_path, 'old_test.wav')
                wav_file_base64_encoded = b64encode(
                    open(wav_file_path, 'rb').read()).decode('utf8')
                obj = self.file_create_params_base64.copy()
                obj.update({
                    'filename': 'test_file%s.wav' % i,
                    'base64_encoded_file': wav_file_base64_encoded
                })
            for attr in attrs:
                obj[attr] = '%s %s' % (attr, i)
            url = getattr(old_models, model_name)._url()('create')
            response = self.app.post(
                url,
                json.dumps(obj),
                self.json_headers,
                {'test.authentication.id': self.contributor_id})

    def _get_test_models(self):
        return {
            'tags': self.db.get_tags(),
            'speakers': self.db.get_speakers(),
            'sources': self.db.get_sources(),
            'elicitation_methods': self.db.get_elicitation_methods(),
            'syntactic_categories': self.db.get_syntactic_categories(),
            'files': self.db.get_files()
        }

    def _create_test_forms(self):
        """Create forms with various properties."""
        test_models = self._get_test_models()
        for form in FORMS:
            f = self.form_create_params.copy()
            f['transcription'] = form.ot
            f['morpheme_break'] = form.mb
            f['morpheme_gloss'] = form.mg
            f['translations'] = [{
                'transcription': form.tl,
                'grammaticality': ''
            }]
            cat_id = [cat for cat in test_models['syntactic_categories'] if
                      cat.name == form.cat][0].id
            f['syntactic_category'] = cat_id
            f['tags'] = []
            f['files'] = []
            f['phonetic_transcription'] = form.pt
            t = test_models['tags'][0]
            f['tags'].append(t.id)
            fi = test_models['files'][0]
            f['files'].append(fi.id)
            f['elicitor'] = self.contributor_id
            f['speaker'] = test_models['speakers'][0].id
            f['elicitation_method'] = test_models['elicitation_methods'][0].id
            f['date_elicited'] = '12/29/2009'
            f['source'] = test_models['sources'][0].id
            response = self.app.post(
                forms_url('create'),
                json.dumps(f),
                self.json_headers,
                {'test.authentication.id': self.contributor_id})

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(
            #dirs_to_clear=['reduced_files_path', 'files_path', 'exports_path'],
            dirs_to_clear=['reduced_files_path', 'files_path'],
            clear_dirs=True)

    def test_schema_introspection(self):
        """Tests that old/lib/introspectmodel.py can correctly introspect the
        model and docstrings of the OLD and return a dict representing the
        schema of the OLD.
        """
        dbsession = self.dbsession
        db = self.db = DBUtils(dbsession, self.settings)
        # response = self.app.post(url('create'), '{}', self.json_headers,
        #                          self.extra_environ_admin)
        # resp = response.json_body
        # old_schema = introspect_old_schema()
        # pprint.pprint(old_schema, width=200)
        # pprint.pprint(old_schema)
        # old_schema = add_html_to_old_schema(old_schema)
        # pprint.pprint(old_schema)
        # old_schema = add_jsonld_to_old_schema(old_schema)
        # pprint.pprint(old_schema, width=200)
        old_schema = get_old_schema()
        write_schema_html_to_disk(old_schema)

    def test_export_creation(self):
        """Tests that POST /exports works as expected: it generates .jsonld
        files in the exports/ directory.
        """
        dbsession = self.dbsession
        db = self.db = DBUtils(dbsession, self.settings)

        # This was copied verbatim (non-DRY) from test_forms_search.py and is
        # not ideal for this kind of testing since it creates OLD models via the
        # session and not via simulated requests. An improved set of tests will
        # generate a more realistic data set. Maybe encrypting a real data set
        # would be the way to go.
        self._create_test_data()

        store_path = self.settings['permanent_store']
        import subprocess
        import pprint
        cmd = ['tree', '-C', store_path]
        tree = subprocess.check_output(cmd)
        #pprint.pprint(tree)
        print('tree')
        print(tree.decode('utf8'))
        print('endtree')

        response = self.app.post(url('create'), '{}', self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        # print(resp)
        # pprint.pprint(resp)
        exports_dir_path = self.settings['exports_dir']
        assert os.path.isdir(exports_dir_path)
        # print(os.listdir(exports_dir_path))
        expected_export_path = os.path.join(exports_dir_path, resp['name'])
        assert os.path.isdir(expected_export_path)
        db_path = os.path.join(expected_export_path, 'data', 'db')
        assert os.path.isdir(db_path)
        # print(os.listdir(db_path))

        form_ids = [
            idtup[0] for idtup in
            dbsession.query(old_models.Form)
            .with_entities(old_models.Form.id).all()]
        assert len(form_ids) == len(FORMS)
        for id_ in form_ids:
            jsonld_fname = 'Form-{}.jsonld'.format(id_)
            path = os.path.join(db_path, jsonld_fname)
            assert os.path.isfile(path)
        target_form = dbsession.query(old_models.Form).get(form_ids[0])
        target_jsonld_path = os.path.join(
            db_path, 'Form-{}.jsonld'.format(form_ids[0]))
        with open(target_jsonld_path) as filei:
            target_jsonld = json.loads(filei.read())
        # pprint.pprint(target_jsonld)
        # pprint.pprint(target_form.get_dict())
        assert '@context' in target_jsonld
        assert '@context' in target_jsonld['Form']
        target_path = (
            '{}/'
            'data/'
            'db/'
            'Form-{}.jsonld'.format(resp['name'], form_ids[0]))
        assert target_path in target_jsonld['@id']
        enterer_path = (
            '{}/'
            'data/'
            'db/'
            'User-{}.jsonld'.format(resp['name'], target_form.enterer_id))
        assert enterer_path in target_jsonld['Form']['enterer']
