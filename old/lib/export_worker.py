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

This module contains some multithreading worker and queue logic for
long-running processes related to the creation of OLD exports.

The export worker can only run a callable that is a global in
:mod:`old.lib.export_worker` and which takes keyword arguments.  Example usage::

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

Sprint 1---Basic:

    X export of entire data set
    X access files (.jsonld, media files) over HTTP
    X download entire export as zipped bag (https://en.wikipedia.org/wiki/BagIt)
    X separate export thread
    X fully public in exports/public/
    X fully private in exports/private/

- Options
  - entire data set, fully public
  - entire data set, fully private
  - entire data set, fully public, private parts encrypted
  - partial data set, fully public, private parts removed

- Public vs Private exports in distinct directories:

  - exports/public/
  - exports/private/

  - The server will be configured to serve everything in exports/public/
    openly. In contrast, access to exports/private/ would be routed through the
    standard OLD/Pyramid auth mechanism.

- Directory structure and archive of entire export (.7z, .tar.gz, .zip)?
  - choose one or offer several options?

- BagIt Specification Conformance
  - https://en.wikipedia.org/wiki/BagIt
  - https://github.com/LibraryOfCongress/bagit-python

- Export type "Partially Encrypted":

  - GnuPG encryption private/public key-based encryption
  - No encryption is the default
  - Special tags used for encrypting specified resources

    - During export creation, user specifies "export encryption prefix", which
      is an OLD tag prefix, e.g., "export-2017-02-01-encrypt"
    - During export, if a resource is tagged with a tag that begins with the
      the "export encryption prefix", then it is encrypted with access
      determined by the suffix of the tag name.
    - For example, "export-2017-02-01-encrypt:all" would mean that all users on
      the OLD instance with known public GPG keys would be able to decrypt.
    - For example, "export-2017-02-01-encrypt:username1,username2" would mean
      that only users with the usernames "username1" and "username2" would be
      able to decrypt that particular resource.
    - Encryption tagging would have to generalize from OLD file resources to
      the associated digital/binary file content. Similarly for other resources
      which are one-to-one associated to binary files, e.g., morphological
      parsers, corpora.

Requirements:

1. Exports are resources that can be:

   a. Created
   b. Read (singleton or collection)
   c. Deleted (if admin)

2. An OLD export is:
   - a .zip file containing all of the data in an OLD at a particular
     moment in time.
   - files are organized according to the bag-it specification
   - the database is serialized to JSON-LD
   - the export should be importable into another OLD system

3. Created in a separate thread.
   - the client must poll the OLD in order to determine when the export is
     complete.
   - the export should be saved to disk and be efficiently retrievable (a
     static asset, with or without authentication required, see
     http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/assets.html)
   - checked for consistency and repaired, if necessary
     how? get all lastmod times for all resources prior to export
     generation and then re-check them prior to export save?

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
    export = dbsession.query(old_models.Export).get(kwargs['export_id'])
    export.generate_succeeded = False
    try:
        _generate_export(export, settings, dbsession)
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


def _generate_export(export, settings, dbsession):
    """Create the JSON-LD export. 
    :param Model export: the Export model.
    :param dict settings: the settings of the OLD instance
    :param object dbsession: a SQLAlchemy database session object.

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

    # Create the OLD.jsonld root export object
    old_jsonld_path = os.path.join(db_path, 'OLD.jsonld')
    old_jsonld = old_schema['OLD']['jsonld'].copy()
    old_jsonld['@id'] = old_jsonld_path

    # Go through each Collection/Resource pair, adding an array of IRIs to
    # OLD.jsonld for each resource collection and creating .jsonld files
    # for each resource instance.
    coll2rsrc = {term: val['resource'] for term, val in old_schema.items()
                    if val['entity_type'] == 'old collection'}
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

            # Insert a representation of each resource attribute into the
            # Resource's .jsonld object.
            for attr, term_def in rsrc_jsonld[rsrc]['@context'].items():
                try:
                    val = getattr(rsrc_mdl_inst, attr)
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

    # Write the OLD.jsonld to disk in the exports/ subdir
    with open(old_jsonld_path, 'w') as fileo:
        fileo.write(
            json.dumps(
                old_jsonld,
                sort_keys=True,
                indent=4,
                separators=(',', ': ')))
    bagit.make_bag(export_path)
    shutil.make_archive(export_path, 'zip', export_path)


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
    export_path = os.path.join(exports_type_path, export.name)
    _create_dir(export_path)
    return export_path


def _create_db_path(export_path):
    db_path = os.path.join(export_path, 'db')
    _create_dir(db_path)
    return db_path


def _create_store_path(export_path):
    store__path = os.path.join(export_path, 'store')
    _create_dir(store__path)
    return store__path
