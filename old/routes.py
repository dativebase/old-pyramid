import logging
import os

import inflect
from pyramid.response import Response

from old.lib.constants import (
    UNAUTHORIZED_MSG,
    UNAUTHENTICATED_MSG,
)
import old.lib.pyramid_routehelper as pyrh
from old.models import User


LOGGER = logging.getLogger(__name__)


p = inflect.engine()
p.classical()

# This dict is configuration for the resources that the OLD exposes. All of the
# keys correspond to resources that will receive the standard REST Atom
# methods/actions (create, new, index, show, update, edit, and delete). The
# config dict value signals additional actions on the resource, e.g., search or
# history. See the ``add_resource`` function for implementation.
RESOURCES = {
    'applicationsetting': {},
    'collection': {
        'searchable': True,
        'history': True
    },
    'collectionbackup': {'searchable': True},
    'corpus': {
        'searchable': True,
        'history': True
    },
    'corpusbackup': {'searchable': True},
    'elicitationmethod': {},
    'file': {'searchable': True},
    'form': {
        'searchable': True,
        'history': True
    },
    'formsearch': {'searchable': True},
    'formbackup': {'searchable': True},
    'keyboard': {'searchable': True},
    'language': {'searchable': True},
    'morphemelanguagemodel': {
        'searchable': True,
        'history': True
    },
    'morphemelanguagemodelbackup': {},
    'morphologicalparser': {
        'searchable': True,
        'history': True
    },
    'morphologicalparserbackup': {},
    'morphology': {
        'searchable': True,
        'history': True
    },
    'morphologybackup': {},
    'orthography': {},
    'page': {'searchable': True},
    'phonology': {
        'searchable': True,
        'history': True
    },
    'phonologybackup': {},
    'source': {'searchable': True},
    'speaker': {},
    'syntacticcategory': {},
    'tag': {},
    'user': {},
}


def fix_for_tests(request):
    """Modifies the request if certain environment variables are present;
    purpose is to simulate different login states for testing.
    """
    if os.path.basename(request.registry.settings.get('__file__', '')) == 'test.ini':
        if 'test.authentication.role' in request.environ:
            role = request.environ['test.authentication.role']
            user = request.dbsession.query(User).filter(User.role==role).first()
            if user:
                request.session['user'] = user.get_dict()
        elif 'test.authentication.id' in request.environ:
            user = request.dbsession.query(User).get(
                request.environ['test.authentication.id'])
            if user:
                request.session['user'] = user.get_dict()
        else:
            if 'user' in request.session:
                del request.session['user']
    return request


UNAUTHENTICATED_RESP = Response(
    json=UNAUTHENTICATED_MSG,
    content_type='application/json',
    status_code=401
)

UNAUTHORIZED_RESP = Response(
    json=UNAUTHORIZED_MSG,
    content_type='application/json',
    status_code=403
)


def authenticate(func):
    def wrapper(context, request):
        LOGGER.info('Authenticate decorator on %s', request.current_route_url())
        request = fix_for_tests(request)
        user = request.session.get('user')
        if user:
            LOGGER.info('User authenticated: %s %s %s', user['first_name'],
                        user['last_name'], user['id'])
            return func(context, request)
        else:
            LOGGER.info('No user; failed to authenticate.')
            return UNAUTHENTICATED_RESP
    return wrapper


def authorize(roles, users=None, user_id_is_args1=False):
    """Authorization decorator.  If user tries to request a resource action
    but has insufficient authorization, this decorator will respond with a
    header status of '403 Forbidden' and a JSON object explanation. The user is
    unauthorized if *any* of the following are true:

    - the user does not have one of the roles in ``roles``
    - the user's id does not match one of the ids in ``users``
    - the user does not have the same id as the id of the entity the action
      takes as argument

    Example 1: (user must be an administrator or a contributor)::

        >>> authorize(['administrator', 'contributor'])

    Example 2: (user must be either an administrator or the contributor with Id
    2)::

        >>> authorize(['administrator', 'contributor'], [2])

    Example 3: (user must have the same ID as the entity she is trying to
    affect)::

        >>> authorize(['administrator', 'contributor', 'viewer'],
                      user_id_is_args1=True)
    """
    def _authorize(func):
        def wrapper(context, request):
            LOGGER.info('In Authorize decorator')
            # Check for authorization via role.
            user = request.session['user']
            role = user['role']
            if role in roles:
                # Check for authorization via user.
                if (    users and role != 'administrator'
                        and user['id'] not in users):
                    LOGGER.info('Failed authorization check; user id %s not'
                                ' in %s.', user['id'], users)
                    return UNAUTHORIZED_RESP
                # Check whether the user id equals the id argument in the URL
                # path. This is useful, e.g., when a user can only edit their
                # own personal page.
                if (    user_id_is_args1 and
                        role != 'administrator' and
                        int(user['id']) != int(request.matchdict['id'])):
                    LOGGER.info('Failed authorization check; user id %s not'
                                ' %s.', user['id'], request.matchdict['id'])
                    return UNAUTHORIZED_RESP
                return func(context, request)
            else:
                LOGGER.info('Failed authorization check; user role %s not'
                            ' in %s.', role, roles)
                return UNAUTHORIZED_RESP
        return wrapper
    return _authorize


