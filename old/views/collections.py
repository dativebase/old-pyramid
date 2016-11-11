# Copyright 2016 Joel Dunham
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

"""Contains the :class:`Collections` view and its auxiliary functions.

.. module:: collections
   :synopsis: Contains the collections view and its auxiliary functions.
"""

import logging
import re
import json
from uuid import uuid4

from formencode.validators import Invalid
from sqlalchemy import bindparam
from sqlalchemy.sql import asc, or_
from sqlalchemy.orm import subqueryload

import old.lib.helpers as h
from old.lib.schemata import FormSchema, FormIdsSchema
from old.lib.SQLAQueryBuilder import OLDSearchParseError # TODO: move this to resources.py?
from old.models import Form, FormBackup, Collection, CollectionBackup, User
from old.views.resources import Resources


LOGGER = logging.getLogger(__name__)

class Collections(Resources):
    """Generate responses to requests on collection resources.

    REST Controller styled on the Atom Publishing Protocol.

    The collections controller is one of the more complex ones.  A great deal of
    this complexity arised from the fact that collections can reference forms
    and other collections in the value of their ``contents`` attribute.  The
    propagation of restricted tags and associated forms and the generation of
    the html from these contents-with-references, necessitates some complex
    logic for updates and deletions.

    .. warning::

        There is a potential issue with collection-collection reference. A
        restricted user can restrict their own collection *A* and that
        restriction would be propagated up the reference chain, possibly causing
        another collection *B* (that was not created by the updater) to become
        restricted. That is, collection-collection reference permits restricted
        users to indirectly restrict collections they would otherwise not be
        permitted to restrict. This will be bothersome to other restricted users
        since they will no longer be able to access the newly restricted
        collection *B*.
    """

    pass

    '''

    def search(self):
        """Return the list of collection resources matching the input JSON
        query.

        :URL: ``SEARCH /collections`` (or ``POST /collections/search``)
        :request body: A JSON object of the form::

                {"query": {"filter": [ ... ], "order_by": [ ... ]},
                 "paginator": { ... }}

            where the ``order_by`` and ``paginator`` attributes are optional.

        .. note::

            Search does not return the forms of all collections that match the
            search.  For that, a second request is required, i.e., to
            ``GET /collections/id``.
        """
        try:
            json_search_params = unicode(request.body, request.charset)
            python_search_params = json.loads(json_search_params)
            SQLAQuery = h.eagerload_collection(
                self.query_builder.get_SQLA_query(python_search_params.get('query')))
            query = h.filter_restricted_models('Collection', SQLAQuery)
            return h.add_pagination(query, python_search_params.get('paginator'))
        except h.JSONDecodeError:
            response.status_int = 400
            return self.JSONDecodeErrorResponse
        except (OLDSearchParseError, Invalid) as e:
            response.status_int = 400
            return {'errors': e.unpack_errors()}
        except:
            response.status_int = 400
            return {'error': u'The specified search parameters generated an invalid database query'}

    @h.jsonify
    @h.restrict('GET')
    @h.authenticate
    def new_search(self):
        """Return the data necessary to search the collection resources.

        :URL: ``GET /collections/new_search``
        :returns: ``{"search_parameters": {"attributes": { ... }, "relations": { ... }}``

        """

        return {'search_parameters': h.get_search_parameters(self.query_builder)}

    @h.jsonify
    @h.restrict('GET')
    @h.authenticate
    def index(self):
        """Get all collection resources.

        :URL: ``GET /collections`` with optional query string parameters for
            ordering and pagination.
        :returns: a list of all collection resources.

        .. note::

           See :func:`utils.add_order_by` and :func:`utils.add_pagination` for the
           query string parameters that effect ordering and pagination.

        .. note::
        
            ``GET /collections`` does not return the forms of the collections
            returned.  For that, a second request is required, i.e., to
            ``GET /collections/id`` with the relevant ``id`` value.

        """
        try:
            query = h.eagerload_collection(Session.query(Collection))
            query = h.add_order_by(query, dict(request.GET), self.query_builder)
            query = h.filter_restricted_models('Collection', query)
            return h.add_pagination(query, dict(request.GET))
        except Invalid as e:
            response.status_int = 400
            return {'errors': e.unpack_errors()}

    @h.jsonify
    @h.restrict('POST')
    @h.authenticate
    @h.authorize(['administrator', 'contributor'])
    def create(self):
        """Create a new collection resource and return it.

        :URL: ``POST /collections``
        :request body: JSON object representing the collection to create.
        :returns: the newly created collection.

        """
        try:
            unrestricted_users = h.get_unrestricted_users()
            user = session['user']
            schema = CollectionSchema()
            values = json.loads(unicode(request.body, request.charset))
            collections_referenced = get_collections_referenced(values['contents'],
                                                        user, unrestricted_users)
            values = add_contents_unpacked_to_values(values, collections_referenced)
            values = add_form_ids_list_to_values(values)
            state = h.get_state_object(values)
            data = schema.to_python(values, state)
            collection = create_new_collection(data, collections_referenced)
            Session.add(collection)
            Session.commit()
            return collection.get_full_dict()
        except h.JSONDecodeError:
            response.status_int = 400
            return self.JSONDecodeErrorResponse
        except InvalidCollectionReferenceError as e:
            response.status_int = 400
            return {'error': u'Invalid collection reference error: there is no collection with id %d' % e.args[0]}
        except UnauthorizedCollectionReferenceError:
            response.status_int = 403
            return {'error': u'Unauthorized collection reference error: you are not authorized to access collection %d' % e.args[0]}
        except Invalid as e:
            response.status_int = 400
            return {'errors': e.unpack_errors()}

    @h.jsonify
    @h.restrict('GET')
    @h.authenticate
    @h.authorize(['administrator', 'contributor'])
    def new(self):
        """Return the data necessary to create a new collection.

        :URL: ``GET /collections/new`` with optional query string parameters 
        :returns: a dictionary of lists of resources.

        .. note::
        
           See :func:`get_new_edit_collection_data` to understand how the query
           string parameters can affect the contents of the lists in the
           returned dictionary.

        """
        return get_new_edit_collection_data(request.GET)

    @h.jsonify
    @h.restrict('PUT')
    @h.authenticate
    @h.authorize(['administrator', 'contributor'])
    def update(self, id):
        """Update a collection and return it.
        
        :URL: ``PUT /collections/id``
        :Request body: JSON object representing the collection with updated attribute values.
        :param str id: the ``id`` value of the collection to be updated.
        :returns: the updated collection model.

        """
        collection = h.eagerload_collection(Session.query(Collection),
                                           eagerload_forms=True).get(int(id))
        if collection:
            unrestricted_users = h.get_unrestricted_users()
            user = session['user']
            if h.user_is_authorized_to_access_model(user, collection, unrestricted_users):
                try:
                    schema = CollectionSchema()
                    values = json.loads(unicode(request.body, request.charset))
                    collections_referenced = get_collections_referenced(
                                values['contents'], user, unrestricted_users, id)
                    values = add_contents_unpacked_to_values(values, collections_referenced)
                    values = add_form_ids_list_to_values(values)
                    state = h.get_state_object(values)
                    data = schema.to_python(values, state)
                    collection_dict = collection.get_full_dict()
                    collection, restricted, contents_changed = update_collection(
                        collection, data, collections_referenced)
                    # collection will be False if there are no changes (cf. update_collection).
                    if collection:
                        backup_collection(collection_dict)
                        update_collections_that_reference_this_collection(collection, self.query_builder,
                                            restricted=restricted, contents_changed=contents_changed)
                        Session.add(collection)
                        Session.commit()
                        return collection.get_full_dict()
                    else:
                        response.status_int = 400
                        return {'error':
                            u'The update request failed because the submitted data were not new.'}
                except h.JSONDecodeError:
                    response.status_int = 400
                    return self.JSONDecodeErrorResponse
                except CircularCollectionReferenceError as e:
                    response.status_int = 400
                    return {'error':
                        u'Circular collection reference error: collection %d references collection %d.' % (id, e.args[0])}
                except InvalidCollectionReferenceError as e:
                    response.status_int = 400
                    return {'error': u'Invalid collection reference error: there is no collection with id %d' % e.args[0]}
                except UnauthorizedCollectionReferenceError:
                    response.status_int = 403
                    return {'error': u'Unauthorized collection reference error: you are not authorized to access collection %d' % e.args[0]}
                except Invalid as e:
                    response.status_int = 400
                    return {'errors': e.unpack_errors()}
            else:
                response.status_int = 403
                return h.unauthorized_msg
        else:
            response.status_int = 404
            return {'error': 'There is no collection with id %s' % id}

    @h.jsonify
    @h.restrict('DELETE')
    @h.authenticate
    @h.authorize(['administrator', 'contributor'])
    def delete(self, id):
        """Delete an existing collection and return it.

        :URL: ``DELETE /collections/id``
        :param str id: the ``id`` value of the collection to be deleted.
        :returns: the deleted collection model.

        .. note::

           Only administrators and a collection's enterer can delete it.

        """
        collection = h.eagerload_collection(Session.query(Collection),
                                           eagerload_forms=True).get(id)
        if collection:
            if session['user'].role == u'administrator' or \
            collection.enterer is session['user']:
                session['user'] = Session.merge(session['user'])
                collection.modifier = session['user']
                collection_dict = collection.get_full_dict()
                backup_collection(collection_dict)
                update_collections_that_reference_this_collection(collection,
                                                self.query_builder, deleted=True)
                Session.delete(collection)
                Session.commit()
                return collection_dict
            else:
                response.status_int = 403
                return h.unauthorized_msg
        else:
            response.status_int = 404
            return {'error': 'There is no collection with id %s' % id}

    @h.jsonify
    @h.restrict('GET')
    @h.authenticate
    def show(self, id):
        """Return a collection.
        
        :URL: ``GET /collections/id``
        :param str id: the ``id`` value of the collection to be returned.
        :returns: a collection model object.

        .. note::

            Returns all of the forms of the collection, unlike the other
            collections actions.

            If there is a truthy GET param with key 'latex' and if the markup
            language is reStructuredText, then the collection's
            contents_unpacked value will be returned as a LaTeX string in the
            'latex' attribute.

        """

        collection = h.eagerload_collection(Session.query(Collection),
                                           eagerload_forms=True).get(id)
        if collection:
            unrestricted_users = h.get_unrestricted_users()
            user = session['user']
            if h.user_is_authorized_to_access_model(user, collection, unrestricted_users):
                result = collection.get_full_dict()
                # TODO: deal with markdown2latex ...
                if request.GET.get('latex') and \
                collection.markup_language == 'reStructuredText':
                    result['latex'] = h.rst2latex(collection.contents_unpacked)
                return result
            else:
                response.status_int = 403
                return h.unauthorized_msg
        else:
            response.status_int = 404
            return {'error': 'There is no collection with id %s' % id}

    @h.jsonify
    @h.restrict('GET')
    @h.authenticate
    @h.authorize(['administrator', 'contributor'])
    def edit(self, id):
        """Return a collection and the data needed to update it.

        :URL: ``GET /collections/edit`` with optional query string parameters 
        :param str id: the ``id`` value of the collection that will be updated.
        :returns: a dictionary of the form::

                {"collection": {...}, "data": {...}}

            where the value of the ``collection`` key is a dictionary
            representation of the collection and the value of the ``data`` key
            is a dictionary containing the objects necessary to update a
            collection, viz. the return value of
            :func:`CollectionsController.new`

        .. note::
        
           This action can be thought of as a combination of
           :func:`CollectionsController.show` and
           :func:`CollectionsController.new`.  See
           :func:`get_new_edit_collection_data` to understand how the query string
           parameters can affect the contents of the lists in the ``data``
           dictionary.

        """
        collection = h.eagerload_collection(Session.query(Collection)).get(id)
        if collection:
            unrestricted_users = h.get_unrestricted_users()
            if h.user_is_authorized_to_access_model(
                                session['user'], collection, unrestricted_users):
                data = get_new_edit_collection_data(request.GET)
                return {'data': data, 'collection': collection}
            else:
                response.status_int = 403
                return h.unauthorized_msg
        else:
            response.status_int = 404
            return {'error': 'There is no collection with id %s' % id}

    @h.jsonify
    @h.restrict('GET')
    @h.authenticate
    def history(self, id):
        """Return a collection and its previous versions.

        :URL: ``GET /collections/history/id``
        :param str id: a string matching the ``id`` or ``UUID`` value of the
            collection whose history is requested.
        :returns: a dictionary of the form::

                {"collection": { ... }, "previous_versions": [ ... ]}

            where the value of the ``collection`` key is the collection whose
            history is requested and the value of the ``previous_versions`` key
            is a list of dictionaries representing previous versions of the
            collection.

        """
        collection, previous_versions = h.get_model_and_previous_versions('Collection', id)
        if collection or previous_versions:
            unrestricted_users = h.get_unrestricted_users()
            user = session['user']
            accessible = h.user_is_authorized_to_access_model
            unrestricted_previous_versions = [cb for cb in previous_versions
                                    if accessible(user, cb, unrestricted_users)]
            collection_is_restricted = collection and not accessible(user, collection, unrestricted_users)
            previous_versions_are_restricted = previous_versions and not unrestricted_previous_versions
            if collection_is_restricted or previous_versions_are_restricted :
                response.status_int = 403
                return h.unauthorized_msg
            else :
                return {'collection': collection,
                        'previous_versions': unrestricted_previous_versions}
        else:
            response.status_int = 404
            return {'error': 'No collections or collection backups match %s' % id}

    '''


