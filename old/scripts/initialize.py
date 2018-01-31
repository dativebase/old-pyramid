# Copyright 2018 Joel Dunham
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

"""Setup an OLD instance by creating its database tables and directory
structure and by adding some defaults to the database.
"""

import argparse
import logging
import os
import sys

from pyramid.paster import (
    get_appsettings,
    setup_logging,
)
from sqlalchemy.exc import ProgrammingError, IntegrityError

from old import (
    db_session_factory_registry,
    override_settings_with_env_vars
)
import old.lib.helpers as h
import old.models.modelbuilders as omb
from old.models.meta import Base


LOGGER = logging.getLogger(__name__)


def get_args():
    parser = argparse.ArgumentParser(
        description='Initialize an OLD instance: build its database tables, set'
                    ' some initial data and create its default directory'
                    ' structure.\n\nNote: if using MySQL, the OLD_NAME database'
                    ' must already exist, e.g., CREATE DATABASE <OLD_NAME>'
                    ' DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_bin;',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        'config_file', metavar='CONFIG_FILE',
        help='Path (relative or absolute) to the OLD config file, e.g.,'
             'config.ini',
        default='config.ini')
    parser.add_argument(
        'old_name', metavar='OLD_NAME',
        help='The name of the OLD instance to set up. This should be valid as'
             ' both the name of the database where the tables will be created'
             ' and the name of the directory where the instance\'s files will'
             ' be stored',
        default='old')
    return parser.parse_args()


def drop_tables(dbsession, old_name):
    try:
        Base.metadata.drop_all(bind=dbsession.bind, checkfirst=True)
        LOGGER.info('Dropped database tables for old "%s".', old_name)
    except ProgrammingError:
        LOGGER.info('Unable to create the database tables. Are you sure that'
                    ' the database "%s" exists?', old_name)
        sys.exit(1)


def create_tables(dbsession, old_name):
    try:
        Base.metadata.create_all(bind=dbsession.bind, checkfirst=True)
        LOGGER.info('Created database tables for old "%s".', old_name)
    except ProgrammingError:
        LOGGER.info('Unable to create the database tables. Are you sure that'
                    ' the database "%s" exists?', old_name)
        sys.exit(1)


def main(argv=None):
    args = get_args()
    setup_logging(args.config_file)
    settings = get_appsettings(args.config_file, options={})
    settings['old_name'] = args.old_name
    settings = override_settings_with_env_vars(settings)
    testing = settings.get('testing', '0') == '1'
    dbsession = db_session_factory_registry.get_session(settings)()
    if testing:
        LOGGER.info('Initializing OLD "%s" for testing.', args.old_name)
    else:
        LOGGER.info('Initializing OLD "%s".', args.old_name)
    h.create_OLD_directories(settings)
    LOGGER.info('Created directory structure for old "%s" at path %s.',
                args.old_name, os.path.join(
                    settings['permanent_store'],
                    settings['old_name']))
    languages = omb.get_language_objects(settings['here'], truncated=False)
    administrator = omb.generate_default_administrator(settings=settings)
    contributor = omb.generate_default_contributor(settings=settings)
    viewer = omb.generate_default_viewer(settings=settings)
    if testing:
        drop_tables(dbsession, args.old_name)
        create_tables(dbsession, args.old_name)
        dbsession.add_all(languages + [administrator, contributor, viewer])
        LOGGER.info('Added ISO languages data and default users')
    else:
        created = ['home page', 'help page', 'default application settings',
                   'useful tags and categories']
        create_tables(dbsession, args.old_name)
        homepage = omb.generate_default_home_page()
        helppage = omb.generate_default_help_page()
        application_settings = omb.generate_default_application_settings()
        restricted_tag = omb.generate_restricted_tag()
        foreign_word_tag = omb.generate_foreign_word_tag()
        data = [administrator, contributor, viewer, homepage, helppage,
                application_settings, restricted_tag, foreign_word_tag]
        if settings['add_language_data'] != '0':
            created.append('ISO language data')
            data += languages
        if settings['empty_database'] == '0':
            dbsession.add_all(data)
            for thing in created:
                LOGGER.info('Created %s.', thing)
    try:
        dbsession.commit()
        LOGGER.info('Changes committed to the database')
    except IntegrityError:
        dbsession.rollback()
        LOGGER.info('Unable to commit the changes to the database. This may be'
                    ' because the database was already previously initialized.'
                    ' Try dropping it and re-creating it before running this'
                    ' initialization script.')
    else:
        LOGGER.info('OLD "%s" successfully set up.', args.old_name)
    finally:
        dbsession.close()
