# Copyright 2017 Joel Dunham
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

"""This module introspects the OLD's models and returns various data structures
based on that model. In particular, it contains functions that can generate
JSON-LD schema definitions for OLD models and their properties/attributes at a
given OLD version.

TODO:

1. My terms are all hierarchical and all need definitions:

   - old: "An OLD is ... (from module docstring of old/__init__.py?)
   - old/forms: "The forms of an OLD are a set of OLD form resources stored
                within a single OLD instance." (from docstring of model module?)
   - old/Form: "An OLD form is ..." (from docstring of model class)
   - old/Form/transcription: "An OLD form transcription is ..." (from docstring
     of model column)

2. Encode the languages of strings, i.e., internationalization:
   https://www.w3.org/TR/json-ld/#string-internationalization

   - it looks like you can use ISO 639-3
   - it looks like specific terms can have specific languages::

    {
        '@context': {
            'transcription': {
                '@id': 'http://schema.onlinelinguisticdatabase.org/Form/transcription',
                '@language': 'bla'
            }
        }
    }

3. Use abbreviated forms of IRIs:
   {
       '@context': {
            'ex': 'http://schema.onlinelinguisticdatabase.org/',
            'transcription': 'ex:Form/transcription
       }
   }

"""

import importlib
import inspect
import logging
import os
import pprint

from sqlalchemy.orm.attributes import (
    InstrumentedAttribute,
    CollectionAttributeImpl,
    ScalarObjectAttributeImpl,
    ScalarAttributeImpl
)

import old
from old.lib.utils import to_single_space
import old.models as old_models


LOGGER = logging.getLogger(__name__)
OLD_SCHEMA_URL = 'http://schema.onlinelinguisticdatabase.org/{}'.format(
    old.__version__)


def get_old_model_classes():
    """Introspect all of the OLD models and return a dict mapping the names of
    the models to the classes themselves.
    """
    old_model_classes = {}
    for model_module_name in os.listdir('./old/models/'):
        if (    model_module_name in ('__init__.py') or
                not model_module_name.endswith('.py')):
            continue
        module_path = 'old.models.{}'.format(
            model_module_name).replace('.py', '')
        model_module = importlib.import_module(module_path)
        for name, val in model_module.__dict__.items():
            if inspect.isclass(val):
                cls = inspect.getmro(val)[0]
                name = cls.__name__
                if (    issubclass(cls, old_models.Model) and
                        name not in ('Base', 'Model')):
                    old_model_classes[name] = cls
    return old_model_classes


def get_model_docstring(model_cls):
    """Return an OLD class's docstring in a format that succinctly describes
    what the model is. That is, if it has a docstring, just return the first
    paragraph with all contiguous whitespace collapsed.
    """
    docstring = model_cls.__doc__ or ''
    if docstring:
        docstring = to_single_space(docstring.split('\n\n')[0])
    return docstring


