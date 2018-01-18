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

"""This module tests the form search functionality, i.e., requests to SEARCH
/forms and POST /forms/search.

NOTE: getting the non-standard http SEARCH method to work in the tests required
using the request method of TestController().app and specifying values for the
method, body, headers, and environ kwarg parameters.  WebTest prints a
WSGIWarning when unknown HTTP methods (e.g., SEARCH) are used.  To prevent this,
I altered the global valid_methods tuple of webtest.lint at runtime by adding a
'SEARCH' method (see _add_SEARCH_to_web_test_valid_methods() below).
"""

from datetime import date, datetime, timedelta
from functools import reduce
import json
import logging
import platform
import re

from old.tests import TestView, add_SEARCH_to_web_test_valid_methods
from old.lib.dbutils import DBUtils
import old.models as old_models
import old.lib.helpers as h
import old.models.modelbuilders as omb


LOGGER = logging.getLogger(__name__)


url = old_models.Form._url()



# Global temporal objects -- useful for creating the data upon which to search
# and for formulating assertions about the results of those searches.
TODAY_TIMESTAMP = datetime.now()
DAY_DELTA = timedelta(1)
YESTERDAY_TIMESTAMP = TODAY_TIMESTAMP - DAY_DELTA
JAN1 = date(2012, 1, 1)
JAN2 = date(2012, 1, 2)
JAN3 = date(2012, 1, 3)
JAN4 = date(2012, 1, 4)

MYSQL_ENGINE = old_models.Model.__table_args__.get('mysql_engine')

################################################################################
# Functions for creating & retrieving test data
################################################################################


def _create_test_models(dbsession, n=100):
    _add_test_models_to_session('Tag', n, ['name'], dbsession)
    _add_test_models_to_session('Speaker', n, ['first_name', 'last_name', 'dialect'], dbsession)
    _add_test_models_to_session('Source', n, ['author_first_name', 'author_last_name',
                                            'title'], dbsession)
    _add_test_models_to_session('ElicitationMethod', n, ['name'], dbsession)
    _add_test_models_to_session('SyntacticCategory', n, ['name'], dbsession)
    _add_test_models_to_session('File', n, ['name'], dbsession)
    dbsession.commit()

def _add_test_models_to_session(model_name, n, attrs, dbsession):
    for i in range(1, n + 1):
        m = getattr(old_models, model_name)()
        for attr in attrs:
            setattr(m, attr, '%s %s' % (attr, i))
        dbsession.add(m)

def _get_test_models(db):
    default_models = {
        'tags': db.get_tags(),
        'speakers': db.get_speakers(),
        'sources': db.get_sources(),
        'elicitation_methods': db.get_elicitation_methods(),
        'syntactic_categories': db.get_syntactic_categories(),
        'files': db.get_files()
    }
    return default_models

def _create_test_forms(db, dbsession, n=100):
    """Create n forms with various properties.  A testing ground for searches!
    """
    test_models = _get_test_models(db)
    users = db.get_users()
    viewer = [u for u in users if u.role == 'viewer'][0]
    contributor = [u for u in users if u.role == 'contributor'][0]
    administrator = [u for u in users if u.role == 'administrator'][0]
    for i in range(1, n + 1):
        f = old_models.Form()
        f.transcription = 'transcription %d' % i
        if i > 50:
            f.transcription = f.transcription.upper()
            administrator.remembered_forms.append(f)
        f.morpheme_break = 'morpheme_break %d' % i
        f.morpheme_gloss = 'morpheme_gloss %d' % i
        f.comments = 'comments %d' % i
        f.speaker_comments = 'speaker_comments %d' % i
        f.morpheme_break_ids = '[[[]]]'
        f.morpheme_gloss_ids = '[[[]]]'
        tl = old_models.Translation()
        tl.transcription = 'translation %d' % i
        f.enterer = contributor
        f.syntactic_category = test_models['syntactic_categories'][i - 1]
        if i > 75:
            f.phonetic_transcription = 'phonetic_transcription %d' % i
            f.narrow_phonetic_transcription = 'narrow_phonetic_transcription %d' % i
            t = test_models['tags'][i - 1]
            f.tags.append(t)
            tl.grammaticality = '*'
            viewer.remembered_forms.append(f)
        if i > 65 and i < 86:
            fi = test_models['files'][i - 1]
            f.files.append(fi)
            contributor.remembered_forms.append(f)
        #if (i -1) == 73:
        #    f.files.append(test_models['files'][70])
        if i > 50:
            f.elicitor = contributor
            if i != 100:
                f.speaker = test_models['speakers'][0]
                f.datetime_modified = TODAY_TIMESTAMP
                f.datetime_entered = TODAY_TIMESTAMP
        else:
            f.elicitor = administrator
            f.speaker = test_models['speakers'][-1]
            f.datetime_modified = YESTERDAY_TIMESTAMP
            f.datetime_entered = YESTERDAY_TIMESTAMP
        if i < 26:
            f.elicitation_method = test_models['elicitation_methods'][0]
            f.date_elicited = JAN1
        elif i < 51:
            f.elicitation_method = test_models['elicitation_methods'][24]
            f.date_elicited = JAN2
        elif i < 76:
            f.elicitation_method = test_models['elicitation_methods'][49]
            f.date_elicited = JAN3
        else:
            f.elicitation_method = test_models['elicitation_methods'][74]
            if i < 99:
                f.date_elicited = JAN4
        if (i > 41 and i < 53) or i in [86, 92, 3]:
            f.source = test_models['sources'][i]
        if i != 87:
            f.translations.append(tl)
        if i == 79:
            tl = old_models.Translation()
            tl.transcription = 'translation %d the second' % i
            f.translations.append(tl)
            t = test_models['tags'][i - 2]
            f.tags.append(t)
        dbsession.add(f)
    dbsession.commit()


def _create_test_data(db, dbsession, n=100):
    _create_test_models(dbsession, n)
    _create_test_forms(db, dbsession, n)