################################################################################
# Backup collection
################################################################################

def backup_collection(collection_dict):
    """Backup a collection.

    :param dict form_dict: a representation of a collection model.
    :returns: ``None``

    """
    collection_backup = CollectionBackup()
    collection_backup.vivify(collection_dict)
    Session.add(collection_backup)


################################################################################
# Reference-extraction functions
################################################################################

# The following set of functions generate data from the references in the contents
# attribute of a collection.  The two primary tasks are to generate values for
# the 'forms' and 'contents_unpacked' attributes of the collection.  The three
# "public" functions are get_collections_referenced, add_form_ids_list_to_values and
# add_contents_unpacked_to_values.  get_collections_referenced raises errors if
# collection references are invalid and returns a dict from reference ids to
# collection objects, which dict is used by add_contents_unpacked_to_values, the
# output of the latter being used to generate the list of referenced forms.

def get_collections_referenced(contents, user=None, unrestricted_users=None,
                             collection_id=None, patt=None):
    """Return the collections (recursively) referenced by the input ``contents`` value.
    
    That is, return all of the collections referenced in the input ``contents``
    value, plus all of the collections referenced in those collections, etc.

    :param unicode contents: the value of the ``contents`` attribute of a collection.
    :param user: the user model who made the request.
    :param list unrestricted_users: the unrestricted user models of the application.
    :param int collection_id: the ``id`` value of a collection.
    :param patt: a compiled regular expression object.
    :returns: a dictionary whose keys are collection ``id`` values and whose
        values are collection models.

    """
    patt = patt or re.compile(h.collection_reference_pattern)
    collections_referenced = dict([(int(id), get_collection(int(id), user, unrestricted_users))
                                  for id in patt.findall(contents)])
    temp = collections_referenced.copy()
    if collection_id in collections_referenced:
        raise CircularCollectionReferenceError(collection_id)
    [collections_referenced.update(get_collections_referenced(
        collections_referenced[id].contents, user, unrestricted_users, collection_id, patt))
     for id in temp]
    return collections_referenced

