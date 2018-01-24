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

"""For building/generating models, e.g., default models.
"""

import codecs
import logging
import os
import string
from uuid import uuid4

import old.models as old_models
from old.lib.utils import (
    now,
    create_user_directory,
    generate_salt,
    encrypt_password
)

LOGGER = logging.getLogger(__name__)


def generate_default_administrator(**kwargs):
    admin = old_models.User()
    admin.first_name = 'Admin'
    admin.last_name = 'Admin'
    admin.username = 'admin'
    admin.email = 'admin@example.com'
    admin.salt = generate_salt()
    admin.password = str(encrypt_password('adminA_1', admin.salt.encode('utf8')))
    admin.role = 'administrator'
    admin.input_orthography = None
    admin.output_orthography = None
    admin.page_content = ''
    create_user_directory(admin, **kwargs)
    return admin


def generate_default_contributor(**kwargs):
    contributor = old_models.User()
    contributor.first_name = 'Contributor'
    contributor.last_name = 'Contributor'
    contributor.username = 'contributor'
    contributor.email = 'contributor@example.com'
    contributor.salt = generate_salt()
    contributor.password = str(encrypt_password(
        'contributorC_1', contributor.salt.encode('utf8')))
    contributor.role = 'contributor'
    contributor.input_orthography = None
    contributor.output_orthography = None
    contributor.page_content = ''
    create_user_directory(contributor, **kwargs)
    return contributor


def generate_default_viewer(**kwargs):
    viewer = old_models.User()
    viewer.first_name = 'Viewer'
    viewer.last_name = 'Viewer'
    viewer.username = 'viewer'
    viewer.email = 'viewer@example.com'
    viewer.salt = generate_salt()
    viewer.password = str(encrypt_password('viewerV_1', viewer.salt.encode('utf8')))
    viewer.role = 'viewer'
    viewer.input_orthography = None
    viewer.output_orthography = None
    viewer.page_content = ''
    create_user_directory(viewer, **kwargs)
    return viewer


def generate_default_home_page():
    homepage = old_models.Page()
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
    helppage = old_models.Page()
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
    orthography1 = old_models.Orthography()
    orthography1.name = 'Sample Orthography 1'
    orthography1.orthography = 'p,t,k,m,s,[i,i_],[a,a_],[o,o_]'
    orthography1.lowercase = True
    orthography1.initial_glottal_stops = True
    return orthography1


def generate_default_orthography2():
    orthography2 = old_models.Orthography()
    orthography2.name = 'Sample Orthography 2'
    orthography2.orthography = 'b,d,g,m,s,[i,i\u0301],[a,a\u0301],[o,o\u0301]'
    orthography2.lowercase = True
    orthography2.initial_glottal_stops = True
    return orthography2


def generate_default_application_settings(orthographies=None,
                                          unrestricted_users=None):
    english_orthography = ', '.join(list(string.ascii_lowercase))
    application_settings = old_models.ApplicationSettings()
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
    application_settings.storage_orthography = orthographies[1] if orthographies else None
    application_settings.input_orthography = orthographies[0] if orthographies else None
    application_settings.output_orthography = orthographies[0] if orthographies else None
    if unrestricted_users:
        application_settings.unrestricted_users = unrestricted_users
    else:
        application_settings.unrestricted_users = []
    return application_settings


def generate_restricted_tag():
    restricted_tag = old_models.Tag()
    restricted_tag.name = 'restricted'
    restricted_tag.description = '''Forms tagged with the tag 'restricted'
can only be viewed by administrators, unrestricted users and the users they were
entered by.

Note: the restricted tag cannot be deleted and its name cannot be changed.
'''
    return restricted_tag


def generate_foreign_word_tag():
    foreign_word_tag = old_models.Tag()
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
    form = old_models.Form()
    form.UUID = str(uuid4())
    form.transcription = 'test transcription'
    form.morpheme_break_ids = 'null'
    form.morpheme_gloss_ids = 'null'
    form.datetime_entered = now()
    translation = old_models.Translation()
    translation.transcription = 'test translation'
    form.translations.append(translation)
    return form


def generate_default_file():
    file = old_models.File()
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
    elicitation_method = old_models.ElicitationMethod()
    elicitation_method.name = 'test elicitation method'
    elicitation_method.description = 'test elicitation method description'
    return elicitation_method


def generate_s_syntactic_category():
    syntactic_category = old_models.SyntacticCategory()
    syntactic_category.name = 'S'
    syntactic_category.description = 'Tag sentences with S.'
    return syntactic_category


def generate_n_syntactic_category():
    syntactic_category = old_models.SyntacticCategory()
    syntactic_category.name = 'N'
    syntactic_category.description = 'Tag nouns with N.'
    return syntactic_category


def generate_v_syntactic_category():
    syntactic_category = old_models.SyntacticCategory()
    syntactic_category.name = 'V'
    syntactic_category.description = 'Tag verbs with V.'
    return syntactic_category


def generate_num_syntactic_category():
    syntactic_category = old_models.SyntacticCategory()
    syntactic_category.name = 'Num'
    syntactic_category.description = 'Tag number morphology with Num.'
    return syntactic_category


def generate_default_speaker():
    speaker = old_models.Speaker()
    speaker.first_name = 'test speaker first name'
    speaker.last_name = 'test speaker last name'
    speaker.dialect = 'test speaker dialect'
    speaker.page_content = 'test speaker page content'
    return speaker


def generate_default_user():
    user = old_models.User()
    user.username = 'test user username'
    user.first_name = 'test user first name'
    user.last_name = 'test user last name'
    user.email = 'test user email'
    user.affiliation = 'test user affiliation'
    user.role = 'contributor'
    user.page_content = 'test user page content'
    return user


def generate_default_source():
    source = old_models.Source()
    source.type = 'book'
    source.key = str(uuid4())
    source.author = 'test author'
    source.title = 'test title'
    source.publisher = 'Mouton'
    source.year = 1999
    return source


def get_language_objects(here, truncated=True):
    """Return a list of language models generated from a text file in
    ``public/iso_639_3_languages_data``.
    """
    languages_path = os.path.join(
        here, 'old', 'static', 'iso_639_3_languages_data')
    # Use the truncated languages file if we are running tests
    if truncated:
        iso_639_3_file_path = os.path.join(
            languages_path, 'iso_639_3_trunc.tab')
    else:
        iso_639_3_file_path = os.path.join(
            languages_path, 'iso_639_3.tab')
    # QUESTION/TODO: codecs used in Python3 still?
    with codecs.open(iso_639_3_file_path, 'r', 'utf-8') as iso_639_3_file:
        language_list = [l.split('\t') for l in iso_639_3_file]
    return [get_language_object(language) for language in language_list
            if len(language) == 8]


def get_language_object(language_list):
    """Given a list of ISO-639-3 language data, return an OLD language model."""
    return old_models.Language(
        Id=language_list[0],
        Part2B=language_list[1],
        Part2T=language_list[2],
        Part1=language_list[3],
        Scope=language_list[4],
        Type=language_list[5],
        Ref_Name=language_list[6],
        Comment=language_list[7]
    )
