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

from base64 import b64decode
import json
import logging
from mimetypes import guess_type
try:
    from magic import Magic
except ImportError:
    pass
import re

from formencode.foreach import ForEach
from formencode.schema import Schema
from formencode.validators import (
    ByteString,
    DateConverter,
    Email,
    FancyValidator,
    Int,
    Invalid,
    Number,
    OneOf,
    Regex,
    String,
    StringBoolean,
    UnicodeString,
    URL,
)
from formencode.variabledecode import NestedVariables
from sqlalchemy.sql import and_

import old.lib.bibtex as bibtex
import old.lib.constants as oldc
import old.lib.helpers as h
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models as old_models


LOGGER = logging.getLogger(__name__)


################################################################################
# Login Schemata
################################################################################


class LoginSchema(Schema):
    """LoginSchema validates that both username and password have been
    entered.
    """
    allow_extra_fields = True
    filter_extra_fields = True
    username = UnicodeString(not_empty=True)
    password = UnicodeString(not_empty=True)


class PasswordResetSchema(Schema):
    """PasswordResetSchema validates that a username has been submitted."""
    allow_extra_fields = True
    filter_extra_fields = True
    username = UnicodeString(not_empty=True)


################################################################################
# Form Schemata
################################################################################


class ValidTranslations(FancyValidator):
    """Validator for translations.  Ensures that there is at least one non-empty
    translation and that all translation grammaticalities are valid.
    """
    messages = {
        'one_translation': 'Please enter one or more translations',
        'invalid_grammaticality': 'At least one submitted translation'
                                  ' grammaticality does not match any of the'
                                  ' available options.'
    }

    accept_iterator = True

    def _to_python(self, value, state):
        def create_translation(dict_):
            translation = old_models.Translation()
            translation.transcription = h.to_single_space(
                h.normalize(dict_['transcription']))
            translation.grammaticality = dict_['grammaticality']
            return translation
        try:
            translations = [t for t in value if t['transcription'].strip()]
            grammaticalities = [t['grammaticality'] for t in value
                                if t['grammaticality'].strip()]
        except (AttributeError, KeyError, TypeError):
            translations = []
            grammaticalities = []
        valid_grammaticalities = state.db.get_grammaticalities()
        bad_translation_grammaticalities = [
            g for g in grammaticalities if g not in valid_grammaticalities]
        if not translations:
            raise Invalid(self.message("one_translation", state), value, state)
        if bad_translation_grammaticalities:
            raise Invalid(
                self.message("invalid_grammaticality", state), value, state)
        return [create_translation(t) for t in translations]


class ValidOrthographicTranscription(UnicodeString):
    """Orthographic transcription validator.  If orthographic transcription
    validation is set to 'Error' in application settings, this validator will
    forbid orthographic transcriptions that are not constructable using the
    storage orthography and the specified punctuation.
    """
    messages = {
        'invalid_transcription': 'The orthographic transcription you have'
                                 ' entered is not valid. Only graphemes from'
                                 ' the specified storage orthography,'
                                 ' punctuation characters and the space'
                                 ' character are permitted.'
    }

    def validate_python(self, value, state):
        transcription = h.to_single_space(h.normalize(value))
        if (not form_is_foreign_word(state.full_dict, state.db) and
                not transcription_is_valid(
                    state.db,
                    transcription,
                    'orthographic_validation',
                    'orthographic')):
            raise Invalid(self.message("invalid_transcription", state),
                          value, state)


class ValidNarrowPhoneticTranscription(UnicodeString):
    """Narrow phonetic transcription validator.  If narrow phonetic
    transcription validation is set to 'Error' in application settings, this
    validator will forbid narrow phonetic transcriptions that are not
    constructable using the narrow phonetic inventory.
    """
    messages = {
        'invalid_transcription': 'The narrow phonetic transcription you have'
                                 ' entered is not valid. Only graphemes from'
                                 ' the specified narrow phonetic inventory and'
                                 ' the space character are permitted.'
    }

    def validate_python(self, value, state):
        transcription = h.to_single_space(h.normalize(value))
        if (not form_is_foreign_word(state.full_dict, state.db) and
                not transcription_is_valid(
                    state.db,
                    transcription,
                    'narrow_phonetic_validation',
                    'narrow_phonetic')):
            raise Invalid(self.message("invalid_transcription", state),
                          value, state)


class ValidBroadPhoneticTranscription(UnicodeString):
    """Broad phonetic transcription validator.  If broad phonetic
    transcription validation is set to 'Error' in application settings, this
    validator will forbid broad phonetic transcriptions that are not
    constructable using the broad phonetic inventory.
    """

    messages = {
        'invalid_transcription': 'The broad phonetic transcription you have'
                                 ' entered is not valid. Only graphemes from'
                                 ' the specified broad phonetic inventory and'
                                 ' the space character are permitted.'
    }

    def validate_python(self, value, state):
        transcription = h.to_single_space(h.normalize(value))
        if (not form_is_foreign_word(state.full_dict, state.db) and
                not transcription_is_valid(
                    state.db,
                    transcription,
                    'broad_phonetic_validation',
                    'broad_phonetic')):
            raise Invalid(self.message("invalid_transcription", state),
                          value, state)


class ValidMorphemeBreakTranscription(UnicodeString):
    """Morpheme break input validator.  If morpheme break validation is set to
    'Error' in application settings, this validator will forbid morpheme break
    input that is not constructable using the relevant grapheme inventory (i.e.,
    either the storage orthography or the phonemic inventory) and the specified
    morpheme delimiters.
    """
    messages = {
        'invalid_transcription': 'The morpheme segmentation you have entered'
                                 ' is not valid. Only graphemes from the'
                                 ' %(inventory)s, the specified morpheme'
                                 ' delimiters and the space character are'
                                 ' permitted.'
    }

    def validate_python(self, value, state):
        transcription = h.to_single_space(h.normalize(value))
        morpheme_break_is_orthographic = (
            state.db.current_app_set.morpheme_break_is_orthographic)
        inventory = 'phonemic inventory'
        if morpheme_break_is_orthographic:
            inventory = 'storage orthography'
        if (not form_is_foreign_word(state.full_dict, state.db) and
                not transcription_is_valid(
                    state.db,
                    transcription,
                    'morpheme_break_validation',
                    'morpheme_break')):
            raise Invalid(
                self.message("invalid_transcription", state,
                             inventory=inventory),
                value, state)


