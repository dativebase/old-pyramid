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
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
from old.models import Page
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.models import Page


LOGGER = logging.getLogger(__name__)


url = Page._url(old_name=TestView.old_name)


################################################################################
# Functions for creating & retrieving test data
################################################################################

class TestPagesView(TestView):
    
    md_contents = '\n'.join([
        'My Page',
        '=======',
        '',
        'Research Interests',
        '---------------------',
        '',
        '* Item 1',
        '* Item 2',
        ''
    ])

    def test_index(self):
        """Tests that GET /pages returns an array of all pages and that order_by and pagination parameters work correctly."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 pages.
        def create_page_from_index(index):
            page = old_models.Page()
            page.name = 'page%d' % index
            page.markup_language = 'Markdown'
            page.content = self.md_contents
            return page
        pages = [create_page_from_index(i) for i in range(1, 101)]
        dbsession.add_all(pages)
        dbsession.commit()
        pages = db.get_pages(True)
        pages_count = len(pages)

        # Test that GET /pages gives us all of the pages.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == pages_count
        assert resp[0]['name'] == 'page1'
        assert resp[0]['id'] == pages[0].id
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['name'] == pages[46].name
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'Page', 'order_by_attribute': 'name',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted([p.name for p in pages], reverse=True)
        assert result_set == [p['name'] for p in resp]

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'Page', 'order_by_attribute': 'name',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert result_set[46] == resp['items'][0]['name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'Page', 'order_by_attribute': 'name',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'Pageist', 'order_by_attribute': 'nominal',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == pages[0].id

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
        assert response.content_type == 'application/json'

    def test_create(self):
        """Tests that POST /pages creates a new page
        or returns an appropriate error if the input is invalid.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        original_page_count = dbsession.query(Page).count()

        # Create a valid one
        params = self.page_create_params.copy()
        params.update({
            'name': 'page',
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_page_count = dbsession.query(Page).count()
        assert new_page_count == original_page_count + 1
        assert resp['name'] == 'page'
        assert resp['content'] == self.md_contents
        assert resp['html'] == h.get_HTML_from_contents(self.md_contents, 'Markdown')
        assert response.content_type == 'application/json'

        # Invalid because name is empty and markup language is invalid
        params = self.page_create_params.copy()
        params.update({
            'name': '',
            'markup_language': 'markdownable',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'Please enter a value'
        assert resp['errors']['markup_language'] == \
            "Value must be one of: reStructuredText; Markdown (not 'markdownable')"
        assert response.content_type == 'application/json'

        # Invalid because name is too long
        params = self.page_create_params.copy()
        params.update({
            'name': 'name' * 200,
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'Enter a value not more than 255 characters long'
        assert response.content_type == 'application/json'

    def test_new(self):
        """Tests that GET /pages/new returns the list of accepted markup languages."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        response = self.app.get(url('new'), headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp == {'markup_languages': list(oldc.MARKUP_LANGUAGES)}
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /pages/id updates the page with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a page to update.
        params = self.page_create_params.copy()
        params.update({
            'name': 'page',
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        page_count = dbsession.query(Page).count()
        page_id = resp['id']
        original_datetime_modified = resp['datetime_modified']

        # Update the page
        sleep(1)    # sleep for a second to ensure that MySQL registers a different datetime_modified for the update
        params = self.page_create_params.copy()
        params.update({
            'name': 'Awesome Page',
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=page_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        datetime_modified = resp['datetime_modified']
        new_page_count = dbsession.query(Page).count()
        assert page_count == new_page_count
        assert datetime_modified != original_datetime_modified
        assert resp['name'] == 'Awesome Page'
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        response = self.app.put(url('update', id=page_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        page_count = new_page_count
        new_page_count = dbsession.query(Page).count()
        our_page_datetime_modified = dbsession.query(Page).get(page_id).datetime_modified
        assert our_page_datetime_modified.isoformat() == datetime_modified
        assert page_count == new_page_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /pages/id deletes the page with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a page to delete.
        params = self.page_create_params.copy()
        params.update({
            'name': 'page',
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        page_count = dbsession.query(Page).count()
        page_id = resp['id']

        # Now delete the page
        response = self.app.delete(url('delete', id=page_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        new_page_count = dbsession.query(Page).count()
        assert new_page_count == page_count - 1
        assert resp['id'] == page_id
        assert response.content_type == 'application/json'

        # Trying to get the deleted page from the db should return None
        deleted_page = dbsession.query(Page).get(page_id)
        assert deleted_page is None
        assert response.content_type == 'application/json'

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no page with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

    def test_show(self):
        """Tests that GET /pages/id returns the page with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a page to show.
        params = self.page_create_params.copy()
        params.update({
            'name': 'page',
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        page_id = resp['id']

        # Try to get a page using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no page with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('show', id=page_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'page'
        assert resp['content'] == self.md_contents
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /pages/id/edit returns a JSON object of data necessary to edit the page with id=id.

        The JSON object is of the form {'page': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a page to edit.
        params = self.page_create_params.copy()
        params.update({
            'name': 'page',
            'markup_language': 'Markdown',
            'content': self.md_contents
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        page_id = resp['id']

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=page_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin, status=404)
        assert 'There is no page with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('edit', id=page_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['page']['name'] == 'page'
        assert resp['data'] == {'markup_languages': list(oldc.MARKUP_LANGUAGES)}
        assert response.content_type == 'application/json'