def add_form_ids_list_to_values(values):
    """Add a list of referenced form ids to values.
    
    :param dict values: data for creating or updating a collection
    :returns: ``values`` with a ``'forms'`` key whose value is a list of id integers.

    """
    contents_unpacked = get_unicode('contents_unpacked', values)
    values['forms'] = [int(id) for id in h.form_reference_pattern.findall(contents_unpacked)]
    return values

def add_contents_unpacked_to_values(values, collections_referenced):
    """Add a ``'contents_unpacked'`` value to values and return values.
    
    :param dict values: data for creating a collection.
    :param dict collections_referenced: keys are collection ``id`` values and 
        values are collection models.
    :returns: ``values`` updated.

    """
    contents = get_unicode('contents', values)
    values['contents_unpacked'] = generate_contents_unpacked(contents, collections_referenced)
    return values

def get_collections_referenced_in_contents(collection, collections_referenced):
    """Get the immediately referenced collections of a collection.
    
    :param collection: a collection model.
    :param dict collections_referenced: keys are collection ``id`` values and 
        values are collection models.
    :returns: a list of collection models; useful in determining whether
        directly referenced collections are restricted.

    """
    return [collections_referenced[int(id)]
            for id in h.collection_reference_pattern.findall(collection.contents)]

def update_collections_that_reference_this_collection(collection, query_builder, **kwargs):
    """Update all collections that reference the input collection.
    
    :param collection: a collection model.
    :param query_builder: an :class:`SQLAQueryBuilder` instance.
    :param bool kwargs['contents_changed']: indicates whether the input
        collection's ``contents`` value has changed.
    :param bool kwargs['deleted']: indicates whether the input collection has
        just been deleted.
    :returns: ``None``

    Update the ``contents``, ``contents_unpacked``, ``html`` and/or ``form``
    attributes of every collection that references the input collection plus all
    of the collections that reference those collections, etc.  This function is
    called upon successful update and delete requests.

    If the contents of the ``collection`` have changed (i.e.,
    ``kwargs['contents_changed']==True``) , then retrieve all collections
    that reference ``collection`` and all collections that reference those
    referers, etc., and update their ``contents_unpacked``, ``html`` and
    ``forms`` attributes.

    If the ``collection`` has been deleted (i.e., ``kwargs['deleted']==True``),
    then recursively retrieve all collections referencing ``collection`` and
    update their ``contents``, ``contents_unpacked``, ``html`` and ``forms``
    attributes.

    If ``collection`` has just been tagged as restricted (i.e.,
    ``kwargs['restricted']==True``), then recursively restrict all collections
    that reference it.

    In all cases, update the ``datetime_modified`` value of every collection that
    recursively references ``collection``.

    """
    def update_contents_unpacked_etc(collection, **kwargs):
        deleted = kwargs.get('deleted', False)
        collection_id = kwargs.get('collection_id')
        if deleted:
            collection.contents = remove_references_to_this_collection(collection.contents, collection_id)
        collections_referenced = get_collections_referenced(collection.contents)
        collection.contents_unpacked = generate_contents_unpacked(
                                    collection.contents, collections_referenced)
        collection.html = h.get_HTML_from_contents(collection.contents_unpacked,
                                                  collection.markup_language)
        collection.forms = [Session.query(Form).get(int(id)) for id in
                    h.form_reference_pattern.findall(collection.contents_unpacked)]
    def update_modification_values(collection, now):
        collection.datetime_modified = now
        session['user'] = Session.merge(session['user'])
        collection.modifier = session['user']
    restricted = kwargs.get('restricted', False)
    contents_changed = kwargs.get('contents_changed', False)
    deleted = kwargs.get('deleted', False)
    if restricted or contents_changed or deleted:
        collections_referencing_this_collection = get_collections_referencing_this_collection(
            collection, query_builder)
        collections_referencing_this_collection_dicts = [c.get_full_dict() for c in
                                        collections_referencing_this_collection]
        now = h.now()
        if restricted:
            restricted_tag = h.get_restricted_tag()
            [c.tags.append(restricted_tag) for c in collections_referencing_this_collection]
        if contents_changed:
            [update_contents_unpacked_etc(c) for c in collections_referencing_this_collection]
        if deleted:
            [update_contents_unpacked_etc(c, collection_id=collection.id, deleted=True)
             for c in collections_referencing_this_collection]
        [update_modification_values(c, now) for c in collections_referencing_this_collection]
        [backup_collection(cd) for cd in collections_referencing_this_collection_dicts]
        Session.add_all(collections_referencing_this_collection)
        Session.commit()

