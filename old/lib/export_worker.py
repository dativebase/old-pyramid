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

"""

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
from sqlalchemy import create_engine
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import sessionmaker
from paste.deploy import appconfig
from pyld import jsonld
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

    # OLD schema is a dict with JSON-LD-compatible schema info
    old_schema = get_old_schema()

    # All the paths we will need for the export:
    exports_dir_path = _create_exports_dir(settings)
    if export.public:
        exports_type_path = _create_exports_public_dir(exports_dir_path)
    else:
        exports_type_path = _create_exports_private_dir(exports_dir_path)
    export_path = _create_export_dir(exports_type_path, export)
    db_path = _create_db_path(export_path)
    export_store_path = os.path.join(export_path, 'store')
    app_set = db.current_app_set

    # Copy all of the "files" (Files, Parsers, Corpora, etc.) of this OLD
    # to the export directory.
    store_path = settings['permanent_store']
    shutil.copytree(store_path, export_store_path)

    # The IRI/URIs we will need for the "@id" values of the JSON-LD objects
    old_instance_uri = settings['uri']
    db_uri_path = db_path.replace(os.path.dirname(exports_type_path), '')
    path, leaf = os.path.split(db_uri_path)
    db_uri_path = os.path.join(path, 'data', leaf)
    store_uri_path = export_store_path.replace(
        os.path.dirname(exports_type_path), '')
    path, leaf = os.path.split(store_uri_path)
    store_uri_path = os.path.join(path, 'data', leaf)
    if old_instance_uri.endswith('/'):
        old_instance_uri = old_instance_uri[:-1]
    # Note: the /data is required because bagit will put everything in a
    # data/ dir.
    root_iri = '{}{}'.format(old_instance_uri, db_uri_path)
    root_store_iri = '{}{}'.format(old_instance_uri, store_uri_path)

    # Add ontology/data dictionary namespaces (e.g., dc, foaf, prov)
    # the OLD schema
    old_schema = _add_namespaces(old_schema, root_iri)

    # Create the OLD.jsonld root export object
    old_jsonld_path = os.path.join(db_path, 'OLD.jsonld')
    old_jsonld = old_schema['OLD']['jsonld'].copy()
    # old_jsonld['@id'] = old_jsonld_path
    old_jsonld['@id'] = ""  # possible because @base in @context equals old_jsonld_path

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
    for coll, rsrc in coll2rsrc.items():
        rsrcmodel = getattr(old_models, rsrc)
        idattr = inspect(rsrcmodel).primary_key[0].name
        rsrc_id2iri = {
            idtup[0]: _get_jsonld_iri_id(root_iri, rsrc, idtup[0])
            for idtup in dbsession.query(
                rsrcmodel).with_entities(getattr(rsrcmodel, idattr)).all()}
        old_jsonld['OLD'][coll] = list(rsrc_id2iri.values())
        for id_, rsrc_iri in rsrc_id2iri.items():
            rsrc_mdl_inst = dbsession.query(rsrcmodel).get(id_)
            rsrc_jsonld = old_schema[rsrc]['jsonld'].copy()
            rsrc_jsonld['@id'] = rsrc_iri

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
            for attr, term_def in rsrc_jsonld[rsrc]['@context'].items():
                try:
                    val = getattr(rsrc_mdl_inst, attr)
                    # for dc:creator and dc:contributor
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
                    rsrc_jsonld[rsrc][attr] = \
                        _get_rsrc_attr_val_jsonld_repr(
                            val, term_def, root_iri)
                except AttributeError:
                    if attr.endswith('_filedata'):
                        attr_ctprt = attr[:-9]
                        val = getattr(rsrc_mdl_inst, attr_ctprt)
                        print('We want an IRI for attr {} of resource {}'
                                ' with val {}, given root_store_iri {}'.format(
                                    attr, rsrc, val, root_store_iri))
                        rsrc_jsonld[rsrc][attr] = _get_filedata_iri(
                            rsrc, rsrc_mdl_inst, attr, val, root_store_iri)
                    else:
                        raise
            rsrc_jsonld_path = os.path.join(
                db_path, rsrc_iri.split('/')[-1])

            # Write the OLD Resource.jsonld to disk in the exports/ subdir
            # TODO: the entire db should just be in one OLD.jsonld file
            with open(rsrc_jsonld_path, 'w') as fileo:
                fileo.write(
                    json.dumps(
                        rsrc_jsonld,
                        sort_keys=True,
                        indent=4,
                        separators=(',', ': ')))
            # Testing out PyLD's jsonld.normalize here:
            #normalized = jsonld.normalize(
            #    rsrc_jsonld, {
            #        'algorithm': 'URDNA2015',
            #        'format': 'application/nquads'})
            #pprint.pprint('\n\nWITHOUT NORMALIZATION')
            #pprint.pprint(rsrc_jsonld)
            #pprint.pprint('\n\nWITH NORMALIZATION')
            #pprint.pprint(normalized)

    # Dublin Core contributor computed as all speakers and
    # elicitors/enterers/modifiers, in that order, secondarily ordered by
    # weighted resource attribution count.
    dc_contributors = _get_dc_contributors(enterers_dict, elicitors_dict,
                                           modifiers_dict, speakers_dict)
    dc_creators = _get_dc_creators(speakers_dict, elicitors_dict)
    # Add dc:contributors and dc:creators to the export model as JSON arrays
    export.dc_contributor = json.dumps(dc_contributors)
    export.dc_creator = json.dumps(dc_creators)

    # Put dc:contributors and dc:creators into OLD.jsonld
    old_jsonld['OLD']['dc:creator'] = dc_creators
    old_jsonld['OLD']['dc:contributor'] = dc_contributors

    # removed dcterms:bibliographicCitation until that term set is used...
    # TODO: it should be used (or something like it) because
    # ``_get_dc_bib_cit`` returns a useful string.
    # if not export.dc_bibliographic_citation:
    #     # TODO: is ``old_jsonld['@id']`` the actual URI of the data set? It
    #     # needs to be ...
    #     export.dc_bibliographic_citation = _get_dc_bib_cit(
    #         dc_creators, export, old_jsonld['@id'])
    # old_jsonld['OLD']['dc:bibliographicCitation'] = (
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
    old_jsonld['OLD']['dc:date'] = export.dc_date

    # Add the remaining dc: term values to the OLD export object.
    for dc_term in ('publisher', 'description', 'format', 'identifier',
                    'relation', 'coverage', 'rights', 'type', 'title'):
        val = getattr(export, 'dc_{}'.format(dc_term), None)
        if val:
            old_jsonld['OLD']['dc:{}'.format(dc_term)] = val

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
                old_jsonld['OLD']['dc:{}'.format(dc_term)] = val_loaded
            else:
                old_jsonld['OLD']['dc:{}'.format(dc_term)] = val

    # Write the OLD.jsonld to disk in the exports/ subdir
    with open(old_jsonld_path, 'w') as fileo:
        fileo.write(
            json.dumps(
                old_jsonld,
                sort_keys=True,
                indent=4,
                separators=(',', ': ')))

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
    jsonld_type = old_jsonld.get('@type')
    if jsonld_type:
        if isinstance(jsonld_type, list):
            jsonld_type.append('prov:Entity')
        else:
            old_jsonld['@type'] = [jsonld_type, 'prov:Entity']
    old_jsonld['@type'] = ['prov:Entity']
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
    old_instance = {
        '@id': 'old-application-instance',
        '@type': 'prov:SoftwareAgent',
        'foaf:name': old_instance_foaf_name
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


def _get_filedata_iri(rsrc_name, rsrc, attr, val, root_store_iri):
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
    return os.path.join(root_store_iri, dirname, val)


def _get_rsrc_attr_val_jsonld_repr(val, term_def, root_iri):
    """Return a JSON-LD representation of ``val``, which is the value of an OLD
    resource attribute. If ``val` is another OLD resource, we return the IRI
    to its own JSON-LD object.
    """
    if isinstance(val, list):
        return [
            _get_rsrc_attr_val_jsonld_repr(x, term_def, root_iri) for x in val]
    elif val is None:
        return val
    elif isinstance(val, old_models.Model):
        attr_rsrc = val.__class__.__name__
        attr_idattr = inspect(val.__class__).primary_key[0].name
        id_ = getattr(val, attr_idattr)
        return _get_jsonld_iri_id(root_iri, attr_rsrc, id_)
    elif isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    else:
        return val


def _get_jsonld_iri_id(base_path, resource_name, resource_id):
    """Return a JSON-LD IRI ("@id" value) for an OLD resource of type
    ``resource_name`` with id ``resource_id`` being served at the base path
    ``base_path``.
    """
    return os.path.join(
        base_path,
        '{}-{}.jsonld'.format(resource_name, resource_id))


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


def _create_store_path(export_path):
    store_path = os.path.join(export_path, 'store')
    _create_dir(store_path)
    return store_path


def _get_person_full_name(person_model):
    """Given a User or Speaker model, return their full name, e.g., 'Jane
    Doe'.
    """
    return '%s %s' % (person_model.first_name, person_model.last_name)


def _add_namespaces(old_schema, root_iri):
    """Add the namespaces of various ontologies and data dictionaries (e.g.,
    dc, foaf, prov) to the OLD schema.
    """
    # The following line causes allows for relative URIs for resource objects
    # even if the export is served at another URL later.
    old_schema['OLD']['jsonld']['@context']['@base'] = root_iri
    old_schema['OLD']['jsonld']['@context']['dc'] = (
        'http://purl.org/dc/elements/1.1/')
    old_schema['OLD']['jsonld']['@context']['dcterms'] = (
        'http://purl.org/dc/terms/')
    old_schema['OLD']['jsonld']['@context']['prov'] = (
        'http://www.w3.org/ns/prov#')
    old_schema['OLD']['jsonld']['@context']['foaf'] = (
        'http://xmlns.com/foaf/0.1/')
    old_schema['OLD']['jsonld']['@context']['xsd'] = (
        'http://www.w3.org/2001/XMLSchema#')
    old_schema['OLD']['jsonld']['@context']['lime'] = (
        'http://art.uniroma2.it/ontologies/lime#')
    return old_schema


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
