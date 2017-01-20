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

from base64 import encodestring
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
    introspect_old_schema,
    write_schema_html_to_disk
)
from old.lib.dbutils import DBUtils
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import Export
from old.tests import TestView

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Export._url()


# Global temporal objects -- useful for creating the data upon which to search
# and for formulating assertions about the results of those searches.
TODAY_TIMESTAMP = datetime.now()
DAY_DELTA = timedelta(1)
YESTERDAY_TIMESTAMP = TODAY_TIMESTAMP - DAY_DELTA
JAN1 = date(2012, 1, 1)
JAN2 = date(2012, 1, 2)
JAN3 = date(2012, 1, 3)
JAN4 = date(2012, 1, 4)


def _create_test_models(dbsession, n=100):
    _add_test_models_to_session('Tag', n, ['name'], dbsession)
    _add_test_models_to_session('Speaker', n, ['first_name', 'last_name', 'dialect'], dbsession)
    _add_test_models_to_session('Source', n, ['author_first_name', 'author_last_name',
                                            'title'], dbsession)
    _add_test_models_to_session('ElicitationMethod', n, ['name'], dbsession)
    _add_test_models_to_session('SyntacticCategory', n, ['name'], dbsession)
    _add_test_models_to_session('File', n, ['name'], dbsession)
    dbsession.commit()


def _add_test_models_to_session(model_name, n, attrs, dbsession):
    for i in range(1, n + 1):
        m = getattr(old_models, model_name)()
        for attr in attrs:
            setattr(m, attr, '%s %s' % (attr, i))
        dbsession.add(m)


def _get_test_models(db):
    default_models = {
        'tags': db.get_tags(),
        'speakers': db.get_speakers(),
        'sources': db.get_sources(),
        'elicitation_methods': db.get_elicitation_methods(),
        'syntactic_categories': db.get_syntactic_categories(),
        'files': db.get_files()
    }
    return default_models


def _create_test_forms(db, dbsession, n=100):
    """Create n forms with various properties.  A testing ground for searches!
    """
    test_models = _get_test_models(db)
    users = db.get_users()
    viewer = [u for u in users if u.role == 'viewer'][0]
    contributor = [u for u in users if u.role == 'contributor'][0]
    administrator = [u for u in users if u.role == 'administrator'][0]
    for i in range(1, n + 1):
        f = old_models.Form()
        f.transcription = 'transcription %d' % i
        if i > 50:
            f.transcription = f.transcription.upper()
            administrator.remembered_forms.append(f)
        f.morpheme_break = 'morpheme_break %d' % i
        f.morpheme_gloss = 'morpheme_gloss %d' % i
        f.comments = 'comments %d' % i
        f.speaker_comments = 'speaker_comments %d' % i
        f.morpheme_break_ids = '[[[]]]'
        f.morpheme_gloss_ids = '[[[]]]'
        tl = old_models.Translation()
        tl.transcription = 'translation %d' % i
        f.enterer = contributor
        f.syntactic_category = test_models['syntactic_categories'][i - 1]
        if i > 75:
            f.phonetic_transcription = 'phonetic_transcription %d' % i
            f.narrow_phonetic_transcription = 'narrow_phonetic_transcription %d' % i
            t = test_models['tags'][i - 1]
            f.tags.append(t)
            tl.grammaticality = '*'
            viewer.remembered_forms.append(f)
        if i > 65 and i < 86:
            fi = test_models['files'][i - 1]
            f.files.append(fi)
            contributor.remembered_forms.append(f)
        #if (i -1) == 73:
        #    f.files.append(test_models['files'][70])
        if i > 50:
            f.elicitor = contributor
            if i != 100:
                f.speaker = test_models['speakers'][0]
                f.datetime_modified = TODAY_TIMESTAMP
                f.datetime_entered = TODAY_TIMESTAMP
        else:
            f.elicitor = administrator
            f.speaker = test_models['speakers'][-1]
            f.datetime_modified = YESTERDAY_TIMESTAMP
            f.datetime_entered = YESTERDAY_TIMESTAMP
        if i < 26:
            f.elicitation_method = test_models['elicitation_methods'][0]
            f.date_elicited = JAN1
        elif i < 51:
            f.elicitation_method = test_models['elicitation_methods'][24]
            f.date_elicited = JAN2
        elif i < 76:
            f.elicitation_method = test_models['elicitation_methods'][49]
            f.date_elicited = JAN3
        else:
            f.elicitation_method = test_models['elicitation_methods'][74]
            if i < 99:
                f.date_elicited = JAN4
        if (i > 41 and i < 53) or i in [86, 92, 3]:
            f.source = test_models['sources'][i]
        if i != 87:
            f.translations.append(tl)
        if i == 79:
            tl = old_models.Translation()
            tl.transcription = 'translation %d the second' % i
            f.translations.append(tl)
            t = test_models['tags'][i - 2]
            f.tags.append(t)
        dbsession.add(f)
    dbsession.commit()


