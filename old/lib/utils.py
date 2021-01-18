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

"""Utility functions, classes and constants.

.. module:: utils
   :synopsis: Utility functions, classes and constants.

A number of functions, classes and constants used throughout the application.

"""

import configparser
import datetime
import errno
import gzip
import logging
import mimetypes
import os
from random import choice, shuffle
import re
from shutil import rmtree
import smtplib
import string
from subprocess import Popen, PIPE
import unicodedata
from uuid import uuid4
import zipfile

from docutils.core import publish_parts
from markdown import Markdown
from passlib.hash import pbkdf2_sha512

from old.lib.constants import (
    RSRC_TO_DIR,
    RSRC_TO_SUBDIR,
    FORM_REFERENCE_PATTERN,
    WORD_BOUNDARY_SYMBOL
)


LOGGER = logging.getLogger(__name__)


################################################################################
# File system functions
################################################################################

def get_old_directory_path(directory_name, settings):
    """Return the absolute path to an OLD directory in /store."""
    try:
        return os.path.join(
            settings['permanent_store'],
            settings['old_name'],
            RSRC_TO_DIR[directory_name])
    except KeyError as error:
        print('Exception when joining store path to directory_name'
              ' {}'.format(directory_name))
        print(settings)
        print(error)
        return None


def get_model_directory_path(model_object, settings):
    """Return the path to a model object's directory, e.g., <Morphology 1> will
    return /store/morphologies/morphology_1/.
    """
    return os.path.join(
        get_old_directory_path(model_object.__tablename__, settings),
        '%s_%d' % (RSRC_TO_SUBDIR[model_object.__tablename__],
                   model_object.id)
    )


def get_model_file_path(model_object, model_directory_path, file_type=None):
    """Return the path to a foma-based model's file of the given type.
    This function serves to provide a consistent interface for retrieving file
    paths for parser-related files.
    :param model_object: a phonology, morphology or morphological parser model
        object.
    :param str model_directory_path: the absolute path to the directory that
        houses the files of the foma-based model (i.e., phonology, morphology
        or morphophonology).
    :param str file_type: one of 'script', 'binary', 'compiler' or 'log'.
    :returns: an absolute path to the file of the supplied type for the model
        object given.
    TODO: remove the model id suffix from the file name: redundant.  Will
        require fixes in the tests.
    TODO: file_type now defaults to None so that extensionless paths can be
        returned -- make sure this is not causing bugs.
    """
    file_type2extension = {
        'script': '.script',
        'binary': '.foma',
        'compiler': '.sh',
        'log': '.log',
        'lexicon': '.pickle',
        'dictionary': '_dictionary.pickle',
        'lm_corpus': '.txt',
        'arpa': '.lm',
        'lm_trie': '.pickle',
        'vocabulary': '.vocab'
    }
    tablename = model_object.__tablename__
    temp = {'morphologicalparser': 'morphophonology'}.get(tablename, tablename)
    file_name = RSRC_TO_SUBDIR.get(temp, temp)
    return os.path.join(
        model_directory_path,
        '%s_%d%s' % (file_name, model_object.id,
                     file_type2extension.get(file_type, ''))
    )


def create_OLD_directories(settings):
    """Make all of the required OLD directories."""
    for directory_name in ('files', 'reduced_files', 'users', 'corpora',
                           'phonologies', 'morphologies',
                           'morpheme_language_models', 'morphological_parsers'):
        make_directory_safely(get_old_directory_path(directory_name, settings))


def get_modification_time(path):
    """Return the modification time of the file or directory with ``path``.
    Return None if path doesn't exist.
    """
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


get_file_modification_time = get_modification_time


def create_user_directory(user, settings):
    """Create a directory named ``user.username`` in
    ``<permanent_store>/<old_name>/users/``.
    """
    try:
        make_directory_safely(os.path.join(
            get_old_directory_path('users', settings),
            user.username))
    except (TypeError, KeyError) as e:
        print(e)
        raise Exception('The settings dict was inadequate.')