def get_collections_referencing_this_collection(collection, query_builder):
    """Return all collections that recursively reference ``collection``.
    
    That is, return all collections that reference ``collection`` plus all
    collections that reference those referencing collections, etc.
    
    :param collection: a collection model object.
    :param query_builder: an :class:`SQLAQueryBuilder` instance.
    :returns: a list of collection models.

    """
    patt = h.collection_reference_pattern.pattern.replace(
        '\d+', str(collection.id)).replace('\\', '')
    query = {'filter': ['Collection', 'contents', 'regex', patt]}
    result = query_builder.get_SQLA_query(query).all()
    for c in result[:]:
        result += get_collections_referencing_this_collection(c, query_builder)
    return result


def update_collection_by_deletion_of_referenced_form(collection, referenced_form):
    """Update a collection based on the deletion of a form it references.

    This function is called in the :class:`FormsController` when a form is
    deleted.  It is called on each collection that references the deleted form
    and the changes to each of those collections are propagated through all of
    the collections that reference them, and so on.
    
    :param collection: a collection model object.
    :param referenced_form: a form model object.
    :returns: ``None``.

    """
    collection_dict = collection.get_full_dict()
    collection.contents = remove_references_to_this_form(collection.contents, referenced_form.id)
    collections_referenced = get_collections_referenced(collection.contents)
    collection.contents_unpacked = generate_contents_unpacked(
                                collection.contents, collections_referenced)
    collection.html = h.get_HTML_from_contents(collection.contents_unpacked,
                                              collection.markup_language)
    collection.datetime_modified = datetime.datetime.utcnow()
    backup_collection(collection_dict)
    update_collections_that_reference_this_collection(
        collection, OldcollectionsController.query_builder, contents_changed=True)
    Session.add(collection)
    Session.commit()


