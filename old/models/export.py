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

"""Export model"""

import codecs
import os
import hashlib
import pickle
from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import (
    Integer,
    Unicode,
    UnicodeText,
    DateTime,
    TIMESTAMP,
    Boolean
)
from sqlalchemy.orm import relation
from .meta import Base, now
import logging

log = logging.getLogger(__name__)

class Export(Base):

    __tablename__ = 'export'

    def __repr__(self):
        return '<Export (%s)>' % self.id

    id = Column(Integer, Sequence('export_seq_id', optional=True),
                primary_key=True)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='Morphology.enterer_id==User.id')
    datetime_entered = Column(DateTime)
    timestamp = Column(TIMESTAMP)
    generate_succeeded = Column(Boolean, default=False)
    generate_message = Column(Unicode(255))
    generate_attempt = Column(Unicode(36)) # a UUID

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'name': self.name,
            'enterer': self.get_mini_user_dict(self.enterer),
            'datetime_entered': self.datetime_entered,
            'timestamp': self.timestamp,
            'generate_succeeded': self.compile_succeeded,
            'generate_message': self.compile_message,
            'generate_attempt': self.compile_attempt,
        }

