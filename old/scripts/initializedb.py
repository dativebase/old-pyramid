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

"""Setup the OLD application: database tables and directory structure"""

import logging
import os
import sys

from pyramid.paster import (
    get_appsettings,
    setup_logging,
)
from pyramid.scripts.common import parse_vars

from old import db_session_factory_registry
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.models.meta import Base
from old.models import get_engine


LOGGER = logging.getLogger(__name__)


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=None):
    if argv is None:
        argv = sys.argv
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)
    engine = get_engine(settings)
    Base.metadata.create_all(engine)

    try:
        dbsession = db_session_factory_registry.get_session(settings)()
        filename = os.path.basename(settings['__file__'])
        # Create the ``store`` directory and those for file, analysis and
        # corpora objects and their subdirectories.  See ``lib.utils.py`` for
        # details.
        h.create_OLD_directories(settings)
        # ISO-639-3 Language data for the languages table
        LOGGER.info('Retrieving ISO-639-3 languages data.')
        languages = omb.get_language_objects(settings['here'], truncated=False)
        # Get default users.
        LOGGER.info('Creating a default administrator, contributor and viewer.')
        administrator = omb.generate_default_administrator(
            settings=settings)
        contributor = omb.generate_default_contributor(
            settings=settings)
        viewer = omb.generate_default_viewer(settings=settings)
        # If we are running tests, make sure the test db contains only language
        # data.

        if filename == 'test.ini':
            # Permanently drop any existing tables
            Base.metadata.drop_all(bind=dbsession.bind, checkfirst=True)
            LOGGER.info("Existing tables dropped.")
            # Create the tables if they don't already exist
            Base.metadata.create_all(bind=dbsession.bind, checkfirst=True)
            LOGGER.info('Tables created.')
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
            LOGGER.info('Tables created.')
            # Get default home & help pages.
            LOGGER.info("Creating default home and help pages.")
            homepage = omb.generate_default_home_page()
            helppage = omb.generate_default_help_page()
            # Get default application settings.
            LOGGER.info("Generating default application settings.")
            application_settings = omb.generate_default_application_settings()
            # Get default tags and categories
            LOGGER.info("Creating some useful tags and categories.")
            restricted_tag = omb.generate_restricted_tag()
            foreign_word_tag = omb.generate_foreign_word_tag()
            # Initialize the database
            LOGGER.info("Adding defaults.")
            data = [administrator, contributor, viewer, homepage, helppage,
                    application_settings, restricted_tag, foreign_word_tag]
            if settings['add_language_data'] != '0':
                data += languages
            if settings['empty_database'] == '0':
                dbsession.add_all(data)
            LOGGER.info("OLD successfully set up.")
    finally:
        dbsession.commit()
        #dbsession.close()
        dbsession.remove()
