# Copyright 2021 Joel Dunham
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

from base64 import encodebytes
import datetime
import json
import logging
import os
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc

from old.lib.dbutils import DBUtils
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
import old.views.sync as sut
from old.tests import TestView

LOGGER = logging.getLogger(__name__)


forms_url = old_models.Form._url(old_name=TestView.old_name)



class TestSyncView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def get_table_expected(self, mdl):
        return {str(r.id): r.datetime_modified.isoformat() for
                r in self.dbsession.query(mdl).all()}

    def get_expected(self):
        return {t: self.get_table_expected(getattr(old_models, t)) for t in sut.RESOURCES}

    def test_last_modified(self):

        db = DBUtils(self.dbsession, self.settings)
        url = '/{}/sync/last_modified'.format(self.old_name)

        r1 = self.app.get(url, {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        exp1 = self.get_expected()
        assert exp1 == r1

        # Create some forms and other data in the db
        restricted_tag = omb.generate_restricted_tag()
        application_settings = omb.generate_default_application_settings()
        self.dbsession.add_all([application_settings, restricted_tag])
        self.dbsession.commit()
        restricted_tag = db.get_restricted_tag()

        for i in range(10):
            params = self.form_create_params.copy()
            params.update({
                'transcription': str(i),
                'translations': [{'transcription': str(i), 'grammaticality': '' }]})
            params = json.dumps(params)
            response = self.app.post(
                forms_url('create'), params, self.json_headers,
                self.extra_environ_contrib)
            resp = response.json_body
            datetime_modified = resp['datetime_modified']

        # Now the last_modified payload will contain 10 forms, 10
        # translations, 1 app settings and 1 tag.
        r2 = self.app.get(url, {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        exp2 = self.get_expected()
        assert exp2 == r2
        assert 0 == len(r2['FormBackup'])
        assert 0 == len(r2['FormTag'])
        assert 10 == len(r2['Form'])
        assert 10 == len(r2['Translation'])
        assert 1 == len(r2['ApplicationSettings'])
        assert 1 == len(r2['Tag'])

        # Update one of the forms just created
        params = self.form_create_params.copy()
        form_id = sorted(r2['Form'])[0]
        params.update({
            'transcription': 'Updated!',
            'translations': [{
                'transcription': 'test_update_translation',
                'grammaticality': ''
            }],
            'morpheme_break': 'a-b',
            'morpheme_gloss': 'c-d',
            'status': 'requires testing',
            'tags': [restricted_tag.id]
        })
        params = json.dumps(params)
        response = self.app.put(forms_url('update', id=form_id), params,
                                self.json_headers, self.extra_environ_contrib)
        resp = response.json_body

        # Now we will have a FormBackup and a FormTag
        r3 = self.app.get(url, {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        exp3 = self.get_expected()
        assert exp3 == r3
        assert r2['Form'][form_id] != r3['Form'][form_id]
        assert 1 == len(r3['FormBackup'])
        assert 1 == len(r3['FormTag'])

        # Delete the second form created
        sec_form_id = str(sorted([int(i) for i in r2['Form']])[1])
        response = self.app.delete(
                forms_url('delete', id=sec_form_id),
                extra_environ=self.extra_environ_contrib)

        # Now we will have 2 FormBackups and 9 Forms
        r4 = self.app.get(url, {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        exp4 = self.get_expected()
        assert exp4 == r4
        assert 2 == len(r4['FormBackup'])
        assert 9 == len(r4['Form'])
