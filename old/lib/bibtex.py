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

"""bibtex.py encodes and describes the BibTeX specification (see Kopka & Daly,
2004 for details).  Useful for validating OLD source input since the data
structure for OLD sources is the BibTeX data structure.

Use Pybtex (http://pybtex.sourceforge.net/manual.html) to parse BibTeX files if
need be:

from io import StringIO
from pybtex.database.input.bibtex import Parser

e1 = '''
@BOOK{knuth:86a,
  AUTHOR = "Donald E. Knuth",
  TITLE = {The \TeX{}book},
  EDITION = "third",
  PUBLISHER = "Addison--Wesley",
  ADDRESS = {Reading, Massachusetts},
  YEAR = 1986
}
'''.strip()

parser = Parser()
bib_data = parser.parse_stream(StringIO(e1))
knuth86a = parser.data.entries['knuth:86a']
unicode(knuth86a.persons['author'][0])
u'Knuth, Donald E.'

"""


# Entry types.
ENTRY_TYPES = {
    'article': {
        'description': 'An article from a journal or magazine.',
        'required': ('author', 'title', 'journal', 'year'),
        'optional': ('volume', 'number', 'pages', 'month', 'note')
    },
    'book': {
        'description': 'A book with an explicit publisher.',
        'required': (('author', 'editor'), 'title', 'publisher', 'year'),
        'optional': (('volume', 'number'), 'series', 'address', 'edition',
                     'month', 'note')
    },
    'booklet': {
        'description': 'A work that is printed and bound, but without a named'
                       ' publisher or sponsoring institution.',
        'required': ('title',),
        'optional': ('author', 'howpublished', 'address', 'month', 'year',
                     'note')
    },
    'conference': {
        'description': 'The same as inproceedings, included for Scribe'
                       ' compatibility.',
        'required': ('author', 'title', 'booktitle', 'year'),
        'optional': ('editor', ('volume', 'number'), 'series', 'pages',
                     'address', 'month', 'organization', 'publisher', 'note')
    },
    'inbook': {
        'description': 'A part of a book, usually untitled. May be a chapter'
                       ' (or section or whatever) and/or a range of pages.',
        'required': (('author', 'editor'), 'title', ('chapter', 'pages'),
                     'publisher', 'year'),
        'optional': (('volume', 'number'), 'series', 'type', 'address',
                     'edition', 'month', 'note')
    },
    'incollection': {
        'description': 'A part of a book having its own title.',
        'required': ('author', 'title', 'booktitle', 'publisher', 'year'),
        'optional': ('editor', ('volume', 'number'), 'series', 'type',
                     'chapter', 'pages', 'address', 'edition', 'month', 'note')
    },
    'inproceedings': {
        'description': 'An article in a conference proceedings.',
        'required': ('author', 'title', 'booktitle', 'year'),
        'optional': ('editor', ('volume', 'number'), 'series', 'pages',
                    'address', 'month', 'organization', 'publisher', 'note')
    },
    'manual': {
        'description': 'Technical documentation.',
        'required': ('title',),
        'optional': ('author', 'organization', 'address', 'edition', 'month',
                     'year', 'note')
    },
    'mastersthesis': {
        'description': 'A Master\'s thesis.',
        'required': ('author', 'title', 'school', 'year'),
        'optional': ('type', 'address', 'month', 'note')
    },
    'misc': {
        'description': 'For use when nothing else fits.',
        'required': (),
        'optional': ('author', 'title', 'howpublished', 'month', 'year', 'note')
    },
    'phdthesis': {
        'description': 'A Ph.D. thesis.',
        'required': ('author', 'title', 'school', 'year'),
        'optional': ('type', 'address', 'month', 'note')
    },
    'proceedings': {
        'description': 'The proceedings of a conference.',
        'required': ('title', 'year'),
        'optional': ('editor', ('volume', 'number'), 'series', 'address',
                     'month', 'publisher', 'organization', 'note')
    },
    'techreport': {
        'description': 'A report published by a school or other institution,'
                       ' usually numbered within a series.',
        'required': ('author', 'title', 'institution', 'year'),
        'optional': ('type', 'number', 'address', 'month', 'note')
    },
    'unpublished': {
        'description': 'A document having an author and title, but not formally'
                       ' published.',
        'required': ('author', 'title', 'note'),
        'optional': ('month', 'year')
    }
}


# Other entry types.  Not recommended.
OTHER_ENTRY_TYPES = (
    'collection',
    'patent'
)