def remove_references_to_this_form(contents, form_id):
    """Remove references to a form from the ``contents`` value of another collection.

    :param unicode contents: the value of the ``contents`` attribute of a collection.
    :param int form_id: an ``id`` value of a form.
    :returns: the modified ``contents`` string.

    """
    #patt = re.compile('[Ff]orm\[(%d)\]' % form_id)
    patt = re.compile(h.form_reference_pattern.pattern.replace('\d+',
                                                        str(form_id)))
    return patt.sub('', contents)

def remove_references_to_this_collection(contents, collection_id):
    """Remove references to a collection from the ``contents`` value of another collection.
    
    :param unicode contents: the value of the ``contents`` attribute of a collection.
    :param int collection_id: an ``id`` value of a collection.
    :returns: the modified ``contents`` string.

    """
    #patt = re.compile('[cC]ollection[\[\(](%d)[\]\)]' % collection_id)
    patt = re.compile(h.collection_reference_pattern.pattern.replace('\d+',
                                                        str(collection_id)))
    return patt.sub('', contents)

def get_unicode(key, dict_):
    """Return ``dict_[key]``, making sure it defaults to a unicode object."""
    value = dict_.get(key, u'')
    if isinstance(value, unicode):
        return value
    elif isinstance(value, str):
        return unicode(value)
    return u''

