from pyramid.response import Response
from pyramid.view import view_config
from old.views.resources import Resources
from sqlalchemy.exc import DBAPIError

from ..models import Form


class Forms(Resources):

    def index(self):
        user = self.request.user
        return {'resource': 'forms'}
        #return Response('View all {}'.format(self.collection_name))
