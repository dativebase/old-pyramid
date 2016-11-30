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

import json
import logging
import os

import transaction

from old.lib.dbutils import DBUtils
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
from old.models import Morphology


LOGGER = logging.getLogger(__name__)


url = old_models.MorphologyBackup._url()
mgy_url = old_models.Morphology._url()
cp_url = old_models.Corpus._url()



class TestMorphologybackupsView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def tearDown(self):
        super().tearDown(dirs_to_destroy=['morphology'])

    def test_index(self):
        """Tests that ``GET /morphologybackups`` behaves correctly.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Define some extra_environs
            view = {'test.authentication.role': 'viewer', 'test.application_settings': True}
            contrib = {'test.authentication.role': 'contributor', 'test.application_settings': True}
            admin = {'test.authentication.role': 'administrator', 'test.application_settings': True}

            # Create a corpus
            params = self.corpus_create_params.copy()
            params.update({
                'name': 'Corpus',
                'description': 'A description of the corpus',
            })
            params = json.dumps(params)
            response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            corpus_id = resp['id']

            # Create a morphology.
            params = self.morphology_create_params.copy()
            params.update({
                'name': 'Morphology',
                'description': 'A description of this morphology.',
                'script_type': 'lexc',
                'rules_corpus': corpus_id,
                'extract_morphemes_from_rules_corpus': True
            })
            params = json.dumps(params)
            response = self.app.post(mgy_url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            morphology_count = dbsession.query(Morphology).count()
            morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % resp['id'])
            morphology_dir_contents = os.listdir(morphology_dir)
            morphology_id = resp['id']
            assert morphology_count == 1
            assert resp['name'] == 'Morphology'
            assert resp['description'] == 'A description of this morphology.'
            assert 'morphology_%d.script' % morphology_id not in morphology_dir_contents # generate has not yet been requested.
            assert response.content_type == 'application/json'
            assert resp['script_type'] == 'lexc'
            assert resp['rules'] == ''
            assert resp['rules_generated'] is None
            assert resp['generate_attempt'] is None

            # Update the morphology as the admin to create a morphology backup.
            params = self.morphology_create_params.copy()
            params.update({
                'name': 'Morphology Renamed',
                'description': 'A description of this morphology.',
                'script_type': 'lexc',
                'rules_corpus': corpus_id,
                'extract_morphemes_from_rules_corpus': True
            })
            params = json.dumps(params)
            response = self.app.put(mgy_url('update', id=morphology_id), params,
                            self.json_headers, admin)
            resp = response.json_body
            morphology_count = dbsession.query(old_models.Morphology).count()
            assert response.content_type == 'application/json'
            assert morphology_count == 1

            # Now Update the morphology as the default contributor to create a second backup.
            params = self.morphology_create_params.copy()
            params.update({
                'name': 'Morphology Renamed by Contributor',
                'description': 'A description of this morphology.',
                'script_type': 'lexc',
                'rules_corpus': corpus_id,
                'extract_morphemes_from_rules_corpus': True
            })
            params = json.dumps(params)
            response = self.app.put(mgy_url('update', id=morphology_id), params,
                            self.json_headers, contrib)
            resp = response.json_body
            morphology_count = dbsession.query(old_models.Morphology).count()
            assert morphology_count == 1

            # Now GET the morphology backups (as the viewer).
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=view)
            resp = response.json_body
            assert len(resp) == 2
            assert response.content_type == 'application/json'

            # Now update the morphology.
            params = self.morphology_create_params.copy()
            params.update({
                'name': 'Morphology Updated',
                'description': 'A description of this morphology.',
                'script_type': 'lexc',
                'rules_corpus': corpus_id,
                'extract_morphemes_from_rules_corpus': True
            })
            params = json.dumps(params)
            response = self.app.put(mgy_url('update', id=morphology_id), params,
                            self.json_headers, contrib)
            resp = response.json_body
            morphology_count = dbsession.query(old_models.Morphology).count()
            assert morphology_count == 1

            # Now GET the morphology backups.  Admin and contrib should see 4 and the
            # viewer should see 1
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=contrib)
            resp = response.json_body
            all_morphology_backups = resp
            assert len(resp) == 3

            # Test the paginator GET params.
            paginator = {'items_per_page': 1, 'page': 2}
            response = self.app.get(url('index'), paginator,
                                    headers=self.json_headers, extra_environ=admin)
            resp = response.json_body
            assert len(resp['items']) == 1
            assert resp['items'][0]['name'] == all_morphology_backups[1]['name']
            assert response.content_type == 'application/json'

            # Test the order_by GET params.
            order_by_params = {'order_by_model': 'MorphologyBackup', 'order_by_attribute': 'datetime_modified',
                         'order_by_direction': 'desc'}
            response = self.app.get(url('index'), order_by_params,
                            headers=self.json_headers, extra_environ=admin)
            resp = response.json_body
            result_set = sorted(all_morphology_backups, key=lambda pb: pb['datetime_modified'], reverse=True)
            assert [pb['id'] for pb in resp] == [pb['id'] for pb in result_set]

            # Test the order_by *with* paginator.
            params = {'order_by_model': 'MorphologyBackup', 'order_by_attribute': 'datetime_modified',
                         'order_by_direction': 'desc', 'items_per_page': 1, 'page': 3}
            response = self.app.get(url('index'), params,
                            headers=self.json_headers, extra_environ=admin)
            resp = response.json_body
            assert result_set[2]['name'] == resp['items'][0]['name']

            # Now test the show action:

            # Get a particular morphology backup
            response = self.app.get(url('show', id=all_morphology_backups[0]['id']),
                                    headers=self.json_headers, extra_environ=admin)
            resp = response.json_body
            assert resp['name'] == all_morphology_backups[0]['name']
            assert response.content_type == 'application/json'

            # A nonexistent pb id will return a 404 error
            response = self.app.get(url('show', id=100987),
                        headers=self.json_headers, extra_environ=view, status=404)
            resp = response.json_body
            assert resp['error'] == 'There is no morphology backup with id 100987'
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