def get_contents(collection_id, collections_referenced):
    """Return the ``contents`` value of the collection with ``collection_id`` as its ``id`` value.

    :param int collection_id: the ``id`` value of a collection model.
    :param dict collections_referenced: the collections (recursively) referenced by a collection.
    :returns: the contents of a collection, or a warning message.

    """
    return getattr(collections_referenced[collection_id],
                   u'contents',
                   u'Collection %d has no contents.' % collection_id)

def generate_contents_unpacked(contents, collections_referenced, patt=None):
    """Generate the ``contents_unpacked`` value of a collection.
    
    :param unicode contents: the value of the ``contents`` attribute of a collection
    :param dict collections_referenced: the collection models referenced by a
        collection; keys are collection ``id`` values.
    :param patt: a compiled regexp pattern object that matches collection references.
    :returns: a unicode object as a value for the ``contents_unpacked`` attribute
        of a collection model.

    .. note::
    
        Circular, invalid and unauthorized reference chains are caught in the
        generation of ``collections_referenced``.

    """
    patt = patt or re.compile(h.collection_reference_pattern)
    return patt.sub(
        lambda m: generate_contents_unpacked(
            get_contents(int(m.group(1)), collections_referenced),
            collections_referenced, patt),
        contents
    )

# Three custom error classes to raise when collection.contents are invalid
class CircularCollectionReferenceError(Exception):
    pass

class InvalidCollectionReferenceError(Exception):
    pass

class UnauthorizedCollectionReferenceError(Exception):
    pass

