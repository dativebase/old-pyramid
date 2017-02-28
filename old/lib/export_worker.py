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

"""OLD JSON-LD/BagIt Export

The exports created are "zipped bags" (.zip files conforming to the BagIt
specification) containing the files on disk of an OLD as well as a
representation of the data set as a set of JSON-LD files.

This module contains the multithreading worker and queue logic for
the long-running processes needed for the creation of OLD exports.

1. Exports are resources that can be:

   a. Created
   b. Read (singleton or collection)
   c. Deleted (if admin)

2. An OLD export is:
   - a .zip file containing all of the data in an OLD at a particular
     moment in time.
   - files are organized according to the bag-it specification
   - a representation of the database as JSON-LD (linked data)
   - (importable into another OLD system; TODO)

3. Created in a separate thread.
   - the client must poll the OLD in order to determine when the export is
     complete.
   - the export should be saved to disk and be efficiently retrievable (a
     static asset, with or without authentication required, see
     http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/assets.html)
   - checked for consistency and repaired, if necessary
     how? get all lastmod times for all resources prior to export
     generation and then re-check them prior to export save? TODO (to consider).

The export worker can only run callables that are global in
:mod:`old.lib.export_worker` and which take keyword arguments. Example usage::

    from old.lib.export_worker import EXPORT_WORKER_Q
    EXPORT_WORKER_Q.put({
        'id': h.generate_salt(),
        'func': 'generate_export',
        'args': {
            'export_id': export.id,
            'user_id': self.logged_in_user.id,
            'settings': self.request.registry.settings,
        }
    })

Cf. http://www.chrismoos.com/2009/03/04/pylons-worker-threads.

For an introduction to Python threading, see
http://www.ibm.com/developerworks/aix/library/au-threadingpython/.

TODO:

1. Use dc:rights (or dcterms:rights and dcterms:RightsStatement) to allow for
   the assertion of access rights over the data set. If the data set is
   private, automatically assert that only contributors+ of the OLD can access
   the data set::

   ex:myVideo dc:rights "May be used only by members of the myProject" .

   ex:myDocuments dcterms:title "Diaries of Juanita Ramirez"
       dcterms:rights _:accessConditions
   _:accessConditions dcterms:title "Access to my stuff"
   dcterms:description "Resources under this right can only be read, searched
                        and used by members of the myProject" .

"""

import csv
import datetime
import json
import logging
import os
import pprint
import queue
import re
import shutil
import threading
from uuid import uuid4

import bagit
import inflect
from paste.deploy import appconfig
from pyld import jsonld
from rdflib import Graph, plugin
from rdflib.serializer import Serializer
from sqlalchemy import create_engine
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import sessionmaker
import transaction

from old.lib.constants import __version__
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
from old.lib.introspectmodel import get_old_schema
import old.models as old_models
from old.models.morphologicalparser import Cache
from old.models import (
    get_engine,
    get_session_factory,
    get_tm_session,
)


LOGGER = logging.getLogger(__name__)
HANDLER = logging.FileHandler('exportworker.log')
FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
HANDLER.setFormatter(FORMATTER)
LOGGER.addHandler(HANDLER)
LOGGER.setLevel(logging.DEBUG)


inflect_p = inflect.engine()
inflect_p.classical()


OOLD_URL = 'http://ontology.onlinelinguisticdatabase.org/2017/02/oold/'

OOLD = {
    "@context": {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcterms": "http://bloody-byte.net/rdf/dc_owl2dl/dcterms/",
        "gold": "http://purl.org/linguistics/gold/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "@base": OOLD_URL,
        "defines": {
            "@reverse": "rdfs:isDefinedBy"
        },
        "propertyOf": { 
            "@id": "rdfs:domain",
            "@type": "@id"
        },
        "propertyOn": { 
            "@id": "rdfs:range",
            "@type": "@id"
        }
    },
    "@id": "",
    "@type": "owl:Ontology",
    "dc:title": "Online Linguistic Database Ontology",
    "dc:description": (
        "An ontology for the Online Linguistic Database, a research data"
        " management system for linguistic fieldwork and language"
        " documentation."),
    # "owl:versionInfo": "v 2.0.0 2017/02/17 21:48:51", TODO: add this

    "defines": [
        {
            "@id": "member",
            "@type": "owl:ObjectProperty",
            "rdfs:label": "member",
            "rdfs:comment": (
                "Expresses that the owl:Thing in the domain contains the"
                " owl:Thing in the range as a member."),
            "rdfs:domain": "owl:Thing",
            "rdfs:range": "owl:Thing"
        },
        # NOTE: redefining here some GOLD DatatypeProperty elements so that
        # their ranges are gold:Thing and not gold:LinguisticUnit. Otherwise,
        # it is not clear how one would relate a
        # gold:WrittenLinguisticExpression to a string literal.
        {
            "@id": "stringRep",
            "@type": "owl:DatatypeProperty",
            "rdfs:label": "stringRep",
            "rdfs:domain": "gold:Thing",
            "rdfs:range": "xsd:string"
        },
        {
            "@id": "phoneticRep",
            "@type": "owl:DatatypeProperty",
            "rdfs:label": "phoneticRep",
            "rdfs:subPropertyOf": "stringRep"
        },
        {
            "@id": "orthographicRep",
            "@type": "owl:DatatypeProperty",
            "rdfs:label": "orthographicRep",
            "rdfs:subPropertyOf": "stringRep"
        },
        {
            "@id": "phonemicRep",
            "@type": "owl:DatatypeProperty",
            "rdfs:label": "phonemicRep",
            "rdfs:subPropertyOf": "stringRep"
        }
    ]
}


################################################################################
# WORKER THREAD & QUEUE
################################################################################


EXPORT_WORKER_Q = queue.Queue(1)


class ExportWorkerThread(threading.Thread):
    """Define the export worker."""

    def run(self):
        while True:
            msg = EXPORT_WORKER_Q.get()
            try:
                LOGGER.debug('ExportWorkerThread trying to call %s',
                             msg.get('func'))
                globals()[msg.get('func')](**msg.get('args'))
            except Exception as error:
                LOGGER.warning('Unable to process in worker thread: %s %s',
                               error.__class__.__name__, error)
            EXPORT_WORKER_Q.task_done()


def start_export_worker():
    """Called in ``main`` of :mod:`old.__init__.py`."""
    export_worker = ExportWorkerThread()
    export_worker.setDaemon(True)
    export_worker.start()
    export_worker2 = ExportWorkerThread()
    export_worker2.setDaemon(True)
    export_worker2.start()


# TODO: confirm that the following two functions can be deleted (and the
# transaction import)

def get_dbsession_from_settings(settings):
    engine = get_engine(settings)
    session_factory = get_session_factory(engine)
    return get_tm_session(session_factory, transaction.manager)


def get_dbsession(config_path):
    config_dir, config_file = os.path.split(config_path)
    settings = appconfig('config:{}'.format(config_file),
                         relative_to=config_dir)
    return get_dbsession_from_settings(settings)


def get_local_logger():
    local_logger = logging.getLogger(__name__)
    local_logger.addHandler(HANDLER)
    local_logger.setLevel(logging.DEBUG)
    return local_logger


def generate_export(**kwargs):
    """Create the JSON-LD export. This function controls error handling and
    export *attempt* logic. See ``_generate_export`` for actual export logic.
    """
    settings = kwargs.get('settings')
    engine = create_engine(settings['sqlalchemy.url'])
    dbsession = sessionmaker(bind=engine)()
    db = DBUtils(dbsession, settings)
    export = dbsession.query(old_models.Export).get(kwargs['export_id'])
    export.generate_succeeded = False
    try:
        _generate_export(export, settings, dbsession, db)
        export.generate_succeeded = True
        export.generate_message = 'Export successfully generated'
    except Exception as error:
        LOGGER.error('Exception when attempting to generate OLD export.')
        LOGGER.error(error, exc_info=True)
        export.generate_message = (
            'Attempt to generate export failed due to an uncaught exception.'
            ' See logs.')
    finally:
        export.generate_attempt = str(uuid4())
        export.modifier_id = kwargs['user_id']
        export.datetime_modified = h.now()
        dbsession.add(export)
        dbsession.commit()