def _create_test_data(db, dbsession, n=100):
    _create_test_models(dbsession, n)
    _create_test_forms(db, dbsession, n)


class TestExportsView(TestView):

    n = 100

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(
            dirs_to_clear=['reduced_files_path', 'files_path', 'exports_path'],
            clear_dirs=True)

    def test_schema_introspection(self):
        """Tests that old/lib/introspectmodel.py can correctly introspect the
        model and docstrings of the OLD and return a dict representing the
        schema of the OLD.
        """
        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        response = self.app.post(url('create'), '{}', self.json_headers,
        resp = response.json_body
        # old_schema = introspect_old_schema()
        # pprint.pprint(old_schema, width=200)
        # pprint.pprint(old_schema)
        # old_schema = add_html_to_old_schema(old_schema)
        # pprint.pprint(old_schema)
        # old_schema = add_jsonld_to_old_schema(old_schema)
        # pprint.pprint(old_schema, width=200)
        # write_schema_html_to_disk(old_schema)

    def test_export_creation(self):
        """Tests that POST /exports works as expected: it generates .jsonld
        files in the exports/ directory.
        """
        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # This was copied verbatim (non-DRY) from test_forms_search.py and is
        # not ideal for this kind of testing since it creates OLD models via the
        # session and not via simulated requests. An improved set of tests will
        # generate a more realistic data set. Maybe encrypting a real data set
        # would be the way to go.
        _create_test_data(db, dbsession, self.n)

        response = self.app.post(url('create'), '{}', self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        print(resp)
        pprint.pprint(resp)
        exports_dir_path = self.settings['exports_dir']
        assert os.path.isdir(exports_dir_path)
        print(os.listdir(exports_dir_path))
        expected_export_path = os.path.join(exports_dir_path, resp['name'])
        assert os.path.isdir(expected_export_path)
        db_path = os.path.join(expected_export_path, 'db')
        assert os.path.isdir(db_path)
        print(os.listdir(db_path))

        form_ids = [
            idtup[0] for idtup in
            dbsession.query(old_models.Form)
            .with_entities(old_models.Form.id).all()]
        assert len(form_ids) == self.n
        for id_ in form_ids:
            jsonld_fname = 'Form-{}.jsonld'.format(id_)
            path = os.path.join(db_path, jsonld_fname)
            assert os.path.isfile(path)
        target_form = dbsession.query(old_models.Form).get(form_ids[0])
        target_jsonld_path = os.path.join(
            db_path, 'Form-{}.jsonld'.format(form_ids[0]))
        with open(target_jsonld_path) as filei:
            target_jsonld = json.loads(filei.read())
        pprint.pprint(target_jsonld)
        pprint.pprint(target_form.get_dict())
        assert '@context' in target_jsonld
        assert '@context' in target_jsonld['Form']
        target_path = (
            '{}/'
            'db/'
            'Form-{}.jsonld'.format(resp['name'], form_ids[0]))
        assert target_path in target_jsonld['@id']
        enterer_path = (
            '{}/'
            'db/'
            'User-{}.jsonld'.format(resp['name'], target_form.enterer_id))
        assert enterer_path in target_jsonld['Form']['enterer']
