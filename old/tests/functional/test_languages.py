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

from old.lib.dbutils import DBUtils
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
from old.models import Language
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder


LOGGER = logging.getLogger(__name__)


url = Language._url(old_name=TestView.old_name)


class TestLanguagesView(TestView):

    def test_index(self):
        """Tests that GET & SEARCH /languages behave correctly.
        NOTE: during testing, the language table contains only 8 records.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        languages = dbsession.query(old_models.Language).all()

        # GET the languages
        response = self.app.get(url('index'), headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == len(languages)
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 2, 'page': 2}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 2
        assert resp['items'][0]['Part2B'] == languages[2].Part2B
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'Language', 'order_by_attribute': 'Ref_Name',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted(languages, key=lambda l: l.Ref_Name, reverse=True)
        assert [l['Id'] for l in resp] == [l.Id for l in result_set]

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'Language', 'order_by_attribute': 'Ref_Name',
                        'order_by_direction': 'desc', 'items_per_page': 1, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert result_set[2].Ref_Name == resp['items'][0]['Ref_Name']
        assert response.content_type == 'application/json'

        # Now test the show action:

        response = self.app.get(url('show', id=languages[4].Id),
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['Ref_Name'] == languages[4].Ref_Name
        assert response.content_type == 'application/json'

        # A nonexistent language Id will return a 404 error
        response = self.app.get(url('show', id=100987),
            headers=self.json_headers, extra_environ=self.extra_environ_view, status=404)
        resp = response.json_body
        assert resp['error'] == 'There is no language with Id 100987'
        assert response.content_type == 'application/json'

        # Test the search action
        add_SEARCH_to_web_test_valid_methods()

        # A search on language transcriptions using POST /languages/search
        json_query = json.dumps({'query': {'filter':
                        ['Language', 'Ref_Name', 'like', '%m%']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_view)
        resp = response.json_body
        result_set = [l for l in languages if 'm' in l.Ref_Name]
        assert resp
        assert set([l['Id'] for l in resp]) == set([l.Id for l in result_set])
        assert response.content_type == 'application/json'

        # A search on language Ref_Name using SEARCH /languages
        json_query = json.dumps({'query': {'filter':
                        ['Language', 'Ref_Name', 'like', '%l%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_view)
        resp = response.json_body
        result_set = [l for l in languages if 'l' in l.Ref_Name]
        assert resp
        assert len(resp) == len(result_set)
        assert set([l['Id'] for l in resp]) == set([l.Id for l in result_set])

        # I'm just going to assume that the order by and pagination functions are
        # working correctly since the implementation is essentially equivalent
        # to that in the index action already tested above.

        # Attempting to call edit/new/create/delete/update on a read-only resource
        # will return a 404 response
        response = self.app.get(
            url('edit', id=2232), extra_environ=self.extra_environ_contrib,
            status=404)
        assert response.json_body['error'] == 'This resource is read-only.'
        assert response.content_type == 'application/json'
        response = self.app.get(
            url('new', id=2232),
            extra_environ=self.extra_environ_contrib, status=404)
        assert response.json_body['error'] == 'This resource is read-only.'
        assert response.content_type == 'application/json'
        response = self.app.post(
            url('create'), extra_environ=self.extra_environ_contrib,
            status=404)
        assert response.json_body['error'] == 'This resource is read-only.'
        assert response.content_type == 'application/json'
        response = self.app.put(
            url('update', id=2232), extra_environ=self.extra_environ_contrib,
            status=404)
        assert response.json_body['error'] == 'This resource is read-only.'
        assert response.content_type == 'application/json'
        response = self.app.delete(
            url('delete', id=2232), extra_environ=self.extra_environ_contrib,
            status=404)
        assert response.json_body['error'] == 'This resource is read-only.'
        assert response.content_type == 'application/json'

    def test_new_search(self):
        """Tests that GET /languages/new_search returns the search parameters for searching the languages resource."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        query_builder = SQLAQueryBuilder(
            dbsession, model_name='Language', settings=self.settings)
        response = self.app.get(
            url('new_search'), headers=self.json_headers,
            extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['search_parameters'] == query_builder.get_search_parameters()
