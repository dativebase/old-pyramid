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

"""Morpheme language model backup model"""

import json
import logging

from sqlalchemy import Column, Sequence
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, Boolean, Float

from old.models.meta import Base, now


LOGGER = logging.getLogger(__file__)


class MorphemeLanguageModelBackup(Base):
    # pylint: disable=too-many-instance-attributes

    __tablename__ = 'morphemelanguagemodelbackup'

    def __repr__(self):
        return '<MorphemeLanguageModelBackup (%s)>' % self.id

    id = Column(
        Integer, Sequence('morphemelanguagemodelbackup_seq_id', optional=True),
        primary_key=True)
    morphemelanguagemodel_id = Column(Integer)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    corpus = Column(UnicodeText)
    enterer = Column(UnicodeText)
    modifier = Column(UnicodeText)
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
    generate_succeeded = Column(Boolean, default=False)
    generate_message = Column(Unicode(255))
    generate_attempt = Column(Unicode(36)) # a UUID
    perplexity = Column(Float, default=0.0)
    perplexity_attempt = Column(Unicode(36)) # a UUID
    perplexity_computed = Column(Boolean, default=False)
    toolkit = Column(Unicode(10))
    order = Column(Integer)
    smoothing = Column(Unicode(30))
    vocabulary_morphology = Column(UnicodeText)
    restricted = Column(Boolean)
    categorial = Column(Boolean)

    def vivify(self, morpheme_language_model_dict):
        """The vivify method gives life to a morpheme language model backup by
        specifying its attributes using the to-be-backed-up morpheme language
        model (morpheme_language_model_dict) The relational attributes of the
        to-be-backed-up morpheme language model are converted into (truncated)
        JSON objects.
        """
        self.UUID = morpheme_language_model_dict['UUID']
        self.morphemelanguagemodel_id = morpheme_language_model_dict['id']
        self.name = morpheme_language_model_dict['name']
        self.description = morpheme_language_model_dict['description']
        self.corpus = json.dumps(morpheme_language_model_dict['corpus'])
        self.enterer = json.dumps(morpheme_language_model_dict['enterer'])
        self.modifier = json.dumps(morpheme_language_model_dict['modifier'])
        self.datetime_entered = morpheme_language_model_dict['datetime_entered']
        self.datetime_modified = morpheme_language_model_dict['datetime_modified']
        self.generate_succeeded = morpheme_language_model_dict['generate_succeeded']
        self.generate_message = morpheme_language_model_dict['generate_message']
        self.generate_attempt = morpheme_language_model_dict['generate_attempt']
        self.perplexity = morpheme_language_model_dict['perplexity']
        self.perplexity_attempt = morpheme_language_model_dict['perplexity_attempt']
        self.perplexity_computed = morpheme_language_model_dict['perplexity_computed']
        self.toolkit = morpheme_language_model_dict['toolkit']
        self.order = morpheme_language_model_dict['order']
        self.smoothing = morpheme_language_model_dict['smoothing']
        self.vocabulary_morphology = json.dumps(
            morpheme_language_model_dict['vocabulary_morphology'])
        self.restricted = morpheme_language_model_dict['restricted']
        self.categorial = morpheme_language_model_dict['categorial']

    def get_dict(self):
        return {
            'id': self.id,
            'morphemelanguagemodel_id': self.morphemelanguagemodel_id,
            'UUID': self.UUID,
            'name': self.name,
            'corpus': self.json_loads(self.corpus),
            'description': self.description,
            'enterer': self.json_loads(self.enterer),
            'modifier': self.json_loads(self.modifier),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'generate_succeeded': self.generate_succeeded,
            'generate_message': self.generate_message,
            'perplexity': self.perplexity,
            'perplexity_attempt': self.perplexity_attempt,
            'perplexity_computed': self.perplexity_computed,
            'generate_attempt': self.generate_attempt,
            'toolkit': self.toolkit,
            'order': self.order,
            'smoothing': self.smoothing,
            'vocabulary_morphology': self.json_loads(self.vocabulary_morphology),
            'restricted': self.restricted,
            'categorial': self.categorial
        }