def destroy_user_directory(user, settings):
    """Destroys a directory named ``user.username`` in
    ``<permanent_store>/<old_name>/users/``.
    """
    try:
        rmtree(os.path.join(get_old_directory_path('users', settings),
                            user.username))
    except (TypeError, KeyError):
        raise Exception('The settings dict was inadequate.')


def rename_user_directory(old_name, new_name, settings):
    try:
        old_path = os.path.join(get_old_directory_path('users', settings),
                                old_name)
        new_path = os.path.join(get_old_directory_path('users', settings),
                                new_name)
        try:
            os.rename(old_path, new_path)
        except OSError:
            make_directory_safely(new_path)
    except (TypeError, KeyError):
        raise Exception('The settings dict was inadequate.')


def destroy_all_directories(directory_name, settings):
    """Remove all subdirectories from ``<permanent_store>/<old_name>/directory_name``,
    e.g., all in /store/corpora/.
    """
    try:
        dir_path = get_old_directory_path(directory_name, settings)
        for name in os.listdir(dir_path):
            path = os.path.join(dir_path, name)
            if os.path.isdir(path):
                rmtree(path)
    except (TypeError, KeyError) as e:
        raise Exception('The settings dict was inadequate (%s).' % e)


def make_directory_safely(path):
    """Create a directory and avoid race conditions.
    Taken from
    http://stackoverflow.com/questions/273192/python-best-way-to-create-directory-if-it-doesnt-exist-for-file-write.
    Listed as ``make_sure_path_exists``.
    """
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def secure_filename(path):
    """Removes null bytes, path.sep and path.altsep from a path.
    From http://lucumr.pocoo.org/2010/12/24/common-mistakes-as-web-developer/
    """
    patt = re.compile(r'[\0%s]' % re.escape(''.join(
        [os.path.sep, os.path.altsep or ''])))
    return patt.sub('', path)


def clean_and_secure_filename(path):
    return secure_filename(path)\
        .replace("'", "")\
        .replace('"', '')\
        .replace(' ', '_')


################################################################################
# String functions
################################################################################


def to_single_space(string_):
    """Remove leading and trailing whitespace and replace newlines, tabs and
    sequences of 2 or more space to one space.
    """
    patt = re.compile(' {2,}')
    return patt.sub(' ', string_.strip().replace('\n', ' ').replace('\t', ' '))


def remove_all_white_space(string_):
    """Remove all spaces, newlines and tabs."""
    return string_.replace('\n', '').replace('\t', '').replace(' ', '')


def esc_RE_meta_chars(string_):
    # pylint: disable=anomalous-backslash-in-string
    """Escapes regex metacharacters so that we can formulate an SQL regular
    expression based on an arbitrary, user-specified inventory of
    graphemes/polygraphs::
        >>> esc_RE_meta_chars('-')
        '\\\-'
    """
    def esc(c):
        if c in '\\^$*+?{,}.|][()^-':
            return re.escape(c)
        return c
    return ''.join([esc(c) for c in string_])


def camel_case2lower_space(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1).lower()


def get_names_and_code_points(graph):
    return (graph,
            get_unicode_names(graph),
            get_unicode_code_points(graph))


def get_unicode_names(string_):
    """Returns a string of comma-delimited unicode character names corresponding
    to the characters in the input string_.
    """
    try:
        return ', '.join([unicodedata.name(c, '<no name>') for c in
                          string_])
    except TypeError:
        return ', '.join([unicodedata.name(str(c), '<no name>')
                          for c in string_])
    except UnicodeDecodeError:
        return string_


def get_unicode_code_points(string_):
    """Returns a string of comma-delimited unicode code points corresponding
    to the characters in the input string_.
    """
    return ', '.join(['U+%04X' % ord(c) for c in string_])


################################################################################
# Unicode functions
################################################################################


def normalize(unistr):
    """Return a unistr using canonical decompositional normalization (NFD)."""
    try:
        return unicodedata.normalize('NFD', unistr)
    except TypeError:
        return unicodedata.normalize('NFD', str(unistr))
    except UnicodeDecodeError:
        return unistr


