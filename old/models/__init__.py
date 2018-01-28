import re

from sqlalchemy import engine_from_config, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import configure_mappers, sessionmaker

# import or define all models here to ensure they are attached to the
# Base.metadata prior to any initialization routines
from .applicationsettings import ApplicationSettings
from .collection import Collection
from .collectionbackup import CollectionBackup
from .corpus import Corpus
from .corpusbackup import CorpusBackup
from .elicitationmethod import ElicitationMethod
from .file import File
from .form import Form
from .formbackup import FormBackup
from .formsearch import FormSearch
from .keyboard import Keyboard
from .language import Language
from .model import Model
from .morphemelanguagemodel import MorphemeLanguageModel
from .morphemelanguagemodelbackup import MorphemeLanguageModelBackup
from .morphologicalparser import MorphologicalParser
from .morphologicalparserbackup import MorphologicalParserBackup
from .morphology import Morphology
from .morphologybackup import MorphologyBackup
from .orthography import Orthography
from .page import Page
from .phonology import Phonology
from .phonologybackup import PhonologyBackup
from .source import Source
from .speaker import Speaker
from .syntacticcategory import SyntacticCategory
from .tag import Tag
from .translation import Translation
from .user import User

# run configure_mappers after defining all of the models to ensure
# all relationships can be setup
configure_mappers()


def patch_sqlite(settings):
    """Make SQLite behave how we want it to: regex search and case-sensitive
    LIKE.
    """
    RDBMS_Name, *_ = settings['sqlalchemy.url'].split(':')
    if RDBMS_Name == 'sqlite':
        # pylint: disable=unused-variable
        @event.listens_for(Engine, 'begin')
        def sqlite_patches(dbapi_connection):
            # Define a regexp function for SQLite,
            def regexp(expr, item):
                """This is the Python re-based regexp function that we provide
                for SQLite.  Note that searches will be case-sensitive by
                default. Such behaviour is assured in MySQL by inserting
                COLLATE expressions into the query (cf. in
                SQLAQueryBuilder.py).
                """
                patt = re.compile(expr)
                try:
                    return item and patt.search(item) is not None
                # This will make regexp searches work on int, date & datetime
                # fields.
                except TypeError:
                    return item and patt.search(str(item)) is not None
            dbapi_connection.connection.create_function('regexp', 2, regexp)
            # Make LIKE searches case-sensitive in SQLite.
            cursor = dbapi_connection.connection.cursor()
            cursor.execute("PRAGMA case_sensitive_like=ON")
            cursor.close()


def get_engine(settings, prefix='sqlalchemy.'):
    patch_sqlite(settings)
    return engine_from_config(settings, prefix)


def get_session_factory(engine):
    factory = sessionmaker()
    factory.configure(bind=engine)
    return factory
