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

"""PhonologyBackup model

Used to save phonology data that has been updated or deleted.  This is a
non-relational table, because keeping a copy of every single change relationally
seemed like more trouble than it's worth.
"""

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from .meta import Base, now
import json

class PhonologyBackup(Base):
    """Class for creating OLD phonology_backup models.

    The vivify method takes a phonology and a user object as input and populates
    a number of phonology-like attributes, converting relational attributes to
    JSON objects.

    """

    __tablename__ = "phonologybackup"

    def __repr__(self):
        return "<PhonologyBackup (%s)>" % self.id

    id = Column(Integer, Sequence('phonologybackup_seq_id', optional=True), primary_key=True)
    phonology_id = Column(Integer)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    script = Column(UnicodeText)
    enterer = Column(UnicodeText)
    modifier = Column(UnicodeText)
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    compile_succeeded = Column(Boolean, default=False)
    compile_message = Column(Unicode(255))
    compile_attempt = Column(Unicode(36))

    def vivify(self, phonology_dict):
        """The vivify method gives life to a phonology_backup by specifying its
        attributes using the to-be-backed-up phonology (phonology_dict) and the
        modifier (current user).  The relational attributes of the
        to-be-backed-up phonology are converted into (truncated) JSON objects.

        """

        self.UUID = phonology_dict['UUID']
        self.phonology_id = phonology_dict['id']
        self.name = phonology_dict['name']
        self.description = phonology_dict['description']
        self.script = phonology_dict['script']
        self.enterer = json.dumps(phonology_dict['enterer'])
        self.modifier = json.dumps(phonology_dict['modifier'])
        self.datetime_entered = phonology_dict['datetime_entered']
        self.datetime_modified = phonology_dict['datetime_modified']
        self.compile_succeeded = phonology_dict['compile_succeeded']
        self.compile_message = phonology_dict['compile_message']
        self.compile_attempt = phonology_dict['compile_attempt']

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'phonology_id': self.phonology_id,
            'name': self.name,
            'description': self.description,
            'script': self.script,
            'enterer': self.json_loads(self.enterer),
            'modifier': self.json_loads(self.modifier),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'compile_succeeded': self.compile_succeeded,
            'compile_message': self.compile_message,
            'compile_attempt': self.compile_attempt
        }