def normalize_dict(dict_):
    """NFD normalize all unicode values in dict_."""
    for key in dict_:
        try:
            dict_[key] = normalize(dict_[key])
        except TypeError:
            pass
    return dict_



################################################################################
# Date & Time-related Functions
################################################################################


def now():
    return datetime.datetime.utcnow()


def round_datetime(dt):
    """Round a datetime to the nearest second."""
    discard = datetime.timedelta(microseconds=dt.microsecond)
    dt -= discard
    if discard >= datetime.timedelta(microseconds=500000):
        dt += datetime.timedelta(seconds=1)
    return dt


def datetime_string2datetime(datetime_string, rdbms_name=None,
                             mysql_engine=None):
    """Parse an ISO 8601-formatted datetime into a Python datetime object.
    Cf. http://stackoverflow.com/questions/531157/parsing-datetime-strings-with-microseconds
    Previously called ISO8601Str2datetime.
    """
    try:
        parts = datetime_string.split('.')
        years_to_seconds_string = parts[0]
        datetime_object = datetime.datetime.strptime(years_to_seconds_string,
                                                     "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    try:
        microseconds = int(parts[1])
        datetime_object = datetime_object.replace(microsecond=microseconds)
    except (IndexError, ValueError, OverflowError):
        pass
    # MySQL InnoDB tables round microseconds to the nearest second.
    if rdbms_name == 'mysql' and mysql_engine == 'InnoDB':
        datetime_object = round_datetime(datetime_object)
    return datetime_object


def date_string2date(date_string):
    """Parse an ISO 8601-formatted date into a Python date object."""
    try:
        return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        return None


def human_readable_seconds(seconds):
    return '%02dm%02ds' % (seconds / 60, seconds % 60)


################################################################################
# Miscellaneous Functions & Classes
################################################################################


def get_int(input_):
    try:
        return int(input_)
    except (ValueError, TypeError):
        return None


class FakeForm:
    pass



################################################################################
# Authorization Functions
################################################################################


def get_RDBMS_name(settings):
    try:
        SQLAlchemyURL = settings['sqlalchemy.url']
        prefix = SQLAlchemyURL.split(':')[0]
        if prefix.startswith('mysql'):
            return 'mysql'
        return prefix
    except (TypeError, KeyError):
        # WARNING The exception below should be raised during production,
        # development and testing -- however, it must be replaced with the log
        # to allow Sphinx to import the controllers and build the API docs
        # LOGGER.warning('The settings dict was inadequate.')
        raise Exception('The settings dict was inadequate.')


################################################################################
# File-specific data & functionality
################################################################################


def guess_type(filename):
    guess = mimetypes.guess_type(filename)[0]
    if guess:
        return guess.replace('audio/wav', 'audio/x-wav')
    # Hack for Windows environments where .ogg files may not be recognized
    _, ext = os.path.splitext(filename)
    if ext == '.ogg':
        return 'audio/ogg'
    return guess


def is_audio_video_file(file_):
    return 'audio' in file_.MIME_type or 'video' in file_.MIME_type


def clear_directory_of_files(directory_path):
    """Removes all files from the directory path but leaves the directory."""
    for filename in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, filename)):
            os.remove(os.path.join(directory_path, filename))


################################################################################
# Collection-specific data & functionality
################################################################################


def get_ids_of_forms_referenced(referencing_string):
    """Return a list of form ids corresponding to the form references in ``referencing_string``."""
    return [int(id) for id in
            FORM_REFERENCE_PATTERN.findall(referencing_string)]


def rst2html(string_):
    try:
        return publish_parts(string_, writer_name='html')['html_body']
    except:
        return string_


def rst2latex(string_, **kwargs):
    """Use docutils.core to return a string_ of restructuredtext as a full LaTeX
    document.
    """
    return publish_parts(string_, writer_name='latex')['whole']\
        .replace('\\usepackage[utf8]{inputenc}', '')


