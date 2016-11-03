"""ApplicationSettings model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from sqlalchemy.orm import relation
from .meta import Base, now
import logging

log = logging.getLogger(__name__)

def delete_key(dict_, key_):
    """Try to delete the key_ from the dict_; then return the dict_."""
    try:
        del dict_[key_]
    except:
        pass
    return dict_


class ApplicationSettingsUser(Base):

    __tablename__ = 'applicationsettingsuser'

    id = Column(Integer, Sequence('applicationsettingsuser_seq_id',
        optional=True), primary_key=True)
    applicationsettings_id = Column(Integer,
            ForeignKey('applicationsettings.id'))
    user_id = Column(Integer, ForeignKey('user.id'))
    datetime_modified = Column(DateTime, default=now)


class ApplicationSettings(Base):

    __tablename__ = 'applicationsettings'

    def __repr__(self):
        return '<ApplicationSettings (%s)>' % self.id

    id = Column(Integer, Sequence('applicationsettings_seq_id', optional=True),
                primary_key=True)
    object_language_name = Column(Unicode(255))
    object_language_id = Column(Unicode(3))
    metalanguage_name = Column(Unicode(255))
    metalanguage_id = Column(Unicode(3))
    metalanguage_inventory = Column(UnicodeText)
    orthographic_validation = Column(Unicode(7))
    narrow_phonetic_inventory = Column(UnicodeText)
    narrow_phonetic_validation = Column(Unicode(7))
    broad_phonetic_inventory = Column(UnicodeText)
    broad_phonetic_validation = Column(Unicode(7))
    morpheme_break_is_orthographic = Column(Boolean)
    morpheme_break_validation = Column(Unicode(7))
    phonemic_inventory = Column(UnicodeText)
    morpheme_delimiters = Column(Unicode(255))
    punctuation = Column(UnicodeText)
    grammaticalities = Column(Unicode(255))
    storage_orthography_id = Column(Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    storage_orthography = relation('Orthography',
        primaryjoin='ApplicationSettings.storage_orthography_id==Orthography.id')
    input_orthography_id = Column(Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    input_orthography = relation('Orthography',
        primaryjoin='ApplicationSettings.input_orthography_id==Orthography.id')
    output_orthography_id = Column(Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    output_orthography = relation('Orthography',
        primaryjoin='ApplicationSettings.output_orthography_id==Orthography.id')
    datetime_modified = Column(DateTime, default=now)
    unrestricted_users = relation('User', secondary=ApplicationSettingsUser.__table__)

    def get_dict(self):
        """Return a Python dictionary representation of the ApplicationSettings.
        This facilitates JSON-stringification, cf. utils.JSONOLDEncoder.
        Relational data are truncated, e.g., application_settings.get_dict()['storage_orthography']
        is a dict with keys that are a subset of an orthography's attributes.
        """
        return {
            'id': self.id,
            'object_language_name': self.object_language_name,
            'object_language_id': self.object_language_id,
            'metalanguage_name': self.metalanguage_name,
            'metalanguage_id': self.metalanguage_id,
            'metalanguage_inventory': self.metalanguage_inventory,
            'orthographic_validation': self.orthographic_validation,
            'narrow_phonetic_inventory': self.narrow_phonetic_inventory,
            'narrow_phonetic_validation': self.narrow_phonetic_validation,
            'broad_phonetic_inventory': self.broad_phonetic_inventory,
            'broad_phonetic_validation': self.broad_phonetic_validation,
            'morpheme_break_is_orthographic': self.morpheme_break_is_orthographic,
            'morpheme_break_validation': self.morpheme_break_validation,
            'phonemic_inventory': self.phonemic_inventory,
            'morpheme_delimiters': self.morpheme_delimiters,
            'punctuation': self.punctuation,
            'grammaticalities': self.grammaticalities,
            'datetime_modified': self.datetime_modified,
            'storage_orthography': self.get_mini_orthography_dict(self.storage_orthography),
            'input_orthography': self.get_mini_orthography_dict(self.input_orthography),
            'output_orthography': self.get_mini_orthography_dict(self.output_orthography),
            'unrestricted_users': self.get_mini_list(self.unrestricted_users)
        }

