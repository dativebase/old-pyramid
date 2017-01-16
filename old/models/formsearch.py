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

"""FormSearch model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from sqlalchemy.orm import relation
from .meta import Base, now
import logging
log = logging.getLogger(__name__)

class FormSearch(Base):
    """A form search is a saved copy of a search that was performed across the
    set of forms in the database.
    """

    __tablename__ = 'formsearch'

    def __repr__(self):
        return '<FormSearch (%s)>' % self.id

    id = Column(
        Integer, Sequence('formsearch_seq_id', optional=True), primary_key=True)
    name = Column(
        Unicode(255),
        doc='A name for the OLD search')
    search = Column(
        UnicodeText,
        doc='The search expression (a JSON string/object) that defines what'
        ' forms are to be returned and their ordering.')
    description = Column(
        UnicodeText,
        doc='A description of the OLD search.')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation(
        'User',
        doc='The person (OLD user) who entered/created the form search. This'
        ' value is specified automatically by the OLD.')
    datetime_modified = Column(DateTime, default=now)

    def get_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'search': self.json_loads(self.search),
            'description': self.description,
            'enterer': self.get_mini_user_dict(self.enterer),
            'datetime_modified': self.datetime_modified
        }
