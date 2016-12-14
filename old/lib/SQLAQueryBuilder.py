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

"""This module defines :class:`SQLAQueryBuilder`.  An ``SQLAQueryBuilder``
instance is used to build an SQLAlchemy query object from a Python data
structure (nested lists).

The two public methods are get_SQLA_query and get_SQLA_filter.  Both take a list
representing a filter expression as input.  get_SQLA_query returns an SQLAlchemy
query object, including joins and filters.  get_SQLA_filter returns an SQLAlchemy
filter expression and is called by get_SQLA_query.  Errors in the Python filter
expression will cause custom OLDSearchParseErrors to be raised.

The searchable models and their attributes (scalars & collections) are defined
in SQLAQueryBuilder.schema.

Simple filter expressions are lists with four or five items.  Complex filter
expressions are constructed via lists whose first element is one of the boolean
keywords 'and', 'or', 'not' and whose second element is a filter expression or
a list thereof (in the case of 'and' and 'or').  The examples below show a
filter expression accepted by SQLAQueryBuilder('Form').get_SQLA_query on the
second line followed by the equivalent SQLAlchemy ORM expression.  Note that the
target model of the SQLAQueryBuilder is set to 'Form' so all queries will be
against the Form model.

1. Simple scalar queries::

        ['Form', 'transcription', 'like', '%a%']
        self.dbsession.query(Form).filter(Form.transcription.like('%a%'))

2. Scalar relations::

        ['Form', 'enterer', 'first_name', 'regex', '^[JS]']
        self.dbsession.query(Form).filter(Form.enterer.has(User.first_name.op('regexp')('^[JS]')))

3. Scalar relations presence/absence::

        ['Form', 'enterer', '=', 'None']
        self.dbsession.query(Form).filter(Form.enterer==None)

4. Collection relations (w/ SQLA's collection.any() method)::

        ['Form', 'files', 'id', 'in', [1, 2, 33, 5]]
        self.dbsession.query(Form).filter(Form.files.any(File.id.in_([1, 2, 33, 5])))

5. Collection relations (w/ joins; should return the same results as (4)):

        ['File', 'id', 'in', [1, 2, 33, 5]]
        file_alias = aliased(File)
        self.dbsession.query(Form).filter(file_alias.id.in_([1, 2, 33, 5])).outerjoin(file_alias, Form.files)

6. Collection relations presence/absence::

        ['Form', 'files', '=', None]
        self.dbsession.query(Form).filter(Form.files == None)

7. Negation::

        ['not', ['Form', 'transcription', 'like', '%a%']]
        self.dbsession.query(Form).filter(not_(Form.transcription.like('%a%')))

8. Conjunction::

        ['and', [['Form', 'transcription', 'like', '%a%'],
                 ['Form', 'elicitor', 'id', '=', 13]]]
        self.dbsession.query(Form).filter(and_(Form.transcription.like('%a%'),
                                        Form.elicitor.has(User.id==13)))

9. Disjunction::

        ['or', [['Form', 'transcription', 'like', '%a%'],
                ['Form', 'date_elicited', '<', '2012-01-01']]]
        self.dbsession.query(Form).filter(or_(Form.transcription.like('%a%'),
                                       Form.date_elicited < datetime.date(2012, 1, 1)))

10. Complex::

        ['and', [['Translation', 'transcription', 'like', '%1%'],
                 ['not', ['Form', 'morpheme_break', 'regex', '[28][5-7]']],
                 ['or', [['Form', 'datetime_modified', '<', '2012-03-01T00:00:00'],
                         ['Form', 'datetime_modified', '>', '2012-01-01T00:00:00']]]]]
        translation_alias = aliased(Translation)
        self.dbsession.query(Form).filter(and_(
            translation_alias.transcription.like('%1%'),
            not_(Form.morpheme_break.op('regexp')('[28][5-7]')),
            or_(
                Form.datetime_modified < ...,
                Form.datetime_modified > ...
            )
        )).outerjoin(translation_alias, Form.translations)

Note also that SQLAQueryBuilder detects the RDBMS and issues collate commands
where necessary to ensure that pattern matches are case-sensitive while ordering
is not.

A further potential enhancement would be to allow doubly relational searches, e.g.,
return all forms whose enterer has remembered a form with a transcription like 'a':

11. Scalar's collection relations::

        ['Form', 'enterer', 'remembered_forms', 'transcription', 'like', '%a%']
        self.dbsession.query(Form).filter(Form.enterer.has(User.remembered_forms.any(
            Form.transcription.like('%1%'))))

"""

import logging
import datetime
from sqlalchemy.sql import or_, and_, not_, asc, desc
from sqlalchemy.exc import OperationalError, InvalidRequestError
from sqlalchemy.sql.expression import collate
from sqlalchemy.orm import aliased
from sqlalchemy.types import Unicode, UnicodeText
from old.lib.utils import normalize

