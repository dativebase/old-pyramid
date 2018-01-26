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

"""Keyboard model: encodes a mapping between JavaScript key codes and Unicode
characters."""

import json

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText
from sqlalchemy.orm import relation

from old.models.meta import Base, now


class Keyboard(Base):

    __tablename__ = 'keyboard'

    def __repr__(self):
        return "<Keyboard (%s)>" % self.id

    id = Column(Integer, Sequence('keyboard_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(255), unique=True)
    description = Column(UnicodeText)
    keyboard = Column(UnicodeText, default=u'{}')

    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='Keyboard.enterer_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='Keyboard.modifier_id==User.id')
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)

    def get_dict(self):
        """Return a Python dictionary representation of the Keyboard.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder. Relational
        data are truncated, e.g., keyboard_dict['elicitor'] is a dict with keys
        for 'id', 'first_name' and 'last_name' (cf. get_mini_user_dict above) and
        lacks keys for other attributes such as 'username',
        'personal_page_content', etc.

        """
        try:
            keyboard = json.loads(self.keyboard)
        except (json.decoder.JSONDecodeError, TypeError):
            keyboard = {}
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'keyboard': keyboard,
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.get_mini_user_dict(self.modifier),
        }
