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

    X export of entire data set
    X access files (.jsonld, media files) over HTTP
    X download entire export as zipped bag (https://en.wikipedia.org/wiki/BagIt)
    - separate export thread
    - fully public in exports/public/

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
import shutil
from uuid import uuid4

import bagit
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

    def generate(self):
        """After creating the export database model, the user must request this
        action in order to generate the actual export .zip directory on disk in
        a separate thread.
        """
        export, id_ = self._model_from_id(eager=True)
        if not export:
            self.request.response.status_int = 404
            return {'error': 'There is no export with id %s' % id}
        EXPORT_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'generate_export',
            'args': {
                'export_id': id_,
                'user_id': self.logged_in_user.id,
                'settings': self.request.registry.settings
            }
        })
        return export

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

    def _get_user_data(self, data):
        return {}

    def _get_update_data(self, user_data):
        return {}
