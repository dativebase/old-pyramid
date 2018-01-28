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
import json

from old.lib.dbutils import DBUtils
from time import sleep
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.models import ElicitationMethod

LOGGER = logging.getLogger(__name__)


url = ElicitationMethod._url(old_name=TestView.old_name)



################################################################################
# Functions for creating & retrieving test data
################################################################################

class TestElicitationMethodsView(TestView):

    def test_index(self):
        """Tests that GET /elicitationmethods returns an array of all elicitation methods and that order_by and pagination parameters work correctly."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 elicitation methods.
        def create_elicitation_method_from_index(index):
            elicitation_method = old_models.ElicitationMethod()
            elicitation_method.name = 'em%d' % index
            elicitation_method.description = 'description %d' % index
            return elicitation_method
        elicitation_methods = [create_elicitation_method_from_index(i) for i in range(1, 101)]
        dbsession.add_all(elicitation_methods)
        dbsession.commit()
        elicitation_methods = db.get_elicitation_methods(True)
        elicitation_methods_count = len(elicitation_methods)

        # Test that GET /elicitationmethods gives us all of the elicitation methods.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == elicitation_methods_count
        assert resp[0]['name'] == 'em1'
        assert resp[0]['id'] == elicitation_methods[0].id
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['name'] == elicitation_methods[46].name

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'ElicitationMethod', 'order_by_attribute': 'name',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted([em.name for em in elicitation_methods], reverse=True)
        assert result_set == [em['name'] for em in resp]

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'ElicitationMethod', 'order_by_attribute': 'name',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert result_set[46] == resp['items'][0]['name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'ElicitationMethod', 'order_by_attribute': 'name',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'ElicitationMethodist', 'order_by_attribute': 'nominal',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == elicitation_methods[0].id

        # Expect a 400 error when the paginator GET params are empty
        # or are integers less than 1
        paginator = {'items_per_page': 'a', 'page': ''}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter an integer value'
        assert resp['errors']['page'] == 'Please enter a value'

        paginator = {'items_per_page': 0, 'page': -1}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter a number that is 1 or greater'
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'

    def test_create(self):
        """Tests that POST /elicitationmethods creates a new elicitation method
        or returns an appropriate error if the input is invalid.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        original_EM_count = dbsession.query(ElicitationMethod).count()

        # Create a valid one
        params = json.dumps({'name': 'em', 'description': 'Described.'})
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_EM_count = dbsession.query(ElicitationMethod).count()
        assert new_EM_count == original_EM_count + 1
        assert resp['name'] == 'em'
        assert resp['description'] == 'Described.'
        assert response.content_type == 'application/json'

        # Invalid because name is not unique
        params = json.dumps({'name': 'em', 'description': 'Described.'})
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'The submitted value for ElicitationMethod.name is not unique.'
        assert response.content_type == 'application/json'

        # Invalid because name is empty
        params = json.dumps({'name': '', 'description': 'Described.'})
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'Please enter a value'

        # Invalid because name is too long
        params = json.dumps({'name': 'name' * 400, 'description': 'Described.'})
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'Enter a value not more than 255 characters long'

    def test_new(self):
        """Tests that GET /elicitationmethods/new returns an empty JSON object."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        response = self.app.get(url('new'), headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp == {}
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /elicitationmethods/id updates the elicitationmethod with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create an elicitation method to update.
        params = json.dumps({'name': 'name', 'description': 'description'})
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        elicitation_method_count = dbsession.query(ElicitationMethod).count()
        elicitation_method_id = resp['id']
        original_datetime_modified = resp['datetime_modified']

        # Update the elicitation method
        sleep(1)    # sleep for a second to ensure that MySQL registers a different datetime_modified for the update
        params = json.dumps({'name': 'name', 'description': 'More content-ful description.'})
        response = self.app.put(url('update', id=elicitation_method_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        datetime_modified = resp['datetime_modified']
        new_elicitation_method_count = dbsession.query(ElicitationMethod).count()
        assert elicitation_method_count == new_elicitation_method_count
        assert datetime_modified != original_datetime_modified
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        response = self.app.put(url('update', id=elicitation_method_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        elicitation_method_count = new_elicitation_method_count
        new_elicitation_method_count = dbsession.query(ElicitationMethod).count()
        our_EM_datetime_modified = dbsession.query(ElicitationMethod).get(elicitation_method_id).datetime_modified
        assert our_EM_datetime_modified.isoformat() == datetime_modified
        assert elicitation_method_count == new_elicitation_method_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /elicitationmethods/id deletes the elicitation_method with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create an elicitation method to delete.
        params = json.dumps({'name': 'name', 'description': 'description'})
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        elicitation_method_count = dbsession.query(ElicitationMethod).count()
        elicitation_method_id = resp['id']

        # Now delete the elicitation method
        response = self.app.delete(url('delete', id=elicitation_method_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        new_elicitation_method_count = dbsession.query(ElicitationMethod).count()
        assert new_elicitation_method_count == elicitation_method_count - 1
        assert resp['id'] == elicitation_method_id
        assert response.content_type == 'application/json'

        # Trying to get the deleted elicitation method from the db should return None
        deleted_elicitation_method = dbsession.query(ElicitationMethod).get(elicitation_method_id)
        assert deleted_elicitation_method is None

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no elicitation method with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'

    def test_show(self):
        """Tests that GET /elicitationmethods/id returns the elicitation method with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create an elicitation method to show.
        params = json.dumps({'name': 'name', 'description': 'description'})
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        elicitation_method_id = resp['id']

        # Try to get a elicitation_method using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no elicitation method with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'

        # Valid id
        response = self.app.get(url('show', id=elicitation_method_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'name'
        assert resp['description'] == 'description'
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /elicitationmethods/id/edit returns a JSON object of data necessary to edit the elicitation method with id=id.

        The JSON object is of the form {'elicitation_method': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create an elicitation method to edit.
        params = json.dumps({'name': 'name', 'description': 'description'})
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        elicitation_method_id = resp['id']

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=elicitation_method_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no elicitation method with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Valid id
        response = self.app.get(url('edit', id=elicitation_method_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['elicitation_method']['name'] == 'name'
        assert resp['data'] == {}
        assert response.content_type == 'application/json'
