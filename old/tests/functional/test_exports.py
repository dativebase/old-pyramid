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

from base64 import encodestring
import datetime
import json
import logging
import os
import pprint
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc

from old.lib.introspectmodel import (
    get_old_model_classes,
    get_old_jsonld_schema,
    get_jsonld_form_context
)
from old.lib.dbutils import DBUtils
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import Export
from old.tests import TestView

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Export._url()


###############################################################################
# Functions for creating & retrieving test data
###############################################################################

class TestExportsView(TestView):

    # Clear all models in the database except Language; recreate the users.
    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def test_create(self):
        """Tests that POST /exports initiates the creation of a new export."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        response = self.app.post(url('create'), '{}', self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        jsonld_schema = get_old_jsonld_schema()
        # pprint.pprint(jsonld_schema, width=200)
        # pprint.pprint(jsonld_schema)

        jsonld_form_context = get_jsonld_form_context(jsonld_schema)
        pprint.pprint(jsonld_form_context)

