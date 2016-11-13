"""ApplicationSettings model"""

import logging
import re

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime, Boolean
from sqlalchemy.orm import relation

from old.lib.utils import esc_RE_meta_chars, get_names_and_code_points
from old.models.meta import Base, now


LOGGER = logging.getLogger(__name__)


class ApplicationSettingsUser(Base):

    __tablename__ = 'applicationsettingsuser'

    id = Column(
        Integer,
        Sequence('applicationsettingsuser_seq_id', optional=True),
        primary_key=True)
    applicationsettings_id = Column(
        Integer, ForeignKey('applicationsettings.id'))
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
    storage_orthography_id = Column(
        Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    storage_orthography = relation(
        'Orthography',
        primaryjoin='ApplicationSettings.storage_orthography_id==Orthography.id')
    input_orthography_id = Column(
        Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    input_orthography = relation(
        'Orthography',
        primaryjoin='ApplicationSettings.input_orthography_id==Orthography.id')
    output_orthography_id = Column(
        Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    output_orthography = relation(
        'Orthography',
        primaryjoin='ApplicationSettings.output_orthography_id==Orthography.id')
    datetime_modified = Column(DateTime, default=now)
    unrestricted_users = relation(
        'User', secondary=ApplicationSettingsUser.__table__)

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

    @property
    def morpheme_delimiters_list(self):
        return self.morpheme_delimiters.split(',')

    @property
    def morpheme_delimiters_inventory(self):
        return Inventory(self.morpheme_delimiters_list)

    @property
    def punctuation_list(self):
        return list(self.punctuation)

    @property
    def punctuation_inventory(self):
        return Inventory(self.punctuation_list)

    @property
    def grammaticalities_list(self):
        grammaticalities = self.grammaticalities.strip()
        if grammaticalities:
            return [''] + grammaticalities.replace(' ', '').split(',')
        return ['']

    @property
    def storage_orthography_list(self):
        if self.storage_orthography and self.storage_orthography.orthography:
            return self.storage_orthography.orthography.split(',')
        return []

    def get_transcription_inventory(self, type_, dbsession):
        """Return an ``Inventory`` instance for one of the transcription-type
        attributes of forms, as indicated by ``type_``, which should be one of
        'orthographic', 'broad_phonetic', 'narrow_phonetic', or
        'morpheme_break'. The ``dbsession`` must be supplied.

        foreign_word_narrow_phonetic_transcriptions, \
        foreign_word_broad_phonetic_transcriptions, \
        foreign_word_orthographic_transcriptions, \
        foreign_word_morphemic_transcriptions = get_foreign_word_transcriptions()

        self.narrow_phonetic_inventory = Inventory(
            foreign_word_narrow_phonetic_transcriptions + [' '] +
            self.application_settings.narrow_phonetic_inventory.split(','))
        self.broad_phonetic_inventory = Inventory(
            foreign_word_broad_phonetic_transcriptions + [' '] +
            self.application_settings.broad_phonetic_inventory.split(','))
        self.orthographic_inventory = Inventory(
            foreign_word_orthographic_transcriptions +
            self.punctuation + [' '] + self.storage_orthography)
        if self.application_settings.morpheme_break_is_orthographic:
            self.morpheme_break_inventory = Inventory(
                foreign_word_morphemic_transcriptions +
                self.morpheme_delimiters + [' '] + self.storage_orthography)
        else:
            self.morpheme_break_inventory = Inventory(
                foreign_word_morphemic_transcriptions +
                self.morpheme_delimiters + [' '] +
                self.application_settings.phonemic_inventory.split(','))
        """
        pass


def _get_regex_validator(input_list):
    """Returns a regex that matches only strings composed of zero or more
    of the graphemes in the inventory (plus the space character).
    """
    disj_patt = '|'.join([esc_RE_meta_chars(g) for g in input_list])
    return '^(%s)*$' % disj_patt


class Inventory:
    """An inventory is a set of graphemes/polygraphs/characters. Initialization
    requires a list.
    """
    def __init__(self, input_list):
        self.input_list = input_list
        self.inventory_with_unicode_metadata = [
            get_names_and_code_points(g) for g in self.input_list]
        self.regex_validator = _get_regex_validator(input_list)
        self.compiled_regex_validator = re.compile(self.regex_validator)

    def get_input_list(self):
        return self.input_list

    def get_regex_validator(self):
        return self.regex_validator

    def get_non_matching_substrings(self, string):
        """Return a list of substrings of string that are not constructable
        using the inventory.  This is useful for showing invalid substrings.
        """
        regex = '|'.join([esc_RE_meta_chars(g) for g in self.input_list])
        regex = '(%s)+' % regex
        patt = re.compile(regex)
        list_ = patt.split(string)
        non_matching_substrings = [
            esc_RE_meta_chars(x) for x in list_[::2] if x]
        return non_matching_substrings

    def string_is_valid(self, string):
        """Return False if string cannot be generated by concatenating the
        elements of the orthography; otherwise, return True.
        """
        if self.compiled_regex_validator.match(string):
            return True
        return False
