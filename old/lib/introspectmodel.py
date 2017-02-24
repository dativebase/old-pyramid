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

- http://json-ld.org/spec/latest/json-ld-api-best-practices/

TODO:

Connect my terms to other ontologies/schemata:

- ORE aggregate
- Dublin Core schemas (dcmitype)
- schema.org


1. My terms are all hierarchical and all need definitions:

   - old: "An OLD is ... (from module docstring of old/__init__.py?)
   - old/forms: "The forms of an OLD are a set of OLD form resources stored
                within a single OLD instance." (from docstring of model module?)
   - old/Form: "An OLD form is ..." (from docstring of model class)
   - old/Form/transcription: "An OLD form transcription is ..." (from docstring
     of model column)

2. Static, versioned schema site,
   - Served at URL = schema.onlinelinguisticdatabase.org/<VERSION>/
   - URL/OLD.jsonld:         JSON-LD context for entire OLD schema
   - URL/OLD:                HTML page with term definition for OLD
   - URL/forms:              HTML page with term definition for collection of OLD forms
   - URL/Form:               HTML page with term definition for collection of OLD forms
   - URL/Form.jsonld:        JSON-LD context for a single OLD form
   - URL/Form/transcription: HTML page defining the attribute (e.g., Form transcription)

3. Encode the languages of strings, i.e., internationalization:
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

4. Use abbreviated forms of IRIs:
   {
       '@context': {
            'ex': 'http://schema.onlinelinguisticdatabase.org/',
            'transcription': 'ex:Form/transcription
       }
   }

