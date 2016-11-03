import logging
import os
import pprint
import sys
import transaction

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars

from ..models.meta import Base
from ..models import (
    get_engine,
    get_session_factory,
    get_tm_session,
    )
from ..models import ApplicationSettings
from ..models import Collection
from ..models import CollectionBackup
from ..models import Corpus
from ..models import CorpusBackup
from ..models import ElicitationMethod
from ..models import File
from ..models import Form
from ..models import FormBackup
from ..models import FormSearch
from ..models import Keyboard
from ..models import Language
from ..models import MorphemeLanguageModel
from ..models import MorphemeLanguageModelBackup
from ..models import MorphologicalParser
from ..models import MorphologicalParserBackup
from ..models import Morphology
from ..models import MorphologyBackup
from ..models import Orthography
from ..models import Page
from ..models import Phonology
from ..models import PhonologyBackup
from ..models import Source
from ..models import Speaker
from ..models import SyntacticCategory
from ..models import Tag
from ..models import Translation
from ..models import User
import old.lib.helpers as h

log = logging.getLogger(__name__)


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)

    pprint.pprint(settings)

    engine = get_engine(settings)
    Base.metadata.create_all(engine)

    session_factory = get_session_factory(engine)

    with transaction.manager:
        dbsession = get_tm_session(session_factory, transaction.manager)

        filename = os.path.basename(settings['__file__'])

        # Create the ``store`` directory and those for file, analysis and
        # corpora objects and their subdirectories.  See ``lib.utils.py`` for
        # details.
        h.create_OLD_directories(settings=settings)

        # ISO-639-3 Language data for the languages table
        log.info('Retrieving ISO-639-3 languages data.')
        languages = h.get_language_objects(filename, settings['here'])

        # Get default users.
        log.info('Creating a default administrator, contributor and viewer.')
        administrator = h.generate_default_administrator(
            settings=settings)
        contributor = h.generate_default_contributor(
            settings=settings)
        viewer = h.generate_default_viewer(settings=settings)

        # If we are running tests, make sure the test db contains only language data.
        if filename == 'test.ini':
            # Permanently drop any existing tables
            Base.metadata.drop_all(bind=dbsession.bind, checkfirst=True)
            log.info("Existing tables dropped.")

            # Create the tables if they don't already exist
            Base.metadata.create_all(bind=dbsession.bind, checkfirst=True)
            log.info('Tables created.')

            dbsession.add_all(languages + [administrator, contributor, viewer])

        # Not a test: add a bunch of nice defaults.
        else:

            # Create the _requests_tests.py script
            # requests_tests_path = os.path.join(
            #     settings['here'], 'old', 'tests', 'scripts',
            #     '_requests_tests.py')
            # This line is problematic in production apps because the
            # _requests_tests.py file is not included in the build. So, I'm
            # commenting it out by default.
            # copyfile(requests_tests_path, '_requests_tests.py')

            # Create the tables if they don't already exist
            Base.metadata.create_all(bind=dbsession.bind, checkfirst=True)
            log.info('Tables created.')

            # Get default home & help pages.
            log.info("Creating default home and help pages.")
            homepage = h.generate_default_home_page()
            helppage = h.generate_default_help_page()

            # Get default application settings.
            log.info("Generating default application settings.")
            application_settings = h.generate_default_application_settings()

            # Get default tags and categories
            log.info("Creating some useful tags and categories.")
            restricted_tag = h.generate_restricted_tag()
            foreign_word_tag = h.generate_foreign_word_tag()
            S = h.generate_s_syntactic_category()
            N = h.generate_n_syntactic_category()
            V = h.generate_v_syntactic_category()

            # Initialize the database
            log.info("Adding defaults.")
            data = [administrator, contributor, viewer, homepage, helppage,
                    application_settings, restricted_tag, foreign_word_tag]
            if settings['add_language_data'] != '0':
                data += languages
            if settings['empty_database'] == '0':
                dbsession.add_all(data)
            log.info("OLD successfully set up.")