def get_auth_decorators(resource, action):
    """TODO: there are resource-specific authorization controls."""
    if action in ('create', 'new', 'update', 'edit', 'delete'):
        if resource == 'user':
            if action in ('update', 'edit'):
                return (authenticate,
                        authorize(['administrator', 'contributor', 'viewer'],
                                  user_id_is_args1=True))
            return (authenticate, authorize(['administrator']))
        elif resource == 'applicationsetting':
            if action in ('update', 'edit', 'create', 'new', 'delete'):
                return (authenticate, authorize(['administrator']))
            return authenticate
        return (authenticate, authorize(['administrator', 'contributor']))
    return authenticate


def get_search_config(collection_name):
    """Return the route name, path, request method, and class attribute for
    configuring search across the resource with collection name
    ``collection_name``.
    """
    if collection_name == 'corpora':
        return (
            (
                'search_corpus_forms',
                '/corpora/{id}',
                'SEARCH',
                'search'
            ), (
                'search_corpus_forms_post',
                '/corpora/{id}/search',
                'POST',
                'search'
            ), (
                'new_search_corpus_forms',
                '/corpora/new_search',
                'GET',
                'new_searchx'
            )
        )
    return (
        (
            'search_{}'.format(collection_name),
            '/{}'.format(collection_name),
            'SEARCH',
            'search'
        ), (
            'search_{}_post'.format(collection_name),
            '/{}/search'.format(collection_name),
            'POST',
            'search'
        ), (
            'new_search_{}'.format(collection_name),
            '/{}/new_search'.format(collection_name),
            'GET',
            'new_search'
        )
    )


def add_resource(config, member_name, rsrc_config=None):
    """Add route/view configuration to ``config`` that exposes ``member_name``
    as a RESTful resource. The ``rsrc_config`` dict provides additional
    configuration of the resource; e.g., setting 'searchable' to ``True`` will
    set up search-related routes. Configuration should be centralized in the
    ``RESOURCES`` constant.
    authentication GET-only
    """
    if not rsrc_config:
        rsrc_config = {}
    collection_name = p.plural(member_name)
    class_name = collection_name.capitalize()
    view_callable = 'old.views.{}.{}'.format(collection_name, class_name)

    if rsrc_config.get('searchable', False):
        for route_name, path, request_method, attr in get_search_config(
                collection_name):
            config.add_route(route_name, path, request_method=request_method)
            config.add_view(view_callable,
                            attr=attr,
                            route_name=route_name,
                            request_method=request_method,
                            renderer='json',
                            decorator=get_auth_decorators(member_name, attr))

    if rsrc_config.get('history', False):
        route_name, path, request_method, attr = (
            '{}_history'.format(member_name),
            '/{}/{{id}}/history'.format(collection_name),
            'GET',
            'history'
        )
        config.add_route(route_name, path, request_method=request_method)
        config.add_view(view_callable,
                        attr=attr,
                        route_name=route_name,
                        request_method=request_method,
                        renderer='json',
                        decorator=get_auth_decorators(member_name, attr))

    for action in ('create', 'index', 'new', 'edit', 'delete', 'update',
                   'show'):
        route_name = '{}_{}'.format(action, member_name)
        if action == 'index':
            route_name = '{}_{}'.format(action, collection_name)
        path = '/{}'.format(collection_name)
        if action == 'new':
            path = '{}/new'.format(path)
        elif action == 'edit':
            path = '{}/{{id}}/edit'.format(path)
        elif action in ('delete', 'update', 'show'):
            path = '{}/{{id}}'.format(path)
        request_method = {'create': 'POST', 'delete': 'DELETE',
                          'update': 'PUT'}.get(action, 'GET')
        config.add_route(route_name, path, request_method=request_method)
        config.add_view(view_callable,
                        attr=action,
                        route_name=route_name,
                        request_method=request_method,
                        renderer='json',
                        decorator=get_auth_decorators(member_name, action))

