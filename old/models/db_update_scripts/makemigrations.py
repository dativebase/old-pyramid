#!/usr/bin/env python

"""
===============================================================================
  Make Migrations for an OLD
===============================================================================

This script creates (MySQL) database migration scripts for an OLD instance, and
also optionally performs the created migrations.

Note that it does this in a rather silly way, but it avoids a lot of
complications and dependencies so this is the way I went with it:

    1. Create a dummy OLD db based on the currently installed OLD's model.
    2. Dump the dummy OLD db and parse its schema manually.
    3. Dump the target OLD MySQL db.
    4. Generate migration SQL based on a comparison of the two MySQL dump
       files.
    5. Create a backup of the target db prior to performing the migrations.
    6. Perform the migration on the target OLD db (if user chooses), using SQL.
    7. Destroy the dummy OLD.

Usage::

    ./makemigrations.py \
        /full/path/to/pylons/config/for/target/old.ini \
        mysql_username

The script will prompt you for the password that goes with mysql_username.
"""

from __future__ import print_function
import datetime
import getpass
import optparse
import os
import shutil
import stat
import subprocess
import sys

import old


if "check_output" not in dir(subprocess): # duck punch it in!
    def f(*popenargs, **kwargs):
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed, it will be overridden.')
        process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
        output, unused_err = process.communicate()
        retcode = process.poll()
        if retcode:
            cmd = kwargs.get("args")
            if cmd is None:
                cmd = popenargs[0]
            raise subprocess.CalledProcessError(retcode, cmd)
        return output
    subprocess.check_output = f


MODEL_SCHEMA_FILE_NAME = 'model-schema.sql'
DATABASE_SCHEMA_FILE_NAME = 'database-schema.sql'
TMP_DIR_NAME = '.tmp'
BACKUP_DIR_NAME = 'backups'
DUMMY_OLD_DB_NAME = 'old_database_for_migrations_fox'


def cleanup_on_exception(func):
    """Destroy our temporary files (and database) if an exception occurs."""
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception:
            self.cleanup()
            raise
    return wrapper


