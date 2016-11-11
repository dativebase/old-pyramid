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

"""Utility functions, classes and constants.

.. module:: utils
   :synopsis: Utility functions, classes and constants.

A number of functions, classes and constants used throughout the application.

"""

import os
import re
import errno
import datetime
import unicodedata
import string
import smtplib
import gzip
import zipfile
import codecs
import configparser
from random import choice, shuffle
from shutil import rmtree
from passlib.hash import pbkdf2_sha512
from uuid import uuid4, UUID
from mimetypes import guess_type
import json
from sqlalchemy import engine_from_config
from sqlalchemy.sql import or_, not_, desc, asc
from sqlalchemy.orm import subqueryload, joinedload, sessionmaker
from .. import models
#import old.models
model = models
from ..models import Form, File, Collection
from ..models.meta import Model, Base
from paste.deploy import appconfig
from pyramid.threadlocal import get_current_registry

# from pylons import app_globals, session, url
# TODO: purge app_globals from OLD
# TODO: create app_globals in get_current_registry().settings
# TODO: get beaker session
# TODO: url generation in Pyramid?

from formencode.schema import Schema
from formencode.validators import Int, UnicodeString, OneOf
from markdown import Markdown
from docutils.core import publish_parts
from subprocess import Popen, PIPE
import transaction
import zope.sqlalchemy

import logging

log = logging.getLogger(__name__)


################################################################################
# File system functions
################################################################################


map2directory = {
    'file': 'files',
    'files': 'files',
    'reduced_files': os.path.join('files', 'reduced_files'),
    'users': 'users',
    'user': 'users',
    'corpora': 'corpora',
    'corpus': 'corpora',
    'phonologies': 'phonologies',
    'phonology': 'phonologies',
    'morphologies': 'morphologies',
    'morphology': 'morphologies',
    'morphological_parsers': 'morphological_parsers',
    'morphologicalparsers': 'morphological_parsers',
    'morphologicalparser': 'morphological_parsers',
    'morpheme_language_models': 'morpheme_language_models',
    'morphemelanguagemodels': 'morpheme_language_models',
    'morphemelanguagemodel': 'morpheme_language_models'
}


map2subdirectory = {
    'corpora': 'corpus',
    'corpus': 'corpus',
    'phonologies': 'phonology',
    'phonology': 'phonology',
    'morphologies': 'morphology',
    'morphology': 'morphology',
    'morphological_parsers': 'morphological_parser',
    'morphologicalparsers': 'morphological_parser',
    'morphologicalparser': 'morphological_parser',
    'morpheme_language_models': 'morpheme_language_model',
    'morphemelanguagemodels': 'morpheme_language_model',
    'morphemelanguagemodel': 'morpheme_language_model'
}


def get_OLD_directory_path(directory_name, settings):
    """Return the absolute path to an OLD directory in /store."""
    try:
        store = settings['permanent_store']
        return os.path.join(store, map2directory[directory_name])
    except Exception as e:
        print('Exception when joining store path to directory_name'
              ' {}'.format(directory_name))
        print(settings)
        print(e)
        return None


def get_model_directory_path(model_object, settings):
    """Return the path to a model object's directory, e.g., <Morphology 1> will
    return /store/morphologies/morphology_1/.
    """
    return os.path.join(
        get_OLD_directory_path(model_object.__tablename__, settings),
        '%s_%d' % (map2subdirectory[model_object.__tablename__],
                   model_object.id)
    )


def get_model_file_path(model_object, model_directory_path, file_type=None):
    """Return the path to a foma-based model's file of the given type.
    This function serves to provide a consistent interface for retrieving file
    paths for parser-related files.
    :param model_object: a phonology, morphology or morphological parser model
        object.
    :param str model_directory_path: the absolute path to the directory that
        houses the files of the foma-based model (i.e., phonology, morphology
        or morphophonology).
    :param str file_type: one of 'script', 'binary', 'compiler' or 'log'.
    :returns: an absolute path to the file of the supplied type for the model
        object given.
    TODO: remove the model id suffix from the file name: redundant.  Will
        require fixes in the tests.
    TODO: file_type now defaults to None so that extensionless paths can be
        returned -- make sure this is not causing bugs.
    """
    file_type2extension = {
        'script': '.script',
        'binary': '.foma',
        'compiler': '.sh',
        'log': '.log',
        'lexicon': '.pickle',
        'dictionary': '_dictionary.pickle',
        'lm_corpus': '.txt',
        'arpa': '.lm',
        'lm_trie': '.pickle',
        'vocabulary': '.vocab'
    }
    tablename = model_object.__tablename__
    temp = {'morphologicalparser': 'morphophonology'}.get(tablename, tablename)
    file_name = map2subdirectory.get(temp, temp)
    return os.path.join(
        model_directory_path,
        '%s_%d%s' % (file_name, model_object.id,
                     file_type2extension.get(file_type, ''))
    )


def create_OLD_directories(settings):
    """Make all of the required OLD directories."""
    for directory_name in ('files', 'reduced_files', 'users', 'corpora',
                           'phonologies', 'morphologies',
                           'morphological_parsers'):
        make_directory_safely(get_OLD_directory_path(directory_name, settings))


def get_modification_time(path):
    """Return the modification time of the file or directory with ``path``.
    Return None if path doesn't exist.
    """
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


get_file_modification_time = get_modification_time


def create_user_directory(user, settings):
    """Create a directory named ``user.username`` in
    ``<permanent_store>/users/``.
    """
    try:
        make_directory_safely(os.path.join(
            get_OLD_directory_path('users', settings),
            user.username))
    except (TypeError, KeyError) as e:
        print(e)
        raise Exception('The settings dict was inadequate.')


