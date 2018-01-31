import logging

from pyramid.view import (
    view_config,
    notfound_view_config
)


LOGGER = logging.getLogger(__name__)


@notfound_view_config(renderer='json')
def notfound_view(request):
    request.response.status = 404
    #LOGGER.warning('No handler found for %s', request.current_route_url())
    return {'error': 'The resource could not be found.'}


@view_config(context=Exception, renderer='json')
def error(exc, request):
    LOGGER.error(exc, exc_info=True)
    request.response.status = 500
    return {'error': 'Internal Server Error'}