def md2html(string_):
    try:
        return Markdown().convert(string_)
    except:
        return string_


def get_HTML_from_contents(contents, markup_language):
    if markup_language == 'Markdown':
        return md2html(contents)
    return rst2html(contents)


def generate_salt():
    return uuid4().hex


def encrypt_password(password, salt):
    """Use PassLib's pbkdf2 implementation to generate a hash from a password.
    Cf. http://packages.python.org/passlib/lib/passlib.hash.pbkdf2_digest.html\
        #passlib.hash.pbkdf2_sha512
    """
    return pbkdf2_sha512.encrypt(password, salt=salt)


def generate_password(length=12):
    lc_letters = string.ascii_letters[:26]
    uc_letters = string.ascii_letters[26:]
    digits = string.digits
    symbols = string.punctuation.replace('\\', '')
    password = [choice(lc_letters) for i in range(3)] + \
               [choice(uc_letters) for i in range(3)] + \
               [choice(digits) for i in range(3)] + \
               [choice(symbols) for i in range(3)]
    shuffle(password)
    return ''.join(password)


################################################################################
# Email Functionality
################################################################################


def get_value_from_gmail_config(gmail_config, key, default=None):
    try:
        return gmail_config.get('DEFAULT', key)
    except configparser.Error:
        return default


class OLDSendEmailError(Exception):
    pass


def send_password_reset_email_to(user, new_password, settings, app_url,
                                 language_id='old'):
    """Send the "password reset" email to the user. If
    password_reset_smtp_server is set to smtp.gmail.com in the settings dict,
    then the email will be sent using smtp.gmail.com and the system will expect
    gmail_from_address and gmail_from_password keys in the settings dict
    valuating to a valid Gmail address/password pair. If we are testing and
    there is a test_email_to setting, then that value will be the target of the
    email -- this allows testers to verify that an email is in fact being
    received.
    """
    LOGGER.info('Attempting to send a password reset email to %s (%s).',
                user.username, user.email)
    to_address = user.email
    test_email_to = settings.get('test_email_to')
    testing = settings.get('testing') == '1'
    if testing and test_email_to:
        to_address = test_email_to
    password_reset_smtp_server = settings.get('password_reset_smtp_server')
    app_name = language_id.upper() + ' OLD' if language_id != 'old' else 'OLD'
    try:
        if password_reset_smtp_server == 'smtp.gmail.com':
            from_address = settings['gmail_from_address']
            from_password = settings['gmail_from_password']
            server = smtplib.SMTP(password_reset_smtp_server, 587)
            server.ehlo()
            server.starttls()
            server.login(from_address, from_password)
        else:
            from_address = '%s@old.org' % language_id
            server = smtplib.SMTP(password_reset_smtp_server)
    except ConnectionRefusedError:
        LOGGER.warning('Failed to instantiate an SMTP instance. Is thera an'
                       ' SMTP server installed on this machine?', exc_info=True)
        raise
    except OSError:
        LOGGER.warning('Failed to instantiate an SMTP instance', exc_info=True)
        raise
    except KeyError:
        LOGGER.warning('Failed to access required configuration', exc_info=True)
        raise
    to_addresses = [to_address]
    message = ''.join([
        'From: %s <%s>\n' % (app_name, from_address),
        'To: %s %s <%s>\n' % (user.first_name, user.last_name, to_address),
        'Subject: %s Password Reset\n\n' % app_name,
        'Your password at %s has been reset to:\n\n    %s\n\n' % (
            app_url, new_password),
        'Please change it once you have logged in.\n\n',
        '(Do not reply to this email.)'
    ])
    try:
        failures = server.sendmail(from_address, to_addresses, message)
    except OSError as exc:
        LOGGER.warning('Failed to send email: %s', exc)
        raise
    finally:
        server.quit()
    if failures:
        raise OLDSendEmailError(failures)


