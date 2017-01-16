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

"""SyntacticCategory model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now

class SyntacticCategory(Base):
    """An OLD syntactic category is the grammatical category assigned to a
    form. It may derive from a syntactic or a morphological analysis.
    """

    __tablename__ = 'syntacticcategory'

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return '<SyntacticCategory (%s)>' % self.id

    id = Column(Integer, Sequence('syntacticcategory_seq_id', optional=True), primary_key=True)
    name = Column(
        Unicode(255),
        doc='The name of a syntactic category is the category itself, e.g.,'
        ' “D” or “S”.')
    type = Column(
        Unicode(60),
        doc='The type of syntactic category; one of “lexical”,'
        ' “phrasal” or “sentential”.')
    description = Column(UnicodeText)
    datetime_modified = Column(DateTime, default=now)

    forms_doc = (
        'The set of OLD form resources that an OLD syntactic category resource'
        ' is associated to.')

    def get_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'description': self.description,
            'datetime_modified': self.datetime_modified
        }