def destroy_user_directory(user, settings):
    """Destroys a directory named ``user.username`` in
    ``<permanent_store>/users/``.
    """
    try:
        rmtree(os.path.join(get_OLD_directory_path('users', settings),
                            user.username))
    except (TypeError, KeyError):
        raise Exception('The settings dict was inadequate.')


def rename_user_directory(old_name, new_name, settings):
    try:
        old_path = os.path.join(get_OLD_directory_path('users', settings),
                                old_name)
        new_path = os.path.join(get_OLD_directory_path('users', settings),
                                new_name)
        try:
            os.rename(old_path, new_path)
        except OSError:
            make_directory_safely(new_path)
    except (TypeError, KeyError):
        raise Exception('The settings dict was inadequate.')


def destroy_all_directories(directory_name, settings):
    """Remove all subdirectories from ``<permanent_store>/directory_name``,
    e.g., all in /store/corpora/.
    """
    try:
        dir_path = get_OLD_directory_path(directory_name, settings)
        for name in os.listdir(dir_path):
            path = os.path.join(dir_path, name)
            if os.path.isdir(path):
                rmtree(path)
    except (TypeError, KeyError) as e:
        raise Exception('The settings dict was inadequate (%s).' % e)


def make_directory_safely(path):
    """Create a directory and avoid race conditions.
    Taken from
    http://stackoverflow.com/questions/273192/python-best-way-to-create-directory-if-it-doesnt-exist-for-file-write.
    Listed as ``make_sure_path_exists``.
    """
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def secure_filename(path):
    """Removes null bytes, path.sep and path.altsep from a path.
    From http://lucumr.pocoo.org/2010/12/24/common-mistakes-as-web-developer/
    """
    patt = re.compile(r'[\0%s]' % re.escape(''.join(
        [os.path.sep, os.path.altsep or ''])))
    return patt.sub('', path)


def clean_and_secure_filename(path):
    return secure_filename(path)\
        .replace("'", "")\
        .replace('"', '')\
        .replace(' ', '_')


################################################################################
# String functions
################################################################################


def to_single_space(string):
    """Remove leading and trailing whitespace and replace newlines, tabs and
    sequences of 2 or more space to one space.
    """
    patt = re.compile(' {2,}')
    return patt.sub(' ', string.strip().replace('\n', ' ').replace('\t', ' '))


def remove_all_white_space(string):
    """Remove all spaces, newlines and tabs."""
    return string.replace('\n', '').replace('\t', '').replace(' ', '')


def esc_RE_meta_chars(string):
    """Escapes regex metacharacters so that we can formulate an SQL regular
    expression based on an arbitrary, user-specified inventory of
    graphemes/polygraphs::
        >>> esc_RE_meta_chars('-')
        '\\\-'
    """
    def esc(c):
        if c in '\\^$*+?{,}.|][()^-':
            return re.escape(c)
        return c
    return ''.join([esc(c) for c in string])


def camel_case2lower_space(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1).lower()


################################################################################
# Unicode functions
################################################################################


def normalize(unistr):
    """Return a unistr using canonical decompositional normalization (NFD)."""
    try:
        return unicodedata.normalize('NFD', unistr)
    except TypeError:
        return unicodedata.normalize('NFD', str(unistr))
    except UnicodeDecodeError:
        return unistr


def normalize_dict(dict_):
    """NFD normalize all unicode values in dict_."""
    for key in dict_:
        try:
            dict_[key] = normalize(dict_[key])
        except TypeError:
            pass
    return dict_


################################################################################
# Query Convenience Functions
################################################################################


def get_grammaticalities():
    try:
        return get_application_settings().grammaticalities.replace(
                                                            ' ', '').split(',')
    except AttributeError:
        return []

def get_morpheme_delimiters_DEPRECATED():
    """Return the morpheme delimiters from app settings as a list."""
    application_settings = get_application_settings()
    try:
        morpheme_delimiters = application_settings.morpheme_delimiters
    except AttributeError:
        return []
    try:
        return morpheme_delimiters and morpheme_delimiters.split(',') or []
    except AttributeError:
        return []

def get_morpheme_delimiters(type_='list'):
    """Return the morpheme delimiters from app settings as an object of type ``type_``."""
    application_settings = get_application_settings()
    morpheme_delimiters = getattr(application_settings, 'morpheme_delimiters', '')
    if type_ != 'list':
        return morpheme_delimiters
    if morpheme_delimiters:
        return morpheme_delimiters.split(',')
    return []

def is_lexical(form):
    """Return True if the input form is lexical, i.e, if neither its morpheme
    break nor its morpheme gloss lines contain the space character or any of the
    morpheme delimiters.  Note: designed to work on dict representations of forms
    also.
    """
    delimiters = get_morpheme_delimiters() + [' ']
    try:
        return bool(form.morpheme_break) and bool(form.morpheme_gloss) and not (
                    set(delimiters) & set(form.morpheme_break) and
                    set(delimiters) & set(form.morpheme_gloss))
    except AttributeError:
        return bool(form['morpheme_break']) and bool(form['morpheme_gloss']) and not (
                    set(delimiters) & set(form['morpheme_break']) and
                    set(delimiters) & set(form['morpheme_gloss']))
    except:
        return False

def get_paginated_query_results(query, paginator):
    if 'count' not in paginator:
        paginator['count'] = query.count()
    start, end = get_start_and_end_from_paginator(paginator)
    items = query.slice(start, end).all()
    if paginator.get('minimal'):
        items = minimal(items)
    return {
        'paginator': paginator,
        'items': items
    }

def minimal(models_array):
    """Return a minimal representation of the models in `models_array`. Right
    now, this means we just return the id, the datetime_entered and the
    datetime_modified. Useful for graphing data and for checking for updates.

    """

    return [minimal_model(model) for model in models_array]