class TestFormsSearchView(TestView):

    n = 100

    def tearDown(self):
        self.tear_down_dbsession()

    def setUp(self):
        self.default_setup()

    # There are 24 distinct forms search tests (a-x).  Aside from the
    # requirement that the initialize "test" needs to run first, these create
    # tests do not need to be executed in the order determined by their names;
    # it just helps in locating them.
    def test_a_initialize(self):
        """Tests POST /forms/search: initialize database."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        self.create_db()
        # Add a bunch of data to the db.
        db.clear_all_models(['Language', 'User'])
        _create_test_data(db, dbsession, self.n)
        add_SEARCH_to_web_test_valid_methods()

    def test_search_b_equals(self):
        """Tests POST /forms/search: equals."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        # Simple == search on transcriptions
        json_query = json.dumps(
            {'query': {
                'filter': ['Form', 'transcription', '=',
                            'transcription 10']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1
        assert resp[0]['transcription'] == 'transcription 10'
        assert response.content_type == 'application/json'

    def test_search_c_not_equals(self):
        """Tests SEARCH /forms: not equals."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['not', ['Form', 'transcription', '=', 'transcription 10']]}})
        response = self.app.request(url('search'), method='SEARCH',
            body=json_query.encode('utf8'), headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == self.n - 1
        assert 'transcription 10' not in [f['transcription'] for f in resp]

    def test_search_d_like(self):
        """Tests POST /forms/search: like."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'like', '%1%']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 20  # 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 31, 41, 51, 61, 71, 81, 91, 100

        # Case-sensitive like.  This shows that _collate_attribute is working
        # as expected in SQLAQueryBuilder.
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'like', '%T%']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

        json_query = json.dumps(
            {'query': {'filter': ['or', [
                ['Form', 'transcription', 'like', 'T%'],
                ['Form', 'transcription', 'like', 't%']]]}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100

        # Testing the "_" wildcard
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'like', 'T_A%']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

    def test_search_e_not_like(self):
        """Tests SEARCH /forms: not like."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['not', ['Form', 'transcription', 'like', '%1%']]}})
        response = self.app.request(url('search'), method='SEARCH',
            body=json_query.encode('utf8'), headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 80

    def test_search_f_regexp(self):
        """Tests POST /forms/search: regular expression."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '[345]2']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert sorted([f['transcription'] for f in resp]) == \
            [u'TRANSCRIPTION 52', 'transcription 32', 'transcription 42']
        assert len(resp) == 3  # 32, 42, 52

        # Case-sensitive regexp.  This shows that _collate_attribute is working
        # as expected in SQLAQueryBuilder.
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '^T']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '^[Tt]']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100

        # Beginning and end of string anchors
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '^[Tt]ranscription 1.$']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 10
        assert response.content_type == 'application/json'

        # Quantifiers
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '2{2,}']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # Quantifiers
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '[123]{2,}']}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 9

        # Bad regex
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'regex', '[123]{3,2}']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['error'] == 'The specified search parameters generated an invalid database query'

    def test_search_g_not_regexp(self):
        """Tests SEARCH /forms: not regular expression."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['not', ['Form', 'transcription', 'regexp', '[345]2']]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 97

    def test_search_h_empty(self):
        """Tests POST /forms/search: is NULL."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'narrow_phonetic_transcription', '=', None]}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 75

        # Same as above but with a double negative
        json_query = json.dumps(
            {'query': {'filter': ['not', ['Form', 'narrow_phonetic_transcription', '!=', None]]}})
        response = self.app.post(url('search_post'), json_query,
                                    self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 75

    def test_search_i_not_empty(self):
        """Tests SEARCH /forms: is not NULL."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['not', ['Form', 'narrow_phonetic_transcription', '=', None]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 25

        # Same as above, but with !=, i.e., __ne__
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'narrow_phonetic_transcription', '!=', None]}})
        response = self.app.request(url('search'), body=json_query.encode('utf8'), method='SEARCH',
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 25

    def test_search_j_invalid_json(self):
        """Tests POST /forms/search: invalid JSON params."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        json_query = json.dumps(
            {'query': {'filter': ['not', ['Form', 'narrow_phonetic_transcription', '=', None]]}})
        json_query = json_query[:-1]  # Cut off the end to make it bad!
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['error'] == \
            'JSON decode error: the parameters provided were not valid JSON.'

    def test_search_k_malformed_query(self):
        """Tests SEARCH /forms: malformed query."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # TypeError - bad num args: 'NOT' will be treated as the first arg to
        # _get_simple_filter_expression and ['Form', 'transcription', '=', 10] will be passed
        # as the second -- two more are required.
        json_query = json.dumps({'query': {'filter': ['NOT', ['Form', 'id', '=', 10]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Malformed OLD query error'] == 'The submitted query was malformed'

        # After recognizing 'not', the query builder will look at only the next
        # list and ignore all the rest.
        json_query = json.dumps(
            {'query': {'filter':
                ['not',
                    ['Form', 'transcription', '=', 'transcription 10'], 
                    ['Form', 'transcription', '=', 'transcription 10'],
                    ['Form', 'transcription', '=', 'transcription 10']]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99
        assert 'transcription 10' not in [f['transcription'] for f in resp]

        # IndexError will be raised when python[1] is called.
        json_query = json.dumps({'query': {'filter': ['not']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Malformed OLD query error'] == 'The submitted query was malformed'

        # IndexError will be raised when python[0] is called.
        json_query = json.dumps({'query': {'filter': []}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Malformed OLD query error'] == 'The submitted query was malformed'

        # IndexError will be raised when python[1] is called.
        json_query = json.dumps({'query': {'filter': ['and']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Malformed OLD query error'] == 'The submitted query was malformed'
        assert resp['errors']['IndexError'] == 'list index out of range'

        # TypeError bad num args will be triggered when _get_simple_filter_expression is
        # called on a string whose len is not 4, i.e., 'id' or '='.
        json_query = json.dumps({'query': {'filter': ['and', ['Form', 'id', '=', '1099']]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert 'TypeError' in resp['errors']
        assert resp['errors']['Malformed OLD query error'] == 'The submitted query was malformed'

        # TypeError when asking whether [] is in a dict (lists are unhashable)
        json_query = json.dumps({'query': {'filter': [[], 'a', 'a', 'a']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['TypeError'] == "unhashable type: 'list'"
        assert resp['errors']['Malformed OLD query error'] == 'The submitted query was malformed'

        # With no 'query' attribute, the SQLAQueryBuilder will be passed None
        # will immediately raise an AttributeError.
        json_query = json.dumps({'filter': ['Form', 'id', '=', 2]})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['error'] == 'The specified search parameters generated an invalid database query'

        # With no 'filter' attribute, the SQLAQueryBuilder will be passed a list
        # will immediately raise an AttributeError when it tries to call [...].get('filter').
        json_query = json.dumps({'query': ['Form', 'id', '=', 2]})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['error'] == 'The specified search parameters generated an invalid database query'

    def test_search_l_lexical_semantic_error(self):
        """Tests POST /forms/search: lexical & semantic errors.

        These are when SQLAQueryBuilder.py raises a OLDSearchParseError because a
        relation is not permitted, e.g., 'contains', or not permitted for a
        given attribute.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # search_parser.py does not allow the contains relation (OLDSearchParseError)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'transcription', 'contains', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert 'Form.transcription.contains' in resp['errors']

        # old_models.Form.translations.__eq__('abcdefg') will raise a custom OLDSearchParseError
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'translations', '=', 'abcdefg']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['InvalidRequestError'] == \
            "Can't compare a collection to an object or collection; use contains() to test for membership."

        # old_models.Form.tags.regexp('xyz') will raise a custom OLDSearchParseError
        json_query = json.dumps({'query': {'filter': ['Form', 'tags', 'regex', 'xyz']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.tags.regex'] == 'The relation regex is not permitted for Form.tags'

        # old_models.Form.translations.like('transcription') will raise a custom OLDSearchParseError
        json_query = json.dumps({'query': {'filter': ['Form', 'translations', 'like', 'abc']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.translations.like'] == \
            'The relation like is not permitted for Form.translations'

        # old_models.Form.tags.__eq__('tag') will raise a custom OLDSearchParseError
        json_query = json.dumps({'query': {'filter': ['Form', 'tags', '__eq__', 'tag']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert 'InvalidRequestError' in resp['errors']

    def test_search_m_conjunction(self):
        """Tests SEARCH /forms: conjunction."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        users = db.get_users()
        contributor = [u for u in users if u.role == 'contributor'][0]
        models = _get_test_models(db)

        # 1 conjunct -- pointless, but it works...
        query = {'query': {'filter': [
            'and', [
                ['Form', 'transcription', 'like', '%2%']
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 19

        # 2 conjuncts
        query = {'query': {'filter': [
            'and', [
                ['Form', 'transcription', 'like', '%2%'],
                ['Form', 'transcription', 'like', '%1%']
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 2
        assert sorted([f['transcription'] for f in resp]) == ['transcription 12', 'transcription 21']

        # More than 2 conjuncts
        query = {'query': {'filter': [
            'and', [
                ['Form', 'transcription', 'like', '%1%'],
                ['Form', 'elicitor', 'id', '=', contributor.id],
                ['Form', 'elicitation_method', 'id', '=', models['elicitation_methods'][49].id]
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 3
        assert sorted([f['transcription'] for f in resp]) == \
            ['TRANSCRIPTION 51', 'TRANSCRIPTION 61', 'TRANSCRIPTION 71']

        # Multiple redundant conjuncts -- proof of possibility
        query = {'query': {'filter': [
            'and', [
                ['Form', 'transcription', 'like', '%1%'],
                ['Form', 'transcription', 'like', '%1%'],
                ['Form', 'transcription', 'like', '%1%'],
                ['Form', 'transcription', 'like', '%1%'],
                ['Form', 'transcription', 'like', '%1%'],
                ['Form', 'transcription', 'like', '%1%'],
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 20

    def test_search_n_disjunction(self):
        """Tests POST /forms/search: disjunction."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        users = db.get_users()
        contributor = [u for u in users if u.role == 'contributor'][0]

        # 1 disjunct -- pointless, but it works...
        query = {'query': {'filter': [
            'or', [
                ['Form', 'transcription', 'like', '%2%']   # 19 total
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 19

        # 2 disjuncts
        query = {'query': {'filter': [
            'or', [
                ['Form', 'transcription', 'like', '%2%'],    # 19; Total: 19
                ['Form', 'transcription', 'like', '%1%']     # 18 (20 but '12' and '21' shared with '2'); Total: 37
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 37

        # 3 disjuncts
        query = {'query': {'filter': [
            'or', [
                ['Form', 'transcription', 'like', '%2%'],    # 19; Total: 19
                ['Form', 'transcription', 'like', '%1%'],    # 18 (20 but '12' and '21' shared with '2'); Total: 37
                ['Form', 'elicitor', 'id', '=', contributor.id]   # 39 (50 but 11 shared with '2' and '1'); Total: 76
            ]
        ]}}
        json_query = json.dumps(query)
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 76
        assert response.content_type == 'application/json'

    def test_search_o_int(self):
        """Tests SEARCH /forms: integer searches."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        forms = db.get_forms()
        form_ids = [f.id for f in forms]

        # = int
        json_query = json.dumps({'query': {'filter': ['Form', 'id', '=', form_ids[1]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1
        assert resp[0]['id'] == form_ids[1]

        # < int (str)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'id', '<', str(form_ids[16])]}}) # Thanks to SQLAlchemy, a string will work here too
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 16

        # >= int
        json_query = json.dumps({'query': {'filter': ['Form', 'id', '>=', form_ids[97]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 3

        # in array
        json_query = json.dumps(
            {'query': {'filter':
                ['Form', 'id', 'in', [form_ids[12], form_ids[36], form_ids[28], form_ids[94]]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 4
        assert sorted([f['id'] for f in resp]) == [form_ids[12], form_ids[28], form_ids[36], form_ids[94]]

        # in None -- Error
        json_query = json.dumps({'query': {'filter': ['Form', 'id', 'in', None]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.id.in_'] == "Invalid filter expression: Form.id.in_(None)"
        assert response.content_type == 'application/json'

        # in int -- Error
        json_query = json.dumps({'query': {'filter': ['Form', 'id', 'in', 2]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.id.in_'] == "Invalid filter expression: Form.id.in_(2)"
        assert response.content_type == 'application/json'

        # regex int - The OLD's Python-based regexp implementation for SQLite will
        # automatically convert a non-string field value to a string before doing
        # the regexp comparison.  I believe that this parallels MySQL's regexp
        # behaviour accurately.
        str_patt = '[13][58]'
        patt = re.compile(str_patt)
        expected_id_matches = [f.id for f in forms if patt.search(str(f.id))]        
        json_query = json.dumps({'query': {'filter': ['Form', 'id', 'regex', '[13][58]']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len(expected_id_matches)
        assert sorted([f['id'] for f in resp]) == sorted(expected_id_matches)

        # like int - RDBMS treats ints as strings for LIKE search
        json_query = json.dumps({'query': {'filter': ['Form', 'id', 'like', '%2%']}})
        expected_matches = [i for i in form_ids if '2' in str(i)]
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len(expected_matches)

    def test_search_p_date(self):
        """Tests POST /forms/search: date searches."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # = date
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '=', JAN1.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 25
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '=', JAN4.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 23

        # != date -- *NOTE:* the NULL date_elicited values will not be counted.
        # The implicit query is 'is not null and != 2012-01-01'
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '!=', JAN1.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 73
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '!=', JAN4.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 75

        # To get what one really wants (perhaps), test for NULL too:
        query = {'query': {'filter': [
            'or', [['Form', 'date_elicited', '!=', JAN1.isoformat()],
                ['Form', 'date_elicited', '=', None]]]}}
        json_query = json.dumps(query)
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 75

        # < date
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '<', JAN1.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 0
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '<', JAN3.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

        # <= date
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '<=', JAN3.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 75

        # > date
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '>', JAN2.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 48
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '>', '0001-01-01']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 98

        # >= date
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '>=', JAN2.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 73

        # =/!= None
        json_query = json.dumps({'query': {'filter': ['Form', 'date_elicited', '=', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 2

        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '__ne__', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 98

    def test_search_q_date_invalid(self):
        """Tests SEARCH /forms: invalid date searches."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # = invalid date
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '=', '12-01-01']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['date 12-01-01'] == \
            'Date search parameters must be valid ISO 8601 date strings.'

        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', '=', '2012-01-32']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['date 2012-01-32'] == \
            'Date search parameters must be valid ISO 8601 date strings.'

        # regex on invalid date will fail because SQLA only allows Python datetime
        # objects as input on queries (though None is also allowed to test for nullness)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', 'regex', '01']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['date 01'] == \
            'Date search parameters must be valid ISO 8601 date strings.'

        # regex on valid date will work and will act just like = -- no point
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', 'regex', '2012-01-01']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 25

        # Same thing for like, it works like = but what's the point?
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', 'like', '2012-01-01']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 25

        # in_ on a date.  This will raise a TypeError ('datetime.date' object is
        # not iterable) that is caught in _get_filter_expression
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', 'in', '2012-01-02']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.date_elicited.in_'] == 'Invalid filter expression: Form.date_elicited.in_(datetime.date(2012, 1, 2))'

        # in_ on a list of dates works (SQLAQueryBuilder generates a list of date objects)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'date_elicited', 'in', ['2012-01-01', '2012-01-02']]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

    def test_search_r_datetime(self):
        """Tests POST /forms/search: datetime searches."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # = datetime
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '=', TODAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 49

        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '=', YESTERDAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

        # != datetime -- *NOTE:* the NULL datetime_entered values will not be counted.
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '!=', TODAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '!=', YESTERDAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 49

        # To get what one really wants (perhaps), test for NULL too:
        query = {'query': {'filter':
            ['or', [['Form', 'datetime_entered', '!=', TODAY_TIMESTAMP.isoformat()],
                ['Form', 'datetime_entered', '=', None]]]}}
        json_query = json.dumps(query)
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 51

        # < datetime
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '<', TODAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 50

        # <= datetime
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_modified', '<=', TODAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # > datetime
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '>', TODAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 0
        # Note: Python2.6/Debian(?) bug: using a year before 1900 will cause problems: 
        # ValueError: year=1 is before 1900; the datetime strftime() methods require year >= 1900
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '>', '1901-01-01T09:08:07']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # >= datetime
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '>=', YESTERDAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # =/!= None
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '=', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_entered', '__ne__', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # datetime in today
        midnight_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        midnight_tomorrow = midnight_today + DAY_DELTA
        query = {'query': {'filter':
            ['and', [['Form', 'datetime_entered', '>', midnight_today.isoformat()],
                            ['Form', 'datetime_entered', '<', midnight_tomorrow.isoformat()]]]}}
        json_query = json.dumps(query)
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 49

    def test_search_s_datetime_invalid(self):
        """Tests SEARCH /forms: invalid datetime searches."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # = invalid datetime
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_modified', '=', '12-01-01T09']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['datetime 12-01-01T09'] == \
            'Datetime search parameters must be valid ISO 8601 datetime strings.'

        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_modified', '=', '2012-01-30T09:08:61']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['datetime 2012-01-30T09:08:61'] == \
            'Datetime search parameters must be valid ISO 8601 datetime strings.'

        # Trailing period and too many microseconds will both succeed.
        json_query = json.dumps({'query': {'filter':
                ['Form', 'datetime_modified', '=', '2012-01-30T09:08:59.123456789123456789123456789']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        json_query = json.dumps({'query': {'filter':
            ['Form', 'datetime_modified', '=', '2012-01-30T09:08:59.']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)

        # regex on invalid datetime will fail because SQLA only allows Python datetime
        # objects as input on queries (though None is also allowed to test for nullness)
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'datetime_modified', 'regex', '01']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['datetime 01'] == \
            'Datetime search parameters must be valid ISO 8601 datetime strings.'

        # regex on valid datetime will work and will similarly to equality test.
        # NOTE: I TURNED OFF THIS TEST BECAUSE MySQL datetime behaviour with MyISAM/InnoDB on Mac/Linux
        # is inconsistent and extremeely frustrating !!!
        RDBMSName = h.get_RDBMS_name(self.settings)
        if RDBMSName == 'mysql':
            if MYSQL_ENGINE == 'InnoDB':
                _today_timestamp = h.round_datetime(TODAY_TIMESTAMP).isoformat()
            else:
                _today_timestamp = TODAY_TIMESTAMP.isoformat().split('.')[0]
        else:
            _today_timestamp = TODAY_TIMESTAMP.isoformat()
        json_query = json.dumps({'query': {'filter':
                ['Form', 'datetime_modified', 'regex', _today_timestamp]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        #assert len(resp) == 49

        # Same thing for like, it works like = but what's the point?
        json_query = json.dumps({'query': {'filter':
                ['Form', 'datetime_modified', 'like', _today_timestamp]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        #assert len(resp) == 49

        # in_ on a datetime.  This will raise a TypeError ('datetime.datetime' object is
        # not iterable) that is caught in _get_filter_expression
        json_query = json.dumps({'query': {'filter':
            ['Form', 'datetime_modified', 'in', TODAY_TIMESTAMP.isoformat()]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        error_prefix = 'Invalid filter expression: Form.datetime_modified.in_'
        received_error = resp['errors']['Form.datetime_modified.in_']
        assert received_error.startswith(error_prefix)

        # in_ on a list of datetimes works (SQLAQueryBuilder generates a list of datetime objects)
        json_query = json.dumps({'query': {'filter':
            ['Form', 'datetime_modified', 'in',
                [TODAY_TIMESTAMP.isoformat(), YESTERDAY_TIMESTAMP.isoformat()]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

    def test_search_t_many_to_one(self):
        """Tests POST /forms/search: searches on many-to-one attributes."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        test_models = _get_test_models(db)
        users = db.get_users()
        forms = db.get_forms()
        contributor = [u for u in users if u.role == 'contributor'][0]

        # = int
        json_query = json.dumps(
            {'query': {'filter': ['Form', 'enterer', 'id', '=', contributor.id]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100

        json_query = json.dumps({'query': {'filter':
            ['Form', 'speaker', 'id', '=', test_models['speakers'][0].id]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 49

        # in array of ints
        json_query = json.dumps({'query': {'filter':
            ['Form', 'speaker', 'id', 'in', [s.id for s in test_models['speakers']]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # <
        json_query = json.dumps({'query': {'filter':
            ['Form', 'elicitation_method', 'id', '<', 56]}})
        expected_forms = [f for f in db.get_forms() if f.elicitationmethod_id < 56]
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len(expected_forms)

        # regex
        json_query = json.dumps({'query': {'filter':
            ['Form', 'elicitation_method', 'name', 'regex', '5']}})
        expected_forms = [f for f in db.get_forms() if '5' in f.elicitation_method.name]
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len(expected_forms)

        json_query = json.dumps({'query': {'filter':
            ['Form', 'elicitation_method', 'id', 'regex', '[56]']}})
        expected_forms = [f for f in db.get_forms() 
            if '5' in str(f.elicitationmethod_id) or '6' in str(f.elicitationmethod_id)] 
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len(expected_forms)

        # like
        json_query = json.dumps({'query': {'filter':
            ['Form', 'syntactic_category', 'name', 'like', '%5%']}})
        expected_forms = [f for f in db.get_forms() if '5' in f.syntactic_category.name]
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len(expected_forms)

        # Show how we can search things other than ids
        json_query = json.dumps({'query': {'filter':
            ['Form', 'syntactic_category', 'name', 'like', '%5%']}})
        expected_forms = [f for f in db.get_forms() if '5' in f.syntactic_category.name]
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp
        assert len(resp) == len(expected_forms)
        assert response.content_type == 'application/json'

        # Searching for the presence/absence of a many-to-one relation
        json_query = json.dumps({'query': {'filter': ['Form', 'source', '!=', None]}})
        expected_forms = [f for f in db.get_forms() if f.source]
        response = self.app.post(url('search_post'), json_query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp
        assert len(resp) == len(expected_forms)
        json_query = json.dumps({'query': {'filter': ['Form', 'source', '=', None]}})
        expected_forms = [f for f in db.get_forms() if not f.source]
        response = self.app.post(url('search_post'), json_query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp
        assert len(resp) == len(expected_forms)

    def test_search_u_one_to_many(self):
        """Tests SEARCH /forms: searches on one-to-many attributes, viz. Translation."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # translation.transcription =
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'transcription', '=', 'translation 1']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # translation.transcription = (with any())
        json_query = json.dumps({'query': {'filter':
            ['Form', 'translations', 'transcription', '=', 'translation 1']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # translation.transcription_grammaticality
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'grammaticality', '=', '*']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 24

        # translation.transcription like
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'transcription', 'like', '%1%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 20

        # translation.transcription regexp
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'transcription', 'regex', '[13][25]']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 4

        # translation.transcription in_
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'transcription', 'in_', [u'translation 1', 'translation 2']]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 2

        # translation.transcription <
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'transcription', '<', 'z']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # translation.datetime_modified
        json_query = json.dumps({'query': {'filter':
            ['Translation', 'datetime_modified', '>', YESTERDAY_TIMESTAMP.isoformat()]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # To search for the presence/absence of translations, one must use the
        # translations attribute of the Form model, =/!= and None.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'translations', '=', None]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # Using an empty list to test for presence of translations fails too.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'translations', '=', []]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['InvalidRequestError'] == \
            "Can't compare a collection to an object or collection; use contains() to test for membership."

        json_query = json.dumps({'query': {'filter':
            ['Form', 'translations', '!=', None]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 99

        # Using anything other than =/!= on Form.translations will raise an error.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'translations', 'like', None]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.translations.like'] == 'The relation like is not permitted for Form.translations'

        # Using a value other than None on Form.translations will also raise an error
        json_query = json.dumps({'query': {'filter':
            ['Form', 'translations', '=', 'translation 1']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['InvalidRequestError'] == \
            "Can't compare a collection to an object or collection; use contains() to test for membership."

        # Search based on two distinct translations (only Form #79 has two) ...
        json_query = json.dumps({'query': {'filter':
            ['and', [
                ['Translation', 'transcription', '=', 'translation 79'],
                ['Translation', 'transcription', '=', 'translation 79 the second']]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # ... one is ungrammatical, the other is unspecified
        json_query = json.dumps({'query': {'filter':
            ['and', [
                ['Translation', 'grammaticality', '=', '*'],
                ['Translation', 'grammaticality', '=', None]]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # Same search as above but using has()
        json_query = json.dumps({'query': {'filter':
            ['and', [
                ['Form', 'translations', 'grammaticality', '=', '*'],
                ['Form', 'translations', 'grammaticality', '=', None]]]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

    def test_search_v_many_to_many(self):
        """Tests POST /forms/search: searches on many-to-many attributes, i.e., Tag, File, Collection, User."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # tag.name =
        json_query = json.dumps({'query': {'filter': ['Tag', 'name', '=', 'name 76']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # file.name like
        json_query = json.dumps({'query': {'filter':
            ['File', 'name', 'like', '%name 6%']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 4

        # file.name regexp
        json_query = json.dumps({'query': {'filter':
            ['File', 'name', 'regex', 'name [67]']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 14

        # Same regexp on file.name as above exceupt using the SQLA ORM's any()
        json_query = json.dumps({'query': {'filter':
            ['Form', 'files', 'name', 'regex', 'name [67]']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 14

        # tag.name in_
        json_query = json.dumps({'query': {'filter':
            ['Tag', 'name', 'in_', [u'name 77', 'name 79', 'name 99']]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 3

        # tag.name <
        json_query = json.dumps({'query': {'filter':
            ['Tag', 'name', '<', 'name 8']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 5   # 76, 77, 78, 79, 100

        # file.datetime_modified
        json_query = json.dumps({'query': {'filter':
            ['File', 'datetime_modified', '>', YESTERDAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 20  # All forms with a file attached

        json_query = json.dumps({'query': {'filter':
            ['File', 'datetime_modified', '<', YESTERDAY_TIMESTAMP.isoformat()]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 0

        # To search for the presence/absence of tags/files/collections, one must use the
        # tags/files/collections attributes of the Form old_models.
        json_query = json.dumps({'query': {'filter': ['Form', 'tags', '=', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 75

        json_query = json.dumps({'query': {'filter': ['Form', 'files', '!=', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 20

        # Using anything other than =/!= on Form.tags/files/collections will raise an error.
        json_query = json.dumps({'query': {'filter': ['Form', 'tags', 'like', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.tags.like'] == 'The relation like is not permitted for Form.tags'

        json_query = json.dumps({'query': {'filter':
            ['Form', 'files', '=', 'file 80']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['InvalidRequestError'] == \
            "Can't compare a collection to an object or collection; use contains() to test for membership."

        # tag.name in_ with double matches (Form #79 has Tags #78 and #79)
        json_query = json.dumps({'query': {'filter':
            ['Tag', 'name', 'in_', [u'name 78', 'name 79']]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 2

        # Form #79 has Tags #78 and #79
        json_query = json.dumps({'query': {'filter':
            ['and', [
                ['Tag', 'name', '=', 'name 78'],
                ['Tag', 'name', '=', 'name 79']]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # Form #79 has Tags #78 and #79, Form #78 has Tag #78
        json_query = json.dumps({'query': {'filter':
            ['Tag', 'name', '=', 'name 78']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 2

        # Form #79 has Tags #78 and #79
        json_query = json.dumps({'query': {'filter':
            ['and', [
                ['Tag', 'name', '=', 'name 78'],
                ['Tag', 'name', '=', 'name 79']]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # Search forms by memorizer

        # Get some pertinent data
        forms = db.get_forms()
        users = db.get_users()
        viewer_remembered_forms = [f for f in forms
                                    if int(f.transcription.split(' ')[-1]) > 75]

        contributor = [u for u in users if u.role == 'contributor'][0] # i > 65, i < 86
        contributor_remembered_forms = [f for f in forms
                                    if int(f.transcription.split(' ')[-1]) > 65 and
                                    int(f.transcription.split(' ')[-1]) < 86]
        contributor_id = contributor.id
        administrator_remembered_forms = [f for f in forms
                                    if int(f.transcription.split(' ')[-1]) > 50]

        # Everything memorized by admins and viewers
        json_query = json.dumps({'query': {'filter':
            ['Memorizer', 'role', 'in', [u'administrator', 'viewer']]}})
        response = self.app.post(url('search_post'), json_query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = list(set(viewer_remembered_forms) | set(administrator_remembered_forms))
        assert set([f['id'] for f in resp]) == set([f.id for f in result_set])

        # Try the same query as above except use the "memorizers" attribute
        json_query = json.dumps({'query': {'filter':
            ['Form', 'memorizers', 'role', 'in', [u'administrator', 'viewer']]}})
        response = self.app.post(url('search_post'), json_query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert set([f['id'] for f in resp]) == set([f.id for f in result_set])

        # Everything memorized by the contributor matching a regex
        json_query = json.dumps({'query': {'filter':
            ['and', [['Memorizer', 'id', '=', contributor_id],
                        ['Form', 'transcription', 'regex', '[13580]']]]}})
        response = self.app.post(url('search_post'), json_query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = [f for f in contributor_remembered_forms
                        if re.search('[13580]', f.transcription)]
        assert set([f['id'] for f in resp]) == set([f.id for f in result_set])
        assert response.content_type == 'application/json'

        # The same query as above except use the "memorizers" attribute
        json_query = json.dumps({'query': {'filter':
            ['and', [['Form', 'memorizers', 'id', '=', contributor_id],
                        ['Form', 'transcription', 'regex', '[13580]']]]}})
        response = self.app.post(url('search_post'), json_query, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert set([f['id'] for f in resp]) == set([f.id for f in result_set])
        assert response.content_type == 'application/json'

        # Invalid memorizer search
        json_query = json.dumps({'query': {'filter': ['Memorizer', 'username', 'like', '%e%']}})
        response = self.app.post(url('search_post'), json_query,
                self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['errors']['Memorizer.username'] == 'Searching on Memorizer.username is not permitted'

        # Invalid memorizer search using the "memorizers" attribute
        json_query = json.dumps({'query': {'filter': ['Form', 'memorizers', 'username', 'like', '%e%']}})
        response = self.app.post(url('search_post'), json_query,
                self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert response.content_type == 'application/json'
        assert resp['errors']['User.username'] == 'Searching on User.username is not permitted'

    def test_search_w_in(self):
        """Tests SEARCH /forms: searches using the in_ relation."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Array value -- all good.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'in', ['transcription 1']]}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1

        # String value -- no error because strings are iterable; but no results
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'in', 'transcription 1']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 0

    def fix_form(self, form):
        for key, val in form.items():
            if isinstance(val, (datetime, date)):
                form[key] = val.isoformat()
        return form

    def test_search_x_complex(self):
        """Tests POST /forms/search: complex searches."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        forms = json.loads(json.dumps([self.fix_form(f.get_dict()) for f in db.get_forms()]))
        RDBMSName = h.get_RDBMS_name(self.settings)

        # A fairly complex search
        json_query = json.dumps({'query': {'filter': [
            'and', [
                ['Translation', 'transcription', 'like', '%1%'],
                ['not', ['Form', 'morpheme_break', 'regex', '[18][5-7]']],
                ['or', [
                    ['Form', 'datetime_modified', '=', TODAY_TIMESTAMP.isoformat()],
                    ['Form', 'date_elicited', '=', JAN1.isoformat()]]]]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body

        # Emulate the search Pythonically
        MYSQL_ENGINE = old_models.Model.__table_args__.get('mysql_engine')
        if RDBMSName == 'mysql' and MYSQL_ENGINE == 'InnoDB':
            _today_timestamp = h.round_datetime(TODAY_TIMESTAMP)
        else:
            _today_timestamp = TODAY_TIMESTAMP
        result_set = [f for f in forms if
            '1' in ' '.join([g['transcription'] for g in f['translations']]) and
            not re.search('[18][5-7]', f['morpheme_break']) and
            (_today_timestamp.isoformat().split('.')[0] == f['datetime_modified'].split('.')[0] or
                (f['date_elicited'] and JAN1.isoformat() == f['date_elicited']))]
        assert len(resp) == len(result_set)

        # A complex search entailing multiple joins
        tag_names = ['name 2', 'name 4', 'name 88']
        patt = '([13579][02468])|([02468][13579])'
        json_query = json.dumps({'query': {'filter': [
            'or', [
                ['Translation', 'transcription', 'like', '%1%'],
                ['Tag', 'name', 'in', ['name 2', 'name 4', 'name 88']],
                ['and', [
                    ['not', ['File', 'name', 'regex', patt]],
                    ['Form', 'date_elicited', '!=', None]]]]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body

        # Emulate the search in Python
        # Note that the Python-based regexp for SQLite requires that the attribute
        # being searched be Python-truthy in order for the pattern to match.  I doubt
        # that this is the behaviour of MySQL's regexp...
        result_set = [f for f in forms if
            '1' in ' '.join([g['transcription'] for g in f['translations']]) or
            set([t['name'] for t in f['tags']]) & set(tag_names) or
            (f['files'] and
                not re.search(patt, ', '.join([fi['name'] for fi in f['files']])) and
                f['date_elicited'] is not None)]
        assert len(resp) == len(result_set)

        # A super complex search ...  The implicit assertion is that a 200 status
        # code is returned.  At this point I am not going to bother attempting to
        # emulate this query in Python ...
        json_query = json.dumps({'query': {'filter': [
            'and', [
                ['Form', 'transcription', 'like', '%5%'],
                ['Form', 'morpheme_break', 'like', '%9%'],
                ['not', ['Translation', 'transcription', 'like', '%6%']],
                ['or', [
                    ['Form', 'datetime_entered', '<', TODAY_TIMESTAMP.isoformat()],
                    ['Form', 'datetime_modified', '>', YESTERDAY_TIMESTAMP.isoformat()],
                    ['not', ['Form', 'date_elicited', 'in', [JAN1.isoformat(), JAN3.isoformat()]]],
                    ['and', [
                        ['Form', 'enterer', 'id', 'regex', '[135680]'],
                        ['Form', 'id', '<', 90]
                    ]]
                ]],
                ['not', ['not', ['not', ['Tag', 'name', '=', 'name 7']]]]
            ]
        ]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body

    def test_search_y_paginator(self):
        """Tests SEARCH /forms: paginator."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        forms = json.loads(json.dumps([self.fix_form(f.get_dict()) for f in db.get_forms()]))

        # A basic search with a paginator provided.
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'like', '%T%']},
            'paginator': {'page': 2, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        result_set = [f for f in forms if 'T' in f['transcription']]
        assert resp['paginator']['count'] == len(result_set)
        assert len(resp['items']) == 10
        assert resp['items'][0]['id'] == result_set[10]['id']
        assert resp['items'][-1]['id'] == result_set[19]['id']

        # An invalid paginator (here 'page' is less than 1) will result in formencode.Invalid
        # being raised resulting in a response with a 400 status code and a JSON error msg.
        json_query = json.dumps({
            'query': {
                'filter': ['Form', 'transcription', 'like', '%T%']},
            'paginator': {'page': 0, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'

        # Some "invalid" paginators will silently fail.  For example, if there is
        # no 'pages' key, then GET /forms will just assume there is no paginator
        # and all of the results will be returned.
        json_query = json.dumps({
            'query': {
                'filter': ['Form', 'transcription', 'like', '%T%']},
            'paginator': {'pages': 0, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len([f for f in forms if 'T' in f['transcription']])

        # Adding a 'count' key to the paginator object in the request will spare
        # the server from running query.count().  Note that the server will not
        # attempt to verify the count (since that would defeat the purpose) but
        # will simply pass it back.  The server trusts that the client is passing
        # in a factual count.  Here we pass in an inaccurate count for demonstration.
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'like', '%T%']},
            'paginator': {'page': 2, 'items_per_page': 16, 'count': 750}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['paginator']['count'] == 750
        assert len(resp['items']) == 16
        assert resp['items'][0]['id'] == result_set[16]['id']
        assert resp['items'][-1]['id'] == result_set[31]['id']

    def test_search_z_order_by(self):
        """Tests POST /forms/search: order by."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        # order by transcription ascending
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Form', 'transcription', 'asc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[-1]['transcription'] == 'TRANSCRIPTION 99'
        assert resp[0]['transcription'] == 'transcription 1'

        # order by transcription descending
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Form', 'transcription', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[-1]['transcription'] == 'transcription 1'
        assert resp[0]['transcription'] == 'TRANSCRIPTION 99'

        # order by translation ascending
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Translation', 'transcription', 'asc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[0]['translations'] == [] # Form # 87 has no translations
        assert resp[1]['translations'][0]['transcription'] == 'translation 1'
        assert resp[-1]['translations'][0]['transcription'] == 'translation 99'

        # order by with missing direction defaults to 'asc'
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Translation', 'transcription']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[0]['translations'] == [] # Form # 87 has no translations
        assert resp[1]['translations'][0]['transcription'] == 'translation 1'
        assert resp[-1]['translations'][0]['transcription'] == 'translation 99'

        # order by with unknown direction defaults to 'asc'
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Translation', 'transcription', 'descending']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[0]['translations'] == [] # Form # 87 has no translations
        assert resp[1]['translations'][0]['transcription'] == 'translation 1'
        assert resp[-1]['translations'][0]['transcription'] == 'translation 99'

        # syntactically malformed order by
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Translation']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'

        # searches with lexically malformed order bys
        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Form', 'foo', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Form.foo'] == 'Searching on Form.foo is not permitted'
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'

        json_query = json.dumps({'query': {
                'filter': ['Form', 'transcription', 'regex', '[tT]'],
                'order_by': ['Foo', 'id', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Foo'] == 'Searching the Form model by joining on the Foo model is not possible'
        assert resp['errors']['Foo.id'] == 'Searching on Foo.id is not permitted'
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'

    def test_search_za_restricted(self):
        """Tests SEARCH /forms: restricted forms."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # First restrict the even-numbered forms
        restricted_tag = omb.generate_restricted_tag()
        dbsession.add(restricted_tag)
        dbsession.commit()
        restricted_tag = db.get_restricted_tag()
        forms = db.get_forms()
        form_count = len(forms)
        for form in forms:
            if int(form.transcription.split(' ')[-1]) % 2 == 0:
                form.tags.append(restricted_tag)
        dbsession.commit()
        restricted_forms = dbsession.query(old_models.Form).filter(
            old_models.Tag.name=='restricted').outerjoin(old_models.Form.tags).all()
        restricted_form_count = len(restricted_forms)

        # A viewer will only be able to see the unrestricted forms
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'regex', '[tT]']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_view)
        resp = response.json_body
        assert len(resp) == restricted_form_count
        assert 'restricted' not in [
            x['name'] for x in reduce(list.__add__, [f['tags'] for f in resp])]

        # An administrator will be able to access all forms
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'regex', '[tT]']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == form_count
        assert 'restricted' in [
            x['name'] for x in reduce(list.__add__, [f['tags'] for f in resp])]

        # Filter out restricted forms and do pagination
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'regex', '[tT]']},
            'paginator': {'page': 3, 'items_per_page': 7}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_view)
        resp = response.json_body
        result_set = [f for f in db.get_forms()
                        if int(f.transcription.split(' ')[-1]) % 2 != 0]
        assert resp['paginator']['count'] == restricted_form_count
        assert len(resp['items']) == 7
        assert resp['items'][0]['id'] == result_set[14].id

    def test_search_zb_like_escaping(self):
        """Tests SEARCH /forms: escaping special characters in LIKE queries.

        Note: these tests are RDBMS-specific: MySQL allows escaping of "_" and
        "%" in LIKE queries via the backslash.  In SQLite, on the other hand,
        the backslash only works if "ESCAPE '\'" is specified after the LIKE
        pattern.  As far as I can tell, this is not supported in SQLAlchemy.
        Therefore, any OLD system using SQLite will not permit searching for "_"
        or "%" in LIKE queries (regexp will do the trick though...).
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        create_params = self.form_create_params
        RDBMSName = h.get_RDBMS_name(self.settings)

        # Create a form with an underscore and a percent sign in it.
        params = create_params.copy()
        params.update({
            'transcription': '_%',
            'translations': [{'transcription': 'LIKE, test or some junk',
                            'grammaticality': ''}]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)

        forms = dbsession.query(old_models.Form).all()
        forms_count = len(forms)

        # Show how the underscore is a wildcard when unescaped: all forms will
        # be returned.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'like', '%_%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == forms_count
        assert response.content_type == 'application/json'

        # Show how the underscore can be escaped and we can use it to match the
        # one underscore-containing form in the db (*in MySQL only*).
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'like', '%\_%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        if RDBMSName == 'mysql':
            assert len(resp) == 1
        else:
            assert len(resp) == 0
        assert response.content_type == 'application/json'

        # Show how we can use a regexp search to match the underscore in SQLite
        # (and MySQL).
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'regexp', '_']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1
        assert response.content_type == 'application/json'

        # Show how the percent sign is a zero-or-more-anything quantifier when
        # unescaped: all forms will be returned.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'like', '%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == forms_count
        assert response.content_type == 'application/json'

        # Show how the percent sign can be escaped and we can use it to match the
        # one percent sign-containing form in the db (*in MySQL only*).
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'like', '%\%%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        if RDBMSName == 'mysql':
            assert len(resp) == 1
        else:
            assert len(resp) == 0
        assert response.content_type == 'application/json'

        # Show how we can use a regexp search to match the percent sign in both
        # RDBMSs.
        json_query = json.dumps({'query': {'filter':
            ['Form', 'transcription', 'regexp', '%']}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 1
        assert response.content_type == 'application/json'

    def test_z_cleanup(self):
        """Tests POST /forms/search: clean up the database."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Clear the remembered forms of all the users
        users = db.get_users()
        viewer = [u for u in users if u.role == 'viewer'][0]
        contributor = [u for u in users if u.role == 'contributor'][0]
        administrator = [u for u in users if u.role == 'administrator'][0]
        viewer.remembered_forms = []
        contributor.remembered_forms = []
        administrator.remembered_forms = []
        dbsession.commit()

        # Remove all models and recreate the users
        db.clear_all_models()
        administrator = omb.generate_default_administrator(settings=self.settings)
        contributor = omb.generate_default_contributor(settings=self.settings)
        viewer = omb.generate_default_viewer(settings=self.settings)
        dbsession.add_all([administrator, contributor, viewer])
        dbsession.commit()

        super().tearDown()
