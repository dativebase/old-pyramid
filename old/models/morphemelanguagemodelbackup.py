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

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean, Float
from .meta import Base, now
from .morphemelanguagemodel import MorphemeLanguageModel
import json
import logging

log = logging.getLogger(__file__)

class MorphemeLanguageModelBackup(Base):
    """An OLD morpheme language model (LM) backup is a copy of the state of a
    morpheme LM at a certain point in time. Every time a morpheme LM is
    modified or deleted a backup is created first.
    """

    __tablename__ = 'morphemelanguagemodelbackup'

    def __repr__(self):
        return '<MorphemeLanguageModelBackup (%s)>' % self.id

    id = Column(
        Integer, Sequence('morphemelanguagemodelbackup_seq_id', optional=True), primary_key=True)
    morphemelanguagemodel_id = Column(
        Integer,
        doc='The id of the morpheme language model that this morpheme language'
        ' model backup is a backup for.')
    UUID = Column(
        Unicode(36),
        doc='The UUID of the morpheme language model that this morpheme'
        ' language model backup is a backup for.')
    name = Column(Unicode(255), doc=MorphemeLanguageModel.name.__doc__)
    description = Column(UnicodeText, doc=MorphemeLanguageModel.description.__doc__)
    corpus = Column(UnicodeText, doc=MorphemeLanguageModel.corpus.__doc__)
    enterer = Column(UnicodeText, doc=MorphemeLanguageModel.enterer.__doc__)
    modifier = Column(UnicodeText, doc=MorphemeLanguageModel.modifier.__doc__)
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime)
    generate_succeeded = Column(Boolean, default=False, doc=MorphemeLanguageModel.generate_succeeded.__doc__)
    generate_message = Column(Unicode(255), doc=MorphemeLanguageModel.generate_message.__doc__)
    generate_attempt = Column(Unicode(36), doc=MorphemeLanguageModel.generate_attempt.__doc__)
    perplexity = Column(Float, default=0.0, doc=MorphemeLanguageModel.perplexity.__doc__)
    perplexity_attempt = Column(Unicode(36), doc=MorphemeLanguageModel.perplexity_attempt.__doc__)
    perplexity_computed = Column(Boolean, default=False, doc=MorphemeLanguageModel.perplexity_computed.__doc__)
    toolkit = Column(Unicode(10), doc=MorphemeLanguageModel.toolkit.__doc__)
    order = Column(Integer, doc=MorphemeLanguageModel.order.__doc__)
    smoothing = Column(Unicode(30), doc=MorphemeLanguageModel.smoothing.__doc__)
    vocabulary_morphology = Column(UnicodeText, doc=MorphemeLanguageModel.vocabulary_morphology.__doc__)
    restricted = Column(Boolean, doc=MorphemeLanguageModel.restricted.__doc__)
    categorial = Column(Boolean, doc=MorphemeLanguageModel.categorial.__doc__)

    def vivify(self, morpheme_language_model_dict):
        """The vivify method gives life to a morpheme language model backup by specifying its
        attributes using the to-be-backed-up morpheme language model (morpheme_language_model_dict)
        The relational attributes of the to-be-backed-up morpheme language model are converted into (truncated) JSON objects.

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
        self.vocabulary_morphology = json.dumps(morpheme_language_model_dict['vocabulary_morphology'])
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

