# Copyright 2016 Joel Dunham
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

"""Requests to / are routed here. Returns a dict (JSON object) describing the
OLD.
"""

import datetime
import logging
import re
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy.sql import asc, or_
from sqlalchemy.orm import subqueryload
from sqlalchemy.orm.attributes import InstrumentedAttribute

import old.models as old_models
# TODO: ...
# from onlinelinguisticdatabase.config.routing import make_map

LOGGER = logging.getLogger(__name__)


RESOURCES = (
    'ApplicationSettings',
    'Collection',
    'CollectionBackup',
    'Corpus',
    'CorpusBackup',
    'ElicitationMethod',
    'File',
    'Form',
    'FormBackup',
    'FormSearch',
    'Keyboard',
    'Language',
    'MorphemeLanguageModel',
    'MorphemeLanguageModelBackup',
    'MorphologicalParser',
    'MorphologicalParserBackup',
    'Morphology',
    'MorphologyBackup',
    'Orthography',
    'Page',
    'Phonology',
    'PhonologyBackup'
)


class Info:

    def __init__(self, request):
        self.request = request

    def index(self):
        """Making a request to an OLD with no path in the URL should return
        information about that OLD. This method returns a JSON object with the
        following keys:

        - app = 'Online Linguistic Database'
        - version = the current version of the OLD
        - paths = an array of valid URL paths and HTTP methods that this OLD
          exposes, e.g., "GET /forms"

        .. warning::

            The 'version' key must be valuated with a valid version string,
            i.e., only digits and period characters. When ``python setup.py``
            is run, the 'version' key will be updated with the current version
            as specified in setup.py.
        """
        # Get OLD resources as a dict from resource names to lists of resource
        # attributes.
        resources = {}
        for rname in RESOURCES:
            resources[rname] = []
            r_class = getattr(old_models, rname)
            for key in sorted(r_class.__dict__):
                if key.endswith('_id'):
                    continue
                val = r_class.__dict__[key]
                if isinstance(val, InstrumentedAttribute):
                    resources[rname].append(key)
            resources[rname].sort()

        # Get the valid paths of this OLD, e.g., GET /forms or PUT
        # /syntacticcategories as a sorted list of strings.
        UNEXPOSED = ('OPTIONS',)
        routes = self.request.registry.introspector.get_category('routes')
        myroutes = []
        for route in routes:
            r_methods = route['introspectable']['request_methods']
            if r_methods:
                r_method = '/'.join(
                    [m for m in route['introspectable']['request_methods']
                     if m not in UNEXPOSED])
            else:
                r_method = 'GET'
            r_patt = route['introspectable']['pattern']\
                .replace('{', '<')\
                .replace('}', '>')
            myroutes.append((r_patt, r_method))

        meta = {
            'app': 'Online Lingusitic Database',
            'version': '2.0.0',
            'paths': ['%s %s' % (r[1], r[0]) for r in sorted(myroutes)],
            'resources': resources
        }
        return meta
