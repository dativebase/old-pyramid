import logging

import inflect
from pyramid.response import Response

from old.lib.constants import (
    UNAUTHORIZED_MSG,
    UNAUTHENTICATED_MSG,
)
from old.models import User


LOGGER = logging.getLogger(__name__)


INFLP = inflect.engine()
INFLP.classical()


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


def add_resource(config, member_name, rsrc_config=None):
    """Add route/view configuration to ``config`` that exposes ``member_name``
    as a RESTful resource. The ``rsrc_config`` dict provides additional
    configuration of the resource; e.g., setting 'searchable' to ``True`` will
    set up search-related routes. Configuration should be centralized in the
    ``RESOURCES`` constant.
    """
    if not rsrc_config:
        rsrc_config = {}
    collection_name = INFLP.plural(member_name)
    class_name = collection_name.capitalize()
    view_callable = 'old.views.{}.{}'.format(collection_name, class_name)

    # Search-related routes
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

    # History route
    if rsrc_config.get('history', False):
        route_name, path, request_method, attr = (
            '{}_history'.format(member_name),
            '/{{old_name}}/{}/{{id}}/history'.format(collection_name),
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

    # Standard CRUD routes
    for action in ('create', 'index', 'new', 'edit', 'delete', 'update',
                   'show'):
        route_name = '{}_{}'.format(action, member_name)
        if action == 'index':
            route_name = '{}_{}'.format(action, collection_name)
        path = '{{old_name}}/{}'.format(collection_name)
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


def fix_for_tests(request):
    """Modifies the request if certain environment variables are present.
    Purpose is to simulate different login states for testing.
    """
    if request.registry.settings.get('testing', '0') == '1':
        LOGGER.info('Rigging the authentication mechanism for testing')
        if 'test.authentication.role' in request.environ:
            role = request.environ['test.authentication.role']
            user = request.dbsession.query(User).filter(
                User.role == role).first()
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
    """Authentication decorator."""
    def wrapper(context, request):
        request = fix_for_tests(request)
        user = request.session.get('user')
        if user:
            LOGGER.info('User %s is authenticated (accessing %s).',
                        user['username'], request.current_route_url())
            return func(context, request)
        LOGGER.info('No user is authenticated; cannot access %s.',
                    request.current_route_url())
        return UNAUTHENTICATED_RESP
    return wrapper


def authorize(roles, users=None, user_id_is_args1=False):
    """Function that returns an authorization decorator. If user tries to
    request a resource action but has insufficient authorization, this
    decorator will respond with a header status of '403 Forbidden' and a JSON
    object explanation. The user is unauthorized if *any* of the following are
    true:

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
        >>>           user_id_is_args1=True)
    """
    def _authorize(func):
        def wrapper(context, request):
            # Check for authorization via role.
            user = request.session['user']
            role = user['role']
            if role in roles:
                # Check for authorization via user.
                if (users and role != 'administrator' and
                        user['id'] not in users):
                    LOGGER.info('User %s is not authorized to make this request'
                                ' (%s) because they are not in the set of'
                                ' authorized users.', user['username'],
                                request.current_route_url())
                    return UNAUTHORIZED_RESP
                # Check whether the user id equals the id argument in the URL
                # path. This is useful, e.g., when a user can only edit their
                # own personal page.
                if (user_id_is_args1 and
                        role != 'administrator' and
                        int(user['id']) != int(request.matchdict['id'])):
                    LOGGER.info('User %s is not authorized to make this request'
                                ' (%s) because they are not the unique user'
                                ' authorized to do so.', user['username'],
                                request.current_route_url())
                    return UNAUTHORIZED_RESP
                LOGGER.info('User %s is authorized to make this request (%s).',
                            user['username'], request.current_route_url())
                return func(context, request)
            else:
                LOGGER.info('User %s is not authorized to make this request'
                            ' (%s) because their role %s is not in the set of'
                            ' authorized roles: %s.', user['username'],
                            request.current_route_url(), role, ', '.join(roles))
                return UNAUTHORIZED_RESP
        return wrapper
    return _authorize


def get_auth_decorators(resource, action):
    """Convenience for returning the appropriate authorization decorator, given
    a specific resource and action on that resource.
    """
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


CORPORA_SEARCH_CONFIG = (
    (
        'search_corpus_forms',
        '{old_name}/corpora/{id}',
        'SEARCH',
        'search'
    ), (
        'search_corpus_forms_post',
        '{old_name}/corpora/{id}/search',
        'POST',
        'search'
    ), (
        'new_search_corpus_forms',
        '{old_name}/corpora/new_search',
        'GET',
        'new_searchx'
    )
)


def get_search_config(collection_name):
    """Return the route name, path, request method, and class attribute for
    configuring search across the resource with collection name
    ``collection_name``.
    """
    if collection_name == 'corpora':
        return CORPORA_SEARCH_CONFIG
    return (
        (
            'search_{}'.format(collection_name),
            '/{{old_name}}/{}'.format(collection_name),
            'SEARCH',
            'search'
        ), (
            'search_{}_post'.format(collection_name),
            '/{{old_name}}/{}/search'.format(collection_name),
            'POST',
            'search'
        ), (
            'new_search_{}'.format(collection_name),
            '/{{old_name}}/{}/new_search'.format(collection_name),
            'GET',
            'new_search'
        )
    )


def cors(request):
    request.response.status_int = 204
    return request.response


def _corpora_special_routing(config):
    # To search across corpora, you need to issue a SEARCH/POST
    # /corpora/searchcorpora request.
    config.add_route('search_corpora',
                     '/{old_name}/corpora/searchcorpora',
                     request_method=('POST', 'SEARCH'))
    config.add_view('old.views.corpora.Corpora',
                    attr='search_corpora',
                    route_name='search_corpora',
                    request_method=('POST', 'SEARCH'),
                    renderer='json',
                    decorator=authenticate)
    config.add_route('new_search_corpora',
                     '/{old_name}/corpora/new_search_corpora',
                     request_method='GET')
    config.add_view('old.views.corpora.Corpora',
                    attr='new_search_corpora',
                    route_name='new_search_corpora',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('corpora_word_category_sequences',
                     '/{old_name}/corpora/{id}/get_word_category_sequences',
                     request_method='GET')
    config.add_view('old.views.corpora.Corpora',
                    attr='get_word_category_sequences',
                    route_name='corpora_word_category_sequences',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('corpus_serve_file',
                     '/{old_name}/corpora/{id}/servefile/{file_id}',
                     request_method='GET')
    config.add_view('old.views.corpora.Corpora',
                    attr='servefile',
                    route_name='corpus_serve_file',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('corpus_tgrep2',
                     '/{old_name}/corpora/{id}/tgrep2',
                     request_method=('POST', 'SEARCH'))
    config.add_view('old.views.corpora.Corpora',
                    attr='tgrep2',
                    route_name='corpus_tgrep2',
                    request_method=('POST', 'SEARCH'),
                    renderer='json',
                    decorator=authenticate)
    config.add_route('corpus_writetofile',
                     '/{old_name}/corpora/{id}/writetofile',
                     request_method='PUT')
    config.add_view('old.views.corpora.Corpora',
                    attr='writetofile',
                    route_name='corpus_writetofile',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))


def _files_special_routing(config):
    config.add_route('serve_file',
                     '/{old_name}/files/{id}/serve',
                     request_method='GET')
    config.add_view('old.views.files.Files',
                    attr='serve',
                    route_name='serve_file',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('serve_reduced_file',
                     '/{old_name}/files/{id}/serve_reduced',
                     request_method='GET')
    config.add_view('old.views.files.Files',
                    attr='serve_reduced',
                    route_name='serve_reduced_file',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)


def _forms_special_routing(config):
    config.add_route('remember_forms',
                     '/{old_name}/forms/remember',
                     request_method='POST')
    config.add_view('old.views.forms.Forms',
                    attr='remember',
                    route_name='remember_forms',
                    request_method='POST',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('update_morpheme_references',
                     '/{old_name}/forms/update_morpheme_references',
                     request_method='PUT')
    config.add_view('old.views.forms.Forms',
                    attr='update_morpheme_references',
                    route_name='update_morpheme_references',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate, authorize(['administrator'])))


def _authentication_routing(config):
    config.add_route('authenticate', '/{old_name}/login/authenticate')
    config.add_view('old.views.auth.login',
                    route_name='authenticate',
                    renderer='json')
    config.add_route('logout', '/{old_name}/login/logout')
    config.add_view('old.views.auth.logout',
                    route_name='logout',
                    renderer='json')
    config.add_route('email_reset_password',
                     '/{old_name}/login/email_reset_password',
                     request_method='POST')
    config.add_view('old.views.auth.email_reset_password',
                    route_name='email_reset_password',
                    renderer='json')


def _mlm_special_routing(config):
    config.add_route('morpheme_lm_compute_perplexity',
                     '/{old_name}/morphemelanguagemodels/{id}/compute_perplexity',
                     request_method='PUT')
    config.add_view('old.views.morphemelanguagemodels.Morphemelanguagemodels',
                    attr='compute_perplexity',
                    route_name='morpheme_lm_compute_perplexity',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('generate_morpheme_lm',
                     '/{old_name}/morphemelanguagemodels/{id}/generate',
                     request_method='PUT')
    config.add_view('old.views.morphemelanguagemodels.Morphemelanguagemodels',
                    attr='generate',
                    route_name='generate_morpheme_lm',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('morpheme_lm_get_probabilities',
                     '/{old_name}/morphemelanguagemodels/{id}/get_probabilities',
                     request_method='PUT')
    config.add_view('old.views.morphemelanguagemodels.Morphemelanguagemodels',
                    attr='get_probabilities',
                    route_name='morpheme_lm_get_probabilities',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('morpheme_lm_serve_arpa',
                     '/{old_name}/morphemelanguagemodels/{id}/serve_arpa',
                     request_method='GET')
    config.add_view('old.views.morphemelanguagemodels.Morphemelanguagemodels',
                    attr='serve_arpa',
                    route_name='morpheme_lm_serve_arpa',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)


def _mp_special_routing(config):
    config.add_route('mparser_apply_down',
                     '/{old_name}/morphologicalparsers/{id}/applydown',
                     request_method='PUT')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='applydown',
                    route_name='mparser_apply_down',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('mparser_apply_up',
                     '/{old_name}/morphologicalparsers/{id}/applyup',
                     request_method='PUT')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='applyup',
                    route_name='mparser_apply_up',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('mparser_export',
                     '/{old_name}/morphologicalparsers/{id}/export',
                     request_method='GET')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='export',
                    route_name='mparser_export',
                    request_method='GET',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('mparser_generate',
                     '/{old_name}/morphologicalparsers/{id}/generate',
                     request_method='PUT')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='generate',
                    route_name='mparser_generate',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('mparser_generate_and_compile',
                     '/{old_name}/morphologicalparsers/{id}/generate_and_compile',
                     request_method='PUT')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='generate_and_compile',
                    route_name='mparser_generate_and_compile',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('mparser_parse',
                     '/{old_name}/morphologicalparsers/{id}/parse',
                     request_method='PUT')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='parse',
                    route_name='mparser_parse',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('mparser_servecompiled',
                     '/{old_name}/morphologicalparsers/{id}/servecompiled',
                     request_method='GET')
    config.add_view('old.views.morphologicalparsers.Morphologicalparsers',
                    attr='servecompiled',
                    route_name='mparser_servecompiled',
                    request_method='GET',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))


def _morphology_special_routing(config):
    config.add_route('morphology_servecompiled',
                     '/{old_name}/morphologies/{id}/servecompiled',
                     request_method='GET')
    config.add_view('old.views.morphologies.Morphologies',
                    attr='servecompiled',
                    route_name='morphology_servecompiled',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('morphology_applydown',
                     '/{old_name}/morphologies/{id}/applydown',
                     request_method='PUT')
    config.add_view('old.views.morphologies.Morphologies',
                    attr='applydown',
                    route_name='morphology_applydown',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('morphology_applyup',
                     '/{old_name}/morphologies/{id}/applyup',
                     request_method='PUT')
    config.add_view('old.views.morphologies.Morphologies',
                    attr='applyup',
                    route_name='morphology_applyup',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('morphology_generate',
                     '/{old_name}/morphologies/{id}/generate',
                     request_method='PUT')
    config.add_view('old.views.morphologies.Morphologies',
                    attr='generate',
                    route_name='morphology_generate',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('morphology_generate_and_compile',
                     '/{old_name}/morphologies/{id}/generate_and_compile',
                     request_method='PUT')
    config.add_view('old.views.morphologies.Morphologies',
                    attr='generate_and_compile',
                    route_name='morphology_generate_and_compile',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))


def _phonology_special_routing(config):
    config.add_route('phonology_applydown',
                     '/{old_name}/phonologies/{id}/applydown',
                     request_method='PUT')
    config.add_view('old.views.phonologies.Phonologies',
                    attr='applydown',
                    route_name='phonology_applydown',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('phonology_phonologize',
                     '/{old_name}/phonologies/{id}/phonologize',
                     request_method='PUT')
    config.add_view('old.views.phonologies.Phonologies',
                    attr='applydown',
                    route_name='phonology_phonologize',
                    request_method='PUT',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('phonology_compile',
                     '/{old_name}/phonologies/{id}/compile',
                     request_method='PUT')
    config.add_view('old.views.phonologies.Phonologies',
                    attr='compile',
                    route_name='phonology_compile',
                    request_method='PUT',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))
    config.add_route('phonology_servecompiled',
                     '/{old_name}/phonologies/{id}/servecompiled',
                     request_method='GET')
    config.add_view('old.views.phonologies.Phonologies',
                    attr='servecompiled',
                    route_name='phonology_servecompiled',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('phonology_runtests',
                     '/{old_name}/phonologies/{id}/runtests',
                     request_method='GET')
    config.add_view('old.views.phonologies.Phonologies',
                    attr='runtests',
                    route_name='phonology_runtests',
                    request_method='GET',
                    renderer='json',
                    decorator=(authenticate,
                               authorize(['administrator', 'contributor'])))


def _rf_special_routing(config):
    # Pylons: controller='rememberedforms', action='show'
    config.add_route('show_remembered_forms',
                     '/{old_name}/rememberedforms/{id}',
                     request_method='GET')
    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='show',
                    route_name='show_remembered_forms',
                    request_method='GET',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('remembered_forms_update',
                     '/{old_name}/rememberedforms/{id}',
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
                     '/{old_name}/rememberedforms/{id}',
                     request_method='SEARCH')
    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='search',
                    route_name='search_remembered_forms',
                    request_method='SEARCH',
                    renderer='json',
                    decorator=authenticate)
    config.add_route('search_remembered_forms_post',
                     '/{old_name}/rememberedforms/{id}/search',
                     request_method='POST')
    config.add_view('old.views.rememberedforms.Rememberedforms',
                    attr='search',
                    route_name='search_remembered_forms_post',
                    request_method='POST',
                    renderer='json',
                    decorator=authenticate)


def includeme(config):
    config.add_route('info', '/{old_name}/', request_method='GET')
    config.add_view('old.views.info.Info',
                    attr='index',
                    route_name='info',
                    request_method='GET',
                    renderer='json')
    # CORS preflight OPTIONS requests: don't interfere with them
    # TODO: test if this works.
    config.add_route('cors_proceed', '/{old_name}/*garbage', request_method='OPTIONS')
    config.add_view(cors,
                    route_name='cors_proceed',
                    request_method='OPTIONS')
    _corpora_special_routing(config)
    _files_special_routing(config)
    _forms_special_routing(config)
    _authentication_routing(config)
    _mlm_special_routing(config)
    _mp_special_routing(config)
    _morphology_special_routing(config)
    _phonology_special_routing(config)
    _rf_special_routing(config)
    # See ``RESOURCES`` for config and ``add_resource`` for implementation.
    for member_name, rsrc_config in RESOURCES.items():
        add_resource(config, member_name, rsrc_config)