def get_general_col_term_defn(col_name, model_name):
    """Return a default OLD JSON-LD schema. These columns are common to many
    OLD models and they always have the same semantics so there is no need to
    define them on a per-model basis.
    """
    return {
        'tablename': lambda mname: (
            'The name of the relational database table that an OLD {mname} is'
            ' stored in.'.format(mname=mname)),
        'id': lambda mname: (
            'The integer id of an OLD {mname}. Created by the relational database'
            ' management system. No two instances of a given OLD {mname} in a'
            ' given OLD instance can have the same id'
            ' value.'.format(mname=mname)),
        'UUID': lambda mname: (
            'A Universally unique identifier assigned to an OLD'
            ' {mname}.'.format(mname=mname)),
        'datetime_entered': lambda mname: (
            'The date and time when an OLD {mname} was entered into the'
            ' database, i.e., its creation time.'.format(mname=mname)),
        'datetime_created': lambda mname: (
            'The date and time when an OLD {mname} was'
            ' created.'.format(mname=mname)),
        'datetime_modified': lambda mname: (
            'The date and time when an OLD {mname} was last'
            ' modified.'.format(mname=mname)),
        'enterer': lambda mname: (
            'The person (OLD user) who entered/created an OLD'
            ' {mname}.'.format(mname=mname)),
        'modifier': lambda mname: (
            'The person (OLD user) who last modified an OLD'
            ' {mname}.'.format(mname=mname)),
        'tags': lambda mname: (
            'A collection of zero or more OLD tag resources associated to an'
            ' OLD {mname}'.format(mname=mname)),
        'description': lambda mname: (
            'A description of an OLD {mname}.'.format(mname=mname)),
        'name': lambda mname: 'The name of an OLD {mname}.'.format(mname=mname),
        'generate_succeeded': lambda mname: (
            'A boolean indicating whether the most recent attempt to generate an'
            ' OLD {mname} has succeeded. Useful because the generation of a(n)'
            ' {mname} is a long-running process in a separate'
            ' thread.'.format(mname=mname)),
        'generate_message': lambda mname: (
            'A string indicating details of the result of the most recent attempt'
            ' to generate an OLD {mname}. Useful because the generation of a(n)'
            ' {mname} is a long-running process in a separate'
            ' thread.'.format(mname=mname)),
        'generate_attempt': lambda mname: (
            'A UUID string uniquely identifying an attempt to generate a particular'
            ' OLD {mname}. A change in this value indicates that a generation'
            ' attempt has ended.'.format(mname=mname)),
        'compile_succeeded': lambda mname: (
            'A boolean indicating whether the most recent attempt to compile an'
            ' OLD {mname} has succeeded. Useful for finite-state resources that'
            ' must be parsed, composed, minimized, determinized, etc. and saved to'
            ' a compact binary representation.'.format(mname=mname)),
        'compile_message': lambda mname: (
            'A string indicating details of the result of the most recent attempt'
            ' to compile an OLD {mname}. Useful for finite-state resources that'
            ' must be parsed, composed, minimized, determinized, etc. and saved'
            ' to a compact binary representation.'.format(mname=mname)),
        'compile_attempt': lambda mname: (
            'A UUID string uniquely identifying an attempt to compile a particular'
            ' OLD {mname}. A change in this value indicates that a compilation'
            ' attempt has ended.'.format(mname=mname))
    }.get(col_name, lambda mname: None)(model_name)


def get_col_term_defn(col_name, col_obj, model_name, old_model_class):
    """Get a JSON-LD term definition for an OLD model's column (property)."""
    try:
        result = getattr(col_obj, '__doc__', None)
    except AttributeError:
        result = None
    if not result:
        result = get_general_col_term_defn(col_name, model_name)
    if not result:
        backrefdocattr = '{}_doc'.format(col_name)
        result = getattr(old_model_class, backrefdocattr, None)
    return result


def get_relational_term_counterpart(needle, schema):
    """Return the term definition of a relational attribute of an OLD resource,
    given ``needle`` which is a JSON-LD IRI string corresponding to the
    ``_id``-suffixed attribute that references the id value of the related
    resource.
    """
    for term, term_def in schema.items():
        if term == needle:
            return term_def
        if term.replace('_', '') == needle:
            return term_def
    return None


def fix_id_suffixed_cols(jsonld_schema):
    """Attempt to get JSON-LD term definitions for ``_id``-suffixed attributes
    of OLD models/resources, using their ``_id``-less counterparts.
    """
    new_jsonld_schema = jsonld_schema.copy()
    for term, val in jsonld_schema.items():
        term_def = val['definition']
        if term_def is None and term.endswith('_id'):
            counterpart_term = term.replace('_id', '')
            counterpart_val = get_relational_term_counterpart(counterpart_term, jsonld_schema)
            if counterpart_val:
                new_val = counterpart_val.copy()
                new_val['definition'] = 'An integer identifier for the {} relation. {}'.format(
                    counterpart_term, counterpart_val['definition'])
                new_jsonld_schema[term] = new_val
    return new_jsonld_schema


