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

"""Orthography model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from .meta import Base, now

class Orthography(Base):
    """An OLD orthography (alphabet) defines the licit characters (and other
    properties) of a given orthography (i.e., writing system).
    """

    __tablename__ = 'orthography'

    def __repr__(self):
        return '<Orthography (%s)>' % self.id

    id = Column(
        Integer, Sequence('orthography_seq_id', optional=True),
        primary_key=True)
    name = Column(Unicode(255))
    orthography = Column(
        UnicodeText,
        doc='An OLD orthography\'s orthography attribute is a comma-delimited'
        ' sequence of characters that defines the graphemes/polygraphs of the'
        ' orthography.')
    lowercase = Column(
        Boolean, default=False,
        doc='When the lowercase attribute of an OLD orthography is set to'
        ' “true” (the default), then it should be assumed that only lowercase'
        ' graphemes are used in this orthography. When set to “false”, the'
        ' system should try to guess uppercase alternants for the graphemes in'
        ' this orthography.')
    initial_glottal_stops = Column(
        Boolean, default=True,
        doc='When the initial glottal stops attribute of an OLD orthography is'
        ' set to “true” (the default), the system assumes that glottal stops'
        ' are written (overtly) at the beginning of a word in this orthography.'
        ' When set to “false”, the system removes initial glottal stops when'
        ' translating strings into this orthography.')
    datetime_modified = Column(DateTime, default=now)
