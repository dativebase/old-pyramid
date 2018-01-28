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
import os
import json

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
from time import sleep
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
import old.models as old_models
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.models import User

LOGGER = logging.getLogger(__name__)


url = User._url(old_name=TestView.old_name)



class TestUsersView(TestView):

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_destroy=['user'])

    def test_index(self):
        """Tests that GET /users returns an array of all users and that order_by and pagination parameters work correctly."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 users.
        def create_user_from_index(index):
            user = old_models.User()
            user.username = 'user_%d' % index
            user.password = 'Aaaaaa_%d' % index
            user.first_name = 'John%d' % index
            user.last_name = 'Doe'
            user.email = 'john.doe@gmail.com'
            user.role = 'viewer'
            return user
        users = [create_user_from_index(i) for i in range(1, 101)]
        dbsession.add_all(users)
        dbsession.commit()
        users = db.get_users(True)
        users_count = len(users)

        # Test that GET /users gives us all of the users.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == users_count
        assert resp[3]['first_name'] == 'John1'
        assert resp[0]['id'] == users[0].id
        assert 'password' not in resp[3]
        # Previously asserted username not in user dicts returned. Why?
        assert 'username' in resp[3]
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['first_name'] == users[46].first_name
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'User', 'order_by_attribute': 'username',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        result_set = sorted(users, key=lambda u: u.username, reverse=True)
        assert [u.id for u in result_set] == [u['id'] for u in resp]
        assert response.content_type == 'application/json'

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'User', 'order_by_attribute': 'username',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert result_set[46].first_name == resp['items'][0]['first_name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'User', 'order_by_attribute': 'username',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'Userist', 'order_by_attribute': 'nominal',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == users[0].id

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
        """Tests that POST /users creates a new user
        or returns an appropriate error if the input is invalid.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Attempt to create a user as a contributor and expect to fail
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_contrib, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Create a valid one
        original_researchers_directory = os.listdir(self.users_path)
        original_user_count = dbsession.query(User).count()
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        researchers_directory_m_time = os.stat(self.users_path).st_mtime
        assert new_user_count == original_user_count + 1
        assert resp['username'] == 'johndoe'
        assert resp['email'] == 'john.doe@gmail.com'
        assert 'password' not in resp
        assert new_researchers_directory != original_researchers_directory
        assert 'johndoe' in new_researchers_directory
        assert response.content_type == 'application/json'

        # Invalid because username is not unique
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Zzzzzz_1',
            'password_confirm': 'Zzzzzz_1',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        researchers_directory = new_researchers_directory
        new_researchers_directory = os.listdir(self.users_path)
        new_researchers_directory_m_time = os.stat(self.users_path).st_mtime
        assert researchers_directory == new_researchers_directory
        assert researchers_directory_m_time == new_researchers_directory_m_time
        assert new_user_count == user_count
        assert resp['errors'] == 'The username johndoe is already taken.'
        assert response.content_type == 'application/json'

        # Invalid because username contains illicit characters
        params = self.user_create_params.copy()
        params.update({
            'username': 'johannes dough',
            'password': 'Zzzzzz_1',
            'password_confirm': 'Zzzzzz_1',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == 'The username johannes dough is invalid; only letters of the English alphabet, numbers and the underscore are permitted.'
        assert response.content_type == 'application/json'

        # Invalid because username must be a non-empty string
        params = self.user_create_params.copy()
        params.update({
            'username': '',
            'password': 'Zzzzzz_1',
            'password_confirm': 'Zzzzzz_1',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == 'A username is required when creating a new user.'
        assert response.content_type == 'application/json'

        params = self.user_create_params.copy()
        params.update({
            'username': None,
            'password': 'Zzzzzz_1',
            'password_confirm': 'Zzzzzz_1',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == 'A username is required when creating a new user.'
        assert response.content_type == 'application/json'

        # Invalid because username and password are both too long.  Notice how the space in the
        # username does not raise an error because the chained validators are not
        # called
        params = self.user_create_params.copy()
        params.update({
            'username': 'johannes dough' * 200,
            'password': 'Zzzzzz_1' * 200,
            'password_confirm': 'Zzzzzz_1' * 200,
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors']['username'] == 'Enter a value not more than 255 characters long'
        assert resp['errors']['password'] == 'Enter a value not more than 255 characters long'
        assert response.content_type == 'application/json'

        # Invalid because password and password_confirm do not match.
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Zzzzzz_1',
            'password_confirm': 'Zzzzzzx_1',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == 'The password and password_confirm values do not match.'
        assert response.content_type == 'application/json'

        # Invalid because no password was provided.
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': '',
            'password_confirm': '',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == 'A password is required when creating a new user.'
        assert response.content_type == 'application/json'

        # Invalid because no password was provided.
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': None,
            'password_confirm': None,
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == 'A password is required when creating a new user.'
        assert response.content_type == 'application/json'

        # Invalid because the password is too short
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'aA_9',
            'password_confirm': 'aA_9',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == ' '.join([
            'The submitted password is invalid; valid passwords contain at least 8 characters',
            'and either contain at least one character that is not in the printable ASCII range',
            'or else contain at least one symbol, one digit, one uppercase letter and one lowercase letter.'])
        assert response.content_type == 'application/json'

        # Invalid because the password does not contain an uppercase printable ASCII character
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'abcdefg_9',
            'password_confirm': 'abcdefg_9',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == ' '.join([
            'The submitted password is invalid; valid passwords contain at least 8 characters',
            'and either contain at least one character that is not in the printable ASCII range',
            'or else contain at least one symbol, one digit, one uppercase letter and one lowercase letter.'])

        # Invalid because the password does not contain a lowercase printable ASCII character
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'ABCDEFG_9',
            'password_confirm': 'ABCDEFG_9',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == ' '.join([
            'The submitted password is invalid; valid passwords contain at least 8 characters',
            'and either contain at least one character that is not in the printable ASCII range',
            'or else contain at least one symbol, one digit, one uppercase letter and one lowercase letter.'])

        # Invalid because the password does not contain a symbol from the printable ASCII character range
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'abcdefgH9',
            'password_confirm': 'abcdefgH9',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == ' '.join([
            'The submitted password is invalid; valid passwords contain at least 8 characters',
            'and either contain at least one character that is not in the printable ASCII range',
            'or else contain at least one symbol, one digit, one uppercase letter and one lowercase letter.'])
        assert response.content_type == 'application/json'

        # Invalid because the password does not contain a digit
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'abcdefgH.',
            'password_confirm': 'abcdefgH.',
            'first_name': 'Johannes',
            'last_name': 'Dough',
            'email': 'johannes.dough@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors'] == ' '.join([
            'The submitted password is invalid; valid passwords contain at least 8 characters',
            'and either contain at least one character that is not in the printable ASCII range',
            'or else contain at least one symbol, one digit, one uppercase letter and one lowercase letter.'])
        assert response.content_type == 'application/json'

        # Valid user: the password contains a unicode character
        researchers_directory = os.listdir(self.users_path)
        researchers_directory_m_time = os.stat(self.users_path).st_mtime
        sleep(1)
        params = self.user_create_params.copy()
        params.update({
            'username': 'aadams',
            'password': 'abcde\u0301fgh',
            'password_confirm': 'abcde\u0301fgh',
            'first_name': 'Alexander',
            'last_name': 'Adams',
            'email': 'aadams@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        new_researchers_directory_m_time = os.stat(self.users_path).st_mtime
        assert 'aadams' not in researchers_directory
        assert 'aadams' in new_researchers_directory
        assert researchers_directory_m_time != new_researchers_directory_m_time
        assert new_user_count == user_count + 1
        assert resp['first_name'] == 'Alexander'
        assert 'password' not in resp
        assert response.content_type == 'application/json'

        # Invalid user: first_name is empty, email is invalid, affilication is too
        # long, role is unrecognized, input_orthography is nonexistent, markup_language is unrecognized.
        params = self.user_create_params.copy()
        params.update({
            'username': 'xyh',
            'password': 'abcde\u0301fgh',
            'password_confirm': 'abcde\u0301fgh',
            'first_name': '',
            'last_name': 'Yetzer-Hara',
            'affiliation': 'here, there, everywhere, ' * 200,
            'email': 'paradoxofevil@gmail',
            'role': 'master',
            'markup_language': 'markdownandupanddown',
            'page_content': 'My OLD Page\n===============\n\nWhat a great linguistic fieldwork application!\n\n',
            'input_orthography': 1234
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count
        assert resp['errors']['first_name'] == 'Please enter a value'
        assert resp['errors']['email'] == 'The domain portion of the email address is invalid (the portion after the @: gmail)'
        assert resp['errors']['affiliation'] == 'Enter a value not more than 255 characters long'
        assert resp['errors']['role'] == "Value must be one of: viewer; contributor; administrator (not 'master')"
        assert resp['errors']['input_orthography'] == 'There is no orthography with id 1234.'
        assert resp['errors']['markup_language'] == "Value must be one of: reStructuredText; Markdown (not 'markdownandupanddown')"
        assert response.content_type == 'application/json'

        # Valid user: all fields have valid values
        orthography1 = omb.generate_default_orthography1()
        orthography2 = omb.generate_default_orthography2()
        dbsession.add_all([orthography1, orthography2])
        dbsession.flush()
        orthography1_id = orthography1.id
        orthography2_id = orthography2.id
        dbsession.commit()
        params = self.user_create_params.copy()
        params.update({
            'username': 'alyoshas',
            'password': 'xY9.Bfx_J Jre\u0301',
            'password_confirm': 'xY9.Bfx_J Jre\u0301',
            'first_name': 'Alexander',
            'last_name': 'Solzhenitsyn',
            'email': 'amanaplanacanalpanama@gmail.com',
            'affiliation': 'Moscow State University',
            'role': 'contributor',
            'markup_language': 'Markdown',
            'page_content': 'My OLD Page\n===============\n\nWhat a great linguistic fieldwork application!\n\n',
            'input_orthography': orthography1_id,
            'output_orthography': orthography2_id
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert new_user_count == user_count + 1
        assert resp['username'] == 'alyoshas'
        assert resp['first_name'] == 'Alexander'
        assert resp['last_name'] == 'Solzhenitsyn'
        assert resp['email'] == 'amanaplanacanalpanama@gmail.com'
        assert resp['affiliation'] == 'Moscow State University'
        assert resp['role'] == 'contributor'
        assert resp['markup_language'] == 'Markdown'
        assert resp['page_content'] == 'My OLD Page\n===============\n\nWhat a great linguistic fieldwork application!\n\n'
        assert resp['html'] == h.get_HTML_from_contents(resp['page_content'], 'Markdown')
        assert resp['input_orthography']['id'] == orthography1_id
        assert resp['output_orthography']['id'] == orthography2_id
        assert response.content_type == 'application/json'

    def test_new(self):
        """Tests that GET /users/new returns the data necessary to create a new user.

        The properties of the JSON object are 'roles', 'orthographies' and
        'markup_languages' and their values are arrays/lists.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # A contributor (or a viewer) should return a 403 status code on the
        # new action, which requires an administrator.
        response = self.app.get(url('new'), extra_environ=self.extra_environ_contrib,
                                status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Add some test data to the database.
        application_settings = omb.generate_default_application_settings()
        orthography1 = omb.generate_default_orthography1()
        orthography2 = omb.generate_default_orthography2()
        dbsession.add_all([application_settings, orthography1, orthography2])
        dbsession.commit()

        # Get the data currently in the db (see websetup.py for the test data).
        data = {
            'orthographies': db.get_mini_dicts_getter('Orthography')(),
            'roles': oldc.USER_ROLES,
            'markup_languages': oldc.MARKUP_LANGUAGES
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        # GET /users/new without params.  Without any GET params, /files/new
        # should return a JSON array for every store.
        response = self.app.get(url('new'),
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['orthographies'] == data['orthographies']
        assert resp['roles'] == data['roles']
        assert resp['markup_languages'] == data['markup_languages']
        assert response.content_type == 'application/json'

        # GET /new_file with params.  Param values are treated as strings, not
        # JSON.  If any params are specified, the default is to return a JSON
        # array corresponding to store for the param.  There are three cases
        # that will result in an empty JSON array being returned:
        # 1. the param is not specified
        # 2. the value of the specified param is an empty string
        # 3. the value of the specified param is an ISO 8601 UTC datetime
        #    string that matches the most recent datetime_modified value of the
        #    store in question.
        params = {
            # Value is any string: 'orthographies' will be in response.
            'orthographies': 'anything can go here!'
        }
        response = self.app.get(url('new'), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['orthographies'] == data['orthographies']
        assert resp['roles'] == data['roles']
        assert resp['markup_languages'] == data['markup_languages']
        assert response.content_type == 'application/json'

        params = {
            # Value is ISO 8601 UTC datetime string that does not match the most
            # recent Orthography.datetime_modified value: 'orthographies' *will* be in
            # response.
            'orthographies': datetime.datetime.utcnow().isoformat()
        }
        response = self.app.get(url('new'), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['orthographies'] == data['orthographies']
        assert resp['roles'] == data['roles']
        assert resp['markup_languages'] == data['markup_languages']
        assert response.content_type == 'application/json'

        params = {
            # Value is ISO 8601 UTC datetime string that does match the most
            # recent Orthography.datetime_modified value: 'orthographies' will *not* be in response.
            'orthographies': db.get_most_recent_modification_datetime('Orthography').isoformat()
        }
        response = self.app.get(url('new'), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['orthographies'] == []
        assert resp['roles'] == data['roles']
        assert resp['markup_languages'] == data['markup_languages']
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /users/id updates the user with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        default_contributor_id = dbsession.query(User).filter(User.role=='contributor').first().id
        def_contrib_environ = {'test.authentication.id': default_contributor_id}

        # Create a user to update.
        original_researchers_directory = os.listdir(self.users_path)
        original_user_count = dbsession.query(User).count()
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        user_id = resp['id']
        datetime_modified = resp['datetime_modified']
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        assert new_user_count == original_user_count + 1
        assert resp['username'] == 'johndoe'
        assert resp['email'] == 'john.doe@gmail.com'
        assert 'password' not in resp
        assert new_researchers_directory != original_researchers_directory
        assert 'johndoe' in new_researchers_directory
        assert response.content_type == 'application/json'

        # Update the user
        sleep(1)    # sleep for a second to ensure that MySQL registers a different datetime_modified for the update
        params = self.user_create_params.copy()
        params.update({
            'username': 'johnbuck',    # Admins CAN change usernames
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'contributor'  # Admins CAN change roles
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        new_datetime_modified = resp['datetime_modified']
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        researchers_directory = new_researchers_directory
        new_researchers_directory = os.listdir(self.users_path)
        assert user_count == new_user_count
        assert new_datetime_modified != datetime_modified
        assert resp['username'] == 'johnbuck'
        assert resp['role'] == 'contributor'
        assert resp['last_name'] == 'Doe'
        assert researchers_directory != new_researchers_directory
        assert 'johndoe' in researchers_directory and 'johndoe' not in new_researchers_directory
        assert 'johnbuck' in new_researchers_directory and 'johnbuck' not in researchers_directory
        assert response.content_type == 'application/json'

        # Attempt to update the user as a contributor and expect to fail
        params = self.user_create_params.copy()
        params.update({
            'username': 'johnbuck',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Buck',        # here is the attempted change
            'email': 'john.doe@gmail.com',
            'role': 'contributor'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers,
                                    def_contrib_environ, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Attempt to update the user as the user and expect to succeed
        user_environ = {'test.authentication.id': user_id}
        params = self.user_create_params.copy()
        params.update({
            'username': 'johnbuck',
            'password': 'Zzzzzz.9',    # Change the password too
            'password_confirm': 'Zzzzzz.9',
            'first_name': 'John',
            'last_name': 'Buck',        # Now this change will succeed
            'email': 'john.doe@gmail.com',
            'role': 'contributor'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers,
                                    user_environ)
        resp = response.json_body
        user_just_updated = dbsession.query(User).get(user_id)
        assert resp['username'] == 'johnbuck'
        assert resp['last_name'] == 'Buck'
        assert h.encrypt_password(u'Zzzzzz.9', user_just_updated.salt.encode('utf8')) == user_just_updated.password
        assert response.content_type == 'application/json'

        # Simulate a user attempting to update his username.  Expect to fail.
        params = self.user_create_params.copy()
        params.update({
            'username': 'iroc_z',  # Not permitted
            'password': 'Zzzzzz.9',
            'password_confirm': 'Zzzzzz.9',
            'first_name': 'John',
            'last_name': 'Buck',
            'email': 'john.doe@gmail.com',
            'role': 'contributor'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers,
                                    user_environ, status=400)
        resp = response.json_body
        assert resp['errors'] == 'Only administrators can update usernames.'
        assert response.content_type == 'application/json'

        # Simulate a user attempting to update his role.  Expect to fail.
        params = self.user_create_params.copy()
        params.update({
            'username': 'johnbuck',
            'password': 'Zzzzzz.9',
            'password_confirm': 'Zzzzzz.9',
            'first_name': 'John',
            'last_name': 'Buck',
            'email': 'john.doe@gmail.com',
            'role': 'administrator'    # Not permitted
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers,
                                    user_environ, status=400)
        resp = response.json_body
        assert resp['errors'] == 'Only administrators can update roles.'
        assert response.content_type == 'application/json'

        # Update the user with empty values for username and password and expect
        # these fields to retain their original values.
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
        params = self.user_create_params.copy()
        params.update({
            'first_name': 'John',
            'last_name': 'Buckley',         # Here is a change
            'email': 'john.doe@gmail.com',
            'role': 'contributor',
            'markup_language': 'Markdown',  # Another change
            'page_content': md_contents       # And another
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers, user_environ)
        resp = response.json_body
        user_just_updated = dbsession.query(User).get(user_id)
        assert resp['username'] == 'johnbuck'
        assert resp['last_name'] == 'Buckley'
        assert h.encrypt_password(u'Zzzzzz.9', user_just_updated.salt.encode('utf8')) == user_just_updated.password
        assert resp['html'] == h.get_HTML_from_contents(md_contents, 'Markdown')
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        params = self.user_create_params.copy()
        params.update({
            'first_name': 'John',
            'last_name': 'Buckley',
            'email': 'john.doe@gmail.com',
            'role': 'contributor',
            'markup_language': 'Markdown',
            'page_content': md_contents
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=user_id), params, self.json_headers, user_environ, status=400)
        resp = response.json_body
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /users/id deletes the user with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a user to delete.
        original_researchers_directory = os.listdir(self.users_path)
        original_user_count = dbsession.query(User).count()
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        user_id = resp['id']
        datetime_modified = resp['datetime_modified']
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        researchers_directory_m_time = os.stat(self.users_path).st_mtime
        assert new_user_count == original_user_count + 1
        assert resp['username'] == 'johndoe'
        assert resp['email'] == 'john.doe@gmail.com'
        assert 'password' not in resp
        assert new_researchers_directory != original_researchers_directory
        assert 'johndoe' in new_researchers_directory

        # Write a file to the user's directory just to make sure that the deletion
        # works on a non-empty directory
        f = open(os.path.join(self.users_path, 'johndoe', 'test_file.txt'), 'w')
        f.write('Some content here.')
        f.close()
        assert 'test_file.txt' in os.listdir(os.path.join(self.users_path, 'johndoe'))

        # Now delete the user
        response = self.app.delete(url('delete', id=user_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        researchers_directory = new_researchers_directory
        new_researchers_directory = os.listdir(self.users_path)
        deleted_user = dbsession.query(User).get(user_id)
        assert deleted_user is None
        assert new_user_count == user_count - 1
        assert resp['id'] == user_id
        assert 'password' not in resp
        assert resp['username'] == 'johndoe'
        assert researchers_directory != new_researchers_directory
        assert 'johndoe' not in new_researchers_directory and 'johndoe' in researchers_directory
        assert response.content_type == 'application/json'

        # Again create a user to (attempt to) delete.
        original_researchers_directory = os.listdir(self.users_path)
        original_user_count = dbsession.query(User).count()
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        user_id = resp['id']
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        assert new_user_count == original_user_count + 1
        assert resp['username'] == 'johndoe'
        assert resp['email'] == 'john.doe@gmail.com'
        assert 'password' not in resp
        assert new_researchers_directory != original_researchers_directory
        assert 'johndoe' in new_researchers_directory
        assert response.content_type == 'application/json'

        # Show that a user cannot delete his own user object
        user_environ = {'test.authentication.id': user_id}
        response = self.app.delete(url('delete', id=user_id), headers=self.json_headers,
            extra_environ=user_environ, status=403)
        resp = response.json_body
        user_count = new_user_count
        new_user_count = dbsession.query(User).count()
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin, status=404)
        assert 'There is no user with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

    def test_show(self):
        """Tests that GET /users/id returns the user with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a user to show.
        original_researchers_directory = os.listdir(self.users_path)
        original_user_count = dbsession.query(User).count()
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        user_id = resp['id']
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        assert new_user_count == original_user_count + 1
        assert resp['username'] == 'johndoe'
        assert resp['email'] == 'john.doe@gmail.com'
        assert 'password' not in resp
        assert new_researchers_directory != original_researchers_directory
        assert 'johndoe' in new_researchers_directory

        # Try to get a user using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id), headers=self.json_headers,
                            extra_environ=self.extra_environ_admin, status=404)
        resp = response.json_body
        assert 'There is no user with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id (show that a viewer can GET a user too)
        response = self.app.get(url('show', id=user_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        # Previously asserted username not in user dicts returned. Why?
        assert 'username' in resp
        assert 'password' not in resp
        assert resp['email'] == 'john.doe@gmail.com'
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /users/id/edit returns a JSON object of data necessary to edit the user with id=id.

        The JSON object is of the form {'user': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add some test data to the database.
        orthography1 = omb.generate_default_orthography1()
        orthography2 = omb.generate_default_orthography2()
        dbsession.add_all([orthography1, orthography2])
        dbsession.commit()

        # Get the data currently in the db (see websetup.py for the test data).
        data = {
            'orthographies': db.get_mini_dicts_getter('Orthography')(),
            'roles': oldc.USER_ROLES,
            'markup_languages': oldc.MARKUP_LANGUAGES
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        # Create a user to edit.
        original_researchers_directory = os.listdir(self.users_path)
        original_user_count = dbsession.query(User).count()
        params = self.user_create_params.copy()
        params.update({
            'username': 'johndoe',
            'password': 'Aaaaaa_1',
            'password_confirm': 'Aaaaaa_1',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@gmail.com',
            'role': 'viewer'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        user_id = resp['id']
        new_user_count = dbsession.query(User).count()
        new_researchers_directory = os.listdir(self.users_path)
        assert new_user_count == original_user_count + 1
        assert resp['username'] == 'johndoe'
        assert resp['email'] == 'john.doe@gmail.com'
        assert 'password' not in resp
        assert new_researchers_directory != original_researchers_directory
        assert 'johndoe' in new_researchers_directory
        assert response.content_type == 'application/json'

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=user_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin, status=404)
        assert 'There is no user with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id, admin
        response = self.app.get(url('edit', id=user_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['user']['username'] == 'johndoe'
        assert resp['data']['orthographies'] == data['orthographies']
        assert resp['data']['roles'] == data['roles']
        assert resp['data']['markup_languages'] == data['markup_languages']
        assert response.content_type == 'application/json'

        # Valid id, user self-editing, GET params
        user_environ = {'test.authentication.id': user_id}
        params = {
            # Value is ISO 8601 UTC datetime string that does match the most
            # recent Orthography.datetime_modified value: 'orthographies' will *not* be in response.
            'orthographies': db.get_most_recent_modification_datetime('Orthography').isoformat()
        }
        response = self.app.get(url('edit', id=user_id), params,
            headers=self.json_headers, extra_environ=user_environ)
        resp = response.json_body
        assert resp['user']['username'] == 'johndoe'
        assert resp['data']['orthographies'] == []
        assert resp['data']['roles'] == data['roles']
        assert resp['data']['markup_languages'] == data['markup_languages']
        assert response.content_type == 'application/json'

        # Valid id but contributor -- expect to fail
        response = self.app.get(url('edit', id=user_id),
            headers=self.json_headers, extra_environ=self.extra_environ_contrib, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'
