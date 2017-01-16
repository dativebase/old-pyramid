"""Tag model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime

from .meta import Base, now


class Tag(Base):
    """An OLD tag is a general-purpose resource used to categorize numerous
    other OLD resources. Several OLD resources can be associated to zero or
    many tags.
    """

    __tablename__ = 'tag'

    def __repr__(self):
        return '<Tag (%s)>' % self.id

    id = Column(Integer, Sequence('tag_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(255), unique=True)
    description = Column(UnicodeText)
    datetime_modified = Column(DateTime, default=now)

    forms_doc = (
        'The set of OLD form resources that an OLD tag resource is associated'
        ' to.')
    files_doc = (
        'The set of OLD file resources that an OLD tag resource is associated'
        ' to.')

    def get_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'datetime_modified': self.datetime_modified
        }
