import datetime
from old.models import Model
from pyramid.authentication import (
    AuthTktAuthenticationPolicy,
    AuthTktCookieHelper,
)
from pyramid.config import Configurator
from pyramid.renderers import JSON
from pyramid.security import (
    unauthenticated_userid,
    Everyone,
    Authenticated
)
from pyramid.settings import asbool


def asint(setting):
    """Convert variable to int, leave None unchanged"""
    if setting is None:
        return setting
    else:
        return int(setting)


"""
class MyAuthenticationPolicy(object):

    def __init__(self, settings):
        self.cookie = AuthTktCookieHelper(
            settings.get('auth.secret'),
            cookie_name=settings.get('auth.token') or 'auth_tkt',
            secure=asbool(settings.get('auth.secure')),
            timeout=asint(settings.get('auth.timeout')),
            reissue_time=asint(settings.get('auth.reissue_time')),
            max_age=asint(settings.get('auth.max_age')),
    )

def remember(self, request, principal, **kw):
    return self.cookie.remember(request, principal, **kw)

def forget(self, request):
    return self.cookie.forget(request)

def unauthenticated_userid(self, request):
    result = self.cookie.identify(request)
    if result:
        return result['userid']

def authenticated_userid(self, request):
    if request.user:
        return request.user.id

def effective_principals(self, request):
    principals = [Everyone]
    user = request.user
    if user:
        principals += [Authenticated, 'u:%s' % user.id]
        principals.extend(('g:%s' % g.name for g in user.groups))
    return principals
"""



def old_model_adapter(obj, request):
    try:
        return obj.get_dict()
    except AttributeError:
        r = obj.__dict__.copy()
        if '_sa_instance_state' in r:
            del r['_sa_instance_state']
        return r


def datetime_adapter(obj, request):
    return obj.isoformat()


def get_json_renderer():
    json_renderer = JSON()
    json_renderer.add_adapter(datetime.datetime, datetime_adapter)
    json_renderer.add_adapter(datetime.date, datetime_adapter)
    json_renderer.add_adapter(Model, old_model_adapter)
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
            except Exception as e:
                origin = 'http://dativebeta.lingsync.org'
            # In the test case, there will be no origin. So we set it to
            # *anything* here, so that WebTest's lint.py doesn't choke on
            # `None`.
            if not origin:
                origin = 'http://localhost:9000'

            # new_headers['Access-Control-Allow-Origin'] = 'http://localhost:9000'
            new_headers['Access-Control-Allow-Origin'] = origin

            # Use this header to indicate that cookies should be included in CORS requests.
            new_headers['Access-Control-Allow-Credentials'] = 'true'

            # What was here before: new_headers['Access-Control-Allow-Methods'] = 'OPTIONS, GET, POST'
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

            # What was here before: new_headers['Access-Control-Allow-Headers'] = 'Content-Type, content-type, Depth, User-Agent, X-File-Size, X-Requested-With, If-Modified-Since, X-File-Name, Cache-Control'
            new_headers['Access-Control-Allow-Headers'] = ', '.join((
                'Content-Type',
                'content-type',
                'If-Modified-Since'
            ))

            # This causes the preflight result to be cached for specified
            # milliseconds. From LingSync's CouchDB config
            # NOTE: Comment out during development
            #new_headers['Access-Control-Max-Age'] = '12345'

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
            #
            # If you want clients to be able to access other headers, you have
            # to use the Access-Control-Expose-Headers header. The value of
            # this header is a comma-delimited list of response headers you
            # want to expose to the client.
            # NOTE: Commented this out for debuggin ...
            new_headers['Access-Control-Expose-Headers'] = \
                'Access-Control-Allow-Origin, Access-Control-Allow-Credentials'

            headers = list(new_headers.items())

            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


def authenticate(userid, request):
    user = request.user
    if user is not None:
        return []
    return None


def get_user(request):
    # the below line is just an example, use your own method of
    # accessing a database connection here (this could even be another
    # request property such as request.db, implemented using this same
    # pattern).
    print('in get_user')
    print('request is...')
    print(request)
    userid = unauthenticated_userid(request)
    if userid is not None:
        return request.dbsession.query(User).get(userid)


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.

    TODO:
    # start foma worker -- used for long-running tasks like FST compilation
    foma_worker = start_foma_worker()
    """
    config = Configurator(settings=settings)
    config.include('pyramid_beaker')
    config.include('pyramid_jinja2')
    config.include('.models')
    config.include('.routes')
    config.add_renderer('json', get_json_renderer())
    config.add_request_method(get_user, 'user', reify=True)
    config.scan()
    return OLDHeadersMiddleware(config.make_wsgi_app())