def includeme(config):
    # Pyramid boilerplate
    # config.add_static_view('static', 'static', cache_max_age=3600)
    # config.add_route('home', '/')

    # The ErrorController route (handles 404/500 error pages); it should
    # likely stay at the top, ensuring it can always be resolved
    config.add_route('error_action', '/error/{action}')
    config.add_route('error_id_action', '/error/{id}/{action}')

    config.add_route('info', '/', request_method='GET')
    config.add_view('old.views.info.Info',
                    attr='index',
                    route_name='info',
                    request_method='GET',
                    renderer='json')

    # CORS preflight OPTIONS requests---don't interfere with them
    # TODO: test if this works.
    def cors(request):
        request.response.status_int = 204
        return request.response
    config.add_route('cors_proceed', '/*garbage', request_method='OPTIONS')
    config.add_view(cors,
                    route_name='cors_proceed',
                    request_method='OPTIONS')

    # To search across corpora, you need to issue a SEARCH/POST
    # /corpora/searchcorpora request. Corpora.search_corpora should handle
    # this.
    config.add_route('search_corpora', '/corpora/searchcorpora',
                     request_method=('POST', 'SEARCH'))
    config.add_view('old.views.corpora.Corpora',
                    attr='search_corpora',
                    route_name='search_corpora',
                    request_method=('POST', 'SEARCH'),
                    renderer='json',
                    decorator=authenticate)

    config.add_route('new_search_corpora',
                     '/corpora/new_search_corpora',
                     request_method='GET')
    config.add_view('old.views.corpora.Corpora',
                    attr='new_search_corpora',
                    route_name='new_search_corpora',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)

    config.add_route('corpora_word_category_sequences',
                     '/corpora/{id}/get_word_category_sequences',
                     request_method='GET')
    config.add_view('old.views.corpora.Corpora',
                    attr='get_word_category_sequences',
                    route_name='corpora_word_category_sequences',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)

    # To search within the forms of a corpus, use one of the following two:
    # Pylons: controller='corpora', action='search',
    # config.add_route('search_corpus', '/corpora/{id}', request_method='SEARCH')
    # config.add_route('search_corpus_post', '/corpora/{id}/search',
    #                  request_method='POST')

    config.add_route('corpus_serve_file',
                     '/corpora/{id}/servefile/{file_id}',
                     request_method='GET')
    config.add_view('old.views.corpora.Corpora',
                    attr='servefile',
                    route_name='corpus_serve_file',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)

    config.add_route('corpus_tgrep2',
                     '/corpora/{id}/tgrep2',
                     request_method=('POST', 'SEARCH'))
    config.add_view('old.views.corpora.Corpora',
                    attr='tgrep2',
                    route_name='corpus_tgrep2',
                    request_method=('POST', 'SEARCH'),
                    renderer='json',
                    decorator=authenticate)

    config.add_route('corpus_writetofile',
                     '/corpora/{id}/writetofile',
                     request_method='PUT')
    config.add_view('old.views.corpora.Corpora',
                    attr='writetofile',
                    route_name='corpus_writetofile',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))

    config.add_route('serve_file', '/files/{id}/serve', request_method='GET')
    config.add_view('old.views.files.Files',
                    attr='serve',
                    route_name='serve_file',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)

    config.add_route('serve_reduced_file', '/files/{id}/serve_reduced',
                     request_method='GET')
    config.add_view('old.views.files.Files',
                    attr='serve_reduced',
                    route_name='serve_reduced_file',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)


    config.add_route('remember_forms', '/forms/remember', request_method='POST')
    config.add_view('old.views.forms.Forms',
                    attr='remember',
                    route_name='remember_forms',
                    request_method='POST',
                    renderer='json',
                    decorator=authenticate)

    config.add_route('update_morpheme_references',
                     '/forms/update_morpheme_references',
                     request_method='PUT')
    config.add_view('old.views.forms.Forms',
                    attr='update_morpheme_references',
                    route_name='update_morpheme_references',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate, authorize(['administrator'])))

    config.add_route('authenticate', '/login/authenticate')
    config.add_route('logout', '/login/logout')
    config.add_route('email_reset_password', '/login/email_reset_password',
                     request_method='POST')

    # Pylons: controller='morphemelanguagemodels', action='compute_perplexity'
    config.add_route('morpheme_lm_compute_perplexity',
                     '/morphemelanguagemodels/{id}/compute_perplexity',
                     request_method='PUT')
    config.add_route('generate_morpheme_lm',
                     '/morphemelanguagemodels/{id}/generate',
                     request_method='PUT')
    config.add_route('morpheme_lm_get_probabilities',
                     '/morphemelanguagemodels/{id}/get_probabilities',
                     request_method='PUT')
    config.add_route('morpheme_lm_serve_arpa',
                     '/morphemelanguagemodels/{id}/serve_arpa',
                     request_method='GET')

    config.add_route('mparser_apply_down',
                     '/morphologicalparsers/{id}/applydown',
                     request_method='PUT')
    config.add_route('mparser_apply_up',
                     '/morphologicalparsers/{id}/applyup',
                     request_method='PUT')
    config.add_route('mparser_export', '/morphologicalparsers/{id}/export',
                     request_method='GET')
    config.add_route('mparser_generate', '/morphologicalparsers/{id}/generate',
                     request_method='PUT')
    config.add_route('mparser_generate_and_compile',
                     '/morphologicalparsers/{id}/generate_and_compile',
                     request_method='PUT')
    config.add_route('mparser_parse', '/morphologicalparsers/{id}/parse',
                     request_method='PUT')
    config.add_route('mparser_servecompiled',
                     '/morphologicalparsers/{id}/servecompiled',
                     request_method='GET')

    config.add_route('morphology_applydown', '/morphologies/{id}/applydown',
                     request_method='PUT')
    config.add_route('morphology_applyup', '/morphologies/{id}/applyup',
                     request_method='PUT')
    config.add_route('morphology_generate', '/morphologies/{id}/generate',
                     request_method='PUT')
    config.add_route('morphology_generate_and_compile',
                     '/morphologies/{id}/generate_and_compile',
                     request_method='PUT')
    config.add_route('morphology_servecompiled',
                     '/morphologies/{id}/servecompiled',
                     request_method='GET')

    config.add_route('phonology_applydown', '/phonologies/{id}/applydown',
                     request_method='PUT')
    config.add_route('phonology_phonologize', '/phonologies/{id}/phonologize',
                     request_method='PUT')
    config.add_route('phonology_compile', '/phonologies/{id}/compile',
                     request_method='PUT')
    config.add_route('phonology_servecompiled',
                     '/phonologies/{id}/servecompiled',
                     request_method='GET')
    config.add_route('phonology_runtests',
                     '/phonologies/{id}/runtests',
                     request_method='GET')

    # rememberedforms "resource"
    # Pylons: controller='rememberedforms', action='show'
    config.add_route('show_remembered_forms',
                     '/rememberedforms/{id}',
                     request_method='GET')

    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='show',
                    route_name='show_remembered_forms',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)

    config.add_route('remembered_forms_update',
                     '/rememberedforms/{id}',
                     request_method='PUT')
    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='update',
                    route_name='remembered_forms_update',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(
                                   ['administrator', 'contributor', 'viewer'],
                                   user_id_is_args1=True)))

    config.add_route('search_remembered_forms',
                     '/rememberedforms/{id}',
                     request_method='SEARCH')
    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='search',
                    route_name='search_remembered_forms',
                    request_method='SEARCH',
                    renderer='json',
                    decorator=authenticate)

    config.add_route('search_remembered_forms_post',
                     '/rememberedforms/{id}/search',
                     request_method='POST')
    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='search',
                    route_name='search_remembered_forms_post',
                    request_method='POST',
                    renderer='json',
                    decorator=authenticate)

    # REST resource routes. See ``RESOURCES`` for config and ``add_resource``
    # for implementation.
    for member_name, rsrc_config in RESOURCES.items():
        add_resource(config, member_name, rsrc_config)

    # Map '/collections' to oldcollections controller (conflict with Python
    # collections module).
    # TODO: still necessary in Pyramid?
    # config.add_route('collections', controller='oldcollections')