def minimal_model(model):
    return {
        'id': model.id,
        'datetime_entered': getattr(model, 'datetime_entered', None),
        'datetime_modified': getattr(model, 'datetime_modified', None)
    }

def add_pagination(query, paginator):
    if (paginator and paginator.get('page') is not None and
        paginator.get('items_per_page') is not None):
        paginator = PaginatorSchema.to_python(paginator)    # raises formencode.Invalid if paginator is invalid
        return get_paginated_query_results(query, paginator)
    else:
        if paginator and paginator.get('minimal'):
            return minimal(query.all())
        return query.all()

def get_last_modified(result):
    """Return a ``datetime`` instance representing the most recent modification
    of the result set in ``result``. Useful for cacheing, i.e., via
    Last-Modified header.
    """
    if 'items' in result:
        result = result['items']
    if result:
        return sorted(r.datetime_modified for r in result)[-1]\
            .strftime('%a, %d %b %Y %H:%M:%S GMT')
    return None

def add_order_by(query, order_by_params, query_builder, primary_key='id'):
    """Add an ORDER BY clause to the query using the get_SQLA_order_by method of
    the supplied query_builder (if possible) or using a default ORDER BY <primary_key> ASC.
    """
    if order_by_params and order_by_params.get('order_by_model') and \
    order_by_params.get('order_by_attribute') and order_by_params.get('order_by_direction'):
        order_by_params = OrderBySchema.to_python(order_by_params)
        order_by_params = [order_by_params['order_by_model'],
            order_by_params['order_by_attribute'], order_by_params['order_by_direction']]
        order_by_expression = query_builder.get_SQLA_order_by(order_by_params, primary_key)
        query_builder.clear_errors()
        return query.order_by(order_by_expression)
    else:
        model_ = getattr(model, query_builder.model_name)
        return query.order_by(asc(getattr(model_, primary_key)))


################################################################################
# OLD model objects getters: for defaults and testing
################################################################################

def generate_default_administrator(**kwargs):
    admin = model.User()
    admin.first_name = 'Admin'
    admin.last_name = 'Admin'
    admin.username = 'admin'
    admin.email = 'admin@example.com'
    admin.salt = generate_salt()
    admin.password = str(encrypt_password('adminA_1', admin.salt))
    admin.role = 'administrator'
    admin.input_orthography = None
    admin.output_orthography = None
    admin.page_content = ''
    create_user_directory(admin, **kwargs)
    return admin

def generate_default_contributor(**kwargs):
    contributor = model.User()
    contributor.first_name = 'Contributor'
    contributor.last_name = 'Contributor'
    contributor.username = 'contributor'
    contributor.email = 'contributor@example.com'
    contributor.salt = generate_salt()
    contributor.password = str(encrypt_password(
        'contributorC_1', contributor.salt))
    contributor.role = 'contributor'
    contributor.input_orthography = None
    contributor.output_orthography = None
    contributor.page_content = ''
    create_user_directory(contributor, **kwargs)
    return contributor

def generate_default_viewer(**kwargs):
    viewer = model.User()
    viewer.first_name = 'Viewer'
    viewer.last_name = 'Viewer'
    viewer.username = 'viewer'
    viewer.email = 'viewer@example.com'
    viewer.salt = generate_salt()
    viewer.password = str(encrypt_password('viewerV_1', viewer.salt))
    viewer.role = 'viewer'
    viewer.input_orthography = None
    viewer.output_orthography = None
    viewer.page_content = ''
    create_user_directory(viewer, **kwargs)
    return viewer

def generate_default_home_page():
    homepage = model.Page()
    homepage.name = 'home'
    homepage.heading = 'Welcome to the OLD'
    homepage.markup = 'reStructuredText'
    homepage.content = """
The Online Linguistic Database is a web application that helps people to
document, study and learn a language.
        """
    homepage.markup = 'restructuredtext'
    return homepage

def generate_default_help_page():
    helppage = model.Page()
    helppage.name = 'help'
    helppage.heading = 'OLD Application Help'
    helppage.markup = 'reStructuredText'
    helppage.content = """
Welcome to the help page of this OLD application.

This page should contain content entered by your administrator.
        """
    helppage.markup = 'restructuredtext'
    return helppage

def generate_default_orthography1():
    orthography1 = model.Orthography()
    orthography1.name = 'Sample Orthography 1'
    orthography1.orthography = 'p,t,k,m,s,[i,i_],[a,a_],[o,o_]'
    orthography1.lowercase = True
    orthography1.initial_glottal_stops = True
    return orthography1

def generate_default_orthography2():
    orthography2 = model.Orthography()
    orthography2.name = 'Sample Orthography 2'
    orthography2.orthography = 'b,d,g,m,s,[i,i\u0301],[a,a\u0301],[o,o\u0301]'
    orthography2.lowercase = True
    orthography2.initial_glottal_stops = True
    return orthography2

def generate_default_application_settings(orthographies=[],
                                          unrestricted_users=[]):
    english_orthography = ', '.join(list(string.ascii_lowercase))
    application_settings = model.ApplicationSettings()
    application_settings.object_language_name = 'Unspecified'
    application_settings.object_language_id = 'uns'
    application_settings.metalanguage_name = 'English'
    application_settings.metalanguage_id = 'eng'
    application_settings.metalanguage_inventory = english_orthography
    application_settings.orthographic_validation = 'None'
    application_settings.narrow_phonetic_inventory = ''
    application_settings.narrow_phonetic_validation = 'None'
    application_settings.broad_phonetic_inventory = ''
    application_settings.broad_phonetic_validation = 'None'
    application_settings.narrow_phonetic_inventory = ''
    application_settings.narrow_phonetic_validation = 'None'
    application_settings.morpheme_break_is_orthographic = False
    application_settings.morpheme_break_validation = 'None'
    application_settings.phonemic_inventory = ''
    application_settings.morpheme_delimiters = '-,='
    application_settings.punctuation = """.,;:!?'"\u2018\u2019\u201C\u201D[]{}()-"""
    application_settings.grammaticalities = '*,#,?'
    application_settings.storage_orthography = orthographies[1] if 1 < len(orthographies) else None
    application_settings.input_orthography = orthographies[0] if 0 < len(orthographies) else None
    application_settings.output_orthography = orthographies[0] if 0 < len(orthographies) else None
    application_settings.unrestricted_users = unrestricted_users
    return application_settings

