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
import pickle
from shutil import copyfileobj
from subprocess import call
from time import sleep

from sqlalchemy.sql import desc

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
import old.models as old_models
import old.models.modelbuilders as omb
from old.models import Morphology, MorphologyBackup
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods


LOGGER = logging.getLogger(__name__)


url = Morphology._url(old_name=TestView.old_name)
fm_url = old_models.Form._url(old_name=TestView.old_name)
fs_url = old_models.FormSearch._url(old_name=TestView.old_name)
cp_url = old_models.Corpus._url(old_name=TestView.old_name)



class TestMorphologiesView(TestView):
    """Tests the morphologies controller.  WARNING: the tests herein are pretty messy.  The higher 
    ordered tests will fail if the previous tests have not been run.

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
        self.app.post(fm_url('create'), params, self.json_headers,
                      self.extra_environ_admin)

    def human_readable_seconds(self, seconds):
        return '%02dm%02ds' % (seconds / 60, seconds % 60)

    def test_a_create(self):
        """Tests that POST /morphologies creates a new morphology.

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
        dbsession.add_all(cats.values())
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
            ('be\u0301casse', 'be\u0301casse', 'woodcock', 'woodcock', cats['N']),

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
            ('La tortue roulait', 'la tortue roule-ait', 'the turtle roll-3SG.IMPV', 'The turtle was rolling.', cats['S'])
        )

        for tuple_ in dataset:
            self.create_form(*map(str, tuple_))

        # Create a lexicon form search and corpus, exclude the chat morpheme
        query = {'filter': ['and', [
                                ['Form', 'syntactic_category', 'name', 'in', ['N', 'V', 'AGR', 'PHI', 'D']],
                                ['not', ['Form', 'transcription', '=', 'chat']]]]}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Find morphemes',
            'search': query
        })
        params = json.dumps(params)

        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        lexicon_form_search_id = response.json_body['id']
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of lexical items',
            'form_search': lexicon_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        lexicon_corpus_id = response.json_body['id']

        # Create a rules corpus
        query = {'filter': ['Form', 'syntactic_category', 'name', '=', 'S']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Find sentences',
            'description': 'Returns all sentential forms',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        rules_form_search_id = response.json_body['id']
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of sentences',
            'form_search': rules_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        rules_corpus_id = response.json_body['id']

        # Create a rules corpus that contains no forms
        query = {'filter': ['Form', 'syntactic_category', 'name', '=', 'NO EXISTY']}
        params = self.form_search_create_params.copy()
        params.update({
            'name': 'Find nothing',
            'description': 'Returns the empty set',
            'search': query
        })
        params = json.dumps(params)
        response = self.app.post(fs_url('create'), params, self.json_headers, self.extra_environ_admin)
        empty_form_search_id = response.json_body['id']
        params = self.corpus_create_params.copy()
        params.update({
            'name': 'Corpus of nada',
            'form_search': empty_form_search_id
        })
        params = json.dumps(params)
        response = self.app.post(cp_url('create'), params, self.json_headers, self.extra_environ_admin)
        empty_rules_corpus_id = response.json_body['id']

        # Finally, create a morphology using the lexicon and rules corpora
        name = 'Morphology of a very small subset of french'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules_corpus': rules_corpus_id,
            'script_type': 'regex'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == name
        assert resp['script_type'] == 'regex'

        # Attempt to create a morphology with no rules corpus and an invalid lexicon corpus;
        # expect to be warned about the lexicon corpus but get no message about the rules corpus.
        params = self.morphology_create_params.copy()
        params.update({
            'name': 'Anonymous',
            'lexicon_corpus': 123456789
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, 400)
        resp = response.json_body
        assert resp['errors']['lexicon_corpus'] == 'There is no corpus with id 123456789.'

        # Create a morphology with only a rules corpus
        params = self.morphology_create_params.copy()
        params.update({
            'name': 'Rules corpus only',
            'rules_corpus': rules_corpus_id,
            'script_type': 'regex'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'Rules corpus only'
        assert resp['script_type'] == 'regex'

        # Create a morphology with only an empty rules corpus; this will generate an invalid
        # foma script, i.e., it will not compile.
        params = self.morphology_create_params.copy()
        params.update({
            'name': 'Empty rules corpus',
            'rules_corpus': empty_rules_corpus_id,
            'script_type': 'regex',
            'extract_morphemes_from_rules_corpus': True
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['script_type'] == 'regex'

        # Create an include unknowns morphology using the same corpus for lexicon and rules
        name = 'Morphology that includes unknowns of a very small subset of french'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': rules_corpus_id,
            'rules_corpus': rules_corpus_id,
            'script_type': 'lexc',
            'include_unknowns': True,
            'extract_morphemes_from_rules_corpus': True
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == name
        assert resp['script_type'] == 'lexc'
        assert resp['include_unknowns'] is True

        # 3 morphologies:
        # 1. rich input, rich output
        # 2. rich input, impoverished outputs
        # 3. impoverished outputs, rich output

        # rich input, rich output
        name = 'Morphology of a very small subset of french, rich morphemes on upper and lower.'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules_corpus': rules_corpus_id,
            'script_type': 'regex',
            'rich_upper': True,
            'rich_lower': True
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == name
        assert resp['script_type'] == 'regex'
        assert resp['rich_upper'] is True
        assert resp['rich_lower'] is True

        # impoverished upper, rich lower
        name = 'Morphology of a very small subset of french, impoverished morphemes on upper and rich on lower.'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules_corpus': rules_corpus_id,
            'script_type': 'regex',
            'rich_upper': False,
            'rich_lower': True
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == name
        assert resp['script_type'] == 'regex'
        assert resp['rich_upper'] is False
        assert resp['rich_lower'] is True


    def test_b_compile(self):
        """Tests that PUT /morphologies/id/generate_and_compile generates and compiles the foma script of the morphology with id.

        .. note::

            Morphology compilation is accomplished via a worker thread and
            requests to /morphologies/id/compile return immediately.  When the
            script compilation attempt has terminated, the values of the
            ``compile_attempt``, ``datetime_modified``, ``compile_succeeded``,
            ``compile_message`` and ``modifier`` attributes of the morphology are
            updated.  Therefore, the tests must poll ``GET /morphologies/id``
            in order to know when the compilation-tasked worker has finished.

        .. note::

            Depending on system resources, the following tests may fail.  A fast
            system may compile the large FST in under 30 seconds; a slow one may
            fail to compile the medium one in under 30.

        Backups

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        morphologies = dbsession.query(Morphology).all()
        morphology_1_id = morphologies[0].id # has both rules and lexicon corpus
        morphology_2_id = morphologies[1].id # has only rules corpus
        morphology_3_id = morphologies[2].id # has an empty rules corpus, invalid foma script generated
        morphology_4_id = morphologies[3].id # has the same corpus for rules and lexicon, include_unknowns True
        morphology_5_id = morphologies[4].id # rules and lexicon corpora, rich upper and lower
        morphology_6_id = morphologies[5].id # rules and lexicon corpora, rich upper and lower

        # If foma is not installed, make sure the error message is being returned
        # and exit the test.
        if not h.foma_installed():
            response = self.app.put(
                '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_1_id),
                headers=self.json_headers,
                extra_environ=self.extra_environ_contrib, status=400)
            resp = response.json_body
            assert resp['error'] == 'Foma and flookup are not installed.'
            return

        # Attempt to get the compiled script before it has been created.
        response = self.app.get(
            '/{old_name}/morphologies/{id}/servecompiled'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['error'] == 'Morphology %d has not been compiled yet.' % morphology_1_id

        # Compile the first morphology's script
        # NOTE: this will update the morphology (since a script value will be generated for the first time)
        # and will result in the generation of a new morphology backup old_models.
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_1_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_1_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_1_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_1_id)
            sleep(1)
        response = self.app.get(url('show', id=morphology_1_id), params={'script': '1', 'lexicon': '1'},
                    headers=self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script_path = os.path.join(morphology_dir, 'morphology.script')
        morphology_script = codecs.open(morphology_script_path, mode='r', encoding='utf8').read()
        assert 'define morphology' in morphology_script
        assert '(NCat)' in morphology_script, '(NCat) is not in {}'.format(morphology_script) # cf. tortue
        assert '(DCat)' in morphology_script # cf. la
        assert '(NCat "-" PHICat)' in morphology_script # cf. chien-s
        assert '(DCat "-" PHICat)' in morphology_script # cf. le-s
        assert '(VCat "-" AGRCat)' in morphology_script # cf. nage-aient, parle-ait
        assert ('c h a t "%scat%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
                not in morphology_script) # cf. extract_morphemes_from_rules_corpus = False and chat's exclusion from the lexicon corpus
        assert 'c h i e n "%sdog%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in morphology_script
        assert 'b e \u0301 c a s s e "%swoodcock%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in morphology_script
        assert resp['compile_succeeded'] is True
        assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
        assert morphology_binary_filename in morphology_dir_contents
        assert resp['modifier']['role'] == 'contributor'
        rules = resp['rules_generated']
        assert 'D' in rules # cf. le
        assert 'N' in rules # cf. tortue
        assert 'D-PHI' in rules # cf. le-s
        assert 'N-PHI' in rules # cf. chien-s
        assert 'V-AGR' in rules # cf. nage-aient, parle-ait
        assert 'lexicon' in resp
        assert 'script' in resp
        assert resp['script'] == morphology_script
        assert ['chat', 'cat'] not in resp['lexicon']['N']
        assert ['chien', 'dog'] in resp['lexicon']['N']

        # Test GET /morphologies/1?script=1&lexicon=1 and make sure the script and lexicon are returned
        response = self.app.get(url('show', id=morphology_1_id), params={'script': '1', 'lexicon': '1'},
                    headers=self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp['script'] == morphology_script
        lexicon = resp['lexicon']
        assert ['s', 'PL'] in lexicon['PHI']
        assert ['oiseau', 'bird'] in lexicon['N']
        assert ['aient', '3PL.IMPV'] in lexicon['AGR']
        assert ['la', 'the'] in lexicon['D']
        assert ['nage', 'swim'] in lexicon['V']

        # Get the compiled foma script.
        response = self.app.get(
            '/{old_name}/morphologies/{id}/servecompiled'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        morphology_binary_path = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id,
                'morphology.foma')
        foma_file = open(morphology_binary_path, 'rb')
        foma_file_content = foma_file.read()
        assert foma_file_content == response.body
        assert response.content_type == 'application/octet-stream'

        # Attempt to get the compiled foma script of a non-existent morphology.
        response = self.app.get(
            '/{old_name}/morphologies/{id}/servecompiled'.format(old_name=self.old_name, id=123456789),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin, status=404)
        resp = response.json_body
        assert resp['error'] == 'There is no morphology with id 123456789'

        # Compile the first morphology's script again
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        morphology_binary_filename = 'morphology.foma'
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id)
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_1_id`` until ``compile_attempt`` has
        # changed.
        while True:
            response = self.app.get(url('show', id=morphology_1_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_1_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_1_id)
            sleep(1)
        assert resp['compile_succeeded'] is True
        assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
        assert morphology_binary_filename in os.listdir(morphology_dir)

        # Test that PUT /morphologies/id/applydown and PUT /morphologies/id/applyup are working correctly.
        # Note that the value of the ``transcriptions`` key can be a string or a list of strings.

        # Test applydown with a valid form|gloss-form|gloss sequence.
        morpheme_sequence = 'chien%sdog%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER,
                oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        params = json.dumps({'morpheme_sequences': morpheme_sequence})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % morphology_1_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert resp[morpheme_sequence] == ['chien-s']

        # Make sure the temporary morphologization files have been deleted.
        assert not [fn for fn in morphology_dir_contents if fn.startswith('inputs_')]
        assert not [fn for fn in morphology_dir_contents if fn.startswith('outputs_')]
        assert not [fn for fn in morphology_dir_contents if fn.startswith('apply_')]

        # Test applydown with an invalid form|gloss-form|gloss sequence.
        invalid_morpheme_sequence = 'e\u0301cureuil%ssquirrel%sN-s%sPL%sPHI' % (
                oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        params = json.dumps({'morpheme_sequences': invalid_morpheme_sequence})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % morphology_1_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert resp[invalid_morpheme_sequence] == []

        # Test applydown with multiple morpheme sequences.
        ms1 = 'chien%sdog%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        ms2 = 'tombe%sfall%sV-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        params = json.dumps({'morpheme_sequences': [ms1, ms2]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % morphology_1_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert resp[ms1] == ['chien-s']
        assert resp[ms2] == []

        # Test applyup
        morpheme_sequence = 'chien-s'
        params = json.dumps({'morpheme_sequences': morpheme_sequence})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % morphology_1_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert resp[morpheme_sequence] == ['chien%sdog%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER,
            oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]

        # Test applyup with multiple input sequences
        ms1 = 'vache-s'
        ms2 = 'cheval'
        ms3 = 'vache-ait'
        ms4 = 'tombe-ait'
        ms5 = 'poule!t-s'
        params = json.dumps({'morpheme_sequences': [ms1, ms2, ms3, ms4, ms5]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp[ms1] == ['vache%scow%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, 
            oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]
        assert resp[ms2] == ['cheval%shorse%sN' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]
        assert resp[ms3] == []
        assert resp[ms4] == ['tombe%sfall%sV-ait%s3SG.IMPV%sAGR' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER,
            oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]
        assert resp[ms5] == ['poule!t%schicken%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, 
            oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]

        # Compile the second morphology's script (the one with only a rules corpus)
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_2_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_2_id`` until ``compile_attempt`` has
        # changed.
        while True:
            response = self.app.get(url('show', id=morphology_2_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_2_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_2_id)
            sleep(1)
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_2_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script_path = os.path.join(morphology_dir, 'morphology.script')
        morphology_script = codecs.open(morphology_script_path, mode='r', encoding='utf8').read()
        assert resp['compile_succeeded'] is True
        assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
        assert morphology_binary_filename in morphology_dir_contents
        assert resp['modifier']['role'] == 'contributor'
        assert 'define morphology' in morphology_script
        assert '(NCat)' in morphology_script # cf. tortue
        assert '(DCat)' in morphology_script # cf. la
        assert '(NCat "-" PHICat)' in morphology_script # cf. chien-s
        assert '(DCat "-" PHICat)' in morphology_script # cf. le-s
        assert '(VCat "-" AGRCat)' in morphology_script # cf. nage-aient, parle-ait
        # Note the change in the following two assertions from above.
        assert 'c h i e n "%sdog%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) not in morphology_script
        assert 'b e \u0301 c a s s e "%swoodcock%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) not in morphology_script

        # Compile the third morphology's script (the one with an empty rules corpus)
        # This one will not compile.
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_3_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_3_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_3_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_3_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_3_id)
            sleep(1)
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_3_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script_path = os.path.join(morphology_dir, 'morphology.script')
        morphology_script = codecs.open(morphology_script_path, mode='r', encoding='utf8').read()
        assert resp['compile_succeeded'] is False
        assert resp['compile_message'].startswith('Foma script is not a well-formed morphology')
        assert morphology_binary_filename not in morphology_dir_contents
        assert resp['modifier']['role'] == 'contributor'
        assert morphology_script.replace(' ', '').replace('\n', '') == 'definemorphology();'

        # Update the first morphology so that extract_morphemes_from_rules_corpus is set to True.
        # Now when we compile it we should expect the "chat" morpheme to be present in the script
        # and in the lexicon. 
        morphology_1 = self.app.get(
            url('show', id=morphology_1_id), headers=self.json_headers,
            extra_environ=self.extra_environ_contrib).json_body
        assert morphology_1['extract_morphemes_from_rules_corpus'] is False
        params = self.morphology_create_params.copy()
        for key in params:
            params[key] = morphology_1.get(key)
        params['lexicon_corpus'] = morphology_1['lexicon_corpus']['id']
        params['rules_corpus'] = morphology_1['rules_corpus']['id']
        params['extract_morphemes_from_rules_corpus'] = True
        params = json.dumps(params)
        response = self.app.put(url('update', id=morphology_1_id), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['extract_morphemes_from_rules_corpus'] is True
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_1_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_1_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_1_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_1_id)
            sleep(1)
        response = self.app.get(url('show', id=morphology_1_id), params={'script': '1', 'lexicon': '1'},
                    headers=self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script = resp['script']
        rules = resp['rules_generated']
        assert 'define morphology' in morphology_script
        assert '(NCat)' in morphology_script # cf. tortue
        assert '(DCat)' in morphology_script # cf. la
        assert '(NCat "-" PHICat)' in morphology_script # cf. chien-s
        assert '(DCat "-" PHICat)' in morphology_script # cf. le-s
        assert '(VCat "-" AGRCat)' in morphology_script # cf. nage-aient, parle-ait
        assert 'c h a t "%scat%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in morphology_script # HERE IS THE CHANGE!
        assert 'c h i e n "%sdog%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in morphology_script
        assert 'b e \u0301 c a s s e "%swoodcock%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in morphology_script
        assert resp['compile_succeeded'] is True
        assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
        assert morphology_binary_filename in morphology_dir_contents
        assert resp['modifier']['role'] == 'contributor'
        assert 'D' in rules # cf. le
        assert 'N' in rules # cf. tortue
        assert 'D-PHI' in rules # cf. le-s
        assert 'N-PHI' in rules # cf. chien-s
        assert 'V-AGR' in rules # cf. nage-aient, parle-ait
        assert ['chat', 'cat'] in resp['lexicon']['N']

        # Compile the fourth morphology's script (include unknowns)
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_4_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_4_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_4_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_4_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_4_id)
            sleep(1)
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_4_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script_path = os.path.join(morphology_dir, 'morphology.script')
        morphology_script = codecs.open(morphology_script_path, mode='r', encoding='utf8').read()
        assert resp['compile_succeeded'] is True
        assert resp['include_unknowns'] is True

        # Compile the fifth morphology's script (rich upper and lower)
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_5_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_5_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_5_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_5_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_5_id)
            sleep(1)
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_5_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script_path = os.path.join(morphology_dir, 'morphology.script')
        morphology_script = codecs.open(morphology_script_path, mode='r', encoding='utf8').read()
        assert resp['compile_succeeded'] is True
        assert resp['include_unknowns'] is False
        assert resp['rich_upper'] is True
        assert resp['rich_lower'] is True

        # Test applyup on morphology 5, i.e., a rich upper/lower one.
        ms1 = 'vache\u2980cow\u2980N-s\u2980PL\u2980PHI'
        ms2 = 'tombe\u2980fall\u2980V-ait\u29803SG.IMPV\u2980AGR'
        params = json.dumps({'morpheme_sequences': [ms1, ms2]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=morphology_5_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp[ms1] == [ms1]
        assert resp[ms2] == [ms2]

        # Compile the sixth morphology's script (impoverished upper and rich lower)
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_6_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        compile_attempt = resp['compile_attempt']

        # Poll ``GET /morphologies/morphology_6_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_6_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_6_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_6_id)
            sleep(1)
        morphology_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_6_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_dir_contents = os.listdir(morphology_dir)
        morphology_script_path = os.path.join(morphology_dir, 'morphology.script')
        morphology_script = codecs.open(morphology_script_path, mode='r', encoding='utf8').read()
        assert resp['compile_succeeded'] is True
        assert resp['include_unknowns'] is False
        assert resp['rich_upper'] is False
        assert resp['rich_lower'] is True

        # Test applyup on morphology False, i.e., a rich upper/lower one.
        ms1o = 'vache-s'
        ms1 = 'vache\u2980cow\u2980N-s\u2980PL\u2980PHI'
        ms2o = 'tombe-ait'
        ms2 = 'tombe\u2980fall\u2980V-ait\u29803SG.IMPV\u2980AGR'
        params = json.dumps({'morpheme_sequences': [ms1, ms2]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=morphology_6_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp[ms1] == [ms1o]
        assert resp[ms2] == [ms2o]


    def test_c_index(self):
        """Tests that GET /morphologies returns all morphology resources."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morphologies = dbsession.query(Morphology).all()

        # Get all morphologies
        response = self.app.get(url('index'), headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == 6

        # Test the paginator GET params.
        paginator = {'items_per_page': 1, 'page': 1}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp['items']) == 1
        assert resp['items'][0]['name'] == morphologies[0].name
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'Morphology', 'order_by_attribute': 'id',
                    'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp[0]['id'] == morphologies[-1].id
        assert response.content_type == 'application/json'

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'Morphology', 'order_by_attribute': 'id',
                    'order_by_direction': 'desc', 'items_per_page': 1, 'page': 6}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert morphologies[0].name == resp['items'][0]['name']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'Morphology', 'order_by_attribute': 'name',
                    'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

    def test_d_show(self):
        """Tests that GET /morphologies/id returns the morphology with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morphologies = dbsession.query(Morphology).all()

        # Try to get a morphology using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no morphology with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(
            url('show', id=morphologies[0].id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == morphologies[0].name
        assert resp['description'] == morphologies[0].description
        assert response.content_type == 'application/json'

    def test_e_new_edit(self):
        """Tests that GET /morphologies/new and GET /morphologies/id/edit return the data needed to create or update a morphology.

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        morphologies = dbsession.query(Morphology).all()

        # Test GET /morphologies/new
        response = self.app.get(url('new'), headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp['corpora']) == 3

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=morphologies[0].id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no morphology with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('edit', id=morphologies[0].id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['morphology']['name'] == morphologies[0].name
        assert len(resp['data']['corpora']) == 3
        assert response.content_type == 'application/json'

    def fix_mrphlgy(self, morphology):
        for key, val in morphology.items():
            if isinstance(val, (datetime, date)):
                morphology[key] = val.isoformat()
        return morphology

    def test_f_update(self):
        """Tests that PUT /morphologies/id updates the morphology with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        foma_installed = h.foma_installed()

        morphologies = [
            json.loads(json.dumps(self.fix_mrphlgy(m.get_dict())))
            for m in dbsession.query(Morphology).all()]
        morphology_1_id = morphologies[0]['id']
        morphology_1_name = morphologies[0]['name']
        morphology_1_description = morphologies[0]['description']
        morphology_1_modified = morphologies[0]['datetime_modified']
        morphology_1_rules_corpus_id = morphologies[0]['rules_corpus']['id']
        morphology_1_lexicon_corpus_id = morphologies[0]['lexicon_corpus']['id']
        morphology_count = len(morphologies)
        morphology_1_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id)
        morphology_1_script_path = os.path.join(morphology_1_dir, 'morphology.script')
        morphology_1_script = ''
        if foma_installed:
            morphology_1_script = codecs.open(morphology_1_script_path, mode='r', encoding='utf8').read()

        # Update the first morphology.  This will create the second backup for this morphology,
        # the first having been created by the successful compile attempt in test_compile.
        original_backup_count = dbsession.query(MorphologyBackup).count()
        params = self.morphology_create_params.copy()
        params.update({
            'name': morphology_1_name,
            'description': 'New description',
            'rules_corpus': morphology_1_rules_corpus_id,
            'lexicon_corpus': morphology_1_lexicon_corpus_id,
            'script_type': 'regex'
        })
        params = json.dumps(params)
        sleep(1)
        response = self.app.put(url('update', id=morphology_1_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        new_backup_count = dbsession.query(MorphologyBackup).count()
        datetime_modified = resp['datetime_modified']
        new_morphology_count = dbsession.query(Morphology).count()
        if foma_installed:
            updated_morphology_1_script = codecs.open(morphology_1_script_path, mode='r', encoding='utf8').read()
        else:
            updated_morphology_1_script = ''
        assert morphology_count == new_morphology_count
        assert datetime_modified != morphology_1_modified
        assert resp['description'] == 'New description'
        assert updated_morphology_1_script == morphology_1_script
        assert response.content_type == 'application/json'
        assert original_backup_count + 1 == new_backup_count
        backup = dbsession.query(MorphologyBackup).filter(
            MorphologyBackup.UUID==str(
            resp['UUID'])).order_by(
            desc(MorphologyBackup.id)).first()
        assert backup.datetime_modified.isoformat() == morphology_1_modified
        assert backup.description == morphology_1_description
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        response = self.app.put(url('update', id=morphology_1_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        morphology_count = new_morphology_count
        new_morphology_count = dbsession.query(Morphology).count()
        our_morphology_datetime_modified = dbsession.query(Morphology).get(morphology_1_id).datetime_modified
        assert our_morphology_datetime_modified.isoformat() == datetime_modified
        assert morphology_count == new_morphology_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

        # Create a new sentential form that implies a new morphological rule: V-PHI
        S = dbsession.query(old_models.SyntacticCategory).filter(old_models.SyntacticCategory.name=='S').first()
        form_create_params = ('Les fourmis tombes.', 'le-s fourmi-s tombe-s', 'the-PL ant-PL fall-PL', 'The ants fallings.', S.id)
        self.create_form(*form_create_params)

        # Another attempt at updating will still fail because the form just created will not have
        # updated the rules corpus of the morphology
        response = self.app.put(url('update', id=morphology_1_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        morphology_count = new_morphology_count
        new_morphology_count = dbsession.query(Morphology).count()
        our_morphology_datetime_modified = dbsession.query(Morphology).get(morphology_1_id).datetime_modified
        assert our_morphology_datetime_modified.isoformat() == datetime_modified
        assert morphology_count == new_morphology_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

        # Now update the rules corpus
        rules_corpus = dbsession.query(old_models.Corpus).get(morphology_1_rules_corpus_id)
        corpus_create_params = self.corpus_create_params.copy()
        corpus_create_params.update({
            'name': rules_corpus.name,
            'description': rules_corpus.description,
            'content': rules_corpus.content,
            'form_search': rules_corpus.form_search.id
        })
        corpus_create_params = json.dumps(corpus_create_params)
        self.app.put(cp_url('update', id=morphology_1_rules_corpus_id), corpus_create_params, self.json_headers, self.extra_environ_admin)

        # If we now perform a compile request on the morphology, we will get an updated script.
        # This will also result in the generation of a new morphology backup.
        if h.foma_installed():
            response = self.app.put(
                '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_1_id),
                headers=self.json_headers,
                extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            compile_attempt = resp['compile_attempt']
            while True:
                response = self.app.get(url('show', id=morphology_1_id),
                            headers=self.json_headers, extra_environ=self.extra_environ_contrib)
                resp = response.json_body
                if compile_attempt != resp['compile_attempt']:
                    LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_1_id)
                    break
                else:
                    LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_1_id)
                sleep(1)
            updated_morphology_1_script = codecs.open(morphology_1_script_path, mode='r', encoding='utf8').read()
            assert morphology_1_script != updated_morphology_1_script
            assert 'define morphology' in updated_morphology_1_script
            assert '(NCat)' in updated_morphology_1_script # cf. tortue
            assert '(DCat)' in updated_morphology_1_script # cf. la
            assert '(NCat "-" PHICat)' in updated_morphology_1_script # cf. chien-s
            assert '(DCat "-" PHICat)' in updated_morphology_1_script # cf. le-s
            assert '(VCat "-" AGRCat)' in updated_morphology_1_script # cf. nage-aient, parle-ait
            assert 'c h i e n "%sdog%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in updated_morphology_1_script
            assert 'b e \u0301 c a s s e "%swoodcock%sN":0' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER) in updated_morphology_1_script
            assert '(VCat "-" PHICat)' in updated_morphology_1_script # THIS IS THE NEW PART
            assert '(VCat "-" PHICat)' not in morphology_1_script # THIS IS THE NEW PART

    def test_g_history(self):
        """Tests that GET /morphologies/id/history returns the morphology with id=id and its previous incarnations.

        The JSON object returned is of the form
        {'morphology': morphology, 'previous_versions': [...]}.

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        foma_installed = h.foma_installed()
        if foma_installed:
            # Note: compilation requests no longer result in the creation of backups.
            # Ignore the above assertions that they do.
            morphology_1_backup_count = 2
        else:
            morphology_1_backup_count = 1

        morphologies = dbsession.query(Morphology).all()
        morphology_1_id = morphologies[0].id
        morphology_1_UUID = morphologies[0].UUID

        # Now get the history of the first morphology (which was updated twice in ``test_update``.
        response = self.app.get(
            url('history', id=morphology_1_id),
            headers=self.json_headers, extra_environ=self.extra_environ_view_appset)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert 'morphology' in resp
        assert 'previous_versions' in resp
        assert len(resp['previous_versions']) == morphology_1_backup_count
        if foma_installed:
            assert resp['previous_versions'][0]['extract_morphemes_from_rules_corpus'] is True
            assert resp['previous_versions'][1]['extract_morphemes_from_rules_corpus'] is False

        # Get the same history as above, except use the UUID
        response = self.app.get(
            url('history', id=morphology_1_UUID),
            headers=self.json_headers, extra_environ=self.extra_environ_view_appset)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert 'morphology' in resp
        assert 'previous_versions' in resp
        assert len(resp['previous_versions']) == morphology_1_backup_count

        # Attempt to get the history with an invalid id and expect to fail
        response = self.app.get(
            url('history', id=123456789),
            headers=self.json_headers, extra_environ=self.extra_environ_view_appset, status=404)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['error'] == 'No morphologies or morphology backups match 123456789'

        # Further tests could be done ... cf. the tests on the history action of the phonologies controller ...

    def test_h_lexc_scripts(self):
        """Tests that morphologies written in the lexc formalism work as expected."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        if not h.foma_installed():
            return

        morphologies = [
            json.loads(json.dumps(self.fix_mrphlgy(m.get_dict())))
            for m in dbsession.query(Morphology).all()]

        morphology_1_id = morphologies[0]['id']
        morphology_1_name = morphologies[0]['name']
        morphology_1_description = morphologies[0]['description']
        morphology_1_modified = morphologies[0]['datetime_modified']
        morphology_1_compile_attempt = morphologies[0]['compile_attempt']
        morphology_1_rules_corpus_id = morphologies[0]['rules_corpus']['id']
        morphology_1_lexicon_corpus_id = morphologies[0]['lexicon_corpus']['id']
        morphology_count = len(morphologies)
        morphology_1_dir = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id)
        morphology_1_script_path = os.path.join(morphology_1_dir, 'morphology.script')
        morphology_1_script = codecs.open(morphology_1_script_path, mode='r', encoding='utf8').read()

        # Update morphology 1 by making it into a lexc script
        orig_backup_count = dbsession.query(MorphologyBackup).count()
        params = self.morphology_create_params.copy()
        params.update({
            'name': morphology_1_name,
            'description': morphology_1_description,
            'rules_corpus': morphology_1_rules_corpus_id,
            'lexicon_corpus': morphology_1_lexicon_corpus_id,
            'script_type': 'lexc'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=morphology_1_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        new_backup_count = dbsession.query(MorphologyBackup).count()
        datetime_modified = resp['datetime_modified']
        new_morphology_count = dbsession.query(Morphology).count()
        assert new_backup_count == orig_backup_count + 1
        assert new_morphology_count == morphology_count
        assert resp['script_type'] == 'lexc'
        assert datetime_modified > morphology_1_modified

        # Before we compile, save the previous script and its compiled version, just for testing
        # NOTE: I compared the compiled regexes generated from the two different types of scripts
        # generated for the same morphology: foma did *not* evaluate them as equivalent.  I do not know
        # what to make of this at this point ...
        morphology_path = os.path.join(self.morphologies_path, 'morphology_%d' % morphology_1_id)
        #morphology_script_path = os.path.join(morphology_path, 'morphology.script')
        #morphology_script_backup_path = os.path.join(morphology_path, 'morphology_backup.script')
        morphology_binary_path = os.path.join(morphology_path, 'morphology.foma')
        #morphology_binary_backup_path = os.path.join(morphology_path, 'morphology_backup.foma')
        #copyfileobj(open(morphology_script_path, 'rb'), open(morphology_script_backup_path, 'wb'))
        #copyfileobj(open(morphology_binary_path, 'rb'), open(morphology_binary_backup_path, 'wb'))

        # Compile the morphology and get an altogether new script, i.e., one in the lexc formalism this time
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)

        # Poll ``GET /morphologies/morphology_1_id`` until ``compile_attempt`` has changed.
        while True:
            response = self.app.get(url('show', id=morphology_1_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if morphology_1_compile_attempt != resp['compile_attempt']:
                LOGGER.debug('Compile attempt for morphology %d has terminated.' % morphology_1_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d to compile ...' % morphology_1_id)
            sleep(1)

        updated_morphology_1_script = codecs.open(morphology_1_script_path, mode='r', encoding='utf8').read()
        assert updated_morphology_1_script != morphology_1_script
        assert resp['compile_succeeded'] is True
        assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
        assert 'define morphology' not in updated_morphology_1_script
        assert 'define morphology' in morphology_1_script
        assert resp['modifier']['role'] == 'contributor'

        # Get the compiled foma script.
        response = self.app.get(
            '/{old_name}/morphologies/{id}/servecompiled'.format(old_name=self.old_name, id=morphology_1_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        foma_file = open(morphology_binary_path, 'rb')
        foma_file_content = foma_file.read()
        assert foma_file_content == response.body
        assert response.content_type == 'application/octet-stream'

        # Test applydown with multiple morpheme sequences.
        ms1 = 'chien%sdog%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        ms2 = 'tombe%sfall%sV-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        ms3 = 'e\u0301cureuil%ssquirrel%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, 
                oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
        params = json.dumps({'morpheme_sequences': [ms1, ms2, ms3]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp[ms1] == ['chien-s']
        assert resp[ms2] == ['tombe-s']
        assert resp[ms3] == []

        # Test applyup with multiple input sequences
        ms1 = 'vache-s'
        ms2 = 'cheval'
        ms3 = 'vache-ait'
        ms4 = 'tombe-ait'
        params = json.dumps({'morpheme_sequences': [ms1, ms2, ms3, ms4]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=morphology_1_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp[ms1] == ['vache%scow%sN-s%sPL%sPHI' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]
        assert resp[ms2] == ['cheval%shorse%sN' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]
        assert resp[ms3] == []
        assert resp[ms4] == ['tombe%sfall%sV-ait%s3SG.IMPV%sAGR' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER,
            oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)]

    def test_i_large_morphologies(self):
        """Tests that morphology functionality works with large datasets.

        .. note::

            This test only works if MySQL is being used as the RDBMS for the
            test *and* there is a file in 
            ``onlinelinguisticdatabase/onlinelinguisticdatabase/tests/data/datasets/``
            that is a MySQL dump file of a valid OLD database.  The name of
            this file can be configured by setting the ``old_dump_file``
            variable.  Note that no such dump file is provided with the OLD
            source since the file used by the developer contains data that
            cannot be publicly shared.

        .. warning::

            This test will take a long time to complete.  If the morphologies
            have been precompiled (see below), it will take about 3 minutes. 
            If they have not been precompiled, it will take about 12 minutes
            for the lexc Blackfoot morphology to compile and the regex
            Blackfoot morphology will exceed the morphology compile timeout
            value of 30 minutes (as specified in lib/utils.py).

        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # If foma is not installed, exit.
        if not h.foma_installed():
            return

        # Configuration

        # The ``old_dump_file`` variable holds the name of a MySQL dump file in
        # /tests/data/datasets that will be used to populate the database.
        old_dump_file = 'blaold.sql'
        backup_dump_file = 'old_test_dump.sql'

        # These variables hold the names of the pre-generated foma scripts and
        # their compiled counterparts. These files, if specified, should be
        # present in /tests/data/morphologies. Specifying these variables
        # sidesteps the lengthy compilation process, if desired. Set these
        # variables to None if you want the compilation, i.e., want to
        # regenerate the values.
        pregenerated_lexc_morphology = None # 'blaold_morphology_lexc.script'
        precompiled_lexc_morphology = None # 'blaold_morphology_lexc.foma'
        pregenerated_regex_morphology = None # 'blaold_morphology_regex.script'
        precompiled_regex_morphology = None # 'blaold_morphology_regex.foma'

        # Here we load a whole database from the mysqpl dump file specified in
        # ``tests/data/datasets/<old_dump_file>``.
        old_dump_file_path = os.path.join(self.test_datasets_path,
            old_dump_file)
        backup_dump_file_path = os.path.join(self.test_datasets_path,
            backup_dump_file)
        tmp_script_path = os.path.join(self.test_datasets_path, 'tmp.sh')
        if not os.path.isfile(old_dump_file_path):
            return
        rdbms = self.settings.get('rdbms')
        if rdbms != 'mysql':
            return
        username = self.settings.get('user')
        password = self.settings.get('password')
        db_name = self.settings.get('name')
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

        # Create a lexicon form search and corpus
        # The code below constructs a query that finds a (large) subset of the Blackfoot morphemes.
        # Notes for future morphology creators:
        # 1. the "oth" category is a mess: detangle the nominalizer, inchoative, transitive suffixes, etc. from
        #    one another and from the numerals and temporal modifiers -- ugh!
        # 2. the "pro" category" is also a mess: clearly pronoun-forming iisto does not have the same distribution 
        #    as the verbal suffixes aiksi and aistsi!  And oht, the LING/means thing, is different again...
        # 3. hkayi, that thing at the end of demonstratives, is not agra, what is it? ...
        # 4. the dim category contains only 'sst' 'DIM' and is not used in any forms ...
        lexical_category_names = ['nan', 'nin', 'nar', 'nir', 'vai', 'vii', 'vta', 'vti', 'vrt', 'adt',
            'drt', 'prev', 'med', 'fin', 'oth', 'o', 'und', 'pro', 'asp', 'ten', 'mod', 'agra', 'agrb', 'thm', 'whq',
            'num', 'stp', 'PN']
        not_complex_conjunct = ['not', ['Form', 'morpheme_break', 'regex', '[ -]']]
        durative_morpheme = 15717
        hkayi_morpheme = 23429
        exclusions = ['not', ['Form', 'id', 'in', [durative_morpheme, hkayi_morpheme]]]
        query = {'filter': ['and', [['Form', 'syntactic_category', 'name', 'in', lexical_category_names],
                                    not_complex_conjunct, exclusions]]}
        query_ = {'filter': ['and', [['Form', 'id', '<', 1000],
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

        # Create a rules corpus
        # The goal here is to exclude things that look like words but are not really words, i.e., 
        # morphemes; as a heuristic we search for forms categorized as 'sent' or whose transcription
        # value contains a space.
        query = {'filter': ['or', [['Form', 'syntactic_category', 'name', '=', 'sent'],
                                    ['Form', 'transcription', 'like', '% %']]]}
        # TODO: exclude ungrammatical forms!
        query_ = {'filter': ['and', [
                                ['or', [['Form', 'syntactic_category', 'name', '=', 'sent'],
                                        ['Form', 'transcription', 'like', '% %']]],
                                ['Form', 'id', '<', 23000],
                                ['Form', 'id', '>', 22000]]]}
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

        # Finally, create a morphology using the lexicon and rules corpora

        # Set it initially to extract morphemes from the rules corpus. 
        name = 'Morphology of Blackfoot'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules_corpus': rules_corpus_id,
            'script_type': 'lexc',
            'extract_morphemes_from_rules_corpus': True
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        large_morphology_id = resp['id']
        assert resp['name'] == name
        assert resp['script_type'] == 'lexc'

        # Generate the morphology's script without compiling it.
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate'.format(old_name=self.old_name, id=large_morphology_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        generate_attempt = resp['generate_attempt']

        # Poll ``GET /morphologies/large_morphology_id`` until ``generate_attempt`` has changed.
        seconds_elapsed = 0
        wait = 2
        while True:
            response = self.app.get(url('show', id=large_morphology_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if generate_attempt != resp['generate_attempt']:
                LOGGER.debug('Generate attempt for morphology %d has terminated.' % large_morphology_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d\'s script to generate: %s' % (
                    large_morphology_id, self.human_readable_seconds(seconds_elapsed)))
            sleep(wait)
            seconds_elapsed = seconds_elapsed + wait

        # Get the morphology's lexicon and script (the script will be very large, i.e., > 30 MB)
        response = self.app.get(url('show', id=large_morphology_id), params={'script': '1', 'lexicon': '1'},
                    headers=self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        original_lexicon = resp['lexicon']
        original_lexical_items_count = sum(len(v) for v in original_lexicon.values())
        original_script = resp['script']
        original_script_len = len(original_script)
        LOGGER.debug('The Blackfoot morphology when morphemes are extracted from the rules corpus is %d characters long' % original_script_len)
        LOGGER.debug('The Blackfoot morphology when morphemes are extracted from the rules corpus has %d lexical items' % original_lexical_items_count)

        # Now update the morphology so that morphemes are not extracted from the rules corpus.
        # This will reduce needless complexity in the morphology by removing a lot of homophonic lexical items.
        name = 'Morphology of Blackfoot'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules_corpus': rules_corpus_id,
            'script_type': 'lexc',
            'extract_morphemes_from_rules_corpus': False
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=large_morphology_id), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        large_morphology_id = resp['id']
        assert resp['name'] == name
        assert resp['script_type'] == 'lexc'

        # Generate the morphology's script (and lexicon) again. regardless of whether we have a pregenerated one
        response = self.app.put(
            '/{old_name}/morphologies/{id}/generate'.format(old_name=self.old_name, id=large_morphology_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        generate_attempt = resp['generate_attempt']

        # Poll ``GET /morphologies/large_morphology_id`` until ``generate_attempt`` has changed.
        seconds_elapsed = 0
        wait = 2
        while True:
            response = self.app.get(url('show', id=large_morphology_id),
                        headers=self.json_headers, extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            if generate_attempt != resp['generate_attempt']:
                LOGGER.debug('Generate attempt for morphology %d has terminated.' % large_morphology_id)
                break
            else:
                LOGGER.debug('Waiting for morphology %d\'s script to generate (%s) ...' % (
                    large_morphology_id, self.human_readable_seconds(seconds_elapsed)))
            sleep(wait)
            seconds_elapsed = seconds_elapsed + wait

        # Get the morphology's newly generated lexicon and script.
        response = self.app.get(url('show', id=large_morphology_id), params={'script': '1', 'lexicon': '1'},
                    headers=self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        new_lexicon = resp['lexicon']
        new_lexical_items_count = sum(len(v) for v in new_lexicon.values())
        new_script = resp['script']
        new_script_len = len(new_script)
        # When lexical items are not extracted from the rules corpus, the lexicon and script should both be shorter.
        LOGGER.debug('The Blackfoot morphology when morphemes are NOT extracted from the rules corpus is %d characters long' % new_script_len)
        LOGGER.debug('The Blackfoot morphology when morphemes are NOT extracted from the rules corpus has %d lexical items' % new_lexical_items_count)
        assert new_script_len < original_script_len
        assert new_lexical_items_count < original_lexical_items_count

        ################################################################################
        # NEW -- this will GREATLY reduce compilation time
        ################################################################################

        # Rich morphemes will make the morphology FSTs much slower to compile
        rich_upper = False

        # Generate a list of X number of morphotactic rules: alter X to alter compile time
        rules_generated = resp['rules_generated']
        first_100_rules = ' '.join(rules_generated.split()[:100])
        crucial_rules = 'agra-vai vai vta-thm-agrb PN'
        rules_specified = '%s %s' % (first_100_rules, crucial_rules)

        # Update the morphology by specifying the rules explicitly: a very restricted morphotactics.
        name = 'Morphology of Blackfoot'
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            'rules': rules_specified,
            'script_type': 'lexc',
            'extract_morphemes_from_rules_corpus': False,
            'rich_upper': rich_upper
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=large_morphology_id), params, self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        large_morphology_id = resp['id']
        assert resp['name'] == name
        assert resp['script_type'] == 'lexc'

        ################################################################################
        # END NEW
        ################################################################################

        # Compile the morphology's script (if necessary, cf. precompiled_lexc_morphology and pregenerated_lexc_morphology)
        morphology_directory = os.path.join(self.morphologies_path, 'morphology_%d' % large_morphology_id)
        morphology_binary_filename = 'morphology.foma'
        morphology_script_filename = 'morphology.script'
        morphology_binary_path = os.path.join(morphology_directory, morphology_binary_filename)
        morphology_script_path = os.path.join(morphology_directory, morphology_script_filename)
        try:
            precompiled_lexc_morphology_path = os.path.join(self.test_morphologies_path, precompiled_lexc_morphology)
            pregenerated_lexc_morphology_path = os.path.join(self.test_morphologies_path, pregenerated_lexc_morphology)
        except Exception:
            precompiled_lexc_morphology_path = None
            pregenerated_lexc_morphology_path = None
        if (precompiled_lexc_morphology_path and pregenerated_lexc_morphology_path and 
            os.path.exists(precompiled_lexc_morphology_path) and os.path.exists(pregenerated_lexc_morphology_path)):
            # Use the precompiled morphology script if it's available,
            copyfileobj(open(precompiled_lexc_morphology_path, 'rb'), open(morphology_binary_path, 'wb'))
            copyfileobj(open(pregenerated_lexc_morphology_path, 'rb'), open(morphology_script_path, 'wb'))
        else:
            # Compile the morphology's script
            response = self.app.put(
                '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=large_morphology_id),
                headers=self.json_headers,
                extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            compile_attempt = resp['compile_attempt']

            # Poll ``GET /morphologies/large_morphology_id`` until ``compile_attempt`` has
            # changed.
            # WARNING: it takes about 11 minutes on my machine for foma to compile this morphology
            seconds_elapsed = 0
            wait = 10
            while True:
                response = self.app.get(url('show', id=large_morphology_id),
                            headers=self.json_headers, extra_environ=self.extra_environ_contrib)
                resp = response.json_body
                if compile_attempt != resp['compile_attempt']:
                    LOGGER.debug('Compile attempt for morphology %d has terminated.' % large_morphology_id)
                    break
                else:
                    LOGGER.debug('Waiting for morphology %d to compile (%s) ...' % (
                        large_morphology_id, self.human_readable_seconds(seconds_elapsed)))
                sleep(wait)
                seconds_elapsed = seconds_elapsed + wait
            morphology_dir_contents = os.listdir(morphology_directory)
            assert resp['compile_succeeded'] is True
            assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
            assert morphology_binary_filename in morphology_dir_contents
            assert resp['modifier']['role'] == 'contributor'

        # If ``rich_upper`` is set to False, expect to find a pickled dictionary interface 
        # to the morphology's lexicon in its directory.
        if not resp['rich_upper']:
            large_morphology = dbsession.query(old_models.Morphology).get(large_morphology_id)
            dictionary_path = large_morphology.get_file_path('dictionary')
            assert os.path.isfile(dictionary_path)
            dictionary = pickle.load(open(dictionary_path, 'rb'))
            first_key = list(dictionary.keys())[0]
            assert type(dictionary[first_key]) == list

        # Get the morphology again, this time requesting the lexicon attribute
        response = self.app.get(url('show', id=large_morphology_id), params={'lexicon': '1'},
                    headers=self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        lexicon = resp['lexicon']
        assert type(lexicon) is dict
        assert 'vai' in lexicon
        assert 'nan' in lexicon
        assert len(lexicon['nan']) > 500

        # Get the compiled foma script.
        response = self.app.get(
            '/{old_name}/morphologies/{id}/servecompiled'.format(old_name=self.old_name, 
            id=large_morphology_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        foma_file = open(morphology_binary_path, 'rb')
        foma_file_content = foma_file.read()
        assert foma_file_content == response.body
        assert response.content_type == 'application/octet-stream'

        # Test that PUT /morphologies/id/applydown and PUT /morphologies/id/applyup are working correctly.
        # Note that the value of the ``transcriptions`` key can be a string or a list of strings.
        seqs = (
            (
                'ipommo%stransfer.title.to%svta-oki%sINV%sthm-wa%s3SG%sagrb' % (
                    oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER,
                    oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER),
                'ipommo-oki-wa'
            ),
            ('Joel%sJoel%sPN' % (oldc.RARE_DELIMITER, oldc.RARE_DELIMITER), 'Joel'),
            (
                'kit%s2%sagra-sska\u0301akanii%sagree%svai' % (
                    oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER),
                'kit-sska\u0301akanii'
            )
        )

        # Test applydown with a valid morpheme sequence.
        morpheme_sequence_1 = rich_upper and seqs[0][0] or seqs[0][1]
        phoneme_sequence_1 = seqs[0][1]
        params = json.dumps({'morpheme_sequences': morpheme_sequence_1})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert phoneme_sequence_1 in resp[morpheme_sequence_1]

        # Make sure the temporary morphologization files have been deleted.
        assert not [fn for fn in morphology_dir_contents if fn.startswith('inputs_')]
        assert not [fn for fn in morphology_dir_contents if fn.startswith('outputs_')]
        assert not [fn for fn in morphology_dir_contents if fn.startswith('apply_')]

        # Test applydown with an invalid morpheme sequence.
        invalid_morpheme_sequence = (rich_upper and 'e\u0301cureuil%ssquirrel%sN-s%sPL%sAGR' % (
                oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER, oldc.RARE_DELIMITER)
                or 'e\u0301cureuil-s')
        params = json.dumps({'morpheme_sequences': invalid_morpheme_sequence})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert resp[invalid_morpheme_sequence] == []

        # Test applydown with multiple morpheme sequences.
        morpheme_sequence_2 = rich_upper and seqs[1][0] or seqs[1][1]
        phoneme_sequence_2 = seqs[1][1]
        morpheme_sequence_3 = rich_upper and seqs[2][0] or seqs[2][1]
        phoneme_sequence_3 = seqs[2][1]
        params = json.dumps({'morpheme_sequences': [morpheme_sequence_1, morpheme_sequence_2, morpheme_sequence_3]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert phoneme_sequence_1 in resp[morpheme_sequence_1]
        assert phoneme_sequence_2 in resp[morpheme_sequence_2]
        assert phoneme_sequence_3 in resp[morpheme_sequence_3]

        # Test applyup
        params = json.dumps({'morpheme_sequences': phoneme_sequence_1})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert morpheme_sequence_1 in resp[phoneme_sequence_1]

        # Test applyup with multiple input sequences
        params = json.dumps({'morpheme_sequences': [phoneme_sequence_1, phoneme_sequence_2, phoneme_sequence_3]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert morpheme_sequence_1 in resp[phoneme_sequence_1]
        assert morpheme_sequence_2 in resp[phoneme_sequence_2]
        assert morpheme_sequence_3 in resp[phoneme_sequence_3]

        # Now update the morphology so that its script will be generated as a regex.
        params = self.morphology_create_params.copy()
        params.update({
            'name': name,
            'lexicon_corpus': lexicon_corpus_id,
            #'rules_corpus': rules_corpus_id,
            'rules': rules_specified, # specify the rules explicitly: a very restricted morphotactics.
            'script_type': 'regex',
            'exctract_morphemes_from_rules_corpus': False,
            'rich_upper': rich_upper
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=large_morphology_id), params,
                    self.json_headers, self.extra_environ_admin_appset)
        resp = response.json_body
        assert resp['name'] == name
        assert resp['script_type'] == 'regex'
        assert resp['rich_upper'] == rich_upper

        # Compile the morphology's script (if necessary, cf. precompiled_regex_morphology and pregenerated_regex_morphology)
        try:
            precompiled_regex_morphology_path = os.path.join(self.test_morphologies_path, precompiled_regex_morphology)
            pregenerated_regex_morphology_path = os.path.join(self.test_morphologies_path, pregenerated_regex_morphology)
        except Exception:
            precompiled_regex_morphology_path = None
            pregenerated_regex_morphology_path = None
        if (precompiled_regex_morphology_path and pregenerated_regex_morphology_path and 
            os.path.exists(precompiled_regex_morphology_path) and os.path.exists(pregenerated_regex_morphology_path)):
            # Use the precompiled morphology script if it's available,
            copyfileobj(open(precompiled_regex_morphology_path, 'rb'), open(morphology_binary_path, 'wb'))
            copyfileobj(open(pregenerated_regex_morphology_path, 'rb'), open(morphology_script_path, 'wb'))
        else:
            # Compile the morphology's script
            response = self.app.put(
                '/{old_name}/morphologies/{id}/generate_and_compile'.format(old_name=self.old_name, id=large_morphology_id),
                headers=self.json_headers,
                extra_environ=self.extra_environ_contrib)
            resp = response.json_body
            compile_attempt = resp['compile_attempt']

            # Poll ``GET /morphologies/large_morphology_id`` until ``compile_attempt`` has
            # changed.
            # WARNING: it takes well over 30 minutes (the default max compile time for morphologies) to generate and compile
            # this regex FST.  I had to compile it "by hand" via the foma interface...
            seconds_elapsed = 0
            wait = 10
            while True:
                response = self.app.get(url('show', id=large_morphology_id),
                            headers=self.json_headers, extra_environ=self.extra_environ_contrib)
                resp = response.json_body
                if compile_attempt != resp['compile_attempt']:
                    LOGGER.debug('Compile attempt for morphology %d has terminated.' % large_morphology_id)
                    break
                else:
                    LOGGER.debug('Waiting for morphology %d to compile (%s) ...' % (
                        large_morphology_id, self.human_readable_seconds(seconds_elapsed)))
                sleep(wait)
                seconds_elapsed = seconds_elapsed + wait
            morphology_dir_contents = os.listdir(morphology_directory)
            assert resp['compile_succeeded'] is True
            assert resp['compile_message'] == 'Compilation process terminated successfully and new binary file was written.'
            assert morphology_binary_filename in morphology_dir_contents
            assert resp['modifier']['role'] == 'contributor'

        # Get the compiled foma script.
        response = self.app.get(
            '/{old_name}/morphologies/{id}/servecompiled'.format(old_name=self.old_name, id=large_morphology_id),
            headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        foma_file = open(morphology_binary_path, 'rb')
        foma_file_content = foma_file.read()
        assert foma_file_content == response.body
        assert response.content_type == 'application/octet-stream'

        # The same tests we ran with the lexc version of the morphology should also work with this version:

        # Test applydown with a valid morpheme sequence.
        params = json.dumps({'morpheme_sequences': morpheme_sequence_1})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert phoneme_sequence_1 in resp[morpheme_sequence_1]

        # Make sure the temporary morphologization files have been deleted.
        assert not [fn for fn in morphology_dir_contents if fn.startswith('inputs_')]
        assert not [fn for fn in morphology_dir_contents if fn.startswith('outputs_')]
        assert not [fn for fn in morphology_dir_contents if fn.startswith('apply_')]

        # Test applydown with an invalid form|gloss-form|gloss sequence.
        params = json.dumps({'morpheme_sequences': invalid_morpheme_sequence})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert resp[invalid_morpheme_sequence] == []

        # Test applydown with multiple morpheme sequences.
        params = json.dumps({'morpheme_sequences': [morpheme_sequence_1, morpheme_sequence_2, morpheme_sequence_3]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applydown'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert phoneme_sequence_1 in resp[morpheme_sequence_1]
        assert phoneme_sequence_2 in resp[morpheme_sequence_2]
        assert phoneme_sequence_3 in resp[morpheme_sequence_3]

        # Test applyup
        params = json.dumps({'morpheme_sequences': phoneme_sequence_1})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        morphology_dir_path = os.path.join(self.morphologies_path,
                                        'morphology_%d' % large_morphology_id)
        morphology_dir_contents = os.listdir(morphology_dir_path)
        assert morpheme_sequence_1 in resp[phoneme_sequence_1]

        # Test applyup with multiple input sequences
        params = json.dumps({'morpheme_sequences': [phoneme_sequence_1, phoneme_sequence_2, phoneme_sequence_3]})
        response = self.app.put(
            '/{old_name}/morphologies/{id}/applyup'.format(old_name=self.old_name, id=large_morphology_id),
            params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert morpheme_sequence_1 in resp[phoneme_sequence_1]
        assert morpheme_sequence_2 in resp[phoneme_sequence_2]
        assert morpheme_sequence_3 in resp[phoneme_sequence_3]

        # Finally, load the original database back in so that subsequent tests can work.
        with open(tmp_script_path, 'w') as tmpscript:
            tmpscript.write('#!/bin/sh\nmysql -u %s -p%s %s < %s' % (username, password, db_name, backup_dump_file_path))
        with open(os.devnull, "w") as fnull:
            call([tmp_script_path], stdout=fnull, stderr=fnull)
        os.remove(tmp_script_path)
        os.remove(backup_dump_file_path)

    def test_z_cleanup(self):
        """Clean up after the tests."""
        super().tearDown(dirs_to_destroy=['user', 'morphology', 'corpus'])
