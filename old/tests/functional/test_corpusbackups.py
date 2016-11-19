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
import pprint
from time import sleep

import transaction

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import (
    Corpus,
    CorpusBackup
)
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods


LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = CorpusBackup._url()
crps_url = Corpus._url()
fs_url = old_models.FormSearch._url()


class TestCorpusbackupsView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_SEARCH_to_web_test_valid_methods()

    def tearDown(self):
        super().tearDown(dirs_to_destroy=['corpus'])

    def test_index(self):
        """Tests that GET & SEARCH /corpusbackups behave correctly.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            tag = old_models.Tag()
            tag.name = 'random tag name'
            dbsession.add(tag)
            dbsession.flush()
            tag_id = tag.id
            transaction.commit()

            # Add 10 forms and use them to generate a valid value for ``test_corpus_content``
            def create_form_from_index(index):
                form = old_models.Form()
                form.transcription = 'Form %d' % index
                translation = old_models.Translation()
                translation.transcription = 'Translation %d' % index
                form.translation = translation
                return form
            forms = [create_form_from_index(i) for i in range(1, 10)]
            dbsession.add_all(forms)
            transaction.commit()
            forms = db.get_forms()
            half_forms = forms[:5]
            form_ids = [form.id for form in forms]
            half_form_ids = [form.id for form in half_forms]
            test_corpus_content = ','.join(map(str, form_ids))
            test_corpus_half_content = ','.join(map(str, half_form_ids))

            # Create a form search model
            query = {'filter': ['Form', 'transcription', 'regex', '[a-zA-Z]{3,}']}
            params = json.dumps({
                'name': 'form search',
                'description': 'This one\'s worth saving!',
                'search': query
            })
            response = self.app.post(fs_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            form_search_id = resp['id']

            # Generate some valid corpus creation input parameters.
            params = self.corpus_create_params.copy()
            params.update({
                'name': 'Corpus',
                'description': 'Covers a lot of the data.',
                'content': test_corpus_content
            })
            params = json.dumps(params)

            # Attempt to create a corpus as a viewer and expect to fail
            response = self.app.post(crps_url('create'), params, self.json_headers,
                                    self.extra_environ_view, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'
            assert response.content_type == 'application/json'

            # Successfully create a corpus as the admin
            assert os.listdir(self.corpora_path) == []
            original_corpus_count = dbsession.query(Corpus).count()
            response = self.app.post(crps_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            corpus_id = resp['id']
            new_corpus_count = dbsession.query(Corpus).count()
            corpus = dbsession.query(Corpus).get(corpus_id)
            corpus_form_ids = sorted([f.id for f in corpus.forms])
            corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
            corpus_dir_contents = os.listdir(corpus_dir)
            assert new_corpus_count == original_corpus_count + 1
            assert resp['name'] == 'Corpus'
            assert resp['description'] == 'Covers a lot of the data.'
            assert corpus_dir_contents == []
            assert response.content_type == 'application/json'
            assert resp['content'] == test_corpus_content
            assert corpus_form_ids == sorted(form_ids)

            # Update the corpus as the contributor -- now we should have one backup
            params = self.corpus_create_params.copy()
            params.update({
                'name': 'Corpus',
                'description': 'Covers a little less data.',
                'content': test_corpus_half_content
            })
            params = json.dumps(params)
            response = self.app.put(crps_url('update', id=corpus_id), params,
                    self.json_headers, self.extra_environ_contrib)
            resp = response.json_body
            corpus_count = new_corpus_count
            new_corpus_count = dbsession.query(Corpus).count()
            corpus = dbsession.query(Corpus).get(corpus_id)
            corpus_form_ids = sorted([f.id for f in corpus.forms])
            assert new_corpus_count == corpus_count
            assert resp['name'] == 'Corpus'
            assert resp['description'] == 'Covers a little less data.' 
            assert response.content_type == 'application/json'
            assert resp['content'] == test_corpus_half_content
            assert corpus_form_ids == sorted(half_form_ids)

            # Update the corpus again -- now we should have two backups
            sleep(1)
            params = self.corpus_create_params.copy()
            params.update({
                'name': 'Corpus',
                'description': 'Covers a little less data.',
                'content': test_corpus_half_content,
                'tags': [tag_id]
            })
            params = json.dumps(params)
            response = self.app.put(crps_url('update', id=corpus_id), params,
                    self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            corpus_count = new_corpus_count
            new_corpus_count = dbsession.query(Corpus).count()
            corpus = dbsession.query(Corpus).get(corpus_id)
            corpus_form_ids = sorted([f.id for f in corpus.forms])
            assert new_corpus_count == corpus_count
            assert resp['name'] == 'Corpus'
            assert resp['description'] == 'Covers a little less data.' 
            assert response.content_type == 'application/json'
            assert resp['content'] == test_corpus_half_content
            assert corpus_form_ids == sorted(half_form_ids)

            all_corpus_backups = dbsession.query(CorpusBackup).order_by(CorpusBackup.id).all()
            all_corpus_backup_ids = [cb.id for cb in all_corpus_backups]
            all_corpus_backup_descriptions = [cb.description for cb in all_corpus_backups]

            # Now request the corpus backups as either the contributor or the viewer and 
            # expect to get them all.
            response = self.app.get(url('index'), headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            assert len(resp) == 2
            assert response.content_type == 'application/json'
            assert resp[0]['modifier']['role'] == 'administrator'
            assert resp[1]['modifier']['role'] == 'contributor'

            # The admin should get them all too.
            response = self.app.get(url('index'), headers=self.json_headers, extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert len(resp) == 2
            assert [cb['id'] for cb in resp] == all_corpus_backup_ids

            # Test the paginator GET params.
            paginator = {'items_per_page': 1, 'page': 2}
            response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp['items']) == 1
            assert resp['paginator']['count'] == 2
            assert response.content_type == 'application/json'
            assert resp['items'][0]['id'] == all_corpus_backup_ids[1]

            # Test the order_by GET params.
            order_by_params = {'order_by_model': 'CorpusBackup',
                'order_by_attribute': 'id', 'order_by_direction': 'desc'}
            response = self.app.get(url('index'), order_by_params,
                            headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            result_set = list(reversed(all_corpus_backup_ids))
            assert [cb['id'] for cb in resp] == result_set

            # Test the order_by *with* paginator.  
            params = {'order_by_model': 'CorpusBackup', 'order_by_attribute': 'id',
                        'order_by_direction': 'desc', 'items_per_page': 1, 'page': 1}
            response = self.app.get(url('index'), params,
                            headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert result_set[0] == resp['items'][0]['id']

            # Now test the show action:

            # Get a specific corpus backup. 
            response = self.app.get(url('show', id=all_corpus_backup_ids[0]),
                                    headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['description'] == 'Covers a lot of the data.'
            assert resp['content'] == test_corpus_content
            assert response.content_type == 'application/json'

            # A nonexistent cb id will return a 404 error
            response = self.app.get(url('show', id=100987),
                        headers=self.json_headers, extra_environ=self.extra_environ_view, status=404)
            resp = response.json_body
            assert resp['error'] == 'There is no corpus backup with id 100987'
            assert response.content_type == 'application/json'

            # Test the search action
            add_SEARCH_to_web_test_valid_methods()

            # A search on corpus backup titles using POST /corpusbackups/search
            json_query = json.dumps({'query': {'filter':
                            ['CorpusBackup', 'description', 'like', '%less%']}})
            response = self.app.post(url('search_post'), json_query,
                            self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            result_set = [name for name in all_corpus_backup_descriptions if 'less' in name]
            assert len(resp) == len(result_set) == 1
            assert resp[0]['description'] == result_set[0]
            assert response.content_type == 'application/json'

            # A search on corpus backup titles using SEARCH /corpusbackups
            json_query = json.dumps({'query': {'filter':
                            ['CorpusBackup', 'description', 'like', '%less%']}})
            response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
                            headers=self.json_headers, environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp) == len(result_set) == 1
            assert resp[0]['description'] == result_set[0]
            assert response.content_type == 'application/json'

            # Attempting to call edit/new/create/delete/update on a read-only resource
            # will return a 404 response
            response = self.app.get(url('edit', id=2232), status=404, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'This resource is read-only.'
            response = self.app.get(url('new', id=2232), status=404, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'This resource is read-only.'
            response = self.app.post(url('create'), status=404, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'This resource is read-only.'
            response = self.app.put(url('update', id=2232), status=404, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'This resource is read-only.'
            response = self.app.delete(url('delete', id=2232), status=404, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'This resource is read-only.'
            assert response.content_type == 'application/json'

    def test_new_search(self):
        """Tests that GET /corpusbackups/new_search returns the search
        parameters for searching the corpus backups resource.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)
            query_builder = SQLAQueryBuilder(
                dbsession, 'CorpusBackup', settings=self.settings)
            response = self.app.get(
                url('new_search'), headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert resp['search_parameters'] == query_builder.get_search_parameters()