def generate_restricted_tag():
    restricted_tag = model.Tag()
    restricted_tag.name = 'restricted'
    restricted_tag.description = '''Forms tagged with the tag 'restricted'
can only be viewed by administrators, unrestricted users and the users they were
entered by.

Note: the restricted tag cannot be deleted and its name cannot be changed.
'''
    return restricted_tag

def generate_foreign_word_tag():
    foreign_word_tag = model.Tag()
    foreign_word_tag.name = 'foreign word'
    foreign_word_tag.description = '''Use this tag for lexical entries that are
not from the object language. For example, it might be desirable to create a
form as lexical entry for a proper noun like "John".  Such a form should be
tagged as a "foreign word". This will allow forms containing "John" to have
gapless syntactic category string values. Additionally, the system ignores
foreign word transcriptions when validating user input against orthographic,
phonetic and phonemic inventories.

Note: the foreign word tag cannot be deleted and its name cannot be changed.
'''
    return foreign_word_tag

def generate_default_form():
    form = Form()
    form.UUID = str(uuid4())
    form.transcription = 'test transcription'
    form.morpheme_break_ids = 'null'
    form.morpheme_gloss_ids = 'null'
    form.datetime_entered = now()
    translation = model.Translation()
    translation.transcription = 'test translation'
    form.translations.append(translation)
    return form

def generate_default_file():
    file = model.File()
    file.name = 'test_file_name' # VARCHAR 255, UNIQUE
    file.MIME_type = 'image/jpeg' # VARCHAR 255
    file.size = 1024 # INT
    file.description = 'An image of the land.' # TEXT
    #date_elicited # DATE
    #elicitor # INT, FOREIGN KEY: USER ID
    #enterer # INT, FOREIGN KEY: USER ID
    #speaker # INT, FOREIGN KEY: SPEAKER ID
    #utterance_type # VARCHAR 255
    #embedded_file_markup # TEXT
    #embedded_file_password # VARCHAR 255
    return file

def generate_default_elicitation_method():
    elicitation_method = model.ElicitationMethod()
    elicitation_method.name = 'test elicitation method'
    elicitation_method.description = 'test elicitation method description'
    return elicitation_method

def generate_s_syntactic_category():
    syntactic_category = model.SyntacticCategory()
    syntactic_category.name = 'S'
    syntactic_category.description = 'Tag sentences with S.'
    return syntactic_category

def generate_n_syntactic_category():
    syntactic_category = model.SyntacticCategory()
    syntactic_category.name = 'N'
    syntactic_category.description = 'Tag nouns with N.'
    return syntactic_category

def generate_v_syntactic_category():
    syntactic_category = model.SyntacticCategory()
    syntactic_category.name = 'V'
    syntactic_category.description = 'Tag verbs with V.'
    return syntactic_category

def generate_num_syntactic_category():
    syntactic_category = model.SyntacticCategory()
    syntactic_category.name = 'Num'
    syntactic_category.description = 'Tag number morphology with Num.'
    return syntactic_category

def generate_default_speaker():
    speaker = model.Speaker()
    speaker.first_name = 'test speaker first name'
    speaker.last_name = 'test speaker last name'
    speaker.dialect = 'test speaker dialect'
    speaker.page_content = 'test speaker page content'
    return speaker

def generate_default_user():
    user = model.User()
    user.username = 'test user username'
    user.first_name = 'test user first name'
    user.last_name = 'test user last name'
    user.email = 'test user email'
    user.affiliation = 'test user affiliation'
    user.role = 'contributor'
    user.page_content = 'test user page content'
    return user

def generate_default_source():
    source = model.Source()
    source.type = 'book'
    source.key = str(uuid4())
    source.author = 'test author'
    source.title = 'test title'
    source.publisher = 'Mouton'
    source.year = 1999
    return source


################################################################################
# Date & Time-related Functions
################################################################################


def now():
    return datetime.datetime.utcnow()


def round_datetime(dt):
    """Round a datetime to the nearest second."""
    discard = datetime.timedelta(microseconds=dt.microsecond)
    dt -= discard
    if discard >= datetime.timedelta(microseconds=500000):
        dt += datetime.timedelta(seconds=1)
    return dt


def datetime_string2datetime(datetime_string, RDBMSName=None,
                             mysql_engine=None):
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
    """Parse an ISO 8601-formatted date into a Python date object."""
    try:
        return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        return None


def human_readable_seconds(seconds):
    return '%02dm%02ds' % (seconds / 60, seconds % 60)


################################################################################
# Miscellaneous Functions & Classes
################################################################################

def get_int(input_):
    try:
        return int(input_)
    except (ValueError, TypeError):
        return None


class FakeForm:
    pass


class State(object):
    """Empty class used to create a state instance with a 'full_dict' attribute
    that points to a dict of values being validated by a schema. For example,
    the call to FormSchema().to_python in controllers/forms.py requires this
    State() instance as its second argument in order to make the inventory-based
    validators work correctly (see, e.g., ValidOrthographicTranscription).
    """
    pass