def model_is_m2m_relation(model_term_defn):
    """Return ``True`` if the model described by the docstring
    ``model_term_defn`` is a dummy model that simply encodes a many-to-many
    relationship, e.g., the ``FormFile`` model. We don't need these models
    described in our JSON-LD schema. At present, we use a simple heuristic for
    determining this, i.e., we look for a characteristic substring in the
    docstring.
    """
    return 'encodes the many-to-many relationship between' in model_term_defn


def get_old_jsonld_schema():
    """Return a JSON-LD schema for the OLD. That is, return a dict, whose
    attributes are model schema paths and whose values are ...::

        {
            "http://schema.onlinelinguisticdatabase.org/Form":
                "String describing what a form is.",
            ...
        }

    """
    jsonld_schema = {}
    old_model_classes = get_old_model_classes()
    for model_name in sorted(old_model_classes.keys()):
        old_model_class = old_model_classes[model_name]
        model_term = model_name
        model_term_iri = '{}/{}'.format(OLD_SCHEMA_URL, model_name)
        model_term_defn = get_model_docstring(old_model_class)
        if model_is_m2m_relation(model_term_defn):
            continue
        jsonld_schema[model_term] = {
            'definition': model_term_defn,
            '@id': model_term_iri
        }
        for col_name in old_model_class.__dict__:
            if '_sa_' == col_name[:4] or col_name.startswith('__'):
                continue
            col_obj = getattr(old_model_class, col_name)
            try:
                assert isinstance(
                    col_obj, InstrumentedAttribute)
            except Exception as e:
                continue
            col_term = '{}/{}'.format(model_term, col_name)
            col_term_iri = '{}/{}'.format(OLD_SCHEMA_URL, col_term)
            col_term_defn = get_col_term_defn(
                col_name, col_obj, model_name, old_model_class)
            val = {
                '@id': col_term_iri,
                'definition': col_term_defn
            }
            if isinstance(col_obj.impl, (ScalarObjectAttributeImpl,)):
                val['@type'] = '@id'
            jsonld_schema[col_term] = val
    jsonld_schema = fix_id_suffixed_cols(jsonld_schema)
    return jsonld_schema


def get_jsonld_form_context(jsonld_schema=None):
    if not jsonld_schema:
        jsonld_schema = get_old_jsonld_schema()
    form_context = {}
    for term, val in jsonld_schema.items():
        parts = term.split('/')
        if len(parts) > 1 and parts[0] == 'Form':
            term = term.split('/')[1]
            if term.endswith('_id'):
                continue
            if val.get('@type'):
                new_val = {
                    '@type': val['@type'],
                    '@id': val['@id']
                }
            else:
                new_val = val['@id']
            form_context[term] = new_val
    return form_context





