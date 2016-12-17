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

import datetime
import json
import logging
import os
import pprint
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import (
    Corpus,
    CorpusBackup
)
from old.tests import TestView


LOGGER = logging.getLogger(__name__)


url = Corpus._url()
fs_url = old_models.FormSearch._url()


class TestCorporaView(TestView):

    # Clear all models in the database except Language; recreate the corpora.
    def tearDown(self):
        super().tearDown(dirs_to_destroy=['user', 'corpus'])

    def test_index(self):
        """Tests that GET /corpora returns an array of all corpora and that
        order_by and pagination parameters work correctly.
        """

        print('FUCK YOU')
        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 corpora.
        def create_corpus_from_index(index):
            print('creating a corpus from index {}'.format(index))
            corpus = old_models.Corpus()
            corpus.name = 'Corpus %d' % index
            corpus.description = 'A corpus with %d rules' % index
            corpus.content = '1'
            return corpus
        corpora = [create_corpus_from_index(i) for i in range(1, 101)]
        dbsession.add_all(corpora)
        dbsession.commit()
        corpora = db.get_corpora(True)
        corpora_count = len(corpora)

        # Test that GET /corpora gives us all of the corpora.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == corpora_count
        assert resp[0]['name'] == 'Corpus 1'
        assert resp[0]['id'] == corpora[0].id
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['name'] == corpora[46].name
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'Corpus', 'order_by_attribute': 'name',
                    'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted(corpora, key=lambda c: c.name, reverse=True)
        assert [c.id for c in result_set] == [c['id'] for c in resp]
        assert response.content_type == 'application/json'

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'Corpus', 'order_by_attribute': 'name',
                    'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert result_set[46].name == resp['items'][0]['name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'Corpus', 'order_by_attribute': 'name',
                    'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'Corpusist', 'order_by_attribute': 'nominal',
                    'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == corpora[0].id

        # Expect a 400 error when the paginator GET params are empty
        # or are integers less than 1
        paginator = {'items_per_page': 'a', 'page': ''}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter an integer value'
        assert resp['errors']['page'] == 'Please enter a value'
        assert response.content_type == 'application/json'

        paginator = {'items_per_page': 0, 'page': -1}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter a number that is 1 or greater'
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'
        assert response.content_type == 'application/json'

    def test_create(self):
        """Tests that POST /corpora creates a new corpus
        or returns an appropriate error if the input is invalid.

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

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
        dbsession.commit()
        forms = db.get_forms()
        half_forms = forms[:5]
        form_ids = [form.id for form in forms]
        half_form_ids = [form.id for form in half_forms]
        test_corpus_content = ','.join(map(str, half_form_ids))

        # Create a form search model
        query = {'filter': ['Form', 'transcription', 'regex', '[a-zA-Z]{3,}']}
        params = json.dumps({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        response = self.app.post(
            fs_url('create'), params, self.json_headers,
            self.extra_environ_admin)
        resp = response.json_body
        form_search_id = resp['id']

        # Generate some valid corpus creation input parameters.
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus',
            'description': 'Covers a lot of the data.',
            'content': test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)

        # Attempt to create a corpus as a viewer and expect to fail
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_view, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Successfully create a corpus as the admin
        assert os.listdir(self.corpora_path) == []
        original_corpus_count = dbsession.query(Corpus).count()
        response = self.app.post(url('create'), params, self.json_headers,
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
        assert resp['form_search']['id'] == form_search_id

        # Invalid because ``form_search`` refers to a non-existent form search.
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus Chi',
            'description': 'Covers a lot of the data, padre.',
            'content': test_corpus_content,
            'form_search': 123456789
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert new_corpus_count == corpus_count
        assert resp['errors']['form_search'] == 'There is no form search with id 123456789.'
        assert response.content_type == 'application/json'

        # Invalid because ``content`` refers to non-existent forms
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus Chi Squared',
            'description': 'Covers a lot of the data, padre.',
            'content': test_corpus_content + ',123456789'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert new_corpus_count == corpus_count
        #assert 'There is no form with id 123456789.' in resp['errors']['forms']
        assert resp['errors'] == 'At least one form id in the content was invalid.'
        assert response.content_type == 'application/json'

        # Invalid because name is not unique
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus',
            'description': 'Covers a lot of the data, dude.',
            'content': test_corpus_content
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert new_corpus_count == corpus_count
        assert resp['errors']['name'] == 'The submitted value for Corpus.name is not unique.'
        assert response.content_type == 'application/json'

        # Invalid because name must be a non-empty string
        params = self.corpus_create_params.copy()
        params.update({
            'name': '',
            'description': 'Covers a lot of the data, sista.',
            'content': test_corpus_content
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert new_corpus_count == corpus_count
        assert resp['errors']['name'] == 'Please enter a value'
        assert response.content_type == 'application/json'

        # Invalid because name must be a non-empty string
        params = self.corpus_create_params.copy()
        params.update({
            'name': None,
            'description': 'Covers a lot of the data, young\'un.',
            'content': test_corpus_content
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert new_corpus_count == corpus_count
        assert resp['errors']['name'] == 'Please enter a value'
        assert response.content_type == 'application/json'

        # Invalid because name is too long.
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus' * 200,
            'description': 'Covers a lot of the data, squirrel salad.',
            'content': test_corpus_content
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert new_corpus_count == corpus_count
        assert resp['errors']['name'] == 'Enter a value not more than 255 characters long'
        assert response.content_type == 'application/json'

        # Create a corpus whose forms are specified in the content value.
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus by contents',
            'description': 'Covers a lot of the data.',
            'content': test_corpus_content
        })
        params = json.dumps(params)
        original_corpus_count = dbsession.query(Corpus).count()
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        corpus_id = resp['id']
        new_corpus_count = dbsession.query(Corpus).count()
        corpus = dbsession.query(Corpus).get(corpus_id)
        corpus_form_ids = sorted([f.id for f in corpus.forms])
        corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
        corpus_dir_contents = os.listdir(corpus_dir)
        assert new_corpus_count == original_corpus_count + 1
        assert resp['name'] == 'Corpus by contents'
        assert resp['description'] == 'Covers a lot of the data.'
        assert corpus_dir_contents == []
        assert response.content_type == 'application/json'
        assert resp['content'] == test_corpus_content
        assert corpus_form_ids == sorted(half_form_ids)
        assert resp['form_search'] == None

    def test_new(self):
        """Tests that GET /corpora/new returns data needed to create a new corpus."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a tag
        t = omb.generate_restricted_tag()
        dbsession.add(t)
        dbsession.commit()

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

        # Get the data currently in the db (see websetup.py for the test data).
        data = {
            'tags': db.get_mini_dicts_getter('Tag')(),
            'users': db.get_mini_dicts_getter('User')(),
            'form_searches': db.get_mini_dicts_getter('FormSearch')(),
            'corpus_formats': list(oldc.CORPUS_FORMATS.keys())
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        # Unauthorized user ('viewer') should return a 401 status code on the
        # new action, which requires a 'contributor' or an 'administrator'.
        response = self.app.get(url('new'), status=403,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['error'] == 'You are not authorized to access this resource.'

        # Get the data needed to create a new corpus; don't send any params.
        response = self.app.get(url('new'), headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp['users'] == data['users']
        assert resp['form_searches'] == data['form_searches']
        assert resp['tags'] == data['tags']
        assert resp['corpus_formats'] == data['corpus_formats']
        assert response.content_type == 'application/json'

        # GET /new_corpus with params.  Param values are treated as strings, not
        # JSON.  If any params are specified, the default is to return a JSON
        # array corresponding to store for the param.  There are three cases
        # that will result in an empty JSON array being returned:
        # 1. the param is not specified
        # 2. the value of the specified param is an empty string
        # 3. the value of the specified param is an ISO 8601 UTC datetime
        #    string that matches the most recent datetime_modified value of the
        #    store in question.
        params = {
            # Value is any string: 'form_searches' will be in response.
            'form_searches': 'anything can go here!',
            # Value is ISO 8601 UTC datetime string that does not match the most
            # recent Tag.datetime_modified value: 'tags' *will* be in
            # response.
            'tags': datetime.datetime.utcnow().isoformat(),
            # Value is ISO 8601 UTC datetime string that does match the most
            # recent SyntacticCategory.datetime_modified value:
            # 'syntactic_categories' will *not* be in response.
            'users': db.get_most_recent_modification_datetime(
                'User').isoformat()
        }
        response = self.app.get(url('new'), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['form_searches'] == data['form_searches']
        assert resp['tags'] == data['tags']
        assert resp['users'] == []
        assert resp['corpus_formats'] == data['corpus_formats']

    def test_update(self):
        """Tests that PUT /corpora/id updates the corpus with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

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
        dbsession.commit()
        forms = db.get_forms()
        form_ids = [form.id for form in forms]
        test_corpus_content = ','.join(map(str, form_ids))
        new_test_corpus_content = ','.join(map(str, form_ids[:5]))

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
            'content': test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)

        # Successfully create a corpus as the admin
        assert os.listdir(self.corpora_path) == []
        original_corpus_count = dbsession.query(Corpus).count()
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        corpus_id = resp['id']
        new_corpus_count = dbsession.query(Corpus).count()
        corpus = dbsession.query(Corpus).get(corpus_id)
        corpus_form_ids = sorted([f.id for f in corpus.forms])
        corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
        corpus_dir_contents = os.listdir(corpus_dir)
        original_datetime_modified = resp['datetime_modified']
        assert new_corpus_count == original_corpus_count + 1
        assert resp['name'] == 'Corpus'
        assert resp['description'] == 'Covers a lot of the data.'
        assert corpus_dir_contents == []
        assert response.content_type == 'application/json'
        assert resp['content'] == test_corpus_content
        assert corpus_form_ids == sorted(form_ids)
        assert resp['form_search']['id'] == form_search_id

        # Update the corpus
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        orig_backup_count = dbsession.query(CorpusBackup).count()
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus',
            'description': 'Covers a lot of the data.  Best yet!',
            'content': new_test_corpus_content,        # Here is the change
            'form_search': form_search_id
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=corpus_id), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        new_backup_count = dbsession.query(CorpusBackup).count()
        datetime_modified = resp['datetime_modified']
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        assert corpus_count == new_corpus_count
        assert datetime_modified != original_datetime_modified
        assert resp['description'] == 'Covers a lot of the data.  Best yet!'
        assert resp['content'] == new_test_corpus_content
        assert response.content_type == 'application/json'
        assert orig_backup_count + 1 == new_backup_count
        assert response.content_type == 'application/json'
        backup = dbsession.query(CorpusBackup).filter(
            CorpusBackup.UUID==str(resp['UUID'])).order_by(
            desc(CorpusBackup.id)).first()
        assert backup.datetime_modified.strftime(oldc.ISO_STRFTIME) == original_datetime_modified
        assert backup.content == test_corpus_content

        # Attempt an update with no new input and expect to fail
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        response = self.app.put(url('update', id=corpus_id), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        dbsession.expire(corpus)
        our_corpus_datetime_modified = dbsession.query(Corpus).get(corpus_id).datetime_modified
        assert our_corpus_datetime_modified.strftime(oldc.ISO_STRFTIME) == datetime_modified
        assert corpus_count == new_corpus_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /corpora/id deletes the corpus with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Count the original number of corpora and corpus_backups.
        corpus_count = dbsession.query(Corpus).count()
        corpus_backup_count = dbsession.query(CorpusBackup).count()

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
        dbsession.commit()
        forms = db.get_forms()
        form_ids = [form.id for form in forms]
        test_corpus_content = ','.join(map(str, form_ids))

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
            'content': test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)

        # Successfully create a corpus as the admin
        assert os.listdir(self.corpora_path) == []
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        corpus_id = resp['id']
        corpus = dbsession.query(Corpus).get(corpus_id)
        corpus_form_ids = sorted([f.id for f in corpus.forms])
        corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
        corpus_dir_contents = os.listdir(corpus_dir)
        assert resp['name'] == 'Corpus'
        assert resp['description'] == 'Covers a lot of the data.'
        assert corpus_dir_contents == []
        assert response.content_type == 'application/json'
        assert resp['content'] == test_corpus_content
        assert corpus_form_ids == sorted(form_ids)
        assert resp['form_search']['id'] == form_search_id

        # Now count the corpora and corpus_backups.
        new_corpus_count = dbsession.query(Corpus).count()
        new_corpus_backup_count = dbsession.query(CorpusBackup).count()
        assert new_corpus_count == corpus_count + 1
        assert new_corpus_backup_count == corpus_backup_count

        # Now delete the corpus
        response = self.app.delete(url('delete', id=corpus_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        corpus_count = new_corpus_count
        new_corpus_count = dbsession.query(Corpus).count()
        corpus_backup_count = new_corpus_backup_count
        new_corpus_backup_count = dbsession.query(CorpusBackup).count()
        assert new_corpus_count == corpus_count - 1
        assert new_corpus_backup_count == corpus_backup_count + 1
        assert resp['id'] == corpus_id
        assert response.content_type == 'application/json'
        assert not os.path.exists(corpus_dir)
        assert resp['content'] == test_corpus_content

        # Trying to get the deleted corpus from the db should return None
        dbsession.expire(corpus)
        deleted_corpus = dbsession.query(Corpus).get(corpus_id)
        assert deleted_corpus == None

        # The backed up corpus should have the deleted corpus's attributes
        backed_up_corpus = dbsession.query(CorpusBackup).filter(
            CorpusBackup.UUID==str(resp['UUID'])).first()
        assert backed_up_corpus.name == resp['name']
        modifier = json.loads(str(backed_up_corpus.modifier))
        assert modifier['first_name'] == 'Admin'
        assert backed_up_corpus.datetime_entered.strftime(oldc.ISO_STRFTIME) == resp['datetime_entered']
        assert backed_up_corpus.UUID == resp['UUID']

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no corpus with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

    def test_show(self):
        """Tests that GET /corpora/id returns the corpus with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

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
        dbsession.commit()
        forms = db.get_forms()
        form_ids = [form.id for form in forms]
        test_corpus_content = ','.join(map(str, form_ids))

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
            'content': test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)

        # Successfully create a corpus as the admin
        assert os.listdir(self.corpora_path) == []
        original_corpus_count = dbsession.query(Corpus).count()
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        corpus_count = dbsession.query(Corpus).count()
        corpus_id = resp['id']
        corpus = dbsession.query(Corpus).get(corpus_id)
        corpus_form_ids = sorted([f.id for f in corpus.forms])
        corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
        corpus_dir_contents = os.listdir(corpus_dir)
        assert resp['name'] == 'Corpus'
        assert resp['description'] == 'Covers a lot of the data.'
        assert corpus_dir_contents == []
        assert response.content_type == 'application/json'
        assert resp['content'] == test_corpus_content
        assert corpus_form_ids == sorted(form_ids)
        assert resp['form_search']['id'] == form_search_id
        assert corpus_count == original_corpus_count + 1

        # Try to get a corpus using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no corpus with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('show', id=corpus_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'Corpus'
        assert resp['description'] == 'Covers a lot of the data.'
        assert resp['content'] == test_corpus_content
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /corpora/id/edit returns a JSON object of data necessary to edit the corpus with id=id.

        The JSON object is of the form {'corpus': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

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
        dbsession.commit()
        forms = db.get_forms()
        form_ids = [form.id for form in forms]
        test_corpus_content = ','.join(map(str, form_ids))

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
            'content': test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)

        # Successfully create a corpus as the admin
        assert os.listdir(self.corpora_path) == []
        original_corpus_count = dbsession.query(Corpus).count()
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        corpus_count = dbsession.query(Corpus).count()
        corpus_id = resp['id']
        corpus = dbsession.query(Corpus).get(corpus_id)
        corpus_form_ids = sorted([f.id for f in corpus.forms])
        corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
        corpus_dir_contents = os.listdir(corpus_dir)
        assert resp['name'] == 'Corpus'
        assert resp['description'] == 'Covers a lot of the data.'
        assert corpus_dir_contents == []
        assert response.content_type == 'application/json'
        assert resp['content'] == test_corpus_content
        assert corpus_form_ids == sorted(form_ids)
        assert resp['form_search']['id'] == form_search_id
        assert corpus_count == original_corpus_count + 1

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=corpus_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no corpus with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Get the data currently in the db (see websetup.py for the test data).
        data = {
            'tags': db.get_mini_dicts_getter('Tag')(),
            'users': db.get_mini_dicts_getter('User')(),
            'form_searches': db.get_mini_dicts_getter('FormSearch')(),
            'corpus_formats': list(oldc.CORPUS_FORMATS.keys())
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        # Valid id
        response = self.app.get(url('edit', id=corpus_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['corpus']['name'] == 'Corpus'
        assert resp['data'] == data
        assert response.content_type == 'application/json'

    def test_history(self):
        """Tests that GET /corpora/id/history returns the corpus with id=id and
        its previous incarnations.
        The JSON object returned is of the form
        {'corpus': corpus, 'previous_versions': [...]}.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        users = db.get_users()
        contributor_id = [u for u in users if u.role=='contributor'][0].id
        administrator_id = [u for u in users if u.role=='administrator'][0].id

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
        dbsession.commit()
        forms = db.get_forms()
        form_ids = [form.id for form in forms]
        test_corpus_content = ','.join(map(str, form_ids))
        new_test_corpus_content = ','.join(map(str, form_ids[:5]))
        newest_test_corpus_content = ','.join(map(str, form_ids[:4]))

        # Create a form search model
        query = {'filter': ['Form', 'transcription', 'regex', '[a-zA-Z]{3,}']}
        params = json.dumps({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        response = self.app.post(fs_url('create'), params,
                                    self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        form_search_id = resp['id']

        # Generate some valid corpus creation input parameters.
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus',
            'description': 'Covers a lot of the data.',
            'content': test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)

        # Successfully create a corpus as the admin
        assert os.listdir(self.corpora_path) == []
        original_corpus_count = dbsession.query(Corpus).count()
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        corpus_count = dbsession.query(Corpus).count()
        corpus_id = resp['id']
        corpus = dbsession.query(Corpus).get(corpus_id)
        corpus_form_ids = sorted([f.id for f in corpus.forms])
        corpus_dir = os.path.join(self.corpora_path, 'corpus_%d' % corpus_id)
        corpus_dir_contents = os.listdir(corpus_dir)
        original_datetime_modified = resp['datetime_modified']
        assert resp['name'] == 'Corpus'
        assert resp['description'] == 'Covers a lot of the data.'
        assert corpus_dir_contents == []
        assert response.content_type == 'application/json'
        assert resp['content'] == test_corpus_content
        assert corpus_form_ids == sorted(form_ids)
        assert resp['form_search']['id'] == form_search_id
        assert corpus_count == original_corpus_count + 1

        # Update the corpus as the admin.
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        orig_backup_count = dbsession.query(CorpusBackup).count()
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus',
            'description': 'Covers a lot of the data.  Best yet!',
            'content': new_test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=corpus_id), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        new_backup_count = dbsession.query(CorpusBackup).count()
        first_update_datetime_modified = datetime_modified = resp['datetime_modified']
        new_corpus_count = dbsession.query(Corpus).count()
        assert corpus_count == new_corpus_count
        assert datetime_modified != original_datetime_modified
        assert resp['description'] == 'Covers a lot of the data.  Best yet!'
        assert resp['content'] == new_test_corpus_content
        assert response.content_type == 'application/json'
        assert orig_backup_count + 1 == new_backup_count
        backup = dbsession.query(CorpusBackup).filter(
            CorpusBackup.UUID==str(resp['UUID'])).order_by(
            desc(CorpusBackup.id)).first()
        assert backup.datetime_modified.strftime(oldc.ISO_STRFTIME) == original_datetime_modified
        assert backup.content == test_corpus_content
        assert json.loads(backup.modifier)['first_name'] == 'Admin'
        assert response.content_type == 'application/json'

        # Update the corpus as the contributor.
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        orig_backup_count = dbsession.query(CorpusBackup).count()
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus',
            'description': 'Covers even more data.  Better than ever!',
            'content': newest_test_corpus_content,
            'form_search': form_search_id
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=corpus_id), params, self.json_headers,
                                self.extra_environ_contrib)
        resp = response.json_body
        backup_count = new_backup_count
        new_backup_count = dbsession.query(CorpusBackup).count()
        datetime_modified = resp['datetime_modified']
        new_corpus_count = dbsession.query(Corpus).count()
        assert corpus_count == new_corpus_count == 1
        assert datetime_modified != original_datetime_modified
        assert resp['description'] == 'Covers even more data.  Better than ever!'
        assert resp['content'] == newest_test_corpus_content
        assert resp['modifier']['id'] == contributor_id
        assert response.content_type == 'application/json'
        assert backup_count + 1 == new_backup_count
        backup = dbsession.query(CorpusBackup).filter(
            CorpusBackup.UUID==str(resp['UUID'])).order_by(
            desc(CorpusBackup.id)).first()
        assert backup.datetime_modified.strftime(oldc.ISO_STRFTIME) == first_update_datetime_modified
        assert backup.content == new_test_corpus_content
        assert json.loads(backup.modifier)['first_name'] == 'Admin'
        assert response.content_type == 'application/json'

        # Now get the history of this corpus.
        extra_environ = {'test.authentication.role': 'contributor',
                        'test.application_settings': True}
        response = self.app.get(
            '/corpora/{}/history'.format(corpus_id),
            headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert 'corpus' in resp
        assert 'previous_versions' in resp
        first_version = resp['previous_versions'][1]
        second_version = resp['previous_versions'][0]
        current_version = resp['corpus']

        assert first_version['name'] == 'Corpus'
        assert first_version['description'] == 'Covers a lot of the data.'
        assert first_version['enterer']['id'] == administrator_id
        assert first_version['modifier']['id'] == administrator_id
        # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
        # so the test will fail/be inconsistent with <
        assert first_version['datetime_modified'] <= second_version['datetime_modified']

        assert second_version['name'] == 'Corpus'
        assert second_version['description'] == 'Covers a lot of the data.  Best yet!'
        assert second_version['content'] == new_test_corpus_content
        assert second_version['enterer']['id'] == administrator_id
        assert second_version['modifier']['id'] == administrator_id
        assert second_version['datetime_modified'] <= current_version['datetime_modified']

        assert current_version['name'] == 'Corpus'
        assert current_version['description'] == 'Covers even more data.  Better than ever!'
        assert current_version['content'] == newest_test_corpus_content
        assert current_version['enterer']['id'] == administrator_id
        assert current_version['modifier']['id'] == contributor_id

        # Get the history using the corpus's UUID and expect it to be the same
        # as the one retrieved above
        corpus_UUID = resp['corpus']['UUID']
        response = self.app.get(
            '/corpora/{}/history'.format(corpus_UUID),
            headers=self.json_headers, extra_environ=extra_environ)
        resp_UUID = response.json_body
        assert resp == resp_UUID

        # Attempt to call history with an invalid id and an invalid UUID and
        # expect 404 errors in both cases.
        bad_id = 103
        bad_UUID = str(uuid4())
        response = self.app.get(
            '/corpora/{}/history'.format(bad_id),
            headers=self.json_headers, extra_environ=extra_environ,
            status=404)
        resp = response.json_body
        assert resp['error'] == 'No corpora or corpus backups match %d' % bad_id
        response = self.app.get(
            '/corpora/{}/history'.format(bad_UUID),
            headers=self.json_headers, extra_environ=extra_environ,
            status=404)
        resp = response.json_body
        assert resp['error'] == 'No corpora or corpus backups match %s' % bad_UUID

        # Now delete the corpus ...
        response = self.app.delete(url('delete', id=corpus_id),
                        headers=self.json_headers, extra_environ=extra_environ)

        # ... and get its history again, this time using the corpus's UUID
        response = self.app.get(
            '/corpora/{}/history'.format(corpus_UUID),
            headers=self.json_headers, extra_environ=extra_environ)
        by_UUID_resp = response.json_body
        assert by_UUID_resp['corpus'] == None
        assert len(by_UUID_resp['previous_versions']) == 3
        first_version = by_UUID_resp['previous_versions'][2]
        second_version = by_UUID_resp['previous_versions'][1]
        third_version = by_UUID_resp['previous_versions'][0]

        assert first_version['name'] == 'Corpus'
        assert first_version['description'] == 'Covers a lot of the data.'
        assert first_version['enterer']['id'] == administrator_id
        assert first_version['modifier']['id'] == administrator_id
        # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
        # so the test will fail/be inconsistent with <
        assert first_version['datetime_modified'] <= second_version['datetime_modified']

        assert second_version['name'] == 'Corpus'
        assert second_version['description'] == 'Covers a lot of the data.  Best yet!'
        assert second_version['content'] == new_test_corpus_content
        assert second_version['enterer']['id'] == administrator_id
        assert second_version['modifier']['id'] == administrator_id
        assert second_version['datetime_modified'] <= third_version['datetime_modified']

        assert third_version['name'] == 'Corpus'
        assert third_version['description'] == 'Covers even more data.  Better than ever!'
        assert third_version['content'] == newest_test_corpus_content
        assert third_version['enterer']['id'] == administrator_id
        assert third_version['modifier']['id'] == contributor_id

        # Get the deleted corpus's history again, this time using its id.  The 
        # response should be the same as the response received using the UUID.
        response = self.app.get(
            '/corpora/{}/history'.format(corpus_id),
            headers=self.json_headers, extra_environ=extra_environ)
        by_corpus_id_resp = response.json_body
        assert by_corpus_id_resp == by_UUID_resp
