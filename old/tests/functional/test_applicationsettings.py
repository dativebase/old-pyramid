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
import logging
import json

from old.lib.dbutils import DBUtils
from old.tests import TestView
from old.models import ApplicationSettings, User, Orthography
import old.lib.helpers as h
import old.models.modelbuilders as omb

LOGGER = logging.getLogger(__name__)


url = ApplicationSettings._url(old_name=TestView.old_name)



def add_default_application_settings(dbsession):
    """Add the default application settings to the database."""
    orthography1 = omb.generate_default_orthography1()
    orthography2 = omb.generate_default_orthography2()
    contributor = dbsession.query(User).filter(User.role=='contributor').first()
    application_settings = omb.generate_default_application_settings([orthography1, orthography2], [contributor])
    dbsession.add(application_settings)
    dbsession.commit()
    return application_settings


class TestApplicationsettingsView(TestView):

    def test_index(self):
        """Tests that GET /applicationsettings returns a JSON array of application settings objects."""
        db = DBUtils(self.dbsession, self.settings)
        # Add the default application settings.
        application_settings = add_default_application_settings(self.dbsession)
        response = self.app.get(url('index'),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1
        assert resp[0]['object_language_name'] == db.current_app_set.object_language_name
        assert resp[0]['storage_orthography']['name'] == db.current_app_set.storage_orthography.name
        assert resp[0]['unrestricted_users'][0]['role'] == db.current_app_set.unrestricted_users[0].role

    def test_create(self):
        """Tests that POST /applicationsettings correctly creates a new application settings."""

        db = DBUtils(self.dbsession, self.settings)

        # Add some orthographies.
        orthography1 = omb.generate_default_orthography1()
        orthography2 = omb.generate_default_orthography2()
        self.dbsession.add_all([orthography1, orthography2])
        self.dbsession.flush()
        orthography2_id = orthography2.id
        orthography2_orthography = orthography2.orthography
        self.dbsession.commit()
        self.dbsession.expunge_all()
        self.dbsession.close()

        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': 'test_create object language name',
            'object_language_id': 'tco',
            'metalanguage_name': 'test_create metalanguage name',
            'metalanguage_id': 'tcm',
            'orthographic_validation': 'Warning',
            'narrow_phonetic_validation': 'Error',
            'morpheme_break_is_orthographic': False,
            'morpheme_delimiters': '-,+',
            'punctuation': '!?.,;:-_',
            'grammaticalities': '*,**,***,?,??,???,#,##,###',
            'unrestricted_users': [self.dbsession.query(User).filter(
                User.role=='viewer').first().id],
            'storage_orthography': orthography2_id,
            'input_orthography': orthography2_id,
            'output_orthography': orthography2_id
        })
        params = json.dumps(params)

        response = self.app.post(url('create'), params,
                                 self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['object_language_name'] == 'test_create object language name'
        assert resp['morpheme_break_is_orthographic'] is False
        assert resp['storage_orthography']['orthography'] == orthography2_orthography
        assert resp['unrestricted_users'][0]['first_name'] == 'Viewer'
        assert 'password' not in resp['unrestricted_users'][0]
        assert response.content_type == 'application/json'

        # Attempt the same above creation as a contributor and expect to fail.
        response = self.app.post(url('create'), params,
            self.json_headers, self.extra_environ_contrib, status=403)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['error'] == 'You are not authorized to access this resource.'

    def test_create_invalid(self):
        """Tests that POST /applicationsettings responds with an appropriate error when invalid params are submitted in the request."""
        db = DBUtils(self.dbsession, self.settings)

        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': '!' * 256,   # too long
            'object_language_id': 'too long',    # too long also
            'orthographic_validation': 'No Way!', # not a valid value
            # formencode.validators.StringBoolean accepts 'true', 'false' (with
            # any character in uppercase) as well as any int or float.  'Truish'
            # is unacceptable.
            'morpheme_break_is_orthographic': 'Truish',
            'storage_orthography': 'accept me!'  # integer (orth.id) required
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['errors']['object_language_id'] == \
            'Enter a value not more than 3 characters long'
        assert resp['errors']['object_language_name'] == \
            'Enter a value not more than 255 characters long'
        assert 'Value must be one of: None; Warning; Error' in \
            resp['errors']['orthographic_validation']
        assert "Value should be 'true' or 'false'" in \
            resp['errors']['morpheme_break_is_orthographic']
        assert resp['errors']['storage_orthography'] == \
            'Please enter an integer value'

    def test_new(self):
        """Tests that GET /applicationsettings/new returns an appropriate JSON object for creating a new application settings object.

        The properties of the JSON object are 'languages', 'users' and
        'orthographies' and their values are arrays/lists.
        """

        db = DBUtils(self.dbsession, self.settings)

        # Add some orthographies.
        orthography1 = omb.generate_default_orthography1()
        orthography2 = omb.generate_default_orthography2()
        self.dbsession.add_all([orthography1, orthography2])
        self.dbsession.commit()

        # Get the data currently in the db (see websetup.py for the test data).
        languages = db.get_languages()
        data = {
            'users': db.get_mini_dicts_getter('User')(),
            'orthographies': db.get_mini_dicts_getter('Orthography')()
        }

        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        # GET /applicationsettings/new without params.  Expect a JSON array for
        # every store.
        response = self.app.get(url('new'),
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert (sorted([l['Id'] for l in resp['languages']]) ==
                sorted([l.Id for l in languages]))
        assert resp['users'] == data['users']
        assert resp['orthographies'] == data['orthographies']
        assert response.content_type == 'application/json'

        # GET /applicationsettings/new with params.  Param values are treated as
        # strings, not JSON.  If any params are specified, the default is to
        # return a JSON array corresponding to store for the param.  There are
        # three cases that will result in an empty JSON array being returned:
        # 1. the param is not specified
        # 2. the value of the specified param is an empty string
        # 3. the value of the specified param is an ISO 8601 UTC datetime
        #    string that matches the most recent datetime_modified value of the
        #    store in question.
        params = {
            # Value is empty string: 'languages' will not be in response.
            'languages': '',
            # Value is any string: 'users' will be in response.
            'users': 'anything can go here!',
            # Value is ISO 8601 UTC datetime string that does not match the most
            # recent Orthography.datetime_modified value: 'orthographies' *will*
            # be in the response.
            'orthographies': datetime.datetime.utcnow().isoformat(),
        }
        response = self.app.get(url('new'), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['languages'] == []
        assert resp['users'] == data['users']
        assert resp['orthographies'] == data['orthographies']

    def test_update(self):
        """Tests that PUT /applicationsettings/id correctly updates an existing application settings."""

        db = DBUtils(self.dbsession, self.settings)

        application_settings_count = self.dbsession.query(
            ApplicationSettings).count()
        contributor_id = self.dbsession.query(User).filter(User.role=='contributor').first().id

        # Create an application settings to update.
        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': 'test_update object language name',
            'object_language_id': 'tuo',
            'metalanguage_name': 'test_update metalanguage name',
            'metalanguage_id': 'tum',
            'orthographic_validation': 'None',
            'narrow_phonetic_validation': 'Warning',
            'morpheme_break_is_orthographic': True,
            'morpheme_delimiters': '+',
            'punctuation': '!.;:',
            'grammaticalities': '*,**,?,??,#,##',
            'unrestricted_users': [contributor_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        id = int(resp['id'])
        new_application_settings_count = self.dbsession.query(ApplicationSettings).count()
        assert resp['object_language_name'] == 'test_update object language name'
        assert resp['unrestricted_users'][0]['role'] == 'contributor'
        assert new_application_settings_count == application_settings_count + 1

        # Update the application settings we just created but expect to fail
        # because the unrestricted users ids are invalid.
        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': 'Updated!',
            'unrestricted_users': [2000, 5000],
            'morpheme_delimiters': '-,='
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=id), params,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        application_settings_count = new_application_settings_count
        new_application_settings_count = self.dbsession.query(ApplicationSettings).count()
        assert resp['errors']['unrestricted_users'] == [u"There is no user with id 2000.", "There is no user with id 5000."]
        assert new_application_settings_count == application_settings_count
        assert response.content_type == 'application/json'

        # Update the application settings.
        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': 'Updated!',
            'unrestricted_users': [contributor_id],
            'morpheme_delimiters': '-,='
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=id), params,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        application_settings_count = new_application_settings_count
        new_application_settings_count = self.dbsession.query(ApplicationSettings).count()
        assert resp['object_language_name'] == 'Updated!'
        assert new_application_settings_count == application_settings_count
        assert response.content_type == 'application/json'

        # Attempt an update with no new data -- expect a 400 status code where
        # the response body is a JSON object with an appropriate 'error'
        # attribute.
        response = self.app.put(url('update', id=id), params,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert 'the submitted data were not new' in resp['error']

        # Unauthorized update attempt as contributor
        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': 'Updated by a contrib!',
            'unrestricted_users': [contributor_id],
            'morpheme_delimiters': '-,='
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=id), params,
                        self.json_headers, self.extra_environ_contrib, status=403)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['error'] == 'You are not authorized to access this resource.'

    def test_delete(self):
        """Tests that DELETE /applicationsettings/id deletes the application settings with id=id and returns a JSON representation.

        If the id is invalid or unspecified, then JSON null or a 404 status code
        are returned, respectively.
        """

        db = DBUtils(self.dbsession, self.settings)

        # Count the original number of application settings.
        application_settings_count = self.dbsession.query(
            ApplicationSettings).count()

        # Add an orthography.
        orthography1 = omb.generate_default_orthography1()
        self.dbsession.add(orthography1)
        self.dbsession.commit()
        orthography1 = db.get_orthographies()[0]
        orthography1_id = orthography1.id
        orthography1 = self.dbsession.query(Orthography).get(orthography1_id)

        # First create an application settings to delete.
        params = self.application_settings_create_params.copy()
        params.update({
            'object_language_name': 'test_delete object language name',
            'object_language_id': 'tdo',
            'metalanguage_name': 'test_delete metalanguage name',
            'metalanguage_id': 'tdm',
            'storage_orthography': orthography1_id,
            'morpheme_delimiters': '-'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_application_settings_count = self.dbsession.query(
            ApplicationSettings).count()
        assert resp['object_language_name'] == 'test_delete object language name'
        assert new_application_settings_count == application_settings_count + 1

        # Delete the application settings we just created
        response = self.app.delete(
            url('delete', id=resp['id']),
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        new_application_settings_count = self.dbsession.query(ApplicationSettings).count()
        assert new_application_settings_count == application_settings_count
        assert response.content_type == 'application/json'
        # The deleted application settings will be returned to us, so the
        # assertions from above should still hold true.
        assert resp['object_language_name'] == 'test_delete object language name'

        # Trying to get the deleted form from the db should return None.
        deleted_application_settings = self.dbsession.query(
            ApplicationSettings).get(resp['id'])
        assert deleted_application_settings is None

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
                            extra_environ=self.extra_environ_admin, status=404)
        assert response.json_body['error'] == \
            'There is no application settings with id %s' % id
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
                                    extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Unauthorized delete attempt as contributor
        response = self.app.post(url('create'), params,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        application_settings_count = new_application_settings_count
        new_application_settings_count = self.dbsession.query(ApplicationSettings).count()
        assert resp['object_language_name'] == 'test_delete object language name'
        assert new_application_settings_count == application_settings_count + 1
        response = self.app.delete(url('delete', id=resp['id']),
            headers=self.json_headers, extra_environ=self.extra_environ_contrib, status=403)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['error'] == 'You are not authorized to access this resource.'

    def test_show(self):
        """Tests that GET /applicationsettings/id returns the JSON application settings object with id=id
        or a 404 status code depending on whether the id is valid or
        invalid/unspecified, respectively.
        """

        db = DBUtils(self.dbsession, self.settings)

        # Invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
                            extra_environ=self.extra_environ_admin, status=404)
        assert response.json_body['error'] == 'There is no application settings with id %s' % id
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
                                extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Add the default application settings.
        application_settings = add_default_application_settings(self.dbsession)
        application_settings = db.current_app_set
        application_settings_id = application_settings.id
        application_settings_storage_orthography_name = \
            application_settings.storage_orthography.name

        # Valid id
        response = self.app.get(url('show', id=application_settings_id),
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert type(resp) == type({})
        assert resp['object_language_name'] == \
            application_settings.object_language_name
        assert resp['storage_orthography']['name'] == \
            application_settings_storage_orthography_name

    def test_edit(self):
        """Tests that GET /applicationsettings/id/edit returns a JSON object for editing an existing application settings.

        The JSON object is of the form {application_settings: {...}, data: {...}}
        or {'error': '...'} (and a 404 status code) depending on whether the id
        is valid or invalid/unspecified, respectively.
        """

        db = DBUtils(self.dbsession, self.settings)

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(
            url('edit', id=100000000000), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id: expect 404 Not Found
        id = 100000000000
        response = self.app.get(url('edit', id=id),
                            extra_environ=self.extra_environ_admin, status=404)
        assert response.json_body['error'] == \
            'There is no application settings with id %s' % id
        assert response.content_type == 'application/json'

        # No id: expect 404 Not Found
        response = self.app.get(url('edit', id=''),
            status=404, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Add the default application settings.
        application_settings = add_default_application_settings(self.dbsession)
        application_settings = db.current_app_set
        application_settings_id = application_settings.id

        # Valid id
        response = self.app.get(url('edit', id=application_settings_id),
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert type(resp) == type({})
        assert resp['application_settings']['object_language_name'] == \
            application_settings.object_language_name

        # Valid id with GET params.  Param values are treated as strings, not
        # JSON.  If any params are specified, the default is to return a JSON
        # array corresponding to store for the param.  There are three cases
        # that will result in an empty JSON array being returned:
        # 1. the param is not specified
        # 2. the value of the specified param is an empty string
        # 3. the value of the specified param is an ISO 8601 UTC datetime
        #    string that matches the most recent datetime_modified value of the
        #    store in question.

        # Get the data currently in the db (see websetup.py for the test data).
        languages = db.get_languages()
        data = {
            'users': db.get_mini_dicts_getter('User')(),
            'orthographies': db.get_mini_dicts_getter('Orthography')()
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        params = {
            # Value is a non-empty string: 'users' will be in response.
            'users': 'give me some users!',
            # Value is empty string: 'languages' will not be in response.
            'languages': '',
            # Value is ISO 8601 UTC datetime string that does not match the most
            # recent Orthography.datetime_modified value: 'orthographies' *will*
            # be in the response.
            'orthographies': datetime.datetime.utcnow().isoformat(),
        }
        response = self.app.get(url('edit', id=application_settings_id), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['data']['users'] == data['users']
        assert resp['data']['languages'] == []
        assert resp['data']['orthographies'] == data['orthographies']

        # Invalid id with GET params.  It should still return a 404 Not Found.
        params = {
            # If id were valid, this would cause a users array to be returned also.
            'users': 'True',
        }
        response = self.app.get(
            url('edit', id=id), params,
            extra_environ=self.extra_environ_admin, status=404)
        assert response.json_body['error'] == \
            'There is no application settings with id %s' % id