def get_state_object(values={}, dbsession=None, logged_in_user=None, **kwargs):
    """Return a State instance with some special attributes needed in the forms
    and oldcollections controllers.
    """
    state = State()
    state.full_dict = values
    state.dbsession = dbsession
    state.user = logged_in_user
    for key, val in kwargs.items():
        setattr(state, key, val)
    return state


################################################################################
# Authorization Functions
################################################################################

def user_is_authorized_to_access_model(user, model_object, unrestricted_users):
    """Return True if the user is authorized to access the model object.  Models
    tagged with the 'restricted' tag are only accessible to administrators,
    their enterers and unrestricted users.
    """
    if user.role == 'administrator':
        return True
    if isinstance(model_object, (Form, File, Collection)):
        tags = model_object.tags
        tag_names = [t.name for t in tags]
        enterer_id = model_object.enterer_id
    else:
        model_backup_dict = model_object.get_dict()
        tags = model_backup_dict['tags']
        tag_names = [t['name'] for t in tags]
        enterer_id = model_backup_dict['enterer'].get('id', None)
    return not tags or \
        'restricted' not in tag_names or \
        user in unrestricted_users or \
        user.id == enterer_id



def get_unrestricted_users():
    """Return the list of unrestricted users in
    app_globals.application_settings.application_settings.unrestricted_users.
    """
    return getattr(getattr(getattr(app_globals, 'application_settings', None),
                   'application_settings', None), 'unrestricted_users', [])


unauthorized_msg = {'error': 'You are not authorized to access this resource.'}


def get_RDBMS_name(**kwargs):
    settings = get_settings(**kwargs)
    try:
        SQLAlchemyURL = settings['sqlalchemy.url']
        return SQLAlchemyURL.split(':')[0]
    except (TypeError, KeyError):
        # WARNING The exception below should be raised during production, development
        # and testing -- however, it must be replaced with the log to allow Sphinx to
        # import the controllers and build the API docs
        #log.warn('The config object was inadequate.')
        raise Exception('The settings dict was inadequate.')


################################################################################
# Some simple and ubiquitously used schemata
################################################################################

class PaginatorSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = False
    items_per_page = Int(not_empty=True, min=1)
    page = Int(not_empty=True, min=1)

class OrderBySchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = False
    order_by_model = UnicodeString()
    order_by_attribute = UnicodeString()
    order_by_direction = OneOf(['asc', 'desc'])

################################################################################
# File-specific data & functionality
################################################################################

allowed_file_types = (
    #'text/plain',
    #'application/x-latex',
    #'application/msword',
    #'application/vnd.ms-powerpoint',
    #'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    #'application/vnd.oasis.opendocument.text',
    'application/pdf',
    'image/gif',
    'image/jpeg',
    'image/png',
    'audio/mpeg',
    'audio/ogg',
    'audio/x-wav',
    'video/mpeg',
    'video/mp4',
    'video/ogg',
    'video/quicktime',
    'video/x-ms-wmv'
)

def is_audio_video_file(file_):
    return 'audio' in file_.MIME_type or 'video' in file_.MIME_type

utterance_types = (
    'None',
    'Object Language Utterance',
    'Metalanguage Utterance',
    'Mixed Utterance'
)

guess_type = guess_type

def clear_directory_of_files(directory_path):
    """Removes all files from the directory path but leaves the directory."""
    for filename in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, filename)):
            os.remove(os.path.join(directory_path, filename))


################################################################################
# Collection-specific data & functionality
################################################################################

collection_types = (
    'story',
    'elicitation',
    'paper',
    'discourse',
    'other'
)

# Corpus formats -- determine how a corpus is rendered as a file, e.g., a
# treebank will output a file containing representations of phrase structure for
# each form in the corpus and the file will be called ``corpus_1.tbk`` ...

corpus_formats = {
    'treebank': {
        'extension': 'tbk',
        'suffix': '',
        'writer': lambda f: '(TOP-%d %s)\n' % (f.id, f.syntax)
    },
    'transcriptions only': {
        'extension': 'txt',
        'suffix': '_transcriptions',
        'writer': lambda f: '%s\n' % f.transcription
    }
}


# This is the regex for finding form references in the contents of collections.
form_reference_pattern = re.compile('[Ff]orm\[([0-9]+)\]')

# This is the regex for finding collection references in the contents of collections.
#collection_reference_pattern = re.compile('[cC]ollection[\(\[](\d+)[\)\]]')
collection_reference_pattern = re.compile('[cC]ollection[\[\(](\d+)[\]\)]')

def get_ids_of_forms_referenced(referencing_string):
    """Return a list of form ids corresponding to the form references in ``referencing_string``."""
    return [int(id) for id in form_reference_pattern.findall(referencing_string)]

def rst2html(string):
    try:
        return publish_parts(string, writer_name='html')['html_body']
    except:
        return string

def rst2latex(string, **kwargs):
    """Use docutils.core to return a string of restructuredtext as a full LaTeX
    document.

    """

    return publish_parts(string, writer_name='latex')['whole']\
        .replace('\\usepackage[utf8]{inputenc}', '')

def md2html(string):
    try:
        return Markdown().convert(string)
    except:
        return string

markup_language_to_func = {
    'reStructuredText': rst2html,
    'Markdown': md2html
}

markup_languages = markup_language_to_func.keys()

def get_HTML_from_contents(contents, markup_language):
    return markup_language_to_func.get(markup_language, rst2html)(contents)


# Subject to change!  Or maybe these should be user-definable ...
syntactic_category_types = (
    'lexical',
    'phrasal',
    'sentential'
)

form_statuses = ('tested', 'requires testing')

user_roles = (
    'viewer',
    'contributor',
    'administrator'
)

def generate_salt():
    return str(uuid4().hex).encode('utf8')

