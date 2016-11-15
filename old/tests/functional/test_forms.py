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
