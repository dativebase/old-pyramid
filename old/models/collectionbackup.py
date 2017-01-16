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

"""CollectionBackup model

Used to save Collection data that has been updated or deleted.  This is a
non-relational table, because keeping a copy of every single change relationally
seemed like more trouble than it's worth.
"""

import json

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, Date, DateTime
from .meta import Base, now
from .collection import Collection


class CollectionBackup(Base):
    """An OLD collection backup is a copy of the state of a collection at a
    certain point in time. Every time a collection is modified or deleted a
    backup is created first.
    """

    __tablename__ = "collectionbackup"

    def __repr__(self):
        return "<CollectionBackup (%s)>" % self.id

    id = Column(
        Integer, Sequence('collectionbackup_seq_id', optional=True),
        primary_key=True)
    collection_id = Column(
        Integer,
        doc='The id of the collection that this collection backup is a backup'
        ' for.')
    UUID = Column(
        Unicode(36),
        doc='The UUID of the collection that this collection backup is a backup'
        ' for.')
    title = Column(Unicode(255), doc=Collection.title.__doc__)
    type = Column(Unicode(255), doc=Collection.type.__doc__)
    url = Column(Unicode(255), doc=Collection.url.__doc__)
    description = Column(UnicodeText, doc=Collection.description.__doc__)
    markup_language = Column(Unicode(100), doc=Collection.markup_language.__doc__)
    contents = Column(UnicodeText, doc=Collection.contents.__doc__)
    html = Column(UnicodeText, doc=Collection.html.__doc__)
    date_elicited = Column(Date, doc=Collection.date_elicited.__doc__)
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    speaker = Column(UnicodeText, doc=Collection.speaker.__doc__)
    source = Column(UnicodeText, doc=Collection.source.__doc__)
    elicitor = Column(UnicodeText, doc=Collection.elicitor.__doc__)
    enterer = Column(UnicodeText, doc=Collection.enterer.__doc__)
    modifier = Column(UnicodeText, doc=Collection.modifier.__doc__)
    tags = Column(UnicodeText, doc=Collection.tags.__doc__)
    files = Column(UnicodeText, doc=Collection.files.__doc__)
    forms = Column(UnicodeText, doc=Collection.forms_doc)

    def vivify(self, collection_dict):
        """The vivify method gives life to CollectionBackup by specifying its
        attributes using the to-be-backed-up collection as represented in
        ``collection_dict``.  The relational attributes of the backup are
        converted to (truncated) JSON objects.
        """
        self.collection_id = collection_dict['id']
        self.UUID = collection_dict['UUID']
        self.title = collection_dict['title']
        self.type = collection_dict['type']
        self.url = collection_dict['url']
        self.description = collection_dict['description']
        self.markup_language = collection_dict['markup_language']
        self.contents = collection_dict['contents']
        self.html = collection_dict['html']
        self.date_elicited = collection_dict['date_elicited']
        self.datetime_entered = collection_dict['datetime_entered']
        self.datetime_modified = collection_dict['datetime_modified']
        self.source = json.dumps(collection_dict['source'])
        self.speaker = json.dumps(collection_dict['speaker'])
        self.elicitor = json.dumps(collection_dict['elicitor'])
        self.enterer = json.dumps(collection_dict['enterer'])
        self.modifier = json.dumps(collection_dict['modifier'])
        self.tags = json.dumps(collection_dict['tags'])
        self.files = json.dumps(collection_dict['files'])
        self.forms = json.dumps([f['id'] for f in collection_dict['forms']])

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'collection_id': self.collection_id,
            'title': self.title,
            'type': self.type,
            'url': self.url,
            'description': self.description,
            'markup_language': self.markup_language,
            'contents': self.contents,
            'html': self.html,
            'date_elicited': self.date_elicited,
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'speaker': self.json_loads(self.speaker),
            'source': self.json_loads(self.source),
            'elicitor': self.json_loads(self.elicitor),
            'enterer': self.json_loads(self.enterer),
            'modifier': self.json_loads(self.modifier),
            'tags': self.json_loads(self.tags),
            'files': self.json_loads(self.files),
            'forms': self.json_loads(self.forms)
        }
