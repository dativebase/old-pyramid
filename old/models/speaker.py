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

"""Speaker model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now

class Speaker(Base):

    __tablename__ = 'speaker'

    def __repr__(self):
        return '<Speaker (%s)>' % self.id

    id = Column(Integer, Sequence('speaker_seq_id', optional=True), primary_key=True)
    first_name = Column(Unicode(255))
    last_name = Column(Unicode(255))
    dialect = Column(Unicode(255))
    markup_language = Column(Unicode(100))
    page_content = Column(UnicodeText)
    html = Column(UnicodeText)
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)

    def get_dict(self):
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'dialect': self.dialect,
            'markup_language': self.markup_language,
            'page_content': self.page_content,
            'html': self.html,
            'datetime_modified': self.datetime_modified
        }
