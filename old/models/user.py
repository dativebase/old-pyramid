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

"""User model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from sqlalchemy.orm import relation
from .meta import Base, now

class UserForm(Base):

    __tablename__ = 'userform'

    id = Column(Integer, Sequence('userform_seq_id', optional=True),
            primary_key=True)
    form_id = Column(Integer, ForeignKey('form.id'))
    user_id = Column(Integer, ForeignKey('user.id'))
    datetime_modified = Column(DateTime, default=now)

class User(Base):

    __tablename__ = 'user'

    def __repr__(self):
        return "<User (%s)>" % self.id

    id = Column(Integer, Sequence('user_seq_id', optional=True),
            primary_key=True)
    username = Column(Unicode(255), unique=True)
    password = Column(Unicode(255))
    salt = Column(Unicode(255))
    first_name = Column(Unicode(255))
    last_name = Column(Unicode(255))
    email = Column(Unicode(255))
    affiliation = Column(Unicode(255))
    role = Column(Unicode(100))
    markup_language = Column(Unicode(100))
    page_content = Column(UnicodeText)
    html = Column(UnicodeText)
    input_orthography_id = Column(Integer, ForeignKey('orthography.id',
        ondelete='SET NULL'))
    input_orthography = relation('Orthography',
        primaryjoin='User.input_orthography_id==Orthography.id')
    output_orthography_id = Column(Integer, ForeignKey('orthography.id',
        ondelete='SET NULL'))
    output_orthography = relation('Orthography',
        primaryjoin='User.output_orthography_id==Orthography.id')
    datetime_modified = Column(DateTime, default=now)
    remembered_forms = relation('Form', secondary=UserForm.__table__,
            backref='memorizers')

    def get_dict(self):
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'affiliation': self.affiliation,
            'role': self.role,
            'markup_language': self.markup_language,
            'page_content': self.page_content,
            'html': self.html,
            'input_orthography': self.get_mini_orthography_dict(self.input_orthography),
            'output_orthography': self.get_mini_orthography_dict(self.output_orthography),
            'datetime_modified': self.datetime_modified,
            'username': self.username
        }

    def get_full_dict(self):
        return self.get_dict()
