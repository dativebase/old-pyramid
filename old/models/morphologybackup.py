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

"""MorphologyBackup model

Used to save morphology data that has been updated or deleted.  This is a
non-relational table, because keeping a copy of every single change relationally
seemed like more trouble than it's worth.
"""

import json
import logging

from sqlalchemy import Column, Sequence
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, Boolean

from old.models.meta import Base, now


LOGGER = logging.getLogger(__name__)


class MorphologyBackup(Base):
    """Class for creating OLD morphology_backup models.

    The vivify method takes a morphology and a user object as input and populates
    a number of morphology-like attributes, converting relational attributes to
    JSON objects.

    """
    # pylint: disable=too-many-instance-attributes

    __tablename__ = "morphologybackup"

    def __repr__(self):
        return "<MorphologyBackup (%s)>" % self.id

    id = Column(Integer, Sequence('morphologybackup_seq_id', optional=True), primary_key=True)
    morphology_id = Column(Integer)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    script_type = Column(Unicode(5))
    lexicon_corpus = Column(UnicodeText)
    rules_corpus = Column(UnicodeText)
    enterer = Column(UnicodeText)
    modifier = Column(UnicodeText)
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
    compile_succeeded = Column(Boolean, default=False)
    compile_message = Column(Unicode(255))
    compile_attempt = Column(Unicode(36))
    generate_attempt = Column(Unicode(36))
    extract_morphemes_from_rules_corpus = Column(Boolean, default=False)
    rules = Column(UnicodeText)
    rich_upper = Column(Boolean, default=False)
    rich_lower = Column(Boolean, default=False)
    include_unknowns = Column(Boolean, default=False)

    def vivify(self, morphology_dict):
        """The vivify method gives life to a morphology_backup by specifying its
        attributes using the to-be-backed-up morphology (morphology_dict) and the
        modifier (current user).  The relational attributes of the
        to-be-backed-up morphology are converted into (truncated) JSON objects.

        """
        self.UUID = morphology_dict['UUID']
        self.morphology_id = morphology_dict['id']
        self.name = morphology_dict['name']
        self.description = morphology_dict['description']
        self.script_type = morphology_dict['script_type']
        self.rules_corpus = json.dumps(morphology_dict['rules_corpus'])
        self.lexicon_corpus = json.dumps(morphology_dict['lexicon_corpus'])
        self.enterer = json.dumps(morphology_dict['enterer'])
        self.modifier = json.dumps(morphology_dict['modifier'])
        self.datetime_entered = morphology_dict['datetime_entered']
        self.datetime_modified = morphology_dict['datetime_modified']
        self.compile_succeeded = morphology_dict['compile_succeeded']
        self.compile_message = morphology_dict['compile_message']
        self.compile_attempt = morphology_dict['compile_attempt']
        self.generate_attempt = morphology_dict['generate_attempt']
        self.extract_morphemes_from_rules_corpus = morphology_dict[
            'extract_morphemes_from_rules_corpus']
        self.rules = morphology_dict['rules']
        self.rich_upper = morphology_dict['rich_upper']
        self.rich_lower = morphology_dict['rich_lower']
        self.include_unknowns = morphology_dict['include_unknowns']

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'morphology_id': self.morphology_id,
            'name': self.name,
            'description': self.description,
            'script_type': self.script_type,
            'rules_corpus': self.json_loads(self.rules_corpus),
            'lexicon_corpus': self.json_loads(self.lexicon_corpus),
            'enterer': self.json_loads(self.enterer),
            'modifier': self.json_loads(self.modifier),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'compile_succeeded': self.compile_succeeded,
            'compile_message': self.compile_message,
            'compile_attempt': self.compile_attempt,
            'generate_attempt': self.generate_attempt,
            'extract_morphemes_from_rules_corpus': self.extract_morphemes_from_rules_corpus,
            'rules': self.rules,
            'rich_upper': self.rich_upper,
            'rich_lower': self.rich_lower,
            'include_unknowns': self.include_unknowns
        }
