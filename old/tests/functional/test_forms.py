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

from base64 import encodestring
import datetime
import json
import logging
import os
import pprint
from time import sleep
import transaction

from sqlalchemy.sql import desc
import pytest

from old.lib.dbutils import DBUtils
import old.lib.helpers as h
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import (
    Form,
    Tag,
    User,
    get_engine,
    get_session_factory,
    get_tm_session,
)
from old.models.form import FormFile
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Form._url()
files_url = old_models.File._url()


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

    def test_create(self):
        """Tests that POST /forms correctly creates a new form."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Pass some mal-formed JSON to test that a 400 error is returned.
            params = '"a'   # Bad JSON
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin, status=400)
            resp = response.json_body
            assert (resp['error'] == 'JSON decode error: the parameters'
                    ' provided were not valid JSON.')

            # Create a test form.
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
                                     self.extra_environ_admin)
            resp = response.json_body
            form_count = dbsession.query(Form).count()
            assert type(resp) == type({})
            assert resp['transcription'] == 'test_create_transcription'
            assert (resp['translations'][0]['transcription'] ==
                    'test_create_translation')
            assert resp['morpheme_break_ids'] == None
            assert resp['enterer']['first_name'] == 'Admin'
            assert resp['status'] == 'tested'
            assert form_count == 1
            assert response.content_type == 'application/json'

            # Add an empty application settings and two syntactic categories.
            n_syncat = omb.generate_n_syntactic_category()
            num_syncat = omb.generate_num_syntactic_category()
            s_syncat = omb.generate_s_syntactic_category()
            agr_syncat = old_models.SyntacticCategory(name='Agr')
            application_settings = old_models.ApplicationSettings()
            dbsession.add_all([s_syncat, n_syncat, num_syncat, agr_syncat,
                               application_settings])
            dbsession.flush()
            n_syncat_id = n_syncat.id
            num_syncat_id = num_syncat.id
            agr_syncat_id = agr_syncat.id
            transaction.commit()

            # Create three lexical forms, two of which are disambiguated only by
            # their category

            # chien/dog/N
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'chien',
                'morpheme_break': 'chien',
                'morpheme_gloss': 'dog',
                'translations': [{
                    'transcription': 'dog',
                    'grammaticality': ''
                }],
                'syntactic_category': n_syncat_id
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            dog_id = resp['id']

            # s/PL/Num
            params = self.form_create_params.copy()
            params.update({
                'transcription': 's',
                'morpheme_break': 's',
                'morpheme_gloss': 'PL',
                'translations': [{
                    'transcription': 'plural',
                    'grammaticality': ''
                }],
                'syntactic_category': num_syncat_id
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            plural_num_id = resp['id']
            form_count = dbsession.query(Form).count()
            assert form_count == 3

            # s/PL/Agr
            params = self.form_create_params.copy()
            params.update({
                'transcription': 's',
                'morpheme_break': 's',
                'morpheme_gloss': 'PL',
                'translations': [{
                    'transcription': 'plural',
                    'grammaticality': ''
                }],
                'syntactic_category': agr_syncat_id
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            plural_agr_id = resp['id']

            # Create another form whose morphemic analysis will reference the
            # lexical items created above. Since the current application
            # settings lists no morpheme delimiters, each word will be treated
            # as a morpheme by compile_morphemic_analysis.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Les chiens aboient.',
                'morpheme_break': 'les chien-s aboient',
                'morpheme_gloss': 'the dog-PL bark',
                'translations': [{
                    'transcription': 'The dogs are barking.',
                    'grammaticality': ''
                }],
                'syntactic_category': dbsession.query(
                    old_models.SyntacticCategory).filter(
                    old_models.SyntacticCategory.name=='S').first().id
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            form_count = dbsession.query(Form).count()
            assert type(resp) == type({})
            assert resp['transcription'] == 'Les chiens aboient.'
            assert (resp['translations'][0]['transcription'] == 'The dogs are'
                    ' barking.')
            assert resp['syntactic_category']['name'] == 'S'
            assert resp['morpheme_break_ids'] == [[[]], [[]], [[]]]
            assert resp['morpheme_gloss_ids'] == [[[]], [[]], [[]]]
            assert resp['syntactic_category_string'] == '? ? ?'
            assert (resp['break_gloss_category'] == 'les|the|? chien-s|dog-PL|?'
                    ' aboient|bark|?')
            assert resp['syntactic_category']['name'] == 'S'
            assert form_count == 5

            # Re-create the form from above but this time add a non-empty
            # application settings.  Now we should expect the
            # morpheme_break_ids, morpheme_gloss_ids and
            # syntactic_category_string to have non-vacuous values since '-' is
            # specified as a morpheme delimiter.
            application_settings = omb.generate_default_application_settings()
            dbsession.add(application_settings)
            transaction.commit()
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            form_count = dbsession.query(Form).count()
            assert resp['morpheme_break_ids'][1][0][0][2] == 'N'
            assert form_count == 6
            assert resp['morpheme_break_ids'][0] == [[]]
            assert resp['morpheme_break_ids'][1][0][0][0] == dog_id
            assert resp['morpheme_break_ids'][1][0][0][1] == 'dog'
            assert resp['morpheme_break_ids'][1][0][0][2] == 'N'
            assert resp['morpheme_break_ids'][1][1][0][0] == plural_num_id
            assert resp['morpheme_break_ids'][1][1][0][1] == 'PL'
            assert resp['morpheme_break_ids'][1][1][0][2] == 'Num'
            assert resp['morpheme_break_ids'][1][1][1][0] == plural_agr_id
            assert resp['morpheme_break_ids'][1][1][1][1] == 'PL'
            assert resp['morpheme_break_ids'][1][1][1][2] == 'Agr'
            assert resp['morpheme_break_ids'][2] == [[]]
            assert resp['morpheme_gloss_ids'][0] == [[]]
            assert resp['morpheme_gloss_ids'][1][0][0][0] == dog_id
            assert resp['morpheme_gloss_ids'][1][0][0][1] == 'chien'
            assert resp['morpheme_gloss_ids'][1][0][0][2] == 'N'
            assert resp['morpheme_gloss_ids'][1][1][0][0] == plural_num_id
            assert resp['morpheme_gloss_ids'][1][1][0][1] == 's'
            assert resp['morpheme_gloss_ids'][1][1][0][2] == 'Num'
            assert resp['morpheme_gloss_ids'][1][1][1][0] == plural_agr_id
            assert resp['morpheme_gloss_ids'][1][1][1][1] == 's'
            assert resp['morpheme_gloss_ids'][1][1][1][2] == 'Agr'
            assert resp['morpheme_gloss_ids'][2] == [[]]
            assert resp['syntactic_category_string'] == '? N-Num ?'
            assert (resp['break_gloss_category'] == 'les|the|?'
                    ' chien|dog|N-s|PL|Num aboient|bark|?')

            # Recreate the above form but put morpheme delimiters in unexpected
            # places.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Les chiens aboient.',
                'morpheme_break': 'les chien- -s aboient',
                'morpheme_gloss': 'the dog- -PL bark',
                'translations': [{
                    'transcription': 'The dogs are barking.',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            form_count = dbsession.query(Form).count()
            morpheme_break_ids = resp['morpheme_break_ids']
            assert len(morpheme_break_ids) == 4   # 3 spaces in the mb field
            assert len(morpheme_break_ids[1]) == 2  # 'chien-' is split into
                                                    # 'chien' and ''
            assert ('N-?' in resp['syntactic_category_string'] and
                    '?-Num' in resp['syntactic_category_string'])

    def test_create_invalid(self):
        """Tests that POST /forms with invalid input returns an appropriate
        error.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Empty translations should raise error
            form_count = dbsession.query(Form).count()
            params = self.form_create_params.copy()
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin, status=400)
            resp = response.json_body
            new_form_count = dbsession.query(Form).count()
            assert resp['errors']['translations'] == 'Please enter a value'
            assert new_form_count == form_count

            # If all transcription-type values are empty, an error should be
            # returned for that special case.
            form_count = dbsession.query(Form).count()
            params = self.form_create_params.copy()
            params.update({
                'translations': [{
                    'transcription': 'good',
                    'grammaticality': ''
                }],
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin, status=400)
            resp = response.json_body
            new_form_count = dbsession.query(Form).count()
            assert resp['errors'] == ('You must enter a value in at least one of'
                                      ' the following fields: transcription,'
                                      ' morpheme break, phonetic transcription,'
                                      ' or narrow phonetic transcription.')
            assert new_form_count == form_count

            # Exceeding length restrictions should return errors also.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test create invalid transcription' * 100,
                'grammaticality': '*',
                'phonetic_transcription':
                    'test create invalid phonetic transcription' * 100,
                'narrow_phonetic_transcription':
                    'test create invalid narrow phonetic transcription' * 100,
                'morpheme_break': 'test create invalid morpheme break' * 100,
                'morpheme_gloss': 'test create invalid morpheme gloss' * 100,
                'translations': [{
                    'transcription': 'test create invalid translation',
                    'grammaticality': ''
                }],
                'status': 'invalid status value'
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin, status=400)
            resp = response.json_body
            new_form_count = dbsession.query(Form).count()
            too_long_error = 'Enter a value not more than 510 characters long'
            assert resp['errors']['transcription'] == too_long_error
            assert resp['errors']['phonetic_transcription'] == too_long_error
            assert (resp['errors']['narrow_phonetic_transcription'] ==
                    too_long_error)
            assert resp['errors']['morpheme_break'] == too_long_error
            assert resp['errors']['morpheme_gloss'] == too_long_error
            assert (resp['errors']['status'] ==
                "Value must be one of: tested; requires testing (not 'invalid"
                " status value')")
            assert new_form_count == form_count

            # Add some default application settings and set
            # app_globals.application_settings.
            application_settings = omb.generate_default_application_settings()
            bad_grammaticality = '***'
            good_grammaticality = (
                application_settings.grammaticalities.split(',')[0])
            dbsession.add(application_settings)
            transaction.commit()
            extra_environ = self.extra_environ_admin.copy()
            extra_environ['test.application_settings'] = True

            # Create a form with an invalid grammaticality
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test create invalid transcription',
                'grammaticality': bad_grammaticality,
                'translations': [{
                    'transcription': 'test create invalid translation',
                    'grammaticality': bad_grammaticality
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ=extra_environ, status=400)
            resp = response.json_body
            new_form_count = dbsession.query(Form).count()
            assert (resp['errors']['grammaticality'] == 'The grammaticality'
                    ' submitted does not match any of the available options.')
            assert (resp['errors']['translations'] == 'At least one submitted'
                    ' translation grammaticality does not match any of the'
                    ' available options.')
            assert new_form_count == form_count

            # Create a form with a valid grammaticality
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test create invalid transcription',
                'grammaticality': good_grammaticality,
                'translations': [{
                    'transcription': 'test create invalid translation',
                    'grammaticality': good_grammaticality
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ=extra_environ)
            resp = response.json_body
            new_form_count = dbsession.query(Form).count()
            assert resp['grammaticality'] == good_grammaticality
            assert good_grammaticality in [t['grammaticality'] for t in
                                           resp['translations']]
            assert new_form_count == form_count + 1

            # Create a form with some invalid many-to-one data, i.e.,
            # elicitation method, speaker, enterer, etc.
            bad_id = 109
            bad_int = 'abc'
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test create invalid transcription',
                'translations': [{
                    'transcription': 'test create invalid translation',
                    'grammaticality': ''
                }],
                'elicitation_method': bad_id,
                'syntactic_category': bad_int,
                'speaker': bad_id,
                'elicitor': bad_int,
                'verifier': bad_id,
                'source': bad_int
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ=extra_environ, status=400)
            resp = response.json_body
            form_count = new_form_count
            new_form_count = dbsession.query(Form).count()
            assert response.content_type == 'application/json'
            assert (resp['errors']['elicitation_method'] ==
                    'There is no elicitation method with id %d.' % bad_id)
            assert (resp['errors']['speaker'] == 'There is no speaker with id'
                    ' %d.' % bad_id)
            assert (resp['errors']['verifier'] == 'There is no user with id'
                    ' %d.' % bad_id)
            assert (resp['errors']['syntactic_category'] == 'Please enter an'
                    ' integer value')
            assert resp['errors']['elicitor'] == 'Please enter an integer value'
            assert resp['errors']['source'] == 'Please enter an integer value'
            assert new_form_count == form_count

            # Now create a form with some *valid* many-to-one data, i.e.,
            # elicitation method, speaker, elicitor, etc.
            elicitation_method = omb.generate_default_elicitation_method()
            s_syncat = omb.generate_s_syntactic_category()
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([elicitation_method, s_syncat, speaker, source])
            dbsession.flush()
            source_id = source.id
            source_year = source.year
            elicitation_method_name = elicitation_method.name
            transaction.commit()
            contributor = dbsession.query(old_models.User).filter(
                old_models.User.role=='contributor').first()
            administrator = dbsession.query(old_models.User).filter(
                old_models.User.role=='administrator').first()
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test create invalid transcription',
                'translations': [{'transcription': 'test create invalid translation',
                            'grammaticality': ''}],
                'elicitation_method': db.get_elicitation_methods()[0].id,
                'syntactic_category': db.get_syntactic_categories()[0].id,
                'speaker': db.get_speakers()[0].id,
                'elicitor': contributor.id,
                'verifier': administrator.id,
                'source': source_id
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ=extra_environ)
            resp = response.json_body
            new_form_count = dbsession.query(Form).count()
            assert resp['elicitation_method']['name'] == elicitation_method_name
            assert resp['source']['year'] == source_year    # etc. ...
            assert new_form_count == form_count + 1

    def test_create_with_inventory_validation(self):
        """Tests that POST /forms correctly applies inventory-based validation
        on form creation attempts.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Configure the application settings with some VERY STRICT
            # inventory-based validation settings.
            orthography = old_models.Orthography(
                name='Test Orthography',
                orthography='o,O',
                lowercase=True,
                initial_glottal_stops=True
            )
            dbsession.add(orthography)
            transaction.commit()
            application_settings = omb.generate_default_application_settings()
            application_settings.orthographic_validation = 'Error'
            application_settings.narrow_phonetic_inventory = 'n,p,N,P'
            application_settings.narrow_phonetic_validation = 'Error'
            application_settings.broad_phonetic_inventory = 'b,p,B,P'
            application_settings.broad_phonetic_validation = 'Error'
            application_settings.morpheme_break_is_orthographic = False
            application_settings.morpheme_break_validation = 'Error'
            application_settings.phonemic_inventory = 'p,i,P,I'
            application_settings.storage_orthography = db.get_orthographies()[0]
            dbsession.add(application_settings)
            transaction.commit()

            extra_environ = self.extra_environ_admin.copy()

            # Create a form with all invalid transcriptions.
            params = self.form_create_params.copy()
            params.update({
                'narrow_phonetic_transcription':
                    'test narrow phonetic transcription validation',
                'phonetic_transcription':
                    'test broad phonetic transcription validation',
                'transcription':
                    'test orthographic transcription validation',
                'morpheme_break': 'test morpheme break validation',
                'translations': [{
                    'transcription': 'test validation translation',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ, status=400)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert ('The orthographic transcription you have entered is not'
                    ' valid' in resp['errors']['transcription'])
            assert ('The broad phonetic transcription you have entered is not'
                    ' valid' in resp['errors']['phonetic_transcription'])
            assert ('The narrow phonetic transcription you have entered is not'
                    ' valid' in resp['errors']['narrow_phonetic_transcription'])
            assert ('The morpheme segmentation you have entered is not valid'
                    in resp['errors']['morpheme_break'])
            assert 'phonemic inventory' in resp['errors']['morpheme_break']
            assert form_count == 0

            # Create a form with some invalid and some valid transcriptions.
            params = self.form_create_params.copy()
            params.update({
                # Now it's valid
                'narrow_phonetic_transcription': 'np NP n P N p',
                'phonetic_transcription':
                    'test broad phonetic transcription validation',
                'transcription': '',
                'morpheme_break': 'test morpheme break validation',
                'translations': [{
                    'transcription': 'test validation translation',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ, status=400)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            pprint.pprint(resp)
            assert ('The broad phonetic transcription you have entered is not'
                    ' valid' in resp['errors']['phonetic_transcription'])
            assert 'narrow_phonetic_transcription' not in resp
            assert ('The morpheme segmentation you have entered is not valid'
                    in resp['errors']['morpheme_break'])
            assert form_count == 0

            # Now change the validation settings to make some transcriptions
            # valid.
            application_settings = omb.generate_default_application_settings()
            application_settings.orthographic_validation = 'Warning'
            application_settings.narrow_phonetic_inventory = 'n,p,N,P'
            application_settings.narrow_phonetic_validation = 'Error'
            application_settings.broad_phonetic_inventory = 'b,p,B,P'
            application_settings.broad_phonetic_validation = 'None'
            application_settings.morpheme_break_is_orthographic = True
            application_settings.morpheme_break_validation = 'Error'
            application_settings.phonemic_inventory = 'p,i,P,I'
            application_settings.storage_orthography = db.get_orthographies()[0]
            dbsession.add(application_settings)
            transaction.commit()
            params = self.form_create_params.copy()
            params.update({
                'narrow_phonetic_transcription':
                    'test narrow phonetic transcription validation',
                'phonetic_transcription':
                    'test broad phonetic transcription validation',
                'transcription':
                    'test orthographic transcription validation',
                'morpheme_break': 'test morpheme break validation',
                'translations': [{
                    'transcription': 'test validation translation',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ, status=400)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert 'transcription' not in resp['errors']
            assert 'phonetic_transcription' not in resp['errors']
            assert ('The narrow phonetic transcription you have entered is not'
                    ' valid' in resp['errors']['narrow_phonetic_transcription'])
            assert ('The morpheme segmentation you have entered is not valid'
                    in resp['errors']['morpheme_break'])
            assert form_count == 0

            # Now perform a successful create by making the narrow phonetic and
            # morpheme break fields valid according to the relevant inventories.
            params = self.form_create_params.copy()
            params.update({
                'narrow_phonetic_transcription':
                    'n p NP N P NNNN pPPP pnNpP   ',
                'phonetic_transcription':
                    'test broad phonetic transcription validation',
                'transcription':
                    'test orthographic transcription validation',
                'morpheme_break': 'OOO ooo OOO   o',
                'translations': [{
                    'transcription': 'test validation translation',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert 'errors' not in resp
            assert form_count == 1

            # Create a foreign word form (i.e., one tagged with a foreign word
            # tag). Such forms should be able to violate the inventory-based
            # validation restrictions. We need to ensure that
            # update_application_settings_if_form_is_foreign_word is updating
            # the application settings' Inventory objects with the foreign word.
            retain_extra_environ = extra_environ.copy()
            foreign_word_tag = omb.generate_foreign_word_tag()
            dbsession.add(foreign_word_tag)
            transaction.commit()
            params = self.form_create_params.copy()
            params.update({
                'narrow_phonetic_transcription': 'f`ore_n',
                'phonetic_transcription': 'foren',
                'transcription': 'foreign',
                'morpheme_break': 'foreign',
                'translations': [{
                    'transcription': 'foreign translation',
                    'grammaticality': ''
                }],
                'tags': [db.get_foreign_word_tag().id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     retain_extra_environ)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            #application_settings = response.g.application_settings
            application_settings = db.current_app_set
            assert ('f`ore_n' in
                    application_settings.get_transcription_inventory(
                        'narrow_phonetic', db).input_list)
            assert ('foren' in
                    application_settings.get_transcription_inventory(
                        'broad_phonetic', db).input_list)
            assert ('foreign' in
                    application_settings.get_transcription_inventory(
                        'morpheme_break', db).input_list)
            assert ('foreign' in
                    application_settings.get_transcription_inventory(
                        'orthographic', db).input_list)
            assert 'errors' not in resp
            assert form_count == 2

            # Now create a form that would violate inventory-based validation
            # rules but is nevertheless accepted because the violations are
            # foreign words.
            params = self.form_create_params.copy()
            params.update({
                'narrow_phonetic_transcription': 'n f`ore_np',
                'phonetic_transcription': 'b p',
                'transcription': 'o O',
                'morpheme_break': 'o-foreign-O',
                'translations': [{
                    'transcription': 'sentence containing foreign word',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert 'errors' not in resp
            assert form_count == 3

    def test_relational_attribute_creation(self):
        """Tests that POST/PUT create and update many-to-many data correctly."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)
            form_count = dbsession.query(old_models.Form).count()

            # Add an empty application settings and two syntactic categories.
            restricted_tag = omb.generate_restricted_tag()
            restricted_tag_name = restricted_tag.name
            foreign_word_tag = omb.generate_foreign_word_tag()
            foreign_word_tag_name = foreign_word_tag.name
            file1_name = 'test_relational_file'
            file2_name = 'test_relational_file_2'
            file1 = omb.generate_default_file()
            file1.name = file1_name
            file2 = omb.generate_default_file()
            file2.name = file2_name
            dbsession.add_all([restricted_tag, foreign_word_tag,
                               file1, file2])
            transaction.commit()

            # Create a form with some files and tags.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test relational transcription',
                'translations': [{
                    'transcription': 'test relational translation',
                    'grammaticality': ''
                }],
                'tags': [t.id for t in db.get_tags()],
                'files': [f.id for f in db.get_files()]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            new_form_count = dbsession.query(old_models.Form).count()
            resp = response.json_body
            form_files = dbsession.query(FormFile)
            created_form_id = resp['id']
            assert new_form_count == form_count + 1
            assert len([ff.form_id for ff in form_files
                        if ff.form_id == resp['id']]) == 2
            assert file1_name in [f['name'] for f in resp['files']]
            assert file2_name in [f['name'] for f in resp['files']]
            assert restricted_tag_name in [t['name'] for t in resp['tags']]

            # Attempt to update the form we just created but don't change the
            # tags. Expect the update attempt to fail.
            tags = [t.id for t in db.get_tags()]
            tags.reverse()
            files = [f.id for f in db.get_files()]
            files.reverse()
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test relational transcription',
                'translations': [{
                    'transcription': 'test relational translation',
                    'grammaticality': ''
                }],
                'tags': tags,
                'files': files
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=created_form_id), params,
                                    self.json_headers,
                                    self.extra_environ_admin, status=400)
            resp = response.json_body
            assert (resp['error'] == 'The update request failed because the'
                    ' submitted data were not new.')

            # Now update by removing one of the files and expect success.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test relational transcription',
                'translations': [{
                    'transcription': 'test relational translation',
                    'grammaticality': ''
                }],
                'tags': tags,
                'files': files[0:1]
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=created_form_id), params,
                                    self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            form_count = new_form_count
            new_form_count = dbsession.query(old_models.Form).count()
            assert new_form_count == form_count
            assert len(resp['files']) == 1
            assert restricted_tag_name in [t['name'] for t in resp['tags']]
            assert foreign_word_tag_name in [t['name'] for t in resp['tags']]

            # Attempt to create a form with some *invalid* files and tags and
            # fail.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test relational transcription invalid',
                'translations': [{
                    'transcription': 'test relational translation invalid',
                    'grammaticality': ''
                }],
                'tags': [1000, 9875, 'abcdef'],
                'files': [44, '1t']
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin, status=400)
            form_count = new_form_count
            new_form_count = dbsession.query(old_models.Form).count()
            resp = response.json_body
            assert new_form_count == form_count
            assert 'Please enter an integer value' in resp['errors']['files']
            assert 'There is no file with id 44.' in resp['errors']['files']
            assert 'There is no tag with id 1000.' in resp['errors']['tags']
            assert 'There is no tag with id 9875.' in resp['errors']['tags']
            assert 'Please enter an integer value' in resp['errors']['tags']

    def test_relational_restrictions(self):
        """Tests that the restricted tag works correctly with respect to
        relational attributes of forms.

        That is, tests that (a) form.files does not return restricted files to
        restricted users and (b) a restricted user cannot append a restricted
        form to file.forms.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            admin = self.extra_environ_admin.copy()
            contrib = self.extra_environ_contrib.copy()

            # Create a test form.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test',
                'translations': [{
                    'transcription': 'test_create_translation',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     admin)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert resp['transcription'] == 'test'
            assert form_count == 1

            # Now create the restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            dbsession.add(restricted_tag)
            dbsession.flush()
            restricted_tag_id = restricted_tag.id
            transaction.commit()

            # Then create two files, one restricted and one not.
            wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
            wav_file_base64 = encodestring(open(wav_file_path, 'rb').read())\
                .decode('utf8')

            params = self.file_create_params.copy()
            params.update({
                'filename': 'restricted_file.wav',
                'base64_encoded_file': wav_file_base64,
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params,
                                     self.json_headers, admin)
            resp = response.json_body
            restricted_file_id = resp['id']

            params = self.file_create_params.copy()
            params.update({
                'filename': 'unrestricted_file.wav',
                'base64_encoded_file': wav_file_base64
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params,
                                     self.json_headers, admin)
            resp = response.json_body
            unrestricted_file_id = resp['id']

            # Now, as a (restricted) contributor, attempt to create a form and
            # associate it to a restricted file -- expect to fail.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test',
                'translations': [{
                    'transcription': 'test_create_translation',
                    'grammaticality': ''
                }],
                'files': [restricted_file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     contrib, status=400)
            resp = response.json_body
            assert ('You are not authorized to access the file with id %d.' %
                restricted_file_id in resp['errors']['files'])

            # Now, as a (restricted) contributor, attempt to create a form and
            # associate it to an unrestricted file -- expect to succeed.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test',
                'translations': [{
                    'transcription': 'test_create_translation',
                    'grammaticality': ''
                }],
                'files': [unrestricted_file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     contrib)
            resp = response.json_body
            unrestricted_form_id = resp['id']
            assert resp['transcription'] == 'test'
            assert resp['files'][0]['name'] == 'unrestricted_file.wav'

            # Now, as a(n unrestricted) administrator, attempt to create a form
            # and associate it to a restricted file -- expect (a) to succeed
            # and (b) to find that the form is now restricted.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test',
                'translations': [{
                    'transcription': 'test_create_translation',
                    'grammaticality': ''
                }],
                'files': [restricted_file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     admin)
            resp = response.json_body
            indirectly_restricted_form_id = resp['id']
            assert resp['transcription'] == 'test'
            assert resp['files'][0]['name'] == 'restricted_file.wav'
            assert 'restricted' in [t['name'] for t in resp['tags']]

            # Now show that the indirectly restricted forms are inaccessible to
            # unrestricted users.
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=contrib)
            resp = response.json_body
            assert indirectly_restricted_form_id not in [f['id'] for f in resp]

            # Now, as a(n unrestricted) administrator, create a form.
            unrestricted_form_params = self.form_create_params.copy()
            unrestricted_form_params.update({
                'transcription': 'test',
                'translations': [{
                    'transcription': 'test_create_translation',
                    'grammaticality': ''
                }]
            })
            params = json.dumps(unrestricted_form_params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     admin)
            resp = response.json_body
            unrestricted_form_id = resp['id']
            assert resp['transcription'] == 'test'

            # As a restricted contributor, attempt to update the unrestricted
            # form just created by associating it to a restricted file --
            # expect to fail.
            unrestricted_form_params.update({'files': [restricted_file_id]})
            params = json.dumps(unrestricted_form_params)
            response = self.app.put(url('update', id=unrestricted_form_id),
                                    params, self.json_headers, contrib,
                                    status=400)
            resp = response.json_body
            assert ('You are not authorized to access the file with id %d.' %
                    restricted_file_id in resp['errors']['files'])

            # As an unrestricted administrator, attempt to update an
            # unrestricted form by associating it to a restricted file --
            # expect to succeed.
            response = self.app.put(url('update', id=unrestricted_form_id),
                                    params, self.json_headers, admin)
            resp = response.json_body
            assert resp['id'] == unrestricted_form_id
            assert 'restricted' in [t['name'] for t in resp['tags']]

            # Now show that the newly indirectly restricted form is also
            # inaccessible to an unrestricted user.
            response = self.app.get(url('show', id=unrestricted_form_id),
                                    headers=self.json_headers,
                                    extra_environ=contrib, status=403)
            resp = response.json_body
            assert response.content_type == 'application/json'
            assert (resp['error'] == 'You are not authorized to access this'
                    ' resource.')

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

            # Unauthorized user ('viewer') should return a 403 status code on
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
            n_syncat = omb.generate_n_syntactic_category()
            num_syncat = omb.generate_num_syntactic_category()
            s_syncat = omb.generate_s_syntactic_category()
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([application_settings, elicitation_method,
                               foreign_word_tag, restricted_tag, n_syncat, num_syncat, s_syncat,
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

    def test_update(self):
        """Tests that PUT /forms/id correctly updates an existing form."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            form_count = dbsession.query(old_models.Form).count()

            # Add the default application settings and the restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            application_settings = omb.generate_default_application_settings()
            dbsession.add_all([application_settings, restricted_tag])
            transaction.commit()
            restricted_tag = db.get_restricted_tag()

            # Create a form to update.
            params = self.form_create_params.copy()
            original_transcription = 'test_update_transcription'
            original_translation = 'test_update_translation'
            params.update({
                'transcription': original_transcription,
                'translations': [{
                    'transcription': original_translation,
                    'grammaticality': ''
                }],
                'tags': [restricted_tag.id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            id_ = int(resp['id'])
            new_form_count = dbsession.query(old_models.Form).count()
            datetime_modified = resp['datetime_modified']
            assert resp['transcription'] == original_transcription
            assert (resp['translations'][0]['transcription'] ==
                    original_translation)
            assert new_form_count == form_count + 1

            # As a viewer, attempt to update the restricted form we just
            # created. Expect to fail.
            extra_environ = {'test.authentication.role': 'viewer'}
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Updated!',
                'translations': [{
                    'transcription': 'test_update_translation',
                    'grammaticality': ''
                }],
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=id_), params,
                                    self.json_headers, extra_environ,
                                    status=403)
            resp = response.json_body
            assert (resp['error'] == 'You are not authorized to access this'
                    ' resource.')

            # As an administrator now, update the form just created and expect
            # to succeed.
            orig_backup_count = dbsession.query(old_models.FormBackup).count()
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Updated!',
                'translations': [{
                    'transcription': 'test_update_translation',
                    'grammaticality': ''
                }],
                'morpheme_break': 'a-b',
                'morpheme_gloss': 'c-d',
                'status': 'requires testing'
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=id_), params,
                                    self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            new_form_count = dbsession.query(old_models.Form).count()
            new_backup_count = dbsession.query(old_models.FormBackup).count()
            morpheme_break_ids_of_word = resp['morpheme_break_ids']
            assert resp['transcription'] == 'Updated!'
            assert (resp['translations'][0]['transcription'] ==
                    'test_update_translation')
            assert resp['morpheme_break'] == 'a-b'
            assert resp['morpheme_gloss'] == 'c-d'
            assert resp['morpheme_break_ids'] == [[[], []]]
            assert resp['morpheme_gloss_ids'] == [[[], []]]
            assert resp['status'] == 'requires testing'
            assert new_form_count == form_count + 1
            assert orig_backup_count + 1 == new_backup_count
            backup = dbsession.query(old_models.FormBackup).filter(
                old_models.FormBackup.UUID==resp['UUID']).order_by(
                desc(old_models.FormBackup.id)).first()
            assert datetime_modified.startswith(
                backup.datetime_modified.isoformat())
            assert backup.transcription == original_transcription
            assert response.content_type == 'application/json'

            # Attempt an update with no new data. Expect a 400 error
            # and response['errors'] = {'no change': The update request failed
            # because the submitted data were not new.'}.
            orig_backup_count = dbsession.query(old_models.FormBackup).count()
            response = self.app.put(url('update', id=id_), params,
                                    self.json_headers,
                                    self.extra_environ_admin, status=400)
            new_backup_count = dbsession.query(old_models.FormBackup).count()
            resp = response.json_body
            assert orig_backup_count == new_backup_count
            assert 'the submitted data were not new' in resp['error']

            # Now create a lexical form matching one of the
            # morpheme-form/morpheme-gloss pairs in the above form. The call
            # to update_forms_containing_this_form_as_morpheme in the create
            # action will cause the morpheme_break_ids and morpheme_gloss_ids
            # attributes of the phrasal form to change.
            orig_backup_count = dbsession.query(old_models.FormBackup).count()
            updated_word = dbsession.query(old_models.Form).get(id_)
            assert (json.loads(updated_word.morpheme_break_ids) ==
                    morpheme_break_ids_of_word)
            new_params = self.form_create_params.copy()
            new_params.update({
                'transcription': 'a',
                'translations': [{
                    'transcription': 'lexical',
                    'grammaticality': ''
                }],
                'morpheme_break': 'a',
                'morpheme_gloss': 'c'
            })
            new_params = json.dumps(new_params)
            response = self.app.post(url('create'), new_params,
                                     self.json_headers,
                                     self.extra_environ_admin)
            updated_word = dbsession.query(old_models.Form).get(id_)
            new_morpheme_break_ids_of_word = json.loads(
                updated_word.morpheme_break_ids)
            new_morpheme_gloss_ids_of_word = json.loads(
                updated_word.morpheme_gloss_ids)
            new_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_morpheme_break_ids_of_word != morpheme_break_ids_of_word
            assert orig_backup_count + 1 == new_backup_count
            assert new_morpheme_break_ids_of_word[0][0][0][1] == 'c'
            assert new_morpheme_break_ids_of_word[0][0][0][2] == None
            assert new_morpheme_gloss_ids_of_word[0][0][0][1] == 'a'
            assert new_morpheme_gloss_ids_of_word[0][0][0][2] == None

            # A vacuous update on the word will fail since the updating was
            # accomplished via the creation of the a/c morpheme.
            response = self.app.put(url('update', id=id_), params,
                                    self.json_headers,
                                    self.extra_environ_admin, status=400)
            resp = response.json_body
            assert 'the submitted data were not new' in resp['error']

            # Again update our form, this time making it into a foreign word.
            # Updating a form into a foreign word should update the Inventory
            # objects in app_globals.
            # First we create an application settings with some VERY STRICT
            # inventory-based validation settings. Also we add a foreign word
            # tag.
            orthography = old_models.Orthography(
                name='Test Orthography',
                orthography='o,O',
                lowercase=True,
                initial_glottal_stops=True
            )
            dbsession.add(orthography)
            transaction.commit()
            application_settings = omb.generate_default_application_settings()
            application_settings.orthographic_validation = 'Error'
            application_settings.narrow_phonetic_inventory = 'n,p,N,P'
            application_settings.narrow_phonetic_validation = 'Error'
            application_settings.broad_phonetic_inventory = 'b,p,B,P'
            application_settings.broad_phonetic_validation = 'Error'
            application_settings.morpheme_break_is_orthographic = False
            application_settings.morpheme_break_validation = 'Error'
            application_settings.phonemic_inventory = 'p,i,P,I'
            application_settings.storage_orthography = db.get_orthographies()[0]
            foreign_word_tag = omb.generate_foreign_word_tag()
            dbsession.add_all([application_settings, foreign_word_tag])
            transaction.commit()

            extra_environ = self.extra_environ_admin.copy()
            # Now we update using the same params as before, only this time we
            # tag as a foreign word.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Updated!',
                'translations': [{
                    'transcription': 'test_update_translation',
                    'grammaticality': ''
                }],
                'tags': [db.get_foreign_word_tag().id],
                'morpheme_break': 'a-b',
                'morpheme_gloss': 'c-d'
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=id_), params,
                                    self.json_headers, extra_environ)
            resp = response.json_body
            application_settings = db.current_app_set
            # This is how we know that
            # update_application_settings_if_form_is_foreign_word is working
            assert ('a-b' in
                    application_settings.get_transcription_inventory(
                        'morpheme_break', db).input_list)
            assert ('Updated!' in
                    application_settings.get_transcription_inventory(
                        'orthographic', db).input_list)
            assert 'errors' not in resp

            # Now update our form by adding a many-to-one datum, viz. a speaker
            speaker = omb.generate_default_speaker()
            dbsession.add(speaker)
            transaction.commit()
            speaker = db.get_speakers()[0]
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'oO',
                'translations': [{
                    'transcription': 'Updated again translation',
                    'grammaticality': ''
                }],
                'speaker': speaker.id,
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=id_), params,
                                    self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert resp['speaker']['first_name'] == speaker.first_name

    def test_delete(self):
        """Tests that DELETE /forms/id deletes the form with id=id and returns
        a JSON representation.

        If the id is invalid or unspecified, then JSON null or a 404 status code
        are returned, respectively.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            original_contributor_id = dbsession.query(old_models.User).filter(
                old_models.User.role=='contributor').first().id
            # Add some objects to the db: a default application settings, a
            # speaker, a tag, a file ...
            application_settings = omb.generate_default_application_settings()
            speaker = omb.generate_default_speaker()
            my_contributor = omb.generate_default_user()
            my_contributor.username = 'uniqueusername'
            tag = old_models.Tag()
            tag.name = 'default tag'
            file = omb.generate_default_file()
            dbsession.add_all([application_settings, speaker, my_contributor,
                               tag, file])
            dbsession.flush()
            my_contributor_id = my_contributor.id
            my_contributor_first_name = my_contributor.first_name
            tag_id = tag.id
            file_id = file.id
            speaker_first_name = speaker.first_name
            speaker_id = speaker.id
            transaction.commit()
            my_contributor = dbsession.query(old_models.User).filter(
                old_models.User.username=='uniqueusername').first()

            # Count the original number of forms and form_backups.
            form_count = dbsession.query(old_models.Form).count()
            form_backup_count = dbsession.query(old_models.FormBackup).count()

            # First, as my_contributor, create a form to delete.
            extra_environ = {'test.authentication.id': my_contributor_id}
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test_delete_transcription',
                'translations': [{
                    'transcription': 'test_delete_translation',
                    'grammaticality': ''
                }],
                'speaker': str(speaker_id),
                'tags': [tag_id],
                'files': [file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ)
            resp = response.json_body
            to_delete_id = resp['id']
            assert resp['transcription'] == 'test_delete_transcription'
            assert (resp['translations'][0]['transcription'] ==
                    'test_delete_translation')
            assert resp['tags'][0]['name'] == 'default tag'
            assert resp['files'][0]['name'] == 'test_file_name'

            # Query the Translation from the db and expect it to be present.
            translation = dbsession.query(old_models.Translation).get(
                resp['translations'][0]['id'])
            assert translation.transcription == 'test_delete_translation'

            # Now count the forms and form_backups.
            new_form_count = dbsession.query(old_models.Form).count()
            new_form_backup_count = dbsession.query(
                old_models.FormBackup).count()
            assert new_form_count == form_count + 1
            assert new_form_backup_count == form_backup_count

            # Now, as the default contributor, attempt to delete the
            # my_contributor-entered form we just created and expect to fail.
            extra_environ = {'test.authentication.id': original_contributor_id}
            response = self.app.delete(url('delete', id=to_delete_id),
                                       extra_environ=extra_environ, status=403)
            resp = response.json_body
            assert (resp['error'] == 'You are not authorized to access this'
                    ' resource.')

            # As my_contributor, attempt to delete the form we just created and
            # expect to succeed. Show that translations get deleted when forms
            # do but many-to-many relations (e.g., tags and files) and
            # many-to-one relations (e.g., speakers) do not.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.delete(url('delete', id=to_delete_id),
                                    extra_environ=extra_environ)
            resp = response.json_body
            new_form_count = dbsession.query(old_models.Form).count()
            new_form_backup_count = dbsession.query(
                old_models.FormBackup).count()
            translation_of_deleted_form = dbsession.query(
                old_models.Translation).get(resp['translations'][0]['id'])
            tag_of_deleted_form = dbsession.query(old_models.Tag).get(
                resp['tags'][0]['id'])
            file_of_deleted_form = dbsession.query(old_models.File).get(
                resp['files'][0]['id'])
            speaker_of_deleted_form = dbsession.query(old_models.Speaker).get(
                resp['speaker']['id'])
            assert translation_of_deleted_form is None
            assert isinstance(tag_of_deleted_form, old_models.Tag)
            assert isinstance(file_of_deleted_form, old_models.File)
            assert isinstance(speaker_of_deleted_form, old_models.Speaker)
            assert new_form_count == form_count
            assert new_form_backup_count == form_backup_count + 1
            assert response.content_type == 'application/json'

            # The deleted form will be returned to us, so the assertions from
            # above should still hold true.
            assert resp['transcription'] == 'test_delete_transcription'
            assert (resp['translations'][0]['transcription'] ==
                    'test_delete_translation')

            # Trying to get the deleted form from the db should return None
            deleted_form = dbsession.query(old_models.Form).get(to_delete_id)
            assert deleted_form == None

            # The backed up form should have the deleted form's attributes
            backed_up_form = dbsession.query(old_models.FormBackup).filter(
                old_models.FormBackup.UUID==resp['UUID']).first()
            assert backed_up_form.transcription == resp['transcription']
            modifier = json.loads(backed_up_form.modifier)
            assert modifier['first_name'] == my_contributor_first_name
            backed_up_speaker = json.loads(backed_up_form.speaker)
            assert backed_up_speaker['first_name'] == speaker_first_name
            assert (backed_up_form.datetime_entered.isoformat() ==
                    resp['datetime_entered'])
            assert backed_up_form.UUID == resp['UUID']

            # Delete with an invalid id
            id = 9999999999999
            response = self.app.delete(
                url('delete', id=id), headers=self.json_headers,
                extra_environ=self.extra_environ_admin, status=404)
            assert response.content_type == 'application/json'
            assert ('There is no form with id %s' % id in
                    response.json_body[ 'error'])

            # Delete without an id
            response = self.app.delete(
                url('delete', id=''), status=404, headers=self.json_headers,
                extra_environ=self.extra_environ_admin)
            assert (response.json_body['error'] == 'The resource could not be'
                    ' found.')

    def test_delete_foreign_word(self):
        """Tests that DELETE /forms/id on a foreign word updates the global
        Inventory objects correctly.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First create an application settings with some VERY STRICT
            # inventory-based validation settings and a foreign word tag.
            orthography = old_models.Orthography()
            orthography.name = 'Test Orthography'
            orthography.orthography = 'o,O'
            orthography.lowercase = True
            orthography.initial_glottal_stops = True
            dbsession.add(orthography)
            transaction.commit()
            application_settings = omb.generate_default_application_settings()
            application_settings.orthographic_validation = 'Error'
            application_settings.narrow_phonetic_inventory = 'n,p,N,P'
            application_settings.narrow_phonetic_validation = 'Error'
            application_settings.broad_phonetic_inventory = 'b,p,B,P'
            application_settings.broad_phonetic_validation = 'Error'
            application_settings.morpheme_break_is_orthographic = False
            application_settings.morpheme_break_validation = 'Error'
            application_settings.phonemic_inventory = 'p,i,P,I'
            application_settings.storage_orthography = db.get_orthographies()[0]
            foreign_word_tag = omb.generate_foreign_word_tag()
            dbsession.add_all([application_settings, foreign_word_tag])
            transaction.commit()

            # The extra_environ request param causes app_globals.application_settings to be set to
            # an h.ApplicationSettings instance that has our old_models.ApplicationSettings
            # instance as an attribute.  We do this with some special keys in environ.
            # We need to ensure that update_application_settings_if_form_is_foreign_word
            # is updating the global Inventory objects with the foreign word.
            # The key 'test.application_settings' in the environ causes application
            # settings to be deleted from app_globals after each request; to prevent
            # this we pass in 'test.retain_application_settings' also.
            extra_environ = self.extra_environ_admin.copy()
            extra_environ['test.application_settings'] = True
            extra_environ['test.retain_application_settings'] = True

            # Then create a foreign word form to delete.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test_delete_transcription',
                'translations': [{'transcription': 'test_delete_translation', 'grammaticality': ''}],
                'tags': [db.get_foreign_word_tag().id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)
            resp = response.json_body

            application_settings = db.current_app_set
            assert ('test_delete_transcription' in
                    application_settings.get_transcription_inventory(
                        'orthographic', db).input_list)
            assert resp['transcription'] == 'test_delete_transcription'
            assert resp['translations'][0]['transcription'] == 'test_delete_translation'

            # Delete the form we just created and observe that the orthographic
            # transcription has been removed from the orthographic_inventory object.
            response = self.app.delete(url('delete', id=resp['id']),
                                    extra_environ=extra_environ)
            resp = response.json_body
            # We have to re-create a new ``DBUtils`` object because the
            # existing one caches _foreign_word_transcriptions
            db = DBUtils(dbsession, self.settings)
            application_settings = db.get_current_app_set()
            assert ('test_delete_transcription' not in
                    application_settings.get_transcription_inventory(
                        'orthographic', db).input_list)

    def test_show(self):
        """Tests that GET /forms/id returns a JSON form object, null or 404
        depending on whether the id is valid, invalid or unspecified,
        respectively.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First add a form.
            form = omb.generate_default_form()
            dbsession.add(form)
            transaction.commit()
            form_id = db.get_forms()[0].id

            # Invalid id
            id = 100000000000
            response = self.app.get(url('show', id=id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin,
                status=404)
            resp = response.json_body
            assert response.content_type == 'application/json'
            assert 'There is no form with id %s' % id in response.json_body[
                'error']

            # No id
            response = self.app.get(url('show', id=''), status=404,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == \
                'The resource could not be found.'

            # Valid id
            response = self.app.get(url('show', id=form_id), headers=self.json_headers,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['transcription'] == 'test transcription'
            assert resp['translations'][0]['transcription'] == 'test translation'
            assert response.content_type == 'application/json'

            # Now test that the restricted tag is working correctly.
            # First get the default contributor's id.
            users = db.get_users()
            contributor_id = [u for u in users if u.role == 'contributor'][0].id

            # Then add another contributor and a restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            my_contributor = omb.generate_default_user()
            my_contributor_first_name = 'Mycontributor'
            my_contributor.first_name = my_contributor_first_name
            my_contributor.username = 'uniqueusername'
            dbsession.add_all([restricted_tag, my_contributor])
            transaction.commit()
            my_contributor = dbsession.query(old_models.User).filter(
                old_models.User.first_name == my_contributor_first_name).first()
            my_contributor_id = my_contributor.id

            # Then add the default application settings with my_contributor as the
            # only unrestricted user.
            application_settings = omb.generate_default_application_settings()
            application_settings.unrestricted_users = [my_contributor]
            dbsession.add(application_settings)
            transaction.commit()
            # Finally, issue a POST request to create the restricted form with
            # the *default* contributor as the enterer.
            extra_environ = {'test.authentication.id': contributor_id,
                            'test.application_settings': True}
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test restricted tag transcription',
                'translations': [{'transcription': 'test restricted tag translation',
                            'grammaticality': ''}],
                'tags': [db.get_tags()[0].id]    # the restricted tag should be the only one
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            extra_environ)
            resp = response.json_body
            restricted_form_id = resp['id']
            # Expectation: the administrator, the default contributor (qua enterer)
            # and the unrestricted my_contributor should all be able to view the form.
            # The viewer should get a 403 error when attempting to view this form.
            # An administrator should be able to view this form.
            extra_environ = {'test.authentication.role': 'administrator',
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            # The default contributor (qua enterer) should be able to view this form.
            extra_environ = {'test.authentication.id': contributor_id,
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            # Mycontributor (an unrestricted user) should be able to view this
            # restricted form.
            extra_environ = {'test.authentication.id': my_contributor_id,
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            # A (not unrestricted) viewer should *not* be able to view this form.
            extra_environ = {'test.authentication.role': 'viewer',
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id),
                headers=self.json_headers, extra_environ=extra_environ, status=403)
            # Remove Mycontributor from the unrestricted users list and access will be denied.
            application_settings = db.current_app_set
            application_settings.unrestricted_users = []
            dbsession.add(application_settings)
            transaction.commit()
            # Mycontributor (no longer an unrestricted user) should now *not* be
            # able to view this restricted form.
            extra_environ = {'test.authentication.id': my_contributor_id,
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id),
                headers=self.json_headers, extra_environ=extra_environ, status=403)
            # Remove the restricted tag from the form and the viewer should now be
            # able to view it too.
            restricted_form = dbsession.query(old_models.Form).get(restricted_form_id)
            restricted_form.tags = []
            dbsession.add(restricted_form)
            transaction.commit()
            extra_environ = {'test.authentication.role': 'viewer',
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id),
                            headers=self.json_headers, extra_environ=extra_environ)

    def test_edit(self):
        """Tests that GET /forms/id/edit returns a JSON object of data
        necessary to edit the form with id=id.
        The JSON object is of the form {'form': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Add the default application settings and the restricted tag.
            application_settings = omb.generate_default_application_settings()
            restricted_tag = omb.generate_restricted_tag()
            dbsession.add_all([restricted_tag, application_settings])
            transaction.commit()
            restricted_tag = db.get_restricted_tag()
            # Create a restricted form.
            form = omb.generate_default_form()
            form.tags = [restricted_tag]
            dbsession.add(form)
            transaction.commit()
            restricted_form = db.get_forms()[0]
            restricted_form_id = restricted_form.id

            # As a (not unrestricted) contributor, attempt to call edit on the
            # restricted form and expect to fail.
            extra_environ = {'test.authentication.role': 'contributor'}
            response = self.app.get(url('edit', id=restricted_form_id),
                                    extra_environ=extra_environ, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'

            # Not logged in: expect 401 Unauthorized
            response = self.app.get(url('edit', id=restricted_form_id),
                                    status=401)

            resp = response.json_body
            assert response.content_type == 'application/json'
            assert resp['error'] == 'Authentication is required to access this resource.'

            # Invalid id
            id = 9876544
            response = self.app.get(url('edit', id=id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin,
                status=404)
            assert 'There is no form with id %s' % id in response.json_body[
                'error']

            # No id
            response = self.app.get(url('edit', id=''), status=404,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == \
                'The resource could not be found.'
            assert response.content_type == 'application/json'

            # Valid id
            response = self.app.get(url('edit', id=restricted_form_id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['form']['transcription'] == 'test transcription'
            assert resp['form']['translations'][0]['transcription'] == 'test translation'
            assert response.content_type == 'application/json'

            # Valid id with GET params.  Param values are treated as strings, not
            # JSON.  If any params are specified, the default is to return a JSON
            # array corresponding to store for the param.  There are three cases
            # that will result in an empty JSON array being returned:
            # 1. the param is not specified
            # 2. the value of the specified param is an empty string
            # 3. the value of the specified param is an ISO 8601 UTC datetime
            #    string that matches the most recent datetime_modified value of the
            #    store in question.

            # Add some test data to the database.
            application_settings = omb.generate_default_application_settings()
            elicitation_method = omb.generate_default_elicitation_method()
            foreign_word_tag = omb.generate_foreign_word_tag()
            N = omb.generate_n_syntactic_category()
            Num = omb.generate_num_syntactic_category()
            S = omb.generate_s_syntactic_category()
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([application_settings, elicitation_method,
                foreign_word_tag, N, Num, S, speaker, source])
            transaction.commit()

            # Get the data currently in the db (see websetup.py for the test data).
            data = {
                'grammaticalities': db.get_grammaticalities(),
                'elicitation_methods': db.get_mini_dicts_getter('ElicitationMethod')(),
                'tags': db.get_mini_dicts_getter('Tag')(),
                'syntactic_categories': db.get_mini_dicts_getter('SyntacticCategory')(),
                'speakers': db.get_mini_dicts_getter('Speaker')(),
                'users': db.get_mini_dicts_getter('User')(),
                'sources': db.get_mini_dicts_getter('Source')()
            }

            # JSON.stringify and then re-Python-ify the data.  This is what the data
            # should look like in the response to a simulated GET request.
            data = json.loads(json.dumps(data))

            params = {
                # Value is a non-empty string: 'grammaticalities' will be in response.
                'grammaticalities': 'give me some grammaticalities!',
                # Value is empty string: 'elicitation_methods' will not be in response.
                'elicitation_methods': '',
                # Value is ISO 8601 UTC datetime string that does not match the most
                # recent Source.datetime_modified value: 'sources' *will* be in
                # response.
                'sources': datetime.datetime.utcnow().isoformat(),
                # Value is ISO 8601 UTC datetime string that does match the most
                # recent User.datetime_modified value: 'users' will *not* be in response.
                'users': db.get_most_recent_modification_datetime('User').isoformat()
            }
            response = self.app.get(url('edit', id=restricted_form_id), params,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['data']['elicitation_methods'] == []
            assert resp['data']['tags'] == []
            assert resp['data']['grammaticalities'] == data['grammaticalities']
            assert resp['data']['syntactic_categories'] == []
            assert resp['data']['speakers'] == []
            assert resp['data']['users'] == []
            assert resp['data']['sources'] == data['sources']

            # Invalid id with GET params.  It should still return 'null'.
            params = {
                # If id were valid, this would cause a speakers array to be returned
                # also.
                'speakers': 'True',
            }
            response = self.app.get(url('edit', id=id), params,
                                extra_environ=self.extra_environ_admin, status=404)
            assert 'There is no form with id %s' % id in response.json_body[
                'error']

    def test_history(self):
        """Tests that GET /forms/id/history returns the form with id=id and its
        previous incarnations.
        The JSON object returned is of the form
        {'form': form, 'previous_versions': [...]}.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Add some test data to the database.
            application_settings = omb.generate_default_application_settings()
            elicitation_method = omb.generate_default_elicitation_method()
            source = omb.generate_default_source()
            restricted_tag = omb.generate_restricted_tag()
            foreign_word_tag = omb.generate_foreign_word_tag()
            file1 = omb.generate_default_file()
            file1.name = 'file1'
            file2 = omb.generate_default_file()
            file2.name = 'file2'
            N = omb.generate_n_syntactic_category()
            Num = omb.generate_num_syntactic_category()
            S = omb.generate_s_syntactic_category()
            speaker = omb.generate_default_speaker()
            dbsession.add_all([application_settings, elicitation_method, source,
                restricted_tag, foreign_word_tag, file1, file2, N, Num, S, speaker])
            transaction.commit()

            # Create a restricted form (via request) as the default contributor
            users = db.get_users()
            contributor_id = [u for u in users if u.role=='contributor'][0].id
            administrator_id = [u for u in users if u.role=='administrator'][0].id
            speaker_id = db.get_speakers()[0].id
            elicitation_method_id = db.get_elicitation_methods()[0].id
            syntactic_category_ids = [sc.id for sc in db.get_syntactic_categories()]
            first_syntactic_category_id = syntactic_category_ids[0]
            last_syntactic_category_id = syntactic_category_ids[-1]
            tag_ids = [t.id for t in db.get_tags()]
            file_ids = [f.id for f in db.get_files()]
            restricted_tag_id = db.get_restricted_tag().id

            extra_environ = {'test.authentication.role': 'contributor',
                            'test.application_settings': True}
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'created by the contributor',
                'translations': [{'transcription': 'created by the contributor', 'grammaticality': ''}],
                'elicitor': contributor_id,
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            extra_environ)
            form_count = dbsession.query(old_models.Form).count()
            resp = response.json_body
            form_id = resp['id']
            form_UUID = resp['UUID']
            assert form_count == 1

            # Update our form (via request) as the default administrator
            extra_environ = {'test.authentication.role': 'administrator',
                            'test.application_settings': True}
            params = self.form_create_params.copy()
            params.update({
                'grammaticality': '?',
                'transcription': 'updated by the administrator',
                'translations': [{'transcription': 'updated by the administrator',
                            'grammaticality': '*'}],
                'morpheme_break': 'up-dat-ed by the ad-ministr-ator',
                'morpheme_gloss': 'up-date-PAST PREP DET PREP-servant-AGT',
                'speaker': speaker_id,
                'elicitation_method': elicitation_method_id,
                'syntactic_category': first_syntactic_category_id,
                'verifier': administrator_id,
                'tags': tag_ids + [None, ''], # None and '' ('') will be ignored by forms.update_form
                'enterer': administrator_id  # This should change nothing.
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=form_id), params,
                            self.json_headers, extra_environ)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert form_count == 1

            # Finally, update our form (via request) as the default contributor.
            extra_environ = {'test.authentication.role': 'contributor',
                            'test.application_settings': True}
            params = self.form_create_params.copy()
            params.update({
                'grammaticality': '#',
                'transcription': 'updated by the contributor',
                'translations': [{'transcription': 'updated by the contributor',
                            'grammaticality': '*'}],
                'morpheme_break': 'up-dat-ed by the ad-ministr-ator',
                'morpheme_gloss': 'up-date-PAST PREP DET PREP-servant-AGT',
                'speaker': speaker_id,
                'elicitation_method': elicitation_method_id,
                'syntactic_category': last_syntactic_category_id,
                'tags': tag_ids,
                'files': file_ids
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=form_id), params,
                            self.json_headers, extra_environ)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            assert form_count == 1

            # Now get the history of this form.
            extra_environ = {'test.authentication.role': 'contributor',
                            'test.application_settings': True}
            response = self.app.get(
                url(controller='forms', action='history', id=form_id),
                headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert response.content_type == 'application/json'
            assert 'form' in resp
            assert 'previous_versions' in resp
            first_version = resp['previous_versions'][1]
            second_version = resp['previous_versions'][0]
            current_version = resp['form']
            assert first_version['transcription'] == 'created by the contributor'
            assert first_version['morpheme_break'] == ''
            assert first_version['elicitor']['id'] == contributor_id
            assert first_version['enterer']['id'] == contributor_id
            assert first_version['modifier']['id'] == contributor_id
            # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
            # so the test will fail/be inconsistent with <
            assert first_version['datetime_modified'] <= second_version['datetime_modified']
            assert first_version['speaker'] == None
            assert first_version['elicitation_method'] == None
            assert first_version['syntactic_category'] == None
            assert first_version['verifier'] == None
            assert [t['id'] for t in first_version['tags']] == [restricted_tag_id]
            assert first_version['files'] == []
            assert first_version['morpheme_break_ids'] == None

            assert second_version['transcription'] == 'updated by the administrator'
            assert second_version['morpheme_break'] == 'up-dat-ed by the ad-ministr-ator'
            assert second_version['elicitor'] == None
            assert second_version['enterer']['id'] == contributor_id
            assert second_version['modifier']['id'] == administrator_id
            assert second_version['datetime_modified'] <= current_version['datetime_modified']
            assert second_version['speaker']['id'] == speaker_id
            assert second_version['elicitation_method']['id'] == elicitation_method_id
            assert second_version['syntactic_category']['id'] == first_syntactic_category_id
            assert second_version['verifier']['id'] == administrator_id
            assert sorted([t['id'] for t in second_version['tags']]) == sorted(tag_ids)
            assert second_version['files'] == []
            assert len(second_version['morpheme_break_ids']) == 4

            assert current_version['transcription'] == 'updated by the contributor'
            assert current_version['morpheme_break'] == 'up-dat-ed by the ad-ministr-ator'
            assert current_version['elicitor'] == None
            assert current_version['enterer']['id'] == contributor_id
            assert current_version['modifier']['id'] == contributor_id
            assert current_version['speaker']['id'] == speaker_id
            assert current_version['elicitation_method']['id'] == elicitation_method_id
            assert current_version['syntactic_category']['id'] == last_syntactic_category_id
            assert current_version['verifier'] == None
            assert sorted([t['id'] for t in current_version['tags']]) == sorted(tag_ids)
            assert sorted([f['id'] for f in current_version['files']]) == sorted(file_ids)
            assert len(current_version['morpheme_break_ids']) == 4

            # Attempt to get the history of the just-entered restricted form as a
            # viewer and expect to fail with 403.
            extra_environ_viewer = {'test.authentication.role': 'viewer',
                            'test.application_settings': True}
            response = self.app.get(
                url(controller='forms', action='history', id=form_id),
                headers=self.json_headers, extra_environ=extra_environ_viewer,
                status=403)
            resp = response.json_body
            assert response.content_type == 'application/json'
            assert resp['error'] == 'You are not authorized to access this resource.'

            # Attempt to call history with an invalid id and an invalid UUID and
            # expect 404 errors in both cases.
            bad_id = 103
            bad_UUID = str(uuid4())
            response = self.app.get(
                url(controller='forms', action='history', id=bad_id),
                headers=self.json_headers, extra_environ=extra_environ,
                status=404)
            resp = response.json_body
            assert resp['error'] == 'No forms or form backups match %d' % bad_id
            response = self.app.get(
                url(controller='forms', action='history', id=bad_UUID),
                headers=self.json_headers, extra_environ=extra_environ,
                status=404)
            resp = response.json_body
            assert resp['error'] == 'No forms or form backups match %s' % bad_UUID

            # Now delete the form ...
            response = self.app.delete(url('delete', id=form_id),
                            headers=self.json_headers, extra_environ=extra_environ)

            # ... and get its history again, this time using the form's UUID
            response = self.app.get(
                url(controller='forms', action='history', id=form_UUID),
                headers=self.json_headers, extra_environ=extra_environ)
            by_UUID_resp = response.json_body
            assert by_UUID_resp['form'] == None
            assert len(by_UUID_resp['previous_versions']) == 3
            first_version = by_UUID_resp['previous_versions'][2]
            second_version = by_UUID_resp['previous_versions'][1]
            third_version = by_UUID_resp['previous_versions'][0]
            assert first_version['transcription'] == 'created by the contributor'
            assert first_version['morpheme_break'] == ''
            assert first_version['elicitor']['id'] == contributor_id
            assert first_version['enterer']['id'] == contributor_id
            assert first_version['modifier']['id'] == contributor_id
            # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
            # so the test will fail/be inconsistent with <
            assert first_version['datetime_modified'] <= second_version['datetime_modified']
            assert first_version['speaker'] == None
            assert first_version['elicitation_method'] == None
            assert first_version['syntactic_category'] == None
            assert first_version['verifier'] == None
            assert [t['id'] for t in first_version['tags']] == [restricted_tag_id]
            assert first_version['files'] == []
            assert first_version['morpheme_break_ids'] == None

            assert second_version['transcription'] == 'updated by the administrator'
            assert second_version['morpheme_break'] == 'up-dat-ed by the ad-ministr-ator'
            assert second_version['elicitor'] == None
            assert second_version['enterer']['id'] == contributor_id
            assert second_version['modifier']['id'] == administrator_id
            # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
            # so the test will fail/be inconsistent with <
            assert second_version['datetime_modified'] <= third_version['datetime_modified']
            assert second_version['speaker']['id'] == speaker_id
            assert second_version['elicitation_method']['id'] == elicitation_method_id
            assert second_version['syntactic_category']['id'] == first_syntactic_category_id
            assert second_version['verifier']['id'] == administrator_id
            assert sorted([t['id'] for t in second_version['tags']]) == sorted(tag_ids)
            assert second_version['files'] == []
            assert len(second_version['morpheme_break_ids']) == 4

            assert third_version['transcription'] == 'updated by the contributor'
            assert third_version['morpheme_break'] == 'up-dat-ed by the ad-ministr-ator'
            assert third_version['elicitor'] == None
            assert third_version['enterer']['id'] == contributor_id
            assert third_version['modifier']['id'] == contributor_id
            assert third_version['speaker']['id'] == speaker_id
            assert third_version['elicitation_method']['id'] == elicitation_method_id
            assert third_version['syntactic_category']['id'] == last_syntactic_category_id
            assert third_version['verifier'] == None
            assert sorted([t['id'] for t in third_version['tags']]) == sorted(tag_ids)
            assert sorted([f['id'] for f in third_version['files']]) == sorted(file_ids)
            assert len(third_version['morpheme_break_ids']) == 4

            # Get the deleted form's history again, this time using its id.  The 
            # response should be the same as the response received using the UUID.
            response = self.app.get(
                url(controller='forms', action='history', id=form_id),
                headers=self.json_headers, extra_environ=extra_environ)
            by_form_id_resp = response.json_body
            assert by_form_id_resp == by_UUID_resp

            # Create a new restricted form as an administrator.
            params = self.form_create_params.copy()
            params.update({
                'transcription': '2nd form restricted',
                'translations': [{'transcription': '2nd form restricted',
                            'grammaticality': ''}],
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            self.extra_environ_admin)
            resp = response.json_body
            form_count = dbsession.query(old_models.Form).count()
            form_id = resp['id']
            form_UUID = resp['UUID']
            assert form_count == 1

            # Update the just-created form by removing the restricted tag.
            params = self.form_create_params.copy()
            params.update({
                'transcription': '2nd form unrestricted',
                'translations': [{'transcription': '2nd form unrestricted', 'grammaticality': ''}],
                'tags': []
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=form_id), params,
                            self.json_headers, self.extra_environ_admin)
            resp = response.json_body

            # Now update it in another way.
            params = self.form_create_params.copy()
            params.update({
                'transcription': '2nd form unrestricted updated',
                'translations': [{'transcription': '2nd form unrestricted updated',
                            'grammaticality': ''}],
                'tags': []
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=form_id), params,
                            self.json_headers, self.extra_environ_admin)
            resp = response.json_body

            # Get the history of the just-entered restricted form as a
            # contributor and expect to receive only the '2nd form' version in the
            # previous_versions.
            response = self.app.get(
                url(controller='forms', action='history', id=form_id),
                headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp['previous_versions']) == 1
            assert resp['previous_versions'][0]['transcription'] == \
                '2nd form unrestricted'
            assert resp['form']['transcription'] == '2nd form unrestricted updated'

            # Now get the history of the just-entered restricted form as an
            # administrator and expect to receive both backups.
            response = self.app.get(
                url(controller='forms', action='history', id=form_id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp['previous_versions']) == 2
            assert resp['previous_versions'][0]['transcription'] == \
                '2nd form unrestricted'
            assert resp['previous_versions'][1]['transcription'] == \
                '2nd form restricted'
            assert resp['form']['transcription'] == '2nd form unrestricted updated'

    def test_remember(self):
        """Tests that POST /forms/remember correctly saves the input list of
        forms to the logged in user's remembered_forms list.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First create three forms, and restrict the first one.
            restricted_tag = omb.generate_restricted_tag()
            form1 = omb.generate_default_form()
            form2 = omb.generate_default_form()
            form3 = omb.generate_default_form()
            form1.transcription = 'form1'
            form2.transcription = 'form2'
            form3.transcription = 'form3'
            dbsession.add_all([form1, form2, form3, restricted_tag])
            transaction.commit()
            restricted_tag = db.get_restricted_tag()
            form1.tags = [restricted_tag]
            dbsession.add(form1)
            transaction.commit()
            forms = db.get_forms()
            form_ids = [form.id for form in forms]
            form1_id = [f.id for f in forms if f.transcription == 'form1'][0]
            form_ids_set = set(form_ids)

            # Then try to remember all of these forms.  Send a JSON array of form
            # ids to remember and expect to get it back.
            administrator = dbsession.query(old_models.User).filter(old_models.User.role=='administrator').first()
            administrator_datetime_modified = administrator.datetime_modified
            sleep(1)
            params = json.dumps({'forms': form_ids})
            response = self.app.post(url(controller='forms', action='remember'),
                params, headers=self.json_headers,
                extra_environ=self.extra_environ_admin)
            resp = response.json_body
            administrator = dbsession.query(old_models.User).filter(old_models.User.role=='administrator').first()
            assert response.content_type == 'application/json'
            assert len(resp) == len(form_ids)
            assert form_ids_set == set(resp)
            assert administrator.datetime_modified != administrator_datetime_modified
            assert form_ids_set == set([f.id for f in administrator.remembered_forms])

            # A non-int-able form id in the input will result in a 400 error.
            bad_params = form_ids[:]
            bad_params.append('a')
            bad_params = json.dumps({'forms': bad_params})
            response = self.app.post(url(controller='forms', action='remember'),
                bad_params, headers=self.json_headers,
                extra_environ=self.extra_environ_admin, status=400)
            resp = response.json_body
            assert 'Please enter an integer value' in resp['errors']['forms']

            # One nonexistent form id will return a 400 error.
            bad_id = 1000
            bad_params = form_ids[:]
            bad_params.append(bad_id)
            bad_params = json.dumps({'forms': bad_params})
            response = self.app.post(url(controller='forms', action='remember'),
                bad_params, headers=self.json_headers,
                extra_environ=self.extra_environ_admin, status=400)
            resp = response.json_body
            assert 'There is no form with id %d.' % bad_id in resp['errors']['forms']

            # Bad JSON parameters will return its own 400 error.
            bad_JSON = '[%d, %d, %d' % tuple(form_ids)
            response = self.app.post(url(controller='forms', action='remember'),
                bad_JSON, headers=self.json_headers,
                extra_environ=self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['error'] == \
                'JSON decode error: the parameters provided were not valid JSON.'

            # An empty list ...
            empty_list = json.dumps([])
            response = self.app.post(url(controller='forms', action='remember'),
                empty_list, headers=self.json_headers,
                extra_environ=self.extra_environ_admin, status=404)
            resp = response.json_body
            assert resp['error'] == 'No valid form ids were provided.'

            # Re-issue the same remember request that succeeded previously.  Expect
            # user.remembered_forms to be unchanged (i.e., auto-duplicate removal)
            params = json.dumps({'forms': form_ids})
            response = self.app.post(url(controller='forms', action='remember'),
                params, headers=self.json_headers,
                extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp) == len(form_ids)
            assert form_ids_set == set(resp)
            administrator = dbsession.query(old_models.User).filter(
                old_models.User.role=='administrator').first()
            assert form_ids_set == set([f.id for f in administrator.remembered_forms])
            user_forms = dbsession.query(old_models.UserForm).filter(
                old_models.UserForm.user_id==administrator.id).all()
            assert len(user_forms) == len(form_ids)

            # Now again issue the same remember request that succeeded previously
            # but this time as a restricted user, a viewer.  Expect only 2 forms
            # returned.
            extra_environ_viewer = {'test.authentication.role': 'viewer'}
            params = json.dumps({'forms': form_ids})
            response = self.app.post(url(controller='forms', action='remember'),
                params, headers=self.json_headers,
                extra_environ=extra_environ_viewer)
            resp = response.json_body
            assert len(resp) == len(form_ids) - 1
            assert form1_id not in resp
            viewer = dbsession.query(old_models.User).filter(
                old_models.User.role=='viewer').first()
            assert len(resp) == len(viewer.remembered_forms)
            assert form1_id not in [f.id for id in viewer.remembered_forms]

            # Finally, request to remember only the restricted form as a viewer.
            # Expect a 403 error.
            params = json.dumps({'forms': [form1_id]})
            response = self.app.post(url(controller='forms', action='remember'),
                params, headers=self.json_headers,
                extra_environ=extra_environ_viewer, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'
            viewer = dbsession.query(old_models.User).filter(
                old_models.User.role=='viewer').first()
            assert len(viewer.remembered_forms) == 2
            assert form1_id not in [f.id for id in viewer.remembered_forms]

    def _test_update_morpheme_references(self):
        """Tests that GET /forms/update_morpheme_references correctly updates
        the morpheme references.
        *NOTE*: this test has been deactivated (by prefixation with '_') because
        the update_morpheme_references functionality has been made obsolete by
        the calls to update_forms_containing_this_form_as_morpheme in the create, update
        and delete actions. If reactivated, this test will fail as is.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First create a couple of syntactic categories and the application settings
            N = omb.generate_n_syntactic_category()
            Num = omb.generate_num_syntactic_category()
            application_settings = omb.generate_default_application_settings()
            dbsession.add_all([N, Num, application_settings])
            transaction.commit()
            NId = N.id
            NumId = Num.id

            extra_environ = {'test.authentication.role': 'administrator',
                                'test.application_settings': True}

            # Create two forms with morphological analyses.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'abc',
                'morpheme_break': 'a-b-c',
                'morpheme_gloss': '1-2-3',
                'translations': [{'transcription': '123', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'xyz',
                'morpheme_break': 'x-y-z',
                'morpheme_gloss': '7-8-9',
                'translations': [{'transcription': '789', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            # GET the forms and confirm that the morpheme_break_ids values are "empty"
            response = self.app.get(url('forms'), headers=self.json_headers,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp) == 2
            assert [f['morpheme_break_ids'] for f in resp] == [[[[], [], []]], [[[], [], []]]]
            assert [f['morpheme_gloss_ids'] for f in resp] == [[[[], [], []]], [[[], [], []]]]
            assert [f['syntactic_category_string'] for f in resp] == ['?-?-?', '?-?-?']

            # Request PUT /forms/update_morpheme_references and expect nothing to change
            response = self.app.put(url('/forms/update_morpheme_references'),
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            response = self.app.get(url('forms'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp2 = response.json_body
            assert [(f['id'], f['datetime_modified']) for f in resp] == \
                [(f['id'], f['datetime_modified']) for f in resp2]
            assert [f['morpheme_break_ids'] for f in resp2] == [[[[], [], []]], [[[], [], []]]]
            assert [f['morpheme_gloss_ids'] for f in resp2] == [[[[], [], []]], [[[], [], []]]]
            assert [f['syntactic_category_string'] for f in resp2] == ['?-?-?', '?-?-?']

            # Now add the implicit lexical items for the two forms just entered and
            # *then* call /forms/update_morpheme_references and expect a change
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'x',
                'morpheme_break': 'x',
                'morpheme_gloss': '7',
                'translations': [{'transcription': '7', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'y',
                'morpheme_break': 'y',
                'morpheme_gloss': '8',
                'translations': [{'transcription': '8', 'grammaticality': ''}],
                'syntactic_category': NId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'z',
                'morpheme_break': 'z',
                'morpheme_gloss': '9',
                'translations': [{'transcription': '9', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'a',
                'morpheme_break': 'a',
                'morpheme_gloss': '1',
                'translations': [{'transcription': '1', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'b',
                'morpheme_break': 'b',
                'morpheme_gloss': '2',
                'translations': [{'transcription': '2', 'grammaticality': ''}],
                'syntactic_category': NId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'c',
                'morpheme_break': 'c',
                'morpheme_gloss': '3',
                'translations': [{'transcription': '3', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)

            # Request PUT /forms/update_morpheme_references
            sleep(1)
            response = self.app.put(url('/forms/update_morpheme_references'),
                headers=self.json_headers, extra_environ=extra_environ)
            assert response.content_type == 'application/json'

            # Search for our two original morphologically complex forms
            json_query = json.dumps({'query': {'filter':
                ['Form', 'id', 'in', [f['id'] for f in resp]]}})
            response = self.app.post(url('/forms/search'), json_query,
                            self.json_headers, self.extra_environ_admin)

            resp3 = response.json_body
            assert [f['id'] for f in resp] == [f['id'] for f in resp2] == [f['id'] for f in resp3]
            assert [f['datetime_modified'] for f in resp3] != [f['datetime_modified'] for f in resp2]
            assert [f['datetime_modified'] for f in resp3] != [f['datetime_modified'] for f in resp]

            assert resp3[0]['morpheme_break_ids'][0][0][0][1] == '1'
            assert resp3[0]['morpheme_break_ids'][0][0][0][2] == 'Num'
            assert resp3[0]['morpheme_break_ids'][0][1][0][1] == '2'
            assert resp3[0]['morpheme_break_ids'][0][1][0][2] == 'N'
            assert resp3[0]['morpheme_break_ids'][0][2][0][1] == '3'
            assert resp3[0]['morpheme_break_ids'][0][2][0][2] == 'Num'
            assert resp3[0]['morpheme_gloss_ids'][0][0][0][1] == 'a'
            assert resp3[0]['morpheme_gloss_ids'][0][0][0][2] == 'Num'
            assert resp3[0]['morpheme_gloss_ids'][0][1][0][1] == 'b'
            assert resp3[0]['morpheme_gloss_ids'][0][1][0][2] == 'N'
            assert resp3[0]['morpheme_gloss_ids'][0][2][0][1] == 'c'
            assert resp3[0]['morpheme_gloss_ids'][0][2][0][2] == 'Num'

            assert resp3[0]['syntactic_category_string'] == 'Num-N-Num'

            assert resp3[1]['morpheme_break_ids'][0][0][0][1] == '7'
            assert resp3[1]['morpheme_break_ids'][0][0][0][2] == 'Num'
            assert resp3[1]['morpheme_break_ids'][0][1][0][1] == '8'
            assert resp3[1]['morpheme_break_ids'][0][1][0][2] == 'N'
            assert resp3[1]['morpheme_break_ids'][0][2][0][1] == '9'
            assert resp3[1]['morpheme_break_ids'][0][2][0][2] == 'Num'

            assert resp3[1]['morpheme_gloss_ids'][0][0][0][1] == 'x'
            assert resp3[1]['morpheme_gloss_ids'][0][0][0][2] == 'Num'
            assert resp3[1]['morpheme_gloss_ids'][0][1][0][1] == 'y'
            assert resp3[1]['morpheme_gloss_ids'][0][1][0][2] == 'N'
            assert resp3[1]['morpheme_gloss_ids'][0][2][0][1] == 'z'
            assert resp3[1]['morpheme_gloss_ids'][0][2][0][2] == 'Num'

            assert resp3[1]['syntactic_category_string'] == 'Num-N-Num'

            form_backups = dbsession.query(old_models.FormBackup).all()
            assert len(form_backups) == 2
            assert [json.loads(f.morpheme_break_ids) for f in form_backups] == \
                [[[[], [], []]], [[[], [], []]]]
            assert [json.loads(f.modifier)['role'] for f in form_backups] == [
                'administrator', 'administrator']

    def test_new_search(self):
        """Tests that GET /forms/new_search returns the search parameters for searching the forms resource."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            query_builder = SQLAQueryBuilder('Form')
            response = self.app.get(url('/forms/new_search'), headers=self.json_headers,
                                    extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert (resp['search_parameters'] ==
                    query_builder.get_search_parameters())

    def test_create_restricted(self):
        """Tests what happens when a restricted user restricts a form.

        This should be possible since restricted users are able to access the
        restricted forms IF they are the enterer.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            users = h.get_users()
            contributor = [u for u in users if u.role == 'contributor'][0]
            contributor_id = contributor.id
            administrator = [u for u in users if u.role == 'administrator'][0]
            administrator_id = administrator.id
            restricted_tag = omb.generate_restricted_tag()
            application_settings = omb.generate_default_application_settings()
            application_settings.unrestricted_users = []
            dbsession.add_all([application_settings, restricted_tag])
            transaction.commit()
            restricted_tag_id = restricted_tag.id

            # Create a restricted form as a restricted user (the contributor).
            extra_environ = {'test.authentication.id': contributor_id,
                            'test.application_settings': True}
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test restricted tag transcription',
                'translations': [{'transcription': 'test restricted tag translation',
                            'grammaticality': ''}],
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body
            restricted_form_id = resp['id']
            assert 'restricted' in [t['name'] for t in resp['tags']]

            # Create a restricted form as an unrestricted user (administrator).
            extra_environ = {'test.authentication.id': administrator_id,
                            'test.application_settings': True}
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test restricted tag transcription',
                'translations': [{'transcription': 'test restricted tag translation',
                            'grammaticality': ''}],
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body
            restricted_form_id = resp['id']
            assert 'restricted' in [t['name'] for t in resp['tags']]

            # Try to get the restricted tag as the viewer and expect to fail
            extra_environ = {'test.authentication.id': contributor_id,
                            'test.application_settings': True}
            response = self.app.get(url('show', id=restricted_form_id), headers=self.json_headers,
                                    extra_environ=extra_environ, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'

    def test_normalization(self):
        """Tests that unicode input data are normalized and so too are search patterns."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            e_acute_combining = 'e\u0301'  # LATIN SMALL LETTER E, COMBINING ACUTE ACCENT
            e_acute_precomposed = '\u00E9'   # LATIN SMALL LETTER E WITH ACUTE

            # Create a form with a unicode combining character in its transcription
            params = self.form_create_params.copy()
            params.update({
                'transcription': e_acute_combining,
                'translations': [{'transcription': 'test normalization', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            combining_form_id = resp['id']
            combining_transcription = resp['transcription']

            # Create a form with a unicode precomposed character in its transcription
            params = self.form_create_params.copy()
            params.update({
                'transcription': e_acute_precomposed,
                'translations': [{'transcription': 'test normalization', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            precomposed_form_id = resp['id']
            precomposed_transcription = resp['transcription']
            assert combining_transcription == precomposed_transcription   # h.normalize converts these both to 'e\u0301'

            # Now search for the precomposed character and expect to find two matches
            json_query = json.dumps(
                {'query': {'filter': ['Form', 'transcription', 'like', '%\u00E9%']}})
            response = self.app.request(url('search'), method='SEARCH',
                body=json_query, headers=self.json_headers, environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp) == 2
            assert sorted([f['id'] for f in resp]) == sorted([combining_form_id, precomposed_form_id])

            # Search for the e + combining accute and expect to find the same two matches
            json_query = json.dumps(
                {'query': {'filter': ['Form', 'transcription', 'like', '%e\u0301%']}})
            response = self.app.request(url('search'), method='SEARCH',
                body=json_query, headers=self.json_headers, environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp) == 2
            assert sorted([f['id'] for f in resp]) == sorted([combining_form_id, precomposed_form_id])


    def test_lexical_percolation(self):
        """Tests that creation, updating and deletion of a lexical forms percolates up to the phrasal forms containing them.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First create a couple of syntactic categories and the application settings
            Agr = old_models.SyntacticCategory()
            Agr.name = 'Agr'
            N = omb.generate_n_syntactic_category()
            Num = omb.generate_num_syntactic_category()
            application_settings = omb.generate_default_application_settings()
            dbsession.add_all([N, Num, application_settings, Agr])
            transaction.commit()
            NId = N.id
            NumId = Num.id
            AgrId = Agr.id

            extra_environ = {'test.authentication.role': 'administrator',
                                'test.application_settings': True}

            # Create two forms with morphological analyses.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'abc',
                'morpheme_break': 'a-b-c',
                'morpheme_gloss': '1-2-3',
                'translations': [{'transcription': '123', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'xyz',
                'morpheme_break': 'x-y-z',
                'morpheme_gloss': '7-8-9',
                'translations': [{'transcription': '789', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            xyz_id = response.json_body['id']

            # GET the forms and confirm that the morpheme_break_ids values are "empty"
            response = self.app.get(url('forms'), headers=self.json_headers,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            phrasal_ids = [f['id'] for f in resp]
            assert len(resp) == 2
            assert [f['morpheme_break_ids'] for f in resp] == [[[[], [], []]], [[[], [], []]]]
            assert [f['morpheme_gloss_ids'] for f in resp] == [[[[], [], []]], [[[], [], []]]]
            assert [f['syntactic_category_string'] for f in resp] == ['?-?-?', '?-?-?']

            # Now add the implicit lexical items for the two forms just entered and
            # expect the morpheme_break_ids (etc.) fields of the two phrasal forms to
            # have changed.
            sleep(1)

            x_params = self.form_create_params.copy()
            x_params.update({
                'transcription': 'x',
                'morpheme_break': 'x',
                'morpheme_gloss': '7',
                'translations': [{'transcription': '7', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            x_params = json.dumps(x_params)
            response = self.app.post(url('create'), x_params, self.json_headers, extra_environ)
            x_resp = response.json_body
            x_id = x_resp['id']
            assert x_resp['morpheme_break_ids'][0][0][0][1] == '7'
            assert x_resp['morpheme_break_ids'][0][0][0][2] == 'Num'
            assert x_resp['morpheme_gloss_ids'][0][0][0][1] == 'x'
            assert x_resp['morpheme_gloss_ids'][0][0][0][2] == 'Num'
            assert x_resp['syntactic_category_string'] == 'Num'
            assert x_resp['break_gloss_category'] == 'x|7|Num'

            y_params = self.form_create_params.copy()
            y_params.update({
                'transcription': 'y',
                'morpheme_break': 'y',
                'morpheme_gloss': '8',
                'translations': [{'transcription': '8', 'grammaticality': ''}],
                'syntactic_category': NId
            })
            y_params = json.dumps(y_params)
            response = self.app.post(url('create'), y_params, self.json_headers, extra_environ)
            y_id = response.json_body['id']

            z_params = self.form_create_params.copy()
            z_params.update({
                'transcription': 'z',
                'morpheme_break': 'z',
                'morpheme_gloss': '9',
                'translations': [{'transcription': '9', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            z_params = json.dumps(z_params)
            response = self.app.post(url('create'), z_params, self.json_headers, extra_environ)
            z_id = response.json_body['id']

            a_params = self.form_create_params.copy()
            a_params.update({
                'transcription': 'a',
                'morpheme_break': 'a',
                'morpheme_gloss': '1',
                'translations': [{'transcription': '1', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            a_params = json.dumps(a_params)
            response = self.app.post(url('create'), a_params, self.json_headers, extra_environ)

            b_params = self.form_create_params.copy()
            b_params.update({
                'transcription': 'b',
                'morpheme_break': 'b',
                'morpheme_gloss': '2',
                'translations': [{'transcription': '2', 'grammaticality': ''}],
                'syntactic_category': NId
            })
            b_params = json.dumps(b_params)
            response = self.app.post(url('create'), b_params, self.json_headers, extra_environ)

            c_params = self.form_create_params.copy()
            c_params.update({
                'transcription': 'c',
                'morpheme_break': 'c',
                'morpheme_gloss': '3',
                'translations': [{'transcription': '3', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            c_params = json.dumps(c_params)
            response = self.app.post(url('create'), c_params, self.json_headers, extra_environ)

            # Use search to get our two original morphologically complex forms
            json_query = json.dumps({'query': {'filter':
                ['Form', 'id', 'in', phrasal_ids]}})
            response = self.app.post(url('/forms/search'), json_query,
                            self.json_headers, self.extra_environ_admin)

            resp2 = response.json_body
            assert [f['id'] for f in resp] == [f['id'] for f in resp2]
            assert [f['datetime_modified'] for f in resp2] != [f['datetime_modified'] for f in resp]

            assert resp2[0]['morpheme_break_ids'][0][0][0][1] == '1'
            assert resp2[0]['morpheme_break_ids'][0][0][0][2] == 'Num'
            assert resp2[0]['morpheme_break_ids'][0][1][0][1] == '2'
            assert resp2[0]['morpheme_break_ids'][0][1][0][2] == 'N'
            assert resp2[0]['morpheme_break_ids'][0][2][0][1] == '3'
            assert resp2[0]['morpheme_break_ids'][0][2][0][2] == 'Num'

            assert resp2[0]['morpheme_gloss_ids'][0][0][0][1] == 'a'
            assert resp2[0]['morpheme_gloss_ids'][0][0][0][2] == 'Num'
            assert resp2[0]['morpheme_gloss_ids'][0][1][0][1] == 'b'
            assert resp2[0]['morpheme_gloss_ids'][0][1][0][2] == 'N'
            assert resp2[0]['morpheme_gloss_ids'][0][2][0][1] == 'c'
            assert resp2[0]['morpheme_gloss_ids'][0][2][0][2] == 'Num'

            assert resp2[0]['syntactic_category_string'] == 'Num-N-Num'
            assert resp2[0]['break_gloss_category'] == 'a|1|Num-b|2|N-c|3|Num'

            assert resp2[1]['morpheme_break_ids'][0][0][0][1] == '7'
            assert resp2[1]['morpheme_break_ids'][0][0][0][2] == 'Num'
            assert resp2[1]['morpheme_break_ids'][0][1][0][1] == '8'
            assert resp2[1]['morpheme_break_ids'][0][1][0][2] == 'N'
            assert resp2[1]['morpheme_break_ids'][0][2][0][1] == '9'
            assert resp2[1]['morpheme_break_ids'][0][2][0][2] == 'Num'

            assert resp2[1]['morpheme_gloss_ids'][0][0][0][1] == 'x'
            assert resp2[1]['morpheme_gloss_ids'][0][0][0][2] == 'Num'
            assert resp2[1]['morpheme_gloss_ids'][0][1][0][1] == 'y'
            assert resp2[1]['morpheme_gloss_ids'][0][1][0][2] == 'N'
            assert resp2[1]['morpheme_gloss_ids'][0][2][0][1] == 'z'
            assert resp2[1]['morpheme_gloss_ids'][0][2][0][2] == 'Num'

            assert resp2[1]['syntactic_category_string'] == 'Num-N-Num'
            assert resp2[1]['break_gloss_category'] == 'x|7|Num-y|8|N-z|9|Num'

            form_backups = dbsession.query(old_models.FormBackup).all()
            assert len(form_backups) == 6    # each lexical item creation updates one phrasal form

            # Now update the lexical items and expect updates in the phrasal ones too

            # Update the morpheme_break value of the lexical form 'x' and expect the
            # phrasal form 'xyz' to get updated too.
            form_backup_count = dbsession.query(old_models.FormBackup).count()
            x_params = json.loads(x_params)
            x_params['morpheme_break'] = 'xx'
            x_params = json.dumps(x_params)
            response = self.app.put(url('update', id=x_id), x_params, self.json_headers, extra_environ)
            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 2    # 'x' and 'xyz' are both updated
            assert xyz_morpheme_gloss_ids[0][0][0][1] == 'xx' # The 'x' morpheme is still glossed as '7'
            assert xyz_morpheme_break_ids[0][0] == []  # No more 'x' morpheme so w1, m1 is empty
            assert xyz_phrase.break_gloss_category == 'x|7|Num-y|8|N-z|9|Num' # Stays unchanged
            assert xyz_phrase.syntactic_category_string == 'Num-N-Num'      # " "

            # Update the morpheme_gloss value of the lexical form 'y' and expect the
            # phrasal form 'xyz' to get updated too.
            y_params = json.loads(y_params)
            y_params['morpheme_gloss'] = '88'
            y_params = json.dumps(y_params)
            response = self.app.put(url('update', id=y_id), y_params, self.json_headers, extra_environ)
            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 2
            assert xyz_morpheme_break_ids[0][1][0][1] == '88' # The 'y' morpheme is now glossed as '88'
            assert xyz_morpheme_gloss_ids[0][1] == []  # No more '8' morpheme so w1, m1 is empty
            assert xyz_phrase.break_gloss_category == 'x|7|Num-y|8|N-z|9|Num' # Stays unchanged
            assert xyz_phrase.syntactic_category_string == 'Num-N-Num'      # " "

            # Update the syntactic category of the lexical form 'z' and expect the
            # phrasal form 'xyz' to get updated too.
            z_params = json.loads(z_params)
            z_params['syntactic_category'] = NId
            z_params = json.dumps(z_params)
            response = self.app.put(url('update', id=z_id), z_params, self.json_headers, extra_environ)
            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 2
            assert xyz_morpheme_break_ids[0][2][0][2] == 'N' # The 'z' morpheme now has 'N' for category
            assert xyz_morpheme_gloss_ids[0][2][0][2] == 'N' # redundant, I know
            assert xyz_phrase.break_gloss_category == 'x|7|Num-y|8|N-z|9|N'
            assert xyz_phrase.syntactic_category_string == 'Num-N-N'

            # Save these values for the next test:
            xyz_phrase_morpheme_break_ids = xyz_phrase.morpheme_break_ids
            xyz_phrase_morpheme_gloss_ids = xyz_phrase.morpheme_gloss_ids
            xyz_phrase_break_gloss_category = xyz_phrase.break_gloss_category
            xyz_phrase_syntactic_category_string = xyz_phrase.syntactic_category_string

            # Update the lexical form 'z' in a way that is irrelevant to the phrasal
            # form 'xyz'; expect 'xyz' to be unaffected.
            z_params = json.loads(z_params)
            z_params['transcription'] = 'zZz'
            z_params['translations'] = [{'transcription': '999', 'grammaticality': ''}]
            z_params = json.dumps(z_params)
            response = self.app.put(url('update', id=z_id), z_params, self.json_headers, extra_environ)
            new_xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 1    # only the lexical item has been updated
            assert xyz_phrase_morpheme_break_ids == new_xyz_phrase.morpheme_break_ids
            assert xyz_phrase_morpheme_gloss_ids == new_xyz_phrase.morpheme_gloss_ids
            assert xyz_phrase_break_gloss_category == new_xyz_phrase.break_gloss_category
            assert xyz_phrase_syntactic_category_string == new_xyz_phrase.syntactic_category_string

            # Now create a new lexical item that will cause the 'xyz' phrasal form to be udpated
            x2_params = self.form_create_params.copy()
            x2_params.update({
                'transcription': 'x',
                'morpheme_break': 'x',
                'morpheme_gloss': '7',
                'translations': [{'transcription': '7', 'grammaticality': ''}],
                'syntactic_category': AgrId
            })
            x2_params = json.dumps(x2_params)
            response = self.app.post(url('create'), x2_params, self.json_headers, extra_environ)
            x2_id = response.json_body['id']

            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 1    # 'xyz' will have been updated
            assert xyz_morpheme_gloss_ids[0][0][0][1] == 'x' # The new 'x' morpheme ousts the old ill-matching one
            assert xyz_morpheme_break_ids[0][0][0][1] == '7' # " "
            assert len(xyz_morpheme_break_ids[0][0]) == 1  # The 'xx/7' partial match has been removed in favour of the 'x/7' perfect match
            assert xyz_morpheme_break_ids[0][0][0][2] == 'Agr'
            assert xyz_phrase.break_gloss_category == 'x|7|Agr-y|8|N-z|9|N'
            assert xyz_phrase.syntactic_category_string == 'Agr-N-N'

            # Delete the 'y' morpheme and expect the 'xyz' phrase to be udpated.
            response = self.app.delete(url('delete', id=y_id), headers=self.json_headers,
                                    extra_environ=extra_environ)
            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 2    # 'xyz' and 'y' will both have been backed up
            assert xyz_morpheme_gloss_ids[0][1] == []
            assert xyz_morpheme_break_ids[0][1] == []
            assert xyz_phrase.break_gloss_category == 'x|7|Agr-y|8|?-z|9|N'
            assert xyz_phrase.syntactic_category_string == 'Agr-?-N'

            # Delete the 'x/7' morpheme and expect the 'xyz' phrase to be udpated.  The
            # partial match 'xx/7' morpheme will now again be referenced in xyz_form.morpheme_gloss_ids
            response = self.app.delete(url('delete', id=x2_id), headers=self.json_headers, extra_environ=extra_environ)
            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            assert new_form_backup_count == form_backup_count + 2    # 'xyz' and 'x' will both have been backed up
            assert xyz_morpheme_gloss_ids[0][0][0][1] == 'xx'
            assert xyz_morpheme_gloss_ids[0][0][0][2] == 'Num'
            assert xyz_morpheme_break_ids[0][0] == []
            assert xyz_phrase.break_gloss_category == 'x|7|Num-y|8|?-z|9|N'
            assert xyz_phrase.syntactic_category_string == 'Num-?-N'

            # Update the lexical form 'z' so that its new morpheme_break and morpheme_gloss
            # values no longer match the 'xyz' phrasal form.  Expect the 'xyz' form
            # to be updated (shows that potentially affected forms are discovered by
            # searching for matches to the altered lexcical item's current *and* previous
            # states.)
            z_params = json.loads(z_params)
            z_params['morpheme_break'] = 'm'
            z_params['morpheme_gloss'] = '4'
            z_params = json.dumps(z_params)
            response = self.app.put(url('update', id=z_id), z_params, self.json_headers, extra_environ)
            new_xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            form_backup_count = new_form_backup_count
            new_form_backup_count = dbsession.query(old_models.FormBackup).count()
            xyz_phrase = dbsession.query(old_models.Form).get(xyz_id)
            xyz_morpheme_gloss_ids = json.loads(xyz_phrase.morpheme_gloss_ids)
            xyz_morpheme_break_ids = json.loads(xyz_phrase.morpheme_break_ids)
            assert new_form_backup_count == form_backup_count + 2    # only the lexical item has been updated
            assert xyz_morpheme_break_ids[0][2] == []
            assert xyz_morpheme_gloss_ids[0][2] == []
            assert xyz_phrase.break_gloss_category == 'x|7|Num-y|8|?-z|9|?'
            assert xyz_phrase.syntactic_category_string == 'Num-?-?'

            # Update the xyz form so that the delimiters used in the morpheme_break
            # and morpheme_gloss lines do not match.  Show that the morpheme
            # delimiters from the morpheme_break line are the ones that are used in
            # the break_gloss_category and syntactic_category_string values.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'xyz',
                'morpheme_break': 'x=y-z',
                'morpheme_gloss': '7-8=9',
                'translations': [{'transcription': '789', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=xyz_id), params, self.json_headers, extra_environ)
            resp = response.json_body
            assert resp['syntactic_category_string'] == 'Num=?-?'
            assert resp['morpheme_gloss_ids'] == xyz_morpheme_gloss_ids
            assert resp['break_gloss_category'] == 'x|7|Num=y|8|?-z|9|?'

    def test_morphemic_analysis_compilation(self):
        """Tests the behaviour of compile_morphemic_analysis in the forms controller.

        In particular, tests:

        1. that regular expression metacharacters like the caret "^" can be used
           as morpheme delimiters and
        2. that compile_morphemic_analysis works even when no morpheme delimiters
           are supplied and
        3. the matches_found dict in compile_morphemic_analysis reduces redundant
           db queries and processing.

        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First create a couple of syntactic categories and the application settings
            T = old_models.SyntacticCategory()
            T.name = 'T'
            D = old_models.SyntacticCategory()
            D.name = 'D'
            Agr = old_models.SyntacticCategory()
            Agr.name = 'Agr'
            N = omb.generate_n_syntactic_category()
            V = omb.generate_v_syntactic_category()
            S = omb.generate_s_syntactic_category()
            Num = omb.generate_num_syntactic_category()
            application_settings = omb.generate_default_application_settings()
            application_settings.morpheme_delimiters = ''    # NO MORPHEME DELIMITERS
            dbsession.add_all([N, V, D, T, Num, Agr, S, application_settings])
            transaction.commit()
            TId = T.id
            DId = D.id
            NId = N.id
            VId = V.id
            SId = S.id
            NumId = Num.id
            AgrId = Agr.id

            extra_environ = {'test.authentication.role': 'administrator',
                                'test.application_settings': True}

            # Test that compile_morphemic_analysis works when there are no morpheme delimiters

            # First add a sentence with no word-internal morphemes indicated
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Le chien a courru.',
                'morpheme_break': 'le chien a courr',
                'morpheme_gloss': 'the dog has run.PP',
                'translations': [{'transcription': 'The dog ran.', 'grammaticality': ''}],
                'syntactic_category': SId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body
            sent_id = resp['id']
            assert resp['morpheme_break_ids'] == [[[]], [[]], [[]], [[]]]
            assert resp['syntactic_category_string'] == '? ? ? ?'
            assert resp['break_gloss_category'] == 'le|the|? chien|dog|? a|has|? courru|run.PP|?'

            # Now add the words/morphemes for the sentence above.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'le',
                'morpheme_break': 'le',
                'morpheme_gloss': 'the',
                'translations': [{'transcription': 'the', 'grammaticality': ''}],
                'syntactic_category': DId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body
            assert resp['morpheme_break_ids'][0][0][0][1] == 'the'
            assert resp['morpheme_break_ids'][0][0][0][2] == 'D'
            assert resp['morpheme_gloss_ids'][0][0][0][1] == 'le'
            assert resp['syntactic_category_string'] == 'D'
            assert resp['break_gloss_category'] == 'le|the|D'

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'chien',
                'morpheme_break': 'chien',
                'morpheme_gloss': 'dog',
                'translations': [{'transcription': 'dog', 'grammaticality': ''}],
                'syntactic_category': NId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'a',
                'morpheme_break': 'a',
                'morpheme_gloss': 'has',
                'translations': [{'transcription': 'has', 'grammaticality': ''}],
                'syntactic_category': TId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'courr',
                'morpheme_break': 'courr',
                'morpheme_gloss': 'run.PP',
                'translations': [{'transcription': 'run', 'grammaticality': ''}],
                'syntactic_category': VId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            sentence = dbsession.query(old_models.Form).get(sent_id)
            morpheme_break_ids = json.loads(sentence.morpheme_break_ids)
            morpheme_gloss_ids = json.loads(sentence.morpheme_gloss_ids)
            assert morpheme_break_ids[0][0][0][1] == 'the'
            assert morpheme_break_ids[0][0][0][2] == 'D'
            assert morpheme_break_ids[1][0][0][1] == 'dog'
            assert morpheme_break_ids[1][0][0][2] == 'N'
            assert morpheme_break_ids[2][0][0][1] == 'has'
            assert morpheme_break_ids[2][0][0][2] == 'T'
            assert morpheme_break_ids[3][0][0][1] == 'run.PP'
            assert morpheme_break_ids[3][0][0][2] == 'V'

            assert morpheme_gloss_ids[0][0][0][1] == 'le'
            assert morpheme_gloss_ids[0][0][0][2] == 'D'
            assert morpheme_gloss_ids[1][0][0][1] == 'chien'
            assert morpheme_gloss_ids[1][0][0][2] == 'N'
            assert morpheme_gloss_ids[2][0][0][1] == 'a'
            assert morpheme_gloss_ids[2][0][0][2] == 'T'
            assert morpheme_gloss_ids[3][0][0][1] == 'courr'
            assert morpheme_gloss_ids[3][0][0][2] == 'V'

            assert sentence.syntactic_category_string == 'D N T V'
            assert sentence.break_gloss_category == 'le|the|D chien|dog|N a|has|T courru|run.PP|V'

            # Ensure that regex metacharacters can be used as morpheme delimiters
            application_settings = omb.generate_default_application_settings()
            application_settings.morpheme_delimiters = '^,?,+,.'    # regexp metachars
            dbsession.add(application_settings)
            transaction.commit()

            # Now add a sentence that is morphologically parsed using those odd delimiters
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Les chiens ont courru.',
                'morpheme_break': 'le^s chien.s o?nt courr+',
                'morpheme_gloss': 'the^PL dog.PL have?3PL run+PP',
                'translations': [{'transcription': 'The dogs ran.', 'grammaticality': ''}],
                'syntactic_category': SId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body
            sent2_id = resp['id']
            # Note that the only lexical items matching the above form are chien/dog and le/the
            assert resp['morpheme_break_ids'][0][0][0][1] == 'the'
            assert resp['morpheme_break_ids'][0][0][0][2] == 'D'
            assert resp['morpheme_break_ids'][1][0][0][1] == 'dog'
            assert resp['morpheme_break_ids'][1][0][0][2] == 'N'

            assert resp['morpheme_gloss_ids'][0][0][0][1] == 'le'
            assert resp['morpheme_gloss_ids'][0][0][0][2] == 'D'
            assert resp['morpheme_gloss_ids'][1][0][0][1] == 'chien'
            assert resp['morpheme_gloss_ids'][1][0][0][2] == 'N'

            assert resp['syntactic_category_string'] == 'D^? N.? ??? ?+?'
            # The break_gloss_category is ugly ... but it's what we should expect.
            assert resp['break_gloss_category'] == 'le|the|D^s|PL|? chien|dog|N.s|PL|? o|have|??nt|3PL|? courr|run|?+u|PP|?'

            # s/PL/Num
            params = self.form_create_params.copy()
            params.update({
                'transcription': 's',
                'morpheme_break': 's',
                'morpheme_gloss': 'PL',
                'translations': [{'transcription': 'plural', 'grammaticality': ''}],
                'syntactic_category': NumId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            # o/have/T
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'o',
                'morpheme_break': 'o',
                'morpheme_gloss': 'have',
                'translations': [{'transcription': 'have', 'grammaticality': ''}],
                'syntactic_category': TId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            # nt/3PL/Agr
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'nt',
                'morpheme_break': 'nt',
                'morpheme_gloss': '3PL',
                'translations': [{'transcription': 'third person plural', 'grammaticality': ''}],
                'syntactic_category': AgrId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            # courr/run/V
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'courr',
                'morpheme_break': 'courr',
                'morpheme_gloss': 'run',
                'translations': [{'transcription': 'run', 'grammaticality': ''}],
                'syntactic_category': VId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            # u/PP/T
            params = self.form_create_params.copy()
            params.update({
                'transcription': '',
                'morpheme_break': '',
                'morpheme_gloss': 'PP',
                'translations': [{'transcription': 'past participle', 'grammaticality': ''}],
                'syntactic_category': TId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
            resp = response.json_body

            sentence2 = dbsession.query(old_models.Form).get(sent2_id)
            morpheme_break_ids = json.loads(sentence2.morpheme_break_ids)
            morpheme_gloss_ids = json.loads(sentence2.morpheme_gloss_ids)

            assert morpheme_break_ids[0][0][0][1] == 'the'
            assert morpheme_break_ids[0][0][0][2] == 'D'
            assert morpheme_break_ids[0][1][0][1] == 'PL'
            assert morpheme_break_ids[0][1][0][2] == 'Num'

            assert morpheme_break_ids[1][0][0][1] == 'dog'
            assert morpheme_break_ids[1][0][0][2] == 'N'
            assert morpheme_break_ids[1][1][0][1] == 'PL'
            assert morpheme_break_ids[1][1][0][2] == 'Num'

            assert morpheme_break_ids[2][0][0][1] == 'have'
            assert morpheme_break_ids[2][0][0][2] == 'T'
            assert morpheme_break_ids[2][1][0][1] == '3PL'
            assert morpheme_break_ids[2][1][0][2] == 'Agr'

            assert morpheme_break_ids[3][0][0][1] == 'run'
            assert morpheme_break_ids[3][0][0][2] == 'V'
            assert morpheme_break_ids[3][1][0][1] == 'PP'
            assert morpheme_break_ids[3][1][0][2] == 'T'

            assert morpheme_gloss_ids[0][0][0][1] == 'le'
            assert morpheme_gloss_ids[0][0][0][2] == 'D'
            assert morpheme_gloss_ids[0][1][0][1] == 's'
            assert morpheme_gloss_ids[0][1][0][2] == 'Num'

            assert morpheme_gloss_ids[1][0][0][1] == 'chien'
            assert morpheme_gloss_ids[1][0][0][2] == 'N'
            assert morpheme_gloss_ids[1][1][0][1] == 's'
            assert morpheme_gloss_ids[1][1][0][2] == 'Num'

            assert morpheme_gloss_ids[2][0][0][1] == 'o'
            assert morpheme_gloss_ids[2][0][0][2] == 'T'
            assert morpheme_gloss_ids[2][1][0][1] == 'nt'
            assert morpheme_gloss_ids[2][1][0][2] == 'Agr'

            assert morpheme_gloss_ids[3][0][0][1] == 'courr'
            assert morpheme_gloss_ids[3][0][0][2] == 'V'
            assert morpheme_gloss_ids[3][1][0][1] == ''
            assert morpheme_gloss_ids[3][1][0][2] == 'T'

            assert sentence2.syntactic_category_string == 'D^Num N.Num T?Agr V+T'
            assert sentence2.break_gloss_category == \
                'le|the|D^s|PL|Num chien|dog|N.s|PL|Num o|have|T?nt|3PL|Agr courr|run|V+u|PP|T'

            # Now test that the matches_found dict of compile_morphemic_analysis reduces
            # redundant db requests & processing.  Note that seeing this requires
            # placing log.warn statements in the get_perfect_matches & get_partial_matches
            # sub-functions, e.g., log.warn('in get_perfect_matches and %s/%s was not queried!' % (morpheme, gloss))

            # Once matches for the first 7 unique morphemes of this form have been found,
            # compile_morphemic_analysis should thenceforward rely on matches_found for the
            # repeats.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'Les chiens ont courru; les chiens ont courru; les chiens ont courru.',
                'morpheme_break': 'le^s chien.s o?nt courr+u le^s chien.s o?nt courr+u le^s chien.s o?nt courr+',
                'morpheme_gloss': 'the^PL dog.PL have?3PL run+PP the^PL dog.PL have?3PL run+PP the^PL dog.PL have?3PL run+PP',
                'translations': [{'transcription': 'The dogs ran; the dogs ran; the dogs ran.', 'grammaticality': ''}],
                'syntactic_category': SId
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, extra_environ)
