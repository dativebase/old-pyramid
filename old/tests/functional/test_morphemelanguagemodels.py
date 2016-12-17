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

import codecs
from datetime import datetime, date
import json
import logging
import os
from subprocess import call
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
import old.models as old_models
import old.models.modelbuilders as omb
from old.models import MorphemeLanguageModel, MorphemeLanguageModelBackup
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods


LOGGER = logging.getLogger(__name__)


url = MorphemeLanguageModel._url()
fm_url = old_models.Form._url()
fs_url = old_models.FormSearch._url()
cp_url = old_models.Corpus._url()



class TestMorphemelanguagemodelsView(TestView):
    """Tests the morpheme_language_models controller.  WARNING: the tests herein are pretty messy.  The higher 
    ordered tests will fail if the previous tests have not been run.

    TODO: add more tests where we try to create deficient LMs.

    """

    def tearDown(self):
        self.tear_down_dbsession()

    def setUp(self):
        self.default_setup()

    def create_form(self, tr, mb, mg, tl, cat):
        params = self.form_create_params.copy()
        params.update({
            'transcription': tr,
            'morpheme_break': mb,
            'morpheme_gloss': mg,
            'translations': [{
                'transcription': tl,
                'grammaticality': ''
            }],
            'syntactic_category': cat
        })
        params = json.dumps(params)
        self.app.post(fm_url('create'), params, self.json_headers, self.extra_environ_admin)

    def human_readable_seconds(self, seconds):
        return '%02dm%02ds' % (seconds / 60, seconds % 60)

    def test_a_create(self):
        """Tests that POST /morphemelanguagemodels creates a new morphology.

        """
        super().create_db()

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create the default application settings
        application_settings = omb.generate_default_application_settings()
        dbsession.add(application_settings)
        dbsession.commit()

        # Create some syntactic categories
        cats = {
            'N': old_models.SyntacticCategory(name='N'),
            'V': old_models.SyntacticCategory(name='V'),
            'AGR': old_models.SyntacticCategory(name='AGR'),
            'PHI': old_models.SyntacticCategory(name='PHI'),
            'S': old_models.SyntacticCategory(name='S'),
            'D': old_models.SyntacticCategory(name='D')
        }
        dbsession.add_all(list(cats.values()))
        dbsession.flush()
        cats = {k: v.id for k, v in cats.items()}
        dbsession.commit()

        dataset = (
            ('chien', 'chien', 'dog', 'dog', cats['N']),
            ('chat', 'chat', 'cat', 'cat', cats['N']),
            ('oiseau', 'oiseau', 'bird', 'bird', cats['N']),
            ('cheval', 'cheval', 'horse', 'horse', cats['N']),
            ('vache', 'vache', 'cow', 'cow', cats['N']),
            ('grenouille', 'grenouille', 'frog', 'frog', cats['N']),
            ('tortue', 'tortue', 'turtle', 'turtle', cats['N']),
            ('fourmi', 'fourmi', 'ant', 'ant', cats['N']),
            ('poule!t', 'poule!t', 'chicken', 'chicken', cats['N']), # note the ! which is a foma reserved symbol
            (u'be\u0301casse', 'be\u0301casse', 'woodcock', 'woodcock', cats['N']),

            ('parle', 'parle', 'speak', 'speak', cats['V']),
            ('grimpe', 'grimpe', 'climb', 'climb', cats['V']),
            ('nage', 'nage', 'swim', 'swim', cats['V']),
            ('tombe', 'tombe', 'fall', 'fall', cats['V']),

            ('le', 'le', 'the', 'the', cats['D']),
            ('la', 'la', 'the', 'the', cats['D']),

            ('s', 's', 'PL', 'plural', cats['PHI']),

            ('ait', 'ait', '3SG.IMPV', 'third person singular imperfective', cats['AGR']),
            ('aient', 'aient', '3PL.IMPV', 'third person plural imperfective', cats['AGR']),

            ('Les chat nageaient.', 'le-s chat-s nage-aient', 'the-PL cat-PL swim-3PL.IMPV', 'The cats were swimming.', cats['S']),
            ('La tortue parlait', 'la tortue parle-ait', 'the turtle speak-3SG.IMPV', 'The turtle was speaking.', cats['S']),
            ('Les oiseaux parlaient', 'le-s oiseau-s parle-aient', 'the-PL bird-PL speak-3PL.IMPV', 'The birds were speaking.', cats['S']),
            ('Le fourmi grimpait', 'le fourmi grimpe-ait', 'the ant climb-3SG.IMPV', 'The ant was climbing.', cats['S']),
            ('Les grenouilles nageaient', 'le-s grenouille-s nage-aient', 'the-PL frog-PL swim-3PL.IMPV', 'The frogs were swimming.', cats['S']),
            ('Le cheval tombait', 'le cheval tombe-ait', 'the horse fall-3SG.IMPV', 'The horse was falling.', cats['S'])
        )

        for tuple_ in dataset:
            self.create_form(*map(str, tuple_))

        # Create the restricted tag
        restricted_tag = omb.generate_restricted_tag()
        dbsession.add(restricted_tag)

        # Create a form search that finds sentences
        query = {'filter': ['Form', 'syntactic_category', 'name', '=', 'S']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Find sentences',
            'description': 'Returns all sentential forms',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        sentential_form_search_id = response.json_body['id']

        # Create a corpus of sentences
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of sentences',
            'form_search': sentential_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        sentential_corpus_id = response.json_body['id']

        # Create a morpheme language model using the sentential corpus.
        name = 'Morpheme language model'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': sentential_corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['order'] == 3
        assert resp['smoothing'] == '' # The ModKN smoothing algorithm is the implicit default with MITLM
        assert resp['restricted'] is False

        if not h.mitlm_installed():
            return

        # Attempt to compute the perplexity of the LM before its files have been generated.  Expect this
        # to work: perplexity generation creates its own pairs of test/training sets.
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt',
                lm_perplexity_attempt, LOGGER, wait=1, vocal=False)

        perplexity = resp['perplexity']
        LOGGER.debug('Perplexity of super toy french (6 sentence corpus, ModKN, n=3): %s' % perplexity)

        # Attempt to get the ARPA file of the LM before it exists and expect to fail.
        response = self.app.get(
            '/morphemelanguagemodels/{id}/serve_arpa'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin, status=404)
        resp = response.json_body
        assert resp['error'] == 'The ARPA file for morpheme language model %d has not been compiled yet.' % morpheme_language_model_id

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER, wait=1, vocal=False)
        assert resp['generate_message'] == 'Language model successfully generated.'
        assert resp['restricted'] is False

        # Get the ARPA file of the LM as a viewer.
        response = self.app.get(
            '/morphemelanguagemodels/{id}/serve_arpa'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_view)
        assert response.content_type == 'text/plain'
        arpa = str(response.body, encoding='utf8')
        assert oldc.RARE_DELIMITER.join([u'parle', 'speak', 'V']) in arpa

        # Restrict the first sentential form -- relevant for testing the restriction percolation into LMs.
        sentence1 = dbsession.query(old_models.Form).filter(old_models.Form.syntactic_category.has(
            old_models.SyntacticCategory.name=='S')).all()[0]
        sentence1.tags.append(restricted_tag)
        dbsession.commit()

        # Again generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER, wait=1, vocal=False)
        assert resp['generate_message'] == 'Language model successfully generated.'
        assert resp['restricted'] is True # post file generation the LM should now be restricted because of the restricted Form.

        # Attempt to get the ARPA file of the LM as a viewer but expect to fail this time.
        response = self.app.get(
            '/morphemelanguagemodels/{id}/serve_arpa'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_view, status=403)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp == oldc.UNAUTHORIZED_MSG

        # Attempt to get the ARPA file of the LM as an administrator and expect to succeed.
        response = self.app.get(
            '/morphemelanguagemodels/{id}/serve_arpa'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        assert response.content_type == 'text/plain'
        arpa = str(response.body, encoding='utf8')
        assert oldc.RARE_DELIMITER.join([u'parle', 'speak', 'V']) in arpa

        # Get some probabilities
        likely_word = '%s %s' % (
            oldc.RARE_DELIMITER.join([u'chat', 'cat', 'N']),
            oldc.RARE_DELIMITER.join([u's', 'PL', 'PHI']))
        unlikely_word = '%s %s' % (
            oldc.RARE_DELIMITER.join([u's', 'PL', 'PHI']),
            oldc.RARE_DELIMITER.join([u'chat', 'cat', 'N']))
        ms_params = json.dumps({'morpheme_sequences': [likely_word, unlikely_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        likely_word_log_prob = resp[likely_word]
        unlikely_word_log_prob = resp[unlikely_word]
        assert pow(10, likely_word_log_prob) > pow(10, unlikely_word_log_prob)

        # Create a morpheme language model using the same sentential corpus but with some other MITLM-specific settings.
        name = 'Morpheme language model FixKN'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': sentential_corpus_id,
            'toolkit': 'mitlm',
            'order': 4,
            'smoothing': 'FixKN'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['order'] == 4
        assert resp['smoothing'] == 'FixKN'

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER, wait=1, vocal=False)

        # Get probabilities again
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_likely_word_log_prob = resp[likely_word]
        new_unlikely_word_log_prob = resp[unlikely_word]
        assert pow(10, new_likely_word_log_prob) > pow(10, new_unlikely_word_log_prob)
        assert new_likely_word_log_prob != likely_word_log_prob
        assert new_unlikely_word_log_prob != unlikely_word_log_prob

        # Compute the perplexity of the language model just created/generated.  This request will cause
        # the system to automatically split the corpus of the LM into 5 distinct, randomly generated
        # training (90%) and test (10%) sets and compute the perplexity of each test set according to 
        # the LM generated from its training set and return the average of these 5 perplexity calculations.
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER, wait=1, vocal=False)
        perplexity = resp['perplexity']
        LOGGER.debug('Perplexity of super toy french (6 sentence corpus, FixKN, n=4): %s' % perplexity)

        # Attempt to create a morpheme language model that lacks a corpus and has invalid values
        # for toolkit and order -- expect to fail.
        name = 'Morpheme language model with no corpus'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'toolkit': 'mitlm_lmlmlm',
            'order': 7,
            'smoothing': 'strawberry' # this error will only be caught if everything else is groovey
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['corpus'] == 'Please enter a value'
        assert resp['errors']['order'] == 'Please enter a number that is 5 or smaller'
        assert 'toolkit' in resp['errors']

        # Attempt to create a morpheme language model that has an invalid smoothing value and expect to fail.
        name = 'Morpheme language model with no corpus'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'toolkit': 'mitlm',
            'order': 3,
            'smoothing': 'strawberry', # error that will now be caught
            'corpus': sentential_corpus_id
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors'] == 'The LM toolkit mitlm implements no such smoothing algorithm strawberry.'

        # Create a category-based morpheme language old_models.
        name = 'Category-based mMorpheme language model'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'categorial': True,
            'name': name,
            'corpus': sentential_corpus_id,
            'toolkit': 'mitlm',
            'order': 4,
            'smoothing': 'FixKN'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['order'] == 4
        assert resp['smoothing'] == 'FixKN'
        assert resp['categorial'] is True

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER, wait=1,
                vocal=True, task_descr='generate categorial MLM')

        # Get the ARPA file of the LM.
        response = self.app.get(
            '/morphemelanguagemodels/{id}/serve_arpa'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        assert response.content_type == 'text/plain'
        arpa = str(response.body, encoding='utf8')

        # The ARPA-formatted LM file will contain (at least) these category-based bi/trigrams:
        assert 'D PHI' in arpa
        assert 'N PHI' in arpa
        assert 'V AGR' in arpa
        assert '<s> V AGR' in arpa

        # Get the probabilities of our likely and unlikely words based on their category
        likely_word = 'N PHI'
        unlikely_word = 'PHI N'
        ms_params = json.dumps({'morpheme_sequences': [likely_word, unlikely_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        likely_word_log_prob = resp[likely_word]
        unlikely_word_log_prob = resp[unlikely_word]
        assert likely_word_log_prob > unlikely_word_log_prob

        # Compute the perplexity of the category-based language old_models.
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER, wait=1, vocal=False)
        perplexity = resp['perplexity']
        LOGGER.debug('Perplexity of super toy french (6 sentence corpus, category-based, FixKN, n=4): %s' % perplexity)

    def test_b_index(self):
        """Tests that GET /morpheme_language_models returns all morpheme_language_model resources."""

        MITLM_INSTALLED = h.mitlm_installed()

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morpheme_language_models = dbsession.query(MorphemeLanguageModel).all()

        # Get all morpheme_language_models
        response = self.app.get(url('index'), headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        if MITLM_INSTALLED:
            assert len(resp) == 3
        else:
            assert len(resp) == 1
            return

        # Test the paginator GET params.
        paginator = {'items_per_page': 1, 'page': 1}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 1
        assert resp['items'][0]['name'] == morpheme_language_models[0].name
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'MorphemeLanguageModel', 'order_by_attribute': 'id',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == morpheme_language_models[-1].id
        assert response.content_type == 'application/json'

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'MorphemeLanguageModel', 'order_by_attribute': 'id',
                        'order_by_direction': 'desc', 'items_per_page': 1, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert morpheme_language_models[0].name == resp['items'][0]['name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'MorphemeLanguageModel', 'order_by_attribute': 'name',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

    def test_d_show(self):
        """Tests that GET /morphemelanguagemodels/id returns the morpheme_language_model with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morpheme_language_models = dbsession.query(MorphemeLanguageModel).all()

        # Try to get a morpheme_language_model using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no morpheme language model with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('show', id=morpheme_language_models[0].id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == morpheme_language_models[0].name
        assert resp['description'] == morpheme_language_models[0].description
        assert response.content_type == 'application/json'

    def test_e_new_edit(self):
        """Tests that GET /morphemelanguagemodels/new and GET
        /morphemelanguagemodels/id/edit return the data needed to create or
        update a morpheme_language_model.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morpheme_language_models = dbsession.query(MorphemeLanguageModel).all()
        corpora = dbsession.query(old_models.Corpus).all()
        morphologies = dbsession.query(old_models.Morphology).all()
        toolkits = oldc.LANGUAGE_MODEL_TOOLKITS

        # Test GET /morphemelanguagemodels/new
        response = self.app.get(url('new'), headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp['corpora']) == len(corpora)
        assert len(resp['morphologies']) == len(morphologies)
        assert len(list(resp['toolkits'].keys())) == len(list(toolkits.keys()))

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=morpheme_language_models[0].id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no morpheme language model with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('edit', id=morpheme_language_models[0].id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['morpheme_language_model']['name'] == morpheme_language_models[0].name
        assert len(resp['data']['corpora']) == len(corpora)
        assert len(resp['data']['morphologies']) == len(morphologies)
        assert len(list(resp['data']['toolkits'].keys())) == len(list(toolkits.keys()))
        assert response.content_type == 'application/json'

    def fix_lm(self, lm_dict):
        for key, val in lm_dict.items():
            if isinstance(val, (datetime, date)):
                lm_dict[key] = val.isoformat()
        return lm_dict

    def test_f_update(self):
        """Tests that PUT /morphemelanguagemodels/id updates the morpheme_language_model with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        if not h.mitlm_installed():
            return
        morpheme_language_models = [
            json.loads(json.dumps(self.fix_lm(lm.get_dict()))) for lm in
            dbsession.query(MorphemeLanguageModel).all()]
        morpheme_language_model_id = morpheme_language_models[0]['id']
        morpheme_language_model_1_name = morpheme_language_models[0]['name']
        morpheme_language_model_1_description = morpheme_language_models[0]['description']
        morpheme_language_model_1_modified = morpheme_language_models[0]['datetime_modified']
        morpheme_language_model_1_corpus_id = morpheme_language_models[0]['corpus']['id']
        morpheme_language_model_1_vocabulary_morphology_id = getattr(morpheme_language_models[0].get('vocabulary_morphology'), 'id', None)
        morpheme_language_model_count = len(morpheme_language_models)
        morpheme_language_model_1_dir = os.path.join(
            self.morpheme_language_models_path, 'morpheme_language_model_%d' % morpheme_language_model_id)
        morpheme_language_model_1_arpa_path = os.path.join(
            morpheme_language_model_1_dir,
            'morpheme_language_model.lm')
        morpheme_language_model_1_arpa = codecs.open(
            morpheme_language_model_1_arpa_path,
            mode='r',
            encoding='utf8').read()

        # Update the first morpheme language old_models.  This will create the first backup for this morpheme language old_models.
        original_backup_count = dbsession.query(MorphemeLanguageModelBackup).count()
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': morpheme_language_model_1_name,
            'description': 'New description',
            'corpus': morpheme_language_model_1_corpus_id,
            'vocabulary_morphology': morpheme_language_model_1_vocabulary_morphology_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=morpheme_language_model_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        new_backup_count = dbsession.query(MorphemeLanguageModelBackup).count()
        datetime_modified = resp['datetime_modified']
        new_morpheme_language_model_count = dbsession.query(MorphemeLanguageModel).count()
        assert morpheme_language_model_count == new_morpheme_language_model_count
        assert datetime_modified != morpheme_language_model_1_modified
        assert resp['description'] == 'New description'
        assert response.content_type == 'application/json'
        assert original_backup_count + 1 == new_backup_count
        backup = dbsession.query(MorphemeLanguageModelBackup).filter(
            MorphemeLanguageModelBackup.UUID==str(
            resp['UUID'])).order_by(
            desc(MorphemeLanguageModelBackup.id)).first()
        assert backup.datetime_modified.isoformat() == morpheme_language_model_1_modified
        assert backup.description == morpheme_language_model_1_description
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        response = self.app.put(url('update', id=morpheme_language_model_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        morpheme_language_model_count = new_morpheme_language_model_count
        new_morpheme_language_model_count = dbsession.query(MorphemeLanguageModel).count()
        our_morpheme_language_model_datetime_modified = dbsession.query(MorphemeLanguageModel).get(morpheme_language_model_id).datetime_modified
        assert our_morpheme_language_model_datetime_modified.isoformat() == datetime_modified
        assert morpheme_language_model_count == new_morpheme_language_model_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

    def test_g_history(self):
        """Tests that GET /morphemelanguagemodels/id/history returns the morpheme_language_model with id=id and its previous incarnations.

        The JSON object returned is of the form
        {'morpheme_language_model': morpheme_language_model, 'previous_versions': [...]}.

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morpheme_language_models = dbsession.query(MorphemeLanguageModel).all()
        morpheme_language_model_id = morpheme_language_models[0].id
        morpheme_language_model_1_UUID = morpheme_language_models[0].UUID
        morpheme_language_model_1_backup_count = len(dbsession.query(MorphemeLanguageModelBackup).\
                filter(MorphemeLanguageModelBackup.UUID==morpheme_language_model_1_UUID).all())
        # Now get the history of the first morpheme_language_model (which was updated twice in ``test_update``.
        response = self.app.get(
            url('history', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_view_appset)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert 'morpheme_language_model' in resp
        assert 'previous_versions' in resp
        assert len(resp['previous_versions']) == morpheme_language_model_1_backup_count

        # Get the same history as above, except use the UUID
        response = self.app.get(
            url('history', id=morpheme_language_model_1_UUID),
            headers=self.json_headers, extra_environ=self.extra_environ_view_appset)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert 'morpheme_language_model' in resp
        assert 'previous_versions' in resp
        assert len(resp['previous_versions']) == morpheme_language_model_1_backup_count

        # Attempt to get the history with an invalid id and expect to fail
        response = self.app.get(
            url('history', id=123456789),
            headers=self.json_headers, extra_environ=self.extra_environ_view_appset, status=404)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['error'] == 'No morpheme language models or morpheme language model backups match 123456789'

        # Further tests could be done ... cf. the tests on the history action of the phonologies controller ...

    def test_i_large_datasets(self):
        """Tests that morpheme language model functionality works with large datasets.

        .. note::

            This test only works if MySQL is being used as the RDBMS for the test
            *and* there is a file in 
            ``onlinelinguisticdatabase/onlinelinguisticdatabase/tests/data/datasets/``
            that is a MySQL dump file of a valid OLD database.  The name of this file
            can be configured by setting the ``old_dump_file`` variable.  Note that no
            such dump file is provided with the OLD source since the file used by the
            developer contains data that cannot be publicly shared.

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        # Configuration

        # The ``old_dump_file`` variable holds the name of a MySQL dump file in /tests/data/datasets
        # that will be used to populate the database.
        old_dump_file = 'blaold.sql'
        backup_dump_file = 'old_test_dump.sql'

        # Here we load a whole database from the mysqpl dump file specified in ``tests/data/datasets/<old_dump_file>``.
        old_dump_file_path = os.path.join(self.test_datasets_path, old_dump_file)
        backup_dump_file_path = os.path.join(self.test_datasets_path, backup_dump_file)
        tmp_script_path = os.path.join(self.test_datasets_path, 'tmp.sh')
        if not os.path.isfile(old_dump_file_path):
            return
        SQLAlchemyURL = self.settings['sqlalchemy.url']
        if not SQLAlchemyURL.split(':')[0] == 'mysql':
            return
        rdbms, username, password, db_name = SQLAlchemyURL.split(':')
        username = username[2:]
        password = password.split('@')[0]
        db_name = db_name.split('/')[-1]
        # First dump the existing database so we can load it later.
        # Note: the --single-transaction option seems to be required (on Mac MySQL 5.6 using InnoDB tables ...)
        # see http://forums.mysql.com/read.php?10,108835,112951#msg-112951
        with open(tmp_script_path, 'w') as tmpscript:
            tmpscript.write('#!/bin/sh\nmysqldump -u %s -p%s --single-transaction --no-create-info --result-file=%s %s' % (
                username, password, backup_dump_file_path, db_name))
        os.chmod(tmp_script_path, 0o744)
        with open(os.devnull, "w") as fnull:
            call([tmp_script_path], stdout=fnull, stderr=fnull)
        # Now load the dump file of the large database (from old_dump_file)
        with open(tmp_script_path, 'w') as tmpscript:
            tmpscript.write('#!/bin/sh\nmysql -u %s -p%s %s < %s' % (username, password, db_name, old_dump_file_path))
        with open(os.devnull, "w") as fnull:
            call([tmp_script_path], stdout=fnull, stderr=fnull)

        # Recreate the default users that the loaded dump file deleted
        administrator = omb.generate_default_administrator()
        contributor = omb.generate_default_contributor()
        viewer = omb.generate_default_viewer()
        dbsession.add_all([administrator, contributor, viewer])
        dbsession.commit()

        ################################################################################
        # CORPUS
        ################################################################################

        # Create a corpus of forms containing words -- to be used to estimate ngram probabilities
        # The goal here is to exclude things that look like words but are not really words, i.e., 
        # morphemes; as a heuristic we search for grammatical forms categorized as 'sent' or whose
        # transcription value contains a space or a hyphen-minus.
        query = {'filter': ['and', [['or', [['Form', 'syntactic_category', 'name', '=', 'sent'],
                                            ['Form', 'morpheme_break', 'like', '% %'],
                                            ['Form', 'morpheme_break', 'like', '%-%']]],
                                    ['Form', 'syntactic_category_string', '!=', None],
                                    ['Form', 'grammaticality', '=', '']]]}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Forms containing words',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        words_form_search_id = response.json_body['id']

        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of forms that contain words',
            'form_search': words_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        words_corpus_id = response.json_body['id']

        ################################################################################
        # LM 1 -- trigram, ModKN
        ################################################################################

        # Now create a morpheme language model using the corpus of forms containing words
        # Note that the default smoothing algorithm will be ModKN and the order will be 3
        name = 'Morpheme language model for Blackfoot'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': words_corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER)
        assert resp['generate_message'] == 'Language model successfully generated.'

        # Get some probabilities: nit-ihpiyi should be more probable than ihpiyi-nit
        likely_word = '%s %s' % (
            oldc.RARE_DELIMITER.join([u'nit', '1', 'agra']),
            oldc.RARE_DELIMITER.join([u'ihpiyi', 'dance', 'vai']))
        unlikely_word = '%s %s' % (
            oldc.RARE_DELIMITER.join([u'ihpiyi', 'dance', 'vai']),
            oldc.RARE_DELIMITER.join([u'nit', '1', 'agra']))
        ms_params = json.dumps({'morpheme_sequences': [likely_word, unlikely_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        likely_word_log_prob = resp[likely_word]
        unlikely_word_log_prob = resp[unlikely_word]
        assert pow(10, likely_word_log_prob) > pow(10, unlikely_word_log_prob)

        # Compute the perplexity of the LM 
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER)
        perplexity = resp['perplexity']

        # count how many words constitute the corpus.
        lm_corpus_path = os.path.join(self.morpheme_language_models_path,
                'morpheme_language_model_%s' % morpheme_language_model_id,
                'morpheme_language_model.txt')
        word_count = 0
        with codecs.open(lm_corpus_path, encoding='utf8') as f:
            for line in f:
                word_count += 1
        LOGGER.debug('Perplexity of Blackfoot LM %s (%s sentence corpus, ModKN, n=3): %s' % (
            morpheme_language_model_id, word_count, perplexity))

        ################################################################################
        # LM 2 -- trigram, ModKN, category-based
        ################################################################################

        # Recreate the above-created LM except make it category-based.
        name = 'Category-based morpheme language model for Blackfoot'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'categorial': True,
            'name': name,
            'corpus': words_corpus_id,
            'toolkit': 'mitlm'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER)
        assert resp['generate_message'] == 'Language model successfully generated.'

        # Get some probabilities: agra-vai should be more probable than vai-agra
        likely_category_word = 'agra vai'
        unlikely_category_word = 'vai agra'
        ms_params = json.dumps({'morpheme_sequences': [likely_category_word, unlikely_category_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        likely_category_word_log_prob = resp[likely_category_word]
        unlikely_category_word_log_prob = resp[unlikely_category_word]
        assert pow(10, likely_category_word_log_prob) > pow(10, unlikely_category_word_log_prob)

        # Compute the perplexity of the LM 
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER)
        category_based_perplexity = resp['perplexity']

        # count how many words constitute the corpus.
        lm_corpus_path = os.path.join(self.morpheme_language_models_path, 'morpheme_language_model_%s' % morpheme_language_model_id,
                'morpheme_language_model.txt')
        word_count = 0
        with codecs.open(lm_corpus_path, encoding='utf8') as f:
            for line in f:
                word_count += 1
        LOGGER.debug('Perplexity of Blackfoot category-based LM %s (%s sentence corpus, ModKN, n=3): %s' % (
            morpheme_language_model_id, word_count, category_based_perplexity))

        ################################################################################
        # MORPHOLOGY -- we'll use it to specify a fixed vocabulary for subsequent LMs.
        ################################################################################

        # Create a form search that finds lexical items (i.e., Blackfoot morphemes) and make a corpus out of it.
        lexical_category_names = ['nan', 'nin', 'nar', 'nir', 'vai', 'vii', 'vta', 'vti', 'vrt', 'adt',
            'drt', 'prev', 'med', 'fin', 'oth', 'o', 'und', 'pro', 'asp', 'ten', 'mod', 'agra', 'agrb', 'thm', 'whq',
            'num', 'stp', 'PN']
        durative_morpheme = 15717
        hkayi_morpheme = 23429
        query = {'filter': ['and', [['Form', 'syntactic_category', 'name', 'in', lexical_category_names],
                                    ['not', ['Form', 'morpheme_break', 'regex', '[ -]']],
                                    ['not', ['Form', 'id', 'in', [durative_morpheme, hkayi_morpheme]]],
                                    ['not', ['Form', 'grammaticality', '=', '*']]
                                    ]]}
        smaller_query_for_rapid_testing = {'filter': ['and', [['Form', 'id', '<', 1000],
                                    ['Form', 'syntactic_category', 'name', 'in', lexical_category_names]]]}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Blackfoot morphemes',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        lexicon_form_search_id = response.json_body['id']
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of Blackfoot morphemes',
            'form_search': lexicon_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        lexicon_corpus_id = response.json_body['id']

        # Create a form search of forms containing blackfoot words and use it to create a corpus of
        # word-containing forms.  The goal here is to find forms that are explicitly sentences or that
        # contain spaces or morpheme delimiters in their morpheme break fields.
        query = {'filter': ['and', [['or', [['Form', 'syntactic_category', 'name', '=', 'sent'],
                                            ['Form', 'morpheme_break', 'like', '%-%'],
                                            ['Form', 'morpheme_break', 'like', '% %']]],
                                    ['Form', 'grammaticality', '=', '']]]}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Find Blackfoot sentences',
            'description': 'Returns all sentential forms',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        rules_form_search_id = response.json_body['id']

        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of Blackfoot sentences',
            'form_search': rules_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        rules_corpus_id = response.json_body['id']

        # Now we reduce the number of category-based word-formation rules by extracting all such
        # rules implicit in the rules corpus that have four or fewer execmplars.  With the Blackfoot database and the
        # rules corpus form search defined above, this removes more than 1000 sequences from the just over
        # 1,800 that are currently generated, a not insubstantial reduction in complexity of the resulting morphology FST.

        # Get the category sequence types of all of the words in the rules corpus ordered by their counts, minus
        # those with fewer than 5 counts.
        minimum_token_count = 5
        params = {'minimum_token_count': minimum_token_count}
        response = self.app.get(
            '/corpora/{id}/get_word_category_sequences'.format(rules_corpus_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body

        word_category_sequences = ' '.join([word_category_sequence for word_category_sequence, ids in resp])

        # Now create a morphology using the lexicon and rules defined by word_category_sequences
        morphology_name = 'Morphology of Blackfoot'
        params = self.morphology_create_params.copy()
        params.update({
            'name': morphology_name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules': word_category_sequences,
            'script_type': 'lexc',
            'extract_morphemes_from_rules_corpus': False # This is irrelevant since this morphology doesn't use a rules corpus
        })
        params = json.dumps(params)
        response = self.app.post(url('morphologies'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        morphology_id = resp['id']
        assert resp['name'] == morphology_name
        assert resp['script_type'] == 'lexc'

        # Generate the morphology's script without compiling it.
        response = self.app.put(
            '/morphologies/{id}/generate'.format(id=morphology_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        generate_attempt = resp['generate_attempt']

        # Poll ``GET /morphologies/morphology_id`` until ``generate_attempt`` has changed.
        seconds_elapsed = 0
        wait = 2
        while True:
            response = self.app.get(url('morphology', id=morphology_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if generate_attempt != resp['generate_attempt']:
                LOGGER.debug('Generate attempt for morphology %d has terminated.' % morphology_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d\'s script to generate: %s' % (
                    morphology_id, self.human_readable_seconds(seconds_elapsed)))
            sleep(wait)
            seconds_elapsed = seconds_elapsed + wait

        # Now our morphology has a lexicon associated to it that we can use to create a vocabulary
        # for our language old_models.  Since the morphology will only recognize sequences of morphemes
        # that are generable using this vocabulary, we can create a language model over this fixed
        # vocabulary.

        ################################################################################
        # LM 3 -- trigram, ModKN, fixed vocab
        ################################################################################

        # Create the morpheme language model with a vocabulary_morphology value
        name = 'Morpheme language model for Blackfoot with fixed vocabulary'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': words_corpus_id,
            'toolkit': 'mitlm',
            'vocabulary_morphology': morphology_id
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['vocabulary_morphology']['name'] == morphology_name

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER)

        # Get some probabilities: nit-ihpiyi should be more probable than ihpiyi-nit
        ms_params = json.dumps({'morpheme_sequences': [likely_word, unlikely_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_likely_word_log_prob = resp[likely_word]
        new_unlikely_word_log_prob = resp[unlikely_word]
        assert pow(10, new_likely_word_log_prob) > pow(10, new_unlikely_word_log_prob)
        assert new_unlikely_word_log_prob != unlikely_word_log_prob
        assert new_likely_word_log_prob != likely_word_log_prob

        # Compute the perplexity of the LM 
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER,
            task_descr='GET PERPLEXITY OF LM %s' % morpheme_language_model_id)
        new_perplexity = resp['perplexity']

        LOGGER.debug('new_perplexity')
        LOGGER.debug(new_perplexity)
        LOGGER.debug('perplexity')
        LOGGER.debug(perplexity)
        assert new_perplexity < perplexity
        LOGGER.debug('Perplexity of Blackfoot LM %s (%s sentence corpus, ModKN, n=3, fixed vocabulary): %s' % (
            morpheme_language_model_id, word_count, new_perplexity))

        ################################################################################
        # LM 4 -- trigram, ModKN, fixed vocab, categorial
        ################################################################################

        # Create a fixed vocabulary LM that is category-based.
        name = 'Categorial morpheme language model for Blackfoot with fixed vocabulary'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': words_corpus_id,
            'toolkit': 'mitlm',
            'vocabulary_morphology': morphology_id,
            'categorial': True
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['vocabulary_morphology']['name'] == morphology_name

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER)

        # Get some probabilities: agra-vai should be more probable than vai-agra
        ms_params = json.dumps({'morpheme_sequences': [likely_category_word, unlikely_category_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_likely_category_word_log_prob = resp[likely_category_word]
        new_unlikely_category_word_log_prob = resp[unlikely_category_word]
        assert pow(10, new_likely_category_word_log_prob) > pow(10, new_unlikely_category_word_log_prob)
        assert new_unlikely_category_word_log_prob != unlikely_category_word_log_prob
        assert new_likely_category_word_log_prob != likely_category_word_log_prob

        # Compute the perplexity of the LM 
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER,
            task_descr='GET PERPLEXITY OF LM %s' % morpheme_language_model_id)
        new_category_based_perplexity = resp['perplexity']

        LOGGER.debug('Perplexity of Blackfoot LM %s (%s sentence corpus, ModKN, n=3, '
            'fixed vocabulary, category-based): %s' % (
            morpheme_language_model_id, word_count, new_category_based_perplexity))
        # The perplexity of this categorial LM should (and is usually, but not always) lower
        # than the previous categorial one that did not have a fixed vocab.  As a result, the
        # assertion below cannot be categorically relied upon.
        #assert new_category_based_perplexity < (1 + category_based_perplexity)

        ################################################################################
        # LM 5 -- trigram, ModKN, fixed vocab, corpus weighted towards 'nit-ihpiyi'
        ################################################################################

        # Create a language model built on a corpus that contains multiple tokens of certain
        # forms.  This allows us to tinker with the probabilities.  In this specific case,
        # I stack the corpus with forms containing 'nit|1-ihpiyi|dance'.

        # First get the ids of the forms in the corpus
        query = json.dumps({'query': {'filter': ['Form', 'corpora', 'id', '=', words_corpus_id]}})
        response = self.app.post(url('/forms/search'), query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        form_ids = [f['id'] for f in resp]

        # Now get the ids of all forms in the corpus that have nit-ihpiyi 1-dance in them and add them 100 times to the form ids list
        nit_ihpiyi_ids = [f['id'] for f in resp if 'nit|1|agra-ihpiyi|dance|vai' in f['break_gloss_category']]
        form_ids += nit_ihpiyi_ids * 100

        # Create a new corpus that is defined by a list of ids corresponding to forms which contain an inordinate amount of nit-ihpiyi words.
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of forms that contain words with lots of nit-ihpiyi words',
            'content': ','.join(map(str, form_ids))
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        nit_ihpiyi_words_corpus_id = response.json_body['id']

        # Create the morpheme language model with a vocabulary_morphology value
        name = 'Morpheme language model for Blackfoot with fixed vocabulary and weighted towards nit-ihpiyi words'
        params = self.morpheme_language_model_create_params.copy()
        params.update({
            'name': name,
            'corpus': nit_ihpiyi_words_corpus_id,
            'toolkit': 'mitlm',
            'vocabulary_morphology': morphology_id
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        morpheme_language_model_id = resp['id']
        assert resp['name'] == name
        assert resp['toolkit'] == 'mitlm'
        assert resp['vocabulary_morphology']['name'] == morphology_name

        # Generate the files of the language model
        response = self.app.put(
            '/morphemelanguagemodels/{id}/generate'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_generate_attempt = resp['generate_attempt']

        # Poll GET /morphemelanguagemodels/id until generate_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'generate_attempt', lm_generate_attempt, LOGGER, 
            task_descr='GET PERPLEXITY OF L %s' % morpheme_language_model_id)

        # Get some probabilities: nit-ihpiyi should be more probable than ihpiyi-nit.
        # Also, because of the new weighted corpus, nit-ihpiyi should now be assigned a higher probability
        # than it was before.
        ms_params = json.dumps({'morpheme_sequences': [likely_word, unlikely_word]})
        response = self.app.put(
            '/morphemelanguagemodels/{id}/get_probabilities'.format(id=morpheme_language_model_id),
            ms_params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        newer_likely_word_log_prob = resp[likely_word]
        newer_unlikely_word_log_prob = resp[unlikely_word]
        assert pow(10, new_likely_word_log_prob) > pow(10, new_unlikely_word_log_prob)
        assert newer_unlikely_word_log_prob != unlikely_word_log_prob
        # Because we've given more weight to nit-ihpiyi in the LM's corpus, this word should be
        # more probable according to this LM than according to the previous one.
        assert newer_likely_word_log_prob > new_likely_word_log_prob

        # Compute the perplexity of the LM 
        response = self.app.put(
            '/morphemelanguagemodels/{id}/compute_perplexity'.format(id=morpheme_language_model_id),
            {}, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        lm_perplexity_attempt = resp['perplexity_attempt']

        # Poll GET /morphemelanguagemodels/id until perplexity_attempt changes.
        requester = lambda: self.app.get(url('show', id=morpheme_language_model_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = self.poll(requester, 'perplexity_attempt', lm_perplexity_attempt, LOGGER,
            task_descr='GET PERPLEXITY OF LM %s' % morpheme_language_model_id)
        newest_perplexity = resp['perplexity']
        assert newest_perplexity < perplexity
        LOGGER.debug('Perplexity of Blackfoot LM %s (%s sentence corpus, ModKN, n=3, fixed vocabulary, corpus weighted towards nit-ihpiyi): %s' %
                (morpheme_language_model_id, word_count, newest_perplexity))

        """
        # Finally, load the original database back in so that subsequent tests can work.
        with open(tmp_script_path, 'w') as tmpscript:
            tmpscript.write('#!/bin/sh\nmysql -u %s -p%s %s < %s' % (username, password, db_name, backup_dump_file_path))
        with open(os.devnull, "w") as fnull:
            call([tmp_script_path], stdout=fnull, stderr=fnull)
        os.remove(tmp_script_path)
        os.remove(backup_dump_file_path)
        """

        sleep(1) # If I don't sleep here I get an odd thread-related error (conditional upon
        # this being the last test to be run, I think)...

    def test_z_cleanup(self):
        """Clean up after the tests."""
        super().tearDown(
            dirs_to_destroy=['user', 'morpheme_language_model', 'corpus',
                             'morphological_parser'])
