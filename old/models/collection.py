"""Collection model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText, Date
from sqlalchemy.orm import relation
from .meta import Base, now

# pylint: disable=no-member

class CollectionFile(Base):

    __tablename__ = 'collectionfile'

    id = Column(Integer, Sequence('collectionfile_seq_id', optional=True),
                primary_key=True)
    collection_id = Column(Integer, ForeignKey('collection.id'))
    file_id = Column(Integer, ForeignKey('file.id'))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)


class CollectionTag(Base):

    __tablename__ = 'collectiontag'

    id = Column(Integer, Sequence('collectiontag_seq_id', optional=True),
                primary_key=True)
    collection_id = Column(Integer, ForeignKey('collection.id'))
    tag_id = Column(Integer, ForeignKey('tag.id'))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)


class Collection(Base):

    __tablename__ = 'collection'

    def __repr__(self):
        return "<Collection (%s)>" % self.id

    id = Column(Integer, Sequence('collection_seq_id', optional=True), primary_key=True)
    UUID = Column(Unicode(36))
    title = Column(Unicode(255))
    type = Column(Unicode(255))
    url = Column(Unicode(255))
    description = Column(UnicodeText)
    markup_language = Column(Unicode(100))
    contents = Column(UnicodeText)
    html = Column(UnicodeText)
    speaker_id = Column(Integer, ForeignKey('speaker.id', ondelete='SET NULL'))
    speaker = relation('Speaker')
    source_id = Column(Integer, ForeignKey('source.id', ondelete='SET NULL'))
    source = relation('Source')
    elicitor_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    elicitor = relation('User', primaryjoin='Collection.elicitor_id==User.id')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='Collection.enterer_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='Collection.modifier_id==User.id')
    date_elicited = Column(Date)
    datetime_entered = Column(mysql.DATETIME(fsp=6))
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)
    tags = relation('Tag', secondary=CollectionTag.__table__)
    files = relation('File', secondary=CollectionFile.__table__, backref='collections')
    # forms attribute is defined in a relation/backref in the form model

    # The contents_unpacked column holds the contents of the collection where all
    # collection references in the contents field are replaced with the contents
    # of the referred-to collections.  These referred-to collections can refer
    # to others in turn.  The forms related to a collection are calculated by
    # gathering the form references from contents_unpacked.  The result of all
    # this is that the contents (and form references) of a collection can be
    # altered by updates to another collection; however, these updates will not
    # propagate until the collection in question is itself updated.
    contents_unpacked = Column(UnicodeText)

    def get_dict(self):
        """Return a Python dictionary representation of the Collection.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated, e.g., collection_dict['elicitor'] is a dict with keys
        for 'id', 'first_name' and 'last_name' (cf. get_mini_user_dict above) and
        lacks keys for other attributes such as 'username',
        'personal_page_content', etc.
        """

        return {
            'id': self.id,
            'UUID': self.UUID,
            'title': self.title,
            'type': self.type,
            'url': self.url,
            'description': self.description,
            'markup_language': self.markup_language,
            'contents': self.contents,
            'contents_unpacked': self.contents_unpacked,
            'html': self.html,
            'date_elicited': self.date_elicited,
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'speaker': self.get_mini_speaker_dict(self.speaker),
            'source': self.get_mini_source_dict(self.source),
            'elicitor': self.get_mini_user_dict(self.elicitor),
            'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.get_mini_user_dict(self.modifier),
            'tags': self.get_tags_list(self.tags),
            'files': self.get_files_list(self.files)
        }

    def get_full_dict(self):
        result = self.get_dict()
        result['forms'] = self.get_forms_list(self.forms)
        return result
