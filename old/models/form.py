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

"""Form model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, Date, DateTime
from sqlalchemy.orm import relation
from .meta import Base, now


class FormFile(Base):

    __tablename__ = 'formfile'

    id = Column(Integer, Sequence('formfile_seq_id', optional=True), primary_key=True)
    form_id = Column(Integer, ForeignKey('form.id'))
    file_id = Column(Integer, ForeignKey('file.id'))
    datetime_modified = Column(DateTime, default=now)


class FormTag(Base):

    __tablename__ = 'formtag'

    id = Column(Integer, Sequence('formtag_seq_id', optional=True), primary_key=True)
    form_id = Column(Integer, ForeignKey('form.id'))
    tag_id = Column(Integer, ForeignKey('tag.id'))
    datetime_modified = Column(DateTime(), default=now)


class CollectionForm(Base):

    __tablename__ = 'collectionform'

    id = Column(Integer, Sequence('collectionform_seq_id', optional=True), primary_key=True)
    collection_id = Column(Integer, ForeignKey('collection.id'))
    form_id = Column(Integer, ForeignKey('form.id'))
    datetime_modified = Column(DateTime(), default=now)


class Form(Base):

    __tablename__ = "form"

    def __repr__(self):
        return "<Form (%s)>" % self.id

    id = Column(Integer, Sequence('form_seq_id', optional=True), primary_key=True)
    UUID = Column(Unicode(36))
    transcription = Column(Unicode(510), nullable=False)
    phonetic_transcription = Column(Unicode(510))
    narrow_phonetic_transcription = Column(Unicode(510))
    morpheme_break = Column(Unicode(510))
    morpheme_gloss = Column(Unicode(510))
    comments = Column(UnicodeText)
    speaker_comments = Column(UnicodeText)
    grammaticality = Column(Unicode(255))
    date_elicited = Column(Date)
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime, default=now)
    syntactic_category_string = Column(Unicode(510))
    morpheme_break_ids = Column(UnicodeText)
    morpheme_gloss_ids = Column(UnicodeText)
    break_gloss_category = Column(Unicode(1023))
    syntax = Column(Unicode(1023))
    semantics = Column(Unicode(1023))
    status = Column(Unicode(40), default=u'tested')  # u'tested' vs. u'requires testing'
    elicitor_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    elicitor = relation('User', primaryjoin='Form.elicitor_id==User.id')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation('User', primaryjoin='Form.enterer_id==User.id')
    modifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    modifier = relation('User', primaryjoin='Form.modifier_id==User.id')
    verifier_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    verifier = relation('User', primaryjoin='Form.verifier_id==User.id')
    speaker_id = Column(Integer, ForeignKey('speaker.id', ondelete='SET NULL'))
    speaker = relation('Speaker')
    elicitationmethod_id = Column(Integer, ForeignKey('elicitationmethod.id', ondelete='SET NULL'))
    elicitation_method = relation('ElicitationMethod')
    syntacticcategory_id = Column(Integer, ForeignKey('syntacticcategory.id', ondelete='SET NULL'))
    syntactic_category = relation('SyntacticCategory', backref='forms')
    source_id = Column(Integer, ForeignKey('source.id', ondelete='SET NULL'))
    source = relation('Source')
    translations = relation('Translation', backref='form', cascade='all, delete, delete-orphan')
    files = relation('File', secondary=FormFile.__table__, backref='forms')
    collections = relation('Collection', secondary=CollectionForm.__table__, backref='forms')
    tags = relation('Tag', secondary=FormTag.__table__, backref='forms')

    def get_dict(self):
        """Return a Python dictionary representation of the Form.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated, e.g., form_dict['elicitor'] is a dict with keys for
        'id', 'first_name' and 'last_name' (cf. get_mini_user_dict above) and lacks
        keys for other attributes such as 'username', 'personal_page_content', etc.
        """

        return {
            'id': self.id,
            'UUID': self.UUID,
            'transcription': self.transcription,
            'phonetic_transcription': self.phonetic_transcription,
            'narrow_phonetic_transcription': self.narrow_phonetic_transcription,
            'morpheme_break': self.morpheme_break,
            'morpheme_gloss': self.morpheme_gloss,
            'comments': self.comments,
            'speaker_comments': self.speaker_comments,
            'grammaticality': self.grammaticality,
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
            'elicitor': self.get_mini_user_dict(self.elicitor),
            'enterer': self.get_mini_user_dict(self.enterer),
            'modifier': self.get_mini_user_dict(self.modifier),
            'verifier': self.get_mini_user_dict(self.verifier),
            'speaker': self.get_mini_speaker_dict(self.speaker),
            'elicitation_method': self.get_mini_elicitation_method_dict(self.elicitation_method),
            'syntactic_category': self.get_mini_syntactic_category_dict(self.syntactic_category),
            'source': self.get_mini_source_dict(self.source),
            'translations': self.get_translations_list(self.translations),
            'tags': self.get_tags_list(self.tags),
            'files': self.get_files_list(self.files)
        }

    def extract_word_pos_sequences(self, unknown_category, morpheme_splitter,
                                   extract_morphemes=False):
        """Return the unique word-based pos sequences, as well as (possibly)
        the morphemes, implicit in the form.

        :param str unknown_category: the string used in syntactic category
            strings when a morpheme-gloss pair is unknown
        :param morpheme_splitter: callable that splits a strings into its
            morphemes and delimiters
        :param bool extract_morphemes: determines whether we return a list of
            morphemes implicit in the form.
        :returns: 2-tuple: (set of pos/delimiter sequences, list of morphemes
            as (pos, (mb, mg)) tuples).
        """
        if not self.syntactic_category_string:
            return None, None
        pos_sequences = set()
        morphemes = []
        sc_words = self.syntactic_category_string.split()
        mb_words = self.morpheme_break.split()
        mg_words = self.morpheme_gloss.split()
        for sc_word, mb_word, mg_word in zip(sc_words, mb_words, mg_words):
            pos_sequence = tuple(morpheme_splitter(sc_word))
            if unknown_category not in pos_sequence:
                pos_sequences.add(pos_sequence)
                if extract_morphemes:
                    morpheme_sequence = morpheme_splitter(mb_word)[::2]
                    gloss_sequence = morpheme_splitter(mg_word)[::2]
                    for pos, morpheme, gloss in zip(pos_sequence[::2], morpheme_sequence, gloss_sequence):
                        morphemes.append((pos, (morpheme, gloss)))
        return pos_sequences, morphemes

