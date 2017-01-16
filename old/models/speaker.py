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
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now

class Speaker(Base):
    """An OLD speaker is the language speaker (consultant) who is the source of
    a particular form or collection of forms.
    """

    __tablename__ = 'speaker'

    def __repr__(self):
        return '<Speaker (%s)>' % self.id

    id = Column(
        Integer, Sequence('speaker_seq_id', optional=True), primary_key=True)
    first_name = Column(
        Unicode(255),
        doc='The first (given) name of the speaker.')
    last_name = Column(
        Unicode(255),
        doc='The last name (surname) of the speaker.')
    dialect = Column(
        Unicode(255),
        doc='The dialect of a given language spoken by the speaker.')
    markup_language = Column(
        Unicode(100),
        doc='The markup language (“Markdown” or “reStructuredText”)'
        ' that is used to generate HTML from the speaker’s “page content”'
        ' value.')
    page_content = Column(
        UnicodeText,
        doc='The page content is text that defines a speaker’s page; use'
        ' markup conventions from the selected “markup language” in this'
        ' field and the output will be rendered as HTML.')
    html = Column(
        UnicodeText,
        doc='The HTML of an OLD speaker’s page; this is generated from the'
        ' “page content” using the specified “markup language”.')
    datetime_modified = Column(DateTime, default=now)

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
