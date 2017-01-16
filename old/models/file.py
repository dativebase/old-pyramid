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

"""File model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, Date, DateTime, Float
from sqlalchemy.orm import relation
from .meta import Base, now

import logging
log = logging.getLogger(__name__)

class FileTag(Base):
    """The file-tag model encodes the many-to-many relationship between
    files and tags.
    """

    __tablename__ = 'filetag'

    id = Column(Integer, Sequence('filetag_seq_id', optional=True), primary_key=True)
    file_id = Column(Integer, ForeignKey('file.id'))
    tag_id = Column(Integer, ForeignKey('tag.id'))
    datetime_modified = Column(DateTime(), default=now)


class File(Base):
    """An OLD file is a digital file such as an audio file, video file, image,
    etc. A file's digital content may be stored on the OLD instance's server or
    it may be hosted elsewhere. A file may also represent a sub-interval of
    another time-based file.

    There are 3 types of file:

    1. Standard files: their content is a file in /files/filename.  These files
       have a filename attribute.
    2. Subinterval-referring A/V files: these refer to another OLD file for
       their content.  These files have a parent_file attribute (as well as start
       and end attributes.)
    3. Externally hosted files: these refer to a file hosted on another server.
       They have a url attribute (and optionally a password attribute as well.)
    """

    __tablename__ = 'file'

    def __repr__(self):
        return "<File (%s)>" % self.id

    id = Column(Integer, Sequence('file_seq_id', optional=True), primary_key=True)
    filename = Column(
        Unicode(255), unique=True,
        doc='The name of an OLD file as it is written to disk.')
    name = Column(
        Unicode(255),
        doc='The (possibly user-supplied) name of an OLD file; relevant for'
        ' externally hosted files or subinterval files.')
    MIME_type = Column(
        Unicode(255),
        doc='The type of the file; technically, this is the MIME (Multipurpose'
        ' Internet Mail Extensions) type or Internet media type.')
    size = Column(Integer, doc='The size of an OLD file in bytes.')
    description = Column(
        UnicodeText,
        doc='A description of an OLD file.')
    date_elicited = Column(
        Date, doc='The date an OLD file was elicited')
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation(
        'User', primaryjoin='File.enterer_id==User.id',
        doc='The person (OLD user) who entered/created the file. This value is'
        ' specified automatically by the OLD.')
    elicitor_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    elicitor = relation(
        'User', primaryjoin='File.elicitor_id==User.id',
        doc='The person (OLD user) elicited (e.g., recorded) the file.')
    speaker_id = Column(Integer, ForeignKey('speaker.id', ondelete='SET NULL'))
    speaker = relation(
        'Speaker',
        doc='The speaker of the content encoded in this file, if relevant.')
    utterance_type = Column(
        Unicode(255),
        doc='If an OLD file represents an utterance, then this value indicates'
        ' whether that utterance is in the object language, the metalanguage, or'
        ' both.')
    tags = relation(
        'Tag', secondary=FileTag.__table__, backref='files',
        doc='The tags associated to a given file. Useful for categorization.')

    # Attributes germane to externally hosted files.
    url = Column(
        Unicode(255),
        doc='The URL where an OLD file’s data are stored. Relevant to'
        ' externally-hosted files.')
    password = Column(Unicode(255),
        doc='The password (if relevant) needed to access an OLD file’s'
        ' externally hosted data.')

    # Attributes germane to subinterval-referencing a/v files.
    parent_file_id = Column(Integer, ForeignKey('file.id', ondelete='SET NULL'))
    parent_file = relation('File', remote_side=[id],
        doc='The audio or video (parent) file that a subinterval-referencing'
        ' OLD file refers to for its file data.')
    start = Column(
        Float,
        doc='The time in the parent file where a subinterval-referencing OLD'
        ' file’s data begins.')
    end = Column(
        Float,
        doc='The time in the parent file where a subinterval-referencing OLD'
        ' file’s data ends.')

    lossy_filename = Column(
        Unicode(255),
        doc='The name given to the reduced-size copy that was made of this'
        ' file.') # .ogg generated from .wav or resized images

    forms_doc = 'The set of forms that an OLD file resource is associated to.'
    collections_doc = (
        'The set of collection resources that an OLD file resource is'
        ' associated to.')

    def get_dict(self):
        """Return a Python dictionary representation of the File.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated.
        """
        return {
            'id': self.id,
            'date_elicited': self.date_elicited,
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'filename': self.filename,
            'name': self.name,
            'lossy_filename': self.lossy_filename,
            'MIME_type': self.MIME_type,
            'size': self.size,
            'description': self.description,
            'utterance_type': self.utterance_type,
            'url': self.url,
            'password': self.password,
            'enterer': self.get_mini_user_dict(self.enterer),
            'elicitor': self.get_mini_user_dict(self.elicitor),
            'speaker': self.get_mini_speaker_dict(self.speaker),
            'tags': self.get_tags_list(self.tags),
            'forms': self.get_forms_list(self.forms),
            'parent_file': self.get_mini_file_dict(self.parent_file),
            'start': self.start,
            'end': self.end
        }
