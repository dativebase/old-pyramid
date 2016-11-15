import inflect
p = inflect.engine()
p.classical()

from pyramid.response import Response
from old.lib.constants import (
    UNAUTHORIZED_MSG,
    UNAUTHENTICATED_MSG,
)
import old.lib.pyramid_routehelper as pyrh
from old.models import User


RESOURCES = {
    'applicationsetting': {},
    'collection': {'searchable': True},
    'collectionbackup': {'searchable': True},
    'corpus': {},
    'corpusbackup': {'searchable': True},
    'elicitationmethod': {},
    'file': {'searchable': True},
    'form': {'searchable': True},
    'formsearch': {'searchable': True},
    'formbackup': {'searchable': True},
    'keyboard': {'searchable': True},
    'language': {'searchable': True},
    'morphemelanguagemodel': {'searchable': True},
    'morphemelanguagemodelbackup': {},
    'morphologicalparser': {'searchable': True},
    'morphologicalparserbackup': {},
    'morphology': {'searchable': True},
    'morphologybackup': {},
    'orthography': {},
    'page': {'searchable': True},
    'phonology': {'searchable': True},
    'phonologybackup': {},
    'source': {'searchable': True},
    'speaker': {},
    'syntacticcategory': {},
    'tag': {},
    'user': {},
}


def search_connect(config, name):
    """Create a SEARCH mapping for the resource collection with (plural) name
    ``name``. Usage: ``config = search_connect(config, 'forms')``.
    """
    config.add_route(
        'search_{}'.format(name),
        '/{}'.format(name),
        request_method='SEARCH')
    config.add_route(
        'search_{}_post'.format(name),
        '/{}/search'.format(name),
        request_method='POST')
    config.add_route(
        'new_search_{}'.format(name),
        '/{}/new_search'.format(name),
        request_method='GET')
    return config


def fix_for_tests(request):
    """Modifies the request if certain environment variables are present;
    purpose is to simulate different login states for testing.
    """
    if 'test.authentication.role' in request.environ:
        role = request.environ['test.authentication.role']
        user = request.dbsession.query(User).filter(User.role==role).first()
        if user:
            request.session['user'] = user.get_dict()
    if 'test.authentication.id' in request.environ:
        user = request.dbsession.query(User).get(
            request.environ['test.authentication.id'])
        if user:
            request.session['user'] = user.get_dict()
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
        request = fix_for_tests(request)
        if request.session.get('user'):
            return func(context, request)
        else:
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
            # Check for authorization via role.
            user = request.session['user']
            role = user['role']
            if role in roles:
                # Check for authorization via user.
                if (    users and role != 'administrator'
                        and user['id'] not in users):
                    return UNAUTHORIZED_RESP
                # Check whether the user id equals the id argument in the URL
                # path. This is useful, e.g., when a user can only edit their
                # own personal page.
                if (    user_id_is_args1 and
                        role != 'administrator' and
                        int(user['id']) != int(request.matchdict['id'])):
                    return UNAUTHORIZED_RESP
                return func(context, request)
            else:
                return UNAUTHORIZED_RESP
        return wrapper
    return _authorize


def get_auth_decorators(resource, action):
    """TODO: there are resource-specific authorization controls."""
    if action in ('create', 'new', 'update', 'edit', 'delete'):
        return (authenticate, authorize(['administrator', 'contributor']))
    return authenticate


def add_resource(config, member_name, rsrc_config=None):
    """Add route/view configuration to ``config`` that exposes ``member_name``
    as a RESTful resource. The ``rsrc_config`` dict provides additional
    configuration of the resource; e.g., setting 'searchable' to ``True`` will
    set up search-related routes. Configuration should be centralized in the
    ``RESOURCES`` constant.
    """
    if not rsrc_config:
        rsrc_config = {}
    collection_name = p.plural(member_name)
    class_name = collection_name.capitalize()
    view_callable = 'old.views.{}.{}'.format(collection_name, class_name)
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
    if rsrc_config.get('searchable', False):
        for route_name, path, request_method, attr in (
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
            ):
            config.add_route(route_name, path, request_method=request_method)
            config.add_view(view_callable,
                            attr=attr,
                            route_name=route_name,
                            request_method=request_method,
                            renderer='json',
                            decorator=get_auth_decorators(member_name, attr))


