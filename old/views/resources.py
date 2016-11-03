import inflect
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy.exc import DBAPIError
from pyramid.httpexceptions import (
    HTTPForbidden,
    HTTPFound,
    HTTPNotFound,
)



def authenticate(target):
    """Authentication decorator.

    If user is not logged in and tries to call a controller action with this
    decorator, then the response header status will be ``401 Unauthorized`` and
    the response body will be ``{error: "401 Unauthorized"}``.
    """

    def wrapper(target, *args, **kwargs):
        if getattr(session.get('user'), 'username', None):
            return target(*args, **kwargs)
        response.status_int = 401
        return {'error': 'Authentication is required to access this resource.'}

    return decorator(wrapper)(target)


class Resources:

    p = inflect.engine()
    p.classical()

    def __init__(self, request):
        self.request = request
        self.collection_name = self.__class__.__name__.lower()
        self.member_name = self.p.singular_noun(self.collection_name)
        self._query_builder = None

    @property
    def query_builder(self):
        if self._query_builder:
            return self._query_builder
        model_name = self.p.singular_noun(self.__class__.__name__)
        self._query_builder = SQLAQueryBuilder(
            model_name, config=request.registry.settings)
        return self._query_builder

    def index(self):
        user = self.request.user
        return {'resource': 'resource'}
        #return Response('View all {}'.format(self.collection_name))

    def create(self):
        return Response('Create a new {}'.format(self.member_name))

    def new(self):
        # return Response('Get info to create a new {}'.format(self.member_name))
        return {}

    def update(self):
        # expect ``id`` in PUT params
        return Response('Update an existing {}'.format(self.member_name))

    def delete(self):
        # expect ``id`` in DELETE params
        return Response('Delete an existing {}'.format(self.member_name))

    def show(self):
        # expect ``id`` in GET params
        return Response('Show an existing {}'.format(self.member_name))

    def edit(self):
        # expect ``id`` in GET params
        return Response('Get info to create an existing {}'.format(self.member_name))