LOGGER = logging.getLogger(__name__)


import json
import old.models as old_models

try:
    mysql_engine = old_models.Model.__table_args__.get('mysql_engine')
except NameError:
    mysql_engine = None

try:
    from old.lib.utils import get_RDBMS_name
except ImportError:
    def get_RDBMS_name():
        return 'sqlite'

try:
    from utils import datetime_string2datetime, date_string2date
except ImportError:
    # ImportError will be raised in utils if the Pylons environment is not
    # running, e.g., if we are debugging.  In this case, we need to define our
    # own date/datetime parsing functions.

    def round_datetime(dt):
        """Round a datetime to the nearest second."""
        discard = datetime.timedelta(microseconds=dt.microsecond)
        dt -= discard
        if discard >= datetime.timedelta(microseconds=500000):
            dt += datetime.timedelta(seconds=1)
        return dt

    def datetime_string2datetime(datetime_string, RDBMSName=None, mysql_engine=None):
        """Parse an ISO 8601-formatted datetime into a Python datetime object.
        Cf. http://stackoverflow.com/questions/531157/parsing-datetime-strings-with-microseconds

        Previously called ISO8601Str2datetime.
        """
        try:
            parts = datetime_string.split('.')
            years_to_seconds_string = parts[0]
            datetime_object = datetime.datetime.strptime(years_to_seconds_string,
                                                        "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
        try:
            microseconds = int(parts[1])
            datetime_object = datetime_object.replace(microsecond=microseconds)
        except (IndexError, ValueError, OverflowError):
            pass
        # MySQL InnoDB tables round microseconds to the nearest second.
        if RDBMSName == 'mysql' and mysql_engine == 'InnoDB':
            datetime_object = round_datetime(datetime_object)
        return datetime_object

    def date_string2date(date_string):
        try:
            return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()
        except ValueError:
            return None

class OLDSearchParseError(Exception):
    def __init__(self, errors):
        self.errors = errors
    def __repr__(self):
        return '; '.join(['%s: %s' % (k, self.errors[k]) for k in self.errors])
    def __str__(self):
        return self.__repr__()
    def unpack_errors(self):
        return self.errors


class SQLAQueryBuilder(object):
    """Generate an SQLAlchemy query object from a Python dictionary.

    Builds SQLAlchemy queries from Python data structures representing
    arbitrarily complex filter expressions.  Joins are inferred from the filter
    expression.  The public method most likely to be used is
    :func:`get_SQLA_query`.  Example usage::

        query_builder = SQLAlchemyQueryBuilder()
        python_query = {'filter': [
            'and', [
                ['Translation', 'transcription', 'like', '1'],
                ['not', ['Form', 'morpheme_break', 'regex', '[28][5-7]']],
                ['or', [
                    ['Form', 'datetime_modified', '<', '2012-03-01T00:00:00'],
                    ['Form', 'datetime_modified', '>', '2012-01-01T00:00:00']]]]]}
        query = query_builder.get_SQLA_query(python_query)
        forms = query.all()

    """

    def __init__(self, dbsession, model_name='Form', primary_key='id',
                 settings=None):
        self.dbsession = dbsession
        self.errors = {}
        self.joins = []
        self.model_name = model_name  # The name of the target model, i.e., the one we are querying, e.g., 'Form'
        self.primary_key = primary_key    # Some models have a primary key other than 'id' ...
        if not settings:
            settings = {}
        self.RDBMSName = get_RDBMS_name(settings) # i.e., mysql or sqlite

    def get_SQLA_query(self, python):
        self.clear_errors()
        filter_expression = self.get_SQLA_filter(python.get('filter'))
        order_by_expression = self._get_SQLA_order_by(python.get('order_by'), self.primary_key)
        self._raise_search_parse_error_if_necessary()
        query = self._get_base_query()
        query = query.filter(filter_expression)
        query = query.order_by(order_by_expression)
        query = self._add_joins_to_query(query)
        return query

    def get_SQLA_filter(self, python):
        """Return the SQLAlchemy filter expression generable by the input Python
        data structure or raise an OLDSearchParseError if the data structure is
        invalid.
        """
        return self._python2sqla(python)

    def get_SQLA_order_by(self, order_by, primary_key='id'):
        """The public method clears the errors and then calls the private method.
        This prevents interference from errors generated by previous order_by calls.
        """
        self.clear_errors()
        return self._get_SQLA_order_by(order_by, primary_key)

    def _get_SQLA_order_by(self, order_by, primary_key='id'):
        """Input is an array of the form [<model>, <attribute>, <direction>];
        output is an SQLA order_by expression.
        """
        default_order_by = asc(getattr(getattr(old_models, self.model_name), primary_key))
        if order_by is None:
            return default_order_by
        try:
            model_name = self._get_model_name(order_by[0])
            attribute_name = self._get_attribute_name(order_by[1], model_name)
            model = self._get_model(model_name)
            attribute = getattr(model, attribute_name)
            if self.RDBMSName == 'sqlite' and attribute is not None and \
            isinstance(attribute.property.columns[0].type, self.SQLAlchemyStringTypes):
                attribute = collate(attribute, 'NOCASE')    # Force SQLite to order case-insensitively
            try:
                return {'asc': asc, 'desc': desc}.get(order_by[2], asc)(attribute)
            except IndexError:
                return asc(attribute)
        except (IndexError, AttributeError):
            self._add_to_errors('OrderByError', 'The provided order by expression was invalid.')
            return default_order_by

    def clear_errors(self):
        self.errors = {}

    def _raise_search_parse_error_if_necessary(self):
        if self.errors:
            errors = self.errors.copy()
            self.clear_errors()    # Clear the errors so the instance can be reused to build further queries
            raise OLDSearchParseError(errors)

    def _get_base_query(self):
        query_model = getattr(old_models, self.model_name)
        return self.dbsession.query(query_model)

    def _add_joins_to_query(self, query):
        for join in self.joins:
            query = query.outerjoin(join[0], join[1])
        self.joins = []
        return query

    def _python2sqla(self, python):
        """This is the function that is called recursively (if necessary) to
        build the SQLAlchemy filter expression.
        """
        try:
            if python[0] in ('and', 'or'):
                return {'and': and_, 'or': or_}[python[0]](
                    *[self._python2sqla(x) for x in python[1]])
            elif python[0] == 'not':
                return not_(self._python2sqla(python[1]))
            else:
                return self._get_simple_filter_expression(*python)
        except TypeError as e:
            self.errors['Malformed OLD query error'] = 'The submitted query was malformed'
            self.errors['TypeError'] = str(e)
        except IndexError as e:
            self.errors['Malformed OLD query error'] = 'The submitted query was malformed'
            self.errors['IndexError'] = str(e)
        # TODO: catching Exception base class is bad practice
        except Exception as e:
            self.errors['Malformed OLD query error'] = 'The submitted query was malformed'
            self.errors['Exception'] = str(e)

    SQLAlchemyStringTypes = (Unicode, UnicodeText)

    def _add_to_errors(self, key, msg):
        self.errors[str(key)] = msg

    ############################################################################
    # Value converters
    ############################################################################

    def _get_date_value(self, date_string):
        """Converts ISO 8601 date strings to Python datetime.date objects."""
        if date_string is None:
            return date_string   # None can be used on date comparisons so assume this is what was intended
        date = date_string2date(date_string)
        if date is None:
            self._add_to_errors('date %s' % str(date_string),
                'Date search parameters must be valid ISO 8601 date strings.')
        return date

    def _get_datetime_value(self, datetime_string):
        """Converts ISO 8601 datetime strings to Python datetime.datetime objects."""
        if datetime_string is None:
            return datetime_string   # None can be used on datetime comparisons so assume this is what was intended
        datetime = datetime_string2datetime(datetime_string, self.RDBMSName, mysql_engine)
        if datetime is None:
            self._add_to_errors('datetime %s' % str(datetime_string),
                'Datetime search parameters must be valid ISO 8601 datetime strings.')
        return datetime

    ############################################################################
    # Data structures
    ############################################################################
    # Alter the relations, schema and models2joins dicts in order to
    # change what types of input the query builder accepts.

    # The default set of available relations.  Relations with aliases are
    # treated as their aliases.  E.g., a search like ['Form', 'source_id' '=', ...]
    # will generate the filter model.Form.source_id.__eq__(...)
    relations = {
        '__eq__': {},
        '=': {'alias': '__eq__'},
        '__ne__': {},
        '!=': {'alias': '__ne__'},
        'like': {},
        'regexp': {},
        'regex': {'alias': 'regexp'},
        '__lt__': {},
        '<': {'alias': '__lt__'},
        '__gt__': {},
        '>': {'alias': '__gt__'},
        '__le__': {},
        '<=': {'alias': '__le__'},
        '__ge__': {},
        '>=': {'alias': '__ge__'},
        'in_': {},
        'in': {'alias': 'in_'}
    }

    equality_relations = {
        '__eq__': {},
        '=': {'alias': '__eq__'},
        '__ne__': {},
        '!=': {'alias': '__ne__'}
    }

    # The schema attribute describes the database structure in a way that allows
    # the query builder to properly interpret the list-based queries and
    # generate errors where necessary. Maps model names to attribute names.
    # Attribute names whose values contain an 'alias' key are treated as the
    # value of that key, e.g., ['Form', 'enterer' ...] will be treated as
    # Form.enterer_id... The relations listed in self.relations above are the
    # default for all attributes. This can be overridden by specifying a
    # 'relation' key (cf. schema['Form']['translations'] below). Certain
    # attributes require value converters -- functions that change the value in
    # some attribute-specific way, e.g., conversion of ISO 8601 datetimes to
    # Python datetime objects.
    schema = {
        'Collection': {
            'id': {},
            'UUID': {},
            'title': {},
            'type': {},
            'url': {},
            'description': {},
            'markup_language': {},
            'contents': {},
            'html': {},
            'speaker': {'foreign_model': 'Speaker', 'type': 'scalar'},
            'source': {'foreign_model': 'Source', 'type': 'scalar'},
            'elicitor': {'foreign_model': 'User', 'type': 'scalar'},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'date_elicited': {'value_converter': '_get_date_value'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'tags': {'foreign_model': 'Tag', 'type': 'collection'},
            'forms': {'foreign_model': 'Form', 'type': 'collection'},
            'files': {'foreign_model': 'File', 'type': 'collection'}
        },
        'CollectionBackup': {
            'id': {},
            'UUID': {},
            'collection_id': {},
            'title': {},
            'type': {},
            'url': {},
            'description': {},
            'markup_language': {},
            'contents': {},
            'html': {},
            'speaker': {},
            'source': {},
            'elicitor': {},
            'enterer': {},
            'date_elicited': {'value_converter': '_get_date_value'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'tags': {},
            'forms': {},
            'files': {}
        },
        'Corpus': {
            'id': {},
            'UUID': {},
            'name': {},
            'type': {},
            'description': {},
            'content': {},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'},
            'form_search': {'foreign_model': 'FormSearch', 'type': 'scalar'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'tags': {'foreign_model': 'Tag', 'type': 'collection'},
            'forms': {'foreign_model': 'Form', 'type': 'collection'}
        },
        'CorpusBackup': {
            'id': {},
            'UUID': {},
            'name': {},
            'type': {},
            'description': {},
            'content': {},
            'enterer': {},
            'modifier': {},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'tags': {},
            'forms': {}
        },
        'ElicitationMethod': {
            'id': {},
            'name': {},
            'description': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
        },
        'Form': {
            'id': {},
            'UUID': {},
            'transcription': {},
            'phonetic_transcription': {},
            'narrow_phonetic_transcription': {},
            'morpheme_break': {},
            'morpheme_gloss': {},
            'comments': {},
            'speaker_comments': {},
            'grammaticality': {},
            'date_elicited': {'value_converter': '_get_date_value'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'syntactic_category_string': {},
            'morpheme_break_ids': {},
            'morpheme_gloss_ids': {},
            'break_gloss_category': {},
            'syntax': {},
            'semantics': {},
            'status': {},
            'elicitor': {'foreign_model': 'User', 'type': 'scalar'},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'verifier': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'},
            'speaker': {'foreign_model': 'Speaker', 'type': 'scalar'},
            'elicitation_method': {'foreign_model': 'ElicitationMethod', 'type': 'scalar'},
            'syntactic_category': {'foreign_model': 'SyntacticCategory', 'type': 'scalar'},
            'source': {'foreign_model': 'Source', 'type': 'scalar'},
            'translations': {'foreign_model': 'Translation', 'type': 'collection'},
            'tags': {'foreign_model': 'Tag', 'type': 'collection'},
            'files': {'foreign_model': 'File', 'type': 'collection'},
            'collections': {'foreign_model': 'Collection', 'type': 'collection'},
            'memorizers': {'foreign_model': 'User', 'type': 'collection'},
            'corpora': {'foreign_model': 'Corpus', 'type': 'collection'}
        },
        'FormBackup': {
            'id': {},
            'UUID': {},
            'form_id': {},
            'transcription': {},
            'phonetic_transcription': {},
            'narrow_phonetic_transcription': {},
            'morpheme_break': {},
            'morpheme_gloss': {},
            'comments': {},
            'speaker_comments': {},
            'grammaticality': {},
            'date_elicited': {'value_converter': '_get_date_value'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'syntactic_category_string': {},
            'morpheme_break_ids': {},
            'morpheme_gloss_ids': {},
            'break_gloss_category': {},
            'syntax': {},
            'semantics': {},
            'elicitor': {},
            'enterer': {},
            'verifier': {},
            'speaker': {},
            'elicitation_method': {},
            'syntactic_category': {},
            'source': {},
            'translations': {},
            'tags': {},
            'files': {},
            'collections': {}
        },
        'FormSearch': {
            'id': {},
            'name': {},
            'search': {},
            'description': {},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'File': {
            'id': {},
            'filename': {},
            'name': {},
            'MIME_type': {},
            'size': {},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'description': {},
            'date_elicited': {'value_converter': '_get_date_value'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'elicitor': {'foreign_model': 'User', 'type': 'scalar'},
            'speaker': {'foreign_model': 'Speaker', 'type': 'scalar'},
            'parent_file': {'foreign_model': 'File', 'type': 'scalar'},
            'utterance_type': {},
            'start': {},
            'end': {},
            'url': {},
            'password': {},
            'tags': {'foreign_model': 'Tag', 'type': 'collection'},
            'forms': {'foreign_model': 'Form', 'type': 'collection'},
            'collections': {'foreign_model': 'Collection', 'type': 'collection'}
        },
        'Translation': {
            'id': {},
            'transcription': {},
            'grammaticality': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'Language': {
            'Id': {},
            'Part2B': {},
            'Part2T': {},
            'Part1': {},
            'Scope': {},
            'Type': {},
            'Ref_Name': {},
            'Comment': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'Memorizer': {
            'id': {},
            'first_name': {},
            'last_name': {},
            'role': {}
        },
        'MorphemeLanguageModel': {
            'id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'smoothing': {},
            'order': {},
            'corpus': {'foreign_model': 'Corpus', 'type': 'scalar'},
            'vocabulary_morphology': {'foreign_model': 'Morphology', 'type': 'scalar'},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'estimation_succeeded': {},
            'estimation_message': {},
            'estimation_attempt': {}
        },
        'MorphemeLanguageModelBackup': {
            'id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'corpus': {},
            'enterer': {},
            'modifier': {},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'estimation_succeeded': {},
            'estimation_message': {},
            'estimation_attempt': {}
        },
        'MorphologicalParser': {
            'id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'phonology': {'foreign_model': 'Phonology', 'type': 'scalar'},
            'morphology': {'foreign_model': 'Morphology', 'type': 'scalar'},
            'language_model': {'foreign_model': 'MorphemeLanguageModel', 'type': 'scalar'},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'compile_succeeded': {},
            'compile_message': {},
            'compile_attempt': {},
        },
        'MorphologicalParserBackup': {
            'id': {},
            'morphologicalparser_id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'phonology': {},
            'morphology': {},
            'language_model': {},
            'enterer': {},
            'modifier': {},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'compile_succeeded': {},
            'compile_message': {},
            'compile_attempt': {},
        },
        'Morphology': {
            'id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'compile_succeeded': {},
            'compile_message': {},
            'compile_attempt': {},
            'generate_attempt': {},
            'extract_morphemes_from_rules_corpus': {},
            'rules': {},
            'rules_generated': {},
            'script_type': {},
            'lexicon_corpus': {'foreign_model': 'Corpus', 'type': 'scalar'},
            'rules_corpus': {'foreign_model': 'Corpus', 'type': 'scalar'}
        },
        'MorphologyBackup': {
            'id': {},
            'morphology_id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'enterer': {},
            'modifier': {},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'compile_succeeded': {},
            'compile_message': {},
            'compile_attempt': {},
            'generate_attempt': {},
            'extract_morphemes_from_rules_corpus': {},
            'script_type': {},
            'lexicon_corpus': {},
            'rules_corpus': {},
            'rules': {}
        },
        'Orthography': {
            'id': {},
            'name': {},
            'orthography': {},
            'lowercase': {},
            'initial_glottal_stops': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'Phonology': {
            'id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'script': {},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'datetime_compiled': {'value_converter': '_get_datetime_value'},
            'compile_succeeded': {},
            'compile_message': {},
        },
        'PhonologyBackup': {
            'id': {},
            'phonology_id': {},
            'UUID': {},
            'name': {},
            'description': {},
            'script': {},
            'enterer': {},
            'modifier': {},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'datetime_compiled': {'value_converter': '_get_datetime_value'},
            'compile_succeeded': {},
            'compile_message': {},
        },
        'Source': {
            'id': {},
            'file_id': {},
            'file': {'foreign_model': 'File', 'type': 'scalar'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'type': {},
            'key': {},
            'address': {},
            'annote': {},
            'author': {},
            'booktitle': {},
            'chapter': {},
            'crossref': {},
            'edition': {},
            'editor': {},
            'howpublished': {},
            'institution': {},
            'journal': {},
            'key_field': {},
            'month': {},
            'note': {},
            'number': {},
            'organization': {},
            'pages': {},
            'publisher': {},
            'school': {},
            'series': {},
            'title': {},
            'type_field': {},
            'url': {},
            'volume': {},
            'year': {},
            'affiliation': {},
            'abstract': {},
            'contents': {},
            'copyright': {},
            'ISBN': {},
            'ISSN': {},
            'keywords': {},
            'language': {},
            'location': {},
            'LCCN': {},
            'mrnumber': {},
            'price': {},
            'size': {}
        },
        'Speaker': {
            'id': {},
            'first_name': {},
            'last_name': {},
            'dialect': {},
            'page_content': {},
            'markup_language': {},
            'html': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'SyntacticCategory': {
            'id': {},
            'name': {},
            'type': {},
            'description': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'User': {
            'id': {},
            'first_name': {},
            'last_name': {},
            'email': {},
            'affiliation': {},
            'role': {},
            'markup_language': {},
            'page_content': {},
            'html': {},
            'input_orthography': {'foreign_model': 'Orthography', 'type': 'scalar'},
            'output_orthography': {'foreign_model': 'Orthography', 'type': 'scalar'},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'remembered_forms': {'foreign_model': 'Form', 'type': 'collection'}
        },
        'Tag': {
            'id': {},
            'name': {},
            'description': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'}
        },
        'Keyboard': {
            'id': {},
            'name': {},
            'description': {},
            'datetime_modified': {'value_converter': '_get_datetime_value'},
            'datetime_entered': {'value_converter': '_get_datetime_value'},
            'enterer': {'foreign_model': 'User', 'type': 'scalar'},
            'modifier': {'foreign_model': 'User', 'type': 'scalar'}
        }
    }

    model_aliases = {
        'Memorizer': 'User'
    }

    # Maps model names to the names of other models they can be joined to for
    # queries.  The values of the join models are the attributes of the original
    # model that the joins are actually made on, e.g., outerjoin(model.Form.tags)
    models2joins = {
        'Form': {
            'File': 'files',
            'Translation': 'translations',
            'Tag': 'tags',
            'Collection': 'collections',
            'Memorizer': 'memorizers'
        },
        'File': {
            'Tag': 'tags',
            'Form': 'forms',
            'Collection': 'collections'
        },
        'Collection': {
            'Form': 'forms',
            'File': 'files',
            'Tag': 'tags'
        }
    }

    ############################################################################
    # Model getters
    ############################################################################

    def _get_model_name(self, model_name):
        """Always return model_name; store an error if model_name is invalid."""
        if model_name not in self.schema:
            self._add_to_errors(model_name, 'Searching on the %s model is not permitted' % model_name)
        return model_name

    def _get_model(self, model_name, add_to_joins=True):
        try:
            model = getattr(old_models, self.model_aliases.get(model_name, model_name))
        except AttributeError:
            model = None
            self._add_to_errors(model_name, u"The OLD has no model %s" % model_name)

        # Store any implicit joins in self.joins to await addition to the query
        # in self._add_joins_to_query.  Using sqlalchemy.orm's aliased to alias
        # models/tables is what permits filters on multiple -to-many relations.
        # Aliasing File while searching Form.files, for example, permits us to
        # retrieve all forms that are associated to file 71 and file 74.
        if add_to_joins and model_name != self.model_name:
            join_models = self.models2joins.get(self.model_name, {})
            if model_name in join_models:
                join_collection_name = join_models[model_name]
                join_collection = getattr(getattr(old_models, self.model_name),
                                        join_collection_name)
                model = aliased(model)
                self.joins.append((model, join_collection))
            else:
                self._add_to_errors(model_name,
                    u"Searching the %s model by joining on the %s model is not possible" % (
                        self.model_name, model_name))
        return model

    def _get_attribute_model_name(self, attribute_name, model_name):
        """Returns the name of the model X that stores the data for the attribute
        A of model M, e.g., the attribute_model_name for model_name='Form' and
        attribute_name='enterer' is 'User'.
        """
        attribute_dict = self._get_attribute_dict(attribute_name, model_name)
        try:
            return attribute_dict['foreign_model']
        except KeyError:
            self._add_to_errors('%s.%s' % (model_name, attribute_name),
                'The %s attribute of the %s model does not represent a many-to-one relation.' % (
                    attribute_name, model_name))
        # TODO: bare except is bad practice
        except:
            pass    # probably a TypeError, meaning model_name.attribute_name is invalid; would have already been caught

    ############################################################################
    # Attribute getters
    ############################################################################

    def _get_attribute_name(self, attribute_name, model_name):
        """Return attribute_name or cache an error if attribute_name is not in
        self.schema[model_name].
        """
        self._get_attribute_dict(attribute_name, model_name, True)
        return attribute_name

    def _get_attribute_dict(self, attribute_name, model_name, report_error=False):
        """Return the dict needed to validate a given attribute of a given model,
        or return None.  Propagate an error (optionally) if the attribute_name is
        invalid.
        """
        attribute_dict = self.schema.get(model_name, {}).get(
            attribute_name, None)
        if attribute_dict is None and report_error:
            self._add_to_errors('%s.%s' % (model_name, attribute_name),
                'Searching on %s.%s is not permitted' % (model_name, attribute_name))
        return attribute_dict

    def _get_attribute(self, attribute_name, model, model_name):
        try:
            attribute = self._collate_attribute(getattr(model, attribute_name))
        except AttributeError:  # model can be None
            attribute = None
            self._add_to_errors('%s.%s' % (model_name, attribute_name),
                u"There is no attribute %s of %s" % (attribute_name, model_name))
        return attribute

    def _collate_attribute(self, attribute):
        """Append a MySQL COLLATE utf8_bin expression after the column name, if
        appropriate.  This allows regexp and like searches to be case-sensitive.
        An example SQLA query would be self.dbsession.query(model.Form).filter(
        collate(model.Form.transcription, 'utf8_bin').like('a%'))

        Previously there was a condition on collation that the relation_name be in
        ('like', 'regexp').  This condition was removed because MySQL does case-
        insensitive equality searches too!
        """
        if self.RDBMSName == 'mysql' and attribute is not None:
            try:
                attribute_type = attribute.property.columns[0].type
            except AttributeError:
                attribute_type = None
            if isinstance(attribute_type, self.SQLAlchemyStringTypes):
                attribute = collate(attribute, 'utf8_bin')
        return attribute

    ############################################################################
    # Relation getters
    ############################################################################

    def _get_relation_name(self, relation_name, model_name, attribute_name):
        """Return relation_name or its alias; propagate an error if relation_name is invalid."""
        relation_dict = self._get_relation_dict(relation_name, model_name, attribute_name, True)
        try:
            return relation_dict.get('alias', relation_name)
        except AttributeError:  # relation_dict can be None
            return None

    def _get_relation_dict(self, relation_name, model_name, attribute_name, report_error=False):
        attribute_relations = self._get_attribute_relations(attribute_name, model_name)
        try:
            relation_dict = attribute_relations.get(relation_name, None)
        except AttributeError:
            relation_dict = None
        if relation_dict is None and report_error:
            self._add_to_errors('%s.%s.%s' % (model_name, attribute_name, relation_name),
                u"The relation %s is not permitted for %s.%s" % (relation_name, model_name, attribute_name))
        return relation_dict

    def _get_attribute_relations(self, attribute_name, model_name):
        """Return the data structure encoding what relations are valid for the
        input attribute name.
        """
        attribute_dict = self._get_attribute_dict(attribute_name, model_name)
        try:
            if attribute_dict.get('foreign_model'):
                return self.equality_relations
            else:
                return self.relations
        except AttributeError:  # attribute_dict can be None
            return None

    def _get_relation(self, relation_name, attribute, attribute_name, model_name):
        try:
            if relation_name == 'regexp':
                op = getattr(attribute, 'op')
                relation = op('regexp')
            else:
                relation = getattr(attribute, relation_name)
        except AttributeError:  # attribute can be None
            relation = None
            self._add_to_errors('%s.%s.%s' % (model_name, attribute_name, relation_name),
                u"There is no relation '%s' of '%s.%s'" % (relation_name, model_name, attribute_name))
        return relation

    ############################################################################
    # Value getters
    ############################################################################

    def _normalize(self, value):
        def normalize_if_string(value):
            if isinstance(value, str):
                return normalize(value)
            return value
        value = normalize_if_string(value)
        if type(value) is list:
            value = [normalize_if_string(i) for i in value]
        return value

    def _get_value_converter(self, attribute_name, model_name):
        attribute_dict = self._get_attribute_dict(attribute_name, model_name)
        try:
            value_converter_name = attribute_dict.get('value_converter', '')
            return getattr(self, value_converter_name, None)
        except AttributeError:  # attribute_dict can be None
            return None

    def _get_value(self, value, model_name, attribute_name, relation_name):
        """Unicode normalize & modify the value using a value_converter (if necessary)."""
        value = self._normalize(value)    # unicode normalize (NFD) search patterns; we might want to parameterize this
        value_converter = self._get_value_converter(attribute_name, model_name)
        if value_converter is not None:
            if type(value) is type([]):
                value = [value_converter(li) for li in value]
            else:
                value = value_converter(value)
        return value

    ############################################################################
    # Filter expression getters
    ############################################################################

    def _get_invalid_filter_expression_message(self, model_name, attribute_name,
                                          relation_name, value):
        return u"Invalid filter expression: %s.%s.%s(%s)" % (model_name,
                                            attribute_name, relation_name, repr(value))

    def _get_invalid_model_attribute_errors(self, relation, value, model_name,
            attribute_name, relation_name, attribute, attribute_model_name, attribute_model_attribute_name):
        """Avoid catching a (costly) RuntimeError by preventing _get_filter_expression
        from attempting to build relation(value) or attribute.has(relation(value)).
        We do this by returning a non-empty list of error tuples if Model.attribute
        errors are present in self.errors.
        """
        e = []
        if attribute_model_name:
            error_key = '%s.%s' % (attribute_model_name, attribute_model_attribute_name)
            if self.errors.get(error_key) == 'Searching on the %s is not permitted' % error_key:
                e.append(('%s.%s.%s' % (attribute_model_name, attribute_model_attribute_name, relation_name),
                    self._get_invalid_filter_expression_message(attribute_model_name,
                            attribute_model_attribute_name, relation_name, value)))
        error_key = '%s.%s' % (model_name, attribute_name)
        if self.errors.get(error_key) == 'Searching on %s is not permitted' % error_key:
            e.append(('%s.%s.%s' % (model_name, attribute_name, relation_name),
                self._get_invalid_filter_expression_message(model_name, attribute_name,
                                                        relation_name, value)))
        return e

    def _get_meta_relation(self, attribute, model_name, attribute_name):
        """Return the has() or the any() method of the input attribute, depending
        on the value of schema[model_name][attribute_name]['type'].
        """
        return getattr(attribute, {'scalar': 'has', 'collection': 'any'}[
            self.schema[model_name][attribute_name]['type']])

    def _get_filter_expression(self, relation, value, model_name, attribute_name,
                             relation_name, attribute=None, attribute_model_name=None,
                             attribute_model_attribute_name=None):
        """Attempt to return relation(value), catching and storing errors as
        needed.  If 5 args are provided, we are doing a [mod, attr, rel, val]
        search; if all 8 are provided, it's a [mod, attr, attr_mod_attr, rel, val]
        one.
        """
        invalid_model_attribute_errors = self._get_invalid_model_attribute_errors(
            relation, value, model_name, attribute_name, relation_name, attribute,
            attribute_model_name, attribute_model_attribute_name)
        if invalid_model_attribute_errors:
            filter_expression = None
            for e in invalid_model_attribute_errors:
                self._add_to_errors(e[0], e[1])
        else:
            try:
                if attribute_model_name:
                    meta_relation = self._get_meta_relation(attribute, model_name, attribute_name)
                    filter_expression = meta_relation(relation(value))
                else:
                    filter_expression = relation(value)
            except AttributeError:
                filter_expression = None
                self._add_to_errors('%s.%s' % (model_name, attribute_name),
                    'The %s.%s attribute does not represent a many-to-one relation.' % (
                        model_name, attribute_name))
            except TypeError:
                filter_expression = None
                self._add_to_errors('%s.%s.%s' % (model_name, attribute_name, relation_name),
                    self._get_invalid_filter_expression_message(model_name,
                                            attribute_name, relation_name, value))
            except InvalidRequestError as e:
                filter_expression = None
                self.errors['InvalidRequestError'] = str(e)
            except OperationalError as e:
                filter_expression = None
                self.errors['OperationalError'] = str(e)
            except RuntimeError as e:
                filter_expression = None
                self.errors['RuntimeError'] = str(e)
        return filter_expression

    def _get_simple_filter_expression(self, *args):
        """Build an SQLAlchemy filter expression.  Examples:

        1. ['Form', 'transcription', '=', 'abc'] =>
           model.Form.transcription.__eq__('abc')

        2. ['Form', 'enterer', 'first_name', 'like', 'J%'] =>
           self.dbsession.query(model.Form)\
                .filter(model.Form.enterer.has(model.User.first_name.like('J%')))

        3. ['Tag', 'name', 'like', '%abc%'] (when searching the Form model) =>
           aliased_tag = aliased(model.Tag)
           self.dbsession.query(model.Form)\
                .filter(aliased_tag.name.like('%abc%'))\
                .outerjoin(aliased_tag, model.Form.tags)

        4. ['Form', 'tags', 'name', 'like', '%abc%'] =>
           self.dbsession.query(model.Form)\
                .filter(model.Form.tags.any(model.Tag.name.like('%abc%')))
        """
        model_name = self._get_model_name(args[0])
        attribute_name = self._get_attribute_name(args[1], model_name)
        if len(args) == 4:
            model = self._get_model(model_name)
            relation_name = self._get_relation_name(args[2], model_name, attribute_name)
            value = self._get_value(args[3], model_name, attribute_name, relation_name)
            attribute = self._get_attribute(attribute_name, model, model_name)
            relation = self._get_relation(relation_name, attribute, attribute_name, model_name)
            return self._get_filter_expression(relation, value, model_name, attribute_name, relation_name)
        else:
            attribute_model_name = self._get_attribute_model_name(attribute_name, model_name)
            attribute_model_attribute_name = self._get_attribute_name(args[2], attribute_model_name)
            relation_name = self._get_relation_name(args[3], attribute_model_name, attribute_model_attribute_name)
            value = self._get_value(args[4], attribute_model_name, attribute_model_attribute_name, relation_name)
            model = self._get_model(model_name, False)
            attribute = self._get_attribute(attribute_name, model, model_name)
            attribute_model = self._get_model(attribute_model_name, False)
            attribute_model_attribute = self._get_attribute(attribute_model_attribute_name, attribute_model, attribute_model_name)
            relation = self._get_relation(relation_name, attribute_model_attribute, attribute_model_attribute_name, attribute_model_name)
            return self._get_filter_expression(relation, value, model_name, attribute_name, relation_name,
                                             attribute, attribute_model_name, attribute_model_attribute_name)

    def get_search_parameters(self):
        """Given the view's resource-configured SQLAQueryBuilder instance,
        return the list of attributes and their aliases and licit relations
        relevant to searching.
        """
        return {
            'attributes':
                self.schema[self.model_name],
            'relations': self.relations
        }