def includeme(config):
    # Pyramid boilerplate
    config.add_static_view('static', 'static', cache_max_age=3600)
    # config.add_route('home', '/')

    # The ErrorController route (handles 404/500 error pages); it should
    # likely stay at the top, ensuring it can always be resolved
    config.add_route('error_action', '/error/{action}')
    config.add_route('error_id_action', '/error/{id}/{action}')

    config.add_route('info', '/')

    # CORS preflight OPTIONS requests---don't interfere with them
    config.add_route('cors_proceed', '/*garbage', request_method='OPTIONS')

    config.add_route('collections_history', '/collections/{id}/history')
    # Pylons: controller='oldcollections', action='history'

    # To search across corpora, you need to issue a SEARCH/POST
    # /corpora/searchcorpora request. Corpora.search_corpora should handle
    # this.
    config.add_route('search_corpora', '/corpora/searchcorpora',
                     request_method=('POST', 'SEARCH'))
    config.add_route('new_search_corpora', '/corpora/new_search_corpora',
                     request_method='GET')

    # Pylons: controller='corpora', action='get_word_category_sequences'
    config.add_route('corpora_word_category_sequences',
                     '/corpora/{id}/get_word_category_sequences',
                     request_method='GET')
    # To search within the forms of a corpus, use one of the following two:
    # Pylons: controller='corpora', action='search',
    config.add_route('search_corpus', '/corpora/{id}', request_method='SEARCH')
    config.add_route('search_corpus_post', '/corpora/{id}/search',
                     request_method='POST')
    config.add_route('corpus_history', '/corpora/{id}/history')
    config.add_route('corpus_serve_file', '/corpora/{id}/servefile/{file_id}',
                     request_method='GET')
    config.add_route('corpus_tgrep2', '/corpora/{id}/tgrep2',
                     request_method=('POST', 'SEARCH'))
    config.add_route('corpus_writetofile', '/corpora/{id}/writetofile',
                     request_method='PUT')
    config.add_route('corpora_new_search', '/corpora/new_search')

    config.add_route('serve_file', '/files/{id}/serve')
    config.add_route('serve_reduced_file', '/files/{id}/serve_reduced')

    config.add_route('form_history', '/forms/{id}/history')
    config.add_route('remember_forms', '/forms/remember')
    config.add_route('update_morpheme_references',
                     '/forms/update_morpheme_references',
                     request_method='PUT')

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
    config.add_route('morpheme_lm_history',
                     '/morphemelanguagemodels/{id}/history')
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
    config.add_route('mparser_history', '/morphologicalparsers/{id}/history')
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
    config.add_route('morphology_history', '/morphologies/{id}/history')
    config.add_route('morphology_servecompiled',
                     '/morphologies/{id}/servecompiled',
                     request_method='GET')

    config.add_route('phonology_applydown', '/phonologies/{id}/applydown',
                     request_method='PUT')
    config.add_route('phonology_phonologize', '/phonologies/{id}/phonologize',
                     request_method='PUT')
    config.add_route('phonology_compile', '/phonologies/{id}/compile',
                     request_method='PUT')
    config.add_route('phonology_history', '/phonologies/{id}/history')
    config.add_route('phonology_servecompiled',
                     '/phonologies/{id}/servecompiled',
                     request_method='GET')
    config.add_route('phonology_runtests',
                     '/phonologies/{id}/runtests',
                     request_method='GET')

    """
    # SEARCH routes
    search_connect(config, 'collectionbackups')
    search_connect(config, 'collections')
    search_connect(config, 'corpusbackups')
    search_connect(config, 'files')
    search_connect(config, 'formbackups')
    search_connect(config, 'forms')
    search_connect(config, 'formsearches')
    search_connect(config, 'keyboards')
    search_connect(config, 'languages')
    search_connect(config, 'morphemelanguagemodels')
    search_connect(config, 'morphologicalparsers')
    search_connect(config, 'morphologies')
    search_connect(config, 'pages')
    search_connect(config, 'phonologies')
    search_connect(config, 'sources')
    """

    # rememberedforms "resource"
    # Pylons: controller='rememberedforms', action='show'
    config.add_route('show_remembered_forms', '/rememberedforms/{id}',
                     request_method='GET')
    config.add_route('remembered_forms_update', '/rememberedforms/{id}',
                     request_method='PUT')
    config.add_route('search_remembered_forms', '/rememberedforms/{id}',
                     request_method='SEARCH')
    config.add_route('search_remembered_forms_post',
                     '/rememberedforms/{id}/search',
                     request_method='POST')

    # RESTful resource mappings
    """
    add_resource(config, 'applicationsetting')
    add_resource(config, 'collection')
    add_resource(config, 'collectionbackup')
    add_resource(config, 'corpus')
    add_resource(config, 'corpusbackup')
    add_resource(config, 'elicitationmethod')
    add_resource(config, 'file')
    add_resource(config, 'form')
    add_resource(config, 'formsearch')
    add_resource(config, 'formbackup')
    add_resource(config, 'keyboard')
    add_resource(config, 'language')
    add_resource(config, 'morphemelanguagemodel')
    add_resource(config, 'morphemelanguagemodelbackup')
    add_resource(config, 'morphologicalparser')
    add_resource(config, 'morphologicalparserbackup')
    add_resource(config, 'morphology')
    add_resource(config, 'morphologybackup')
    add_resource(config, 'orthography')
    add_resource(config, 'page')
    add_resource(config, 'phonology')
    add_resource(config, 'phonologybackup')
    add_resource(config, 'source')
    add_resource(config, 'speaker')
    add_resource(config, 'syntacticcategory')
    add_resource(config, 'tag')
    add_resource(config, 'user')
    """

    for member_name, rsrc_config in RESOURCES.items():
        add_resource(config, member_name, rsrc_config)

    # Map '/collections' to oldcollections controller (conflict with Python
    # collections module).
    # TODO: still necessary in Pyramid?
    # config.add_route('collections', controller='oldcollections')
