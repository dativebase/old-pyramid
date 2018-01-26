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

"""Page model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText

from old.models.meta import Base, now


class Page(Base):

    __tablename__ = 'page'

    def __repr__(self):
        return '<Page (%s)>' % self.id

    id = Column(Integer, Sequence('page_seq_id', optional=True),
                primary_key=True)
    name = Column(Unicode(255), unique=True)
    heading = Column(Unicode(255))
    markup_language = Column(Unicode(100))
    content = Column(UnicodeText)
    html = Column(UnicodeText)
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
