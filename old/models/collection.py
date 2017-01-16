"""Collection model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, Date, DateTime
from sqlalchemy.orm import relation
from .meta import Base, now

class CollectionFile(Base):
    """The collection-file model encodes the many-to-many relationship between
    collections and files.
    """

    __tablename__ = 'collectionfile'

    id = Column(Integer, Sequence('collectionfile_seq_id', optional=True),
            primary_key=True)
    collection_id = Column(Integer, ForeignKey('collection.id'))
    file_id = Column(Integer, ForeignKey('file.id'))
    datetime_modified = Column(DateTime(), default=now)


class CollectionTag(Base):
    """The collection-tag model encodes the many-to-many relationship between
    collections and tags.
    """

    __tablename__ = 'collectiontag'

    id = Column(Integer, Sequence('collectiontag_seq_id', optional=True),
            primary_key=True)
    collection_id = Column(Integer, ForeignKey('collection.id'))
    tag_id = Column(Integer, ForeignKey('tag.id'))
    datetime_modified = Column(DateTime(), default=now)


class Collection(Base):
    """An OLD collection represents a text, i.e., a document. It is a string of
    text that may contain references to forms in the OLD. The string may also
    contain markup (Markdown or reStructuredText). Using the text, markup,
    and form references, an OLD collection can be represented in various ways
    and exported to various formats, e.g., HTML, LaTeX, PDF.
    """

    __tablename__ = 'collection'

    def __repr__(self):
        return "<Collection (%s)>" % self.id

    id = Column(
        Integer, Sequence('collection_seq_id', optional=True), primary_key=True)
    UUID = Column(Unicode(36))
    title = Column(
        Unicode(255),
        doc='A title for an OLD collection.')
    type = Column(
        Unicode(255),
        doc='The type of an OLD collection, one of “story”,'
        ' “elicitation”, “paper”, “discourse”, or “other”.')
    url = Column(
        Unicode(255),
        doc='The URL path that can be used to navigate to this collection.')
    description = Column(
        UnicodeText, doc='A description of an OLD collection.')
    markup_language = Column(
        Unicode(100),
        doc='The markup language (“Markdown” or “reStructuredText”)'
        ' that is used to markup the text (i.e., the “contents” value) of a'
        ' given OLD collection.')
    contents = Column(
        UnicodeText,
        doc='The string of lightweight markup and references to forms that'
        ' defines the contents of an OLD collection.')
    html = Column(
        UnicodeText,
        doc='The HTML generated from the “contents” value of a given OLD'
        ' collection, using the specified “markup language”.')
    speaker_id = Column(Integer, ForeignKey('speaker.id', ondelete='SET NULL'))
    speaker = relation(
        'Speaker',
        doc='The speaker (consultant) with whom a given OLD collection was'
        ' elicited, if appropriate.')
    source_id = Column(Integer, ForeignKey('source.id', ondelete='SET NULL'))
    source = relation(
        'Source',
        doc='The textual source (e.g., research paper, text collection, book of'
        ' learning materials) from which an OLD collection was drawn, if'
        ' applicable.')
    elicitor_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    elicitor = relation(
        'User', primaryjoin='Collection.elicitor_id==User.id',
        doc='The person who elicited this collection, if appropriate.')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation(
        'User', primaryjoin='Collection.enterer_id==User.id',
        doc='The user who entered/created this collection. This value is'
        ' specified automatically by the OLD.')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation(
        'User', primaryjoin='Collection.modifier_id==User.id',
        doc='The user who made the most recent modification to this collection.'
        ' This value is specified automatically by the OLD.')
    date_elicited = Column(
        Date, doc='The date on which a given collection was elicited')
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    tags = relation(
        'Tag', secondary=CollectionTag.__table__,
        doc='The tags associated to a given collection. Useful for'
        ' categorization.')
    files = relation(
        'File', secondary=CollectionFile.__table__, backref='collections',
        doc='The digital files (e.g., audio, video, image or text) that are'
        ' associated to a given collection.')
    # forms attribute is defined in a relation/backref in the form model
    forms_doc = 'The set of forms that are referenced in an OLD collection.'

    # The contents_unpacked column holds the contents of the collection where all
    # collection references in the contents field are replaced with the contents
    # of the referred-to collections.  These referred-to collections can refer
    # to others in turn.  The forms related to a collection are calculated by
    # gathering the form references from contents_unpacked.  The result of all
    # this is that the contents (and form references) of a collection can be
    # altered by updates to another collection; however, these updates will not
    # propagate until the collection in question is itself updated.
    contents_unpacked = Column(
        UnicodeText,
        doc='The contents_unpacked column holds the contents of the collection'
        ' where all collection references in the contents field are replaced with'
        ' the contents of the referred-to collections. These referred-to'
        ' collections can refer to others in turn. The forms related to a'
        ' collection are calculated by gathering the form references from'
        ' contents_unpacked. The result of all this is that the contents (and'
        ' form references) of a collection can be altered by updates to another'
        ' collection.')

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