# def compile_query(query, settings):
#     """Return the SQLAlchemy query as a bona fide MySQL query.  Taken from
#     http://stackoverflow.com/questions/4617291/\
#     how-do-i-get-a-raw-compiled-sql-query-from-a-sqlalchemy-expression.
#     """
#     rdbms_name = get_RDBMS_name(settings)
#     if rdbms_name == 'mysql':
#         from sqlalchemy.sql import compiler
#         # TODO: MySQLdb (i.e., MySQL-python) does not work with Python 3. See
#         # http://stackoverflow.com/questions/14732533/pyramid-python3-sqlalchemy-and-mysql
#         # for drivers that do, i.e.,:
#         # - http://packages.python.org/oursql/
#         # - https://github.com/petehunt/PyMySQL/
#         # - https://launchpad.net/myconnpy
#         from MySQLdb.converters import conversions, escape
#         # an object representing the dialect; dialect.name will be 'sqlite' or
#         # 'mysql'
#         dialect = query.session.bind.dialect
#         # The query as SQL with variable names instead of values, e.g., 'WHERE
#         # form.transcription like :transcription_1'
#         statement = query.statement
#         comp = compiler.SQLCompiler(dialect, statement)
#         enc = dialect.encoding
#         params = []
#         for key in comp.positiontup:
#             val = comp.params[key]
#             if isinstance(val, str):
#                 val = val.encode(enc)
#             params.append(escape(val, conversions) )
#         return (comp.string.encode(enc) % tuple(params)).decode(enc)
#     else:
#         return str(query)


################################################################################
# Command-line processes
################################################################################


def get_subprocess(command):
    """Return a subprocess process. The command argument is a list. See
    http://docs.python.org/2/library/subprocess.html
    """
    try:
        return Popen(command, stderr=PIPE, stdout=PIPE, stdin=PIPE)
    except OSError:
        return None


def command_line_program_installed_bk(command):
    """Command is the list representing the command-line utility."""
    try:
        return bool(get_subprocess(command))
    except ValueError:
        return False


def command_line_program_installed(program):
    """Check if program is in the user's PATH
    .. note::
        I used to use Python subprocess to attempt to execute the program, but
        I think searching PATH is better.
    """
    for path in os.environ['PATH'].split(os.pathsep):
        path = path.strip('"')
        program_path = os.path.join(path, program)
        if os.path.isfile(program_path) and os.access(program_path, os.X_OK):
            return True
    return False


def mitlm_installed():
    """Check if the MITLM binaries are installed on the host."""
    return command_line_program_installed('estimate-ngram')


def ffmpeg_installed():
    """Check if the ffmpeg command-line utility is installed on the host."""
    return command_line_program_installed('ffmpeg')


def foma_installed():
    """Check if the foma and flookup command-line utilities are installed on
    the host.
    """
    return (command_line_program_installed('foma') and
            command_line_program_installed('flookup'))


def ffmpeg_encodes(format_):
    """Check if ffmpeg encodes the input format. First check if it's
    installed.
    """
    if ffmpeg_installed():
        process = Popen(['ffmpeg', '-formats'], stderr=PIPE, stdout=PIPE)
        stdout, _ = process.communicate()
        stdout = stdout.decode('utf8')
        key = 'E %s' % format_
        return key in stdout
    LOGGER.debug('ffmpeg is NOT installed')
    return False


def get_user_full_name(user):
    return '%s %s' % (user['first_name'], user['last_name'])


def foma_output_file2dict(file_, remove_word_boundaries=True):
    """Return the output of a foma apply request as a dictionary.
    :param file file_: utf8-encoded file object with tab-delimited i/o pairs.
    :param bool remove_word_boundaries: toggles whether word boundaries are removed in the output
    :returns: dictionary of the form ``{i1: [01, 02, ...], i2: [...], ...}``.
    .. note::
        The flookup foma utility returns '+?' when there is no output for a
        given input -- hence the replacement of '+?' with None below.
    """
    def word_boundary_remover(x):
        if (x[0:1], x[-1:]) == (WORD_BOUNDARY_SYMBOL, WORD_BOUNDARY_SYMBOL):
            return x[1:-1]
        return x
    remover = word_boundary_remover if remove_word_boundaries else (lambda x: x)
    result = {}
    for line in file_:
        line = line.strip()
        if line:
            input_, output_ = map(remover, line.split('\t')[:2])
            result.setdefault(input_, []).append({'+?': None}.get(
                output_, output_))
    return dict((k, filter(None, v)) for k, v in result.items())


