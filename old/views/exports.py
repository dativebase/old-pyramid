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

import datetime
import json
import logging
import os
import pprint
import re
from uuid import uuid4

from formencode.validators import Invalid
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
        """Create the JSON-LD export."""
        old_schema = get_old_schema()
        pprint.pprint(old_schema)

        # Create dirs /exports/<THIS_EXPORT_NAME>/db/
        exports_dir_path = self.request.registry.settings['exports_dir']
        _create_dir(exports_dir_path)
        export_path = os.path.join(exports_dir_path, export.name)
        _create_dir(export_path)
        db_path = os.path.join(export_path, 'db')
        _create_dir(db_path)

        old_instance_uri = self.request.registry.settings['uri']
        delible_path = os.path.dirname(exports_dir_path)
        db_uri_path = db_path.replace(delible_path, '')
        if old_instance_uri.endswith('/'):
            old_instance_uri = old_instance_uri[:-1]
        root_iri = '{}{}'.format(old_instance_uri, db_uri_path)

        old_jsonld_path = os.path.join(db_path, 'OLD.jsonld')
        old_jsonld = old_schema['OLD']['jsonld'].copy()
        old_jsonld['@id'] = old_jsonld_path

        coll2rsrc = {term: val['resource'] for term, val in old_schema.items()
                     if val['entity_type'] == 'old collection'}
        for coll, rsrc in coll2rsrc.items():
            rsrcmodel = getattr(old_models, rsrc)
            idattr = inspect(rsrcmodel).primary_key[0].name
            resource_ids = {
                idtup[0]: _get_jsonld_iri_id(root_iri, rsrc, idtup[0])
                for idtup in self.request.dbsession.query(
                    rsrcmodel).with_entities(getattr(rsrcmodel, idattr)).all()}
            old_jsonld['OLD'][coll] = list(resource_ids.values())
            for id_, rsrc_iri in resource_ids.items():
                rsrc_mdl_inst = self.request.dbsession.query(rsrcmodel).get(id_)
                rsrc_jsonld = old_schema[rsrc]['jsonld'].copy()
                rsrc_jsonld['@id'] = rsrc_iri
                for attr, term_def in rsrc_jsonld[rsrc]['@context'].items():
                    val = getattr(rsrc_mdl_inst, attr)
                    if val is None:
                        rsrc_jsonld[rsrc][attr] = val
                    elif (    isinstance(term_def, dict) and
                              term_def.get('@type') == '@id'):
                        attr_rsrc = val.__class__.__name__
                        attr_idattr = inspect(val.__class__).primary_key[0].name
                        id_ = getattr(val, attr_idattr)
                        rsrc_jsonld[rsrc][attr] = _get_jsonld_iri_id(
                            root_iri, attr_rsrc, id_)
                    elif isinstance(val, (datetime.date, datetime.datetime)):
                        rsrc_jsonld[rsrc][attr] = val.isoformat()
                    else:
                        rsrc_jsonld[rsrc][attr] = val
                rsrc_jsonld_path = os.path.join(db_path, rsrc_iri.split('/')[-1])
                with open(rsrc_jsonld_path, 'w') as fileo:
                    fileo.write(
                        json.dumps(
                            rsrc_jsonld,
                            sort_keys=True,
                            indent=4,
                            separators=(',', ': ')))
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
        within the request.
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


def _get_jsonld_iri_id(base_path, resource_name, resource_id):
    return os.path.join(
        base_path,
        '{}-{}.jsonld'.format(resource_name, resource_id))


def _create_dir(exports_dir_path):
    if not os.path.isdir(exports_dir_path):
        h.make_directory_safely(exports_dir_path)

