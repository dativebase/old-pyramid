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

"""Morphological parser backup model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from .meta import Base, now
import json

class MorphologicalParserBackup(Base):

    __tablename__ = 'morphologicalparserbackup'

    def __repr__(self):
        return '<MorphologicalParserBackup (%s)>' % self.id

    id = Column(Integer, Sequence('morphologicalparserbackup_seq_id', optional=True), primary_key=True)
    morphologicalparser_id = Column(Integer)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    phonology = Column(UnicodeText)
    morphology = Column(UnicodeText)
    language_model = Column(UnicodeText)
    enterer = Column(UnicodeText)
    modifier = Column(UnicodeText)
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
    compile_succeeded = Column(Boolean, default=False)
    compile_message = Column(Unicode(255))
    compile_attempt = Column(Unicode(36)) # a UUID

    def vivify(self, morphological_parser_dict):
        """The vivify method gives life to a morphology_backup by specifying its
        attributes using the to-be-backed-up morphology (morphological_parser_dict) and the
        modifier (current user).  The relational attributes of the
        to-be-backed-up morphology are converted into (truncated) JSON objects.

        """
        self.UUID = morphological_parser_dict['UUID']
        self.morphologicalparser_id = morphological_parser_dict['id']
        self.name = morphological_parser_dict['name']
        self.description = morphological_parser_dict['description']
        self.phonology = json.dumps(morphological_parser_dict['phonology'])
        self.morphology = json.dumps(morphological_parser_dict['morphology'])
        self.language_model = json.dumps(morphological_parser_dict['language_model'])
        self.enterer = json.dumps(morphological_parser_dict['enterer'])
        self.modifier = json.dumps(morphological_parser_dict['modifier'])
        self.datetime_entered = morphological_parser_dict['datetime_entered']
        self.datetime_modified = morphological_parser_dict['datetime_modified']
        self.compile_succeeded = morphological_parser_dict['compile_succeeded']
        self.compile_message = morphological_parser_dict['compile_message']
        self.compile_attempt = morphological_parser_dict['compile_attempt']

    def get_dict(self):
        return {
            'id': self.id,
            'morphologicalparser_id': self.morphologicalparser_id,
            'UUID': self.UUID,
            'name': self.name,
            #'phonology': self.get_mini_dict_for(self.phonology),
            'phonology': self.json_loads(self.phonology),
            #'morphology': self.get_mini_dict_for(self.morphology),
            'morphology': self.json_loads(self.morphology),
            #'language_model': self.get_mini_dict_for(self.language_model),
            'language_model': self.json_loads(self.language_model),
            'description': self.description,
            'enterer': self.json_loads(self.enterer),
            #'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.json_loads(self.modifier),
            #'modifier': self.get_mini_user_dict(self.modifier),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'compile_succeeded': self.compile_succeeded,
            'compile_message': self.compile_message,
            'compile_attempt': self.compile_attempt
        }