def form_is_foreign_word(form_dict, db):
    """Returns False if the form being entered (as represented by the form_dict)
    is tagged as a foreign word; otherwise return True.
    """
    tag_ids = [h.get_int(id) for id in form_dict.get('tags', [])]
    tag_ids = [id for id in tag_ids if id]
    try:
        foreign_word_tag_id = db.get_foreign_word_tag().id
    except AttributeError:
        foreign_word_tag_id = None
    if foreign_word_tag_id in tag_ids:
        return True
    return False


def transcription_is_valid(db, transcription, validation_name, inventory_name):
    """Returns a boolean indicating whether the transcription is valid according
    to the appropriate Inventory object in the Application Settings meta object.
    The validation_name parameter is the name of the appropriate validation
    attribute of the application settings model object, e.g.,
    'orthographic_validation'.  The inventory_name parameter is the name of an
    attribute of the Application Settings meta object whose value is the
    appropriate Inventory object for the transcription.
    """
    if getattr(db.current_app_set, validation_name, None) == 'Error':
        inv = db.current_app_set.get_transcription_inventory(inventory_name, db)
        return inv.string_is_valid(transcription)
    return True


class ValidGrammaticality(FancyValidator):

    messages = {
        'invalid_grammaticality': 'The grammaticality submitted does not match'
                                  ' any of the available options.'
    }

    def validate_python(self, value, state):
        valid_grammaticalities = state.db.get_grammaticalities()
        if value not in valid_grammaticalities:
            raise Invalid(self.message("invalid_grammaticality", state),
                          value, state)


class ValidOLDModelObject(FancyValidator):
    """Validator for input values that are integer ids (i.e., primary keys) of
    OLD model objects.  Value must be int-able as well as the id of an existing
    OLD of the type specified in the model_name kwarg.  If valid, the model
    object is returned.  Example usage: ValidOLDModelObject(model_name='User').
    """

    messages = {
        'invalid_model': 'There is no %(model_name_eng)s with id %(id)d.',
        'restricted_model':
            'You are not authorized to access the %(model_name_eng)s with id %(id)d.'
    }

    def _to_python(self, value, state):
        if value in ['', None]:
            return None
        else:
            id_ = Int().to_python(value, state)
            model_object = state.db.dbsession.query(
                getattr(old_models, self.model_name)).get(id_)
            if model_object is None:
                model_name_eng=h.camel_case2lower_space(self.model_name)
                raise Invalid(
                    self.message('invalid_model', state, id=id_,
                                 model_name_eng=model_name_eng),
                    value, state)
            else:
                if self.model_name in ('Form', 'File', 'Collection') and \
                getattr(state, 'user', None):
                    unrestricted_users = state.db.get_unrestricted_users()
                    if state.user.is_authorized_to_access_model(
                            model_object, unrestricted_users):
                        return model_object
                    else:
                        model_name_eng=h.camel_case2lower_space(self.model_name)
                        raise Invalid(
                            self.message("restricted_model", state, id=id_,
                                         model_name_eng=model_name_eng),
                            value, state)
                else:
                    return model_object


class AtLeastOneTranscriptionTypeValue(FancyValidator):
    """Every form must have a value for at least one of transcription,
    phonetic_transcription, narrow_phonetic_transcription, or morpheme_break.
    """
    messages = {
        'transcription': 'You must enter a value in at least one of the'
                         ' following fields: transcription, morpheme break,'
                         ' phonetic transcription, or narrow phonetic'
                         ' transcription.'
    }
    def _to_python(self, values, state):
        if (not values['transcription'].strip()) and \
        (not values['phonetic_transcription'].strip()) and \
        (not values['narrow_phonetic_transcription'].strip()) and \
        (not values['morpheme_break'].strip()):
            raise Invalid(self.message('transcription', state), values, state)
        else:
            return values


class FormSchema(Schema):
    """FormSchema is a Schema for validating the data input upon a form
    creation request.
    """
    allow_extra_fields = True
    filter_extra_fields = True

    chained_validators = [AtLeastOneTranscriptionTypeValue()]
    #transcription = ValidOrthographicTranscription(not_empty=True, max=255)
    transcription = ValidOrthographicTranscription(max=510)
    phonetic_transcription = ValidBroadPhoneticTranscription(max=510)
    narrow_phonetic_transcription = ValidNarrowPhoneticTranscription(max=510)
    morpheme_break = ValidMorphemeBreakTranscription(max=510)
    grammaticality = ValidGrammaticality(if_empty='')
    morpheme_gloss = UnicodeString(max=510)
    translations = ValidTranslations(not_empty=True)
    comments = UnicodeString()
    speaker_comments = UnicodeString()
    syntax = UnicodeString(max=1023)
    semantics = UnicodeString(max=1023)
    status = OneOf(oldc.FORM_STATUSES)
    elicitation_method = ValidOLDModelObject(model_name='ElicitationMethod')
    syntactic_category = ValidOLDModelObject(model_name='SyntacticCategory')
    speaker = ValidOLDModelObject(model_name='Speaker')
    elicitor = ValidOLDModelObject(model_name='User')
    verifier = ValidOLDModelObject(model_name='User')
    source = ValidOLDModelObject(model_name='Source')
    tags = ForEach(ValidOLDModelObject(model_name='Tag'))
    files = ForEach(ValidOLDModelObject(model_name='File'))
    date_elicited = DateConverter(month_style='mm/dd/yyyy')


class FormIdsSchema(Schema):
    """Schema used to validate a JSON object of the form {'forms': [1, 2, 3]}
    where value['forms'] can NOT be an empty array.  Used in the remember method
    of controllers.forms.
    """
    allow_extra_fields = True
    filter_extra_fields = True
    forms = ForEach(ValidOLDModelObject(model_name='Form'), not_empty=True)