class MigrationMaker:

    def remove_trailing_comma(self, line):
        if line[-1] == ',':
            return line[:-1]
        return line

    def sort_table(self, table):
        """Sort all of the lines in a MySQL CREATE TABLE statement, first
        sorting all of the column declaration lines, and then sorting all of
        the KEY/UNIQUE lines.
        """
        filling = table[1:-1]
        cols = sorted([l for l in filling if l.strip().startswith('`')])
        end = sorted([l for l in filling if not l.strip().startswith('`')])
        return [table[0]] + cols + end + [table[-1]]

    def get_schema_from_mysql_dumpfile(self, schema_path):
        """Return a python dict representing the schema of the MySQL database
        represented by the mysqldump file at `schema_path`. This facilitates
        comparison of schemata.
        """
        schema = {}
        in_table = False
        with open(schema_path) as f:
            table = []
            table_name = None
            for l in f:
                if l.startswith('CREATE TABLE '):
                    in_table = True
                    table_name = l.split()[2][1:-1]
                    table = []
                    table.append(self.remove_trailing_comma(l.strip()))
                elif l[0] == ')':
                    table.append(self.remove_trailing_comma(l.strip()))
                    table = self.sort_table(table)
                    schema[table_name] = table
                    in_table = False
                elif in_table:
                    table.append(self.remove_trailing_comma(l.strip()))
        return schema

    def format_table_create_stmt(self, table_schema):
        """Input is `table_schema`, a list of MySQL statement lines
        representing a CREATE TABLE command. Output is a well-formatted CREATE
        TABLE string that MySQL should be able to understand.
        """
        return '%s\n  %s\n%s' % (
            table_schema[0],
            ',\n  '.join(table_schema[1:-1]),
            table_schema[-1]
        )

    def get_updates_from_modify(self, tn, coldef):
        """If a table column is being modified (ALTER), it may require some
        update statements.
        """
        updates = []
        if 'NOT NULL' in coldef:
            colname = coldef.split()[0]
            if colname.startswith('`'):
                colname = colname[1:-1]
            updates.append('UPDATE %s SET %s = \'\' WHERE %s IS NULL;' % (
                tn, colname, colname))
        return updates

    def get_migration_sql(self):
        """Return a string of SQL that can be used to migrate the source
        database to the destination database.
        """
        SQL = []
        if ((not os.path.isfile(self.database_schema_path)) or
                (not os.path.isfile(self.model_schema_path))):
            sys.exit('Either {0} or {1} does not exist'.format(
                self.database_schema_path, self.model_schema_path))
        src_schema = self.get_schema_from_mysql_dumpfile(
            self.database_schema_path)
        dst_schema = self.get_schema_from_mysql_dumpfile(
            self.model_schema_path)
        tables_to_add = [tn for tn in dst_schema if tn not in src_schema]
        tables_to_remove = [tn for tn in src_schema if tn not in dst_schema]
        if tables_to_add:
            for tn in tables_to_add:
                SQL.append(self.format_table_create_stmt(dst_schema[tn]))
        if tables_to_remove:
            for tn in tables_to_remove:
                SQL.append('DROP TABLE `%s`;' % tn)
        table_diffs = {}
        for tn, dst_table_schema in dst_schema.items():
            src_table_schema = src_schema.get(tn)
            if src_table_schema:
                table_diff = self.get_table_diff(dst_table_schema,
                                                 src_table_schema)
                if table_diff:
                    table_diffs[tn] = table_diff
        for tn, changes in table_diffs.items():
            for coldef in changes.get('cols_to_modify', []):
                SQL.append('ALTER TABLE %s MODIFY %s;' % (tn, coldef))
                SQL = SQL + self.get_updates_from_modify(tn, coldef)
            for coldef in changes.get('cols_to_add', []):
                SQL.append('ALTER TABLE %s ADD %s;' % (tn, coldef))
            for coldef in changes.get('cols_to_remove', []):
                SQL.append('ALTER TABLE %s DROP COLUMN %s;' % (
                    tn, coldef.strip().split()[0][1:-1]))
        return '\n'.join(SQL)

    def get_table_diff(self, dst_table_schema, src_table_schema):
        """Return `diff`, a dict with keys for columns to add, remove and
        modify on a given table. `dst_table_schema` and `src_table_schema` are
        lists of strings representing MySQL CREATE TABLE statements.
        """
        diff = {}
        cols_to_add = []
        cols_to_remove = []
        cols_to_modify = []
        for coldef in dst_table_schema[1:-1]:
            if coldef not in src_table_schema[1:-1]:
                if coldef.startswith('`'):
                    colname = coldef.split()[0][1:-1]
                    src_col_names = dict([(x.split()[0][1:-1], x) for x in
                                          src_table_schema if
                                          x.startswith('`')])
                    if colname in src_col_names:
                        # If a `name` col has been changed to have UTF8 charset
                        # and collation, that is an intentional fix of a known
                        # issue. So leave it alone.
                        if (coldef == '`name` varchar(255) DEFAULT NULL' and
                            src_col_names[colname] == '`name` varchar(255)'
                                ' CHARACTER SET utf8 COLLATE utf8_bin DEFAULT'
                                ' NULL'):
                            pass
                        else:
                            print('Modify:\n    {0}\nto\n    {1}\n'.format(
                                  coldef, src_col_names[colname]))
                            cols_to_modify.append(coldef)
                    else:
                        print('Add:\n    {0}\n'.format(coldef))
                        cols_to_add.append(coldef)
        for coldef in src_table_schema[1:-1]:
            if coldef not in dst_table_schema[1:-1]:
                if coldef.startswith('`'):
                    colname = coldef.split()[0][1:-1]
                    dst_col_names = [x.split()[0][1:-1] for x in
                                     dst_table_schema if x.startswith('`')]
                    if colname not in dst_col_names:
                        print('Delete:\n    {0}\n'.format(coldef))
                        cols_to_remove.append(coldef)
        if cols_to_add:
            diff['cols_to_add'] = cols_to_add
        if cols_to_remove:
            diff['cols_to_remove'] = cols_to_remove
        if cols_to_modify:
            diff['cols_to_modify'] = cols_to_modify
        return diff

    def get_here(self):
        return os.path.dirname(os.path.realpath(__file__))

    def get_tmp_path(self):
        return os.path.join(self.get_here(), TMP_DIR_NAME)

    def get_backup_dir_path(self):
        return os.path.join(self.get_here(), BACKUP_DIR_NAME)

    def create_backup_dir(self):
        backup_dir_path = self.get_backup_dir_path()
        if not os.path.exists(backup_dir_path):
            os.mkdir(backup_dir_path)
        return backup_dir_path

    def create_tmp_dir(self):
        tmp_path = self.get_tmp_path()
        if os.path.exists(tmp_path):
            shutil.rmtree(tmp_path)
        os.mkdir(tmp_path)

    def destroy_tmp_dir(self):
        tmp_path = self.get_tmp_path()
        if os.path.exists(tmp_path):
            shutil.rmtree(tmp_path)

    def create_dummy_old_mysql_database(self):
        """Create a dummy MySQL database for the temporary OLD we create in
        order to get the schema.
        """
        create_db_stmt = ('DROP DATABASE IF EXISTS {0}; CREATE DATABASE {1}'
                          ' DEFAULT' ' CHARACTER SET utf8;'.format(
                              DUMMY_OLD_DB_NAME, DUMMY_OLD_DB_NAME))
        command = ['mysql', '-u', self.mysql_root_username,
                   '-p{0}'.format(self.mysql_root_password), '-e',
                   create_db_stmt]
        subprocess.check_output(command)

    def get_dummy_old_config_path(self):
        tmp_path = self.get_tmp_path()
        return os.path.join(tmp_path, 'production.ini')

    def create_dummy_old_config(self):
        """Create the OLD config file (production.ini) in .tmp/."""
        config_path = self.get_dummy_old_config_path()
        command = ['paster', 'make-config', 'onlinelinguisticdatabase',
                   config_path]
        subprocess.check_output(command)

    def setup_dummy_old_mysql_database(self):
        """Set-up the dummy OLD, i.e., create the tables."""
        command = ['paster', 'setup-app', 'production.ini']
        subprocess.call(command, cwd=self.get_tmp_path())

    def fix_dummy_old_config(self):
        """Replace the default SQLite line of the OLD config with MySQL
        lines."""
        fixed_config = []
        config_path = self.get_dummy_old_config_path()
        with open(config_path) as f:
            for l in f:
                if l.startswith('sqlalchemy.url') and 'sqlite' in l:
                    fixed_config.append('# ' + l)
                    fixed_config.append(
                        'sqlalchemy.url = mysql://{0}:{1}@localhost:3306/{2}\n'
                        .format(self.mysql_root_username,
                                self.mysql_root_password, DUMMY_OLD_DB_NAME))
                    fixed_config.append('sqlalchemy.pool_recycle = 3600\n')
                else:
                    fixed_config.append(l)
        fixed_config = ''.join(fixed_config)
        with open(config_path, 'w') as f:
            f.write(fixed_config)

    def dump_dummy_old_mysql_database_schema(self):
        """Dump the dummy OLD MySQL database schema to a file and return the
        path to that file.
        """
        dump_file_path = os.path.join(self.get_tmp_path(),
                                      MODEL_SCHEMA_FILE_NAME)
        command = ['mysqldump', '--skip-comments', '--skip-extended-insert',
                   '--no-data', '--skip-lock-tables', '-u',
                   self.mysql_root_username,
                   '-p{0}'.format(self.mysql_root_password), DUMMY_OLD_DB_NAME]
        with open(dump_file_path, "wb") as f:
            process = subprocess.Popen(command, stdout=f)
        process.communicate()
        assert os.path.isfile(dump_file_path)
        return dump_file_path

    def dump_database_schema(self):
        dump_file_path = os.path.join(self.get_tmp_path(),
                                      DATABASE_SCHEMA_FILE_NAME)
        command = ['mysqldump', '--skip-comments', '--skip-extended-insert',
                   '--no-data', '--skip-lock-tables', '-u',
                   self.mysql_root_username,
                   '-p{0}'.format(self.mysql_root_password), self.db_name]
        with open(dump_file_path, "wb") as f:
            process = subprocess.Popen(command, stdout=f)
        process.communicate()
        assert os.path.isfile(dump_file_path)
        return dump_file_path

    def get_model_schema(self):
        """Get the schema of the current OLD model in an .sql file and return
        the path to that schema file.
        """
        self.create_tmp_dir()
        self.create_dummy_old_mysql_database()
        self.create_dummy_old_config()
        self.fix_dummy_old_config()
        self.setup_dummy_old_mysql_database()
        return self.dump_dummy_old_mysql_database_schema()

    def backup_db(self):
        """Backup the database using mysqldump to a file in backups/ prior to
        performing the migrations.
        """
        backup_dir_path = self.create_backup_dir()
        backup_script_path = self.create_backup_script(backup_dir_path)
        subprocess.check_output([backup_script_path])

    def create_backup_script(self, backup_dir_path):
        backup_script_path = os.path.join(self.get_tmp_path(),
                                          'mysqldump-script.sh')
        backup_path = self.get_backup_path(backup_dir_path)
        with open(backup_script_path, 'w') as f:
            f.write('#!/usr/bin/env bash\n'
                    'SLEEP_TIMEOUT=5\n'
                    'SQLSTMT="FLUSH TABLES WITH READ LOCK;'
                    ' SELECT SLEEP(${{SLEEP_TIMEOUT}})"\n'
                    'mysql -u{username} -p\'{password}\' -Ae"${{SQLSTMT}}" &\n'
                    'mysqldump -u{username} -p{password} --single-transaction'
                    ' --routines --triggers {db_name} > {backup_path}'.format(
                        username=self.mysql_root_username,
                        password=self.mysql_root_password,
                        db_name=self.db_name,
                        backup_path=backup_path))
        st = os.stat(backup_script_path)
        os.chmod(backup_script_path, st.st_mode | stat.S_IEXEC)
        return backup_script_path

    def get_backup_path(self, backup_dir_path):
        backup_filename = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        return os.path.join(backup_dir_path,
                            '{0}_{1}.sql'.format(
                                self.db_name,
                                backup_filename))

    def commit_migrations(self, migration_sql):
        """Perform the migrations."""
        # Create a backup of the current database.
        self.backup_db()
        # Write the migration SQL to migration-script.sql
        migration_file_path = os.path.join(self.get_tmp_path(),
                                           'migration-script.sql')
        with open(migration_file_path, 'w') as f:
            f.write(migration_sql)
        migration_script_path = os.path.join(self.get_tmp_path(),
                                             'migration-script.sh')
        # Write a shell script that will execute the migration-script against
        # the database
        with open(migration_script_path, 'w') as f:
            f.write('#!/usr/bin/env bash\n'
                    'mysql -u {0} -p\'{1}\' {2} < {3}'.format(
                        self.mysql_root_username,
                        self.mysql_root_password,
                        self.db_name,
                        migration_file_path))
        st = os.stat(migration_script_path)
        os.chmod(migration_script_path, st.st_mode | stat.S_IEXEC)
        # Execute the migration script.
        subprocess.check_output([migration_script_path])

    def cleanup(self):
        """Clean up: destroy the dummy OLD database and the entire .tmp/
        dir.
        """
        self.destroy_dummy_database()
        self.destroy_tmp_dir()

    def destroy_dummy_database(self):
        drop_db_stmt = ('DROP DATABASE IF EXISTS {0};'.format(
            DUMMY_OLD_DB_NAME))
        command = ['mysql', '-u', self.mysql_root_username,
                   '-p{0}'.format(self.mysql_root_password), '-e', drop_db_stmt]
        subprocess.check_output(command)

    def get_db_from_config(self):
        """Find the MySQL db_name, username, and password in the Pylons config
        file at ``self.config_path`` and return them as a 3-tuple.
        """
        if not os.path.isfile(self.config_path):
            sys.exit('There is no config file at {0}.'.format(self.config_path))
        with open(self.config_path) as f:
            for l in f:
                if l.startswith('sqlalchemy.url'):
                    db_url = l.strip().split(' ')[2]
                    db_url = db_url.replace('mysql://', '')
                    username, password = db_url.split('@')[0].split(':')
                    db_name = db_url.split('/')[-1]
                    if '?' in db_name:
                        db_name = db_name.split('?')[0]
                    return db_name, username, password
        return None, None, None

    def __init__(self, config_path, mysql_root_username, mysql_root_password):
        self.config_path = config_path
        self.mysql_root_username = mysql_root_username
        self.mysql_root_password = mysql_root_password

    def print_sql(self, sql):
        line = '=' * 80
        print('\n{0}\nMigration SQL\n{1}\n\n{2}\n\n{3}\n'.format(
            line, line, sql, line))

    @cleanup_on_exception
    def migrate(self, commit=False):
        self.db_name, self.username, self.password = self.get_db_from_config()
        self.model_schema_path = self.get_model_schema()
        self.database_schema_path = self.dump_database_schema()
        migration_sql = self.get_migration_sql()
        if not migration_sql.strip():
            sys.exit('There are no migrations to make. The database {0} appears'
                     ' to be up-to-date with the OLD v.'
                     ' {1}.'.format(self.db_name, old.__version__))
        self.print_sql(migration_sql)
        if commit:
            self.commit_migrations(migration_sql)
        self.cleanup()


def main():
    parser = optparse.OptionParser(
        usage="%prog [options] config_path")
    parser.add_option("-c", "--commit", action="store_true", dest="commit",
                      help="Commit updates to the database (default=%default)",
                      default=False)
    (options, args) = parser.parse_args()
    if len(args) != 2:
        parser.error('Wrong number of command-line arguments.')
    config_path, mysql_root_username = args
    mysql_root_password = getpass.getpass()
    migration_maker = MigrationMaker(config_path, mysql_root_username,
                                     mysql_root_password)
    migration_maker.migrate(options.commit)


if __name__ == '__main__':
    main()
