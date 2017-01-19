import re

from sqlalchemy import engine_from_config, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import configure_mappers, sessionmaker
import zope.sqlalchemy

# import or define all models here to ensure they are attached to the
# Base.metadata prior to any initialization routines
from .applicationsettings import ApplicationSettings
from .collection import Collection
from .collectionbackup import CollectionBackup
from .corpus import (
    Corpus,
    CorpusFile
)
from .corpusbackup import CorpusBackup
from .export import Export
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
from .morphologicalparser import (
    MorphologicalParser,
    Parse
)
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
    RDBMS_Name, *rest = settings['sqlalchemy.url'].split(':')
    if RDBMS_Name == 'sqlite':
        #@event.listens_for(Engine, 'connect', once=True)
        #def sqlite_patches(dbapi_connection, connection_record):
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


def get_tm_session(session_factory, transaction_manager):
    """Get a ``sqlalchemy.orm.Session`` instance backed by a transaction.

    This function will hook the session to the transaction manager which
    will take care of committing any changes.

    - When using pyramid_tm it will automatically be committed or aborted
      depending on whether an exception is raised.

    - When using scripts you should wrap the session in a manager yourself.
      For example::

          import transaction

          engine = get_engine(settings)
          session_factory = get_session_factory(engine)
          with transaction.manager:
              dbsession = get_tm_session(session_factory, transaction.manager)
    """
    dbsession = session_factory()
    zope.sqlalchemy.register(
        dbsession, transaction_manager=transaction_manager)
    return dbsession


def includeme(config):
    """
    Initialize the model for a Pyramid app.

    Activate this setup using ``config.include('old.models')``.

    """
    settings = config.get_settings()

    # use pyramid_tm to hook the transaction lifecycle to the request
    config.include('pyramid_tm')

    session_factory = get_session_factory(get_engine(settings))
    config.registry['dbsession_factory'] = session_factory

    # make request.dbsession available for use in Pyramid
    config.add_request_method(
        # r.tm is the transaction manager used by pyramid_tm
        lambda r: get_tm_session(session_factory, r.tm),
        'dbsession',
        reify=True
    )
