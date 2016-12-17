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
import re
from time import sleep

from old.lib.bibtex import ENTRY_TYPES
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
from old.models import Source
import old.models as old_models
import old.models.modelbuilders as omb
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods


LOGGER = logging.getLogger(__name__)


url = Source._url()


################################################################################
# Functions for creating & retrieving test data
################################################################################

today_timestamp = datetime.datetime.now()
day_delta = datetime.timedelta(1)
yesterday_timestamp = today_timestamp - day_delta

def _create_test_models(dbsession, n=100):
    _add_test_models_to_session(dbsession, 'File', n, ['name'])
    dbsession.commit()

def _add_test_models_to_session(dbsession, model_name, n, attrs):
    for i in range(1, n + 1):
        m = getattr(old_models, model_name)()
        for attr in attrs:
            setattr(m, attr, '%s %s' % (attr, i))
        dbsession.add(m)

def _get_test_models(db):
    return {'files': db.get_files()}

def _create_test_sources(dbsession, db, n=100):
    """Create n sources with various properties.  A testing ground for searches!
    """
    files = _get_test_models(db)['files']

    for i in range(1, n + 1):
        s = old_models.Source()
        s.key = str(i)
        if i in range(1, 11):
            s.type = 'article'
            s.author = 'Author Mc%d' % i
            s.title = 'Title %d' % i
            s.journal = 'Journal %d' % i
            s.year = int('199%s' % str(i)[-1])
        elif i in range(11, 21):
            s.type = 'book'
            s.author = 'Author Mc%d' % i
            s.title = 'Title %d' % i
            s.journal = 'Publisher %d' % i
            s.year = int('199%s' % str(i)[-1])
        elif i in range(21, 31):
            s.type = 'booklet'
            s.title = 'Title %d' % i
        elif i in range(31, 41):
            s.type = 'conference'
            s.author = 'Author Mc%d' % i
            s.title = 'Title %d' % i
            s.booktitle = 'Book Title %d' % i
            s.year = int('199%s' % str(i)[-1])
        elif i in range(41, 51):
            s.type = 'inbook'
            s.editor = 'Editor Mc%d' % i
            s.title = 'Title %d' % i
            s.chapter = str(i)
            s.pages = '9--36'
            s.publisher = 'Publisher %d' % i
            s.year = int('199%s' % str(i)[-1])
        elif i in range(51, 61):
            s.type = 'incollection'
            s.author = 'Author Mc%d' % i
            s.title = 'Title %d' % i
            s.booktitle = 'Book Title %d' % i
            s.publisher = 'Publisher %d' % i
            s.year = int('199%s' % str(i)[-1])
        elif i in range(61, 71):
            s.type = 'inproceedings'
            s.author = 'Author Mc%d' % i
            s.title = 'Title %d' % i
            s.booktitle = 'Book Title %d' % i
            s.year = int('199%s' % str(i)[-1])
        elif i in range(71, 81):
            s.type = 'manual'
            s.title = 'Title %d' % i
        elif i in range(81, 91):
            s.type = 'mastersthesis'
            s.author = 'Author Mc%d' % i
            s.title = 'Title %d' % i
            s.school = 'The University of %d' % i
            s.year = int('199%s' % str(i)[-1])
        else:
            s.type = 'misc'

        if i % 2 == 0:
            s.file_id = files[i - 1].id

        if i > 8:
            s.datetime_modified = yesterday_timestamp

        dbsession.add(s)
    dbsession.commit()


def _create_test_data(dbsession, db, n=100):
    _create_test_models(dbsession, n)
    _create_test_sources(dbsession, db, n)


