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
    """The application settings-user model encodes the many-to-many
    relationship between an application settings and its set of unrestricted
    users.
    """

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
    """An OLD application settings is configuration that defines how an OLD
    instance will behave. This is where things like the morpheme delimiter
    closed class is defined and where input validation is configured. The most
    recently created application settings should be considered the current one.
    """

    __tablename__ = 'applicationsettings'

    def __repr__(self):
        return '<ApplicationSettings (%s)>' % self.id

    id = Column(Integer, Sequence('applicationsettings_seq_id', optional=True),
                primary_key=True)
    object_language_name = Column(
        Unicode(255),
        doc='The name of the language that is being documented and analyzed by'
        ' means of this OLD instance. This may be the ISO 639-3 “reference'
        ' name” but this is not required.')
    object_language_id = Column(Unicode(3),
        doc='The three-letter ISO 639-3 identifier for the language that is'
        ' being documented and analyzed by means of this OLD instance.')
    metalanguage_name = Column(
        Unicode(255),
        doc='The name of the language that is being used to translate, document'
        ' and analyze the object language. This may be the ISO 639-3 “reference'
        ' name” but this is not required.')
    metalanguage_id = Column(
        Unicode(3),
        doc='The three-letter ISO 639-3 identifier for the language that is'
        ' being used to translate, document and analyze the object language.')
    metalanguage_inventory = Column(
        UnicodeText,
        doc='A comma-delimited list of graphemes that may be used to specify'
        ' what character sequences should or can be used when writing in the'
        ' metalanguage.')
    orthographic_validation = Column(
        Unicode(7),
        doc='How to validate user input in the “transcription” field of the'
        ' forms in a given OLD. “None” means no validation. “Warning”'
        ' means a warning is generated when a user tries invalid input.'
        ' “Error” means invalid input is forbidden.')
    narrow_phonetic_inventory = Column(
        UnicodeText,
        doc='A comma-delimited list of graphemes that should be used when'
        ' entering data into the narrow phonetic transcription field of a given'
        ' OLD.')
    narrow_phonetic_validation = Column(
        Unicode(7),
        doc='How to validate user input in the “narrow phonetic'
        ' transcription” field.  “None” means no validation.  “Warning”'
        ' means a warning is generated when a user tries invalid input.'
        ' “Error” means invalid input is forbidden.')
    broad_phonetic_inventory = Column(
        UnicodeText,
        doc='A comma-delimited list of graphemes that should be used when'
        ' entering data into the phonetic transcription field.')
    broad_phonetic_validation = Column(
        Unicode(7),
        doc='How to validate user input in the “phonetic transcription”'
        ' field. “None” means no validation. “Warning” means a warning is'
        ' generated when a user tries invalid input. “Error” means invalid'
        ' input is forbidden.')
    morpheme_break_is_orthographic = Column(
        Boolean,
        doc='The morpheme break is orthographic means that the morpheme break'
        ' field should be validated against the storage orthography. If the'
        ' morpheme break is not orthographic, that means that it should be'
        ' validated against the phonemic inventory.')
    morpheme_break_validation = Column(
        Unicode(7),
        doc='How to validate user input in the “morpheme break” field.'
        ' “None” means no validation. “Warning” means a warning is'
        ' generated when a user tries invalid input. “Error” means invalid'
        ' input is forbidden.')
    phonemic_inventory = Column(
        UnicodeText,
        doc='A comma-delimited list of phonemes/graphemes that should be used'
        ' when entering data into the morpheme break field (assuming “morpheme'
        ' break is orthographic” is set to false).')
    morpheme_delimiters = Column(
        Unicode(255),
        doc='A comma-delimited list of delimiter characters that should be used'
        ' to separate morphemes in the morpheme break field and morpheme glosses'
        ' in the morpheme gloss field.')
    punctuation = Column(
        UnicodeText,
        doc='A string of punctuation characters that should define, along with'
        ' the graphemes in the storage orthography, the licit strings in the'
        ' transcription field.')
    grammaticalities = Column(
        Unicode(255),
        doc='A comma-delimited list of characters that will define the options'
        ' in the grammaticality fields. Example: “*,?,#”.')
    storage_orthography_id = Column(
        Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    storage_orthography = relation(
        'Orthography',
        primaryjoin='ApplicationSettings.storage_orthography_id==Orthography.id',
        doc='The orthography that transcription values should be stored in.'
        ' This orthography may affect how orthographic validation works and/or'
        ' how orthography conversion works.')
    input_orthography_id = Column(
        Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    input_orthography = relation(
        'Orthography',
        primaryjoin='ApplicationSettings.input_orthography_id==Orthography.id',
        doc='The orthography that transcription values should be entered in.'
        ' If specified and if different from the storage orthography, then the'
        ' system should convert user input in the input orthography to strings in'
        ' the storage orthography.')
    output_orthography_id = Column(
        Integer, ForeignKey('orthography.id', ondelete='SET NULL'))
    output_orthography = relation(
        'Orthography',
        primaryjoin='ApplicationSettings.output_orthography_id==Orthography.id',
        doc='The orthography that transcription values should be displayed in.'
        ' If specified and if different from the storage orthography, then the'
        ' system should convert stored data in the storage orthography to strings'
        ' in the output orthography.')
    datetime_modified = Column(DateTime, default=now)
    unrestricted_users = relation(
        'User', secondary=ApplicationSettingsUser.__table__,
        doc='A list of users that the OLD server considers to be'
        ' “unrestricted”. These users are able to access data that has been'
        ' tagged with the “restricted” tag.')

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

    def get_transcription_inventory(self, type_, db):
        """Return an ``Inventory`` instance for one of the transcription-type
        attributes of forms, as indicated by ``type_``, which should be one of
        'orthographic', 'broad_phonetic', 'narrow_phonetic', or
        'morpheme_break'. The ``db`` var (a ``DBUtils`` instance) must be
        supplied.
        """
        fwt = db.foreign_word_transcriptions
        attr = '_' + type_ + '_inv'
        inv = getattr(self, attr, None)
        if inv:
            return inv
        if type_ == 'narrow_phonetic':
            setattr(self, attr, Inventory(
                    getattr(fwt, type_) +
                    [' '] +
                    self.narrow_phonetic_inventory.split(',')))
        elif type_ == 'broad_phonetic':
            setattr(self, attr, Inventory(
                    getattr(fwt, type_) +
                    [' '] +
                    self.broad_phonetic_inventory.split(',')))
        elif type_ == 'orthographic':
            setattr(self, attr, Inventory(
                    getattr(fwt, type_) +
                    self.punctuation_list +
                    [' '] +
                    self.storage_orthography_list))
        else:
            if self.morpheme_break_is_orthographic:
                setattr(self, attr, Inventory(
                        getattr(fwt, type_) +
                        self.morpheme_delimiters_list +
                        [' '] +
                        self.storage_orthography_list))
            else:
                setattr(self, attr, Inventory(
                        getattr(fwt, type_) +
                        self.morpheme_delimiters_list +
                        [' '] +
                        self.phonemic_inventory.split(',')))
        return getattr(self, attr)

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