# Universally optional field names. These field names are optional for all
# entry types.
UNIV_OPT_FIELD_NAMES = (
    'key',      # Additional info for alphabetizing entries
    'crossref'  # Field text here is the cite key for another entry,
    'url',
    'crossref'
)


# Field names.
# Note that 'eprint' and 'url' might also be in the standard fields, cf.
# http://en.wikipedia.org/wiki/BibTeX#Bibliographic_information_file
FIELD_NAMES = (
    'address',      # Usually the address of the publisher or other type of
                    # institution. For major publishing houses, van Leunen
                    # recommends omitting the information entirely. For small
                    # publishers, on the other hand, you can help the reader by
                    # giving the complete address.
    'annote',       # An annotation. It is not used by the standard
                    # bibliography styles, but may be used by others that
                    # produce an annotated bibliography.
    'author',       # The name(s) of the author(s), in the format described in
                    # the LaTeX book.
    'booktitle',    # Title of a book, part of which is being cited. See the
                    # LaTeX book for how to type titles. For book entries, use
                    # the title field instead.
    'chapter',      # A chapter (or section or whatever) number.
    'crossref',     # The database key of the entry being cross referenced. Any
                    # fields that are missing from the current record are
                    # inherited from the field being cross referenced.
    'edition',      # The edition of a book---for example, ``Second''. This
                    # should be an ordinal, and should have the first letter
                    # capitalized, as shown here; the standard styles convert
                    # to lower case when necessary.
    'editor',       # Name(s) of editor(s), typed as indicated in the LaTeX
                    # book. If there is also an author field, then the editor
                    # field gives the editor of the book or collection in which
                    # the reference appears.
    'howpublished', # How something strange has been published. The first word
                    # should be capitalized.
    'institution',  # The sponsoring institution of a technical report.
    'journal',      # A journal name. Abbreviations are provided for many
                    # journals.
    'key',          # Used for alphabetizing, cross referencing, and creating a
                    # label when the ``author'' information is missing. This
                    # field should not be confused with the key that appears in
                    # the cite command and at the beginning of the database entry.
    'month',        # The month in which the work was published or, for an
                    # unpublished work, in which it was written. You should use
                    # the standard three-letter abbreviation, as described in
                    # Appendix B.1.3 of the LaTeX book.
    'note',         # Any additional information that can help the reader. The
                    # first word should be capitalized.
    'number',       # The number of a journal, magazine, technical report, or
                    # of a work in a series. An issue of a journal or magazine is
                    # usually identified by its volume and number; the
                    # organization that issues a technical report usually gives
                    # it a number; and sometimes books are given numbers in a
                    # named series.
    'organization', # The organization that sponsors a conference or that
                    # publishes a manual.
    'pages',        # One or more page numbers or range of numbers, such as
                    # 42--111 or 7,41,73--97 or 43+ (the `+' in this last example
                    # indicates pages following that don't form a simple range).
                    # To make it easier to maintain Scribe-compatible databases,
                    # the standard styles convert a single dash (as in 7-33) to
                    # the double dash used in TeX to denote number ranges (as in
                    # 7--33).
    'publisher',    # The publisher's name.
    'school',       # The name of the school where a thesis was written.
    'series',       # The name of a series or set of books. When citing an
                    # entire book, the the title field gives its title and an
                    # optional series field gives the name of a series or
                    # multi-volume set in which the book is published.
    'title',        # The work's title, typed as explained in the LaTeX book.
    'type',         # The type of a technical report---for example, ``Research
                    # Note''.
    'url',          # The universal resource locator for online documents; this
                    # is not standard but supplied by more modern bibliography
                    # styles.
    'volume',       # The volume of a journal or multi-volume book.
    'year'          # The year of publication or, for an unpublished work, the
                    # year it was written. Generally it should consist of four
                    # numerals, such as 1984, although the standard styles can
                    # handle any year whose last four nonpunctuation characters
                    # are numerals, such as `\hbox{(about 1984)}'.
)


# Other field names.
OTHER_FIELD_NAMES = (
    'affiliation',  # The author's affiliation.
    'abstract',     # An abstract of the work.
    'contents',     # A Table of Contents
    'copyright',    # Copyright information.
    'ISBN',         # The International Standard Book Number.
    'ISSN',         # The International Standard Serial Number. Used to identify a journal.
    'keywords',     # Key words used for searching or possibly for annotation.
    'language',     # The language the document is in.
    'location',     # A location associated with the entry, such as the city in which a conference took place.
    'LCCN',         # The Library of Congress Call Number. I've also seen this as lib-congress.
    'mrnumber',     # The Mathematical Reviews number.
    'price',        # The price of the document.
    'size'          # The physical dimensions of a work.
)
