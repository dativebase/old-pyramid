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

"""Language model"""

from sqlalchemy import Column
from sqlalchemy.types import Unicode, DateTime
from .meta import Base, now

class Language(Base):
    """An OLD language is a language in the ISO 639-3 code set."""

    __tablename__ = 'language'

    def __repr__(self):
        return '<Language (%s)>' % self.Id

    Id = Column(
        Unicode(3), primary_key=True,
        doc='A three-character alphabetic unique identifier for a language, as'
        ' specified via the ISO 639-3 standard.')
    Part2B = Column(
        Unicode(3),
        doc='Equivalent ISO 639-2 (three-character) identifier of the'
        ' bibliographic applications code set, if there is one.')
    Part2T = Column(
        Unicode(3),
        doc='Equivalent 639-2 (three-character) identifier of the terminology'
        ' applications code set, if there is one.')
    Part1 = Column(
        Unicode(2),
        doc='Equivalent ISO 639-1 (two-character) identifier, if there is one.')
    Scope = Column(
        Unicode(1),
        doc='One of I(ndividual), M(acrolanguage), or S(pecial). See'
        ' http://www-01.sil.org/iso639-3/scope.asp.')
    Type = Column(
        Unicode(1),
        doc='One of A(ncient), C(onstructed), E(xtinct), H(istorical),'
        ' L(iving), or S(pecial). See http://www-01.sil.org/iso639-3/types.asp.')
    Ref_Name = Column(Unicode(150), doc='Reference language name.')
    Comment = Column(
        Unicode(150), doc='Comment relating to one or more of the columns.')
    datetime_modified = Column(DateTime, default=now)

    def get_dict(self):
        return {
            'Id': self.Id,
            'Part2B': self.Part2B,
            'Part2T': self.Part2T,
            'Part1': self.Part1,
            'Scope': self.Scope,
            'Type': self.Type,
            'Ref_Name': self.Ref_Name,
            'Comment': self.Comment,
            'datetime_modified': self.datetime_modified
        }
