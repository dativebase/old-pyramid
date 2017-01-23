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

"""Contains the :class:`ExportView` for exporting the entire data set.
Current targetted export format: Bagged JSON-LD.

Sprint 1---Basic:

    - export of entire data set
    - fully public in exports/public/
    - access files (.jsonld, media files) over HTTP
    - download entire export as archive (.7z, .tar.gz, .zip)
    - conforms to BagIt specification (https://en.wikipedia.org/wiki/BagIt)

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
import re
from uuid import uuid4

from formencode.validators import Invalid
from pyld import jsonld
from sqlalchemy import bindparam
from sqlalchemy.sql import asc, or_
from sqlalchemy.orm import subqueryload
from sqlalchemy.inspection import inspect

from old.lib.constants import (
    DEFAULT_DELIMITER,
    FORM_REFERENCE_PATTERN,
    JSONDecodeErrorResponse,
    UNAUTHORIZED_MSG,
    UNKNOWN_CATEGORY,
)
from old.lib.dbutils import get_last_modified
import old.lib.helpers as h
from old.lib.introspectmodel import get_old_schema
from old.lib.export_worker import EXPORT_WORKER_Q
from old.lib.schemata import FormIdsSchema
import old.models as old_models
from old.views.resources import (
    Resources,
    SchemaState
)


LOGGER = logging.getLogger(__name__)
NO_UPDATE = {'error': 'Exports cannot be updated.'}


class Exports(Resources):
    """Generate responses to requests on export resources."""

    # Export resources CANNOT be updated:
    def update(self):
        self.request.response.status_int = 404
        return NO_UPDATE

    def edit(self):
        self.request.response.status_int = 404
        return NO_UPDATE

    # TODO: when a user attempts to create an export and one is currently being
    # generated, we should maybe warn them of that prior to creating a new one...

    def _get_create_data(self, data):
        """User supplies no data when creating an export. All data are based on
        logged-in user and date of creation request.
        """
        now = h.now()
        UUID = str(uuid4())
        timestamp = int(now.timestamp())
        name = 'old-export-{}-{}'.format(UUID, timestamp)
        user_model = self.logged_in_user
        return {
            'UUID': UUID,
            'datetime_entered': now,
            'enterer': user_model,
            'name': name,
            'generate_succeeded': False,
            'generate_message': '',
            'generate_attempt': str(uuid4())
        }

    def _post_create(self, export):
        """Create the JSON-LD export.
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
        settings = self.request.registry.settings

        # All the paths we will need for the export:
        exports_dir_path = _create_exports_dir(settings)
        export_path = _create_export_dir(exports_dir_path, export)
        db_path = _create_db_path(export_path)

        # The IRI/URIs we will need for the "@id" values of the JSON-LD objects
        old_instance_uri = settings['uri']
        db_uri_path = db_path.replace(os.path.dirname(exports_dir_path), '')
        if old_instance_uri.endswith('/'):
            old_instance_uri = old_instance_uri[:-1]
        root_iri = '{}{}'.format(old_instance_uri, db_uri_path)

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
                for idtup in self.request.dbsession.query(
                    rsrcmodel).with_entities(getattr(rsrcmodel, idattr)).all()}
            old_jsonld['OLD'][coll] = list(rsrc_id2iri.values())
            for id_, rsrc_iri in rsrc_id2iri.items():
                rsrc_mdl_inst = self.request.dbsession.query(rsrcmodel).get(id_)
                rsrc_jsonld = old_schema[rsrc]['jsonld'].copy()
                rsrc_jsonld['@id'] = rsrc_iri

                # Insert a representation of each resource attribute into the
                # Resource's .jsonld object.
                for attr, term_def in rsrc_jsonld[rsrc]['@context'].items():
                    val = getattr(rsrc_mdl_inst, attr)
                    rsrc_jsonld[rsrc][attr] = _get_rsrc_attr_val_jsonld_repr(
                        val, term_def, root_iri)
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

    def _post_create_TODO(self, export):
        """After creating the export database model, we generate the actual
        export .zip directory on disk in a separate thread here.
        TODO: implement this in a separate thread later. For now prototype it
        within the request. See ``_post_Create`` above.
        """
        EXPORT_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'generate_export',
            'args': {
                'export_id': export.id,
                'user_id': self.logged_in_user.id,
                'config_path': self.request.registry.settings['__file__'],
            }
        })

    def _get_user_data(self, data):
        return {}

    def _get_update_data(self, user_data):
        return {}


def _get_rsrc_attr_val_jsonld_repr(val, term_def, root_iri):
    """Return a JSON-LD representation of ``val``, which is the value of an OLD
    resource attribute. If ``vall` is another OLD resource, we return the IRI
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


def _create_dir(exports_dir_path):
    if not os.path.isdir(exports_dir_path):
        h.make_directory_safely(exports_dir_path)


def _create_exports_dir(settings):
    exports_dir_path = settings['exports_dir']
    _create_dir(exports_dir_path)
    return exports_dir_path


def _create_export_dir(exports_dir_path, export):
    export_path = os.path.join(exports_dir_path, export.name)
    _create_dir(export_path)
    return export_path


def _create_db_path(export_path):
    db_path = os.path.join(export_path, 'db')
    _create_dir(db_path)
    return db_path
