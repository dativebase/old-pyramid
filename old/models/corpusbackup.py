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

"""Corpus backup model"""

from sqlalchemy.dialects import mysql
from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from .meta import Base, now
import json

class CorpusBackup(Base):
    """Define the corpus backup model.

    .. note::

        Unlike with the collection backup model, the corpus backup model does
        not backup references to forms.  This is because corpora will generally
        reference many, many forms and it would be inefficient to store all of
        these references as massive (mostly redundant) JSON arrays...

    """

    __tablename__ = 'corpusbackup'

    def __repr__(self):
        return "<CorpusBackup (%s)>" % self.id

    id = Column(Integer, Sequence('corpusbackup_seq_id', optional=True), primary_key=True)
    corpus_id = Column(Integer)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    type = Column(Unicode(255))
    description = Column(UnicodeText)
    content = Column(UnicodeText(length=2**31))
    enterer = Column(UnicodeText)
    modifier = Column(UnicodeText)
    form_search = Column(UnicodeText)
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
    tags = Column(UnicodeText)

    def vivify(self, corpus_dict):
        """The vivify method gives life to a corpus_backup by specifying its
        attributes using the to-be-backed-up corpus as represented in
        ``corpus_dict``.  The relational attributes of the backup are converted
        to (truncated) JSON objects.

        """
        self.UUID = corpus_dict['UUID']
        self.corpus_id = corpus_dict['id']
        self.name = corpus_dict['name']
        self.description = corpus_dict['description']
        self.content = corpus_dict['content']
        self.enterer = json.dumps(corpus_dict['enterer'])
        self.modifier = json.dumps(corpus_dict['modifier'])
        self.form_search = json.dumps(corpus_dict['form_search'])
        self.datetime_entered = corpus_dict['datetime_entered']
        self.datetime_modified = corpus_dict['datetime_modified']
        self.tags = json.dumps(corpus_dict['tags'])

    def get_dict(self):
        """Return a Python dictionary representation of the Corpus.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated, e.g., corpus_dict['enterer'] is a dict with keys
        for 'id', 'first_name' and 'last_name' (cf. get_mini_user_dict) and
        lacks keys for other attributes such as 'username',
        'personal_page_content', etc.

        """

        return {
            'id': self.id,
            'corpus_id': self.corpus_id,
            'UUID': self.UUID,
            'name': self.name,
            'type': self.type,
            'description': self.description,
            'content': self.content,
            'enterer': self.json_loads(self.enterer),
            'modifier': self.json_loads(self.modifier),
            'form_search': self.json_loads(self.form_search),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'tags': self.json_loads(self.tags)
        }
