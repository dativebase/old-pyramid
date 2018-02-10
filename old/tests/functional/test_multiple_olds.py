# Copyright 2018 Joel Dunham
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

"""Tests that a single OLD process can correctly handle requests against
multiple OLD instances. This test requires that two OLDs have been configured
for testing, see config.ini, esp. ``OLD_NAME_2_TESTS``.
"""

from base64 import b64encode
import json
import logging
import os

import old.lib.helpers as h
import old.models as old_models
from old.models import Form
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Form._url(old_name=TestView.old_name)
url2 = Form._url(old_name=TestView.old_name_2)
files_url = old_models.File._url(old_name=TestView.old_name)
files_url2 = old_models.File._url(old_name=TestView.old_name_2)

def auth_url(route_name):
    return {
        'authenticate': '/{}/login/authenticate'.format(TestView.old_name),
        'logout': '/{}/login/logout'.format(TestView.old_name),
        'email_reset_password': '/{}/login/email_reset_password'.format(
            TestView.old_name)
    }.get(route_name, '')


def auth_url_2(route_name):
    return {
        'authenticate': '/{}/login/authenticate'.format(TestView.old_name_2),
        'logout': '/{}/login/logout'.format(TestView.old_name_2),
        'email_reset_password': '/{}/login/email_reset_password'.format(
            TestView.old_name_2)
    }.get(route_name, '')


class TestMultipleOLDsView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_SEARCH_to_web_test_valid_methods()

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def test_distinct_authentication(self):
        """Tests that logging into one OLD does not get you access to the other
        OLD, in particular it does not give you access to browsing the forms of
        that other OLD.
        """
        # This will prevent routes.py from doing test-specific magic to delete
        # our user sessions. See ``routes.py::fix_for_tests``.
        extra_environ = {'test.rig.auth': False}

        # Login to OLD #1
        params = json.dumps({'username': 'admin', 'password': 'adminA_1'})
        response = self.app.post(
            auth_url('authenticate'), params, self.json_headers,
            extra_environ=extra_environ)
        resp = response.json_body
        assert resp['authenticated'] is True
        assert response.content_type == 'application/json'

        # Expect that we can request the forms from OLD #1 because we are
        # authenticated to it.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)

        # Expect that we can NOT request the forms from OLD #2 because we are
        # NOT authenticated to it.
        response = self.app.get(url2('index'), headers=self.json_headers,
                                extra_environ=extra_environ, status=401)

        # Logout from OLD #1
        response = self.app.get(auth_url('logout'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert resp['authenticated'] is False
        assert response.content_type == 'application/json'

        # Login to OLD #2
        params = json.dumps({'username': 'admin', 'password': 'adminA_1'})
        response = self.app.post(
            auth_url_2('authenticate'), params, self.json_headers,
            extra_environ=extra_environ)
        resp = response.json_body
        assert resp['authenticated'] is True
        assert response.content_type == 'application/json'

        # Expect that we can request the forms from OLD #2 because we are
        # authenticated to it.
        response = self.app.get(url2('index'), headers=self.json_headers,
                                extra_environ=extra_environ)

        # Expect that we can NOT request the forms from OLD #1 because we are
        # NOT authenticated to it.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ, status=401)

    def test_distinct_file_creation(self):
        """Tests that when a file is uploaded to OLD #1 it appears in the
        correct place in the filesystem, and vice versa for OLD #2.
        """
        # This will prevent routes.py from doing test-specific magic to delete
        # our user sessions. See ``routes.py::fix_for_tests``.
        extra_environ = {'test.rig.auth': False}

        # Path on disk to store/oldtests2/files/
        old2_files_path = h.get_old_directory_path(
            'files', settings=self.settings2)

        # Login to OLD #1
        params = json.dumps({'username': 'admin', 'password': 'adminA_1'})
        response = self.app.post(
            auth_url('authenticate'), params, self.json_headers,
            extra_environ=extra_environ)
        resp = response.json_body
        assert resp['authenticated'] is True
        assert response.content_type == 'application/json'

        # Login to OLD #2
        params = json.dumps({'username': 'admin', 'password': 'adminA_1'})
        response = self.app.post(
            auth_url_2('authenticate'), params, self.json_headers,
            extra_environ=extra_environ)
        resp = response.json_body
        assert resp['authenticated'] is True
        assert response.content_type == 'application/json'

        # Get a JPG as a base64 string
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64_encoded = b64encode(f.read()).decode('utf8')

        # Upload a JPG to OLD #1
        params = self.file_create_params_base64.copy()
        filename = 'old_1_file.jpg'
        params.update({
            'filename': filename,
            'base64_encoded_file': jpg_file_base64_encoded
        })
        params = json.dumps(params)
        response = self.app.post(
            files_url('create'), params, self.json_headers, extra_environ)
        resp = response.json_body

        # Expect OLD #1's JPG to be in OLD #1's store/ and not in OLD #2's
        expected_good_path = os.path.join(self.files_path, filename)
        expected_bad_path = os.path.join(old2_files_path, filename)
        assert os.path.isfile(expected_good_path)
        assert not os.path.isfile(expected_bad_path)

        # Upload a JPG to OLD #2
        params = self.file_create_params_base64.copy()
        filename = 'old_2_file.jpg'
        params.update({
            'filename': filename,
            'base64_encoded_file': jpg_file_base64_encoded
        })
        params = json.dumps(params)
        response = self.app.post(
            files_url2('create'), params, self.json_headers, extra_environ)
        resp = response.json_body

        # Expect OLD #2's JPG to be in OLD #2's store/ and not in OLD #1's
        expected_good_path = os.path.join(old2_files_path, filename)
        expected_bad_path = os.path.join(self.files_path, filename)
        assert os.path.isfile(expected_good_path)
        assert not os.path.isfile(expected_bad_path)