def get_collection(collection_id, user, unrestricted_users):
    """Return the collection such that ``collection.id==collection_id``.

    If the collection does not exist or if ``user`` is not authorized to access
    it, raise an appropriate error.

    :param int collection_id: the ``id`` value of a collection.
    :param user: a user model of the logged in user.
    :param list unrestricted_users: the unrestricted users of the system.
    :return: a collection model object.

    """
    collection = Session.query(Collection).get(collection_id)
    if collection:
        if user is None or unrestricted_users is None or \
        h.user_is_authorized_to_access_model(user, collection, unrestricted_users):
            return collection
        else:
            raise UnauthorizedCollectionReferenceError(collection_id)
    raise InvalidCollectionReferenceError(collection_id)


################################################################################
# Get data for requests to /collections/new and /collections/{id}/edit requests
################################################################################

def get_new_edit_collection_data(GET_params):
    """Return the data necessary to create a new OLD collection or update an existing one.
    
    :param GET_params: the ``request.GET`` dictionary-like object generated by
        Pylons which contains the query string parameters of the request.
    :returns: A dictionary whose values are lists of objects needed to create or
        update collections.

    If ``GET_params`` has no keys, then return all data.  If ``GET_params`` does
    have keys, then for each key whose value is a non-empty string (and not a
    valid ISO 8601 datetime) add the appropriate list of objects to the return
    dictionary.  If the value of a key is a valid ISO 8601 datetime string, add
    the corresponding list of objects *only* if the datetime does *not* match
    the most recent ``datetime_modified`` value of the resource.  That is, a
    non-matching datetime indicates that the requester has out-of-date data.

    """
    # Map param names to the OLD model objects from which they are derived.
    param_name2model_name = {
        'speakers': 'Speaker',
        'users': 'User',
        'tags': 'Tag',
        'sources': 'Source'
    }

    # map_ maps param names to functions that retrieve the appropriate data
    # from the db.
    map_ = {
        'speakers': h.get_mini_dicts_getter('Speaker'),
        'users': h.get_mini_dicts_getter('User'),
        'tags': h.get_mini_dicts_getter('Tag'),
        'sources': h.get_mini_dicts_getter('Source')
    }

    # result is initialized as a dict with empty list values.
    result = dict([(key, []) for key in map_])
    result['collection_types'] = h.collection_types
    result['markup_languages'] = h.markup_languages

    # There are GET params, so we are selective in what we return.
    if GET_params:
        for key in map_:
            val = GET_params.get(key)
            # Proceed so long as val is not an empty string.
            if val:
                val_as_datetime_obj = h.datetime_string2datetime(val)
                if val_as_datetime_obj:
                    # Value of param is an ISO 8601 datetime string that
                    # does not match the most recent datetime_modified of the
                    # relevant model in the db: therefore we return a list
                    # of objects/dicts.  If the datetimes do match, this
                    # indicates that the requester's own stores are
                    # up-to-date so we return nothing.
                    if val_as_datetime_obj != h.get_most_recent_modification_datetime(
                    param_name2model_name[key]):
                        result[key] = map_[key]()
                else:
                    result[key] = map_[key]()

    # There are no GET params, so we get everything from the db and return it.
    else:
        for key in map_:
            result[key] = map_[key]()

    return result

################################################################################
# Collection Create & Update Functions
################################################################################

def create_new_collection(data, collections_referenced):
    """Create a new collection.

    :param dict data: the collection to be created.
    :param dict collections_referenced: the collection models recursively referenced in ``data['contents']``.
    :returns: an SQLAlchemy model object representing the collection.

    """
    collection = Collection()
    collection.UUID = unicode(uuid4())

    # User-inputted string data
    collection.title = h.normalize(data['title'])
    collection.type = h.normalize(data['type'])
    collection.url = h.normalize(data['url'])
    collection.description = h.normalize(data['description'])
    collection.markup_language = h.normalize(data['markup_language'])
    collection.contents = h.normalize(data['contents'])
    collection.contents_unpacked = h.normalize(data['contents_unpacked'])
    collection.html = h.get_HTML_from_contents(collection.contents_unpacked,
                                            collection.markup_language)

    # User-inputted date: date_elicited
    collection.date_elicited = data['date_elicited']

    # Many-to-One
    if data['elicitor']:
        collection.elicitor = data['elicitor']
    if data['speaker']:
        collection.speaker = data['speaker']
    if data['source']:
        collection.source = data['source']

    # Many-to-Many: tags, files & forms
    collection.tags = [t for t in data['tags'] if t]
    collection.files = [f for f in data['files'] if f]
    collection.forms = [f for f in data['forms'] if f]

    # Restrict the entire collection if it is associated to restricted forms or
    # files or if it references a restricted collection in its contents field.
    immediately_referenced_collections = get_collections_referenced_in_contents(
                                            collection, collections_referenced)
    tags = [f.tags for f in collection.files + collection.forms + immediately_referenced_collections]
    tags = [tag for tag_list in tags for tag in tag_list]
    restricted_tags = [tag for tag in tags if tag.name == u'restricted']
    if restricted_tags:
        restricted_tag = restricted_tags[0]
        if restricted_tag not in collection.tags:
            collection.tags.append(restricted_tag)

    # OLD-generated Data
    now = datetime.datetime.utcnow()
    collection.datetime_entered = now
    collection.datetime_modified = now
    # Because of SQLAlchemy's uniqueness constraints, we may need to set the
    # enterer to the elicitor.
    if data['elicitor'] and (data['elicitor'].id == session['user'].id):
        collection.enterer = data['elicitor']
    else:
        collection.enterer = session['user']

    return collection


