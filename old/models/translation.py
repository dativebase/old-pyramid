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

"""Translation model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now

class Translation(Base):

    __tablename__ = 'translation'

    def __repr__(self):
        return '<Translation (%s)>' % self.id

    id = Column(Integer, Sequence('translation_seq_id', optional=True), primary_key=True)
    transcription = Column(UnicodeText, nullable=False)
    grammaticality = Column(Unicode(255))
    form_id = Column(Integer, ForeignKey('form.id'))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
