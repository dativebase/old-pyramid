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
import pprint
from time import sleep
import transaction

import pytest

import old.lib.helpers as h
from old.models import Form, Tag
from old.tests import TestView, url

from old.models import (
    get_engine,
    get_session_factory,
    get_tm_session,
)

LOGGER = logging.getLogger(__name__)


def create_tag_from_index(index):
    tag = Tag()
    tag.name = 'tag%d' % index
    tag.description = 'description %d' % index
    return tag


RSRCS_PATH = '/tags'
RSRC_PATH = '/tags/{}'


###############################################################################
# Functions for creating & retrieving test data
###############################################################################

class TestTagsView(TestView):

    @pytest.mark.skip(reason='because')
    def test_index(self):
        """Tests that GET /tags returns an array of all tags and that order_by
        and pagination parameters work correctly.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            # Add 100 tags.
            tags = [create_tag_from_index(i + 1) for i in range(100)]
            dbsession.add_all(tags)
            transaction.commit()
            tags = dbsession.query(Tag).all()
            tags_count = len(tags)
            # Test that GET /tags gives us all of the tags.
            response = self.app.get(
                RSRCS_PATH, headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert len(resp) == tags_count
            assert resp[0]['name'] == 'tag1'
            assert resp[0]['id'] == tags[0].id
            assert response.content_type == 'application/json'

            # Test the paginator GET params.
            paginator = {'items_per_page': 23, 'page': 3}
            response = self.app.get(
                RSRCS_PATH, paginator, headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert len(resp['items']) == 23
            assert resp['items'][0]['name'] == tags[46].name
            assert response.content_type == 'application/json'

            # Test the order_by GET params.
            order_by_params = {
                'order_by_model': 'Tag',
                'order_by_attribute': 'name',
                'order_by_direction': 'desc'
            }
            response = self.app.get(
                RSRCS_PATH, order_by_params, headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            result_set = sorted([t.name for t in tags], reverse=True)
            assert result_set == [t['name'] for t in resp]

            # Test the order_by *with* paginator.
            params = {
                'order_by_model': 'Tag',
                'order_by_attribute': 'name',
                'order_by_direction': 'desc',
                'items_per_page': 23, 'page': 3
            }
            response = self.app.get(
                RSRCS_PATH, params, headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert result_set[46] == resp['items'][0]['name']
            assert response.content_type == 'application/json'

            # Expect a 400 error when the order_by_direction param is invalid
            order_by_params = {
                'order_by_model': 'Tag',
                'order_by_attribute': 'name',
                'order_by_direction': 'descending'
            }
            response = self.app.get(
                RSRCS_PATH, order_by_params, status=400,
                headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert resp['errors']['order_by_direction'] == (
                "Value must be one of: asc; desc (not 'descending')")
            assert response.content_type == 'application/json'

            # Expect the default BY id ASCENDING ordering when the
            # order_by_model/Attribute param is invalid.
            order_by_params = {
                'order_by_model': 'Tagist',
                'order_by_attribute': 'nominal',
                'order_by_direction': 'desc'
            }
            response = self.app.get(
                RSRCS_PATH, order_by_params, headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert resp[0]['id'] == tags[0].id

            # Expect a 400 error when the paginator GET params are empty
            # or are integers less than 1
            paginator = {'items_per_page': 'a', 'page': ''}
            response = self.app.get(
                RSRCS_PATH, paginator, headers=self.json_headers,
                extra_environ=self.extra_environ_view, status=400)
            resp = response.json_body
            assert resp['errors']['items_per_page'] == (
                'Please enter an integer value')
            assert resp['errors']['page'] == 'Please enter a value'
            assert response.content_type == 'application/json'

            paginator = {'items_per_page': 0, 'page': -1}
            response = self.app.get(
                RSRCS_PATH, paginator, headers=self.json_headers,
                extra_environ=self.extra_environ_view, status=400)
            resp = response.json_body
            assert resp['errors']['items_per_page'] == (
                'Please enter a number that is 1 or greater')
            assert resp['errors']['page'] == (
                'Please enter a number that is 1 or greater')
            assert response.content_type == 'application/json'

    @pytest.mark.skip(reason='because')
    def test_create(self):
        """Tests that POST /tags creates a new tag
        or returns an appropriate error if the input is invalid.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            original_tag_count = dbsession.query(Tag).count()

            # Create a valid one
            params = json.dumps({'name': 'tag', 'description': 'Described.'})
            response = self.app.post(
                RSRCS_PATH, params, self.json_headers,
                self.extra_environ_admin)
            resp = response.json_body
            new_tag_count = dbsession.query(Tag).count()
            assert new_tag_count == original_tag_count + 1
            assert resp['name'] == 'tag'
            assert resp['description'] == 'Described.'
            assert response.content_type == 'application/json'

            # Invalid because name is not unique
            params = json.dumps({'name': 'tag', 'description': 'Described.'})
            response = self.app.post(
                RSRCS_PATH, params, self.json_headers,
                self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['errors']['name'] == (
                'The submitted value for Tag.name is not unique.')

            # Invalid because name is empty
            params = json.dumps({'name': '', 'description': 'Described.'})
            response = self.app.post(
                RSRCS_PATH, params, self.json_headers,
                self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['errors']['name'] == 'Please enter a value'
            assert response.content_type == 'application/json'

            # Invalid because name is too long
            params = json.dumps({
                'name': 'name' * 400,
                'description': 'Described.'
            })
            response = self.app.post(
                RSRCS_PATH, params, self.json_headers,
                self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['errors']['name'] == (
                'Enter a value not more than 255 characters long')
            assert response.content_type == 'application/json'

    @pytest.mark.skip(reason='because')
    def test_new(self):
        """Tests that GET /tags/new returns an empty JSON object."""
        response = self.app.get('/tags/new', headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp == {}
        assert response.content_type == 'application/json'

    @pytest.mark.skip(reason='because')
    def test_update(self):
        """Tests that PUT /tags/id updates the tag with id=id."""

        with transaction.manager:
            dbsession = self.get_dbsession()

            # Create a tag to update.
            params = json.dumps({'name': 'name', 'description': 'description'})
            response = self.app.post(RSRCS_PATH, params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            print(resp)
            tag_count = dbsession.query(Tag).count()
            tag_id = resp['id']
            original_datetime_modified = resp['datetime_modified']

            # Update the tag
            # Sleep for a second to ensure that MySQL registers a different
            # datetime_modified for the update.
            sleep(1)
            params = json.dumps({
                'name': 'name',
                'description': 'More content-ful description.'
            })
            response = self.app.put(
                RSRC_PATH.format(tag_id), params, self.json_headers,
                self.extra_environ_admin)
            resp = response.json_body
            datetime_modified = resp['datetime_modified']
            new_tag_count = dbsession.query(Tag).count()
            assert tag_count == new_tag_count
            assert datetime_modified != original_datetime_modified
            assert response.content_type == 'application/json'

            # Attempt an update with no new input and expect to fail
            # Sleep for a second to ensure that MySQL could register a different
            # datetime_modified for the update
            sleep(1)
            response = self.app.put(
                RSRC_PATH.format(tag_id), params, self.json_headers,
                self.extra_environ_admin, status=400)
            resp = response.json_body
            tag_count = new_tag_count
            new_tag_count = dbsession.query(Tag).count()
            our_tag_datetime_modified = dbsession.query(Tag)\
                .get(tag_id).datetime_modified
            assert our_tag_datetime_modified.isoformat() == datetime_modified
            assert tag_count == new_tag_count
            assert resp['error'] == ('The update request failed because the'
                                    ' submitted data were not new.')
            assert response.content_type == 'application/json'

    #@pytest.mark.skip(reason='because')
    def test_delete(self):
        """Tests that DELETE /tags/id deletes the tag with id=id."""
        with transaction.manager:
            dbsession = self.get_dbsession()

            # Create a tag to delete.
            params = json.dumps({'name': 'name', 'description': 'description'})
            response = self.app.post(RSRCS_PATH, params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            tag_count = dbsession.query(Tag).count()
            tag_id = resp['id']

            # Now delete the tag
            response = self.app.delete(
                RSRC_PATH.format(tag_id), headers=self.json_headers,
                extra_environ=self.extra_environ_admin)
            resp = response.json_body
            new_tag_count = dbsession.query(Tag).count()
            assert new_tag_count == tag_count - 1
            assert resp['id'] == tag_id
            assert response.content_type == 'application/json'

            # Trying to get the deleted tag from the db should return None
            deleted_tag = dbsession.query(Tag).get(tag_id)
            assert deleted_tag is None

            # Delete with an invalid id
            id_ = 9999999999999
            response = self.app.delete(
                RSRC_PATH.format(id_), headers=self.json_headers,
                extra_environ=self.extra_environ_admin, status=404)
            resp = response.json_body
            assert ('There is no tag with id %s' % id_ in
                    resp['error'])
            assert response.content_type == 'application/json'

            # Delete without an id
            response = self.app.delete(
                RSRC_PATH.format(''), status=404, headers=self.json_headers,
                extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['error'] == 'The resource could not be found.'
            assert response.content_type == 'application/json'

            # TODO: uncomment this once forms view implemented.
            """
            # Create a form, tag it, delete the tag and show that the form no
            # longer has the tag.
            tag = Tag()
            tag.name = 'tag'
            form = Form()
            form.transcription = 'test'
            form.tags.append(tag)
            dbsession.add_all([form, tag])
            form_id = form.id
            tag_id = tag.id
            response = self.app.delete(
                RSRC_PATH.format(tag_id), headers=self.json_headers,
                extra_environ=self.extra_environ_admin)
            deleted_tag = dbsession.query(Tag).get(tag_id)
            form = dbsession.query(Form).get(form_id)
            assert response.content_type == 'application/json'
            assert deleted_tag is None
            assert form.tags == []
            """

    @pytest.mark.skip(reason='because')
    def test_show(self):
        """Tests that GET /tags/id returns the tag with id=id or an appropriate
        error.
        """
        # Create a tag to show.
        params = json.dumps({'name': 'name', 'description': 'description'})
        response = self.app.post(url('tags'), params, self.json_headers,
                                 self.extra_environ_admin)
        resp = response.json_body
        tag_id = resp['id']

        # Try to get a tag using an invalid id
        id_ = 100000000000
        response = self.app.get(
            url('tag', id=id_), headers=self.json_headers,
            extra_environ=self.extra_environ_admin, status=404)
        resp = response.json_body
        assert ('There is no tag with id %s' % id_ in
                resp['error'])
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(
            url('tag', id=''), status=404, headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(
            RSRC_PATH.format(tag_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'name'
        assert resp['description'] == 'description'
        assert response.content_type == 'application/json'

    @pytest.mark.skip(reason='because')
    def test_edit(self):
        """Tests that GET /tags/id/edit returns a JSON object of data necessary
        to edit the tag with id=id.

        The JSON object is of the form {'tag': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id
        is valid or invalid/unspecified, respectively.
        """
        # Create a tag to edit.
        params = json.dumps({'name': 'name', 'description': 'description'})
        response = self.app.post(
            url('tags'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        tag_id = resp['id']

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit_tag', id=tag_id), status=401)
        resp = response.json_body
        assert resp['error'] == (
            'Authentication is required to access this resource.')
        assert response.content_type == 'application/json'

        # Invalid id
        id_ = 9876544
        response = self.app.get(
            url('edit_tag', id=id_), headers=self.json_headers,
            extra_environ=self.extra_environ_admin, status=404)
        resp = response.json_body
        assert 'There is no tag with id %s' % id_ in resp['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(
            url('edit_tag', id=''), status=404, headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(
            url('edit_tag', id=tag_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['tag']['name'] == 'name'
        assert resp['data'] == {}
        assert response.content_type == 'application/json'
