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

import re
import datetime
import logging
import json

from old.lib.dbutils import DBUtils
from time import sleep
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.models import FormSearch
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder

LOGGER = logging.getLogger(__name__)


url = FormSearch._url()




################################################################################
# Functions for creating & retrieving test data
################################################################################

today_timestamp = datetime.datetime.now()
day_delta = datetime.timedelta(1)
yesterday_timestamp = today_timestamp - day_delta

mysql_engine = old_models.Model.__table_args__.get('mysql_engine')

def _create_test_form_searches(db, dbsession, n=100):
    """Create n form searches with various properties.  A testing ground for searches!
    """
    users = db.get_users()
    contributor = [u for u in users if u.role == 'contributor'][0]

    for i in range(1, n + 1):
        fs = old_models.FormSearch()

        fs.enterer_id = contributor.id
        fs.search = str(json.dumps(
                {'query': {'filter': ['Form', 'transcription', 'regex', '%d' % i]}}))
        if i % 2 == 0:
            fs.name = 'Form Search %d' % i
        else:
            fs.name = 'form search %d' % i

        if i > 50:
            fs.description = 'I really like this search and my favourite number is %d' % i

        if i > 20:
            fs.datetime_modified = today_timestamp
        else:
            fs.datetime_modified = yesterday_timestamp

        dbsession.add(fs)
    dbsession.commit()

def _create_test_data(db, dbsession, n=100):
    _create_test_form_searches(db, dbsession, n)

