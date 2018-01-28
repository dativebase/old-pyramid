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

import logging
import os
import json

from old.lib.dbutils import DBUtils
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
from old.models import MorphemeLanguageModel, MorphemeLanguageModelBackup

LOGGER = logging.getLogger(__name__)


url = MorphemeLanguageModelBackup._url(old_name=TestView.old_name)
mlm_url = MorphemeLanguageModel._url(old_name=TestView.old_name)
fs_url = old_models.FormSearch._url(old_name=TestView.old_name)
cp_url = old_models.Corpus._url(old_name=TestView.old_name)



class TestMorphemelanguagemodelbackupsView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def tearDown(self):
        super().tearDown(dirs_to_destroy=['morpheme_language_model'])

    def test_index(self):
        """Tests that ``GET /morphemelanguagemodelbackups`` behaves correctly.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Define some extra_environs
        view = {'test.authentication.role': 'viewer', 'test.application_settings': True}
        contrib = {'test.authentication.role': 'contributor', 'test.application_settings': True}
        admin = {'test.authentication.role': 'administrator', 'test.application_settings': True}

        # Create a form search that finds all forms (there are none)
        query = {'filter': ['Form', 'transcription', 'like', '%_%']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Find anything',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        form_search_id = response.json_body['id']

        # Create a corpus based on the form search just created
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of sentences',
            'form_search': form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        corpus_id = response.json_body['id']

        # Create a morpheme language model using the corpus just created.
        name = 'Morpheme language model'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.post(mlm_url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['order'] == 3
        assert resp['smoothing'] == '' # The ModKN smoothing algorithm is the implicit default with MITLM
        assert resp['restricted'] is False

        # Update the morpheme language model as the admin to create a backup.
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': 'Morpheme language model renamed',
            'corpus': corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.put(mlm_url('update', id=morpheme_language_model_id), params,
                        self.json_headers, admin)
        resp = response.json_body
        morpheme_language_model_count = dbsession.query(old_models.MorphemeLanguageModel).count()
        assert response.content_type == 'application/json'
        assert morpheme_language_model_count == 1

        # Now Update the morpheme language model as the default contributor to create a second backup.
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': 'Morpheme language model renamed by contributor',
            'corpus': corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.put(mlm_url('update', id=morpheme_language_model_id), params,
                        self.json_headers, contrib)
        resp = response.json_body
        morpheme_language_model_count = dbsession.query(MorphemeLanguageModel).count()
        assert morpheme_language_model_count == 1

        # Now GET the morpheme language model backups (as the viewer).
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=view)
        resp = response.json_body
        assert len(resp) == 2
        assert response.content_type == 'application/json'

        # Now update the morpheme language model yet again.
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': 'Morpheme language model updated yet again',
            'corpus': corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.put(mlm_url('update', id=morpheme_language_model_id), params,
                        self.json_headers, contrib)
        resp = response.json_body
        morpheme_language_model_count = dbsession.query(old_models.MorphemeLanguageModel).count()
        assert morpheme_language_model_count == 1

        # Now GET the morpheme language model backups.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=contrib)
        resp = response.json_body
        all_morpheme_language_model_backups = resp
        assert len(resp) == 3

        # Test the paginator GET params.
        paginator = {'items_per_page': 1, 'page': 2}
        response = self.app.get(url('index'), paginator,
                                headers=self.json_headers, extra_environ=admin)
        resp = response.json_body
        assert len(resp['items']) == 1
        assert resp['items'][0]['name'] == all_morpheme_language_model_backups[1]['name']
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'MorphemeLanguageModelBackup', 'order_by_attribute': 'datetime_modified',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=admin)
        resp = response.json_body
        result_set = sorted(all_morpheme_language_model_backups, key=lambda pb: pb['datetime_modified'], reverse=True)
        assert [pb['id'] for pb in resp] == [pb['id'] for pb in result_set]

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'MorphemeLanguageModelBackup', 'order_by_attribute': 'datetime_modified',
                        'order_by_direction': 'desc', 'items_per_page': 1, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=admin)
        resp = response.json_body
        assert result_set[2]['name'] == resp['items'][0]['name']

        # Now test the show action:

        # Get a particular morpheme language model backup
        response = self.app.get(url('show', id=all_morpheme_language_model_backups[0]['id']),
                                headers=self.json_headers, extra_environ=admin)
        resp = response.json_body
        assert resp['name'] == all_morpheme_language_model_backups[0]['name']
        assert response.content_type == 'application/json'

        # A nonexistent morpheme language model backup id will return a 404 error
        response = self.app.get(url('show', id=100987),
                    headers=self.json_headers, extra_environ=view, status=404)
        resp = response.json_body
        assert resp['error'] == 'There is no morpheme language model backup with id 100987'
        assert response.content_type == 'application/json'

        # Attempting to call edit/new/create/delete/update on a read-only resource
        # will return a 404 response
        response = self.app.get(url('edit', id=2232), status=404, extra_environ=admin)
        assert response.json_body['error'] == 'This resource is read-only.'
        response = self.app.get(url('new', id=2232), status=404, extra_environ=admin)
        assert response.json_body['error'] == 'This resource is read-only.'
        response = self.app.post(url('create'), status=404, extra_environ=admin)
        assert response.json_body['error'] == 'This resource is read-only.'
        response = self.app.put(url('update', id=2232), status=404, extra_environ=admin)
        assert response.json_body['error'] == 'This resource is read-only.'
        response = self.app.delete(url('delete', id=2232), status=404, extra_environ=admin)
        assert response.json_body['error'] == 'This resource is read-only.'
        assert response.content_type == 'application/json'