def encrypt_password(password, salt):
    """Use PassLib's pbkdf2 implementation to generate a hash from a password.
    Cf. http://packages.python.org/passlib/lib/passlib.hash.pbkdf2_digest.html#passlib.hash.pbkdf2_sha512
    """
    return pbkdf2_sha512.encrypt(password, salt=salt)

def generate_password(length=12):
    lc_letters = string.letters[:26]
    uc_letters = string.letters[26:]
    digits = string.digits
    symbols = string.punctuation.replace('\\', '')
    password = [choice(lc_letters) for i in range(3)] + \
               [choice(uc_letters) for i in range(3)] + \
               [choice(digits) for i in range(3)] + \
               [choice(symbols) for i in range(3)]
    shuffle(password)
    return ''.join(password)


def get_search_parameters(query_builder):
    """Given an SQLAQueryBuilder instance, return (relative to the model being
    searched) the list of attributes and their aliases and licit relations
    relevant to searching.
    """
    return {
        'attributes': query_builder.schema[query_builder.model_name],
        'relations': query_builder.relations
    }


################################################################################
# Email Functionality
################################################################################

def get_value_from_gmail_config(gmail_config, key, default=None):
    try:
        return gmail_config.get('DEFAULT', key)
    except:
        return default

def get_gmail_config(**kwargs):
    config = get_config(**kwargs)
    try:
        here = config['here']
    except (TypeError, KeyError):
        raise Exception('The config object was inadequate.')
    gmail_config_path = os.path.join(here, 'gmail.ini')
    gmail_config = configparser.ConfigParser()
    try:
        gmail_config.read(gmail_config_path)
        return gmail_config
    except configparser.Error:
        return None

def get_object_language_id():
    return getattr(get_application_settings(), 'object_language_id', 'old')

def send_password_reset_email_to(user, new_password, **kwargs):
    """Send the "password reset" email to the user.  **kwargs should contain a
    config object (with 'config' as key) or a config file name (e.g.,
    'production.ini' with 'config_filename' as key).  If
    password_reset_smtp_server is set to smtp.gmail.com in the config file, then
    the email will be sent using smtp.gmail.com and the system will expect a
    gmail.ini file with valid gmail_from_address and gmail_from_password values.
    If the config file is test.ini and there is a test_email_to value, then that
    value will be the target of the email -- this allows testers to verify that
    an email is in fact being received.
    """

    to_address = user.email
    config = get_config(**kwargs)
    if os.path.split(config['__file__'])[-1] == 'test.ini' and config.get('test_email_to'):
        to_address = config.get('test_email_to')
    password_reset_smtp_server = config.get('password_reset_smtp_server')
    language_id = get_object_language_id()
    from_address = '%s@old.org' % language_id
    app_name = language_id.upper() + ' OLD' if language_id != 'old' else 'OLD'
    app_URL = url('/', qualified=True)
    if password_reset_smtp_server == 'smtp.gmail.com':
        gmail_config = get_gmail_config(config=config)
        from_address = get_value_from_gmail_config(gmail_config, 'gmail_from_address')
        from_password = get_value_from_gmail_config(gmail_config, 'gmail_from_password')
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(from_address, from_password)
    else:
        server = smtplib.SMTP('localhost')
    to_addresses = [to_address]
    message = ''.join([
        'From: %s <%s>\n' % (app_name, from_address),
        'To: %s %s <%s>\n' % (user.first_name, user.last_name, to_address),
        'Subject: %s Password Reset\n\n' % app_name,
        'Your password at %s has been reset to:\n\n    %s\n\n' % (app_URL, new_password),
        'Please change it once you have logged in.\n\n',
        '(Do not reply to this email.)'
    ])
    failures = server.sendmail(from_address, to_addresses, message)
    server.quit()
    return failures


def compile_query(query, **kwargs):
    """Return the SQLAlchemy query as a bona fide MySQL query.  Taken from
    http://stackoverflow.com/questions/4617291/how-do-i-get-a-raw-compiled-sql-query-from-a-sqlalchemy-expression.
    """

    RDBMSName = get_RDBMS_name(**kwargs)
    if RDBMSName == 'mysql':
        from sqlalchemy.sql import compiler
        from MySQLdb.converters import conversions, escape
        dialect = query.session.bind.dialect    # an object representing the dialect; dialect.name will be 'sqlite' or 'mysql'
        statement = query.statement     # The query as SQL with variable names instead of values, e.g., 'WHERE form.transcription like :transcription_1'
        comp = compiler.SQLCompiler(dialect, statement)
        enc = dialect.encoding
        params = []
        for k in comp.positiontup:
            v = comp.params[k]
            if isinstance(v, unicode):
                v = v.encode(enc)
            params.append( escape(v, conversions) )
        return (comp.string.encode(enc) % tuple(params)).decode(enc)
    else:
        return str(query)


################################################################################
# Command-line processes
################################################################################

def get_subprocess(command):
    """Return a subprocess process.  The command argument is a list.  See
    http://docs.python.org/2/library/subprocess.html
    """
    try:
        return Popen(command, stderr=PIPE, stdout=PIPE, stdin=PIPE)
    except OSError:
        return None

def command_line_program_installed_bk(command):
    """Command is the list representing the command-line utility."""
    try:
        return bool(get_subprocess(command))
    except:
        return False

def command_line_program_installed(program):
    """Check if program is in the user's PATH

    .. note::

        I used to use Python subprocess to attempt to execute the program, but I think searching PATH is better.

    """
    for path in os.environ['PATH'].split(os.pathsep):
        path = path.strip('"')
        program_path = os.path.join(path, program)
        if os.path.isfile(program_path) and os.access(program_path, os.X_OK):
            return True
    return False