def get_file_length(file_path):
    """Return the number of lines in a file.
    cf. http://stackoverflow.com/questions/845058/how-to-get-line-count-cheaply-in-python
    """
    with open(file_path) as file_:
        i = -1
        for i, _ in enumerate(file_):
            pass
    return i + 1


def compress_file(file_path):
    """Compress the file at ``file_path`` using ``gzip``.
    Save it in the same directory with a ".gz" extension.
    """
    with open(file_path, 'rb') as file_i:
        gzip_path = '%s.gz' % file_path
        file_o = gzip.open(gzip_path, 'wb')
        file_o.writelines(file_i)
        file_o.close()
        return gzip_path


def zipdir(path):
    """Create a compressed .zip archive of the directory at ``path``.
    Note that the relative path names of all files in the tree under ``path``
    are maintained.  E.g,. if ``path/dir/x.txt`` exists, then when ``path.zip``
    is unzipped, ``path/dir/x.txt`` will be created.
    """
    dirname = os.path.dirname(path)
    zip_path = '%s.zip' % path
    zip_file = zipfile.ZipFile(zip_path, 'w')
    for root, _, files in os.walk(path):
        for file_ in files:
            full_path = os.path.join(root, file_)
            relative_path = full_path[len(dirname):]
            zip_file.write(full_path, relative_path, zipfile.ZIP_DEFLATED)
    zip_file.close()
    return zip_path


class ZipFile(zipfile.ZipFile):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._directory_name = None

    @property
    def directory_name(self):
        if not self._directory_name:
            self._directory_name = os.path.splitext(
                os.path.basename(self.filename))[0]
        return self._directory_name

    def write_directory(self, directory_path, **kwargs):
        for root, _, files in os.walk(directory_path):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                if kwargs.get('keep_dir', False):
                    new_path = os.path.join(
                        self.directory_name,
                        os.path.basename(directory_path),
                        file_name)
                else:
                    new_path = os.path.join(self.directory_name, file_name)
                self.write(full_path, new_path, zipfile.ZIP_DEFLATED)

    def write_file(self, file_path):
        new_path = os.path.join(
            self.directory_name, os.path.basename(file_path))
        self.write(file_path, new_path, zipfile.ZIP_DEFLATED)


KIB = 1024
MIB = KIB * KIB
GIB = KIB * MIB
TIB = KIB * GIB
PIB = KIB * TIB
EIB = KIB * PIB
ZIB = KIB * EIB
YIB = KIB * ZIB


def pretty_print_bytes(num_bytes):
    """Print an integer byte count to human-readable form."""
    if num_bytes is None:
        return 'File size unavailable.'
    if num_bytes > YIB:
        return '%.3g YIB' % (num_bytes / YIB)
    if num_bytes > ZIB:
        return '%.3g ZIB' % (num_bytes / ZIB)
    if num_bytes > EIB:
        return '%.3g EIB' % (num_bytes / EIB)
    if num_bytes > PIB:
        return '%.3g PIB' % (num_bytes / PIB)
    if num_bytes > TIB:
        return '%.3g TIB' % (num_bytes / TIB)
    if num_bytes > GIB:
        return '%.3g GIB' % (num_bytes / GIB)
    if num_bytes > MIB:
        return '%.3g MIB' % (num_bytes / MIB)
    return '%.3g KIB' % (num_bytes / KIB)


def chunker(sequence, size):
    """Convert a sequence to a generator that yields subsequences of the
    sequence of size ``size``.
    """
    return (sequence[position:position + size] for position in
            range(0, len(sequence), size))
