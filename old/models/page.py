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
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now

class Page(Base):
    """An OLD page resources is a web page written using a specified
    lightweight markup language (i.e., Markdown or reStructuredText).
    """

    __tablename__ = 'page'

    def __repr__(self):
        return '<Page (%s)>' % self.id

    id = Column(
        Integer, Sequence('page_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(255), unique=True)
    heading = Column(
        Unicode(255),
        doc='The text of the primary heading of an OLD page.')
    markup_language = Column(
        Unicode(100),
        doc='The markup language (“Markdown” or “reStructuredText”)'
        ' that is used to generate HTML from the “content” value of an OLD'
        ' page.')
    content = Column(
        UnicodeText,
        doc='The content of an OLD page is the text that defines the content of'
        ' the page. It should make use of the markup conventions from the'
        ' selected “markup language”. It will be rendered as HTML.')
    html = Column(
        UnicodeText,
        doc='The HTML attribute of an OLD page is the string of HTML generated'
        ' from the “content” value using the specified “markup language”.')
    datetime_modified = Column(DateTime, default=now)