class TestFormsearchesView(TestView):

    def test_index(self):
        """Tests that GET /formsearches returns an array of all form searches and that order_by and pagination parameters work correctly."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 form searches.
        def create_form_search_from_index(index):
            form_search = old_models.FormSearch()
            form_search.name = 'form_search%d' % index
            form_search.description = 'description %d' % index
            form_search.search = str(json.dumps(
                {'query': {'filter': ['Form', 'transcription', 'regex', '%d' % index]}}))
            return form_search
        form_searches = [create_form_search_from_index(i) for i in range(1, 101)]
        dbsession.add_all(form_searches)
        dbsession.commit()
        form_searches = db.get_form_searches(True)
        form_searches_count = len(form_searches)

        # Test that GET /formsearches gives us all of the form searches.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == form_searches_count
        assert resp[0]['name'] == 'form_search1'
        assert resp[0]['id'] == form_searches[0].id
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['name'] == form_searches[46].name

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'FormSearch', 'order_by_attribute': 'name',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted([t.name for t in form_searches], reverse=True)
        assert result_set == [t['name'] for t in resp]

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'FormSearch', 'order_by_attribute': 'name',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert result_set[46] == resp['items'][0]['name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'FormSearch', 'order_by_attribute': 'name',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'FormSearchist', 'order_by_attribute': 'nominal',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == form_searches[0].id

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

    def test_create(self):
        """Tests that POST /formsearches creates a new form_search
        or returns an appropriate error if the input is invalid.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        original_form_search_count = dbsession.query(FormSearch).count()
        query = {'filter': ['Form', 'transcription', 'regex', '[a-g]{3,}']}

        # Create a valid one
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_form_search_count = dbsession.query(FormSearch).count()
        assert new_form_search_count == original_form_search_count + 1
        assert resp['name'] == 'form search'
        assert resp['description'] == "This one's worth saving!"
        assert resp['enterer']['first_name'] == 'Admin'
        assert resp['search'] == query
        assert response.content_type == 'application/json'

        # Invalid because name is not unique
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search',
            'description': 'Another one worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'The submitted value for FormSearch.name is not unique.'
        assert response.content_type == 'application/json'

        # Invalid because name is empty
        params = self.form_search_create_params.copy()
        params.update({
            'name': '',
            'description': 'Another one worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'Please enter a value'

        # Invalid because name is too long
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search' * 300,
            'description': 'Another one worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['name'] == 'Enter a value not more than 255 characters long'

        # Invalid because search is invalid
        query = {'filter': ['Form', 'bar', 'like', '%m%']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'invalid query',
            'description': 'Another one worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['search'] == 'The submitted query was invalid'

        # Another invalid search
        query = {'filter': ['Form', 'files', 'like', '%m%']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'invalid query again',
            'description': 'Yet another one worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['search'] == 'The submitted query was invalid'

    def test_new(self):
        """Tests that GET /formsearches/new returns the data necessary to create a new form search."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        response = self.app.get(url('new'), headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert 'attributes' in resp['search_parameters']
        assert 'relations' in resp['search_parameters']
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /formsearches/id updates the form search with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a form search to update.
        query = {'filter': ['Form', 'transcription', 'regex', '[a-g]{3,}']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        form_search_count = dbsession.query(FormSearch).count()
        form_search_id = resp['id']
        original_datetime_modified = resp['datetime_modified']
        assert resp['name'] == 'form search'
        assert resp['description'] == "This one's worth saving!"
        assert resp['search'] == query

        # Update the form search
        sleep(1)    # sleep for a second to ensure that MySQL registers a different datetime_modified for the update
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search for keeping',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=form_search_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        datetime_modified = resp['datetime_modified']
        new_form_search_count = dbsession.query(FormSearch).count()
        assert form_search_count == new_form_search_count
        assert datetime_modified != original_datetime_modified
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        response = self.app.put(url('update', id=form_search_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        form_search_count = new_form_search_count
        new_form_search_count = dbsession.query(FormSearch).count()
        our_form_search_datetime_modified = dbsession.query(FormSearch).get(form_search_id).datetime_modified
        assert our_form_search_datetime_modified.isoformat() == datetime_modified
        assert form_search_count == new_form_search_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /formsearches/id deletes the form search with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a form search to delete.
        query = {'filter': ['Form', 'transcription', 'regex', '[a-g]{3,}']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        form_search_count = dbsession.query(FormSearch).count()
        form_search_id = resp['id']
        assert resp['name'] == 'form search'
        assert resp['description'] == "This one's worth saving!"
        assert resp['search'] == query

        # Now delete the form_search
        response = self.app.delete(url('delete', id=form_search_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        new_form_search_count = dbsession.query(FormSearch).count()
        assert new_form_search_count == form_search_count - 1
        assert resp['id'] == form_search_id
        assert response.content_type == 'application/json'

        # Trying to get the deleted form_search from the db should return None
        deleted_form_search = dbsession.query(FormSearch).get(form_search_id)
        assert deleted_form_search is None

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no form search with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'

    def test_show(self):
        """Tests that GET /formsearches/id returns the formsearch with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a form search to show.
        query = {'filter': ['Form', 'transcription', 'regex', '[a-g]{3,}']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        form_search_id = resp['id']
        assert resp['name'] == 'form search'
        assert resp['description'] == "This one's worth saving!"
        assert resp['search'] == query

        # Try to get a form search using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin, status=404)
        resp = response.json_body
        assert 'There is no form search with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'

        # Valid id
        response = self.app.get(url('show', id=form_search_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'form search'
        assert resp['description'] == "This one's worth saving!"
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /formsearches/id/edit returns a JSON object of data necessary to edit the form search with id=id.

        The JSON object is of the form {'form_search': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a form search to edit.
        query = {'filter': ['Form', 'transcription', 'regex', '[a-g]{3,}']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'form search',
            'description': 'This one\'s worth saving!',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        form_search_id = resp['id']
        assert resp['name'] == 'form search'
        assert resp['description'] == "This one's worth saving!"
        assert resp['search'] == query

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=form_search_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin, status=404)
        assert 'There is no form search with id {}'.format(id) in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'

        # Valid id
        response = self.app.get(url('edit', id=form_search_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['form_search']['name'] == 'form search'
        assert 'attributes' in resp['data']['search_parameters']
        assert 'relations' in resp['data']['search_parameters']
        assert response.content_type == 'application/json'

    def fix_formsearch(self, formsearch):
        for key, val in formsearch.items():
            if isinstance(val, (datetime.datetime, datetime.date)):
                formsearch[key] = val.isoformat()
        return formsearch

    def test_search(self):
        """Tests that SEARCH /formsearches (a.k.a. POST /formsearches/search) correctly returns an array of formsearches based on search criteria."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        # Create some form_searches (and other models) to search and add SEARCH to the list of allowable methods
        _create_test_data(db, dbsession, 100)
        add_SEARCH_to_web_test_valid_methods()
        RDBMSName = h.get_RDBMS_name(self.settings)
        form_searches = json.loads(json.dumps(
            [self.fix_formsearch(fs.get_dict()) for fs in
                db.get_form_searches(True)]))

        # Searching where values may be NULL
        json_query = json.dumps({'query': {'filter': ['FormSearch', 'search', 'like', '%2%']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = [fs for fs in form_searches if '2' in
                        json.dumps(fs['search'])]
        assert resp
        assert len(resp) == len(result_set)
        assert set([s['id'] for s in resp]) == set([s['id'] for s in result_set])
        assert response.content_type == 'application/json'

        # A fairly complex search
        json_query = json.dumps({'query': {'filter': [
            'and', [
                ['FormSearch', 'name', 'regex', '[13456]'],
                ['not', ['FormSearch', 'name', 'like', '%F%']],
                ['or', [
                    ['FormSearch', 'search', 'regex', '[1456]'],
                    ['FormSearch', 'datetime_modified', '>', yesterday_timestamp.isoformat()]]]]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        mysql_engine = old_models.Model.__table_args__.get('mysql_engine')
        if RDBMSName == 'mysql' and mysql_engine == 'InnoDB':
            _yesterday_timestamp = h.round_datetime(yesterday_timestamp)
        else:
            _yesterday_timestamp = yesterday_timestamp
        result_set = [fs for fs in form_searches if
            re.search('[13456]', fs['name']) and not 'F' in fs['name'] and
            (re.search('[1456]', json.dumps(fs['search'])) or fs['datetime_modified'] > _yesterday_timestamp.isoformat())]
        assert resp
        assert len(resp) == len(result_set)
        assert set([s['id'] for s in resp]) == set([s['id'] for s in result_set])

        # A basic search with a paginator provided.
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'search', 'like', '%3%']},
            'paginator': {'page': 2, 'items_per_page': 5}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        result_set = [fs for fs in form_searches if json.dumps(fs['search']) and '3' in json.dumps(fs['search'])]
        assert resp['paginator']['count'] == len(result_set)
        assert len(resp['items']) == 5
        assert resp['items'][0]['id'] == result_set[5]['id']
        assert resp['items'][-1]['id'] == result_set[9]['id']

        # An invalid paginator (here 'page' is less than 1) will result in formencode.Invalid
        # being raised resulting in a response with a 400 status code and a JSON error msg.
        json_query = json.dumps({
            'query': {
                'filter': ['FormSearch', 'search', 'like', '%3%']},
            'paginator': {'page': 0, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'
        assert response.content_type == 'application/json'

        # Some "invalid" paginators will silently fail.  For example, if there is
        # no 'pages' key, then SEARCH /formsearches will just assume there is no paginator
        # and all of the results will be returned.
        json_query = json.dumps({
            'query': {
                'filter': ['FormSearch', 'search', 'like', '%3%']},
            'paginator': {'pages': 1, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len([fs for fs in form_searches if json.dumps(fs['search']) and '3' in json.dumps(fs['search'])])

        # Adding a 'count' key to the paginator object in the request will spare
        # the server from running query.count().  Note that the server will not
        # attempt to verify the count (since that would defeat the purpose) but
        # will simply pass it back.  The server trusts that the client is passing
        # in a factual count.  Here we pass in an inaccurate count for demonstration.
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'search', 'like', '%3%']},
            'paginator': {'page': 2, 'items_per_page': 4, 'count': 750}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['paginator']['count'] == 750
        assert len(resp['items']) == 4
        assert resp['items'][0]['id'] == result_set[4]['id']
        assert resp['items'][-1]['id'] == result_set[7]['id']

        # Test order by: order by name descending
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'search', 'regex', '.'],
                'order_by': ['FormSearch', 'name', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = sorted(form_searches, key=lambda fs: fs['name'].lower(), reverse=True)
        assert len(resp) == 100
        rs_names = [fs['name'] for fs in result_set]
        r_names = [fs['name'] for fs in resp]
        assert rs_names == r_names
        assert resp[0]['name'] == 'form search 99'
        assert resp[-1]['name'] == 'form search 1'

        # order by with missing direction defaults to 'asc'
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'search', 'regex', '.'],
                'order_by': ['FormSearch', 'name']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[0]['name'] == 'form search 1'
        assert resp[-1]['name'] == 'form search 99'
        assert response.content_type == 'application/json'

        # order by with unknown direction defaults to 'asc'
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'search', 'regex', '.'],
                'order_by': ['FormSearch', 'name', 'descending']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[0]['name'] == 'form search 1'
        assert resp[-1]['name'] == 'form search 99'

        # syntactically malformed order by
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'search', 'regex', '.'],
                'order_by': ['FormSearch']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'
        assert response.content_type == 'application/json'

        # searches with lexically malformed order bys
        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'name', 'regex', '.'],
                'order_by': ['FormSearch', 'foo', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['FormSearch.foo'] == 'Searching on FormSearch.foo is not permitted'
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'

        json_query = json.dumps({'query': {
                'filter': ['FormSearch', 'name', 'regex', '.'],
                'order_by': ['Foo', 'id', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Foo'] == 'Searching the FormSearch model by joining on the Foo model is not possible'
        assert resp['errors']['Foo.id'] == 'Searching on Foo.id is not permitted'
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'

    def test_new_search(self):
        """Tests that GET /formsearches/new_search returns the search parameters for searching the form searches resource."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        query_builder = SQLAQueryBuilder(dbsession, 'FormSearch', settings=self.settings)
        response = self.app.get('/formsearches/new_search', headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['search_parameters'] == query_builder.get_search_parameters()
