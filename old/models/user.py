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
from old.models import Form, File, Collection


class UserForm(Base):
    """The file-tag model encodes the many-to-many relationship between
    users and their remembered forms.
    """

    __tablename__ = 'userform'

    id = Column(Integer, Sequence('userform_seq_id', optional=True),
            primary_key=True)
    form_id = Column(Integer, ForeignKey('form.id'))
    user_id = Column(Integer, ForeignKey('user.id'))
    datetime_modified = Column(DateTime, default=now)


class User(Base):
    """An OLD user is a person with an account on a given OLD. Users are the
    elicitors, enterers, and modifiers of content on OLDs.
    """

    __tablename__ = 'user'

    def __repr__(self):
        return "<User (%s)>" % self.id

    id = Column(
        Integer, Sequence('user_seq_id', optional=True), primary_key=True)
    username = Column(
        Unicode(255), unique=True,
        doc='An OLD user’s username, a unique identifier within a given OLD.')
    password = Column(
        Unicode(255),
        doc='An OLD user’s password.')
    salt = Column(
        Unicode(255),
        doc='The salt attribute of an OLD user is a randomly-generated string'
        ' used to enhance the security of the user\'s encrypted password.')
    first_name = Column(
        Unicode(255),
        doc='The first (given) name of an OLD user.')
    last_name = Column(
        Unicode(255),
        doc='The last name (surname) of this user.')
    email = Column(
        Unicode(255),
        doc='An OLD user’s email address.')
    affiliation = Column(
        Unicode(255),
        doc='The academic institution, First Nation, museum, etc. that an OLD'
        ' user is affiliated with.')
    role = Column(
        Unicode(100),
        doc='The role of an OLD user determines level of access: one of'
        ' “administrator”, “contributor”, or “viewer”.')
    markup_language = Column(
        Unicode(100),
        doc='The markup language (Markdown or reStructuredText) that will be'
        ' used to generate HTML from an OLD user’s “page content”.')
    page_content = Column(
        UnicodeText,
        doc='An OLD user\'s page content is text that defines the user’s'
        ' page; users may use markup conventions from the selected “markup'
        ' language” in this field and the output will be rendered as HTML.')
    html = Column(
        UnicodeText,
        doc='The HTML of the user’s page; this is generated from the “page'
        ' content” using the specified “markup language”.')

    input_orthography_id = Column(Integer, ForeignKey('orthography.id',
        ondelete='SET NULL'))
    input_orthography = relation(
        'Orthography',
        primaryjoin='User.input_orthography_id==Orthography.id',
        doc='An OLD user\'s input orthography is the orthography (alphabet)'
        ' that they wish to enter transcriptions of the object language in. The'
        ' software should convert these strings to the storage orthography'
        ' transparently.')
    output_orthography_id = Column(Integer, ForeignKey('orthography.id',
        ondelete='SET NULL'))
    output_orthography = relation(
        'Orthography',
        primaryjoin='User.output_orthography_id==Orthography.id',
        doc='An OLD user\'s output orthography is the orthography (alphabet)'
        ' that they wish transcriptions of the object language to be displayed'
        ' in. The software should convert storage orthography strings to this'
        ' orthography transparently.')

    datetime_modified = Column(DateTime, default=now)
    remembered_forms = relation(
        'Form', secondary=UserForm.__table__, backref='memorizers',
        doc='An OLD user\'s remembered forms are a collection of OLD form'
        ' resources that the user has “remembered”. This can be used to give'
        ' persistent clipboard-like functionality to an OLD client.')

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

    def is_authorized_to_access_model(self, model_object, unrestricted_users):
        """Return True if the user is authorized to access the model object.
        Models tagged with the 'restricted' tag are only accessible to
        administrators, their enterers and unrestricted users.
        NOTE: previously named ``user_is_authorized_to_access_model``
        """
        if self.role == 'administrator':
            return True
        if isinstance(model_object, (Form, File, Collection)):
            tags = model_object.tags
            tag_names = [t.name for t in tags]
            enterer_id = model_object.enterer_id
        else:
            model_backup_dict = model_object.get_dict()
            tags = model_backup_dict['tags']
            tag_names = [t['name'] for t in tags]
            enterer_id = model_backup_dict['enterer'].get('id', None)
        return (
            not tags or
            'restricted' not in tag_names or
            self in unrestricted_users or
            self.id == enterer_id
        )