class TestSourcesView(TestView):

    def test_index(self):
        """Tests that GET /sources returns an array of all sources and that order_by and pagination parameters work correctly."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add 100 sources.
        def create_source_from_index(index):
            source = old_models.Source()
            source.type = 'book'
            source.key = 'key%d' % index
            source.author = 'Chomsky, N.'
            source.title = 'Syntactic Structures %d' % index
            source.publisher = 'Mouton'
            source.year = 1957
            return source
        sources = [create_source_from_index(i) for i in range(1, 101)]
        dbsession.add_all(sources)
        dbsession.commit()
        sources = db.get_sources(True)
        sources_count = len(sources)

        # Test that GET /sources gives us all of the sources.
        extra_environ = self.extra_environ_view
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == sources_count
        assert resp[0]['title'] == 'Syntactic Structures 1'
        assert resp[0]['id'] == sources[0].id
        assert response.content_type == 'application/json'

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['title'] == sources[46].title
        assert response.content_type == 'application/json'

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'Source', 'order_by_attribute': 'title',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        result_set = sorted([s.title for s in sources], reverse=True)
        assert result_set == [s['title'] for s in resp]
        assert response.content_type == 'application/json'

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'Source', 'order_by_attribute': 'title',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert result_set[46] == resp['items'][0]['title']

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'Source', 'order_by_attribute': 'title',
                        'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"
        assert response.content_type == 'application/json'

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'Sourceful', 'order_by_attribute': 'titular',
                        'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert resp[0]['id'] == sources[0].id

        # Expect a 400 error when the paginator GET params are empty
        # or are integers less than 1
        paginator = {'items_per_page': 'a', 'page': ''}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter an integer value'
        assert resp['errors']['page'] == 'Please enter a value'
        assert response.content_type == 'application/json'

        paginator = {'items_per_page': 0, 'page': -1}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter a number that is 1 or greater'
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'
        assert response.content_type == 'application/json'

    def test_create(self):
        """Tests that POST /sources creates a new source or returns an appropriate error
        if the input is invalid.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        ########################################################################
        # BOOK
        ########################################################################

        # Attempt to create a source that has an invalid BibTeX entry type and
        # expect to fail.  Also, check that the length restrictions on the other
        # fields are working too.
        params = self.source_create_params.copy()
        params.update({
            'type': 'novella',
            'author': 'author' * 255
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['type'] == 'novella is not a valid BibTeX entry type'
        assert resp['errors']['author'] == 'Enter a value not more than 255 characters long'
        assert response.content_type == 'application/json'

        # Create a book; required: author or editor, title, publisher and year
        params = self.source_create_params.copy()
        params.update({
            'type': 'bOOk',    # case is irrelevant for entry types
            'key': 'chomsky57',
            'author': 'Noam Chomsky',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957,
            'edition': 'second',   # good optional attribute for a book
            'school': 'Stanford'   # doesn't make sense for a book, but it will still be saved
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'book'      # the OLD converts type to lowercase
        assert resp['school'] == 'Stanford'
        assert resp['edition'] == 'second'
        assert resp['booktitle'] == ''
        assert resp['author'] == 'Noam Chomsky'
        assert response.content_type == 'application/json'

        # Attempt to create another book with the same key and expect to fail.
        params = self.source_create_params.copy()
        params.update({
            'type': 'bOOk',
            'key': 'chomsky57',    # This duplicate is the bad part.
            'author': 'Fred Smith',
            'title': 'Structures Syntax-wise',
            'publisher': 'Backwoods Publishing',
            'year': 1984
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        new_sources_count = dbsession.query(Source).count()
        assert sources_count == new_sources_count
        assert resp['errors']['key'] == 'The submitted source key is not unique'
        assert response.content_type == 'application/json'

        # Attempt to create another book with an invalid key and expect to fail.
        params = self.source_create_params.copy()
        params.update({
            'type': 'bOOk',
            'key': 'cho\u0301msky57',    # Unicode characters are not permitted, PERHAPS THEY SHOULD BE? ...
            'author': 'Fred Smith',
            'title': 'Structures Syntax-wise',
            'publisher': 'Backwoods Publishing',
            'year': 1984
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        new_sources_count = dbsession.query(Source).count()
        assert sources_count == new_sources_count
        assert resp['errors']['key'] == 'Source keys can only contain letters, numerals and symbols (except the comma)'

        # Attempt to create a book source that is invalid because it lacks a year.
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57a',
            'author': 'Noam Chomsky',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'edition': 'second'   # good optional attribute for a book
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['errors'] == \
            'Sources of type book require values for title, publisher and year as well as a value for at least one of author and editor.'
        assert sources_count == new_sources_count
        assert response.content_type == 'application/json'

        # Attempt to create a book source that is invalid because it lacks both
        # author and editor 
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57a',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['errors'] == \
            'Sources of type book require values for title, publisher and year as well as a value for at least one of author and editor.'
        assert sources_count == new_sources_count
        assert response.content_type == 'application/json'

        ########################################################################
        # ARTICLE
        ########################################################################

        # Create an article; required: author, title, journal, year
        params = self.source_create_params.copy()
        params.update({
            'type': 'Article',    # case is irrelevant for entry types
            'key': 'bloomfield46',
            'author': 'Bloomfield, L.',
            'title': 'Algonquian',
            'year': 1946,
            'journal': 'Linguistic Structures of Native America',
            'pages': '85--129'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'article'      # the OLD converts type to lowercase
        assert resp['title'] == 'Algonquian'
        assert resp['author'] == 'Bloomfield, L.'
        assert resp['journal'] == 'Linguistic Structures of Native America'
        assert resp['pages'] == '85--129'
        assert resp['year'] == 1946
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'

        # Attempt to create an article without a year and expect to fail
        params = self.source_create_params.copy()
        params.update({
            'type': 'Article',    # case is irrelevant for entry types
            'key': 'bloomfieldL46',
            'author': 'Bloomfield, L.',
            'title': 'Algonquian',
            'journal': 'Linguistic Structures of Native America',
            'pages': '85--129'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        sources_count = dbsession.query(Source).count()
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert sources_count == new_sources_count
        assert resp['errors'] == \
            'Sources of type article require values for author, title, journal and year.'
        assert response.content_type == 'application/json'

        ########################################################################
        # BOOKLET
        ########################################################################

        # Create a booklet; required: title
        params = self.source_create_params.copy()
        params.update({
            'type': 'BOOKLET',    # case is irrelevant for entry types
            'key': 'mypoetry',
            'title': 'My Poetry (unpublished)'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'booklet'      # the OLD converts type to lowercase
        assert resp['title'] == 'My Poetry (unpublished)'
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'

        # Attempt to create a booklet without a title and expect to fail
        params = self.source_create_params.copy()
        params.update({
            'type': 'Booklet',    # case is irrelevant for entry types
            'key': 'mypoetry2',
            'author': 'Me Meson'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        sources_count = dbsession.query(Source).count()
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert sources_count == new_sources_count
        assert resp['errors'] == \
            'Sources of type booklet require a value for title.'
        assert response.content_type == 'application/json'

        ########################################################################
        # INBOOK
        ########################################################################

        # Create an inbook; required: title, publisher, year and one of author
        # or editor and one of chapter or pages.
        params = self.source_create_params.copy()
        params.update({
            'type': 'inbook',    # case is irrelevant for entry types
            'key': 'vendler67',
            'title': 'Linguistics in Philosophy',
            'publisher': 'Cornell University Press',
            'year': 1967,
            'author': 'Vendler, Zeno',
            'chapter': '4'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        inbook_id = resp['id']
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'inbook'      # the OLD converts type to lowercase
        assert resp['title'] == 'Linguistics in Philosophy'
        assert resp['publisher'] == 'Cornell University Press'
        assert resp['year'] == 1967
        assert resp['author'] == 'Vendler, Zeno'
        assert resp['chapter'] == '4'
        assert resp['pages'] == ''
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'

        # Attempt to create an inbook without a chapter or pages and expect to fail
        params = self.source_create_params.copy()
        params.update({
            'type': 'inbook',    # case is irrelevant for entry types
            'key': 'vendler67again',
            'title': 'Linguistics in Philosophy',
            'publisher': 'Cornell University Press',
            'year': 1967,
            'author': 'Vendler, Zeno'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        sources_count = dbsession.query(Source).count()
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert sources_count == new_sources_count
        assert resp['errors'] == \
            'Sources of type inbook require values for title, publisher and year as well as a value for at least one of author and editor and at least one of chapter and pages.'
        assert response.content_type == 'application/json'

        # 'required': (('author', 'editor'), 'title', ('chapter', 'pages'), 'publisher', 'year')
        # Create a book that the inbook above will cross-reference once updated.
        # required: author or editor, title, publisher and year
        params = self.source_create_params.copy()
        params.update({
            'type': 'bOOk',    # case is irrelevant for entry types
            'key': 'vendler67book',
            'author': 'Vendler, Zeno',
            'title': 'Linguistics in Philosophy',
            'publisher': 'Cornell University Press',
            'year': 1967
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'book'      # the OLD converts type to lowercase
        assert resp['title'] == 'Linguistics in Philosophy'
        assert resp['author'] == 'Vendler, Zeno'
        assert resp['year'] == 1967
        assert resp['publisher'] == 'Cornell University Press'
        assert resp['key'] == 'vendler67book'
        assert response.content_type == 'application/json'

        # Now update the valid inbook created above and have it cross-reference
        # the book just created above.  Because the Vendler book has all of the
        # rest of the attributes, all we need to specify is the chapter.
        params = self.source_create_params.copy()
        params.update({
            'type': 'inbook',    # case is irrelevant for entry types
            'key': 'vendler67',
            'chapter': '4',
            'crossref': 'vendler67book'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=inbook_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        assert resp['type'] == 'inbook'      # the OLD converts type to lowercase
        assert resp['crossref_source']['title'] == 'Linguistics in Philosophy'
        assert resp['crossref_source']['publisher'] == 'Cornell University Press'
        assert resp['crossref_source']['year'] == 1967
        assert resp['crossref_source']['author'] == 'Vendler, Zeno'
        assert resp['chapter'] == '4'

        # Now update our inbook back to how it was and remove the cross-reference;
        # make sure that the crossref_source value is now None.
        params = self.source_create_params.copy()
        params.update({
            'type': 'inbook',    # case is irrelevant for entry types
            'key': 'vendler67',
            'title': 'Linguistics in Philosophy',
            'publisher': 'Cornell University Press',
            'year': 1967,
            'author': 'Vendler, Zeno',
            'chapter': '4'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=inbook_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'inbook'      # the OLD converts type to lowercase
        assert resp['title'] == 'Linguistics in Philosophy'
        assert resp['publisher'] == 'Cornell University Press'
        assert resp['year'] == 1967
        assert resp['author'] == 'Vendler, Zeno'
        assert resp['chapter'] == '4'
        assert resp['pages'] == ''
        assert resp['crossref'] == ''
        assert resp['crossref_source'] is None
        assert new_sources_count == sources_count
        assert response.content_type == 'application/json'


        ########################################################################
        # MISC
        ########################################################################

        # Create a misc; required: nothing.
        params = self.source_create_params.copy()
        params.update({
            'type': 'misc',    # case is irrelevant for entry types
            'key': 'manuel83',
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert resp['type'] == 'misc'      # the OLD converts type to lowercase
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'

        ########################################################################
        # INPROCEEDINGS
        ########################################################################

        # Create an inproceedings; required: author, title, booktitle, year.
        params = self.source_create_params.copy()
        params.update({
            'type': 'inpROceedings',    # case is irrelevant for entry types
            'key': 'oaho83',
            'title': 'On Notions of Information Transfer in {VLSI} Circuits',
            'booktitle': 'Proc. Fifteenth Annual ACM',
            'year': 1983,
            'author': 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        inproceedings_id = resp['id']
        assert resp['type'] == 'inproceedings'      # the OLD converts type to lowercase
        assert resp['title'] == 'On Notions of Information Transfer in {VLSI} Circuits'
        assert resp['booktitle'] == 'Proc. Fifteenth Annual ACM'
        assert resp['year'] == 1983
        assert resp['author'] == 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis'
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'

        # Attempt to create an inproceedings that lacks booktitle and year
        # values; expect to fail.
        params = self.source_create_params.copy()
        params.update({
            'type': 'inpROceedings',    # case is irrelevant for entry types
            'key': 'oaho83_2',
            'title': 'On Notions of Information Transfer in {VLSI} Circuits',
            'author': 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert new_sources_count == sources_count
        assert response.content_type == 'application/json'
        assert resp['errors'] == 'Sources of type inproceedings require values for author, title, booktitle and year.'

        # Now create a proceedings source that will be cross-referenced by the
        # above inproceedings source.
        params = self.source_create_params.copy()
        params.update({
            'type': 'PROceedings',    # case is irrelevant for entry types
            'key': 'acm15_83',
            'title': 'Proc. Fifteenth Annual',
            'booktitle': 'Proc. Fifteenth Annual ACM',
            'year': 1983
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        proceedings_id = resp['id']
        assert resp['type'] == 'proceedings'      # the OLD converts type to lowercase
        assert resp['title'] == 'Proc. Fifteenth Annual'
        assert resp['booktitle'] == 'Proc. Fifteenth Annual ACM'
        assert resp['year'] == 1983
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'

        # Now attempt to create an inproceedings that lacks booktitle and year
        # values but cross-reference the proceedings source we just created; expect to succeed.
        params = self.source_create_params.copy()
        params.update({
            'type': 'inpROceedings',    # case is irrelevant for entry types
            'key': 'oaho83_2',
            'title': 'On Notions of Information Transfer in {VLSI} Circuits',
            'author': 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis',
            'crossref': 'acm15_83'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'
        assert resp['type'] == 'inproceedings'      # the OLD converts type to lowercase
        assert resp['title'] == 'On Notions of Information Transfer in {VLSI} Circuits'
        assert resp['crossref_source']['booktitle'] == 'Proc. Fifteenth Annual ACM'
        assert resp['crossref_source']['year'] == 1983
        assert resp['author'] == 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis'
        assert new_sources_count == sources_count + 1
        assert response.content_type == 'application/json'
        assert resp['crossref_source']['id'] == proceedings_id

        # Make sure the crossref stuff works with updates
        params = self.source_create_params.copy()
        params.update({
            'type': 'inpROceedings',    # case is irrelevant for entry types
            'key': 'oaho83',
            'title': 'On Notions of Information Transfer in {VLSI} Circuits',
            'author': 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis',
            'crossref': 'acm15_83'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=inproceedings_id), params,
                                self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        sources_count = new_sources_count
        new_sources_count = dbsession.query(Source).count()
        assert response.content_type == 'application/json'
        assert resp['type'] == 'inproceedings'      # the OLD converts type to lowercase
        assert resp['title'] == 'On Notions of Information Transfer in {VLSI} Circuits'
        assert resp['crossref_source']['booktitle'] == 'Proc. Fifteenth Annual ACM'
        assert resp['crossref_source']['year'] == 1983
        assert resp['author'] == 'Alfred V. Oaho and Jeffrey D. Ullman and Mihalis Yannakakis'
        assert new_sources_count == sources_count
        assert response.content_type == 'application/json'
        assert resp['crossref_source']['id'] == proceedings_id

    def test_new(self):
        """Tests that GET /sources/new returns the list of valid BibTeX entry types."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        response = self.app.get(url('new'), headers=self.json_headers,
                                extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert sorted(resp['types']) == sorted(ENTRY_TYPES.keys())
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /sources/1 updates an existing source."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a book to update.
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Noam Chomsky',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        source_count = dbsession.query(Source).count()
        book_id = resp['id']
        original_datetime_modified = resp['datetime_modified']

        # Update the book
        sleep(1)    # sleep for a second to ensure that MySQL registers a different datetime_modified for the update
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Chomsky, N.',   # Change the format of the author
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=book_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        datetime_modified = resp['datetime_modified']
        new_source_count = dbsession.query(Source).count()
        assert source_count == new_source_count
        assert datetime_modified != original_datetime_modified
        assert response.content_type == 'application/json'

        # Attempt an update with no new input and expect to fail
        sleep(1)    # sleep for a second to ensure that MySQL could register a different datetime_modified for the update
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Chomsky, N.',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=book_id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        source_count = new_source_count
        new_source_count = dbsession.query(Source).count()
        our_book_datetime_modified = dbsession.query(Source).get(book_id).datetime_modified
        assert our_book_datetime_modified.isoformat() == datetime_modified
        assert source_count == new_source_count
        assert resp['error'] == 'The update request failed because the submitted data were not new.'
        assert response.content_type == 'application/json'

        # Update by adding a file to the source
        file_ = omb.generate_default_file()
        dbsession.add(file_)
        dbsession.flush()
        file_id = file_.id
        filename = file_.name
        dbsession.commit()

        sleep(1)    # sleep for a second to ensure that MySQL can register a different datetime_modified for the update
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Chomsky, N.',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957,
            'file': file_id
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=book_id), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        source_count = new_source_count
        new_source_count = dbsession.query(Source).count()
        new_datetime_modified = resp['datetime_modified']
        assert new_datetime_modified != datetime_modified
        assert source_count == new_source_count
        assert resp['file']['name'] == filename
        assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /sources/id deletes the source with id=id."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a book to delete.
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Noam Chomsky',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        source_count = dbsession.query(Source).count()
        book_id = resp['id']

        # Now delete the source
        response = self.app.delete(url('delete', id=book_id), headers=self.json_headers,
            extra_environ=self.extra_environ_admin)
        resp = response.json_body
        new_source_count = dbsession.query(Source).count()
        assert new_source_count == source_count - 1
        assert resp['id'] == book_id
        assert response.content_type == 'application/json'

        # Trying to get the deleted source from the db should return None
        deleted_source = dbsession.query(Source).get(book_id)
        assert deleted_source is None

        # Delete with an invalid id
        id = 9999999999999
        response = self.app.delete(url('delete', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no source with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

    def test_show(self):
        """Tests that GET /source/id returns the source with id=id or an appropriate error."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a book to show.
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Noam Chomsky',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        book_id = resp['id']

        # Try to get a source using an invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no source with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == 'The resource could not be found.'
        assert response.content_type == 'application/json'

        # Valid id
        response = self.app.get(url('show', id=book_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['author'] == 'Noam Chomsky'
        assert resp['year'] == 1957
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /sources/id/edit returns a JSON object of data necessary to edit the source with id=id.

        The JSON object is of the form {'source': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a book to request edit on.
        params = self.source_create_params.copy()
        params.update({
            'type': 'book',
            'key': 'chomsky57',
            'author': 'Noam Chomsky',
            'title': 'Syntactic Structures',
            'publisher': 'Mouton',
            'year': 1957
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        book_id = resp['id']

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=book_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 9876544
        response = self.app.get(url('edit', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no source with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Valid id
        response = self.app.get(url('edit', id=book_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['source']['title'] == 'Syntactic Structures'
        assert sorted(resp['data']['types']) == sorted(ENTRY_TYPES.keys())
        assert response.content_type == 'application/json'

    def fix_source(self, source):
        for key, val in source.items():
            if isinstance(val, (datetime.datetime, datetime.date)):
                source[key] = val.isoformat()
        return source

    def test_search(self):
        """Tests that SEARCH /sources (a.k.a. POST /sources/search) correctly returns an array of sources based on search criteria."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create some sources (and other models) to search and add SEARCH to the list of allowable methods
        _create_test_data(dbsession, db, 100)
        add_SEARCH_to_web_test_valid_methods()

        sources = json.loads(json.dumps(
            [self.fix_source(s.get_dict()) for s in db.get_sources(True)]))
        for s in sources:
            if s['title'] is None:
                print('this source has no title')
                pprint.pprint(s)

        # Searching where values may be NULL
        json_query = json.dumps({'query': {'filter': ['Source', 'publisher', '=', None]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = [s for s in sources if not s['publisher']]
        assert resp
        assert len(resp) == len(result_set)
        assert set([s['id'] for s in resp]) == set([s['id'] for s in result_set])
        assert response.content_type == 'application/json'

        json_query = json.dumps({'query': {'filter': ['Source', 'publisher', 'like', '%P%']}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = [s for s in sources if s['publisher'] and 'P' in s['publisher']]
        assert resp
        assert len(resp) == len(result_set)
        assert set([s['id'] for s in resp]) == set([s['id'] for s in result_set])
        assert response.content_type == 'application/json'

        # A fairly complex search
        json_query = json.dumps({'query': {'filter': [
            'and', [
                ['Source', 'type', 'in', [u'book', 'article']],
                ['not', ['Source', 'key', 'regex', '[537]']],
                ['or', [
                    ['Source', 'author', 'like', '%A%'],
                    ['Source', 'year', '>', 1994]]]]]}})
        response = self.app.post(url('search_post'), json_query,
                        self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = [s for s in sources if
            s['type'] in ['book', 'article'] and
            not re.search('[537]', s['key']) and
            ('A' in s['author'] or s['year'] > 1994)]
        assert resp
        assert len(resp) == len(result_set)
        assert set([s['id'] for s in resp]) == set([s['id'] for s in result_set])
        assert response.content_type == 'application/json'

        # A basic search with a paginator provided.
        json_query = json.dumps({'query': {
                'filter': ['Source', 'title', 'like', '%3%']},
            'paginator': {'page': 2, 'items_per_page': 5}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        result_set = [s for s in sources if s['title'] and '3' in s['title']]
        assert resp['paginator']['count'] == len(result_set)
        assert len(resp['items']) == 5
        assert resp['items'][0]['id'] == result_set[5]['id']
        assert resp['items'][-1]['id'] == result_set[9]['id']
        assert response.content_type == 'application/json'

        # An invalid paginator (here 'page' is less than 1) will result in formencode.Invalid
        # being raised resulting in a response with a 400 status code and a JSON error msg.
        json_query = json.dumps({
            'query': {
                'filter': ['Source', 'title', 'like', '%3%']},
            'paginator': {'page': 0, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'
        assert response.content_type == 'application/json'

        # Some "invalid" paginators will silently fail.  For example, if there is
        # no 'pages' key, then SEARCH /sources will just assume there is no paginator
        # and all of the results will be returned.
        json_query = json.dumps({
            'query': {
                'filter': ['Source', 'title', 'like', '%3%']},
            'paginator': {'pages': 1, 'items_per_page': 10}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == len([s for s in sources if s['title'] and '3' in s['title']])

        # Adding a 'count' key to the paginator object in the request will spare
        # the server from running query.count().  Note that the server will not
        # attempt to verify the count (since that would defeat the purpose) but
        # will simply pass it back.  The server trusts that the client is passing
        # in a factual count.  Here we pass in an inaccurate count for demonstration.
        json_query = json.dumps({'query': {
                'filter': ['Source', 'title', 'like', '%3%']},
            'paginator': {'page': 2, 'items_per_page': 4, 'count': 750}})
        response = self.app.request(url('search'), method='SEARCH', body=json_query.encode('utf8'),
            headers=self.json_headers, environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['paginator']['count'] == 750
        assert len(resp['items']) == 4
        assert resp['items'][0]['id'] == result_set[4]['id']
        assert resp['items'][-1]['id'] == result_set[7]['id']

        # Test order by: order by title descending
        json_query = json.dumps({'query': {
                'filter': ['Source', 'key', 'regex', '.'],
                'order_by': ['Source', 'title', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        result_set = sorted(sources, key=lambda k: k['title'] or 'z', reverse=True)

        pprint.pprint([s['title'] for s in result_set])
        pprint.pprint([s['title'] for s in resp])

        assert len(resp) == 100
        assert ([s['title'] for s in result_set if s['title']] ==
                [s['title'] for s in resp if s['title']])
        assert resp[-1]['title'] is None
        assert resp[0]['title'] == 'Title 90'
        assert response.content_type == 'application/json'

        # order by with missing direction defaults to 'asc'
        json_query = json.dumps({'query': {
                'filter': ['Source', 'key', 'regex', '.'],
                'order_by': ['Source', 'title']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[-1]['title'] == 'Title 90'
        assert resp[0]['title'] is None

        # order by with unknown direction defaults to 'asc'
        json_query = json.dumps({'query': {
                'filter': ['Source', 'key', 'regex', '.'],
                'order_by': ['Source', 'title', 'descending']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[-1]['title'] == 'Title 90'
        assert resp[0]['title'] is None

        # syntactically malformed order by
        json_query = json.dumps({'query': {
                'filter': ['Source', 'key', 'regex', '.'],
                'order_by': ['Source']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'
        assert response.content_type == 'application/json'

        # searches with lexically malformed order bys
        json_query = json.dumps({'query': {
                'filter': ['Source', 'key', 'regex', '.'],
                'order_by': ['Source', 'foo', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Source.foo'] == 'Searching on Source.foo is not permitted'
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'
        assert response.content_type == 'application/json'

        json_query = json.dumps({'query': {
                'filter': ['Source', 'key', 'regex', '.'],
                'order_by': ['Foo', 'id', 'desc']}})
        response = self.app.post(url('search_post'), json_query,
            self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['Foo'] == 'Searching the Source model by joining on the Foo model is not possible'
        assert resp['errors']['Foo.id'] == 'Searching on Foo.id is not permitted'
        assert resp['errors']['OrderByError'] == 'The provided order by expression was invalid.'
        assert response.content_type == 'application/json'

    def test_new_search(self):
        """Tests that GET /sources/new_search returns the search parameters for searching the sources resource."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        query_builder = SQLAQueryBuilder(dbsession, 'Source', settings=self.settings)
        response = self.app.get('/sources/new_search', headers=self.json_headers,
                                extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert resp['search_parameters'] == query_builder.get_search_parameters()