class FormIdsSchemaNullable(Schema):
    """Schema used to validate a JSON object of the form {'forms': [1, 2, 3]}
    where value['forms'] can be an empty array.  Used in the update method of
    controllers.rememberedforms.
    """
    allow_extra_fields = True
    filter_extra_fields = True
    forms = ForEach(ValidOLDModelObject(model_name='Form'))


################################################################################
# File Schemata
################################################################################


def get_MIME_type_from_contents(contents):
    return Magic(mime=True).from_buffer(contents).replace('application/ogg',
                                                          'audio/ogg')


class ValidBase64EncodedFile(String):
    """Validator for the base64_encoded_file attribute of a file create
    request.
    """
    messages = {
        'invalid_base64_encoded_file': 'The uploaded file must be base64'
                                       ' encoded.'
    }
    def _to_python(self, value, state):
        try:
            return b64decode(value)
        except (TypeError, UnicodeEncodeError):
            raise Invalid(
                self.message('invalid_base64_encoded_file', state),
                value, state)


class ValidFileName(UnicodeString):
    """Ensures that the filename of the file to be uploaded has a valid
    extension, given the allowed file types listed in lib/constants.py.
    """
    messages = {
        'invalid_type': 'The file upload failed because the file type'
                        ' %(MIME_type)s is not allowed.'
    }

    def _to_python(self, value, state):
        MIME_type_from_ext = guess_type(value)[0]
        if MIME_type_from_ext in oldc.ALLOWED_FILE_TYPES:
            return h.clean_and_secure_filename(value)
        else:
            raise Invalid(
                self.message('invalid_type', state,
                             MIME_type=MIME_type_from_ext),
                value, state)


class FileUpdateSchema(Schema):
    """FileUpdateSchema is a Schema for validating the data input upon a file
    update request.
    """
    allow_extra_fields = True
    filter_extra_fields = True
    description = UnicodeString()
    utterance_type = OneOf(oldc.UTTERANCE_TYPES)
    speaker = ValidOLDModelObject(model_name='Speaker')
    elicitor = ValidOLDModelObject(model_name='User')
    tags = ForEach(ValidOLDModelObject(model_name='Tag'))
    forms = ForEach(ValidOLDModelObject(model_name='Form'))
    date_elicited = DateConverter(month_style='mm/dd/yyyy')

class AddMIMETypeToValues(FancyValidator):
    """Guesses the MIME_type based on the file contents and name and sets the
    MIME_type key in values.  If python-magic is installed, the system will guess
    the type from the file contents and an error will be raised if the filename
    extension is inaccurate.
    """
    messages = {
        'mismatched_type': 'The file extension does not match the file\'s true'
                           ' type (%(x)s vs. %(y)s, respectively).'
    }
    def _to_python(self, values, state):
        MIME_type_from_filename = guess_type(values['filename'])[0]
        if 'base64_encoded_file' in values:
            contents = values['base64_encoded_file'][:1024]
        else:
            contents = state.filedata_first_KB
        try:
            MIME_type_from_contents = get_MIME_type_from_contents(contents)
            if MIME_type_from_contents != MIME_type_from_filename:
                raise Invalid(
                    self.message('mismatched_type', state,
                                 x=MIME_type_from_filename,
                                 y=MIME_type_from_contents),
                    values, state)
        except (NameError, KeyError):
            pass    # NameError because Magic is not installed; KeyError
                    # because PlainFile validation will lack a
                    # base64_encoded_file key
        values['MIME_type'] = str(MIME_type_from_filename)
        return values


class FileCreateWithBase64EncodedFiledataSchema(FileUpdateSchema):
    """Schema for validating the data input upon a file create request where a
    base64_encoded_file attribute is present in the JSON request params.  The
    base64_encoded_file and filename attributes can only be specified on the
    create request (i.e., not on the update request).
    """
    chained_validators = [AddMIMETypeToValues()]
    base64_encoded_file = ValidBase64EncodedFile(not_empty=True)
    filename = ValidFileName(not_empty=True, max=255)
    MIME_type = UnicodeString()


class FileCreateWithFiledataSchema(Schema):
    """Schema for validating the data input upon a file create request where the
    Content-Type is 'multipart/form-data'.
    Note the pre-validation NestedVariables call.  This causes certain key-value
    patterns to be transformed to Python data structures.  In this case::

        {'forms-0': 1, 'forms-1': 33, 'tags-0': 2, 'tags-1': 4, 'tags-2': 5}

    becomes

        {'forms': [1, 33], 'tags': [2, 4, 5]}
    """
    allow_extra_fields = True
    filter_extra_fields = True
    pre_validators = [NestedVariables()]
    chained_validators = [AddMIMETypeToValues()]
    filename = ValidFileName(not_empty=True, max=255)
    #filedata_first_KB = String()
    description = UnicodeString()
    utterance_type = OneOf(oldc.UTTERANCE_TYPES)
    speaker = ValidOLDModelObject(model_name='Speaker')
    elicitor = ValidOLDModelObject(model_name='User')
    tags = ForEach(ValidOLDModelObject(model_name='Tag'))
    forms = ForEach(ValidOLDModelObject(model_name='Form'))
    date_elicited = DateConverter(month_style='mm/dd/yyyy')


class ValidAudioVideoFile(FancyValidator):
    """Validator for input values that are integer ids (i.e., primary keys) of
    OLD File objects representing audio or video files.  Note that the
    referenced A/V file must *not* itself be a subinterval-referencing file.
    """
    messages = {
        'invalid_file': 'There is no file with id %(id)d.',
        'restricted_file': 'You are not authorized to access the file with id'
                           ' %(id)d.',
        'not_av': 'File %(id)d is not an audio or a video file.',
        'empty': 'An id corresponding to an existing audio or video file must'
                 ' be provided.',
        'ref_ref': 'The parent file cannot itself be a subinterval-referencing'
                   ' file.'
    }

    def _to_python(self, value, state):
        if value in ['', None]:
            raise Invalid(self.message('empty', state), value, state)
        else:
            id_ = Int().to_python(value, state)
            file_object = state.db.dbsession.query(old_models.File).get(id_)
            if file_object is None:
                raise Invalid(
                    self.message("invalid_file", state, id=id_), value, state)
            else:
                if h.is_audio_video_file(file_object):
                    if file_object.parent_file is None:
                        unrestricted_users = state.db.get_unrestricted_users()
                        if state.user.is_authorized_to_access_model(
                                file_object, unrestricted_users):
                            return file_object
                        else:
                            raise Invalid(
                                self.message("restricted_file", state, id=id_),
                                value, state)
                    else:
                        raise Invalid(
                            self.message('ref_ref', state, id=id_), value, state)
                else:
                    raise Invalid(
                        self.message('not_av', state, id=id_), value, state)