def ffmpeg_installed():
    """Check if the ffmpeg command-line utility is installed on the host.

    Check first if the answer to this question is cached in app_globals.

    """
    try:
        return app_globals.ffmpeg_installed
    except AttributeError:
        ffmpeg_installed = command_line_program_installed('ffmpeg')
        app_globals.ffmpeg_installed = ffmpeg_installed
        return ffmpeg_installed

def foma_installed(force_check=False):
    """Check if the foma and flookup command-line utilities are installed on the host.

    Check first if the answer to this question is cached in app_globals.

    """
    if force_check:
        return command_line_program_installed('foma') and \
            command_line_program_installed('flookup')
    try:
        return app_globals.foma_installed
    except AttributeError:
        foma_installed = command_line_program_installed('foma') and \
                        command_line_program_installed('flookup')
        app_globals.foma_installed = foma_installed
        return foma_installed

def ffmpeg_encodes(format_):
    """Check if ffmpeg encodes the input format.  First check if it's installed."""
    if ffmpeg_installed():
        try:
            return app_globals.ffmpeg_encodes[format_]
        except (AttributeError, KeyError):
            process = Popen(['ffmpeg', '-formats'], stderr=PIPE, stdout=PIPE)
            stdout, stderr = process.communicate()
            encodes_format = 'E %s' % format_ in stdout
            try:
                app_globals.ffmpeg_encodes[format_] = encodes_format
            except AttributeError:
                app_globals.ffmpeg_encodes = {format_: encodes_format}
            return encodes_format
    return False


def get_user_full_name(user):
    return '%s %s' % (user.first_name, user.last_name)


validation_values = ('None', 'Warning', 'Error')

# How long to wait (in seconds) before terminating a process that is trying to
# compile a foma script.
phonology_compile_timeout = 30
morphology_compile_timeout = 60 * 3000  # Give foma morphology scripts 30 minutes to compile
morphological_parser_compile_timeout = 60 * 60  # Give foma morphological parser scripts 60 minutes to compile
morpheme_language_model_generate_timeout = 60 * 15

# The word boundary symbol is used in foma FST scripts to denote the beginning or end of a word,
# i.e., it can be referred to in phonological rules, e.g., define semivowelDrop glides -> 0 || "#" _;$
# The system will wrap inputs in this symbol when applying a phonology against them.
word_boundary_symbol = '#'

def foma_output_file2dict(file_, remove_word_boundaries=True):
    """Return the output of a foma apply request as a dictionary.

    :param file file_: utf8-encoded file object with tab-delimited i/o pairs.
    :param bool remove_word_boundaries: toggles whether word boundaries are removed in the output
    :returns: dictionary of the form ``{i1: [01, 02, ...], i2: [...], ...}``.

    .. note::

        The flookup foma utility returns '+?' when there is no output for a given 
        input -- hence the replacement of '+?' with None below.

    """
    def word_boundary_remover(x):
        if (x[0:1], x[-1:]) == (word_boundary_symbol, word_boundary_symbol):
            return x[1:-1]
        else:
            return x
    remover = word_boundary_remover if remove_word_boundaries else (lambda x: x)
    result = {}
    for line in file_:
        line = line.strip()
        if line:
            i, o = map(remover, line.split('\t')[:2])
            result.setdefault(i, []).append({'+?': None}.get(o, o))
    return dict((k, filter(None, v)) for k, v in result.items())

morphology_script_types = ('regex', 'lexc')

def get_file_length(file_path):
    """Return the number of lines in a file.
    
    cf. http://stackoverflow.com/questions/845058/how-to-get-line-count-cheaply-in-python

    """
    with open(file_path) as f:
        i = -1
        for i, l in enumerate(f):
            pass
    return i + 1

def compress_file(file_path):
    """Compress the file at ``file_path`` using ``gzip``.

    Save it in the same directory with a ".gz" extension.

    """
    with open(file_path, 'rb') as fi:
        gzip_path = '%s.gz' % file_path
        fo = gzip.open(gzip_path, 'wb')
        fo.writelines(fi)
        fo.close()
        return gzip_path

def zipdir(path):
    """Create a compressed .zip archive of the directory at ``path``.

    Note that the relative path names of all files in the tree under ``path``
    are maintained.  E.g,. if ``path/dir/x.txt`` exists, then when ``path.zip``
    is unzipped, ``path/dir/x.txt`` will be created.

    """
    dirname = os.path.dirname(path)
    zip_path = '%s.zip' % path
    zip_file = zipfile.ZipFile(zip_path, 'w')
    for root, dirs, files in os.walk(path):
        for file_ in files:
            full_path = os.path.join(root, file_)
            relative_path = full_path[len(dirname):]
            zip_file.write(full_path, relative_path, zipfile.ZIP_DEFLATED)
    zip_file.close()
    return zip_path

class ZipFile(zipfile.ZipFile):

    @property
    def directory_name(self):
        try:
            return self._directory_name
        except AttributeError:
            self._directory_name = os.path.splitext(os.path.basename(self.filename))[0]
            return self._directory_name

    def write_directory(self, directory_path, **kwargs):
        for root, dirs, files in os.walk(directory_path):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                if kwargs.get('keep_dir', False):
                    new_path = os.path.join(self.directory_name,
                        os.path.basename(directory_path), file_name)
                else:
                    new_path = os.path.join(self.directory_name, file_name)
                self.write(full_path, new_path, zipfile.ZIP_DEFLATED)

    def write_file(self, file_path):
        new_path = os.path.join(self.directory_name, os.path.basename(file_path))
        self.write(file_path, new_path, zipfile.ZIP_DEFLATED)


