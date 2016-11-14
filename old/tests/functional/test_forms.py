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
import json
import logging
import pprint
from time import sleep
import transaction

import pytest

from old.lib.dbutils import DBUtils
import old.lib.helpers as h
import old.models.modelbuilders as omb
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
            db = DBUtils(dbsession, self.settings)
            # Test that the restricted tag is working correctly.
            # First get the users.
            users = dbsession.query(User).all()
            contributor_id = [u for u in users if u.role ==
                              'contributor'][0].id
            # Then add a contributor and a restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            my_contributor = omb.generate_default_user()
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
            application_settings = omb.generate_default_application_settings()
            application_settings.unrestricted_users = [my_contributor]
            dbsession.add(application_settings)
            transaction.commit()

            # Finally, issue two POST requests to create two default forms with
            # the *default* contributor as the enterer. One form will be
            # restricted and the other will not be.
            extra_environ = {'test.authentication.id': contributor_id}

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
            resp = response.json_body
            restricted_form_id = resp['id']

            # Create the unrestricted form.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test restricted tag transcription 2',
                'translations': [{
                    'transcription': 'test restricted tag translation 2',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ)
            resp = response.json_body

            # Expectation: the administrator, the default contributor (qua
            # enterer) and the unrestricted my_contributor should all be able
            # to view both forms. The viewer will only receive the unrestricted
            # form.

            # An administrator should be able to view both forms.
            extra_environ = {'test.authentication.role': 'administrator'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2
            assert resp[0]['transcription'] == 'test restricted tag transcription'
            assert resp[0]['morpheme_break_ids'] == None
            assert resp[0]['morpheme_break_ids'] == None
            assert resp[0]['translations'][0]['transcription'] == 'test restricted tag translation'
            assert type(resp[0]['translations'][0]['id']) == type(1)
            assert type(resp[0]['id']) == type(1)
            assert response.content_type == 'application/json'

            # The default contributor (qua enterer) should also be able to view
            # both forms.
            extra_environ = {'test.authentication.id': contributor_id}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2

            # Mycontributor (an unrestricted user) should also be able to view
            # both forms.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2

            # A (not unrestricted) viewer should be able to view only one form.
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 1

            # Remove Mycontributor from the unrestricted users list and access
            # to the second form will be denied.
            application_settings = db.current_app_set
            application_settings.unrestricted_users = []
            dbsession.add(application_settings)
            transaction.commit()

            # Mycontributor (no longer an unrestricted user) should now *not* be
            # able to view the restricted form.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 1

            # Remove the restricted tag from the form and the viewer should now
            # be able to view it too.
            restricted_form = dbsession.query(Form).get(
                restricted_form_id)
            restricted_form.tags = []
            dbsession.add(restricted_form)
            transaction.commit()
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2

            # Clear all Forms (actually, everything but the tags, users and
            # languages)
            db.clear_all_models(['User', 'Tag', 'Language'])

    def test_new(self):
        """Tests that GET /form/new returns an appropriate JSON object for
        creating a new OLD form.
        The properties of the JSON object are 'grammaticalities',
        'elicitation_methods', 'tags', 'syntactic_categories', 'speakers',
        'users' and 'sources' and their values are arrays/lists.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Unauthorized user ('viewer') should return a 401 status code on
            # the new action, which requires a 'contributor' or an
            # 'administrator'.
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('new'), extra_environ=extra_environ,
                                    status=403)
            resp = response.json_body
            assert response.content_type == 'application/json'
            assert resp['error'] == ('You are not authorized to access this'
                                     ' resource.')

            # Add some test data to the database.
            application_settings = omb.generate_default_application_settings()
            elicitation_method = omb.generate_default_elicitation_method()
            foreign_word_tag = omb.generate_foreign_word_tag()
            restricted_tag = omb.generate_restricted_tag()
            N = omb.generate_n_syntactic_category()
            Num = omb.generate_num_syntactic_category()
            S = omb.generate_s_syntactic_category()
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([application_settings, elicitation_method,
                               foreign_word_tag, restricted_tag, N, Num, S,
                               speaker, source])
            transaction.commit()

            # Get the data currently in the db (see websetup.py for the test
            # data).
            data = {
                'grammaticalities': db.get_grammaticalities(),
                'elicitation_methods': db.get_mini_dicts_getter(
                    'ElicitationMethod')(),
                'tags': db.get_mini_dicts_getter('Tag')(),
                'syntactic_categories': db.get_mini_dicts_getter(
                    'SyntacticCategory')(),
                'speakers': db.get_mini_dicts_getter('Speaker')(),
                'users': db.get_mini_dicts_getter('User')(),
                'sources': db.get_mini_dicts_getter('Source')()
            }
            pprint.pprint(data)

            # JSON.stringify and then re-Python-ify the data. This is what the
            # data should look like in the response to a simulated GET request.
            # data = json.loads(json.dumps(data, cls=h.JSONOLDEncoder))
            data = json.loads(json.dumps(data))

            # GET /form/new without params.  Without any GET params, /form/new
            # should return a JSON array for every store.
            response = self.app.get(url('new'),
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['grammaticalities'] == data['grammaticalities']
            assert resp['elicitation_methods'] == data['elicitation_methods']
            assert resp['tags'] == data['tags']
            assert resp['syntactic_categories'] == data['syntactic_categories']
            assert resp['speakers'] == data['speakers']
            assert resp['users'] == data['users']
            assert resp['sources'] == data['sources']
            assert response.content_type == 'application/json'

            # GET /new_form with params. Param values are treated as strings,
            # not JSON. If any params are specified, the default is to return a
            # JSON array corresponding to store for the param. There are three
            # cases that will result in an empty JSON array being returned:
            # 1. the param is not specified
            # 2. the value of the specified param is an empty string
            # 3. the value of the specified param is an ISO 8601 UTC datetime
            #    string that matches the most recent datetime_modified value of
            #    the store in question.
            params = {
                # Value is empty string: 'grammaticalities' will not be in
                # response.
                'grammaticalities': '',
                # Value is any string: 'elicitation_methods' will be in
                # response.
                'elicitation_methods': 'anything can go here!',
                # Value is ISO 8601 UTC datetime string that does not match the
                # most recent Tag.datetime_modified value: 'tags' *will* be in
                # response.
                'tags': datetime.datetime.utcnow().isoformat(),
                # Value is ISO 8601 UTC datetime string that does match the most
                # recent SyntacticCategory.datetime_modified value:
                # 'syntactic_categories' will *not* be in response.
                'syntactic_categories':
                    db.get_most_recent_modification_datetime(
                        'SyntacticCategory').isoformat()
            }
            response = self.app.get(url('new'), params,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['elicitation_methods'] == data['elicitation_methods']
            assert resp['tags'] == data['tags']
            assert resp['grammaticalities'] == []
            assert resp['syntactic_categories'] == []
            assert resp['speakers'] == []
            assert resp['users'] == []
            assert resp['sources'] == []

