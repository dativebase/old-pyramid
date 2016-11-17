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

import datetime
import logging
import re
import json
from uuid import uuid4

from formencode.validators import Invalid

from old.lib.constants import (
    COLLECTION_REFERENCE_PATTERN,
    FORM_REFERENCE_PATTERN,
    JSONDecodeErrorResponse,
    UNAUTHORIZED_MSG
)
import old.lib.helpers as h
from old.models import (
    Collection,
    CollectionBackup,
    Form
)
from old.views.resources import (
    Resources,
    SchemaState
)


LOGGER = logging.getLogger(__name__)


# Three custom error classes to raise when collection.contents are invalid


class CircularCollectionReferenceError(Exception):
    pass


class InvalidCollectionReferenceError(Exception):
    pass


class UnauthorizedCollectionReferenceError(Exception):
    pass


class Collections(Resources):
    """Generate responses to requests on collection resources.

    The collections view is one of the more complex ones. A great deal of
    this complexity arised from the fact that collections can reference forms
    and other collections in the value of their ``contents`` attribute. The
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

    def create(self):
        """Create a new resource and return it.
        :URL: ``POST /<resource_collection_name>``
        :request body: JSON object representing the resource to create.
        :returns: the newly created resource.
        """
        schema = self.schema_cls()
        try:
            values = json.loads(self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return JSONDecodeErrorResponse
        try:
            state, collections_referenced = self._get_create_state(values)
        except InvalidCollectionReferenceError as error:
            self.request.response.status_int = 400
            return {'error': 'Invalid collection reference error: there is no'
                             ' collection with id %d' % error.args[0]}
        except UnauthorizedCollectionReferenceError as error:
            self.request.response.status_int = 403
            return {'error': 'Unauthorized collection reference error: you are'
                             ' not authorized to access collection %d' %
                             error.args[0]}
        try:
            data = schema.to_python(values, state)
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}
        resource = self._create_new_resource(data, collections_referenced)
        self.request.dbsession.add(resource)
        self.request.dbsession.flush()
        self._post_create(resource)
        return resource.get_full_dict()

    def update(self):
        """Update a collection and return it.
        :URL: ``PUT /collections/id``
        :Request body: JSON object representing the collection with updated
            attribute values.
        :param str id: the ``id`` value of the collection to be updated.
        :returns: the updated collection model.
        """
        resource_model, id_ = self._model_from_id(eager=True)
        if not resource_model:
            self.request.response.status_int = 404
            return {'error': 'There is no %s with id %s' % (self.member_name,
                                                            id_)}
        if self._model_access_unauth(resource_model) is not False:
            self.request.response.status_int = 403
            return UNAUTHORIZED_MSG
        schema = self.schema_cls()
        try:
            values = json.loads(self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return JSONDecodeErrorResponse
        try:
            state, collections_referenced = self._get_create_state(
                values, collection_id=id_)
        except InvalidCollectionReferenceError as error:
            self.request.response.status_int = 400
            return {'error': 'Invalid collection reference error: there is no'
                             ' collection with id %d' % error.args[0]}
        except UnauthorizedCollectionReferenceError as error:
            self.request.response.status_int = 403
            return {'error': 'Unauthorized collection reference error: you are'
                             ' not authorized to access collection %d' %
                             error.args[0]}
        except CircularCollectionReferenceError as error:
            self.request.response.status_int = 400
            return {
                'error': 'Circular collection reference error: collection %d'
                         ' references collection %d.' % (id_, error.args[0])}
        try:
            data = schema.to_python(values, state)
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}

        collection_dict = resource_model.get_full_dict()
        resource_model, restricted, contents_changed = \
            self._update_resource_model(resource_model, data,
                                        collections_referenced)
        # resource_model will be False if there are no changes (cf. update_collection).
        if not resource_model:
            self.request.response.status_int = 400
            return {'error': 'The update request failed because the submitted'
                             ' data were not new.'}
        self._backup_resource(collection_dict)
        self._update_collections_that_reference_this_collection(
            resource_model, restricted=restricted,
            contents_changed=contents_changed)
        self.request.dbsession.add(resource_model)
        self.request.dbsession.flush()
        return resource_model.get_full_dict()

    # Because collection creation/update is special, the following three
    # abtract methods are not useful and need to be declared vacuously.

    def _get_user_data(self, data):
        pass

    def _get_create_data(self, data):
        pass

    def _get_update_data(self, user_data):
        pass

    def _pre_delete(self, collection):
        self._update_collections_that_reference_this_collection(
            collection, deleted=True)

    def _get_delete_dict(self, resource_model):
        return resource_model.get_full_dict()

    def _get_show_dict(self, resource_model):
        """A request to GET /collections/<id> may return a LaTeX representation
        of the collection, if the relevant GET params are supplied.
        """
        result = resource_model.get_full_dict()
        # TODO: deal with markdown2latex ...
        if (    self.request.GET.get('latex') and
                resource_model.markup_language == 'reStructuredText'):
            result['latex'] = h.rst2latex(resource_model.contents_unpacked)
        return result

    def _get_new_edit_collections(self):
        """Returns the names of the collections that are required in order to
        create a new, or edit an existing, form.
        """
        return (
            'collection_types',
            'markup_languages',
            'sources',
            'speakers',
            'tags',
            'users'
        )

    def _filter_query(self, query_obj):
        """Depending on the unrestrictedness of the user and the
        unrestrictedness of the forms in the query, filter it, or not.
        """
        return self._filter_restricted_models(query_obj)

    def _delete_unauth(self, form):
        """Only administrators and a form's enterer can delete it."""
        if (    self.logged_in_user.role == 'administrator' or
                form.enterer.id == self.logged_in_user.id):
            return False
        return True

    def _model_access_unauth(self, resource_model):
        """Ensure that only authorized users can access the provided
        ``resource_model``.
        """
        unrestricted_users = self.db.get_unrestricted_users()
        if not self.logged_in_user.is_authorized_to_access_model(
                resource_model, unrestricted_users):
            return True
        return False

    def _backup_resource(self, collection_dict):
        """Backup a collection.
        :param dict form_dict: a representation of a collection model.
        :returns: ``None``
        """
        collection_backup = CollectionBackup()
        collection_backup.vivify(collection_dict)
        self.request.dbsession.add(collection_backup)

    def _get_create_state(self, values, collection_id=None):
        """Return a SchemaState instance for validation of the resource during
        a create request. Also return the collections referenced by this
        collection.
        """
        collections_referenced = self._get_collections_referenced(
            values['contents'], collection_id=collection_id)
        values = _add_contents_unpacked_to_values(values, collections_referenced)
        values = _add_form_ids_list_to_values(values)
        return (
            SchemaState(
                full_dict=values,
                db=self.db,
                logged_in_user=self.logged_in_user),
            collections_referenced
        )

    def _create_new_resource(self, data, collections_referenced):
        """Create a new collection.
        :param dict data: the collection to be created.
        :returns: an SQLAlchemy model object representing the collection.
        """
        collection = Collection()
        collection.UUID = str(uuid4())
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
        immediately_referenced_collections = \
            _get_collections_referenced_in_contents(
                collection, collections_referenced)
        tags = [f.tags for f in collection.files + collection.forms +
                immediately_referenced_collections]
        tags = [tag for tag_list in tags for tag in tag_list]
        restricted_tags = [tag for tag in tags if tag.name == 'restricted']
        if restricted_tags:
            restricted_tag = restricted_tags[0]
            if restricted_tag not in collection.tags:
                collection.tags.append(restricted_tag)
        # OLD-generated Data
        now = datetime.datetime.utcnow()
        collection.datetime_entered = now
        collection.datetime_modified = now
        collection.enterer = collection.modifier = self.logged_in_user
        return collection

    def _update_resource_model(self, collection, data, collections_referenced):
        """Update a collection model.
        :param collection: the collection model to be updated.
        :param dict data: representation of the updated collection.
        :param dict collections_referenced: the collection models recursively
            referenced in ``data['contents']``.
        :returns: a 3-tuple where the second and third elements are invariable
            booleans indicating whether the collection has become restricted or has
            had its ``contents`` value changed as a result of the update,
            respectively. The first element is the updated collection or ``False``
            of the no update has occurred.
        """
        changed = False
        restricted = False
        contents_changed = False
        # Unicode Data
        changed = collection.set_attr(
            'title', h.normalize(data['title']), changed)
        changed = collection.set_attr(
            'type', h.normalize(data['type']), changed)
        changed = collection.set_attr(
            'url', h.normalize(data['url']), changed)
        changed = collection.set_attr(
            'description', h.normalize(data['description']), changed)
        changed = collection.set_attr(
            'markup_language', h.normalize(data['markup_language']), changed)
        submitted_contents = h.normalize(data['contents'])
        if collection.contents != submitted_contents:
            collection.contents = submitted_contents
            contents_changed = changed = True
        changed = collection.set_attr(
            'contents_unpacked', h.normalize(data['contents_unpacked']),
            changed)
        changed = collection.set_attr(
            'html', h.get_HTML_from_contents(collection.contents_unpacked,
                                             collection.markup_language),
            changed)
        # User-entered date: date_elicited
        changed = collection.set_attr(
            'date_elicited', data['date_elicited'], changed)
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
        # Restrict the entire collection if it is associated to restricted
        # forms or files or if it references a restricted collection.
        tags = [f.tags for f in collection.files + collection.forms +
                list(collections_referenced.values())]
        tags = [tag for tag_list in tags for tag in tag_list]
        restricted_tags = [tag for tag in tags if tag.name == 'restricted']
        if restricted_tags:
            restricted_tag = restricted_tags[0]
            if restricted_tag not in tags_to_add:
                tags_to_add.append(restricted_tag)
        if set(tags_to_add) != set(collection.tags):
            if (    'restricted' in [t.name for t in tags_to_add] and
                    'restricted' not in [t.name for t in collection.tags]):
                restricted = True
            collection.tags = tags_to_add
            changed = True
        if changed:
            collection.datetime_modified = datetime.datetime.utcnow()
            collection.modifier = self.logged_in_user
            return collection, restricted, contents_changed
        return changed, restricted, contents_changed

    def _update_contents_unpacked_etc(self, collection, **kwargs):
        deleted = kwargs.get('deleted', False)
        collection_id = kwargs.get('collection_id')
        if deleted:
            collection.contents = _remove_references_to_this_collection(
                collection.contents, collection_id)
        collections_referenced = self._get_collections_referenced(
            collection.contents)
        collection.contents_unpacked = _generate_contents_unpacked(
            collection.contents, collections_referenced)
        collection.html = h.get_HTML_from_contents(
            collection.contents_unpacked, collection.markup_language)
        collection.forms = [self.request.dbsession.query(Form).get(int(id))
                            for id in
                            FORM_REFERENCE_PATTERN.findall(
                                collection.contents_unpacked)]

    def _update_collections_that_reference_this_collection(self, collection,
                                                           **kwargs):
        """Update all collections that reference the input collection.
        :param collection: a collection model.
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
        restricted = kwargs.get('restricted', False)
        contents_changed = kwargs.get('contents_changed', False)
        deleted = kwargs.get('deleted', False)
        if restricted or contents_changed or deleted:
            collections_referencing_this_collection = \
                self._get_collections_referencing_this_collection(collection)
            collections_referencing_this_collection_dicts = [
                c.get_full_dict() for c in
                collections_referencing_this_collection]
            now = h.now()
            if restricted:
                restricted_tag = self.db.get_restricted_tag()
                for collection_ in collections_referencing_this_collection:
                    collection_.tags.append(restricted_tag)
            if contents_changed:
                for collection_ in collections_referencing_this_collection:
                    self._update_contents_unpacked_etc(collection_)
            if deleted:
                for collection_ in collections_referencing_this_collection:
                    self._update_contents_unpacked_etc(
                        collection_, collection_id=collection.id, deleted=True)
            for collection_ in collections_referencing_this_collection:
                collection_.datetime_modified = now
                collection_.modifier = self.logged_in_user
            for colldict in collections_referencing_this_collection_dicts:
                self._backup_resource(colldict)
            self.request.dbsession.add_all(collections_referencing_this_collection)
            self.request.dbsession.flush()

    def _get_collections_referenced(self, contents, collection_id=None,
                                    patt=None):
        """Return the collections (recursively) referenced by the input
        ``contents`` value.
        That is, return all of the collections referenced in the input ``contents``
        value, plus all of the collections referenced in those collections, etc.
        :param unicode contents: the value of the ``contents`` attribute of a
            collection.
        :param int collection_id: the ``id`` value of a collection.
        :param patt: a compiled regular expression object.
        :returns: a dictionary whose keys are collection ``id`` values and whose
            values are collection models.
        """
        patt = patt or re.compile(COLLECTION_REFERENCE_PATTERN)
        collections_referenced = {int(id_): self._get_collection(int(id_))
                                  for id_ in patt.findall(contents)}
        temp = collections_referenced.copy()
        if collection_id in collections_referenced:
            raise CircularCollectionReferenceError(collection_id)
        for id_ in temp:
            collections_referenced.update(
                self._get_collections_referenced(
                    collections_referenced[id_].contents,
                    collection_id=collection_id,
                    patt=patt)
            )
        return collections_referenced

    def _get_collection(self, collection_id):
        """Return the collection such that ``collection.id==collection_id``.
        If the collection does not exist or if the logged in user is not
        authorized to access it, raise an appropriate error.
        :param int collection_id: the ``id`` value of a collection.
        :return: a collection model object.
        """
        collection = self.request.dbsession.query(Collection).get(collection_id)
        if collection:
            if self._model_access_unauth(collection):
                raise UnauthorizedCollectionReferenceError(collection_id)
            else:
                return collection
        else:
            raise InvalidCollectionReferenceError(collection_id)

    def _get_collections_referencing_this_collection(self, collection):
        """Return all collections that recursively reference ``collection``.
        That is, return all collections that reference ``collection`` plus all
        collections that reference those referencing collections, etc.
        :param collection: a collection model object.
        :param query_builder: an :class:`SQLAQueryBuilder` instance.
        :returns: a list of collection models.
        """
        patt = COLLECTION_REFERENCE_PATTERN.pattern.replace(
            '\d+', str(collection.id)).replace('\\', '')
        query = {'filter': ['Collection', 'contents', 'regex', patt]}
        result = self.query_builder.get_SQLA_query(query).all()
        for c in result[:]:
            result += self._get_collections_referencing_this_collection(c)
        return result

    def _update_collection_by_deletion_of_referenced_form(self, collection,
                                                          referenced_form):
        """Update a collection based on the deletion of a form it references.
        This function is called in :class:`Forms` when a form is deleted. It is
        called on each collection that references the deleted form and the
        changes to each of those collections are propagated through all of the
        collections that reference them, and so on.
        :param collection: a collection model object.
        :param referenced_form: a form model object.
        :returns: ``None``.
        # TODO: this is imported by forms.py as a function. Fix there! ...
        """
        collection_dict = collection.get_full_dict()
        collection.contents = _remove_references_to_this_form(
            collection.contents, referenced_form.id)
        collections_referenced = self._get_collections_referenced(
            collection.contents)
        collection.contents_unpacked = _generate_contents_unpacked(
            collection.contents, collections_referenced)
        collection.html = h.get_HTML_from_contents(collection.contents_unpacked,
                                                   collection.markup_language)
        collection.datetime_modified = datetime.datetime.utcnow()
        self._backup_resource(collection_dict)
        self._update_collections_that_reference_this_collection(
            collection, contents_changed=True)
        self.request.dbsession.add(collection)
        self.request.dbsession.flush()


def _add_form_ids_list_to_values(values):
    """Add a list of referenced form ids to values.
    :param dict values: data for creating or updating a collection
    :returns: ``values`` with a ``'forms'`` key whose value is a list of id
        integers.
    """
    contents_unpacked = get_str('contents_unpacked', values)
    values['forms'] = [int(id) for id in
                       FORM_REFERENCE_PATTERN.findall(contents_unpacked)]
    return values


def _add_contents_unpacked_to_values(values, collections_referenced):
    """Add a ``'contents_unpacked'`` value to values and return values.
    :param dict values: data for creating a collection.
    :param dict collections_referenced: keys are collection ``id`` values and
        values are collection models.
    :returns: ``values`` updated.
    """
    contents = get_str('contents', values)
    values['contents_unpacked'] = _generate_contents_unpacked(
        contents, collections_referenced)
    return values


def _get_collections_referenced_in_contents(collection, collections_referenced):
    """Get the immediately referenced collections of a collection.
    :param collection: a collection model.
    :param dict collections_referenced: keys are collection ``id`` values and
        values are collection models.
    :returns: a list of collection models; useful in determining whether
        directly referenced collections are restricted.
    """
    return [collections_referenced[int(id_)]
            for id_ in COLLECTION_REFERENCE_PATTERN.findall(collection.contents)]


def _remove_references_to_this_form(contents, form_id):
    """Remove references to a form from the ``contents`` value of another
    collection.
    :param unicode contents: the value of the ``contents`` attribute of a
        collection.
    :param int form_id: an ``id`` value of a form.
    :returns: the modified ``contents`` string.
    """
    patt = re.compile(FORM_REFERENCE_PATTERN.pattern.replace(
        '\d+', str(form_id)))
    return patt.sub('', contents)


def _remove_references_to_this_collection(contents, collection_id):
    """Remove references to a collection from the ``contents`` value of another
    collection.
    :param unicode contents: the value of the ``contents`` attribute of a
        collection.
    :param int collection_id: an ``id`` value of a collection.
    :returns: the modified ``contents`` string.
    """
    patt = re.compile(
        COLLECTION_REFERENCE_PATTERN.pattern.replace('\d+', str(collection_id)))
    return patt.sub('', contents)


def get_str(key, dict_):
    """Return ``dict_[key]``, making sure it defaults to a string object."""
    value = dict_.get(key, '')
    if isinstance(value, str):
        return value
    return ''


def get_contents(collection_id, collections_referenced):
    """Return the ``contents`` value of the collection with ``collection_id`` as its ``id`` value.

    :param int collection_id: the ``id`` value of a collection model.
    :param dict collections_referenced: the collections (recursively) referenced by a collection.
    :returns: the contents of a collection, or a warning message.

    """
    return getattr(collections_referenced[collection_id],
                   'contents',
                   'Collection %d has no contents.' % collection_id)


def _generate_contents_unpacked(contents, collections_referenced, patt=None):
    """Generate the ``contents_unpacked`` value of a collection.
    :param unicode contents: the value of the ``contents`` attribute of a
        collection
    :param dict collections_referenced: the collection models referenced by a
        collection; keys are collection ``id`` values.
    :param patt: a compiled regexp pattern object that matches collection
        references.
    :returns: a unicode object as a value for the ``contents_unpacked``
        attribute of a collection model.
    .. note::

        Circular, invalid and unauthorized reference chains are caught in the
        generation of ``collections_referenced``.
    """
    patt = patt or re.compile(COLLECTION_REFERENCE_PATTERN)
    return patt.sub(
        lambda m: _generate_contents_unpacked(
            get_contents(int(m.group(1)), collections_referenced),
            collections_referenced, patt),
        contents
    )
