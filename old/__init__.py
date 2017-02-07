# Copyright 2017 Joel Dunham
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

"""The Online Linguistic Database (OLD) is software for linguistic fieldwork.
An OLD (instance) is a specific deployment of the OLD software as a RESTful web
service used to document and analyze a particular (usually language-specific)
data set.

"""

import datetime
import logging
import mimetypes
import os

from pyramid.authentication import (
    AuthTktAuthenticationPolicy,
    AuthTktCookieHelper,
)
from pyramid.config import Configurator
from pyramid.renderers import JSON
from pyramid.settings import asbool

from old.models import Model
from old.lib.constants import ISO_STRFTIME
from old.lib.foma_worker import start_foma_worker
from old.lib.export_worker import start_export_worker

# Necessary so that static view at exports/public/ serves .jsonld files with
# the correct Content-Type header.
mimetypes.add_type('application/json', '.jsonld')

LOGGER = logging.getLogger(__name__)

__version__ = '2.0.0'


def date_adapter(obj, request):
    return obj.isoformat()


def datetime_adapter(obj, request):
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

            # CORS stuff. See http://stackoverflow.com/questions/2771974/modify-headers-in-pylons-using-middleware
            try:
                origin = environ.get('HTTP_ORIGIN')
            except Exception as error:
                LOGGER.error(
                    'Exception when calling `environ.get(\'HTTP_ORIGIN\')`: %s'
                    ' %s', error.__class__.__name__, error)

                origin = 'http://dativebeta.lingsync.org'
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


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""
    start_foma_worker()
    start_export_worker()
    config = Configurator(settings=settings)
    config.include('pyramid_beaker')
    config.include('pyramid_jinja2')
    config.include('.models')
    config.include('.routes')
    public_exports_path = os.path.join(settings['exports_dir'], 'public')
    config.add_static_view(name='public', path=public_exports_path)
    config.add_renderer('json', get_json_renderer())
    config.scan()
    return OLDHeadersMiddleware(config.make_wsgi_app())
