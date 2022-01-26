"""The Online Linguistic Database (OLD) --- a Pyramid (Python) web application
for building web services (JSON REST APIs) for language documentation and
linguistic analysis.
"""
import datetime
import logging
import os
from urllib.parse import urlparse, urlunparse, ParseResult

from pyramid.authentication import (
    AuthTktAuthenticationPolicy,
    AuthTktCookieHelper,
)
from pyramid.config import Configurator
from pyramid.renderers import JSON
from pyramid.request import Request
from pyramid.settings import asbool
from pyramid_beaker import session_factory_from_settings
from sqlalchemy.orm import scoped_session

from old.models import Model, get_session_factory, get_engine, Tag
from old.lib.constants import ISO_STRFTIME, OLD_NAME_DFLT
from old.lib.foma_worker import start_foma_worker


LOGGER = logging.getLogger(__name__)


__version__ = '2.0.0'


def date_adapter(obj, request):
    # pylint: disable=unused-argument
    return obj.isoformat()


def datetime_adapter(obj, request):
    # pylint: disable=unused-argument
    return obj.strftime(ISO_STRFTIME)


def get_json_renderer():
    json_renderer = JSON()
    json_renderer.add_adapter(datetime.datetime, datetime_adapter)
    json_renderer.add_adapter(datetime.date, date_adapter)
    return json_renderer



