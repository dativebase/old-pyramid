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

"""FormBackup model

Used to save Form data that has been updated or deleted.  This is a
non-relational table, because keeping a copy of every single change relationally
seemed like more trouble than it's worth.
"""

import json

from sqlalchemy import Column, Sequence
from sqlalchemy.types import Integer, Unicode, UnicodeText, Date, DateTime

from .form import Form
from .meta import Base, now

class FormBackup(Base):
    """An OLD form backup is a copy of the state of a form at a
    certain point in time. Every time a form is modified or deleted a
    backup is created first.

    The vivify method takes a Form and a User object as input and populates a
    number of Form-like attributes, converting relational attributes to JSON
    objects.

    The load method converts the JSON objects into Python Column objects, thus
    allowing the FormBackup to behave more like a Form object.
    """

    __tablename__ = "formbackup"

    def __repr__(self):
        return "<FormBackup (%s)>" % self.id

    id = Column(
        Integer, Sequence('formbackup_seq_id', optional=True), primary_key=True)
    form_id = Column(
        Integer,
        doc='The id of the form that this form backup is a backup for.')
    UUID = Column(
        Unicode(36),
        doc='The UUID of the form that this form backup is a backup for.')
    transcription = Column(Unicode(510), nullable=False, doc=Form.transcription.__doc__)
    phonetic_transcription = Column(Unicode(510), doc=Form.phonetic_transcription.__doc__)
    narrow_phonetic_transcription = Column(Unicode(510), doc=Form.narrow_phonetic_transcription.__doc__)
    morpheme_break = Column(Unicode(510), doc=Form.morpheme_break.__doc__)
    morpheme_gloss = Column(Unicode(510), doc=Form.morpheme_gloss.__doc__)
    comments = Column(UnicodeText, doc=Form.comments.__doc__)
    speaker_comments = Column(UnicodeText, doc=Form.speaker_comments.__doc__)
    grammaticality = Column(Unicode(255), doc=Form.grammaticality.__doc__)
    date_elicited = Column(Date, doc=Form.date_elicited.__doc__)
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime)
    syntactic_category_string = Column(Unicode(510), doc=Form.syntactic_category_string.__doc__)
    morpheme_break_ids = Column(UnicodeText, doc=Form.morpheme_break_ids.__doc__)
    morpheme_gloss_ids = Column(UnicodeText, doc=Form.morpheme_gloss_ids.__doc__)
    break_gloss_category = Column(Unicode(1023), doc=Form.break_gloss_category.__doc__)
    syntax = Column(Unicode(1023), doc=Form.syntax.__doc__)
    semantics = Column(Unicode(1023), doc=Form.semantics.__doc__)
    status = Column(Unicode(40), doc=Form.status.__doc__)
    elicitor = Column(UnicodeText, doc=Form.elicitor.__doc__)
    enterer = Column(UnicodeText, doc=Form.enterer.__doc__)
    verifier = Column(UnicodeText, doc=Form.verifier.__doc__)
    speaker = Column(UnicodeText, doc=Form.speaker.__doc__)
    elicitation_method = Column(UnicodeText, doc=Form.elicitation_method.__doc__)
    syntactic_category = Column(UnicodeText, doc=Form.syntactic_category.__doc__)
    source = Column(UnicodeText, doc=Form.source.__doc__)
    translations = Column(UnicodeText, doc=Form.translations.__doc__)
    tags = Column(UnicodeText, doc=Form.tags.__doc__)
    files = Column(UnicodeText, doc=Form.files.__doc__)
    modifier = Column(UnicodeText, doc=Form.modifier.__doc__)

    def vivify(self, form_dict):
        """The vivify method gives life to FormBackup by specifying its
        attributes using the to-be-backed-up form as represented in
        ``form_dict``.  The relational attributes of the backup are converted to
        (truncated) JSON objects.
        """
        self.UUID = form_dict['UUID']
        self.form_id = form_dict['id']
        self.transcription = form_dict['transcription']
        self.phonetic_transcription = form_dict['phonetic_transcription']
        self.narrow_phonetic_transcription = form_dict['narrow_phonetic_transcription']
        self.morpheme_break = form_dict['morpheme_break']
        self.morpheme_gloss = form_dict['morpheme_gloss']
        self.grammaticality = form_dict['grammaticality']
        self.comments = form_dict['comments']
        self.speaker_comments = form_dict['speaker_comments']
        self.date_elicited = form_dict['date_elicited']
        self.datetime_entered = form_dict['datetime_entered']
        self.datetime_modified = form_dict['datetime_modified']
        self.syntactic_category_string = form_dict['syntactic_category_string']
        self.morpheme_break_ids = json.dumps(form_dict['morpheme_break_ids'])
        self.morpheme_gloss_ids = json.dumps(form_dict['morpheme_gloss_ids'])
        self.break_gloss_category = form_dict['break_gloss_category']
        self.syntax = form_dict['syntax']
        self.semantics = form_dict['semantics']
        self.status = form_dict['status']
        self.elicitation_method = json.dumps(form_dict['elicitation_method'])
        self.syntactic_category = json.dumps(form_dict['syntactic_category'])
        self.source = json.dumps(form_dict['source'])
        self.speaker = json.dumps(form_dict['speaker'])
        self.elicitor = json.dumps(form_dict['elicitor'])
        self.enterer = json.dumps(form_dict['enterer'])
        self.verifier = json.dumps(form_dict['verifier'])
        self.modifier = json.dumps(form_dict['modifier'])
        self.translations = json.dumps(form_dict['translations'])
        self.tags = json.dumps(form_dict['tags'])
        self.files = json.dumps(form_dict['files'])

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'form_id': self.form_id,
            'transcription': self.transcription,
            'phonetic_transcription': self.phonetic_transcription,
            'narrow_phonetic_transcription': self.narrow_phonetic_transcription,
            'morpheme_break': self.morpheme_break,
            'morpheme_gloss': self.morpheme_gloss,
            'grammaticality': self.grammaticality,
            'comments': self.comments,
            'speaker_comments': self.speaker_comments,
            'date_elicited': self.date_elicited,
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'syntactic_category_string': self.syntactic_category_string,
            'morpheme_break_ids': self.json_loads(self.morpheme_break_ids),
            'morpheme_gloss_ids': self.json_loads(self.morpheme_gloss_ids),
            'break_gloss_category': self.break_gloss_category,
            'syntax': self.syntax,
            'semantics': self.semantics,
            'status': self.status,
            'elicitation_method': self.json_loads(self.elicitation_method),
            'syntactic_category': self.json_loads(self.syntactic_category),
            'source': self.json_loads(self.source),
            'speaker': self.json_loads(self.speaker),
            'elicitor': self.json_loads(self.elicitor),
            'enterer': self.json_loads(self.enterer),
            'verifier': self.json_loads(self.verifier),
            'modifier': self.json_loads(self.modifier),
            'translations': self.json_loads(self.translations),
            'tags': self.json_loads(self.tags),
            'files': self.json_loads(self.files)
        }

    def load(self):
        """Convert the JSON objects back into Column objects, thus making the
        FormBackup behave just like a Form object.  Almost.
        """
        if self.elicitation_method:
            elicitation_method = json.loads(self.elicitation_method)
            self.elicitation_method = self.Column()
            self.elicitation_method.id = elicitation_method['id']
            self.elicitation_method.name = elicitation_method['name']
        if self.syntactic_category:
            syntactic_category = json.loads(self.syntactic_category)
            self.syntactic_category = self.Column()
            self.syntactic_category.id = syntactic_category['id']
            self.syntactic_category.name = syntactic_category['name']
        if self.source:
            source = json.loads(self.source)
            self.source = self.Column()
            self.source.id = source['id']
            self.source.author_first_name = source['author_first_name']
            self.source.author_last_name = source['author_last_name']
            self.source.year = source['year']
            self.source.full_reference = source['full_reference']
        if self.speaker:
            speaker = json.loads(self.speaker)
            self.speaker = self.Column()
            self.speaker.id = speaker['id']
            self.speaker.first_name = speaker['first_name']
            self.speaker.last_name = speaker['last_name']
            self.speaker.dialect = speaker['dialect']
        if self.elicitor:
            elicitor = json.loads(self.elicitor)
            self.elicitor = self.Column()
            self.elicitor.id = elicitor['id']
            self.elicitor.first_name = elicitor['first_name']
            self.elicitor.last_name = elicitor['last_name']
        if self.enterer:
            enterer = json.loads(self.enterer)
            self.enterer = self.Column()
            self.enterer.id = enterer['id']
            self.enterer.first_name = enterer['first_name']
            self.enterer.last_name = enterer['last_name']
        if self.verifier:
            verifier = json.loads(self.verifier)
            self.verifier = self.Column()
            self.verifier.id = verifier['id']
            self.verifier.first_name = verifier['first_name']
            self.verifier.last_name = verifier['last_name']
        if self.translations:
            translations = json.loads(self.translations)
            self.translations = []
            for translation_dict in translations:
                translation = self.Column()
                translation.id = translation_dict['id']
                translation.transcription = translation_dict['transcription']
                translation.grammaticality = translation_dict['grammaticality']
                self.translations.append(translation)
        if self.tags:
            tags = json.loads(self.tags)
            self.tags = []
            for tag_dict in tags:
                tag = self.Column()
                tag.id = tag_dict['id']
                tag.name = tag_dict['name']
                self.tags.append(tag)
        if self.files:
            files = json.loads(self.files)
            self.files = []
            for file_dict in files:
                file = self.Column()
                file.id = file_dict['id']
                file.name = file_dict['name']
                file.embedded_file_markup = file_dict['embedded_file_markup']
                file.embedded_file_password = file_dict['embedded_file_password']
                self.files.append(file)
        if self.modifier:
            modifier = json.loads(self.modifier)
            self.modifier = self.Column()
            self.modifier.id = modifier['id']
            self.modifier.first_name = modifier['first_name']
            self.modifier.last_name = modifier['last_name']
