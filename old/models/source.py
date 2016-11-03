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

"""Source model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from sqlalchemy.orm import relation
from .meta import Base, now

import logging
log = logging.getLogger(__name__)

class Source(Base):

    __tablename__ = 'source'

    def __repr__(self):
        return '<Source (%s)>' % self.id

    id = Column(Integer, Sequence('source_seq_id', optional=True), primary_key=True)
    file_id = Column(Integer, ForeignKey('file.id', ondelete='SET NULL'))
    file = relation('File')
    crossref_source_id = Column(Integer, ForeignKey('source.id', ondelete='SET NULL'))
    crossref_source = relation('Source', remote_side=[id])
    datetime_modified = Column(DateTime, default=now)

    # BibTeX data structure
    type = Column(Unicode(20))
    key = Column(Unicode(1000))

    # BibTeX fields
    address = Column(Unicode(1000))
    annote = Column(UnicodeText)
    author = Column(Unicode(255))
    booktitle = Column(Unicode(255))
    chapter = Column(Unicode(255))
    crossref = Column(Unicode(1000))
    edition = Column(Unicode(255))
    editor = Column(Unicode(255))
    howpublished = Column(Unicode(255))
    institution = Column(Unicode(255))
    journal = Column(Unicode(255))
    key_field = Column(Unicode(255))
    month = Column(Unicode(100))
    note = Column(Unicode(1000))
    number = Column(Unicode(100))
    organization = Column(Unicode(255))
    pages = Column(Unicode(100))
    publisher = Column(Unicode(255))
    school = Column(Unicode(255))
    series = Column(Unicode(255))
    title = Column(Unicode(255))
    type_field = Column(Unicode(255))
    url = Column(Unicode(1000))
    volume = Column(Unicode(100))
    year = Column(Integer)

    # Non-standard BibTeX fields
    affiliation = Column(Unicode(255))
    abstract = Column(Unicode(1000))
    contents = Column(Unicode(255))
    copyright = Column(Unicode(255))
    ISBN = Column(Unicode(20))
    ISSN = Column(Unicode(20))
    keywords = Column(Unicode(255))
    language = Column(Unicode(255))
    location = Column(Unicode(255))
    LCCN = Column(Unicode(20))
    mrnumber = Column(Unicode(25))
    price = Column(Unicode(100))
    size = Column(Unicode(255))

    def get_dict(self):
        """Return a Python dictionary representation of the Source.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated, e.g., source_dict['file'] is a dict with keys for
        'name', 'size', etc. (cf. get_mini_user_dict of the model superclass) and
        lacks keys for some attributes.
        """
        source_dict = self.__dict__
        source_dict['file'] = self.get_mini_file_dict(self.file)
        source_dict['crossref_source'] = self.get_mini_source_dict(self.crossref_source)
        return source_dict