class ValidSubinterval(FancyValidator):
    """Validator ensures that the float/int value of the 'start' key is less
    than the float/int value of the 'end' key.  These values are also converted
    to floats.
    """
    messages = {
        'invalid': 'The start value must be less than the end value.',
        'not_numbers': 'The start and end values must be numbers.'
    }
    def _to_python(self, values, state):
        if (not isinstance(values['start'], (int, float)) or
                not isinstance(values['end'], (int, float))):
            raise Invalid(self.message('not_numbers', state), values, state)
        values['start'] = float(values['start'])
        values['end'] = float(values['end'])
        if values['start'] < values['end']:
            return values
        else:
            raise Invalid(self.message('invalid', state), values, state)


class FileSubintervalReferencingSchema(FileUpdateSchema):
    """Validates input for subinterval-referencing file creation and update
    requests.
    """
    chained_validators = [ValidSubinterval()]
    name = UnicodeString(max=255)
    parent_file = ValidAudioVideoFile(not_empty=True)
    start = Number(not_empty=True)
    end = Number(not_empty=True)


class ValidMIMEType(FancyValidator):
    """Validator ensures that the user-supplied MIME_type value is one of those
    listed in oldc.ALLOWED_FILE_TYPES.
    """
    messages = {'invalid_type': 'The file upload failed because the file type'
                                ' %(MIME_type)s is not allowed.'}

    def validate_python(self, value, state):
        if value not in oldc.ALLOWED_FILE_TYPES:
            raise Invalid(
                self.message('invalid_type', state, MIME_type=value),
                value, state)


class FileExternallyHostedSchema(FileUpdateSchema):
    """Validates input for files whose content is hosted elsewhere."""
    name = UnicodeString(max=255)
    # add check_exists=True if desired
    url = URL(not_empty=True, check_exists=False, add_http=True)
    password = UnicodeString(max=255)
    MIME_type = ValidMIMEType()


################################################################################
# Collection Schemata
################################################################################


class CollectionSchema(Schema):
    """CollectionSchema is a Schema for validating the data input upon
    collection create and update requests.
    """
    allow_extra_fields = True
    filter_extra_fields = True
    title = UnicodeString(max=255, not_empty=True)
    type = OneOf(oldc.COLLECTION_TYPES)
    url = Regex('^[a-zA-Z0-9_/-]{0,255}$')
    description = UnicodeString()
    markup_language = OneOf(oldc.MARKUP_LANGUAGES, if_empty='reStructuredText')
    contents = UnicodeString()
    contents_unpacked = UnicodeString()
    speaker = ValidOLDModelObject(model_name='Speaker')
    source = ValidOLDModelObject(model_name='Source')
    elicitor = ValidOLDModelObject(model_name='User')
    date_elicited = DateConverter(month_style='mm/dd/yyyy')
    tags = ForEach(ValidOLDModelObject(model_name='Tag'))
    files = ForEach(ValidOLDModelObject(model_name='File'))
    # A forms attribute must be created in the controller using the contents
    # attribute prior to validation.
    forms = ForEach(ValidOLDModelObject(model_name='Form'))


################################################################################
# ApplicationSettings Schemata
################################################################################


class GetMorphemeDelimiters(FancyValidator):
    """Remove redundant commas and whitespace from the string representing the
    morpheme delimiters.
    """
    def _to_python(self, value, state):
        value = h.remove_all_white_space(value)
        return ','.join([d for d in value.split(',') if d])


