# Copyright 2021 Joel Dunham
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.  #  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from base64 import encodebytes
import datetime
import json
import logging
import os
import pprint
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc

from old.lib.dbutils import DBUtils
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import (
    Form,
    Tag,
    User,
)
from old.models.form import FormFile
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Form._url(old_name=TestView.old_name)
files_url = old_models.File._url(old_name=TestView.old_name)


class TestReadonlyMode(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_SEARCH_to_web_test_valid_methods()

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def test_readonly_mode(self):
        if self.settings.get('readonly') == '0':
            return

        # Create form requests fail in read-only mode
        params = self.form_create_params.copy()
        params.update({
            'transcription': 'test_create_transcription',
            'translations': [{
                'transcription': 'test_create_translation',
                'grammaticality': ''
            }],
            'status': 'tested'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                 self.extra_environ_contrib, status=403).json_body
        exp_msg = ('This OLD is running in read-only mode. All attempts to'
                   ' mutate data will be rejected.')
        assert exp_msg == response['error']

        # Update form requests fail in read-only mode
        response = self.app.put(url('update', id=1), params,
                                self.json_headers,
                                self.extra_environ_contrib, status=403).json_body
        assert exp_msg == response['error']

        # Delete form requests fail in read-only mode
        response = self.app.delete(
            url('delete', id=1), extra_environ=self.extra_environ_contrib,
            status=403).json_body
        assert exp_msg == response['error']

        # Remember requests fail in read-only mode
        response = self.app.post(
            '/{}/forms/remember'.format(self.old_name),
            json.dumps({'forms': [1]}),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib,
            status=403).json_body
        assert exp_msg == response['error']

        # Updating morpheme references fails in read-only mode
        response = self.app.put(
            '/{}/forms/update_morpheme_references'.format(self.old_name),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin,
            status=403).json_body
        assert exp_msg == response['error']

        # Creating a new tag fails in read-only mode
        response = self.app.post(
            '/{}/tags'.format(self.old_name),
            json.dumps({'name': 'tag', 'description': 'Described.'}),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib,
            status=403).json_body
        assert exp_msg == response['error']
