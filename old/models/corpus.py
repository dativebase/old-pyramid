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

"""Corpus model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from sqlalchemy.orm import relation
from .meta import Base, now
import logging
log = logging.getLogger(name=__name__)

class CorpusForm(Base):

    __tablename__ = 'corpusform'

    id = Column(Integer, Sequence('corpusform_seq_id', optional=True),
            primary_key=True)
    corpus_id = Column(Integer, ForeignKey('corpus.id'))
    form_id = Column(Integer, ForeignKey('form.id'))
    datetime_modified = Column(DateTime(), default=now)


class CorpusTag(Base):

    __tablename__ = 'corpustag'

    id = Column(Integer, Sequence('corpustag_seq_id', optional=True),
            primary_key=True)
    corpus_id = Column(Integer, ForeignKey('corpus.id'))
    tag_id = Column(Integer, ForeignKey('tag.id'))
    datetime_modified = Column(DateTime(), default=now)


# Keeper is a unicode filter factory -- taken from The Python Cookbook
class Keeper(object):
    """Filters everything from a unicode string except the characters in
    ``keep``.
    """
    def __init__(self, keep):
        self.keep = set(map(ord, keep))
    def __getitem__(self, n):
        if n not in self.keep:
            return None
        return chr(n)
    def __call__(self, s):
        return str(s).translate(self)


class Corpus(Base):

    __tablename__ = 'corpus'

    def __repr__(self):
        return "<Corpus (%s)>" % self.id

    id = Column(Integer, Sequence('corpus_seq_id', optional=True), primary_key=True)
    UUID = Column(Unicode(36))
    name = Column(Unicode(255))
    description = Column(UnicodeText)
    content = Column(UnicodeText(length=2**31))
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='Corpus.enterer_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='Corpus.modifier_id==User.id')
    form_search_id = Column(Integer, ForeignKey('formsearch.id', ondelete='SET NULL'))
    form_search = relation('FormSearch')
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    tags = relation('Tag', secondary=CorpusTag.__table__)
    forms = relation('Form', secondary=CorpusForm.__table__, backref='corpora')

    # ``files`` attribute holds references to ``CorpusFile`` models, not ``File``
    # models.  This is a one-to-many relation, like form.translations.
    files = relation('CorpusFile', backref='corpus', cascade='all, delete, delete-orphan')

    def get_dict(self):
        """Return a Python dictionary representation of the Corpus.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated, e.g., corpus_dict['elicitor'] is a dict with keys
        for 'id', 'first_name' and 'last_name' (cf. get_mini_user_dict above) and
        lacks keys for other attributes such as 'username',
        'personal_page_content', etc.
        """

        return {
            'id': self.id,
            'UUID': self.UUID,
            'name': self.name,
            'description': self.description,
            'content': self.content,
            'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.get_mini_user_dict(self.modifier),
            'form_search': self.get_mini_form_search_dict(self.form_search),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'tags': self.get_tags_list(self.tags),
            'files': self.get_corpus_files_list(self.files)
        }

    def get_full_dict(self):
        result = self.get_dict()
        result['forms'] = self.get_forms_list(self.forms)
        return result

    makefilter = Keeper

    @classmethod
    def get_int(cls, input_):
        try:
            return int(input_)
        except Exception:
            return None

    @classmethod
    def get_form_references(cls, content):
        """Similar to ``get_ids_of_forms_referenced`` except that references are
        assumed to be comma-delimited strings of digits -- all other text is
        filtered out.
        """
        digits_comma_only = cls.makefilter('1234567890,')
        return filter(None, map(cls.get_int, digits_comma_only(content).split(',')))


class CorpusFile(Base):
    """Represents a corpus' forms written to disk in a certain format."""

    __tablename__ = 'corpusfile'

    def __repr__(self):
        return "<CorpusFile (%s)>" % self.id

    id = Column(Integer, Sequence('corpusfile_seq_id', optional=True), primary_key=True)
    corpus_id = Column(Integer, ForeignKey('corpus.id', ondelete='SET NULL'))
    filename = Column(Unicode(255))
    format = Column(Unicode(255))
    creator_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    creator = relation('User', primaryjoin='CorpusFile.creator_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='CorpusFile.modifier_id==User.id')
    datetime_modified = Column(DateTime, default=now)
    datetime_created = Column(DateTime)
    restricted = Column(Boolean)

    def get_dict(self):
        """Return a Python dictionary representation of the corpus file."""
        return {
            'id': self.id,
            'corpus_id': self.corpus_id,
            'filename': self.filename,
            'format': self.format,
            'creator': self.get_mini_user_dict(self.creator),
            'modifier': self.get_mini_user_dict(self.modifier),
            'datetime_modified': self.datetime_modified,
            'datetime_entered': self.datetime_entered,
            'restricted': self.restricted
        }