"""
'http://schema.onlinelinguisticdatabase.org/2.0.0/Form': 'A Form is a linguistic form, i.e., a word, morpheme, or sentence. It may represent an utterance at a specific time by a particular person '
                                                          'or an abstract generalization such as a morpheme.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/UUID': 'A Universally unique identifier assigned to an OLD Form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/break_gloss_category': 'The morpheme break, morpheme gloss and (syntactic) category string values of a form all interleaved into a single '
                                                                               'string. This value is auto-generated by the OLD.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/collections': 'The collections, i.e., texts (e.g., papers, elicitation records, etc.), that a given form is a part of.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/comments': 'General-purpose notes and commentary about the form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/corpora': 'The set of corpora that an OLD form belongs to.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/date_elicited': 'The date when a particular form was elicited.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/datetime_entered': 'The date and time when an OLD Form was entered into the database, i.e., its creation time.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/datetime_modified': 'The date and time when an OLD Form was last modified.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/elicitation_method': 'How a linguistic form was elicited. Examples: “volunteered”, “judged elicitor’s utterance”, “translation task”, etc.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/elicitationmethod_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/elicitationmethod relation. How '
                                                                               'a linguistic form was elicited. Examples: “volunteered”, “judged elicitor’s utterance”, “translation task”, etc.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/elicitor': 'The linguistic fieldworker who elicited the form with the help of the consultant.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/elicitor_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/elicitor relation. The linguistic '
                                                                      'fieldworker who elicited the form with the help of the consultant.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/enterer': 'The person (OLD user) who entered/created an OLD Form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/enterer_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/enterer relation. The person (OLD user) '
                                                                     'who entered/created an OLD Form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/files': 'The digital files (e.g., audio, video, image or text) that are associated to a given form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/grammaticality': 'The grammaticality of the form, e.g., grammatical, ungrammatical, questionable, infelicitous in a given context. Possible '
                                                                         'values are defined in the application settings if each OLD.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/id': 'The integer id of an OLD Form. Created by the relational database management system. No two instances of a given OLD Form in a given '
                                                             'OLD instance can have the same id value.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/memorizers': 'The set of OLD user resources that currently have a particular OLD form in their set of remembered forms.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/modifier': 'The person (OLD user) who last modified an OLD Form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/modifier_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/modifier relation. The person (OLD user) '
                                                                      'who last modified an OLD Form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/morpheme_break': 'A sequence of morpheme shapes and delimiters. The OLD assumes phonemic shapes (e.g., “in-perfect”), but phonetic (i.e., '
                                                                         'allomorphic, e.g., “im-perfect”) ones are ok.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/morpheme_break_ids': 'An OLD-generated value that essentially memoizes/caches the forms (and their relevant properties) that match the '
                                                                             'morphemes transcriptions/shapes identified in the morpheme break value of a form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/morpheme_gloss': 'A sequence of morpheme glosses and delimiters, isomorphic to the morpheme break sequence, e.g., “NEG-parfait”.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/morpheme_gloss_ids': 'An OLD-generated value that essentially memoizes/caches the forms (and their relevant properties) that match the '
                                                                             'morpheme glosses identified in the morpheme break value of a form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/narrow_phonetic_transcription': 'A phonetic transcription, probably in IPA.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/phonetic_transcription': 'A narrow phonetic transcription, probably in IPA.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/semantics': 'A semantic representation of the meaning of the form in some string-based format.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/source': 'The textual source (e.g., research paper, text collection, book of learning materials) from which the form was drawn, if '
                                                                 'applicable.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/source_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/source relation. The textual source (e.g., '
                                                                    'research paper, text collection, book of learning materials) from which the form was drawn, if applicable.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/speaker': 'The speaker (consultant) who produced or judged the form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/speaker_comments': 'Comments about the form made by the speaker/consultant.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/speaker_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/speaker relation. The speaker (consultant) '
                                                                     'who produced or judged the form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/status': 'The status of the form: “tested” for data that have been elicited/tested/verified with a consultant or “requires testing” for data '
                                                                 'that are posited and still need testing/elicitation.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/syntactic_category': 'The category (syntactic and/or morphological) of the form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/syntactic_category_string': 'A sequence of categories (and morpheme delimiters) that is auto-generated by an OLD based on the '
                                                                                    'morphemes/glosses in the morpheme break and morpheme gloss values of a form and the categories of matching '
                                                                                    'lexical items in the database.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/syntacticcategory_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/syntacticcategory relation. The '
                                                                               'category (syntactic and/or morphological) of the form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/syntax': 'A syntactic phrase structure representation in some kind of string-based format.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/tags': 'A collection of zero or more OLD tag resources associated to an OLD Form',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/transcription': 'A transcription of a linguistic form, probably orthographic.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/translations': 'The translations for the form. Each translation may have its own grammaticality/acceptibility specification indicating '
                                                                       'whether it is an acceptable translation for the given form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/verifier': 'The person (OLD user) who has verified the reliability/accuracy of this form.',
 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/verifier_id': 'An integer identifier for the http://schema.onlinelinguisticdatabase.org/2.0.0/Form/verifier relation. The person (OLD user) '
                                                                      'who has verified the reliability/accuracy of this form.',
"""




