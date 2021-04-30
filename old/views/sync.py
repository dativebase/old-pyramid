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

import logging

from sqlalchemy.orm.attributes import InstrumentedAttribute

import old.models as old_models


LOGGER = logging.getLogger(__name__)


RESOURCES = (
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


class Sync:

    def __init__(self, request):
        self.request = request

    def last_modified(self):
        """Return a map whose keys are resource names and whose values are maps
        from row IDs to row last_modified datet-time strings.
        """
        LOGGER.info('Returning last_modified information about this OLD.')
        # Get OLD resources as a dict from resource names to lists of resource
        # attributes.
        resources = {}
        for rname in RESOURCES:
            resources[rname] = {}
            model_cls = getattr(old_models, rname)
            resources[rname] = dict(self.request.dbsession.query(
                getattr(model_cls, 'id'),
                getattr(model_cls, 'datetime_modified')).all())
        LOGGER.info('Returned last_modified information about this OLD.')
        return resources