"""

import importlib
import inspect
import json
import logging
import os
import pprint
import shutil

import inflect
from sqlalchemy.orm.attributes import (
    InstrumentedAttribute,
    CollectionAttributeImpl,
    ScalarObjectAttributeImpl,
    ScalarAttributeImpl
)

from old.lib.constants import __version__
from old.lib.utils import (
    to_single_space,
    camel_case2lower_space
)
import old.models as old_models


inflect_p = inflect.engine()
inflect_p.classical()


LOGGER = logging.getLogger(__name__)

# TODO: this isn't really a schema. The URL here should be changed and it
# should be an OWL ontology.
OLD_SCHEMA_URL = 'http://schema.onlinelinguisticdatabase.org/{}'.format(
    __version__)


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


def fix_id_suffixed_cols(old_schema):
    """Attempt to get JSON-LD term definitions for ``_id``-suffixed attributes
    of OLD models/resources, using their ``_id``-less counterparts.
    """
    for term, val in old_schema.items():
        term_def = val['definition']
        if term_def is None and term.endswith('_id'):
            counterpart_term = term.replace('_id', '')
            counterpart_val = get_relational_term_counterpart(counterpart_term, old_schema)
            if counterpart_val:
                val['definition'] = 'An integer identifier for the {} relation. {}'.format(
                    counterpart_term, counterpart_val['definition'])
    return old_schema


def model_is_m2m_relation(model_term_defn):
    """Return ``True`` if the model described by the docstring
    ``model_term_defn`` is a dummy model that simply encodes a many-to-many
    relationship, e.g., the ``FormFile`` model. We don't need these models
    described in our JSON-LD schema. At present, we use a simple heuristic for
    determining this, i.e., we look for a characteristic substring in the
    docstring.
    """
    return 'encodes the many-to-many relationship between' in model_term_defn


def get_collection_term(model_term):
    """Return the name of the collection of resources corresponding to the name
    of the resource model passed in. E.g., return 'syntactic categories' for
    'SyntacticCategory'.
    """
    if model_term == 'ApplicationSettings':
        return 'application_settings', 'application settings'
    with_space = camel_case2lower_space(model_term)
    *butlast, last = with_space.split()
    hmn = ' '.join(butlast + [inflect_p.plural(last)])
    return hmn.replace(' ', '_'), hmn


def get_collection_defn(collection_term, model_term):
    return ('The {collection} of an OLD are the entire set of {model} resources'
            ' within that OLD.'.format(
                collection=collection_term, model=model_term))


def introspect_old_schema():
    """Return a representation of the schema of the OLD. This dict forms the
    raw material for creating a set of HTML pages and JSON-LD '@context'
    objects that can be referenced in the creation of JSON-LD exports of an OLD
    instance's data set.

    Returns a dict, whose keys are IRI paths representing an OLD, a resource
    collection, a resource, or a resource attribute, and whose values are dicts
    with '@id', 'definition' and possibly '@type' keys. For example::

        {
            'Form/transcription': {
                '@id': 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/transcription',
                'definition': 'A transcription of a linguistic form, probably orthographic.'
            },
            'OLD': {...},
            'forms': {...},
            'Form': {...},
            ...
        }

    """
    # An entry for the entire OLD.
    old_docstring = ('The Online Linguistic Database (OLD) is software for'
        ' linguistic fieldwork.  An OLD (instance) is a specific deployment of'
        ' the OLD software as a RESTful web service used to document and analyze'
        ' a particular (usually language-specific) data set.')
    old_schema = {
        'OLD': {
            'definition': old_docstring,
            '@id': '/OLD',
            'entity_type': 'old instance'
        }
    }
    old_model_classes = get_old_model_classes()
    for model_name in sorted(old_model_classes.keys()):
        # An entry for each OLD resource, e.g., "Form"
        old_model_class = old_model_classes[model_name]
        model_term = model_name
        model_term_iri = '/{}'.format(model_name)
        model_term_defn = get_model_docstring(old_model_class)
        collection_term, collection_term_hmn = get_collection_term(model_term)
        if model_is_m2m_relation(model_term_defn):
            continue
        old_schema[model_term] = {
            'definition': model_term_defn,
            '@id': model_term_iri,
            'entity_type': 'old resource',
            'collection': collection_term
        }
        # An entry for each OLD resource collection, e.g., "forms"
        collection_term_iri = '/{}'.format(collection_term)
        collection_term_defn = get_collection_defn(collection_term_hmn, model_term)
        old_schema[collection_term] = {
            'definition': collection_term_defn,
            '@id': collection_term_iri,
            'entity_type': 'old collection',
            'resource': model_term
        }
        # An entry for each OLD resource attribute, e.g., "Form/transcription"
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
            col_term_iri = '/{}'.format(col_term)
            col_term_defn = get_col_term_defn(
                col_name, col_obj, model_name, old_model_class)
            val = {
                '@id': col_term_iri,
                'definition': col_term_defn,
                'entity_type': 'old resource attribute',
                'parent_resource': model_term
            }
            # Many-to-one relationships should valuate to IRIs in JSON-LD
            if isinstance(col_obj.impl, (ScalarObjectAttributeImpl,)):
                val['@type'] = '@id'
            old_schema[col_term] = val
    old_schema = fix_id_suffixed_cols(old_schema)
    return old_schema

CSS = '''

body {
    font-family: monospace;
    font-size: 15pt;
}

div#main {
    width: 50%;
    margin: 1em auto 1em auto;
}

'''.strip()

HTML_TEMPLATE = '''
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
  <head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
    <title>OLD Schema</title>
    <link rel="stylesheet" type="text/css" href="/{version}/style.css"/>
    <!-- <script type="text/javascript" src="script.js"></script> -->
  </head>
  <body>
    <div id="main">
    {main}
    </div>
  </body>
</html>
'''.strip()


def get_old_inst_html(valdict, old_schema):
    """Return the HTML for the schema page for the OLD itself."""
    inner_html = [
        '      <h1>Online Linguistic Database (OLD) Instance</h1>',
        '      <p>' + valdict['definition'] + '</p>',
        '      <p>An OLD may contain zero or more resources belonging to the'
        '         following collections:</p>',
        '      <ul>'
    ]
    collections = {term: valdict for term, valdict in old_schema.items() if
                   valdict['entity_type'] == 'old collection'}
    for collname in sorted(collections):
        valdict = collections[collname]
        hmn = collname.replace('_', ' ')
        inner_html.append(
            '        <li><a href="/{version}/{coll_url}">{hmn}</a></li>'.format(
                version=__version__, coll_url=valdict['@id'], hmn=hmn))
    inner_html.append('      </ul>')
    return HTML_TEMPLATE.format(version=__version__,
                                main='\n'.join(inner_html))


def get_breadcrumbs(entity_type, **kwargs):
    """Return HTML breadcrumbs for the OLD entity of type ``entity_type``.
    """
    if entity_type == 'old resource':
        return ' / '.join([
            '<a href="/{version}/">OLD</a>'.format(version=__version__),
            '<a href="/{version}/{coll_iri}">{coll_name}</a>'.format(
                version=__version__, coll_iri=kwargs['coll_iri'],
                coll_name=kwargs['coll_name']),
            kwargs['resource']
        ])
    elif entity_type == 'old collection':
        return ' / '.join([
            '<a href="/{version}/">OLD</a>'.format(version=__version__),
            kwargs['collection']
        ])
    elif entity_type == 'old resource attribute':
        return ' / '.join([
            '<a href="/{version}/">OLD</a>'.format(version=__version__),
            '<a href="/{version}/{coll_iri}">{coll_name}</a>'.format(
                version=__version__, coll_iri=kwargs['coll_iri'],
                coll_name=kwargs['coll_name']),
            '<a href="/{version}/{rsrc_iri}">{rsrc_name}</a>'.format(
                version=__version__, rsrc_iri=kwargs['rsrc_iri'],
                rsrc_name=kwargs['rsrc_name']),
            kwargs['attribute']
        ])



def get_resource_html(resource_name, valdict, old_schema):
    """Return the HTML for an OLD resource, e.g., 'Form'."""
    coll_name = valdict['collection']
    coll_iri = old_schema[coll_name]['@id']
    inner_html = [
        '      <h1>OLD Resource: {}</h1>'.format(resource_name),
        '      <div id="bc">' + get_breadcrumbs(
            'old resource', resource=resource_name, coll_iri=coll_iri,
            coll_name=coll_name) + '</div>',
        '      <p>' +  valdict['definition'] + '</p>',
        '      <p>An OLD {} has the following attributes:</p>'.format(
            resource_name),
        '      <ul>'
    ]
    attributes = {term: valdict for term, valdict in old_schema.items() if
                  valdict.get('parent_resource') == resource_name}
    for attrname in sorted(attributes):
        valdict = attributes[attrname]
        hmn = attrname.split('/')[1].replace('_', ' ')
        inner_html.append(
            '        <li><a href="/{version}/{attr_url}">{hmn}</a></li>'.format(
                version=__version__, attr_url=valdict['@id'], hmn=hmn))
    inner_html.append('      </ul>')
    return HTML_TEMPLATE.format(version=__version__,
                                main='\n'.join(inner_html))


def get_collection_html(coll_name, valdict, old_schema):
    """Return the HTML for an OLD collection, e.g., 'forms'."""
    resource = valdict.get('resource')
    resource_url = old_schema[resource]['@id']
    inner_html = [
        '      <h1>OLD Resource Collection: {}</h1>'.format(coll_name),
        '      <div id="bc">' + get_breadcrumbs(
            'old collection', collection=coll_name) + '</div>',
        '      <p>' +  valdict['definition'] + '</p>',
        '      <p>See <a href="/{version}/{rsrc_url}">{rsrc}</a>.</p>'.format(
            version=__version__, rsrc_url=resource_url, rsrc=resource)
    ]
    return HTML_TEMPLATE.format(version=__version__,
                                main='\n'.join(inner_html))


def get_resource_attribute_html(attr_name, valdict, old_schema):
    """Return the HTML for an OLD resource attribute, e.g., 'transcription' of
    'Form'.
    """
    rsrc_name, attr_name = attr_name.split('/')
    rsrc_iri = old_schema[rsrc_name]['@id']
    coll_name = old_schema[rsrc_name]['collection']
    coll_iri = old_schema[coll_name]['@id']
    inner_html = [
        '      <h1>Attribute {} of OLD Resource <a href="/{}/{}">{}</a></h1>'.format(
            attr_name, __version__, rsrc_iri, rsrc_name),
        '      <div id="bc">' + get_breadcrumbs(
            'old resource attribute', attribute=attr_name, coll_iri=coll_iri,
            coll_name=coll_name, rsrc_iri=rsrc_iri, rsrc_name=rsrc_name) + '</div>',
        '      <p>' +  valdict['definition'] + '</p>',
    ]
    return HTML_TEMPLATE.format(version=__version__,
                                main='\n'.join(inner_html))


def add_html_to_old_schema(old_schema):
    """Add 'html' keys to each dict val in the ``old_schema`` dict. The HTML
    should consist of the OLD entity's definition and, if it is a resource, an
    alphabetic listing of its attributes as links.
    """
    for term, valdict in old_schema.items():
        if valdict['entity_type'] == 'old instance':
            valdict['html'] = get_old_inst_html(valdict, old_schema)
        elif valdict['entity_type'] == 'old collection':
            valdict['html'] = get_collection_html(term, valdict, old_schema)
        elif valdict['entity_type'] == 'old resource':
            valdict['html'] = get_resource_html(term, valdict, old_schema)
        elif valdict['entity_type'] == 'old resource attribute':
            valdict['html'] = get_resource_attribute_html(term, valdict, old_schema)
    return old_schema


def add_jsonld_to_old_schema(old_schema):
    """Update the OLD schema so that it contains JSON-LD objects for the OLD
    data set itself as well as for each OLD resource. At present, the top-level
    object of an OLD JSON-LD object is an OLD which contains resource
    collections that valuate to arrays of resource IRIs::

        {
            "@context": {
                "OLD": "<IRI for dereferencing what an OLD is>",
                ... # MORE DC metadata here about this OLD (export)
            },
            "@id": "<IRI for this entire OLD export>",
            "OLD": {
                "@context": {
                    "forms":
                        "<IRI for dereferencing what an OLD forms resource
                        collection is.>",
                    "syntactic_categories":
                        "<IRI for dereferencing what an OLD syntactic categories
                        resource collection is.>",
                    ...
                },
                "forms": [
                    "<IRI for particular Form resource A>",
                    "<IRI for particular Form resource B>"
                    ...
                ],
                "syntactic_categories": [
                    "<IRI for particular SyntacticCategory resource A>",
                    "<IRI for particular SyntacticCategory resource B>"
                    ...
                ],
                ...
            }

    The value of a single Resource instance, say a Form instance as referenced
    by and "<IRI for particular Form resource A>" would be::

        {
            "@context": {
                "Form": "@id": "<IRI for dereferencing what an OLD Form
                            resource is.>"
            },
            "Form": {
                "@context": {
                    "transcription":
                        "<IRI for dereferencing what an OLD Form.transcription
                          attribute is.>",
                    "enterer": {
                        "@type": "@id",
                        "@id": "<IRI for dereferencing what an OLD Form.enterer
                                 attribute is.>"
                    },
                    ...
                },
                "trancsription": "nitsíkohtaahsi'taki",
                "enterer": "<IRI for a particular OLD user who is the enterer>",
                ...
            }
        }

    """
    old_collection_terms = {}
    for term, val in old_schema.items():
        if val.get('entity_type') == 'old resource':
            jsonld_obj = {
                '@context': {
                    term: '{}{}'.format(OLD_SCHEMA_URL, val['@id'])
                },
                term: {
                    '@context': {}
                }
            }
            attributes = {
                attr_term: attr_val
                for attr_term, attr_val in old_schema.items()
                if attr_val.get('parent_resource') == term}
            for attr_term, attr_val in attributes.items():
                short_term = attr_term.split('/')[1]
                term_type = attr_val.get('@type')
                term_iri = '{}{}'.format(OLD_SCHEMA_URL, attr_val['@id'])
                if term_type:
                    jsonld_obj[term]['@context'][short_term] = {
                        '@type': term_type, '@id': term_iri}
                else:
                    jsonld_obj[term]['@context'][short_term] = term_iri
            val['jsonld'] = jsonld_obj
        elif val.get('entity_type') == 'old collection':
            old_collection_terms[term] = '{}{}'.format(
                OLD_SCHEMA_URL, val['@id'])
        old_schema['OLD']['jsonld'] = {
            '@context': {
                'OLD': '{}{}'.format(OLD_SCHEMA_URL, old_schema['OLD']['@id'])
            },
            'OLD': {
                '@context': old_collection_terms
            }
        }
    return old_schema


def write_schema_html_to_disk(old_schema):
    """Write the versioned OLD schema to disk as a set (hierarchy) of HTML
    files.
    """
    schemata_parent_path = os.path.realpath(os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        '..', '..'))
    schemata_path = os.path.join(schemata_parent_path, 'schemata')
    if not os.path.isdir(schemata_path):
        os.makedirs(schemata_path)
    schema_path = os.path.join(schemata_path, __version__)
    if os.path.isdir(schema_path):
        shutil.rmtree(schema_path)
    os.makedirs(schema_path)
    # write CSS
    css_path = os.path.join(schema_path, 'style.css')
    with open(css_path, 'w') as fileo:
        fileo.write(CSS)
    # write index.html (and redundant OLD/index.html)
    old_inst_index = os.path.join(schema_path, 'index.html')
    with open(old_inst_index, 'w') as fileo:
        fileo.write(old_schema['OLD']['html'])
    old_inst_path = os.path.join(schema_path, 'OLD')
    os.makedirs(old_inst_path)
    old_inst_index = os.path.join(old_inst_path, 'index.html')
    with open(old_inst_index, 'w') as fileo:
        fileo.write(old_schema['OLD']['html'])
    # write OLD.jsonld
    old_jsonld_path = os.path.join(schema_path, 'OLD.jsonld')
    with open(old_jsonld_path, 'w') as fileo:
        fileo.write(
            json.dumps(
                old_schema['OLD']['jsonld'],
                sort_keys=True,
                indent=4,
                separators=(',', ': ')))
    # Write HTML pages for resources and resource collections
    for term, valdict in old_schema.items():
        entity_type = valdict['entity_type']
        if entity_type in ('old collection', 'old resource'):
            path = os.path.join(schema_path, term)
            os.makedirs(path)
            index_path = os.path.join(path, 'index.html')
            with open(index_path, 'w') as fileo:
                fileo.write(valdict['html'])
            # Write the resource's JSON-LD obj to a <RESOURCE>.jsonld file.
            # TODO: when served, .jsonld documents should have the header
            # ``content-type:application/ld+json``
            if entity_type == 'old resource':
                path = os.path.join(schema_path, term + '.jsonld')
                with open(path, 'w') as fileo:
                    fileo.write(
                        json.dumps(
                            valdict['jsonld'],
                            sort_keys=True,
                            indent=4,
                            separators=(',', ': ')))
    # Write HTML pages for resource attributes
    for term, valdict in old_schema.items():
        if valdict['entity_type'] == 'old resource attribute':
            attr_path = os.path.join(schema_path, term)
            os.makedirs(attr_path)
            index_path = os.path.join(attr_path, 'index.html')
            with open(index_path, 'w') as fileo:
                fileo.write(valdict['html'])


def add_filedata_attrs(old_schema):
    """Certain OLD resources, notably Files, implicitly reference file objects
    on disk. These are referenced in the JSON-LD export as IRIs, with
    attributes that contain a ``_filedata`` suffix. This function, adds the
    appropriate ``_filedata``-suffixed attributes to the OLD schema.

    TODOs:

    1. The following parser-related resources can have binary files on disk
       associated with them also:

        - morpheme_language_models
        - morphological_parsers
        - morphologies
        - phonologies

       Tests should be written that create resources of the above types, and
       generate and/or compile them, as appropriate. New ``_filedata``-suffixed
       attributes will be necessary.

    2. The OLD user-specific directories are creates as follows:

        - users
            - <username>

    """
    old_schema.update({
        'File/filename_filedata': {
            '@id': '/File/filename_filedata',
            '@type': '@id',
            'definition': 'The IRI where the binary data of an OLD file can be'
                          ' retrieved.',
            'entity_type': 'old resource attribute',
            'parent_resource': 'File'
        },
        'File/lossy_filename_filedata': {
            '@id': '/File/lossy_filename_filedata',
            '@type': '@id',
            'definition': 'The IRI where the reduced-sized binary data of an'
                          ' OLD file can be retrieved.',
            'entity_type': 'old resource attribute',
            'parent_resource': 'File'
        },
        # Note: Corpora.writetofile can also create .gz and .t2c files
        'CorpusFile/filename_filedata': {
            '@id': '/CorpusFile/filename_filedata',
            '@type': '@id',
            'definition': 'The IRI where the binary data of an OLD corpus file'
                          ' can be retrieved.',
            'entity_type': 'old resource attribute',
            'parent_resource': 'CorpusFile'
        }
    })
    return old_schema


def get_old_schema():
    old_schema = introspect_old_schema()
    old_schema = add_filedata_attrs(old_schema)
    old_schema = add_html_to_old_schema(old_schema)
    old_schema = add_jsonld_to_old_schema(old_schema)
    return old_schema
