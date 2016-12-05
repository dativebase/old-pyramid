#!/usr/bin/python

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

"""This executable updates an OLD 1.2.4 MySQL database and makes it compatible
with the OLD 1.2.5 data structure

Usage:

    $ ./old_update_db_1.2.4_1.2.5.py \
        -d mysql_db_name \
        -u mysql_username \
        -p mysql_password \

"""

import os
import sys
import subprocess

# update_SQL holds the SQL statements that create the tables missing in 1.2.4
# and which alter the existing tables.
update_SQL = '''
UPDATE form SET transcription='' where transcription IS NULL;
ALTER TABLE form MODIFY transcription varchar(510) NOT NULL;
UPDATE formbackup SET transcription='' where transcription IS NULL;
ALTER TABLE formbackup MODIFY transcription varchar(510) NOT NULL;
CREATE TABLE `keyboard` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `description` text,
  `keyboard` text,
  `enterer_id` int(11) DEFAULT NULL,
  `modifier_id` int(11) DEFAULT NULL,
  `datetime_entered` datetime DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `enterer_id` (`enterer_id`),
  KEY `modifier_id` (`modifier_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
ALTER TABLE language MODIFY Id varchar(3) NOT NULL;
ALTER TABLE morphologybackup ADD `rich_lower` tinyint(1) DEFAULT NULL;
ALTER TABLE page ADD UNIQUE (name);
ALTER TABLE tag MODIFY name varchar(255) CHARACTER SET utf8 COLLATE utf8_bin DEFAULT NULL;
'''.strip()


def write_update_executable(mysql_update_script_name, here):
    """Write the contents of update_SQL to an executable and return the path to
    it.

    """

    mysql_update_script = os.path.join(here, mysql_update_script_name)
    if os.path.exists(mysql_update_script):
        os.remove(mysql_update_script)
    with open(mysql_update_script, 'w') as f:
        f.write(update_SQL)
    os.chmod(mysql_update_script, 0744)
    return mysql_update_script


def perform_update(mysql_db_name, mysql_update_script, mysql_username, mysql_password, mysql_updater):
    """Perform the preliminary update of the db by calling the executable at
    ``mysql_update_script``.

    """

    print 'Running the MySQL update script ... '
    mysql_script_content = '#!/bin/sh\nmysql -u %s -p%s %s < %s' % (
        mysql_username, mysql_password, mysql_db_name, mysql_update_script)
    with open(mysql_updater, 'w') as f:
        f.write(mysql_script_content)
    with open(os.devnull, 'w') as devnull:
        subprocess.call([mysql_updater], shell=False, stdout=devnull,
            stderr=devnull)
    print 'done.'


def parse_arguments(arg_list):
    result = {}
    map_ = {'-d': 'mysql_db_name', '-u': 'mysql_username', '-p': 'mysql_password'}
    iterator = iter(arg_list)
    try:
        for element in iterator:
            if element in map_:
                result[map_[element]] = iterator.next()
    except Exception:
        pass
    if len(set(['mysql_db_name', 'mysql_username', 'mysql_password']) &
        set(result.keys())) != 3:
        sys.exit('Usage: python old_update_db_1.2.4_1.2.5.py -d mysql_db_name'
            ' -u mysql_username -p mysql_password')
    return result


def write_updater_executable(mysql_updater_name, here):
    """Write to disk the shell script that will be used to load the various
    MySQL scripts. Return the absolute path.

    """

    mysql_updater = os.path.join(here, mysql_updater_name)
    with open(mysql_updater, 'w') as f:
        pass
    os.chmod(mysql_updater, 0744)
    return mysql_updater


if __name__ == '__main__':

    # User must supply values for mysql_db_name, mysql_username and
    # mysql_password.
    arguments = parse_arguments(sys.argv[1:])
    mysql_db_name = arguments.get('mysql_db_name')
    mysql_username = arguments.get('mysql_username')
    mysql_password = arguments.get('mysql_password')

    here = os.path.dirname(os.path.realpath(__file__))

    # The shell script that will be used multiple times to load the MySQL
    # scripts below
    mysql_updater_name = 'tmp.sh'
    mysql_updater = write_updater_executable(mysql_updater_name, here)

    # The executable that performs the update.
    mysql_update_script_name = 'old_update_db_1.2.4_1.2.5.sql'
    mysql_update_script = write_update_executable(mysql_update_script_name,
        here)

    # Perform the preliminary update of the database using ``mysql_update_script``
    perform_update(mysql_db_name, mysql_update_script,
        mysql_username, mysql_password, mysql_updater)


