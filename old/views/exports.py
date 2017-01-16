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

TODO: change module name to exports.py

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

import logging
import re
import json
from uuid import uuid4

from formencode.validators import Invalid
from sqlalchemy import bindparam
from sqlalchemy.sql import asc, or_
from sqlalchemy.orm import subqueryload

from old.lib.constants import (
    DEFAULT_DELIMITER,
    FORM_REFERENCE_PATTERN,
    JSONDecodeErrorResponse,
    UNAUTHORIZED_MSG,
    UNKNOWN_CATEGORY,
)
from old.lib.dbutils import get_last_modified
import old.lib.helpers as h
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
        """After creating the export database model, we generate the actual
        export .zip directory on disk in a separate thread here.
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