def update_collection(collection, data, collections_referenced):
    """Update a collection model.

    :param collection: the collection model to be updated.
    :param dict data: representation of the updated collection.
    :param dict collections_referenced: the collection models recursively referenced in ``data['contents']``.
    :returns: a 3-tuple where the second and third elements are invariable
        booleans indicating whether the collection has become restricted or has
        had its ``contents`` value changed as a result of the update,
        respectively.  The first element is the updated collection or ``False``
        of the no update has occurred.

    """
    changed = False
    restricted = False
    contents_changed = False

    # Unicode Data
    changed = collection.set_attr('title', h.normalize(data['title']), changed)
    changed = collection.set_attr('type', h.normalize(data['type']), changed)
    changed = collection.set_attr('url', h.normalize(data['url']), changed)
    changed = collection.set_attr('description', h.normalize(data['description']), changed)
    changed = collection.set_attr('markup_language', h.normalize(data['markup_language']), changed)
    submitted_contents = h.normalize(data['contents'])
    if collection.contents != submitted_contents:
        collection.contents = submitted_contents
        contents_changed = changed = True
    changed = collection.set_attr('contents_unpacked', h.normalize(data['contents_unpacked']), changed)
    changed = collection.set_attr('html', h.get_HTML_from_contents(collection.contents_unpacked,
                                                      collection.markup_language), changed)

    # User-entered date: date_elicited
    changed = collection.set_attr('date_elicited', data['date_elicited'], changed)

    # Many-to-One Data
    changed = collection.set_attr('elicitor', data['elicitor'], changed)
    changed = collection.set_attr('speaker', data['speaker'], changed)
    changed = collection.set_attr('source', data['source'], changed)

    # Many-to-Many Data: files, forms & tags
    # Update only if the user has made changes.
    files_to_add = [f for f in data['files'] if f]
    forms_to_add = [f for f in data['forms'] if f]
    tags_to_add = [t for t in data['tags'] if t]

    if set(files_to_add) != set(collection.files):
        collection.files = files_to_add
        changed = True

    if set(forms_to_add) != set(collection.forms):
        collection.forms = forms_to_add
        changed = True

    # Restrict the entire collection if it is associated to restricted forms or
    # files or if it references a restricted collection.
    tags = [f.tags for f in collection.files + collection.forms + collections_referenced.values()]
    tags = [tag for tag_list in tags for tag in tag_list]
    restricted_tags = [tag for tag in tags if tag.name == u'restricted']
    if restricted_tags:
        restricted_tag = restricted_tags[0]
        if restricted_tag not in tags_to_add:
            tags_to_add.append(restricted_tag)

    if set(tags_to_add) != set(collection.tags):
        if u'restricted' in [t.name for t in tags_to_add] and \
        u'restricted' not in [t.name for t in collection.tags]:
            restricted = True
        collection.tags = tags_to_add
        changed = True

    if changed:
        collection.datetime_modified = datetime.datetime.utcnow()
        session['user'] = Session.merge(session['user'])
        collection.modifier = session['user']
        return collection, restricted, contents_changed
    return changed, restricted, contents_changed
