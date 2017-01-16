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

"""Source model"""

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import Integer, Unicode, UnicodeText, DateTime
from sqlalchemy.orm import relation
from .meta import Base, now

import logging
log = logging.getLogger(__name__)

class Source(Base):
    """An OLD source is a textual source for a piece of data, i.e., a research
    paper, dictionary, grammar or some other published material. The schema of
    an OLD source is that of a BibTeX entry.
    """

    __tablename__ = 'source'

    def __repr__(self):
        return '<Source (%s)>' % self.id

    id = Column(
        Integer, Sequence('source_seq_id', optional=True), primary_key=True)
    file_id = Column(Integer, ForeignKey('file.id', ondelete='SET NULL'))
    file = relation(
        'File',
        doc='An OLD source\'s file is an OLD file resource (e.g., a PDF)'
        ' containing a digital representation of an OLD source resource.')
    crossref_source_id = Column(
        Integer, ForeignKey('source.id', ondelete='SET NULL'))
    crossref_source = relation(
        'Source', remote_side=[id],
        doc='An OLD source\'s source crossref source attribute is another OLD'
        ' source for cross-referencing. That is, the crossref source supplies'
        ' default values for the missing values of any OLD source that'
        ' cross-references it.')
    datetime_modified = Column(DateTime, default=now)

    # BibTeX data structure
    type = Column(
        Unicode(20),
        doc='The BibTeX entry type of a source, e.g., “article”,'
        ' “book”, etc. A valid type value is obligatory for all source'
        ' models. The chosen type value will determine which other attributes'
        ' must also possess non-empty values.')
    key = Column(
        Unicode(1000),
        doc='The BibTeX key for a source; i.e., the unique string used to'
        ' unambiguously identify a source within a bibliography. E.g.,'
        ' “chomsky57”.')

    # BibTeX fields
    address = Column(Unicode(1000),
        doc='Usually the address of the publisher or other type of institution.')
    annote = Column(UnicodeText,
        doc='An annotation. It is not used by the standard bibliography styles,'
        ' but may be used by others that produce an annotated bibliography.')
    author = Column(Unicode(255),
        doc='The name(s) of the author(s), in the format described in Kopka and'
        ' Daly (2004), i.e., either Given Names Surname or Surname, Given Names.'
        ' For multiple authors, use the formats just specified and separate each'
        ' such formatted name by the word “and”.')
    booktitle = Column(
        Unicode(255),
        doc='Title of a book, part of which is being cited. See Kopka and Daly'
        ' (2004) for details on how to type titles. For book entries, use the'
        ' title field instead.')
    chapter = Column(
        Unicode(255),
        doc='A chapter (or section or whatever) number.')
    crossref = Column(
        Unicode(1000),
        doc='The “key” value of another source to be cross-referenced. Any'
        ' attribute values that are missing from the source model are inherited'
        ' from the source cross-referenced via this attribute.')
    edition = Column(
        Unicode(255),
        doc='The edition of a book—for example, “Second”. This should be'
        ' an ordinal, and should have the first letter capitalized, as shown'
        ' here; the standard styles convert to lower case when necessary.')
    editor = Column(
        Unicode(255),
        doc='Name(s) of editor(s), typed as indicated in Kopka and Daly (2004).'
        ' At its most basic, this means either as Given Names Surname or Surname,'
        ' Given Names and using “and” to separate multiple editor names. If'
        ' there is also a value for the author attribute, then the editor'
        ' attribute gives the editor of the book or collection in which the'
        ' reference appears.')
    howpublished = Column(
        Unicode(255),
        doc='How something has been published. The first word should be'
        ' capitalized.')
    institution = Column(
        Unicode(255),
        doc='The sponsoring institution of a technical report.')
    journal = Column(
        Unicode(255),
        doc='A journal name. Abbreviations are provided for many journals.')
    key_field = Column(
        Unicode(255),
        doc='Used for alphabetizing, cross referencing, and creating a label'
        ' when the author information is missing. This field should not be'
        ' confused with the source’s key attribute.')
    month = Column(
        Unicode(100),
        doc='The month in which the work was published or, for an unpublished'
        ' work, in which it was written.')
    note = Column(
        Unicode(1000),
        doc='Any additional information that can help the reader. The first'
        ' word should be capitalized.')
    number = Column(
        Unicode(100),
        doc='The number of a journal, magazine, technical report, or of a work'
        ' in a series. An issue of a journal or magazine is usually identified by'
        ' its volume and number; the organization that issues a technical report'
        ' usually gives it a number; and sometimes books are given numbers in a'
        ' named series.')
    organization = Column(
        Unicode(255),
        doc='The organization that sponsors a conference or that publishes a'
        ' manual.')
    pages = Column(
        Unicode(100),
        doc='One or more page numbers or range of numbers, such as 42–111 or'
        ' 7,41,73–97 or 43+ (the “+” in this last example indicates pages'
        ' following that don’t form a simple range).')
    publisher = Column(
        Unicode(255),
        doc='The publisher’s name.')
    school = Column(
        Unicode(255),
        doc='The name of the school where a thesis was written.')
    series = Column(
        Unicode(255),
        doc='The name of a series or set of books. When citing an entire book,'
        ' the title attribute gives its title and an optional series attribute'
        ' gives the name of a series or multi-volume set in which the book is'
        ' published.')
    title = Column(
        Unicode(255),
        doc='The work’s title, typed as explained in Kopka and Daly (2004).')
    type_field = Column(
        Unicode(255),
        doc='The type of a technical report—for example, “Research Note”.')
    url = Column(
        Unicode(1000),
        doc='The universal resource locator for online documents; this is not'
        ' standard but supplied by more modern bibliography styles.')
    volume = Column(
        Unicode(100),
        doc='The volume of a journal or multi-volume book.')
    year = Column(
        Integer,
        doc='The year of publication or, for an unpublished work, the year it'
        ' was written. Generally it should consist of four numerals, such as'
        ' 1984.')

    # Non-standard BibTeX fields
    affiliation = Column(
        Unicode(255),
        doc='The author’s affiliation.')
    abstract = Column(
        Unicode(1000),
        doc='An abstract of the work.')
    contents = Column(
        Unicode(255),
        doc='A table of contents.')
    copyright = Column(
        Unicode(255),
        doc='Copyright information.')
    ISBN = Column(
        Unicode(20),
        doc='The International Standard Book Number.')
    ISSN = Column(
        Unicode(20),
        doc='The International Standard Serial Number. Used to identify a'
        ' journal.')
    keywords = Column(
        Unicode(255),
        doc='Key words used for searching or possibly for annotation.')
    language = Column(
        Unicode(255),
        doc='The language the document is in.')
    location = Column(
        Unicode(255),
        doc='A location associated with the entry, such as the city in which a'
        ' conference took place.')
    LCCN = Column(
        Unicode(20),
        doc='The Library of Congress Call Number.')
    mrnumber = Column(
        Unicode(25),
        doc='The Mathematical Reviews number.')
    price = Column(
        Unicode(100),
        doc='The price of the document.')
    size = Column(
        Unicode(255),
        doc='The physical dimensions of a work.')

    def get_dict(self):
        """Return a Python dictionary representation of the Source.  This
        facilitates JSON-stringification, cf. utils.JSONOLDEncoder.  Relational
        data are truncated, e.g., source_dict['file'] is a dict with keys for
        'name', 'size', etc. (cf. get_mini_user_dict of the model superclass) and
        lacks keys for some attributes.
        """
        source_dict = self.__dict__.copy()
        if source_dict.get('_sa_instance_state'):
            del source_dict['_sa_instance_state']
        source_dict['file'] = self.get_mini_file_dict(self.file)
        source_dict['crossref_source'] = self.get_mini_source_dict(self.crossref_source)
        return source_dict
