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


def debug_diff(prev, curr):
    diff = {}
    for t, ids in prev.items():
        cids = curr.get(t)
        if ids != cids:
            diff.setdefault(t, {})
            for i, e in ids.items():
                ce = cids.get(i, {})
                if e != ce:
                    diff[t].setdefault(i, {})
                    for k, v in e.items():
                        cv = ce.get(k)
                        if v != cv:
                            diff[t][i][k] = {'previous': v, 'current': cv}
            for i, ce in cids.items():
                e = ids.get(i, {})
                if e != ce:
                    diff[t].setdefault(i, {})
                    for k, cv in ce.items():
                        v = e.get(k)
                        if v != cv:
                            diff[t][i][k] = {'previous': v, 'current': cv}
    return diff


def human_diff(prev, curr):
    diff = {'delete': {}, 'add': {}, 'update': {}}
    for table, ids in prev.items():
        for id_, modified in ids.items():
            if id_ not in curr[table]:
                diff['delete'].setdefault(table, []).append(id_)
            elif modified != curr[table][id_]:
                diff['update'].setdefault(table, []).append(id_)
    for table, ids in curr.items():
        for id_, modified in ids.items():
            if id_ not in prev[table]:
                diff['add'].setdefault(table, []).append(id_)
    return diff


class TestSyncView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def get_table_expected(self, mdl):
        return {str(r.id): r.datetime_modified.isoformat().replace('T', ' ') for
                r in self.dbsession.query(mdl).all()}

    def get_expected(self):
        return {getattr(old_models, m).__table__.name:
                self.get_table_expected(getattr(old_models, m))
                for m in sut.MODELS}

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
        assert 0 == len(r2['formbackup'])
        assert 0 == len(r2['formtag'])
        assert 10 == len(r2['form'])
        assert 10 == len(r2['translation'])
        assert 1 == len(r2['applicationsettings'])
        assert 1 == len(r2['tag'])

        # Update one of the forms just created
        params = self.form_create_params.copy()
        form_id = sorted(r2['form'])[0]
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

        # Now we will have a formbackup and a formtag
        r3 = self.app.get(url, {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        exp3 = self.get_expected()
        assert exp3 == r3
        assert r2['form'][form_id] != r3['form'][form_id]
        assert 1 == len(r3['formbackup'])
        assert 1 == len(r3['formtag'])

        # Delete the second form created
        sec_form_id = str(sorted([int(i) for i in r2['form']])[1])
        response = self.app.delete(
                forms_url('delete', id=sec_form_id),
                extra_environ=self.extra_environ_contrib)

        # Now we will have 2 formbackups and 9 forms
        r4 = self.app.get(url, {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        exp4 = self.get_expected()

        assert exp4 == r4
        assert 2 == len(r4['formbackup'])
        assert 9 == len(r4['form'])

    def test_tables(self):

        db = DBUtils(self.dbsession, self.settings)
        url = '/{}/sync/tables'.format(self.old_name)

        # Get all the tables of a fresh OLD and expect to receive just three
        # users.
        params = json.dumps({'tables': '*'})
        r1 = self.app.post(
            url,
            params,
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        for k, v in r1.items():
            if k == 'user':
                assert 3 == len(v)
            else:
                assert not v

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

        # Ensure we can get all tables
        params = json.dumps({'tables': '*'})
        r2 = self.app.post(
            url,
            params,
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        expected_counts = {
            'applicationsettings': 1,
            'form': 10,
            'tag': 1,
            'translation': 10,
            'user': 3,
        }
        for k, v in r2.items():
            count = expected_counts.get(k, 0)
            assert count == len(v)

        # Get select tables
        p = {'tables': {'applicationsettings': [1],
                        'form': [1, 9],
                        'translation': [1, 9],
                        'user': [2]}}
        params = json.dumps(p)
        r3 = self.app.post(url,
                           params,
                           headers=self.json_headers,
                           extra_environ=self.extra_environ_contrib).json_body
        expected_counts = {'applicationsettings': 1,
                           'form': 2,
                           'tag': 0,
                           'translation': 2,
                           'user': 1}
        ids = {}
        for k, v in r3.items():
            if v:
                ids[k] = [int(kk) for kk in v]
            count = expected_counts.get(k, 0)
            assert count == len(v)
        assert p['tables'] == ids

        # READ! Fetch the "previous" state in its entirety
        previous_state = self.app.post(
            url, json.dumps({'tables': '*'}), headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body

        # READ! Fetch the "previous" minimal state
        previous_minimal_state = self.app.get(
            '/{}/sync/last_modified'.format(self.old_name), {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body

        # MUTATE! Delete the second form created
        sec_form_id = str(sorted([int(i) for i in r2['form']])[1])
        response = self.app.delete(
                forms_url('delete', id=sec_form_id),
                extra_environ=self.extra_environ_contrib)

        # READ! Re-Re-fetch the current state in its entirety
        current_state = self.app.post(
            url, json.dumps({'tables': '*'}), headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        assert previous_state != current_state

        # READ! Get minimal current state
        current_minimal_state = self.app.get(
            '/{}/sync/last_modified'.format(self.old_name), {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body

        # DIFF!
        expected_diff = {
            'add': {'formbackup': ['1']},
            # The translation should reliably have the same ID as its form just
            # because of how incrementing primary keys works.
            'delete': {'form': [sec_form_id], 'translation': [sec_form_id]},
            'update': {}
        }
        diff = human_diff(previous_minimal_state, current_minimal_state)
        assert expected_diff == diff

        # READ! Fetch only the parts of the current state that we need
        needed_state = self.app.post(
            url, json.dumps({'tables': {'formbackup': [1]}}),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body

        # Repair the previous state using the needed state and expect it to
        # equal the current state.
        del previous_state['form'][sec_form_id]
        del previous_state['translation'][sec_form_id]
        previous_state['formbackup'].update(needed_state['formbackup'])
        assert previous_state == current_state

        # MUTATE! Update one of the forms
        params = self.form_create_params.copy()
        form_id = sorted(r2['form'])[0]
        params.update({
            'transcription': 'Updated!',
            'translations': [{
                'transcription': 'test_update_translation',
                'grammaticality': ''
            }],
            'morpheme_break': 'a-b',
            'morpheme_gloss': 'c-d',
            'status': 'requires testing'
        })
        params = json.dumps(params)
        response = self.app.put(forms_url('update', id=form_id), params,
                                self.json_headers, self.extra_environ_contrib)

        # READ! Fetch the current state in its entirety
        current_state = self.app.post(
            url, json.dumps({'tables': '*'}), headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        assert previous_state != current_state

        # READ! Get minimal current state
        previous_minimal_state = current_minimal_state
        current_minimal_state = self.app.get(
            '/{}/sync/last_modified'.format(self.old_name), {},
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body

        # DIFF!
        diff = human_diff(previous_minimal_state, current_minimal_state)
        # Updating a form (including its translation) results in:
        # - a backup of the previous version of the form,
        # - a new translation entity,
        # - a deletion of the previous translation (now backed up in the
        #   formbackup), and
        # - an updated form
        expected_diff = {
            'add': {'formbackup': ['2'],
                    'translation': ['11']},
            'delete': {'translation': ['1']},
            'update': {'form': ['1']}}
        assert expected_diff == diff

        # READ! Fetch only the parts of the current state that we need
        needed_state = self.app.post(
            url, json.dumps({'tables': {'formbackup': [2],
                                        'translation': [11],
                                        'form': [1]}}),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body

        # Repair the previous state using the needed state and expect it to
        # equal the current state.
        del previous_state['translation']['1']
        previous_state['form'].update(needed_state['form'])
        previous_state['translation'].update(needed_state['translation'])
        previous_state['formbackup'].update(needed_state['formbackup'])
        assert previous_state == current_state
