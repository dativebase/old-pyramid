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
from time import sleep

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
import old.models as old_models
from old.models import Speaker
import old.models.modelbuilders as omb
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods


LOGGER = logging.getLogger(__name__)


url = Speaker._url()


################################################################################
# Functions for creating & retrieving test data
################################################################################

class TestSpeakersView(TestView):

    def test_index(self):
        """Tests that GET /speakers returns an array of all speakers and that order_by and pagination parameters work correctly."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 speakers.
        def create_speaker_from_index(index):
            speaker = old_models.Speaker()
            speaker.first_name = 'John%d' % index
            speaker.last_name = 'Doe%d' % index
            speaker.dialect = 'dialect %d' % index
            speaker.page_content = 'page content %d' % index
            return speaker
        speakers = [create_speaker_from_index(i) for i in range(1, 101)]
        dbsession.add_all(speakers)
        dbsession.commit()
        speakers = db.get_speakers(True)
        speakers_count = len(speakers)

        # Test that GET /speakers gives us all of the speakers.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == speakers_count
        assert resp[0]['first_name'] == 'John1'
        assert resp[0]['id'] == speakers[0].id
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['first_name'] == speakers[46].first_name

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'Speaker', 'order_by_attribute': 'first_name',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted([s.first_name for s in speakers], reverse=True)
        assert result_set == [s['first_name'] for s in resp]

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'Speaker', 'order_by_attribute': 'first_name',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert result_set[46] == resp['items'][0]['first_name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'Speaker', 'order_by_attribute': 'first_name',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'Speakerist', 'order_by_attribute': 'prenom',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == speakers[0].id

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
        """Tests that POST /speakers creates a new speaker
        or returns an appropriate error if the input is invalid.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        original_speaker_count = dbsession.query(Speaker).count()

        # Create a valid one
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'John',
            'last_name': 'Doe',
            'page_content': 'page_content',
            'dialect': 'dialect'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_speaker_count = dbsession.query(Speaker).count()
        assert new_speaker_count == original_speaker_count + 1
        assert resp['first_name'] == 'John'
        assert resp['dialect'] == 'dialect'
        assert response.content_type == 'application/json'

        # Invalid because first_name is too long
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'John' * 400,
            'last_name': 'Doe',
            'page_content': 'page_content',
            'dialect': 'dialect'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['first_name'] == 'Enter a value not more than 255 characters long'
        assert response.content_type == 'application/json'

    def test_new(self):
        """Tests that GET /speakers/new returns an empty JSON object."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        response = self.app.get(url('new'), headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp == {'markup_languages': list(oldc.MARKUP_LANGUAGES)}
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /speakers/id updates the speaker with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a speaker to update.
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'first_name',
            'last_name': 'last_name',
            'page_content': 'page_content',
            'dialect': 'dialect'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        speaker_count = dbsession.query(Speaker).count()
        speaker_id = resp['id']
        original_datetime_modified = resp['datetime_modified']

        # Update the speaker
        sleep(1)    # sleep for a second to ensure that MySQL registers a different datetime_modified for the update
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'first_name',
            'last_name': 'last_name',
            'page_content': 'page_content',
            'dialect': 'updated dialect.'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=speaker_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        datetime_modified = resp['datetime_modified']
        new_speaker_count = dbsession.query(Speaker).count()
        assert speaker_count == new_speaker_count
        assert datetime_modified != original_datetime_modified
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        response = self.app.put(url('update', id=speaker_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        speaker_count = new_speaker_count
        new_speaker_count = dbsession.query(Speaker).count()
        our_speaker_datetime_modified = dbsession.query(Speaker).get(speaker_id).datetime_modified
        assert our_speaker_datetime_modified.isoformat() == datetime_modified
        assert speaker_count == new_speaker_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /speakers/id deletes the speaker with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a speaker to delete.
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'first_name',
            'last_name': 'last_name',
            'page_content': 'page_content',
            'dialect': 'dialect'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        speaker_count = dbsession.query(Speaker).count()
        speaker_id = resp['id']

        # Now delete the speaker
        response = self.app.delete(url('delete', id=speaker_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        new_speaker_count = dbsession.query(Speaker).count()
        assert new_speaker_count == speaker_count - 1
        assert resp['id'] == speaker_id
        assert response.content_type == 'application/json'

        # Trying to get the deleted speaker from the db should return None
        deleted_speaker = dbsession.query(Speaker).get(speaker_id)
        assert deleted_speaker is None
        assert response.content_type == 'application/json'

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no speaker with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

    def test_show(self):
        """Tests that GET /speakers/id returns the speaker with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a speaker to show.
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'first_name',
            'last_name': 'last_name',
            'page_content': 'page_content',
            'dialect': 'dialect'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        speaker_id = resp['id']

        # Try to get a speaker using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no speaker with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('show', id=speaker_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['first_name'] == 'first_name'
        assert resp['dialect'] == 'dialect'
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /speakers/id/edit returns a JSON object of data necessary to edit the speaker with id=id.

        The JSON object is of the form {'speaker': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a speaker to edit.
        params = self.speaker_create_params.copy()
        params.update({
            'first_name': 'first_name',
            'last_name': 'last_name',
            'page_content': 'page_content',
            'dialect': 'dialect'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        speaker_id = resp['id']

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=speaker_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no speaker with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('edit', id=speaker_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['speaker']['first_name'] == 'first_name'
        assert resp['data'] == {'markup_languages': list(oldc.MARKUP_LANGUAGES)}
        assert response.content_type == 'application/json'