class OLDHeadersMiddleware(object):
    """Middleware transforms ``Content-Type: text/html`` headers to
    ``Content-Type: application/json``.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):

        def custom_start_response(status, headers, exc_info=None):
            new_headers = dict(headers)
            if dict(headers).get('Content-Type') == 'text/html; charset=utf-8':
                new_headers['Content-Type'] = 'application/json'

            # CORS stuff. See
            # http://stackoverflow.com/questions/2771974/
            # modify-headers-in-pylons-using-middleware
            origin = environ.get('HTTP_ORIGIN')
            # In the test case, there will be no origin. So we set it to
            # *anything* here, so that WebTest's lint.py doesn't choke on
            # `None`.
            if not origin:
                origin = 'http://localhost:9000'
            new_headers['Access-Control-Allow-Origin'] = origin
            # Use this header to indicate that cookies should be included in
            # CORS requests.
            new_headers['Access-Control-Allow-Credentials'] = 'true'
            new_headers['Access-Control-Allow-Methods'] = ', '.join((
                'GET',
                'HEAD',
                'POST',
                'PUT',
                'DELETE',
                'TRACE',
                'CONNECT',
                'COPY',
                'OPTIONS',
                'SEARCH'
            ))
            new_headers['Access-Control-Allow-Headers'] = ', '.join((
                'Content-Type',
                'content-type',
                'If-Modified-Since'
            ))
            # This causes the preflight result to be cached for specified
            # milliseconds.
            # NOTE: Comment out during development
            # new_headers['Access-Control-Max-Age'] = '12345'

            # Access-Control-Expose-Headers (optional)
            # The XMLHttpRequest 2 object has a getResponseHeader() method that
            # returns the value of a particular response header. During a CORS
            # request, the getResponseHeader() method can only access simple
            # response headers. Simple response headers are defined as follows:
            #
            #    Cache-Control
            #    Content-Language
            #    Content-Type
            #    Expires
            #    Last-Modified
            #    Pragma

            # If you want clients to be able to access other headers, you have
            # to use the Access-Control-Expose-Headers header. The value of
            # this header is a comma-delimited list of response headers you
            # want to expose to the client.
            # NOTE: Commented this out for debuggin ...
            new_headers['Access-Control-Expose-Headers'] = (
                'Access-Control-Allow-Origin, Access-Control-Allow-Credentials')
            headers = list(new_headers.items())
            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


def expandvars_dict(settings):
    """Expands all environment variables in a settings dictionary."""
    return {key: os.path.expandvars(value) for key, value in settings.items()}


class DBSessionFactoryRegistry(object):
    """Stores SQLAlchemy database session factories, keyed by SQLAlchemy URL."""

    def __init__(self):
        self.session_factories = {}

    def get_session(self, settings):
        """Return a SQLAlchemy database session factory.

        :param settings: The OLD configuration settings
        :type settings: dict.
        :returns: A SQLAlchemy session factory (callable)
        """
        sqlalchemy_url = settings['sqlalchemy.url']
        try:
            return self.session_factories[sqlalchemy_url]
        except KeyError:
            self.session_factories[sqlalchemy_url] = scoped_session(
                get_session_factory(get_engine(settings)))
            return self.session_factories[sqlalchemy_url]


db_session_factory_registry = DBSessionFactoryRegistry()


class BeakerSessionFactoryRegistry(object):

    def __init__(self):
        self.session_factories = {}

    def get_session(self, settings):
        old_name = settings['old_name']
        try:
            return self.session_factories[old_name]
        except KeyError:
            # The following changes may be needed. See this issue in the
            # original OLD: https://github.com/dativebase/old/issues/94
            # settings['session.samesite'] = 'None'
            # settings['session.secure'] = True
            self.session_factories[old_name] = session_factory_from_settings(
                settings)
            return self.session_factories[old_name]


beaker_session_factory = BeakerSessionFactoryRegistry()


class MyRequest(Request):
    """Custom request class whose purpose is to override the ``dbsession``
    property so that it returns a db session for the database specified in the
    first/root element of the URL path. For example, a request containing the
    path ``'/blaold/forms/1'`` implies that the database being accessed is
    called ``'blaold'``, while a request containing the path
    ``'/okaold/forms/1'`` implies that the database being accessed is called
    ``'okaold'``.
    """
    # pylint: disable=no-member

    def __init__(self, environ):
        super().__init__(environ)
        self._dbsession = None
        self._beakersession = None
        self._old_name = None
        self._sqlalchemy_url = None
        def session_getter(settings):
            return db_session_factory_registry.get_session(settings)()
        self.session_getter = session_getter

    @property
    def old_name(self):
        """The name of this OLD is extracted from the user-provided URL on
        every request. This is necessary because the OLD is stateless: all
        state is held in the db and a location on the filesystem, which are
        specified by the user-provided URL.
        """
        if self._old_name:
            return self._old_name
        self._old_name = urlparse(self.url).path.lstrip('/').split('/')[0]
        return self._old_name

    @property
    def sqlalchemy_url(self):
        if self._sqlalchemy_url:
            return self._sqlalchemy_url
        self.registry.settings['old_name'] = self.old_name
        self._sqlalchemy_url = build_sqlalchemy_url(self.registry.settings)
        return self._sqlalchemy_url

    @property
    def dbsession(self):
        """The dbsession property should return a different dbsession depending
        on the first/root element of the URL path, e.g.,

        - /blaold/forms/1 should return form 1 in the Blackfoot OLD
        - /okaaold/forms/1 should return form 1 in the Okanagan OLD
        """
        if self._dbsession:
            return self._dbsession
        self.registry.settings['sqlalchemy.url'] = self.sqlalchemy_url
        self._dbsession = db_session_factory_registry.get_session(
            self.registry.settings)()
        self.add_finished_callback(self.close_dbsession)
        return self._dbsession

    def close_dbsession(self, request):
        # pylint: disable=unused-argument
        self._dbsession.commit()

    @property
    def session(self):
        """The (beaker) session should return a different session depending
        on the first/root element of the URL path.
        """
        if self._beakersession:
            return self._beakersession
        self.registry.settings['session.url'] = self.sqlalchemy_url
        if os.path.basename(self.registry.settings[
                'session.lock_dir'].rstrip('/')) != self.old_name:
            self.registry.settings['session.lock_dir'] = os.path.join(
                os.path.dirname(self.registry.settings['session.lock_dir']),
                self.registry.settings['old_name'])
        if not self.registry.settings['session.key'].endswith(
                '_{}'.format(self.old_name)):
            self.registry.settings['session.key'] = '{}_{}'.format(
                self.registry.settings['session.key'],
                self.registry.settings['old_name'])
        self._beakersession = beaker_session_factory.get_session(
            self.registry.settings)(self)
        self.add_finished_callback(self.save_beakersession)
        return self._beakersession

    def save_beakersession(self, request):
        # pylint: disable=unused-argument
        self._beakersession.save()


# The environment variables in the keys of this dict, if set, will override the
# corresponding values in the Pyramid settings dict. See
# ``override_settings_with_env_vars``.
ENV_VAR_MAP = {
    # Database
    'OLD_DB_RDBMS': 'db.rdbms',
    'OLD_DB_USER': 'db.user',
    'OLD_DB_PASSWORD': 'db.password',
    'OLD_DB_HOST': 'db.host',
    'OLD_DB_PORT': 'db.port',
    'OLD_DB_DIRPATH': 'db.dirpath',  # For SQLite only
    'SQLALCHEMY_POOL_RECYCLE': 'sqlalchemy.pool_recycle',
    # Testing
    'OLD_NAME_TESTS': 'old_name_tests',
    'OLD_NAME_2_TESTS': 'old_name_2_tests',
    'OLD_TESTING': 'testing',
    # General OLD config
    'OLD_READONLY': 'readonly',
    'OLD_CREATE_REDUCED_SIZE_FILE_COPIES': 'create_reduced_size_file_copies',
    'OLD_PREFERRED_LOSSY_AUDIO_FORMAT': 'preferred_lossy_audio_format',
    'OLD_PERMANENT_STORE': 'permanent_store',
    'OLD_ADD_LANGUAGE_DATA': 'add_language_data',
    'OLD_EMPTY_DATABASE': 'empty_database',
    # Email
    'OLD_PASSWORD_RESET_SMTP_SERVER': 'password_reset_smtp_server',
    'OLD_TEST_EMAIL_TO': 'test_email_to',
    'OLD_GMAIL_FROM_ADDRESS': 'gmail_from_address',
    'OLD_GMAIL_FROM_PASSWORD': 'gmail_from_password',
    # Beaker session stuff
    'OLD_SESSION_TYPE': 'session.type',
    'OLD_SESSION_URL': 'session.url',
    'OLD_SESSION_DATA_DIR': 'session.data_dir',
    'OLD_SESSION_LOCK_DIR': 'session.lock_dir',
    'OLD_SESSION_KEY': 'session.key',
    'OLD_SESSION_SAMESITE': 'session.samesite',
    'OLD_SESSION_SECRET': 'session.secret',
    'OLD_SESSION_SECURE': 'session.secure',
    'OLD_SESSION_COOKIE_EXPIRES': 'session.cookie_expires'
}


DB_SCHEME = 'mysql+pymysql'


def build_sqlalchemy_url(settings):
    old_name = settings['old_name']
    if settings['db.rdbms'] == 'mysql':
        return urlunparse(ParseResult(
            scheme=DB_SCHEME,
            netloc='{user}:{password}@{host}:{port}'.format(
                user=settings['db.user'],
                password=settings['db.password'],
                host=settings['db.host'],
                port=settings['db.port']),
            path='/{old_name}'.format(
                old_name=old_name),
            params='',
            query='',
            fragment=''))
    _, ext = os.path.splitext(old_name)
    if not ext:
        old_name = '{old_name}.sqlite'.format(old_name=old_name)
    return 'sqlite:///{dirpath}/{old_name}'.format(
        dirpath=settings['db.dirpath'],
        old_name=old_name)


def override_settings_with_env_vars(settings):
    """Override any values in the ``settings`` dict with the value of the
    corresponding environment variable, if it is set.
    """
    for env_var, settings_key in ENV_VAR_MAP.items():
        env_var_val = os.getenv(env_var)
        if env_var_val is None:
            continue
        settings[settings_key] = env_var_val
    settings['old_name'] = settings.get(
        'old_name', settings.get('old_name_tests', OLD_NAME_DFLT))
    settings['sqlalchemy.url'] = build_sqlalchemy_url(settings)
    return settings


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""
    # pylint: disable=unused-argument
    start_foma_worker()
    settings = override_settings_with_env_vars(settings)
    config = Configurator(settings=settings, request_factory=MyRequest)
    config.include('.routes')
    config.add_renderer('json', get_json_renderer())
    return OLDHeadersMiddleware(config.make_wsgi_app())
