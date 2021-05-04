# Copyright 2021 Joel Dunham
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

"""Requests under /sync/ are routed here. These endpoints are specialized for
helping a follower OLD to synchronize with a leader.
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.orm.attributes import InstrumentedAttribute

import old.lib.constants as oldc
import old.models as old_models


LOGGER = logging.getLogger(__name__)


MODELS = (
    'ApplicationSettings',
    'ApplicationSettingsUser',
    'Collection',
    'CollectionBackup',
    'CollectionFile',
    'CollectionForm',
    'CollectionTag',
    'Corpus',
    'CorpusBackup',
    'CorpusFile',
    'CorpusForm',
    'CorpusTag',
    'ElicitationMethod',
    'File',
    'FileTag',
    'Form',
    'FormBackup',
    'FormFile',
    'FormSearch',
    'FormTag',
    'Keyboard',
    # 'Language': {}, # Language is special (immutable) ...
    'MorphemeLanguageModel',
    'MorphemeLanguageModelBackup',
    'MorphologicalParser',
    'MorphologicalParserBackup',
    'Morphology',
    'MorphologyBackup',
    'Orthography',
    'Page',
    'Parse',
    'Phonology',
    'PhonologyBackup',
    'Source',
    'Speaker',
    'SyntacticCategory',
    'Tag',
    'Translation',
    'User',
    'UserForm',
)


TABLES = tuple(getattr(old_models, mname).__table__.name for mname in MODELS)


def date_string(date_thing):
    """Given a "date", return a string, where the date may already be a string
    or it may be a `datetime.datetime` instance.
    """
    if isinstance(date_thing, str):
        return date_thing.replace(' ', 'T')
    return date_thing.strftime(oldc.ISO_STRFTIME)


class Sync:

    def __init__(self, request):
        self.request = request

    def last_modified(self):
        """Return a dict whose keys are table names and whose values are dicts
        from row IDs to row last_modified date-time strings.
        """
        LOGGER.info('Returning last_modified information about this OLD.')
        tables = {}
        for tname in TABLES:
            tables[tname] = {
                r['id']: date_string(r['datetime_modified']) for
                r in self.request.dbsession.execute(
                    text('select id, datetime_modified from {}'.format(tname)))}
        LOGGER.info('Returned last_modified information about this OLD.')
        return tables

    def tables(self):
        """Return the raw tables of the OLD domain model as a single JSON
        object. The JSON request body may optionally be an object with a
        `tables` key whose value is an object whose keys are table names and
        whose values are the integer IDs of the table rows that are needed by
        the requester. The response body is isomorphic to the request: an
        object with table name keys whose values are maps from row IDs to rows
        as flat objects.

        Example request:

            {'tables': {'form': [1, 8], 'corpus': [3]}}

        Example response::

            {'form': {'1': {'id': 1}
                      '8': {'id': 8}},
             'corpus': {'3': {'id': 3}}}
        """
        LOGGER.info('Returning all tables in this OLD matching the supplied IDs.')
        params = json.loads(self.request.body.decode(self.request.charset))
        tables = params.get('tables')
        if not tables:
            msg = "No 'tables' key present in GET params"
            LOGGER.error(msg)
            self.request.response.status_int = 400
            return {'error': msg}
        ret = {}
        if tables == '*':
            LOGGER.warn('Returning all tables')
            for tname in TABLES:
                ret[tname] = {
                    r['id']: dict(r)
                    for r in self.request.dbsession.execute(
                        text('select * from {}'.format(tname)))}
        else:
            LOGGER.info('Returning select tables')
            for tname in TABLES:
                ret[tname] = {}
                ids = tables.get(tname)
                if not ids:
                    continue
                if (not isinstance(ids, list) or
                        set([isinstance(x, int) for x in ids]) != {True}):
                    raise ValueError('Table name must resolve to a list of integers')
                ret[tname] = {
                    r['id']: dict(r)
                    for r in self.request.dbsession.execute(
                        text('select * from {} where id in ({})'.format(
                            tname,
                            ', '.join(str(i) for i in ids))))}
        LOGGER.info('Returned all tables in this OLD matching the supplied request.')
        return ret
