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
    """An export represents the export of the data in an OLD instance."""

    __tablename__ = 'export'

    def __repr__(self):
        return '<Export (%s)>' % self.id

    id = Column(Integer, Sequence('export_seq_id', optional=True),
                primary_key=True)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255), doc='The name of the export.')
    public = Column(
        Boolean, default=False,
        doc='A public export is made accessible on the Internet for all to'
        ' access. By default, OLD exports are not public. A non-public export is'
        ' accessible only to account holders of the OLD it is a part of.')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation(
        'User', primaryjoin='Export.enterer_id==User.id',
        doc='The OLD user who created the export.')
    datetime_entered = Column(DateTime)
    generate_succeeded = Column(
        Boolean, default=False,
        doc='Indicates whether the attempt to generate the export was'
        ' successful or not.')
    generate_message = Column(
        Unicode(255),
        doc='String that indicates what happened in the attempt to generate the'
        ' export.')
    generate_attempt = Column(
        Unicode(36),
        doc='A UUID value that is updated when the attempt to generate the'
        ' export has ended. A change in this value indicates that the generate'
        ' attempt is over.')

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'name': self.name,
            'enterer': self.get_mini_user_dict(self.enterer),
            'datetime_entered': self.datetime_entered,
            'generate_succeeded': self.generate_succeeded,
            'generate_message': self.generate_message,
            'generate_attempt': self.generate_attempt,
        }