def _generate_export(export, settings, dbsession, db):
    """Create the JSON-LD export.
    :param Model export: the Export model.
    :param dict settings: the settings of the OLD instance
    :param object dbsession: a SQLAlchemy database session object.
    :param object db: a DBUtils instance: convenience class for getting stuff
        from the db.

    Everything goes in exports/; It will look like:

    /exports/
        |- old-export-<UUID>-<timestamp>/
            |- db/
            | - OLD.jsonld
            | - Form-1.jsonld
            | - ...

    OLD.jsonld is::

        {
            "@context": {
                "OLD": "<IRI dereferences what an OLD instance is>"
            },
            "@id": "<IRI for this OLD.jsonld object>",
            "OLD": {
                "@context": {
                    "forms": "<IRI dereferences what an OLD forms
                                collection is>",
                    ...
                },
                "forms": [
                    <IRI for Form resource 1>,
                    <IRI for Form resource 2>,
                    ...
                ],
                ...
            }
        }

    Form-1.jsonld is::

        {
            "@context": {
                "Form": "<IRI dereferences what an OLD Form is>"
            },
            "@id": "<IRI for this Form-1.jsonld object>",
            "Form": {
                "@context": {
                    "transcription": "<IRI dereferences what an OLD
                                        Form.transcription is>",
                    ...
                },
                "transcription": "nitsikohtaahsi'taki",
                ...
            }
        }
    """

    # OLD schema is a dict with JSON-LD-compatible schema info. It contains
    # lots of information gleaned from introspecting the OLD's SQLAlchemy
    # models. Most importantly, it contains keys for each model name as
    # follows::
    # {
    #     'Form': {
    #         'entity_type': 'old resource',
    #         'jsonld': {
    #             'Form': {
    #                 '@context': {
    #                     'transcription': 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/transcription'
    #                 }
    #             }
    #         }
    #     }
    # }
    old_schema = get_old_schema()

    # The old_ontology FOX
    old_ontology = get_old_ontology_mapping(old_schema)

    # All the paths we will need for the export:
    exports_dir_path = _create_exports_dir(settings)
    if export.public:
        exports_type_path = _create_exports_public_dir(exports_dir_path)
    else:
        exports_type_path = _create_exports_private_dir(exports_dir_path)
    export_path = _create_export_dir(exports_type_path, export)

    # For Archivematica transfer compliance we put the data in objects/,
    # metadata in metadata/ and other stuff in logs/
    objects_path = _create_objects_dir(export_path)
    metadata_path = _create_metadata_dir(export_path)
    submdocm_path = _create_submdocm_dir(metadata_path)
    logs_path = _create_logs_dir(export_path)

    db_path = _create_db_path(objects_path)
    export_store_path = os.path.join(objects_path, 'store')
    app_set = db.current_app_set

    # Copy all of the "files" (Files, Parsers, Corpora, etc.) of this OLD
    # to the export directory.
    store_path = settings['permanent_store']
    shutil.copytree(store_path, export_store_path)

    # The IRI/URIs we will need for the "@id" values of the JSON-LD objects
    old_instance_uri = settings['uri']
    db_uri_path = db_path.replace(os.path.dirname(exports_type_path), '')
    path, leaf = os.path.split(db_uri_path)
    # db_uri_path = os.path.join(path, 'data', leaf)
    db_uri_path = '{}data/objects/db'.format(
        db_uri_path.replace('objects/db', ''))
    store_uri_path = export_store_path.replace(
        os.path.dirname(exports_type_path), '')
    path, leaf = os.path.split(store_uri_path)
    store_dirname = leaf
    # store_uri_path = os.path.join(path, 'data', leaf)
    store_uri_path = '{}data/objects/store'.format(
        db_uri_path.replace('objects/store', ''))
    if old_instance_uri.endswith('/'):
        old_instance_uri = old_instance_uri[:-1]
    # Note: the /data is required because bagit will put everything in a
    # data/ dir.
    root_iri = '{}{}'.format(old_instance_uri, db_uri_path)
    root_store_iri = '{}{}'.format(old_instance_uri, store_uri_path)

    # Add ontology/data dictionary namespaces (e.g., dc, foaf, prov)
    # the OLD schema
    # old_schema = _add_namespaces(old_schema, root_iri)

    context = _get_namespaces(root_iri)

    # Create the OLD.jsonld root export object
    old_jsonld_path = os.path.join(db_path, 'OLD.jsonld')

    old_jsonld = {
        '@context': context,
        '@id': '',
        '@type': ['dcat:Dataset', 'rdf:Bag']
    }

    # Add dcterms:language, if possible
    force_lang_id = False
    sett_file = os.path.basename(settings.get('__file__', ''))
    if sett_file == 'test.ini':
        force_lang_id = True
    obj_lang, obj_is_iso = db.get_normative_language_id(
        'object', app_set, force_lang_id)
    meta_lang, meta_is_iso = db.get_normative_language_id(
        'meta', app_set, force_lang_id)
    dcterms_language = []
    if obj_is_iso:
        dcterms_language.append({'@id': 'lexvo:{}'.format(obj_lang)})
    if meta_is_iso:
        dcterms_language.append({'@id': 'lexvo:{}'.format(meta_lang)})
    if len(dcterms_language) > 0:
        old_jsonld['dcterms:language'] = dcterms_language

    # old_jsonld['@id'] = old_jsonld_path
    # old_jsonld['@id'] = ""  # possible because @base in @context equals old_jsonld_path

    # Go through each Collection/Resource pair, adding an array of IRIs to
    # OLD.jsonld for each resource collection and creating .jsonld files
    # for each resource instance.
    coll2rsrc = {term: val['resource'] for term, val in old_schema.items()
                 if val['entity_type'] == 'old collection'}

    # Collect stats on the enterers, elicitors, modifiers, speakers for
    # dc:creator and dc:contributor attributes.
    enterers_dict = {}
    elicitors_dict = {}
    modifiers_dict = {}
    speakers_dict = {}

    # Used to collect stats on the newest and oldest resource
    # creation/modification datetimes; these values are used to populate
    # provenance values (PROV ontology)
    oldest_datetime = None
    newest_datetime = None

    # Every resource in an OLD data set is a "member" of that data set, no
    # matter what the resource's type. Member is an owl:ObjectProperty defined
    # in the custom oold ontology.
    members = []

    forms_with_files = []

    for coll, rsrc in coll2rsrc.items():

        # The language resources are not really part of the data set. They are
        # just a representation of SIL's ISO 639-3 language inventory.
        # For future reference:
        # OLD.Language = ['gold:HumanLanguageVariety', 'dbo:language']
        # OLD.Language.Id = http://dbpedia.org/ontology/iso6393Code (dbo)
        if rsrc == 'Language':
            continue

        rsrcmodel = getattr(old_models, rsrc)
        idattr = inspect(rsrcmodel).primary_key[0].name
        rsrc_id2iri = {
            idtup[0]: _get_jsonld_iri_id(root_iri, rsrc, idtup[0])
            for idtup in dbsession.query(
                rsrcmodel).with_entities(getattr(rsrcmodel, idattr)).all()}
        for id_, rsrc_iri in rsrc_id2iri.items():
            rsrc_mdl_inst = dbsession.query(rsrcmodel).get(id_)

            # rsrc_jsonld = old_schema[rsrc]['jsonld'].copy()
            # rsrc_jsonld['@id'] = rsrc_iri

            # FOX change rsrc_iri to a relative id
            resource_type = _get_resource_type(rsrc)
            rsrc_jsonld = {
                '@id': rsrc_iri,
                '@type': resource_type
            }

            # Update the dataset-wide oldest and newest datetime values, if
            # this resources is the oldest or newest one seen.
            for datetime_attr in ('datetime_entered', 'datetime_modified'):
                inst_datetime = getattr(rsrc_mdl_inst, datetime_attr, None)
                if inst_datetime:
                    if (    oldest_datetime is None or
                            inst_datetime < oldest_datetime):
                        oldest_datetime = inst_datetime
                    if (    newest_datetime is None or
                            inst_datetime > newest_datetime):
                        newest_datetime = inst_datetime

            # Insert a representation of each resource attribute into the
            # Resource's .jsonld object.
            for attr, term_def in old_schema[
                    rsrc]['jsonld'][rsrc]['@context'].items():

                # No passwords or id references in the export!
                if attr in ('password', 'salt') or attr.endswith('_id'):
                    continue

                # Skip certain reverse relations.
                if (rsrc, attr) in (
                        ('Translation', 'form'),
                        ('SyntacticCategory', 'forms'),
                        ('File', 'forms'),
                        ('File', 'collections'),
                        ('CorpusFile', 'corpus'),
                        ('Form', 'corpora'),
                        ('Tag', 'forms'),
                        ('Tag', 'files')):
                    continue

                # Not exporting a user's set of "remembered forms" (a.k.a.
                # their form "clipboard"). TODO/QUESTION: is this information
                # relevant enough to be maintained in the dataset?
                if (rsrc, attr) == ('User', 'remembered_forms'):
                    continue

                try:
                    val = getattr(rsrc_mdl_inst, attr)
                except AttributeError:
                    # Handle attributes of OLD resources that reference files
                    # as binary data, e.g., File.filename_filedata
                    if attr.endswith('_filedata'):
                        attr_ctprt = attr[:-9]
                        val = getattr(rsrc_mdl_inst, attr_ctprt, None)
                        if not val:
                            continue
                        filedata_iri = _get_filedata_iri(
                            rsrc, rsrc_mdl_inst, attr, val, store_dirname)
                        if rsrc in ('File', 'CorpusFile'):
                            filedataval = {
                                '@type': 'schema:URL',
                                '@id': filedata_iri
                            }
                            existing = rsrc_jsonld.get('schema:contentUrl')
                            if existing:
                                existing.append(filedataval)
                            else:
                                rsrc_jsonld['schema:contentUrl'] = [
                                    filedataval]
                        else:
                            rsrc_jsonld[attr] = filedata_iri
                        continue
                    else:
                        raise

                # User attributes that imply user accounts on an OLD instance
                # are treated specially.
                if rsrc == 'User' and attr in ('username', 'role'):
                    account = rsrc_jsonld.get('foaf:account')
                    if not account:
                        account = rsrc_jsonld['foaf:account'] = {
                            '@id': 'User-{}-online-linguistic-database-account'.format(
                                rsrc_mdl_inst.id),
                            '@type': 'sioc:UserAccount'
                        }
                    if attr == 'username':
                        account['sioc:name'] = val
                    elif attr == 'role':
                        account['sioc:has_function'] = 'old-role-{}'.format(val)
                    continue

                # collect potential dc:creator and dc:contributor values.
                if val and attr in ('enterer', 'elicitor', 'modifier',
                                    'speaker'):
                    aggr = locals()[attr + 's_dict']
                    record = aggr.get(val.id)
                    if record:
                        record['attribution_count'] += 1
                    else:
                        aggr[val.id] = {
                            'attribution_count': 1,
                            'name': _get_person_full_name(val)
                        }

                # TODO/QUESTION: always ignore empty string and ``None`` values?
                if val in ('', None):
                    continue

                # Elicitation Event.
                # These resource/attribute pairs entail the existence of an
                # elicitation event, which we model with the prov ontology.
                # Note that control flow continues so that these attributes can
                # be expressed as 
                ELICITATION_EVENT_ATTRS = (
                    ('Form', 'date_elicited'),
                    ('Form', 'speaker'),
                    ('Form', 'elicitor'),
                    ('Form', 'elicitation_method'),
                    ('File', 'date_elicited'),
                    ('File', 'elicitor'),
                    ('File', 'speaker')
                )
                if (rsrc, attr) in ELICITATION_EVENT_ATTRS:
                    if 'prov:Entity' not in rsrc_jsonld['@type']:
                        rsrc_jsonld['@type'].append('prov:Entity')
                    rsrc_jsonld = _add_to_elicitation_event(
                        rsrc_jsonld, rsrc, attr, val, rsrc_iri, rsrc_mdl_inst)
                    if attr == 'elicitation_method':
                        continue

                # Entry Event.
                ENTRY_EVENT_ATTRS = (
                    ('Form', 'enterer'),
                    ('Form', 'datetime_entered'),
                    ('File', 'enterer'),
                    ('File', 'datetime_entered'),
                    ('Corpus', 'enterer'),
                    ('Corpus', 'datetime_entered'),
                    ('CorpusFile', 'creator'),
                    ('CorpusFile', 'datetime_created'),
                    ('Export', 'enterer'),
                    ('Export', 'datetime_entered')
                )
                if (rsrc, attr) in ENTRY_EVENT_ATTRS:
                    if 'prov:Entity' not in rsrc_jsonld['@type']:
                        rsrc_jsonld['@type'].append('prov:Entity')
                    rsrc_jsonld = _add_to_entry_event(
                        rsrc_jsonld, rsrc, attr, val, rsrc_iri, rsrc_mdl_inst)

                # Modification Event.
                MODIFICATION_EVENT_ATTRS = (
                    ('Form', 'datetime_modified'),
                    ('Form', 'modifier'),
                    ('File', 'datetime_modified'),
                    ('Corpus', 'datetime_modified'),
                    ('Corpus', 'modifier'),
                    ('CorpusFile', 'modifier'),
                    ('CorpusFile', 'datetime_modified'),
                    ('Export', 'datetime_modified')
                )
                if (rsrc, attr) in MODIFICATION_EVENT_ATTRS:
                    if 'prov:Entity' not in rsrc_jsonld['@type']:
                        rsrc_jsonld['@type'].append('prov:Entity')
                    rsrc_jsonld = _add_to_modification_event(
                        rsrc_jsonld, rsrc, attr, val, rsrc_iri, rsrc_mdl_inst)

                # Form.speaker_comments is a dc:description that
                # prov:wasAttributedTo a speaker.
                if (rsrc, attr) == ('Form', 'speaker_comments'):
                    speaker = getattr(rsrc_mdl_inst, 'speaker', None)
                    if speaker:
                        speaker = {'@id': 'Speaker-{}'.format(speaker.id)}
                    else:
                        # Anonymous speaker
                        speaker = {
                            '@id': 'Form-{}-speaker-comments-speaker'.format(
                                rsrc_mdl_inst.id),
                            '@type': ["prov:Person", "dcterms:Agent"]
                        }
                    existing_description = rsrc_jsonld.get('dc:description')
                    description = {
                        '@type': 'prov:Entity',
                        '@id': 'Form-{}-speaker_comments'.format(rsrc_mdl_inst.id),
                        'prov:wasAttributedTo': speaker,
                        'prov:value': val
                    }
                    if existing_description:
                        if isinstance(existing_description, list):
                            existing_description.append(description)
                        else:
                            rsrc_jsonld['dc:description'] = [
                                existing_description, description]
                    else:
                        rsrc_jsonld['dc:description'] = description
                    continue

                # OLD Tags are treated using the muto ontology:
                # OLD.Resource muto:taggedWith muto:Tagging .
                # muto.Tagging muto:hasTag tag-id .
                elif attr == 'tags':
                    if len(val) == 0:
                        continue
                    # resource muto:taggedWith muto:Tagging
                    # muto:Tagging muto:hasTag muto:Tag
                    tw = rsrc_jsonld.get('muto:taggedWith')
                    if not tw:
                        tw = rsrc_jsonld['muto:taggedWith'] = []
                    for index, tag in enumerate(val):
                        tw.append({
                            '@type': 'muto:Tagging',
                            '@id': '{}-{}-tagging-{}'.format(
                                rsrc, rsrc_mdl_inst.id, index + 1),
                            'muto:hasTag': {'@id': 'Tag-{}'.format(tag.id)}
                        })
                    continue

                # The references to other form in the ``morpheme_..._ids``
                # attributes are treated using gold:hasMorphologicalConstituent
                # Note: the current algorithm currently lists only the first
                # referenced morpheme in the set of matching morphemes as a
                # GOLD morphological constituent. This presumes that the best
                # match is listed first, which may be a faulty assumption. Note
                # also that we are not asserting any ordering relation between
                # the morphological constituents of a given form, although GOLD
                # does allow it.
                elif attr in ('morpheme_gloss_ids', 'morpheme_break_ids'):
                    this_id = rsrc_jsonld['@id']
                    constituents = rsrc_jsonld.get(
                        'gold:hasMorphologicalConstituent')
                    if not constituents:
                        constituents = \
                            rsrc_jsonld['gold:hasMorphologicalConstituent'] = []
                    try:
                        val = json.loads(val)
                    except ValueError:
                        continue
                    for wordref in val:
                        for morphsetref in wordref:
                            if len(morphsetref) > 0:
                                ref = morphsetref[0]
                                if len(ref) > 0:
                                    ref = {'@id': 'Form-{}'.format(ref[0])}
                                    if ref['@id'] != this_id and ref not in constituents:
                                        constituents.append(ref)
                    if len(constituents) == 0:
                        del rsrc_jsonld['gold:hasMorphologicalConstituent']
                    continue

                # Corpus.forms is treated specially as a JSON array of
                # references to forms in gold:hasConstituent
                elif (rsrc, attr) == ('Corpus', 'forms'):
                    # The existence of a search reference trumps any form
                    # references in content and the constituent forms are not
                    # ordered.
                    forms = rsrc_mdl_inst.forms
                    if len(forms) == 0:
                        continue
                    constituents = rsrc_jsonld.get('gold:hasConstituent')
                    if not constituents:
                        constituents = \
                            rsrc_jsonld['gold:hasConstituent'] = []
                    if rsrc_mdl_inst.form_search:
                        for form_mdl in rsrc_mdl_inst.forms:
                            constituents.append(
                                {'@id': 'Form-{}'.format(form_mdl.id)})
                        if len(constituents) == 0:
                            del rsrc_jsonld['gold:hasConstituent']
                    else:
                        rsrc_jsonld['@type'].append('rdf:List')
                        refs = list(old_models.Corpus.get_form_references(
                            rsrc_mdl_inst.content))
                        last_index = len(refs) - 1
                        rdf_list = rsrc_jsonld
                        for index, form_id in enumerate(refs):
                            form_rsrc = {'@id': 'Form-{}'.format(form_id)}
                            constituents.append(form_rsrc)
                            rdf_list['rdf:first'] = form_rsrc
                            if index == last_index:
                                rdf_list['rdf:rest'] = 'rdf:nil'
                            else:
                                next_list = {'@type': 'rdf:List'}
                                rdf_list['rdf:rest'] = next_list
                                rdf_list = next_list
                        if len(constituents) == 0:
                            del rsrc_jsonld['gold:hasConstituent']
                    continue

                # Speakers/Users and their html attributes are treated as
                # foaf:homepage referencing foaf:Document (which is equivalent
                # to schema.org:CreativeWork).
                elif (rsrc, attr) in (
                            ('Speaker', 'html'),
                            ('User', 'html'),
                            ('Speaker', 'page_content'),
                            ('User', 'page_content'),
                            ('Speaker', 'markup_language'),
                            ('User', 'markup_language')
                        ):
                    if attr in ('page_content', 'markup_language'):
                        continue
                    html_doc = {
                        '@id': '{}-{}-html'.format(rsrc, rsrc_mdl_inst.id),
                        '@type': 'foaf:Document',
                        'schema:fileFormat': {'@id': 'iana:text/html'},
                        'schema:text': val
                    }
                    page_content = getattr(rsrc_mdl_inst, 'page_content', None)
                    markup_lang = getattr(rsrc_mdl_inst, 'markup_language',
                                          None)
                    if page_content and markup_lang:
                        if markup_lang == 'Markdown':
                            markup_url = {'@id': 'iana:text/markdown'}
                        else:
                            markup_url = {'@id': (
                                'http://docutils.sourceforge.net/docs/ref/rst/'
                                'restructuredtext.html')}
                        # TODO: schema:isBasedOn does not seem to correctly
                        # describe the relationship between a RST/Markdown
                        # document source and its HTML realization...
                        html_doc['schema:isBasedOn'] = {
                            '@id': '{}-{}-source'.format(
                                rsrc, rsrc_mdl_inst.id),
                            '@type': 'foaf:Document',
                            'schema:fileFormat': markup_url,
                            'schema:text': page_content
                        }
                    rsrc_jsonld['foaf:homepage'] = html_doc
                    continue

                # Any forms with A/V files associated to them are saved for
                # later so that we make sure to describe the association after
                # all other attributes have been described.
                if (rsrc, attr) == ('Form', 'files'):
                    if len(val) > 0:
                        forms_with_files.append((rsrc_mdl_inst.id, rsrc_jsonld))
                    continue

                # Audio/Video files are assumed to be of type
                # gold:SpokenLinguisticExpression
                if (rsrc, attr) == ('File', 'utterance_type'):
                    if (    (rsrc_mdl_inst.MIME_type.startswith('video') or
                             rsrc_mdl_inst.MIME_type.startswith('audio')) and
                            val in ('Mixed Utterance',
                                    'Object Language Utterance',
                                    'Metalanguage Utterance')):
                        rsrc_jsonld['@type'].append(
                            'gold:SpokenLinguisticExpression')

                # Each Corpus model bears the schema:associatedMedia relation
                # to all of its CorpusFile models.
                if (rsrc, attr) == ('Corpus', 'files'):
                    cfs = []
                    if len(val) > 0:
                        for cf in val:
                            cfs.append({'@id': 'CorpusFile-{}'.format(cf.id)})
                    rsrc_jsonld['schema:associatedMedia'] = cfs
                    continue

                # Source.type changes the bibtex: class from bibtex:Entry to
                # bibtex:<Type>
                if (rsrc, attr) in (
                        ('Source', 'type'),
                        ('Source', 'file'),
                        ('Source', 'crossref_source')):
                    if attr == 'type':
                        rsrc_jsonld['@type'].append(
                            'bibtex:{}'.format(val.capitalize()))
                    elif attr == 'file':
                        rsrc_jsonld['schema:associatedMedia'] = {
                            '@id': 'File-{}'.format(val.id)}
                    elif attr == 'crossref_source':
                        rsrc_jsonld['schema:isBasedOn'] = {
                            '@id': 'Source-{}'.format(val.id)}
                    continue

                # Form.translations is a bunch of gold:hasTranslationLine
                # triples
                if (rsrc, attr) == ('Form', 'translations'):
                    rsrc_jsonld['gold:hasTranslationLine'] = [
                        {'@id': 'Translation-{}'.format(tr.id)} for tr in val]
                    continue

                # The "standard" case
                else:
                    rsrc_jsonld = _standard_rsrc_attr(
                        rsrc_jsonld, rsrc, attr, val, rsrc_iri, rsrc_mdl_inst)

            rsrc_jsonld_path = os.path.join(
                db_path, rsrc_iri.split('/')[-1])

            # Attempt to remove duplicates.
            # TODO: some bug (near this code) is causing speaker_comments to
            # disappear on every second resource generation
            for attr, val in rsrc_jsonld.items():
                if isinstance(val, list):
                    allstrings = True
                    for it in val:
                        if not isinstance(it, str):
                            all_strings = False
                    if not allstrings:
                        continue
                    try:
                        newval = list(set(val))
                        rsrc_jsonld[attr] = newval
                    except TypeError:
                        pass

                    """
                    try:
                        rsrc_jsonld[attr] = list(set(val))
                    except TypeError:
                        try:
                            rsrc_jsonld[attr] = [
                                dict(y) if isinstance(y, tuple) else y
                                for y in
                                set([tuple(sorted(x.items()))
                                    if isinstance(x, dict) else x
                                    for x in val])]
                        except TypeError:
                            pass
                    """

            # Add the JSON-LD object representing an OLD resource to the list
            # of members
            members.append(rsrc_jsonld)

    # Associate audio/video files tagged as "mixed utterance" or "object
    # language utterance" as gold:acousticRealization of the Form qua
    # gold:LinguisticUnit and associate such files tagged as "mixed utterance"
    # or "metalanguage utterance" as gold:acousticRealization of the Form's
    # sole translation (if there is one).
    # Note: the OLD's "metalanguage utterance" underspecifies because it is
    # unclear which translation (if there are multiple) the file is an acoustic
    # realization of.
    for form_id, rsrc_jsonld in forms_with_files:
        form_mdl = dbsession.query(old_models.Form).get(form_id)
        acoustic_rlztns = []
        transl_acoustic_rlztns = []
        features = []
        for file_mdl in form_mdl.files:
            features.append({'@id': 'File-{}'.format(file_mdl.id)})
            if (    file_mdl.MIME_type.startswith('audio') or
                    file_mdl.MIME_type.startswith('video')):
                if file_mdl.utterance_type == 'Mixed Utterance':
                    acoustic_rlztns.append(
                        {'@id': 'File-{}'.format(file_mdl.id)})
                    if len(form_mdl.translations) == 1:
                        transl_acoustic_rlztns.append(
                            {'@id': 'File-{}'.format(file_mdl.id)})
                elif file_mdl.utterance_type == 'Object Language Utterance':
                    acoustic_rlztns.append(
                        {'@id': 'File-{}'.format(file_mdl.id)})
                elif file_mdl.utterance_type == 'Metalanguage Utterance':
                    if len(form_mdl.translations) == 1:
                        transl_acoustic_rlztns.append(
                            {'@id': 'File-{}'.format(file_mdl.id)})
        if len(acoustic_rlztns) > 0:
            rsrc_jsonld['gold:acousticRealization'] = acoustic_rlztns
        if len(transl_acoustic_rlztns) > 0:
            transl_id = form_mdl.translations[0].id
            transl_jsonld = [
                x for x in members
                if x['@id'] == 'Translation-{}'.format(transl_id)][0]
            transl_jsonld['gold:acousticRealization'] = transl_acoustic_rlztns
        if len(features) > 0:
            feature = rsrc_jsonld.get('gold:feature')
            if not feature:
                feature = rsrc_jsonld['gold:feature'] = []
            feature.extend(features)

    # Dublin Core contributor computed as all speakers and
    # elicitors/enterers/modifiers, in that order, secondarily ordered by
    # weighted resource attribution count.
    dc_contributors = _get_dc_contributors(enterers_dict, elicitors_dict,
                                           modifiers_dict, speakers_dict)
    dc_creators = _get_dc_creators(speakers_dict, elicitors_dict)
    # Add dc:contributors and dc:creators to the export model as JSON arrays
    export.dc_contributor = json.dumps(dc_contributors)
    export.dc_creator = json.dumps(dc_creators)

    old_jsonld['rdfs:member'] = members

    # Put dc:contributors and dc:creators into OLD.jsonld
    old_jsonld['dc:creator'] = dc_creators
    old_jsonld['dc:contributor'] = dc_contributors

    # removed dcterms:bibliographicCitation until that term set is used...
    # TODO: it should be used (or something like it) because
    # ``_get_dc_bib_cit`` returns a useful string.
    # if not export.dc_bibliographic_citation:
    #     # TODO: is ``old_jsonld['@id']`` the actual URI of the data set? It
    #     # needs to be ...
    #     export.dc_bibliographic_citation = _get_dc_bib_cit(
    #         dc_creators, export, old_jsonld['@id'])
    # old_jsonld['dc:bibliographicCitation'] = (
    #     export.dc_bibliographic_citation)

    # Provenance metadata (PROV ontology)
    now = h.now()
    if oldest_datetime is None:
        oldest_datetime = now
    if newest_datetime is None:
        newest_datetime = now
    old_jsonld = _add_provenance_md(old_jsonld, export, oldest_datetime,
                                    newest_datetime, old_instance_uri, app_set)

    # dc:date http://purl.org/dc/elements/1.1/date
    if not export.dc_date:
        if oldest_datetime == newest_datetime:
            export.dc_date = h.utc_datetime2xsd(newest_datetime)
        else:
            export.dc_date = 'Between {} and {}.'.format(
                h.utc_datetime2xsd(oldest_datetime),
                h.utc_datetime2xsd(newest_datetime))
    old_jsonld['dc:date'] = export.dc_date

    # Add the remaining dc: term values to the OLD export object.
    for dc_term in ('publisher', 'description', 'format', 'identifier',
                    'relation', 'coverage', 'rights', 'type', 'title'):
        val = getattr(export, 'dc_{}'.format(dc_term), None)
        if val:
            old_jsonld['dc:{}'.format(dc_term)] = val

    # dc_language and dc_subject may be a user-supplied strings or
    # auto-generated lists of strings (e.g., ISO 639-3 language Id values for
    # dc_language).
    for dc_term in ('language', 'subject'):
        val = getattr(export, 'dc_{}'.format(dc_term), None)
        if val:
            try:
                val_loaded = json.loads(val)
            except ValueError:
                pass
            if isinstance(val_loaded, list):
                old_jsonld['dc:{}'.format(dc_term)] = val_loaded
            else:
                old_jsonld['dc:{}'.format(dc_term)] = val

    # Write the OLD.jsonld to disk in the exports/ subdir
    with open(old_jsonld_path, 'w') as fileo:
        fileo.write(
            json.dumps(
                old_jsonld,
                sort_keys=True,
                indent=4,
                separators=(',', ': ')))

    # Use rdflib to save the same data set to various other formats:
    # - Turtle (.ttl): human-readable
    # - RDF/XML (.rdf): classic
    # - N-Triples (.nt): large data easily buffered
    # TODO: this should maybe be user-configurable; generating these
    # serializations may be computationally expensive if the data set is large.
    base_path, _ = os.path.splitext(old_jsonld_path)
    turtle_path = '{}.ttl'.format(base_path)
    rdf_xml_path = '{}.rdf'.format(base_path)
    n_triples_path = '{}.nt'.format(base_path)
    graph = Graph().parse(source=old_jsonld_path, format='json-ld')
    with open(turtle_path, 'w') as fileo:
        fileo.write(graph.serialize(format='turtle').decode('utf8'))
    with open(n_triples_path, 'w') as fileo:
        fileo.write(graph.serialize(format='nt').decode('utf8'))
    with open(rdf_xml_path, 'w') as fileo:
        fileo.write(graph.serialize(format='xml').decode('utf8'))

    # Add Dublin Core metadata to metadata/metadata.csv
    metadata_csv_path = os.path.join(metadata_path, 'metadata.csv')
    with open(metadata_csv_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        metadata_attrs = [
            'filename',
            'dc_contributor',
            'dc_creator',
            'dc_publisher',
            'dc_date',
            'dc_description',
            'dc_format',
            'dc_identifier',
            'dc_language',
            'dc_relation',
            'dc_coverage',
            'dc_rights',
            'dc_subject',
            'dc_title',
            'dc_type',
        ]
        writer.writerow([x.replace('_', '.') for x in metadata_attrs])
        vals = ['objects']
        for attr in metadata_attrs[1:]:
            val = getattr(export, attr, '')
            try:
                vallist = json.loads(val)
            except ValueError:
                vallist = None
            if vallist and isinstance(vallist, list):
                vals.append(', '.join(vallist))
            else:
                vals.append(val)
        writer.writerow(vals)

    # BagIt! Add the export model's BagIt-specific metadata elements, if they
    # are populated
    bag_params = {}
    for attr in ('source_organization', 'organization_address', 'contact_name',
                 'contact_phone', 'contact_email'):
        val = getattr(export, attr, None)
        if val:
            key = '-'.join([x.capitalize() for x in attr.split('_')])
            bag_params[key] = val
    bagit.make_bag(export_path, bag_params)

    # ZipIt!
    shutil.make_archive(export_path, 'zip', export_path)


def _add_provenance_md(old_jsonld, export, oldest_datetime, newest_datetime,
                       old_instance_uri, app_set):
    """Add dataset provenance information using PROV ontology: "This export was
    created by an activity of export creation, which started at datetime X and
    ended at datetime Y, and which used a software agent, i.e., a specific OLD
    instance.
    """
    old_jsonld['@type'].append('prov:Entity')
    dataset_creation_activity = {'@id': 'dataset-creation-activity'}
    old_jsonld['prov:wasGeneratedBy'] = dataset_creation_activity
    dataset_creation_activity['@type'] = 'prov:Activity'
    dataset_creation_activity['prov:generated'] = old_jsonld['@id']
    dataset_creation_activity['prov:startedAtTime'] = {
        "@value": h.utc_datetime2xsd(oldest_datetime),
        "@type": "xsd:dateTime"
    }
    dataset_creation_activity['prov:endedAtTime'] = {
        "@value": h.utc_datetime2xsd(newest_datetime),
        "@type": "xsd:dateTime"
    }
    old_instance_foaf_name = h.get_old_instance_descriptive_name(
        app_set, old_instance_uri, __version__)
    old_instance_id = 'old-application-instance'
    old_instance = {
        '@id': old_instance_id,
        '@type': ['prov:SoftwareAgent', 'sioc:Site'],
        # Use 'doap:name' ?
        'foaf:name': old_instance_foaf_name,
        'sioc:scope_of': [
            {
                '@id': 'old-role-administrator',
                '@type': 'sioc:Role',
                'sioc:name': 'administrator',
                'foaf:name': 'administrator'
            },
            {
                '@id': 'old-role-contributor',
                '@type': 'sioc:Role',
                'sioc:name': 'contributor',
                'foaf:name': 'contributor'
            },
            {
                '@id': 'old-role-viewer',
                '@type': 'sioc:role',
                'sioc:name': 'viewer',
                'foaf:name': 'viewer'
            }
        ]
    }
    dataset_creation_activity['prov:used'] = old_instance
    return old_jsonld


def _get_dc_creators(speakers, elicitors):
    """Return a list of Dublin Core creators as strings (first name, last
    name). These are creators of the data set qua export. Speakers are
    listed first, then elicitors. Both are sorted by their attribution count,
    from greatest to least.
    """
    # Get a list of speaker names, sorted by number of speaker attributions from
    # greatest to least.
    speakers_list = sorted(speakers.keys(),
                           key=lambda id_: speakers[id_]['attribution_count'],
                           reverse=True)
    speakers_list = [speakers[id_]['name'] for id_ in speakers_list]
    # Get a list of elicitor names, sorted by number of elicitor attributions
    # from greatest to least.
    elicitors_list = sorted(elicitors.keys(),
                            key=lambda id_: elicitors[id_]['attribution_count'],
                            reverse=True)
    elicitors_list = [elicitors[id_]['name'] for id_ in elicitors_list]
    return speakers_list + elicitors_list


def _get_dc_bib_cit(dc_creators, export, dataset_uri):
    """Return a bibliographic citation for the export. Something like
    "Robertson Bob, et al. 2017. Data Set of Linguistic Data on Language
    Blackfoot (bla) (created by the Online Linguistic Database).
    http://app.onlinelinguisticdatabase.org/blaold/exports/public/old-export-8641d84d-a4bd-4f16-8bbc-342a36e34edb-1487807629/OLD.jsonld".
    """
    author = _get_author_from_creators_list(dc_creators)
    return '{}. {}. {}. {}.'.format(author, h.now().year, export.dc_title,
                                    dataset_uri)


def _get_author_from_creators_list(creators_list):
    """Given a list of data set creators (like ``['Bob Robertson', 'Jane
    Jackowski']``), return a string suitable for a citation, e.g.,
    ``'Robertson, Bob, and Jane Jackowski'``.
    WARNING: this is very naive about name formats and will fail with multiple
    first names, multiple last names, titles, etc.
    """
    if len(creators_list) == 0:
        return ''
    elif len(creators_list) == 1:
        first_name, last_name = creators_list[0].split()
        return '{}, {}'.format(last_name, first_name)
    elif len(creators_list) == 2:
        first_author, second_author = creators_list
        first_name, last_name = first_author.split()
        first_author = '{}, {}'.format(last_name, first_name)
        return '{}, and {}'.format(first_author, second_author)
    else:
        first_name, last_name = creators_list[0].split()
        return '{}, {}, et al'.format(last_name, first_name)


def _get_dc_contributors(enterers, elicitors, modifiers, speakers):
    """Return a list of Dublin Core contributors as strings (first name, last
    name). These are contributors to the data set qua export.  Speakers are
    listed first, then elicitor/enterer/modifier users using a weighted sorting
    approach where each elicitor attribution is worth 2 points and each
    enterer/modifier attribution is worth 1.
    """
    # Get a list of speaker ids, sorted by number of speaker attributions from
    # greatest to least.
    speakers_list = sorted(speakers.keys(),
                           key=lambda id_: speakers[id_]['attribution_count'],
                           reverse=True)
    speakers_list = [speakers[id_]['name'] for id_ in speakers_list]
    # Each elicitor attribution is worth two points:
    users = {}
    for id_, info in elicitors.items():
        score = info['attribution_count'] * 2
        users[id_] = {'score': score, 'name': info['name']}
    # Each enterer/modifier attribution is worth one point:
    for user_dict in (enterers, modifiers):
        for id_, info in user_dict.items():
            existing_user_info = users.get(id_)
            if existing_user_info:
                existing_user_info['score'] += info['attribution_count']
            else:
                users[id_] = {
                    'score': info['attribution_count'],
                    'name': info['name']
                }
    users_list = sorted(users.keys(),
                        key=lambda id_: users[id_]['score'],
                        reverse=True)
    users_list = [users[id_]['name'] for id_ in users_list]
    return speakers_list + users_list


def _get_filedata_iri(rsrc_name, rsrc, attr, val, store_dirname):
    """Return the IRI for a ``_filedata`` "attribute" of an OLD resource.
    For example, File resources with filename attributes should have a
    filename_filedata pseudo-attribute in the JSON-LD export which is an
    IRI that locates the binary data of the File. This method returns that
    IRI. For development, the structure of the store/ directories is:

        - corpora
        - files
            - reduced_files
        - morpheme_language_models
        - morphological_parsers
        - morphologies
        - phonologies
        - users
            - <username>
    """
    dirname = inflect_p.plural(h.camel_case2snake_case(rsrc_name))
    if dirname == 'files':
        if attr == 'lossy_filename_filedata':
            dirname = os.path.join(dirname, 'reduced_files')
    if dirname == 'corpus_files':
        subdirname = 'corpus_%s' % rsrc.id
        dirname = os.path.join('corpora', subdirname)
    return os.path.join('..', store_dirname, dirname, val)


def _get_rsrc_attr_val_jsonld_repr(val):
    """Return a JSON-LD representation of ``val``, which is the value of an OLD
    resource attribute. If ``val` is another OLD resource, we return the IRI
    to its own JSON-LD object.
    """
    if isinstance(val, list):
        return True, [_get_rsrc_attr_val_jsonld_repr(x) for x in val]
    elif val is None:
        return False, val
    elif isinstance(val, old_models.Model):
        attr_rsrc = val.__class__.__name__
        attr_idattr = inspect(val.__class__).primary_key[0].name
        id_ = getattr(val, attr_idattr)
        # return _get_jsonld_iri_id(root_iri, attr_rsrc, id_)
        return True, '{}-{}'.format(attr_rsrc, id_)
    elif isinstance(val, datetime.datetime):
        return False, h.utc_datetime2xsd(val)
    elif isinstance(val, datetime.date):
        return False, val.isoformat()
    else:
        return False, val


def _get_jsonld_iri_id(base_path, resource_name, resource_id):
    """Return a JSON-LD IRI ("@id" value) for an OLD resource of type
    ``resource_name`` with id ``resource_id`` being served at the base path
    ``base_path``.
    return os.path.join(
        base_path,
        '{}-{}.jsonld'.format(resource_name, resource_id))
    """
    return '{}-{}'.format(resource_name, resource_id)


def _create_dir(path):
    if not os.path.isdir(path):
        h.make_directory_safely(path)


def _create_exports_dir(settings):
    exports_dir_path = settings['exports_dir']
    _create_dir(exports_dir_path)
    return exports_dir_path


def _create_exports_public_dir(exports_dir_path):
    public_path = os.path.join(exports_dir_path, 'public')
    _create_dir(public_path)
    return public_path


def _create_exports_private_dir(exports_dir_path):
    private_path = os.path.join(exports_dir_path, 'private')
    _create_dir(private_path)
    return private_path


def _create_export_dir(exports_type_path, export):
    export_path = os.path.join(exports_type_path, export.dc_identifier)
    _create_dir(export_path)
    return export_path


def _create_db_path(export_path):
    db_path = os.path.join(export_path, 'db')
    _create_dir(db_path)
    return db_path


def _create_objects_dir(export_path):
    objects_path = os.path.join(export_path, 'objects')
    _create_dir(objects_path)
    return objects_path


def _create_metadata_dir(export_path):
    metadata_path = os.path.join(export_path, 'metadata')
    _create_dir(metadata_path)
    return metadata_path


def _create_submdocm_dir(metadata_path):
    submdocm_path = os.path.join(metadata_path, 'submissionDocumentation')
    _create_dir(submdocm_path)
    return submdocm_path


def _create_logs_dir(export_path):
    logs_path = os.path.join(export_path, 'logs')
    _create_dir(logs_path)
    return logs_path


def _create_store_path(export_path):
    store_path = os.path.join(export_path, 'store')
    _create_dir(store_path)
    return store_path


def _get_person_full_name(person_model):
    """Given a User or Speaker model, return their full name, e.g., 'Jane
    Doe'.
    """
    return '%s %s' % (person_model.first_name, person_model.last_name)


def _get_namespaces(root_iri):
    """References (links) relevant to the namespaces/ontologies used:

    asit: http://ims.dei.unipd.it/websites/ASIt/RDF/doc/#
    dbo: http://dbpedia.org/ontology/
    dc: http://purl.org/dc/elements/1.1/
    dcat: http://www.w3.org/ns/dcat#
    dcterms: http://purl.org/dc/terms/
    ebucore: http://www.ebu.ch/metadata/ontologies/ebucore/ebucore#
    foaf: http://xmlns.com/foaf/0.1/
    gold: http://purl.org/linguistics/gold/
    iana: http://www.iana.org/assignments/media-types/
    lime: http://art.uniroma2.it/ontologies/lime#
          http://www.essepuntato.it/lode/owlapi/reasoner/http://art.uniroma2.it/ontologies/lime#LinguisticResource
    muto: http://purl.org/muto/core#
          http://muto.socialtagging.org/core/v1.html#
    org: http://www.w3.org/ns/org#
    pcdm: http://pcdm.org/models#
          https://github.com/duraspace/pcdm/wiki
    prov: http://www.w3.org/ns/prov#
          https://www.w3.org/TR/prov-o/
    schema: http://schema.org/
    sioc: http://rdfs.org/sioc/ns#
          http://rdfs.org/sioc/spec/
    skos: http://www.w3.org/2004/02/skos/core#
    xsd: http://www.w3.org/2001/XMLSchema

    Other useful links:

    - http://usefulinc.com/ns/doap
    - https://wiki.archivematica.org/RDF/OWL

    """
    if root_iri[-1] != '/':
        root_iri = root_iri + '/'
    return {
        '@base': root_iri,
        'bibtex': 'http://purl.oclc.org/NET/nknouf/ns/bibtex#',
        'asit': 'http://ims.dei.unipd.it/websites/ASIt/RDF/doc/#',
        'dbo': 'http://dbpedia.org/ontology/',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'dcat': 'http://www.w3.org/ns/dcat#',
        'dcterms': 'http://purl.org/dc/terms/',
        'ebucore': 'http://www.ebu.ch/metadata/ontologies/ebucore/ebucore#',
        'foaf': 'http://xmlns.com/foaf/0.1/',
        'gold': 'http://purl.org/linguistics/gold/',
        'iana': 'http://www.iana.org/assignments/media-types/',
        'lexvo': 'http://www.lexvo.org/page/iso639-3/',
        'lime': 'http://art.uniroma2.it/ontologies/lime#',
        'muto': 'http://purl.org/muto/core#',
        'oold': OOLD_URL,
        'org': 'http://www.w3.org/ns/org#',
        'pcdm': 'http://pcdm.org/models#',
        'prov': 'http://www.w3.org/ns/prov#',
        'schema': 'http://schema.org/',
        'sioc': 'http://rdfs.org/sioc/ns#',
        'skos': 'http://www.w3.org/2004/02/skos/core#',
        'xsd': 'http://www.w3.org/2001/XMLSchema#'
    }


# The following is a draft of how the OLD JSON-LD export ought to look.
# Development in the future can run the test script and compare it to this.
TEST_EXPORT = {
    "@context": {
        #"OLD": "http://schema.onlinelinguisticdatabase.org/2.0.0/OLD",
        "dc": "http://purl.org/dc/terms/",
        #"export": "https://app.onlinelinguisticdatabase.org/testold/public/old-export-064bf372-598f-4007-9d96-487f9db96f06-1487675109/data/db#",
        "@base": "https://app.onlinelinguisticdatabase.org/testold/public/old-export-064bf372-598f-4007-9d96-487f9db96f06-1487675109/data/db/OLD.jsonld",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "dcat": "https://www.w3.org/TR/vocab-dcat/",
        "prov": "http://www.w3.org/ns/prov#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "lime": "http://art.uniroma2.it/ontologies/lime#"
    },
    "@id": "",
    "@type": [
        "dcat:DataSet",
        "prov:Entity",
        "lime:LinguisticResource"
    ],
    "dc:contributor": [
        "Speaker Mcspeakerson",
        "Contributor Contributor",
        "Admin Admin"
    ],
    "dc:creator": [
        "Speaker Mcspeakerson",
        "Contributor Contributor"
    ],
    "dc:title": "old-export-064bf372-598f-4007-9d96-487f9db96f06-1487675109",
    "prov:wasGeneratedBy": {
        "@id": "dataset-creation-activity",
        "@type": "prov:Activity",
        "prov:endedAtTime": {
            "@type": "xsd:dateTime",
            "@value": "2013-01-25T00:00:00Z"
        },
        "prov:generated": "export.OLD.jsonld",
        "prov:startedAtTime": {
            "@type": "xsd:dateTime",
            "@value": "2011-01-25T00:00:00Z"
        },
        "prov:used": {
            "@id": "old-application-instance",
            "@type": "prov:SoftwareAgent",
            "foaf:name": "Blackfoot OLD instance running OLD v1.2.1 at app.onlinelinguisticdatabase.org/blaold/"
        }
    }
}

OOLD_DEV_DELETE = {
    "@context": {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "@base": OOLD_URL,
        "defines": {
            "@reverse": "rdfs:isDefinedBy"
        },
        "propertyOf": { 
            "@id": "rdfs:domain",
            "@type": "@id"
        },
        "propertyOn": { 
            "@id": "rdfs:range",
            "@type": "@id"
        }
    },
    "@id": "",
    "@type": "owl:Ontology",
    "defines": [
        {
            "@id": "member",
            "@type": "owl:ObjectProperty",
            "rdfs:label": "member",
            "rdfs:comment": (
                "Expresses that the owl:Thing in the domain contains the"
                " owl:Thing in the range as a member."),
            "rdfs:domain": "owl:Thing",
            "rdfs:range": "owl:Thing"
        }
    ]
}


OLD_ONTO_MAPPING = {

    'formTranscription': [

        # domain: gold:LinguisticUnit
        # range:  gold:WrittenLinguisticExpression
        'gold:writtenRealization',

        # type: owl:ObjectProperty
        # domain: gold:LinguisticDataStructure
        # ObjectProperty. The binary relation holding between an instance
        # of interlinear glossed text and a linguistic unit (clause, phrase,
        # etc.) from the source language.
        'gold:hasSourceLine'
    ],

    'FormTranscription': 'gold:WrittenLinguisticExpression',

    'formMorphemeBreak': [
        'gold:writtenRealization',
        'gold:hasSourceLine'
    ],

    'formMorphemeGloss': [

        # type: owl:ObjectProperty
        # domain: gold:LinguisticDataStructure
        # The binary relation holding between an instance of interlinear glossed
        # text (IGT) and a sequence of labels or 'grams' used to describe the
        # morphemes of the IGT.
        'gold:hasGlosses',

        # type: owl:ObjectProperty.
        # The relation between an orthographic expression in one language and
        # some orthographic expression in another such that the translation is
        # done on a word by word, or morpheme by morpheme, basis without regard
        # for idiomatic usage.
        'gold:literalTranslation'
    ],

    # type:   owl:ObjectProperty
    # domain: gold:LinguisticDataStructure
    # The binary relation holding between an instance of interlinear glossed
    # text and a linguistic unit (clause, phrase, etc.) acting as a free
    # translation of the source text from the IGT instance.
    'formTranslations': 'gold:hasTranslationLine',

    'FormTranslations': 'gold:LinguisticUnit',


    # type: owl:ObjectProperty.
    # The relation between an orthographic expression in one language and some
    # orthographic expression in another such that both expressions have exactly
    # the same meaning. The words in the translation may not correspond to the
    # those in the source expression.
    '???': 'gold:freeTranslation'


}


def get_old_ontology_mapping(old_schema):
    """Return a dict that maps:
    a. resource names, e.g., "Form",
    b. resource name / attribute name pairs, e.g., "Form-transcription", and
    c. (a)-to-(b) mappings, e.g., "Form-Form-transcription"
    to OWL Classes URIs (for a-b) and OWL ObjectProperty URIs in some defined
    ontology.
    """
    # OLD schema is a dict with JSON-LD-compatible schema info. It contains
    # lots of information gleaned from introspecting the OLD's SQLAlchemy
    # models. Most importantly, it contains keys for each model name as
    # follows::
    # {
    #     'Form': {
    #         'entity_type': 'old resource',
    #         'jsonld': {
    #             'Form': {
    #                 '@context': {
    #                     'transcription': 'http://schema.onlinelinguisticdatabase.org/2.0.0/Form/transcription'
    #                 }
    #             }
    #         }
    #     }
    pass
    """
    for resource_name, obj in old_schema:
        if obj['entity_type'] != 'old resource':
            continue
        for resource_attr in obj['jsonld'][resource_name]['@context']:
    """


def _get_resource_type(resource_name):
    """Return an rdfs:type (or list thereof) for the resource with name
    ``resource_name``.
    """
    if resource_name == 'Form':
        return [
            'gold:LinguisticUnit',
            'gold:InterlinearGlossedText', # subClassOf: gold:LinguisticDataStructure
            'prov:Entity'
        ]
    elif resource_name == 'Source':
        return ['bibtex:Entry']
    elif resource_name == 'Corpus':
        return ['gold:DiscourseUnit', 'schema:CreativeWork']
    elif resource_name == 'CorpusFile':
        return ['schema:CreativeWork']
    elif resource_name == 'Export':
        return ['prov:Entity']
    elif resource_name == 'File':
        return ['pcdm:File', 'schema:MediaObject']
    elif resource_name in ('User', 'Speaker'):
        return ['prov:Person', 'dcterms:Agent', 'foaf:Person', 'asit:Actor']
    elif resource_name == 'ElicitationMethod':
        return 'prov:Entity'
    elif resource_name == 'Tag':
        return 'muto:Tag'
    elif resource_name == 'SyntacticCategory':
        return ['gold:LinguisticProperty',
                'gold:PartOfSpeechProperty',
                'gold:MorphosyntacticProperty']
    elif resource_name == 'Translation':
        return 'gold:LinguisticUnit'

    return 'owl:Thing'


def _get_resource_attribute_type(resource_name, attribute_name):
    """Return an rdfs:type (or list thereof) for attribute ``attribute_name``
    (e.g., 'transcription') of resource ``resource_name`` (e.g., 'Form').
    """
    if attribute_name in ('id', 'UUID'):
        return 'dcterms:identifier', False
    elif attribute_name in ('datetime_modified', 'datetime_entered',
                            'datetime_created'):
        return 'xsd:dateTime', True

    elif resource_name == 'Form':
        if attribute_name in ('transcription', 'morpheme_break',
                              'morpheme_gloss', 'phonetic_transcription',
                              'narrow_phonetic_transcription'):
            return 'gold:WrittenLinguisticExpression', True
        elif attribute_name in ('break_gloss_category',
                                'syntactic_category_string',
                                'status',
                                'files'):
            return 'gold:AnnotationProperty', True

    elif resource_name == 'Translation':
        if attribute_name in ('transcription',):
            return 'gold:WrittenLinguisticExpression', True

    elif resource_name == 'ElicitationMethod':
        if attribute_name == 'name':
            return 'foaf:name', False

    elif resource_name in ('User', 'Speaker'):
        if resource_name == 'User' and attribute_name == 'affiliation':
            return 'org:Organization', True
        if resource_name == 'Speaker' and attribute_name == 'dialect':
            return 'asit:Dialect', True

    elif resource_name == 'Tag':
        if attribute_name == 'name':
            return 'muto:tagLabel', False
        elif attribute_name == 'description':
            return 'dc:description', False

    elif resource_name == 'SyntacticCategory':
        if attribute_name == 'name':
            return 'foaf:name', False
        elif attribute_name == 'description':
            return 'dc:description', False

    elif resource_name == 'File':
        if attribute_name == 'MIME_type':
            return 'dcterms:MediaType', True

    return 'owl:Thing', True


def _get_rsrc_attr_literal_property(resource_name, attribute_name):
    """If the resource-attribute pair should be represented as a literal
    property (a relation between an IRI and a literal like a string, e.g.,
    Form.comments as dc:description), then return that owl:DatatypeProperty
    here. The second argument should be a literal data type (like xsd:dateTime)
    if the JSON data type is not specific enough.
    """
    if attribute_name == 'datetime_modified':
        return 'dcterms:modified', 'xsd:dateTime'
    elif attribute_name in ('datetime_entered', 'datetime_created'):
        return 'dcterms:created', 'xsd:dateTime'
    elif attribute_name == 'date_elicited':
        return 'dcterms:created', 'xsd:date'

    elif resource_name in ('User', 'Speaker'):
        if attribute_name == 'first_name':
            return 'foaf:givenName', None
        elif attribute_name == 'last_name':
            return 'foaf:familyName', None
        elif attribute_name == 'email':
            return 'foaf:mbox', None

    elif resource_name == 'Form':
        if attribute_name == 'comments':
            return 'dc:description', None

    elif resource_name == 'File':
        if attribute_name == 'size':
            return 'ebucore:fileSize', None
        # TODO: distinguish between the original file and the lossy derivative
        # created for network transit.
        elif attribute_name in ('filename', 'lossy_filename'):
            return 'ebucore:filename', None
        elif attribute_name == 'name':
            return 'skos:prefLabel', None
        elif attribute_name == 'description':
            return 'dc:description', None

    elif resource_name == 'Corpus':
        if attribute_name == 'name':
            return 'dc:title', None
        elif attribute_name == 'content':
            return 'schema:text', None

    elif resource_name == 'CorpusFile':
        if attribute_name == 'filename':
            return 'ebucore:filename', None
        elif attribute_name == 'format':
            return 'dc:format', None

    elif resource_name == 'Export':
        if attribute_name in ('dc_contributor', 'dc_creator', 'dc_publisher',
                'dc_date', 'dc_description', 'dc_format', 'dc_identifier',
                'dc_language', 'dc_relation', 'dc_coverage', 'dc_rights',
                'dc_subject', 'dc_title', 'dc_type'):
            return attribute_name.replace('_', ':'), None

    elif resource_name == 'Source':
        # Note: the Source.key_field of OLD::Source is not captured here by
        # bibtex ontology.
        if attribute_name in (
                'address', 'author', 'booktitle', 'chapter', 'crossref',
                'edition', 'editor', 'institution', 'journal', 'month', 'note',
                'number', 'organization', 'pages', 'publisher', 'school',
                'series', 'title', 'url', 'volume', 'year', 'affiliation',
                'abstract', 'contents', 'copyright', 'keywords', 'language',
                'location', 'mrnumber', 'price', 'size', 'key'):
            return 'bibtex:has{}'.format(attribute_name.capitalize()), None
        elif attribute_name == 'annote':
            return 'bibtex:hasAnnotation', None
        elif attribute_name == 'howpublished':
            return 'bibtex:howPublished', None
        elif attribute_name == 'type_field':
            return 'bibtex:hasType', None
        elif attribute_name == 'url':
            return 'bibtex:hasURL', None
        elif attribute_name in ('ISBN', 'ISSN', 'LCCN'):
            return 'bibtex:has{}'.format(attribute_name), None

    return False, None


def _get_resource_attribute_object_property(resource_name, attribute_name):
    """Return an owl:ObjectProperty (or list thereof) that relates the OLD
    resource named by ``resource_name`` (e.g., 'Form') to the OLD resource
    attribute named by ``attribute_name`` (e.g., 'transcription').
    """
    if resource_name == 'Form':
        if attribute_name in ('transcription', 'morpheme_break',
                              'phonetic_transcription',
                              'narrow_phonetic_transcription'):
            return [
                # domain: gold:LinguisticUnit
                # range:  gold:WrittenLinguisticExpression
                'gold:writtenRealization',
                # domain: gold:LinguisticDataStructure
                # ObjectProperty. The binary relation holding between an instance
                # of interlinear glossed text and a linguistic unit (clause, phrase,
                # etc.) from the source language.
                'gold:hasSourceLine'
            ]
        elif attribute_name == 'morpheme_gloss':
            return [
                # type: owl:ObjectProperty
                # domain: gold:LinguisticDataStructure
                # The binary relation holding between an instance of
                # interlinear glossed text (IGT) and a sequence of labels or
                # 'grams' used to describe the morphemes of the IGT.
                'gold:hasGlosses',
                # type: owl:ObjectProperty.
                # The relation between an orthographic expression in one
                # language and some orthographic expression in another such
                # that the translation is done on a word by word, or morpheme
                # by morpheme, basis without regard for idiomatic usage.
                # 'gold:literalTranslation' <= between transcription and morpheme_gloss
            ]
        elif attribute_name == 'translations':
            return [
                # type:   owl:ObjectProperty
                # domain: gold:LinguisticDataStructure
                # The binary relation holding between an instance of
                # interlinear glossed text and a linguistic unit (clause,
                # phrase, etc.) acting as a free translation of the source text
                # from the IGT instance.
                'gold:hasTranslationLine'
            ]
        elif attribute_name in ('elicitor', 'speaker'):
            return ['dcterms:creator', 'prov:wasAttributedTo']
        elif attribute_name in ('enterer', 'modifier', 'creator'):
            return ['dcterms:contributor']
        elif attribute_name == 'source':
            return ['dcterms:source']
        elif attribute_name in ('syntactic_category', 'break_gloss_category',
                                'syntactic_category_string', 'status', 'files'):
            return ['gold:feature']

    elif resource_name == 'Translation':
        if attribute_name == 'transcription':
            return ['gold:writtenRealization']

    elif resource_name in ('User', 'Speaker'):
        if resource_name == 'User':
            if attribute_name == 'affiliation':
                return ['org:memberOf']
        elif resource_name == 'Speaker':
            if attribute_name == 'dialect':
                return ['asit:speaks']

    elif resource_name == 'File':
        if attribute_name == 'MIME_type':
            return ['dcterms:format']
        elif attribute_name in ('elicitor', 'speaker'):
            return ['dcterms:creator', 'prov:wasAttributedTo']
        elif attribute_name in ('enterer', 'modifier'):
            return ['dcterms:contributor']

    elif resource_name == 'Corpus':
        if attribute_name in ('enterer', 'modifier'):
            return ['dcterms:contributor']
        elif attribute_name == 'forms':
            return ['gold:hasConstituent']

    elif resource_name == 'CorpusFile':
        if attribute_name in ('modifier', 'creator'):
            return ['dcterms:contributor']

    elif resource_name == 'Export':
        if attribute_name in ('enterer', 'modifier'):
            return ['dcterms:contributor']

    return ['rdfs:member']


def _get_rsrc_attr_literal_datatype_property(resource_name, attribute_name,
                                             val):
    """Return an owl:DatatypeProperty (or list thereof) that relates the OLD
    resource attribute (identified by ``resource_name`` and ``attribute_name``,
    e.g., 'Form' 'transcription') to its literal value, e.g., "les chiens".
    """
    if attribute_name in ('datetime_modified', 'datetime_entered'):
        return 'xsd:dateTime'
    elif attribute_name == 'date_elicited':
        return 'xsd:date'

    elif resource_name == 'Form':
        if attribute_name in ('transcription', 'morpheme_gloss'):
            return 'oold:orthographicRep'
        elif attribute_name in ('phonetic_transcription',
                                'narrow_phonetic_transcription'):
            return 'oold:phoneticRep'
        # TODO: morpheme break may be orthographic ...
        elif attribute_name == 'morpheme_break':
            return 'oold:phonemicRep'

    elif resource_name == 'Translation':
        if attribute_name == 'transcription':
            return 'oold:orthographicRep'

    elif resource_name == 'User':
        if attribute_name == 'affiliation':
            return 'skos:prefLabel'

    elif resource_name == 'Speaker':
        if attribute_name == 'dialect':
            return 'skos:prefLabel'

    elif resource_name == 'File':
        if attribute_name == 'MIME_type':
            return 'skos:prefLabel'

    return 'rdfs:label'


FORM_TRANSCRIPTION_ATTRS = (
    'transcription',
    'morpheme_break',
    'phonetic_transcription',
    'narrow_phonetic_transcription'
)


def _get_attr_attr_relations(resource_name, attribute_name, attr_dict,
                             rsrc_mdl_inst):
    """Here we create relationships between particular OLD resource attributes.
    For example, the morpheme_gloss value of a Form is the literal translation
    of the transcription and morpheme_break values of that form.
    """
    if resource_name == 'Form':
        morpheme_gloss = getattr(rsrc_mdl_inst, 'morpheme_gloss', None)
        translations = getattr(rsrc_mdl_inst, 'translations', None)
        if attribute_name == 'transcription':
            if morpheme_gloss:
                attr_dict['gold:literalTranslation'] = {
                    '@id': 'Form-{}-morpheme_gloss'.format(rsrc_mdl_inst.id)}
            if translations:
                translations = [
                    {'@id': 'Translation-{}-transcription'.format(t.id)} for t
                    in translations if t.grammaticality.strip() == '']
                attr_dict['gold:translation'] = translations
    return attr_dict


def _standard_rsrc_attr(rsrc_jsonld, rsrc, attr, val, rsrc_iri, rsrc_mdl_inst):
    """Add a representation of attribute ``attr`` of OLD resource ``rsrc`` to
    the JSON-LD of that resource, i.e., ``rsrc_jsonld``. This is "standard" in
    the sense that it is formulaic and does not require special-case logic
    like, for example, Form.speaker_comments does.
    """
    # Check if val is itself an OLD resource
    is_rsrc, val = _get_rsrc_attr_val_jsonld_repr(val)

    if rsrc == 'Export' and attr == 'dc_language':
        try:
            vallist = json.loads(val)
        except ValueError:
            vallist = None
        if vallist and isinstance(vallist, list):
            val = ', '.join(vallist)

    # Check if the attribute should be represented as a simple (typed) literal,
    # e.g., 'dc:identifier': 1.
    rsrc_attr_literal_property, data_type = (
        _get_rsrc_attr_literal_property(rsrc, attr))
    if rsrc_attr_literal_property:
        if data_type:
            val = {'@value': val, '@type': data_type}
        existing = rsrc_jsonld.get(rsrc_attr_literal_property)
        if existing:
            if isinstance(existing, list):
                existing.append(val)
            else:
                rsrc_jsonld[rsrc_attr_literal_property] = [existing, val]
        else:
            rsrc_jsonld[rsrc_attr_literal_property] = [val]
        return rsrc_jsonld

    # The owl:ObjectProperty (or list thereof) that relates a
    # given OLD resource to one of its attributes, e.g., the
    # relation between a Form and its transcription
    rsrc_attr_object_property = (
        _get_resource_attribute_object_property(rsrc, attr))

    # val is a resource, so we reference its @id with the
    # appropriate owl:ObjectProperty(s)
    if is_rsrc:
        if val == []:
            return rsrc_jsonld
        for obj_prop in rsrc_attr_object_property:
            existing = rsrc_jsonld.get(obj_prop)
            if existing:
                if isinstance(val, list):
                    existing.extend(val)
                else:
                    existing.append({'@id': val})
            else:
                rsrc_jsonld[obj_prop] = [{'@id': val}]

    # val is a literal, so we give it its own rdfs:type(s)
    else:
        # '@id' will be something like Form-27-transcription
        attr_type, is_rdf_type = _get_resource_attribute_type(rsrc, attr)
        if is_rdf_type:
            attr_iri = '{}-{}'.format(rsrc_iri, attr)
            rsrc_attr_literal_datatype_property = (
                _get_rsrc_attr_literal_datatype_property(
                    rsrc, attr, val))
            attr_dict = {
                '@id': attr_iri,
                '@type': attr_type,
                rsrc_attr_literal_datatype_property: val
            }
            attr_dict = _get_attr_attr_relations(
                rsrc, attr, attr_dict, rsrc_mdl_inst)
            obj_prop = rsrc_attr_object_property[0]
            existing = rsrc_jsonld.get(obj_prop)
            if existing:
                existing.append(attr_dict)
            else:
                rsrc_jsonld[obj_prop] = [attr_dict]
            for obj_prop in rsrc_attr_object_property[1:]:
                existing = rsrc_jsonld.get(obj_prop)
                if existing:
                    existing.append({'@id': attr_iri})
                else:
                    rsrc_jsonld[obj_prop] = [{'@id': attr_iri}]
        else:
            existing = rsrc_jsonld.get(attr_type)
            if existing:
                if isinstance(existing, list):
                    existing.append(val)
                else:
                    rsrc_jsonld[attr_type] = [existing, val]
            else:
                rsrc_jsonld[attr_type] = val

    return rsrc_jsonld


def _add_to_elicitation_event(rsrc_jsonld, rsrc, attr, val, rsrc_iri,
                              rsrc_mdl_inst):
    """Add an elicitation activity to the OLD resource represented in JSON-LD as
    ``rsrc_jsonld``. The elicitation activity is represented as a
    prof:Activity. Valuated attributes like Form.date_elicited, Form.elicitor,
    Form.speaker, etc. imply an elicitation event.

    QUESTION/TODO: what is the relevance of gold:SpokenLinguisticExpression here?
    """
    wgb = rsrc_jsonld.get('prov:wasGeneratedBy', None)
    elicitation_activity = None
    if wgb:
        try:
            elicitation_activity = [
                act for act in wgb if
                act['@id'].endswith('elicitation-activity')][0]
        except IndexError:
            pass
    else:
        wgb = rsrc_jsonld['prov:wasGeneratedBy'] = []
    if not elicitation_activity:
        elicitation_activity = {
            '@type': 'prov:Activity',
            '@id': '{}-elicitation-activity'.format(rsrc_iri),
            'foaf:name': 'Elicitation of {}'.format(rsrc_iri)
        }
        wgb.append(elicitation_activity)

    # TODO/QUESTION: do these dates need to be expressed as datetimes to be
    # prov-conformant?
    if attr == 'date_elicited':
        elicitation_activity['prov:startedAtTime'] = {
            "@value": val.isoformat(),
            "@type": "xsd:date"
        }
        elicitation_activity['prov:endedAtTime'] = {
            "@value": val.isoformat(),
            "@type": "xsd:date"
        }

    elif attr in ('elicitor', 'speaker'):
        waw = elicitation_activity.get('prov:wasAssociatedWith')
        iri = '{}-{}'.format({'elicitor': 'User'}.get(attr, 'Speaker'), val.id)
        iri = {'@id': iri}
        if waw:
            waw.append(iri)
        else:
            elicitation_activity['prov:wasAssociatedWith'] = [iri]

        wat = rsrc_jsonld.get('prov:wasAttributedTo')
        iri = '{}-{}'.format({'elicitor': 'User'}.get(attr, 'Speaker'), val.id)
        iri = {'@id': iri}
        if wat:
            wat.append(iri)
        else:
            rsrc_jsonld['prov:wasAttributedTo'] = [iri]

    elif attr == 'elicitation_method':
        elicitation_activity['prov:used'] = '{}-{}'.format('ElicitationMethod', val.id)

    return rsrc_jsonld


def _add_to_entry_event(rsrc_jsonld, rsrc, attr, val, rsrc_iri, rsrc_mdl_inst):
    """Add an entry activity to the OLD resource represented in JSON-LD as
    ``rsrc_jsonld``. The entry activity is represented as a
    prof:Activity.
    """
    wgb = rsrc_jsonld.get('prov:wasGeneratedBy', None)
    entry_activity = None
    if wgb:
        try:
            entry_activity = [
                act for act in wgb if
                act['@id'].endswith('entry-activity')][0]
        except IndexError:
            pass
    else:
        wgb = rsrc_jsonld['prov:wasGeneratedBy'] = []
    if not entry_activity:
        entry_activity = {
            '@type': 'prov:Activity',
            '@id': '{}-entry-activity'.format(rsrc_iri),
            'foaf:name': 'Entry of {}'.format(rsrc_iri),
            'prov:used': {'@id': 'old-application-instance'}
        }
        wgb.append(entry_activity)
    datetime_entered = getattr(rsrc_mdl_inst, 'datetime_entered', None)
    if datetime_entered:
        started = entry_activity.get('prov:startedAtTime')
        if not started:
            entry_activity['prov:startedAtTime'] = {
                "@value": h.utc_datetime2xsd(datetime_entered),
                "@type": "xsd:dateTime"
            }
        ended = entry_activity.get('prov:endedAtTime')
        if not ended:
            entry_activity['prov:endedAtTime'] = {
                "@value": h.utc_datetime2xsd(datetime_entered),
                "@type": "xsd:dateTime"
            }
    if attr in ('enterer', 'creator'):
        waw = entry_activity.get('prov:wasAssociatedWith')
        iri = {'@id': 'User-{}'.format(val.id)}
        if waw:
            waw.append(iri)
        else:
            entry_activity['prov:wasAssociatedWith'] = [iri]
        wat = rsrc_jsonld.get('prov:wasAttributedTo')
        iri = {'@id': 'User-{}'.format(val.id)}
        if wat:
            wat.append(iri)
        else:
            rsrc_jsonld['prov:wasAttributedTo'] = [iri]
    return rsrc_jsonld


def _add_to_modification_event(rsrc_jsonld, rsrc, attr, val, rsrc_iri,
                               rsrc_mdl_inst):
    """Add a modification activity to the OLD resource represented in JSON-LD as
    ``rsrc_jsonld``. The modification activity is represented as a
    prof:Activity.
    """
    wgb = rsrc_jsonld.get('prov:wasGeneratedBy', None)
    modification_activity = None
    if wgb:
        try:
            modification_activity = [
                act for act in wgb if
                act['@id'].endswith('modification-activity')][0]
        except IndexError:
            pass
    else:
        wgb = rsrc_jsonld['prov:wasGeneratedBy'] = []
    if not modification_activity:
        modification_activity = {
            '@type': 'prov:Activity',
            '@id': '{}-modification-activity'.format(rsrc_iri),
            'foaf:name': 'Modification of {}'.format(rsrc_iri),
            'prov:used': {'@id': 'old-application-instance'}
        }
        wgb.append(modification_activity)
    datetime_entered = getattr(rsrc_mdl_inst, 'datetime_entered', None)
    if datetime_entered:
        started = modification_activity.get('prov:startedAtTime')
        if not started:
            modification_activity['prov:startedAtTime'] = {
                "@value": h.utc_datetime2xsd(datetime_entered),
                "@type": "xsd:dateTime"
            }
        ended = modification_activity.get('prov:endedAtTime')
        if not ended:
            modification_activity['prov:endedAtTime'] = {
                "@value": h.utc_datetime2xsd(datetime_entered),
                "@type": "xsd:dateTime"
            }
    if attr == 'modifier':
        waw = modification_activity.get('prov:wasAssociatedWith')
        iri = {'@id': 'User-{}'.format(val.id)}
        if waw:
            waw.append(iri)
        else:
            modification_activity['prov:wasAssociatedWith'] = [iri]
        wat = rsrc_jsonld.get('prov:wasAttributedTo')
        iri = {'@id': 'User-{}'.format(val.id)}
        if wat:
            wat.append(iri)
        else:
            rsrc_jsonld['prov:wasAttributedTo'] = [iri]
    return rsrc_jsonld
