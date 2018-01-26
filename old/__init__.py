"""The Online Linguistic Database (OLD) --- a Pyramid (Python) web application
for building web services (JSON REST APIs) for language documentation and
linguistic analysis.
"""
import datetime
import logging
import os
from urllib.parse import urlparse, urlunparse

from pyramid.authentication import (
    AuthTktAuthenticationPolicy,
    AuthTktCookieHelper,
)
from pyramid.config import Configurator
from pyramid.renderers import JSON
from pyramid.request import Request
from pyramid.settings import asbool
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

    def __init__(self):
        self.session_factories = {}

    def get_session(self, settings):
        sqlalchemy_url = settings['sqlalchemy.url']
        try:
            return self.session_factories[sqlalchemy_url]
        except KeyError:
            self.session_factories[sqlalchemy_url] = scoped_session(
                get_session_factory(get_engine(settings)))
            return self.session_factories[sqlalchemy_url]


db_session_factory_registry = DBSessionFactoryRegistry()


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
        self._session = None
        def session_getter(settings):
            return db_session_factory_registry.get_session(settings)()
        self.session_getter = session_getter

    def get_old_name(self):
        return urlparse(self.url).path.lstrip('/').split('/')[0]

    @staticmethod
    def get_new_path(scheme, path, old_name):
        if scheme == 'sqlite':
            return os.path.join(os.path.dirname(path), '{}.sqlite'.format(old_name))
        return old_name

    def get_sqlalchemy_url(self):
        old_name = self.get_old_name()
        settings_sqlalchemy_url = self.registry.settings['sqlalchemy.url']
        if old_name == OLD_NAME_DFLT:
            return settings_sqlalchemy_url
        parsed_sqla_url = urlparse(settings_sqlalchemy_url)
        new_path = self.get_new_path(parsed_sqla_url.scheme,
                                     parsed_sqla_url.path, old_name)
        parsed_sqla_url = parsed_sqla_url._replace(path=new_path)
        return urlunparse(parsed_sqla_url).replace('sqlite:', 'sqlite://', 1)

    @property
    def dbsession(self):
        """The dbsession property should return a different dbsession depending
        on the first/root element of the URL path, e.g.,

        - /blaold/forms/1 should return form 1 in the Blackfoot OLD
        - /okaaold/forms/1 should return form 1 in the Okanagan OLD
        """
        settings = {k: v for k, v in self.registry.settings.items()
                    if k.startswith('sqlalchemy.')}
        settings['sqlalchemy.url'] = self.get_sqlalchemy_url()
        self._session = db_session_factory_registry.get_session(settings)()
        self.add_finished_callback(self.close_dbsession)
        return self._session

    def close_dbsession(self, request):
        # pylint: disable=unused-argument
        self._session.commit()


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""
    # pylint: disable=unused-argument
    start_foma_worker()
    settings = expandvars_dict(settings)
    config = Configurator(settings=settings, request_factory=MyRequest)
    config.include('pyramid_beaker')
    config.include('pyramid_jinja2')
    config.include('.routes')
    config.add_renderer('json', get_json_renderer())
    config.scan()
    return OLDHeadersMiddleware(config.make_wsgi_app())
