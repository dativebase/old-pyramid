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

"""ElicitationMethod model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now

class ElicitationMethod(Base):
    """An elicitation method categorizes how a linguistic form was elicited."""

    __tablename__ = 'elicitationmethod'

    def __repr__(self):
        return '<ElicitationMethod (%s)>' % self.id

    id = Column(Integer, Sequence('elicitationmethod_seq_id', optional=True), primary_key=True)
    name = Column(
        Unicode(255),
        doc='A name for the elicitation method. Each elicitation method must'
        ' have a name and it must be unique among elicitation methods.')
    description = Column(
        UnicodeText, doc='A description of the elicitation method.')
    datetime_modified = Column(DateTime, default=now)