def pretty_print_bytes(num_bytes):
    """Print an integer byte count to human-readable form.
    """
    if num_bytes is None:
        return 'File size unavailable.'
    KiB = 1024
    MiB = KiB * KiB
    GiB = KiB * MiB
    TiB = KiB * GiB
    PiB = KiB * TiB
    EiB = KiB * PiB
    ZiB = KiB * EiB
    YiB = KiB * ZiB
    if num_bytes > YiB:
        return '%.3g YiB' % (num_bytes / YiB)
    elif num_bytes > ZiB:
        return '%.3g ZiB' % (num_bytes / ZiB)
    elif num_bytes > EiB:
        return '%.3g EiB' % (num_bytes / EiB)
    elif num_bytes > PiB:
        return '%.3g PiB' % (num_bytes / PiB)
    elif num_bytes > TiB:
        return '%.3g TiB' % (num_bytes / TiB)
    elif num_bytes > GiB:
        return '%.3g GiB' % (num_bytes / GiB)
    elif num_bytes > MiB:
        return '%.3g MiB' % (num_bytes / MiB)
    elif num_bytes > KiB:
        return '%.3g KiB' % (num_bytes / KiB)


def get_language_objects(here, truncated=True):
    """Return a list of language models generated from a text file in
    ``public/iso_639_3_languages_data``.
    """
    languages_path = os.path.join(
        here, 'old', 'static', 'iso_639_3_languages_data')
    # Use the truncated languages file if we are running tests
    if truncated:
        iso_639_3FilePath = os.path.join(
            languages_path, 'iso_639_3_trunc.tab')
    else:
        iso_639_3FilePath = os.path.join(
            languages_path, 'iso_639_3.tab')
    iso_639_3File = codecs.open(iso_639_3FilePath, 'r', 'utf-8')
    language_list = [l.split('\t') for l in iso_639_3File]
    return [get_language_object(language) for language in language_list
            if len(language) == 8]

def get_language_object(language_list):
    """Given a list of ISO-639-3 language data, return an OLD language model."""
    language = model.Language()
    language.Id = language_list[0]
    language.Part2B = language_list[1]
    language.Part2T = language_list[2]
    language.Part1 = language_list[3]
    language.Scope = language_list[4]
    language.Type = language_list[5]
    language.Ref_Name = language_list[6]
    language.Comment = language_list[7]
    return language


# String to use when a morpheme's category cannot be determined
unknown_category = '?'

# Default delimiter: used to delimit break-gloss-category strings in the ``break_gloss_category`` attribute.
default_delimiter = '|'

# Rare delimiter: used to delimit morphemes shapes from glosses in foma lexica.
rare_delimiter = '\u2980'


def chunker(sequence, size):
    """Convert a sequence to a generator that yields subsequences of the sequence of size ``size``."""
    return (sequence[position:position + size] for position in xrange(0, len(sequence), size))


def get_morpheme_splitter():
    """Return a function that will split words into morphemes."""
    morpheme_splitter = lambda x: [x] # default, word is morpheme
    morpheme_delimiters = get_morpheme_delimiters()
    if morpheme_delimiters:
        morpheme_splitter = re.compile('([%s])' % ''.join([esc_RE_meta_chars(d) for d in morpheme_delimiters])).split
    return morpheme_splitter

def extract_word_pos_sequences(form, unknown_category, morpheme_splitter=None, extract_morphemes=False):
    """Return the unique word-based pos sequences, as well as (possibly) the morphemes, implicit in the form.

    :param form: a form model object
    :param morpheme_splitter: callable that splits a strings into its morphemes and delimiters
    :param str unknown_category: the string used in syntactic category strings when a morpheme-gloss pair is unknown
    :param morphology: the morphology model object -- needed because its extract_morphemes_from_rules_corpus
        attribute determines whether we return a list of morphemes.
    :returns: 2-tuple: (set of pos/delimiter sequences, list of morphemes as (pos, (mb, mg)) tuples).

    """
    if not form.syntactic_category_string:
        return None, None
    morpheme_splitter = morpheme_splitter or get_morpheme_splitter()
    pos_sequences = set()
    morphemes = []
    sc_words = form.syntactic_category_string.split()
    mb_words = form.morpheme_break.split()
    mg_words = form.morpheme_gloss.split()
    for sc_word, mb_word, mg_word in zip(sc_words, mb_words, mg_words):
        pos_sequence = tuple(morpheme_splitter(sc_word))
        if unknown_category not in pos_sequence:
            pos_sequences.add(pos_sequence)
            if extract_morphemes:
                morpheme_sequence = morpheme_splitter(mb_word)[::2]
                gloss_sequence = morpheme_splitter(mg_word)[::2]
                for pos, morpheme, gloss in zip(pos_sequence[::2], morpheme_sequence, gloss_sequence):
                    morphemes.append((pos, (morpheme, gloss)))
    return pos_sequences, morphemes

def get_word_category_sequences(corpus):
    """Return the category sequence types of validly morphologically analyzed words
    in ``corpus`` as well as the exemplars ids of said types.  This is useful for getting
    a sense of which word "templates" are common.

    :returns: a list of 2-tuples of the form [(category_sequence, [id1, id2, ...]), ...]
        ordered by the number of exemplar ids in the list that is the second member.

    """
    result = {}
    morpheme_splitter = get_morpheme_splitter()
    for form in corpus.forms:
        category_sequences, morphemes = form.extract_word_pos_sequences(
            unknown_category, morpheme_splitter, extract_morphemes=False)
        if category_sequences:
            for category_sequence in category_sequences:
                result.setdefault(category_sequence, []).append(form.id)
    return sorted(result.items(), key=lambda t: len(t[1]), reverse=True)

language_model_toolkits = {
    'mitlm': {
        'smoothing_algorithms': ['ML', 'FixKN', 'FixModKN', 'FixKNn', 'KN', 'ModKN', 'KNn'], # cf. http://code.google.com/p/mitlm/wiki/Tutorial
        'executable': 'estimate-ngram'
    }
}

lm_start = '<s>'
lm_end = '</s>'