class ApplicationSettingsSchema(Schema):
    """ApplicationSettingsSchema is a Schema for validating the data
    submitted to ApplicationsettingsController
    (controllers/applicationsettings.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    object_language_name = UnicodeString(max=255)
    object_language_id = UnicodeString(max=3)
    metalanguage_name = UnicodeString(max=255)
    metalanguage_id = UnicodeString(max=3)
    metalanguage_inventory = UnicodeString()
    orthographic_validation = OneOf(oldc.VALIDATION_VALUES)
    narrow_phonetic_inventory = UnicodeString()
    narrow_phonetic_validation = OneOf(oldc.VALIDATION_VALUES)
    broad_phonetic_inventory = UnicodeString()
    broad_phonetic_validation = OneOf(oldc.VALIDATION_VALUES)
    morpheme_break_is_orthographic = StringBoolean()
    morpheme_break_validation = OneOf(oldc.VALIDATION_VALUES)
    phonemic_inventory = UnicodeString()
    morpheme_delimiters = GetMorphemeDelimiters(max=255)
    punctuation = UnicodeString()
    grammaticalities = UnicodeString(max=255)
    unrestricted_users = ForEach(ValidOLDModelObject(model_name='User'))
    orthographies = ForEach(ValidOLDModelObject(model_name='Orthography'))
    storage_orthography = ValidOLDModelObject(model_name='Orthography')
    input_orthography = ValidOLDModelObject(model_name='Orthography')
    output_orthography = ValidOLDModelObject(model_name='Orthography')


################################################################################
# Source Validators
################################################################################


class ValidBibTeXEntryType(FancyValidator):
    """Validator for the source model's type field.  Value must be any case
    permutation of BibTeX entry types (cf. bibtex.entry_types).  The value is
    returned all lowercase.
    """
    messages = {
        'invalid_bibtex_entry': '%(submitted_entry)s is not a valid BibTeX'
                                ' entry type'
    }

    def _to_python(self, value, state):
        if value.lower() in bibtex.entry_types.keys():
            return value.lower()
        else:
            raise Invalid(
                self.message('invalid_bibtex_entry', state,
                             submitted_entry=value),
                value, state)


class ValidBibTexKey(FancyValidator):
    """Validator for the source model's key field.  Value must be any unique
    combination of ASCII letters, numerals and symbols (except the comma).  The
    presence of an 'id' attribute on the state object indicates that we are
    updating an existing source and we nuance our check for uniqueness.
    """
    messages = {
        'invalid_bibtex_key_format': 'Source keys can only contain letters,'
                                     ' numerals and symbols (except the comma)',
        'bibtex_key_not_unique': 'The submitted source key is not unique'
    }

    def validate_python(self, value, state):
        valid = ('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX'
                 'YZ!"#$%&\'()*+-./:;<=>?@[\\]^_`{|}~')
        if set(list(value)) - set(list(valid)):
            raise Invalid(self.message('invalid_bibtex_key_format', state),
                          value, state)
        id_ = getattr(state, 'id', None)
        query = state.db.dbsession.query(old_models.Source)
        if (
                (id_ and query.filter(
                    and_(old_models.Source.key==value,
                         old_models.Source.id!=id_)).first()) or
                (not id_ and
                 query.filter(old_models.Source.key==value).first())):
            raise Invalid(
                self.message('bibtex_key_not_unique', state), value, state)


class ValidBibTeXEntry(FancyValidator):
    """Validator for a Source/BibTeX entry based on its type.  This validator is
    run as a formencode "chained validator", i.e., it is run after the validation
    and conversion of the type and key attributes.  It uses the information in
    lib/bibtex.entry_types[type]['required'] to determine which attributes are
    required for which types.
    """
    messages = {'invalid_entry': '%(msg)s'}

    def parse_requirements(self, entry_type):
        """Given a BibTeX entry type, return a tuple (a, b, c) where a is the
        list of required fields, b is the list of disjunctively required fields
        and c is a string expressing the requirements in English.
        """
        def coordinate(list_):
            if len(list_) > 1:
                return '%s and %s' % (', '.join(list_[:-1]), list_[-1])
            elif len(list_) == 1:
                return list_[0]
            return ''
        def conjugate_values(required_fields):
            if len(required_fields) > 1:
                return 'values'
            return 'a value'
        required = bibtex.entry_types.get(entry_type, {}).get('required', [])
        required_fields = [r for r in required if isinstance(r, str)]
        disjunctively_required_fields = [
            r for r in required if isinstance(r, tuple)]
        msg = 'Sources of type %s require %s for %s' % (
            entry_type, conjugate_values(required_fields),
            coordinate(required_fields))
        if disjunctively_required_fields:
            msg = '%s as well as a value for %s' % (
                msg,
                coordinate(['at least one of %s' % coordinate(drf)
                            for drf in disjunctively_required_fields]))
        return required_fields, disjunctively_required_fields, '%s.' % msg

    def get_required_value(self, values, required_field):
        """Try to get a requied value from the values dict; if it's not there,
        try the cross-referenced source model.
        """
        if values.get(required_field):
            return values[required_field]
        elif getattr(values.get('crossref_source'), required_field, None):
            return getattr(values['crossref_source'], required_field)
        else:
            return None

    def validate_python(self, values, state):
        invalid = False
        type_ = values.get('type', '')
        required_fields, disjunctively_required_fields, msg = \
            self.parse_requirements(type_)
        required_fields_values = filter(
            None,
            [self.get_required_value(values, rf) for rf in required_fields])
        if len(required_fields_values) != len(required_fields):
            invalid = True
        else:
            for drf in disjunctively_required_fields:
                dr_values = filter(
                    None, [self.get_required_value(values, rf) for rf in drf])
                if not dr_values:
                    invalid = True
        if invalid:
            raise Invalid(
                self.message('invalid_entry', state, msg=msg), values, state)


class ValidCrossref(FancyValidator):
    """Validator checks that a specified crossref value is valid, i.e., matches
    the key attribute of an existing source.
    """
    messages = {'invalid_crossref': 'There is no source with "%(crossref)s" as its key.'}

    def _to_python(self, values, state):
        if values.get('crossref') in (None, ''):
            values['crossref_source'] = None
            return values
        else:
            crossref = values['crossref']
            crossref_source = state.db.dbsession.query(old_models.Source).\
                filter(old_models.Source.key == crossref).first()
            if crossref_source is None:
                raise Invalid(self.message('invalid_crossref', state, crossref=crossref),
                              values, state)
            else:
                values['crossref_source'] = crossref_source
                return values


class SourceSchema(Schema):
    """SourceSchema is a Schema for validating the data submitted to
    SourceController (controllers/source.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    chained_validators = [ValidCrossref(), ValidBibTeXEntry()]
    # OneOf lib.bibtex.entry_types with any uppercase permutations
    type = ValidBibTeXEntryType(not_empty=True)
    # any combination of letters, numerals and symbols (except commas)
    key = ValidBibTexKey(not_empty=True, unique=True, max=1000)
    file = ValidOLDModelObject(model_name='File')
    address = UnicodeString(max=1000)
    annote = UnicodeString()
    author = UnicodeString(max=255)
    booktitle = UnicodeString(max=255)
    chapter = UnicodeString(max=255)
    crossref = UnicodeString(max=1000)
    edition = UnicodeString(max=255)
    editor = UnicodeString(max=255)
    howpublished = UnicodeString(max=255)
    institution = UnicodeString(max=255)
    journal = UnicodeString(max=255)
    key_field = UnicodeString(max=255)
    month = UnicodeString(max=100)
    note = UnicodeString(max=1000)
    number = UnicodeString(max=100)
    organization = UnicodeString(max=255)
    pages = UnicodeString(max=100)
    publisher = UnicodeString(max=255)
    school = UnicodeString(max=255)
    series = UnicodeString(max=255)
    title = UnicodeString(max=255)
    type_field = UnicodeString(max=255)
    url = URL(add_http=True, max=1000)
    volume = UnicodeString(max=100)
    # The dawn of recorded history to a millenium into the future!
    year = Int(min=-8000, max=3000)
    # Non-standard BibTeX fields
    affiliation = UnicodeString(max=255)
    abstract = UnicodeString(max=1000)
    contents = UnicodeString(max=255)
    copyright = UnicodeString(max=255)
    ISBN = UnicodeString(max=20)
    ISSN = UnicodeString(max=20)
    keywords = UnicodeString(max=255)
    language = UnicodeString(max=255)
    location = UnicodeString(max=255)
    LCCN = UnicodeString(max=20)
    mrnumber = UnicodeString(max=25)
    price = UnicodeString(max=100)
    size = UnicodeString(max=255)


################################################################################
# Secondary Model Validators
################################################################################

class UniqueUnicodeValue(UnicodeString):
    """Validator ensures that the unicode string value is unique in its column.
    The validator must be initialized with model_name and attribute_name
    attributes, e.g., UniqueUnicodeValue(model_name='ElicitationMethod',
    attribute_name='name').  An 'id' attribute on the state object indicates
    that we are updating and should therefore nuance our test for uniqueness.
    """
    messages = {
        'not_unique': 'The submitted value for'
                      ' %(model_name)s.%(attribute_name)s is not unique.'
    }

    def validate_python(self, value, state):
        model_ = getattr(old_models, self.model_name)
        attribute = getattr(model_, self.attribute_name)
        id_ = getattr(state, 'id', None)
        query = state.db.dbsession.query(model_)
        value = h.normalize(value)
        if (
                (id_ and query.filter(
                    and_(attribute==value, getattr(model_, 'id')!=id_)).first())
                or (not id_ and query.filter(attribute==value).first())):
            raise Invalid(
                self.message('not_unique', state, model_name=self.model_name,
                             attribute_name=self.attribute_name),
                value, state)


class ElicitationMethodSchema(Schema):
    """ElicitationMethodSchema is a Schema for validating the data submitted to
    ElicitationmethodsController (controllers/elicitationmethods.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True,
                              model_name='ElicitationMethod',
                              attribute_name='name')
    description = UnicodeString()


class ValidFormQuery(FancyValidator):
    """Validates a form search query using a SQLAQueryBuilder instance. Returns
    the query as JSON.
    """
    accept_iterator = True
    messages = {'query_error': 'The submitted query was invalid'}
    def _to_python(self, value, state):
        try:
            query_builder = SQLAQueryBuilder(state.db.dbsession,
                                             'Form',
                                             settings=state.settings)
            query_builder.get_SQLA_query(value)
        except:
            raise Invalid(self.message('query_error', state), value, state)
        return str(json.dumps(value))


class FormSearchSchema(Schema):
    """FormSearchSchema is a Schema for validating the data submitted to
    FormsearchesController (controllers/formsearches.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True, model_name='FormSearch',
                              attribute_name='name')
    search = ValidFormQuery()
    description = UnicodeString


class OrthographySchema(Schema):
    """OrthographySchema is a Schema for validating the data submitted to
    OrthographyController (controllers/orthography.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True,
                              model_name='Orthography', attribute_name='name')
    orthography = UnicodeString(not_empty=True)
    lowercase = StringBoolean()
    initial_glottal_stops = StringBoolean()


class PageSchema(Schema):
    """PageSchema is a Schema for validating the data submitted to
    PagesController (controllers/pages.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True, model_name='Page',
                              attribute_name='name')
    heading = UnicodeString(max=255)
    markup_language = OneOf(oldc.MARKUP_LANGUAGES, if_empty='reStructuredText')
    content = UnicodeString()
    html = UnicodeString()


class SpeakerSchema(Schema):
    """SpeakerSchema is a Schema for validating the data submitted to
    SpeakersController (controllers/speakers.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    first_name = UnicodeString(max=255, not_empty=True)
    last_name = UnicodeString(max=255, not_empty=True)
    dialect = UnicodeString(max=255)
    page_content = UnicodeString()
    markup_language = OneOf(oldc.MARKUP_LANGUAGES, if_empty='reStructuredText')


class SyntacticCategorySchema(Schema):
    """SyntacticCategorySchema is a Schema for validating the data submitted to
    SyntacticcategoriesController (controllers/syntacticcategories.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True,
                              model_name='SyntacticCategory',
                              attribute_name='name')
    type = OneOf(oldc.SYNTACTIC_CATEGORY_TYPES)
    description = UnicodeString()


class ValidTagName(FancyValidator):
    """Validator ensures that tag names are unique and prevents the names
    'restricted' and 'foreign word' from being updated.
    """
    messages = {
        'unchangeable': 'The names of the restricted and foreign word tags'
                        ' cannot be changed.'
    }
    def validate_python(self, value, state):
        tag = getattr(state, 'tag', None)
        if tag and tag.name in ('restricted', 'foreign word'):
            raise Invalid(self.message('unchangeable', state), value, state)

class TagSchema(Schema):
    """TagSchema is a Schema for validating the data submitted to
    TagsController (controllers/tags.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    chained_validators = [ValidTagName()]
    name = UniqueUnicodeValue(max=255, not_empty=True,
                              model_name='Tag', attribute_name='name')
    description = UnicodeString()

class KeyboardSchema(Schema):
    """KeyboardSchema is a Schema for validating the data submitted to
    KeyboardsController (controllers/keyboards.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True, model_name='Keyboard',
                              attribute_name='name')
    description = UnicodeString()
    keyboard = UnicodeString(not_empty=True)


################################################################################
# User Validators
################################################################################


class ValidUsernameAndPassword(FancyValidator):
    """Validator for the username, password and password_confirm fields.  Unfortunately,
    I do not know how to throw compound errors so these fields may contain multiple
    errors yet only the first encountered will be returned.
    """
    messages = {
        'bad_password': 'The submitted password is invalid; valid passwords'
                        ' contain at least 8 characters and either contain at'
                        ' least one character that is not in the printable'
                        ' ASCII range or else contain at least one symbol, one'
                        ' digit, one uppercase letter and one lowercase'
                        ' letter.',
        'no_password': 'A password is required when creating a new user.',
        'not_confirmed': 'The password and password_confirm values do not'
                         ' match.',
        'nonunique_username': 'The username %(username)s is already taken.',
        'illegal_chars': 'The username %(username)s is invalid; only letters of'
                         ' the English alphabet, numbers and the underscore are'
                         ' permitted.',
        'no_username': 'A username is required when creating a new user.',
        'non_admin_username_update': 'Only administrators can update usernames.'
    }

    def _to_python(self, values, state):
        user_to_update = getattr(state, 'user_to_update', {})
        user_attempting_update = getattr(state, 'user', {})
        id_ = user_to_update.get('id')
        we_are_creating = id_ is None and True or False
        username = values.get('username', None)
        username_is_a_non_empty_string = (
            isinstance(username, str) and username != '')
        password = values.get('password', None)
        password_is_a_non_empty_string = (
            isinstance(password, str) and password != '')
        password_confirm = values.get('password_confirm', None)

        def contains_non_ASCII_chars(password):
            return ([c for c in password if ord(c) not in range(32, 127)] and
                    True or False)

        def is_high_entropy_ASCII(password):
            """Returns True if the password has a lowercase character, an
            uppercase character, a digit and a symbol.
            """
            symbol_patt = re.compile('''[-!$%^&*()_+|~=`{}\[\]:";'<>?,./]''')
            return (
                re.search('[a-z]', password) is not None and
                re.search('[A-Z]', password) is not None and
                re.search('[0-9]', password) is not None and
                symbol_patt.search(password) is not None
            )

        if password_is_a_non_empty_string:
            if (
                    len(password) < 8 or
                    (not contains_non_ASCII_chars(password) and
                     not is_high_entropy_ASCII(password))):
                raise Invalid(self.message('bad_password', state), 'password',
                              state)
            elif password != password_confirm:
                raise Invalid(self.message('not_confirmed', state), 'password',
                              state)
            else:
                values['password'] = password
        else:
            if we_are_creating:
                raise Invalid(self.message('no_password', state), 'password',
                              state)
            else:
                values['password'] = None
        if username_is_a_non_empty_string:
            User = old_models.User
            query = state.db.dbsession.query(User)
            if re.search('[^\w]+', username):
                # Only word characters are allowed
                raise Invalid(self.message('illegal_chars', state,
                                           username=username),
                              'username', state)

            elif (
                    (id_ and query.filter(
                        and_(User.username==username, User.id!=id_)).first()) or
                    (not id_ and query.filter(User.username==username).first())):
                # No duplicate usernames
                raise Invalid(self.message('nonunique_username', state,
                                           username=username),
                              'username', state)
            elif (user_to_update and username != user_to_update['username'] and
                  user_attempting_update['role'] != 'administrator'):
                # Non-admins cannot change their usernames
                raise Invalid(self.message('non_admin_username_update', state,
                                           username=username),
                              'username', state)
            else:
                values['username'] = username
        else:
            if we_are_creating:
                raise Invalid(self.message('no_username', state), 'username',
                              state)
            else:
                values['username'] = None
        return values


class LicitRoleChange(FancyValidator):
    """Ensures that the role is not being changed by a non-administrator."""
    messages = {
        'non_admin_role_update': 'Only administrators can update roles.'
    }

    def validate_python(self, values, state):
        role = values.get('role')
        user_to_update = getattr(state, 'user_to_update', {})
        user_attempting_update = getattr(state, 'user', {})
        if (
                user_to_update and
                user_to_update['role'] != role and
                user_attempting_update['role'] != 'administrator'):
            raise Invalid(self.message('non_admin_role_update', state),
                          'role', state)


class UserSchema(Schema):
    """UserSchema is a Schema for validating the data submitted to
    UsersController (controllers/users.py).
    Note: non-admins should not be able to edit their usernames or roles
    """
    allow_extra_fields = True
    filter_extra_fields = True
    chained_validators = [ValidUsernameAndPassword(), LicitRoleChange()]
    username = UnicodeString(max=255)
    password = UnicodeString(max=255)
    password_confirm = UnicodeString(max=255)
    first_name = UnicodeString(max=255, not_empty=True)
    last_name = UnicodeString(max=255, not_empty=True)
    email = Email(max=255, not_empty=True)
    affiliation = UnicodeString(max=255)
    role = OneOf(oldc.USER_ROLES, not_empty=True)
    markup_language = OneOf(oldc.MARKUP_LANGUAGES, if_empty='reStructuredText')
    page_content = UnicodeString()
    input_orthography = ValidOLDModelObject(model_name='Orthography')
    output_orthography = ValidOLDModelObject(model_name='Orthography')


class PhonologySchema(Schema):
    """PhonologySchema is a Schema for validating the data submitted to
    PhonologiesController (controllers/phonologies.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True, model_name='Phonology',
                              attribute_name='name')
    description = UnicodeString()
    script = UnicodeString()


class MorphophonemicTranscriptionsSchema(Schema):
    """Validates input to ``phonologies/applydown/id``."""
    allow_extra_fields = True
    filter_extra_fields = True
    transcriptions = ForEach(UnicodeString(), not_empty=True)


TranscriptionsSchema = MorphophonemicTranscriptionsSchema


class MorphemeSequencesSchema(Schema):
    """Validates input to ``morphologies/applydown/id``."""
    allow_extra_fields = True
    filter_extra_fields = True
    morpheme_sequences = ForEach(UnicodeString(), not_empty=True)


class ValidFormReferences(FancyValidator):
    messages = {'invalid': 'At least one form id in the content was invalid.'}

    def _to_python(self, values, state):
        if values.get('form_search'):
            values['forms'] = SQLAQueryBuilder(
                state.db.dbsession,
                'Form',
                settings=state.settings).get_SQLA_query(
                    json.loads(values['form_search'].search)).all()
            return values
        form_references = list(set(
            old_models.Corpus.get_form_references(values.get('content', ''))))
        if not form_references:
            values['forms'] = []
            return values
        RDBMS = h.get_RDBMS_name(state.settings)
        # SQLite will raise an SQLA OperationalError if in_() has too many
        # parameters, so we make multiple queries:
        if RDBMS == 'sqlite':
            forms = []
            for form_id_list in h.chunker(form_references, 500):
                forms += state.db.dbsession.query(old_models.Form)\
                    .filter(old_models.Form.id.in_(form_id_list)).all()
        else:
            forms = state.db.dbsession.query(old_models.Form)\
                .filter(old_models.Form.id.in_(form_references)).all()
        if len(forms) != len(form_references):
            raise Invalid(self.message('invalid', state), values, state)
        else:
            values['forms'] = forms
            return values


class CorpusSchema(Schema):
    """CorpusSchema is a Schema for validating the data submitted to
    CorporaController (controllers/corpora.py).
    .. note::
        Corpora can contain **extremely** large collections of forms.  Therefore
        there needs to be some efficiency measures built in around this collection
        as pertains to validation ...  E.g., validation of forms should be avoided
        on updates if it can first be shown that the set of forms referenced has
        not changed ...
    """
    chained_validators = [ValidFormReferences()]
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(
        max=255, not_empty=True, model_name='Corpus', attribute_name='name')
    description = UnicodeString()
    content = UnicodeString()
    tags = ForEach(ValidOLDModelObject(model_name='Tag'))
    form_search = ValidOLDModelObject(model_name='FormSearch')


class CorpusFormatSchema(Schema):
    """Validates the data submitted to ``PUT /corpora/writetofile/id`` and
    ``GET /corpora/servefile/id``.
    """
    allow_extra_fields = True
    filter_extra_fields = True
    format = OneOf(oldc.CORPUS_FORMATS.keys(), not_empty=True)


class MorphologyRules(UnicodeString):
    def _to_python(self, value, state):
        if value:
            value = h.to_single_space(value)
        return value


class RulesOrRulesCorpus(FancyValidator):
    messages = {
        'invalid': 'A value for either rules or rules_corpus must be'
                   ' specified.'
    }

    def _to_python(self, values, state):
        if values.get('rules') or values.get('rules_corpus'):
            return values
        else:
            raise Invalid(self.message('invalid', state), values, state)


class MorphologySchema(Schema):
    """MorphologySchema is a Schema for validating the data submitted to
    MorphologiesController (controllers/morphologies.py).
    """
    chained_validators = [RulesOrRulesCorpus()]
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True, model_name='Morphology',
                              attribute_name='name')
    description = UnicodeString()
    lexicon_corpus = ValidOLDModelObject(model_name='Corpus')
    rules_corpus = ValidOLDModelObject(model_name='Corpus')
    script_type = OneOf(oldc.MORPHOLOGY_SCRIPT_TYPES)
    extract_morphemes_from_rules_corpus = StringBoolean()
    rules = MorphologyRules()
    rich_upper = StringBoolean()
    rich_lower = StringBoolean()
    include_unknowns = StringBoolean()


class CompatibleParserComponents(FancyValidator):
    """Ensures that the phonology, morphology and LM of a parser are compatible.
    """
    messages = {
        'rare_no_match': 'A parser\'s non-categorial LM must have the same'
                         ' rare_delimiter value as its morphology.'
    }

    def _to_python(self, values, state):
        # If a parser's LM is *not* categorial, then its rare_delimiter value
        # must match that of the morphology or probability estimation will not
        # be possible!
        if not values['language_model'].categorial:
            if (values['language_model'].rare_delimiter !=
                    values['morphology'].rare_delimiter):
                raise Invalid(self.message('rare_no_match', state), values,
                              state)
        return values


class MorphologicalParserSchema(Schema):
    """MorphologicalParserSchema is a Schema for validating the data submitted
    to MorphologicalparsersController (controllers/morphologicalparsers.py).
    """
    chained_validators = [CompatibleParserComponents()]
    allow_extra_fields = True
    filter_extra_fields = True
    name = UniqueUnicodeValue(max=255, not_empty=True,
                              model_name='MorphologicalParser',
                              attribute_name='name')
    description = UnicodeString()
    phonology = ValidOLDModelObject(model_name='Phonology')
    morphology = ValidOLDModelObject(model_name='Morphology', not_empty=True)
    language_model = ValidOLDModelObject(model_name='MorphemeLanguageModel',
                                         not_empty=True)


class ValidSmoothing(FancyValidator):
    messages = {
        'invalid smoothing': 'The LM toolkit %(toolkit)s implements no such'
                             ' smoothing algorithm %(smoothing)s.'
    }

    def _to_python(self, values, state):
        if (values.get('smoothing') and values['smoothing'] not in
                oldc.LANGUAGE_MODEL_TOOLKITS[
                    values['toolkit']]['smoothing_algorithms']):
            raise Invalid(self.message('invalid smoothing', state,
                                       toolkit=values['toolkit'],
                                       smoothing=values['smoothing']),
                          values, state)
        else:
            return values


class MorphemeLanguageModelSchema(Schema):
    """MorphemeLanguageModel is a Schema for validating the data submitted to
    MorphemelanguagemodelsController (controllers/morphemelanguagemodels.py).
    """
    allow_extra_fields = True
    filter_extra_fields = True
    chained_validators = [ValidSmoothing()]
    name = UniqueUnicodeValue(max=255, not_empty=True,
                              model_name='MorphemeLanguageModel',
                              attribute_name='name')
    description = UnicodeString()
    corpus = ValidOLDModelObject(model_name='Corpus', not_empty=True)
    vocabulary_morphology = ValidOLDModelObject(model_name='Morphology')
    toolkit = OneOf(oldc.LANGUAGE_MODEL_TOOLKITS.keys(), not_empty=True)
    order = Int(min=2, max=5, if_empty=3)
    smoothing = UnicodeString(max=30)
    categorial = StringBoolean()


class OrderBySchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = False
    order_by_model = UnicodeString()
    order_by_attribute = UnicodeString()
    order_by_direction = OneOf(['asc', 'desc'])
