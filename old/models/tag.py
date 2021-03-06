"""Tag model"""

from sqlalchemy import Column, Sequence
from sqlalchemy.dialects import mysql
from sqlalchemy.types import Integer, Unicode, UnicodeText

from old.models.meta import Base, now


class Tag(Base):

    __tablename__ = 'tag'

    def __repr__(self):
        return '<Tag (%s)>' % self.id

    id = Column(Integer, Sequence('tag_seq_id', optional=True), primary_key=True)
    name = Column(Unicode(255), unique=True)
    description = Column(UnicodeText)
    datetime_modified = Column(mysql.DATETIME(fsp=6), default=now)

    def get_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'datetime_modified': self.datetime_modified
        }
