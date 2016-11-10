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
from old.models import (
    Form,
    Tag,
    User,
    get_engine,
    get_session_factory,
    get_tm_session,
)
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Form._url()


###############################################################################
# Functions for creating & retrieving test data
###############################################################################

class TestFormsView(TestView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_SEARCH_to_web_test_valid_methods()

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def test_index(self):
        """Tests that GET /forms returns a JSON array of forms with expected
        values.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            # Test that the restricted tag is working correctly.
            # First get the users.
            users = dbsession.query(User).all()
            contributor_id = [u for u in users if u.role ==
                              'contributor'][0].id
            # Then add a contributor and a restricted tag.
            restricted_tag = h.generate_restricted_tag()
            my_contributor = h.generate_default_user()
            my_contributor_first_name = 'Mycontributor'
            my_contributor.first_name = my_contributor_first_name
            dbsession.add_all([restricted_tag, my_contributor])
            transaction.commit()
            my_contributor = dbsession.query(User).filter(
                User.first_name == my_contributor_first_name).first()
            my_contributor_id = my_contributor.id
            restricted_tag = dbsession.query(Tag).filter(
                Tag.name == 'restricted').first()

            # Then add the default application settings with my_contributor as
            # the only unrestricted user.
            application_settings = h.generate_default_application_settings()
            application_settings.unrestricted_users = [my_contributor]
            dbsession.add(application_settings)
            transaction.commit()

            # Finally, issue two POST requests to create two default forms with
            # the *default* contributor as the enterer. One form will be
            # restricted and the other will not be.
            extra_environ = {'test.authentication.id': contributor_id,
                             'test.application_settings': True}

            # Create the restricted form.
            tags = dbsession.query(Tag).all()
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test restricted tag transcription',
                'translations': [{
                    'transcription': 'test restricted tag translation',
                    'grammaticality': ''
                }],
                'tags': [tags[0].id]  # the restricted tag should be the only
                                      # one
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ)
            resp = json.loads(response.body)
            resp = response.json_body
            restricted_form_id = resp['id']

    def _tmp_test_index(self):
        """Tests that GET /forms returns an array of all forms and that order_by
        and pagination parameters work correctly.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            # Add 100 forms.
            forms = [create_form_from_index(i + 1) for i in range(100)]
            dbsession.add_all(forms)
            transaction.commit()
            forms = dbsession.query(Form).all()
            forms_count = len(forms)
            # Test that GET /forms gives us all of the forms.
            response = self.app.get(
                url('index'), headers=self.json_headers,
                extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert len(resp) == forms_count
            assert resp[0]['name'] == 'form1'
            assert resp[0]['id'] == forms[0].id
            assert response.content_type == 'application/json'

