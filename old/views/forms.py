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

"""Contains the :class:`FormsView` and its auxiliary functions.

.. module:: forms
   :synopsis: Contains the forms view and its auxiliary functions.

"""

import logging
import re
import json
from uuid import uuid4

from formencode.validators import Invalid
from sqlalchemy import bindparam
from sqlalchemy.sql import asc, or_
from sqlalchemy.orm import subqueryload

from old.lib.constants import (
    DEFAULT_DELIMITER,
    FORM_REFERENCE_PATTERN,
    JSONDecodeErrorResponse,
    UNAUTHORIZED_MSG,
    UNKNOWN_CATEGORY,
)
from old.lib.dbutils import get_last_modified
import old.lib.helpers as h
from old.lib.schemata import FormIdsSchema
from old.models import (
    Form,
    FormBackup,
    Collection,
    User
)
from old.views.resources import (
    Resources,
    SchemaState
)


LOGGER = logging.getLogger(__name__)
MORPH_ATTRS = (
    'morpheme_break_ids',
    'morpheme_gloss_ids',
    'syntactic_category_string',
    'break_gloss_category'
)


class Forms(Resources):
    """Generate responses to requests on form resources."""

    def _filter_query(self, query_obj):
        """Depending on the unrestrictedness of the user and the
        unrestrictedness of the forms in the query, filter it, or not.
        """
        return self._filter_restricted_models(query_obj)

    def __headers_control(self, result):
        """Set Last-Modified in response header and return 304 if the requester
        already has an up-to-date cache of the results of this call to index/
        WARNING: _headers_control de-activated in forms because it is not
        working correctly: at present, it tells the browser to cache when it
        should not.
        """
        last_modified = get_last_modified(result)
        if last_modified:
            self.request.response.last_modified = last_modified
            self.request.response.cache_control = 'private, max-age=31536000'
        if_modified_since = self.request.if_modified_since
        if (last_modified and if_modified_since and
                last_modified == if_modified_since):
            # In this case, the browser will use its cached response.
            self.request.response.status_int = 304
            return ''
        return False

    def _backup_resource(self, form_dict):
        """Backup a form.
        :param dict form_dict: a representation of a form model.
        """
        form_backup = FormBackup()
        form_backup.vivify(form_dict)
        self.request.dbsession.add(form_backup)

    def _post_create(self, form_model):
        """Update any morphologically complex forms that may contain
        this form as a morpheme.
        """
        self.update_forms_containing_this_form_as_morpheme(form_model)

    def _post_update(self, form, form_dict):
        """If the form has changed, then update any morphologically complex
        forms that may contain this form as a morpheme.
        """
        if update_has_changed_the_analysis(form, form_dict):
            self.update_forms_containing_this_form_as_morpheme(
                form, 'update', form_dict)

    def _get_new_edit_collections(self):
        """Returns the names of the collections that are required in order to
        create a new, or edit an existing, form.
        """
        return (
            'grammaticalities',
            'elicitation_methods',
            'tags',
            'syntactic_categories',
            'speakers',
            'users',
            'sources'
        )

    def _model_access_unauth(self, resource_model):
        """Ensure that only authorized users can access the provided
        ``resource_model``.
        """
        unrestricted_users = self.db.get_unrestricted_users()
        if not self.logged_in_user.is_authorized_to_access_model(
                resource_model, unrestricted_users):
            return True
        return False

    def _delete_unauth(self, form):
        """Only administrators and a form's enterer can delete it."""
        if (    self.logged_in_user.role == 'administrator' or
                form.enterer.id == self.logged_in_user.id):
            return False
        return True

    def _pre_delete(self, form):
        """Fix any collections that may be referencing this form prior to its
        deletion.
        """
        self._update_collections_referencing_this_form(form)

    def _post_delete(self, form):
        """Perform actions after deleting ``resource_model`` from the
        database.
        """
        self.update_forms_containing_this_form_as_morpheme(form, 'delete')

    def _create_new_resource(self, data):
        """Create a new form resource.
        :param dict data: the data for the resource to be created.
        :returns: an SQLAlchemy model object representing the resource.
        Note: we override this super-class method because forms are special: we
        need to add the model to the database and get an id value so that forms
        can reference themselves in their morphological analysis-related
        attributes.
        """
        form_model = super()._create_new_resource(data)
        self.request.dbsession.add(form_model)
        (
            form_model.morpheme_break_ids,
            form_model.morpheme_gloss_ids,
            form_model.syntactic_category_string,
            form_model.break_gloss_category,
            _
        ) = self.compile_morphemic_analysis(form_model)
        return form_model

    def _update_resource_model(self, form_model, data):
        """Update ``form_model`` with ``data`` and return something other
        than ``False`` if form_model has changed as a result.
        :param form_model: the resource model to be updated.
        :param dict data: user-supplied representation of the updated resource.
        :returns: the updated resource model or, if ``changed`` has not been set
            to ``True``, ``False``.
        """
        changed = super()._update_resource_model(form_model, data)
        if changed:
            form_model = changed
        (
            data['morpheme_break_ids'],
            data['morpheme_gloss_ids'],
            data['syntactic_category_string'],
            data['break_gloss_category'],
            _
        ) = self.compile_morphemic_analysis(form_model)
        if not changed:
            for attr in MORPH_ATTRS:
                if self._distinct(attr, data[attr], getattr(form_model, attr)):
                    changed = True
                    break
        if changed:
            for attr in MORPH_ATTRS:
                setattr(form_model, attr, data[attr])
            return form_model
        return changed

    def _distinct(self, attr, new_val, existing_val):
        """Return true if ``new_val`` is distinct from ``existing_val``. The
        ``attr`` value is provided so that certain attributes (e.g., m2m) can
        have a special definition of "distinct".
        """
        if attr == 'translations':
            # Check if the user has made any changes to the translations.
            # If there are changes, then delete all translations and replace
            # with ones. (Note: this will result in the deletion of a
            # translation and the recreation of an identical one with a
            # different index. There may be a "better" way of doing this, but
            # this way is simple...)
            existing_translations = [
                (t.transcription, t.grammaticality) for t in existing_val]
            new_translations = [
                (t.transcription, t.grammaticality) for t in new_val]
            if set(existing_translations) == set(new_translations):
                return False
            return True
        elif attr in ('files', 'tags'):
            if set(new_val) == set(existing_val):
                return False
            return True
        else:
            return new_val != existing_val

    def _get_create_data(self, data):
        user_data = self._get_user_data(data)
        now = h.now()
        # user_dict = self.request.session['user']
        # user_model = self.request.dbsession.query(User).get(user_dict['id'])
        user_model = self.logged_in_user
        user_data.update({
            'datetime_modified': now,
            'datetime_entered': now,
            'UUID': str(uuid4()),
            'enterer': user_model,
            'modifier': user_model
        })
        return user_data

    def _get_update_data(self, user_data):
        now = h.now()
        user_dict = self.request.session['user']
        user_model = self.request.dbsession.query(User).get(user_dict['id'])
        user_data.update({
            'datetime_modified': now,
            'modifier': user_model
        })
        return user_data

    def _get_user_data(self, data):
        user_data = {
            # Unicode Data
            'transcription': h.to_single_space(
                h.normalize(data['transcription'])),
            'phonetic_transcription': h.to_single_space(
                h.normalize(data['phonetic_transcription'])),
            'narrow_phonetic_transcription': h.to_single_space(
                h.normalize(data['narrow_phonetic_transcription'])),
            'morpheme_break': h.to_single_space(
                h.normalize(data['morpheme_break'])),
            'morpheme_gloss': h.to_single_space(
                h.normalize(data['morpheme_gloss'])),
            'comments': h.normalize(data['comments']),
            'speaker_comments': h.normalize(data['speaker_comments']),
            'syntax': h.normalize(data['syntax']),
            'semantics': h.normalize(data['semantics']),
            'grammaticality': data['grammaticality'],
            'status': data['status'],
            # User-entered date: date_elicited
            'date_elicited': data['date_elicited'],
            # Many-to-One
            'elicitation_method': data['elicitation_method'],
            'syntactic_category': data['syntactic_category'],
            'source': data['source'],
            'elicitor': data['elicitor'],
            'verifier': data['verifier'],
            'speaker': data['speaker'],
            # One-to-Many Data: translations
            'translations': data['translations'],
            # Many-to-Many Data: tags & files
            'tags': [t for t in data['tags'] if t],
            'files': [f for f in data['files'] if f]
        }
        # Restrict the entire form if it is associated to restricted files.
        tags = [f.tags for f in user_data['files']]
        tags = [tag for tag_list in tags for tag in tag_list]
        restricted_tags = [tag for tag in tags if tag.name == 'restricted']
        if restricted_tags:
            restricted_tag = restricted_tags[0]
            if restricted_tag not in user_data['tags']:
                user_data['tags'].append(restricted_tag)
        return user_data

    ###########################################################################
    # Idiosyncratic Form Resource Actions
    ###########################################################################

    def remember(self):
        """Cause the logged in user to remember the forms referenced in the
        request body.

        - URL: ``POST /forms/remember``
        - request body: A JSON object of the form ``{"forms": [ ... ]}`` where
          the value of the ``forms`` attribute is the array of form ``id``
          values representing the forms that are to be remembered.

        :returns: A list of form ``id`` values corresponding to the forms that
                  were remembered.
        """
        LOGGER.info('Attempting to remember forms for a user.')
        schema = FormIdsSchema
        try:
            values = json.loads(self.request.body.decode(self.request.charset))
        except ValueError:
            LOGGER.warning('Unable to JSON-parse request body %s in request to'
                           ' /forms/remember', self.request.body)
            self.request.response.status_int = 400
            return JSONDecodeErrorResponse
        user_model = self.logged_in_user
        state = SchemaState(
            full_dict=values,
            db=self.db,
            logged_in_user=user_model)
        try:
            data = schema.to_python(values, state)
        except Invalid as error:
            errors = error.unpack_errors()
            LOGGER.warning('Validating values %s returned error %s', values,
                           errors)
            self.request.response.status_int = 400
            for err in errors['forms']:
                if err and err.startswith('You are not authorized to access'):
                    self.request.response.status_int = 403
                    break
            return {'errors': errors}
        forms = [f for f in data['forms'] if f]
        if not forms:
            self.request.response.status_int = 404
            msg = 'No valid form ids were provided.'
            LOGGER.warning(msg)
            return {'error': msg}
        unrestricted_forms = [f for f in forms
                              if not self._model_access_unauth(f)]
        if not unrestricted_forms:
            self.request.response.status_int = 403
            LOGGER.warning(UNAUTHORIZED_MSG)
            return UNAUTHORIZED_MSG
        user_model.remembered_forms += unrestricted_forms
        user_model.datetime_modified = h.now()
        self.request.dbsession.add(user_model)
        self.request.dbsession.flush()
        self.request.session['user'] = user_model.get_dict()
        ret = [f.id for f in unrestricted_forms]
        LOGGER.info('Remembered %d forms for user %d.', len(ret), user_model.id)
        return ret

    def update_morpheme_references(self):
        """Update the morphological analysis-related attributes of all forms.

        That is, update the values of the ``morpheme_break_ids``,
        ``morpheme_gloss_ids``, ``syntactic_category_string`` and
        ``break_gloss_category`` attributes of every form in the database.

        :URL: ``PUT /forms/update_morpheme_references``
        :returns: a list of ids corresponding to the forms where the update
            caused a change in the values of the target attributes.

        .. warning::

           It should not be necessary to request the regeneration of morpheme
           references via this action since this should already be accomplished
           automatically by the calls to
           ``update_forms_containing_this_form_as_morpheme`` on all successful
           update, create and delete requests on form resources.  This action
           is, therefore, deprecated (read: use it with caution) and may be
           removed in future versions of the OLD.
        """
        LOGGER.info('Attempting to update the morphological analysis-related'
                    ' attributes of all forms.')
        forms = self.db.get_forms()
        return self.update_morpheme_references_of_forms(
            self.db.get_forms(),
            self.db.get_morpheme_delimiters(),
            whole_db=forms,
            make_backups=False
        )

    ###########################################################################
    # Form-specific private methods
    ###########################################################################

    def update_morpheme_references_of_forms(self, forms, valid_delimiters,
                                            **kwargs):
        """Update the morphological analysis-related attributes of a list of
        form models.

        Attempt to update the values of the ``morpheme_break_ids``,
        ``morpheme_gloss_ids``, ``syntactic_category_string`` and
        ``break_gloss_category`` attributes of all forms in ``forms``. The
        ``kwargs`` dict may contain ``lexical_items``,
        ``deleted_lexical_items`` or ``whole_db`` values which will be passed
        to compile_morphemic_analysis.

        :param list forms: the form models to be updated.
        :param list valid_delimiters: morpheme delimiters as strings.
        :param list kwargs['lexical_items']: a list of form models.
        :param list kwargs['deleted_lexical_items']: a list of form models.
        :param list kwargs['whole_db']: a list of all the form models in the
            database.
        :returns: a list of form ``id`` values corresponding to the forms that
            have been updated.
        """
        form_buffer = []
        formbackup_buffer = []
        make_backups = kwargs.get('make_backups', True)
        modifier_dict = self.request.session['user']
        modifier_model = self.request.dbsession.query(User).get(
            modifier_dict['id'])
        modifier_id = modifier_model.id
        modification_datetime = h.now()
        form_table = Form.__table__
        for form in forms:
            (
                morpheme_break_ids,
                morpheme_gloss_ids,
                syntactic_category_string,
                break_gloss_category,
                kwargs['cache']
            ) = self.compile_morphemic_analysis(form, valid_delimiters,
                                                **kwargs)
            if ((
                    morpheme_break_ids,
                    morpheme_gloss_ids,
                    syntactic_category_string,
                    break_gloss_category
                ) != (
                    form.morpheme_break_ids,
                    form.morpheme_gloss_ids,
                    form.syntactic_category_string,
                    form.break_gloss_category)):
                form_buffer.append({
                    'id_': form.id,
                    'morpheme_break_ids': morpheme_break_ids,
                    'morpheme_gloss_ids': morpheme_gloss_ids,
                    'syntactic_category_string':
                        syntactic_category_string,
                    'break_gloss_category': break_gloss_category,
                    'modifier_id': modifier_id,
                    'datetime_modified': modification_datetime
                })
                if make_backups:
                    formbackup = FormBackup()
                    formbackup.vivify(form.get_dict())
                    formbackup_buffer.append(formbackup)
        if form_buffer:
            rdbms_name = h.get_RDBMS_name(self.request.registry.settings)
            if rdbms_name == 'mysql':
                self.request.dbsession.execute('set names utf8;')
            update = form_table.update().where(form_table.c.id==bindparam('id_')).\
                values(**dict([(k, bindparam(k)) for k in form_buffer[0] if k !=
                               'id_']))
            self.request.dbsession.execute(update, form_buffer)
        if make_backups and formbackup_buffer:
            self.request.dbsession.add_all(formbackup_buffer)
            self.request.dbsession.flush()
        return [f['id_'] for f in form_buffer]

    def _update_collections_referencing_this_form(self, form):
        """Update all collections that reference the input form in their
        ``contents`` value.
        When a form is deleted, it is necessary to update all collections whose
        ``contents`` value references the deleted form.  The update removes the
        reference, recomputes the ``contents_unpacked``, ``html`` and ``forms``
        attributes of the affected collection and causes all of these changes to
        percolate through the collection-collection reference chain.
        :param form: a form model object
        :returns: ``None``

        .. note::

            Getting the collections that reference this form by searching for
            those whose ``forms`` attribute contain it is not quite the correct
            way to do this because many of these collections will not
            *directly* reference this form -- in short, this will result in
            redundant updates and backups.
        """
        pattern = FORM_REFERENCE_PATTERN.pattern.replace(
            '[0-9]+', str(form.id))
        collections_referencing_this_form = self.request.dbsession\
            .query(Collection).\
            filter(Collection.contents.op('regexp')(pattern)).all()
        if collections_referencing_this_form:
            from old.views.collections import Collections
            collection_view = Collections(self.request)
            for collection in collections_referencing_this_form:
                collection_view.\
                    update_collection_by_deletion_of_referenced_form(
                        collection, form)

    def get_perfect_matches(self, *args):
        """Return the list of forms that perfectly match a given morpheme.
        That is, return all forms ``f`` such that ``f.morpheme_break==morpheme``
        *and* ``f.morpheme_gloss==gloss``.

        If one of ``lexical_items`` or ``deleted_lexical_items`` is truthy, then
        the result is generated using only those lists plus the existing
        references ``form.morpheme_break_ids`` and ``form.morpheme_gloss_ids``.
        This facilitates lexical change percolation while eliminating
        unnecessary database requests.  Note that the presence of a non-empty
        ``lexical_items`` or ``deleted_lexical_items`` list implies that the
        supplied forms represent the only changes to the database relevant to
        the morphological analysis of ``form``.

        One complication arises from the fact that perfect matches mask partial
        ones.  If :func:`get_perfect_matches` removes the only perfect matches
        for a given morpheme, then it is possible that there are partial
        matches not listed in ``lexical_items``.  Therefore,
        :ref:`get_partial_matches` must be made to query the database *only*
        when the morpheme in question is encountered.  This message is passed
        to :ref:`get_partial_matches` by returning an ordered pair (tuple)
        containing the newly match-less morpheme instead of the usual list of
        matches.

        :param form: the form model whose morphological analysis-related
            attributes are being generated.
        :param int word_index: the index of the word containing the morpheme
            being analyzed.
        :param int morpheme_index: the index, within the word, of the morpheme
            being analyzed.
        :param str morpheme: the transcription of the morpheme.
        :param str gloss: the gloss of the morpheme.
        :param dict matches_found: keys are morpheme 2-tuples and values are
            lists of matches.
        :param list lexical_items: forms constituting the exclusive pool of
            potential matches.
        :param list deleted_lexical_items: forms that must be deleted from the
            matches.
        :returns: an ordered pair (tuple), where the second element is always
            the (potentially updated) ``matches_found`` dictionary.  In the
            normal case, the first element is the list of perfect matches for
            the input morpheme.  When it is necessary to force
            :func:`get_partial_matches` to query the database, the first element
            of the return value is the ``(morpheme, gloss)`` tuple representing
            the morpheme.
        """
        try:
            (form, word_index, morpheme_index, morpheme, gloss, matches_found,
             lexical_items, deleted_lexical_items, whole_db) = args
        except ValueError:
            raise TypeError(
                'get_perfect_matches() missing 9 required'
                ' positional arguments: \'form\', \'word_index\','
                ' \'morpheme_index\', \'morpheme\', \'gloss\','
                ' \'matches_found\', \'lexical_items\','
                ' \'deleted_lexical_items\' and \'whole_db\'')
        if (morpheme, gloss) in matches_found:
            return matches_found[(morpheme, gloss)], matches_found
        if whole_db:
            result = [f for f in whole_db if f.morpheme_break == morpheme and
                      f.morpheme_gloss == gloss]
        elif lexical_items or deleted_lexical_items:
            extant_morpheme_break_ids = json.loads(form.morpheme_break_ids)
            extant_morpheme_gloss_ids = json.loads(form.morpheme_gloss_ids)
            # Extract extant perfect matches as quadruples: (id, mb, mg, sc)
            extant_perfect_matches_originally = [
                (x[0][0], x[1][1], x[0][1], x[0][2]) for x in zip(
                    extant_morpheme_break_ids[word_index][morpheme_index],
                    extant_morpheme_gloss_ids[word_index][morpheme_index])
                if x[0][0] == x[1][0]
            ]
            # Make extant matches look like form objects and remove those that
            # may have been deleted or updated
            extant_perfect_matches = [
                get_fake_form(m) for m in extant_perfect_matches_originally
                if m[0] not in [f.id for f in lexical_items +
                                deleted_lexical_items]
            ]
            perfect_matches_in_lexical_items = [
                f for f in lexical_items if f.morpheme_break == morpheme and
                f.morpheme_gloss == gloss]
            perfect_matches_now = sorted(
                extant_perfect_matches + perfect_matches_in_lexical_items,
                key=lambda f: f.id)
            # If perfect matches have been emptied by us, we return a tuple so
            # that get_partial_matches knows to query the database for this
            # morpheme only
            if (perfect_matches_now == [] and
                    extant_perfect_matches_originally != []):
                return (morpheme, gloss), matches_found
            result = perfect_matches_now
        else:
            result = self.request.dbsession.query(Form)\
                .filter(Form.morpheme_break==morpheme)\
                .filter(Form.morpheme_gloss==gloss).order_by(asc(Form.id)).all()
        matches_found[(morpheme, gloss)] = result
        return result, matches_found

    def get_partial_matches(self, form, word_index, morpheme_index,
                            matches_found, **kwargs):
        """Return the list of forms that partially match a given morpheme.

        If ``kwargs['morpheme']`` is present, return all forms ``f`` such that
        ``f.morpheme_break==kwargs['morpheme']``; else if ``kwargs['gloss']`` is
        present, return all forms such that
        ``f.morpheme_gloss==kwargs['gloss']``.

        If ``kwargs['lexical_items']`` or ``kwargs['deleted_lexical_items']``
        are present, then that list of forms will be used to build the list of
        partial matches and database will, usually, not be queried, cf.
        :func:`get_perfect_matches` above.  The only case where the db will be
        queried (when ``lexical_items`` or ``deleted_lexical_items`` are
        supplied) is when ``kwargs['morpheme']`` or ``kwargs['gloss']`` is in
        ``force_query``.  When this is so, it indicates that
        :func:`get_perfect_matches` is communicating that the supplied lexical
        info resulted in all perfect matches for the given morpheme being
        emptied and that, therefore, the database must be searched for partial
        matches.

        :param form: the form model whose morphological analysis-related
            attributes are being generated.
        :param int word_index: the index of the word containing the morpheme
            being analyzed.
        :param int morpheme_index: the index, within the word, of the morpheme
            being analyzed.
        :param dict matches_found: keys are morpheme 2-tuples and values are
            lists of matches.
        :param str kwargs['morpheme']: the phonemic representation of the
            morpheme, if present.
        :param str kwargs['gloss']: the gloss of the morpheme, if present.
        :param list kwargs['lexical_items']: forms constituting the exclusive
            pool of potential matches.
        :param list kwargs['deleted_lexical_items']: forms that must be deleted
            from the matches.
        :param iterable kwargs['force_query']: a 2-tuple representing a
            morpheme or a list of perfect matches.
        :returns: an ordered pair (tuple), where the first element is the list
            of partial matches found and the second is the (potentially updated)
            ``matches_found`` dictionary.
        """
        lexical_items = kwargs.get('lexical_items')
        deleted_lexical_items = kwargs.get('deleted_lexical_items')
        whole_db = kwargs.get('whole_db')
        force_query = kwargs.get('force_query')   # The output of
                                                  # get_perfect_matches: []
                                                  # or (morpheme, gloss)
        morpheme = kwargs.get('morpheme')
        gloss = kwargs.get('gloss')
        attribute = morpheme and 'morpheme_break' or 'morpheme_gloss'
        value = morpheme or gloss
        if (morpheme, gloss) in matches_found:
            return matches_found[(morpheme, gloss)], matches_found
        if whole_db:
            result = [f for f in whole_db if getattr(f, attribute) == value]
        elif lexical_items or deleted_lexical_items:
            if value in force_query:
                result = self.request.dbsession.query(Form)\
                    .filter(getattr(Form, attribute)==value)\
                    .order_by(asc(Form.id)).all()
            else:
                extant_analyses = json.loads(
                    getattr(form, attribute + '_ids')
                )[word_index][morpheme_index]
                # Extract extant partial matches as quadruples of the form (id,
                # mb, mg, sc) where one of mb or mg will be None.
                extant_partial_matches = [
                    (x[0], None, x[1], x[2]) if morpheme else
                    (x[0], x[1], None, x[2]) for x in extant_analyses]
                # Make extant matches look like form objects and remove those
                # that may have been deleted or updated
                extant_partial_matches = [
                    get_fake_form(m) for m in extant_partial_matches
                    if m[0] not in [f.id for f in lexical_items +
                                    deleted_lexical_items]]
                partial_matches_in_lexical_items = [
                    f for f in lexical_items if getattr(f, attribute) == value]
                result = sorted(
                    extant_partial_matches + partial_matches_in_lexical_items,
                    key=lambda f: f.id)
        else:
            result = self.request.dbsession.query(Form)\
                .filter(getattr(Form, attribute)==value)\
                .order_by(asc(Form.id)).all()
        matches_found[(morpheme, gloss)] = result
        return result, matches_found

    def compile_morphemic_analysis(self, form, morpheme_delimiters=None,
                                   **kwargs):
        """An error-handling wrapper arround :func:`_compile_morphemic_analysis`.

        Catch any error, log it and return a default 4-tuple.

        :param form: the form model for which the morphological values are to be
            generated.
        :param list valid_delimiters: morpheme delimiters as strings.
        :param dict kwargs: arguments that can affect the degree to which the
            database is queried.
        :returns: the output of :func:`_compile_morphemic_analysis` or, if an
            error occurs, a 4-tuple of ``None`` objects.
        """
        try:
            return self._compile_morphemic_analysis(form, morpheme_delimiters,
                                                    **kwargs)
        except Exception as error:  # fix too general exception
            LOGGER.debug('compile_morphemic_analysis raised an error (%s) on'
                         ' "%s"/"%s".', error, form.morpheme_break,
                         form.morpheme_gloss)
            return None, None, None, None, {}

    def _compile_morphemic_analysis(self, form, morpheme_delimiters=None,
                                    **kwargs):
        """Generate values fo the morphological analysis-related attributes of a
        form model.

        :param form: the form model for which the morphological values are to be
            generated.
        :param list valid_delimiters: morpheme delimiters as strings.
        :param dict kwargs: arguments that can affect the degree to which the
            database is queried.
        :returns: a 4-tuple containing the generated values or all four ``None``
            objects if no values can be generated.

        Generate values for the ``morpheme_break_ids``, ``morpheme_gloss_ids``,
        ``syntactic_category_string`` and ``break_gloss_category`` attributes
        of the input form.

        For each morpheme detected in the ``form``, search the database for
        forms whose ``morpheme_break`` value matches the morpheme's phonemic
        form and whose ``morpheme_gloss`` value matches the morpheme's gloss.
        If a perfect match is not found, search the database for forms matching
        just the phonemic form or just the gloss.

        Matching forms are represented as triples where the first element is the
        ``id`` value of the match, the second is its ``morpheme_break`` or
        ``morpheme_gloss`` value and the third is its
        ``syntactic_category.name`` value.  To illustrate, consider a form with
        ``morpheme_break`` value 'chien-s' and ``morpheme_gloss`` value
        'dog-PL' and assume the lexical entries 'chien/dog/N/33',
        's/PL/Agr/103' and 's/PL/Num/111' (where, for */a/b/c/d*, *a* is the
        ``morpheme_break`` value, *b* is the ``morpheme_gloss`` value, *c* is
        the ``syntactic_category.name`` value and *d* is the ``id`` value.
        Running :func:`compile_morphemic_analysis` on the target form returns
        the following 4-tuple ``q``::

            (
                json.dumps([[[[33, 'dog', 'N']], [[111, 'PL', 'Num'], [103, 'PL', 'Agr']]]]),
                json.dumps([[[[33, 'chien', 'N']], [[111, 's', 'Num'], [103, 's', 'Agr']]]]),
                'N-Num',
                'chien|dog|N-s|PL|Num'
            )

        where ``q[0]`` is the ``morpheme_break_ids`` value, ``q[1]`` is the
        ``morpheme_gloss_ids`` value, ``q[2]`` is ``syntactic_category_string``
        value and ``q[3]`` is ``break_gloss_category`` value.

        If ``kwargs`` contains a 'lexical_items' or a 'deleted_lexical_items'
        key, then :func:`compile_morphemic_analysis` will *update* (i.e., not
        re-create) the 4 relevant values of the form using only the items in
        ``kwargs['lexical_items']`` or ``kwargs['deleted_lexical_items']``.
        This facilitates lexical change percolation without massively redundant
        database queries.
        """
        # The default delimiter for the break_gloss_category field
        bgc_delimiter = kwargs.get('bgc_delimiter', DEFAULT_DELIMITER)
        lexical_items = kwargs.get('lexical_items', [])
        deleted_lexical_items = kwargs.get('deleted_lexical_items', [])
        # temporary store -- eliminates redundant queries & processing -- updated
        # as a byproduct of get_perfect_matches and get_partial_matches
        matches_found = kwargs.get('cache', {})
        whole_db = kwargs.get('whole_db')
        morpheme_break_ids = []
        morpheme_gloss_ids = []
        syntactic_category_string = []
        morpheme_delimiters = morpheme_delimiters or self.db.get_morpheme_delimiters()
        if [md for md in morpheme_delimiters if md]:
            morpheme_splitter = '[%s]' % ''.join(
                [h.esc_RE_meta_chars(d) for d in morpheme_delimiters])
        else:
            morpheme_splitter = ''
        morpheme_break = form.morpheme_break
        morpheme_gloss = form.morpheme_gloss
        mb_words = morpheme_break.split()     # e.g., 'le-s chien-s'
        mg_words = morpheme_gloss.split()     # e.g., 'the-PL dog-PL'
        sc_words = morpheme_break.split()[:]  # e.g., 'le-s chien-s' (placeholder)
        if morphemic_analysis_is_consistent(
                morpheme_delimiters=morpheme_delimiters,
                morpheme_break=morpheme_break, morpheme_gloss=morpheme_gloss,
                mb_words=mb_words, mg_words=mg_words,
                morpheme_splitter=morpheme_splitter):
            for i, mb_word in enumerate(mb_words):
                mb_word_analysis = []
                mg_word_analysis = []
                mg_word = mg_words[i]     # e.g., 'dog-PL'
                sc_word = sc_words[i]     # e.g., 'chien-s'
                # splits on delimiters while retaining them
                morpheme_and_delimiter_splitter = '(%s)' % morpheme_splitter
                # e.g., ['chien', 's']
                mb_word_morphemes_list = _split(
                    morpheme_and_delimiter_splitter, mb_word)[::2]
                # e.g., ['dog', 'PL']
                mg_word_morphemes_list = _split(
                    morpheme_and_delimiter_splitter, mg_word)[::2]
                # e.g., ['chien', '-', 's']
                sc_word_analysis = _split(
                    morpheme_and_delimiter_splitter, sc_word)
                for j, morpheme in enumerate(mb_word_morphemes_list):
                    gloss = mg_word_morphemes_list[j]
                    perfect_matches, matches_found = self.get_perfect_matches(
                        form, i, j, morpheme, gloss, matches_found,
                        lexical_items, deleted_lexical_items, whole_db)
                    if perfect_matches and isinstance(perfect_matches, list):
                        mb_word_analysis.append(
                            [(f.id, f.morpheme_gloss,
                              getattr(f.syntactic_category, 'name', None))
                             for f in perfect_matches])
                        mg_word_analysis.append(
                            [(f.id, f.morpheme_break,
                              getattr(f.syntactic_category, 'name', None))
                             for f in perfect_matches])
                        sc_word_analysis[j * 2] = getattr(
                            perfect_matches[0].syntactic_category, 'name',
                            UNKNOWN_CATEGORY)
                    else:
                        morpheme_matches, matches_found = \
                            self.get_partial_matches(
                                form, i, j, matches_found, morpheme=morpheme,
                                force_query=perfect_matches,
                                lexical_items=lexical_items,
                                deleted_lexical_items=deleted_lexical_items,
                                whole_db=whole_db)
                        if morpheme_matches:
                            mb_word_analysis.append(
                                [(f.id, f.morpheme_gloss,
                                  getattr(f.syntactic_category, 'name', None))
                                 for f in morpheme_matches])
                        else:
                            mb_word_analysis.append([])
                        gloss_matches, matches_found = self.get_partial_matches(
                            form, i, j, matches_found, gloss=gloss,
                            force_query=perfect_matches,
                            lexical_items=lexical_items,
                            deleted_lexical_items=deleted_lexical_items,
                            whole_db=whole_db)
                        if gloss_matches:
                            mg_word_analysis.append(
                                [(f.id, f.morpheme_break,
                                  getattr(f.syntactic_category, 'name', None))
                                 for f in gloss_matches])
                        else:
                            mg_word_analysis.append([])
                        sc_word_analysis[j * 2] = \
                            get_category_from_partial_match(morpheme_matches,
                                                            gloss_matches)
                morpheme_break_ids.append(mb_word_analysis)
                morpheme_gloss_ids.append(mg_word_analysis)
                syntactic_category_string.append(''.join(sc_word_analysis))
            syntactic_category_string = ' '.join(syntactic_category_string)
            break_gloss_category = get_break_gloss_category(
                morpheme_delimiters, morpheme_break, morpheme_gloss,
                syntactic_category_string, bgc_delimiter)
        else:
            morpheme_break_ids = morpheme_gloss_ids = \
            syntactic_category_string = break_gloss_category = None
        return (
            json.dumps(morpheme_break_ids),
            json.dumps(morpheme_gloss_ids),
            syntactic_category_string,
            break_gloss_category, matches_found
        )

    def update_forms_containing_this_form_as_morpheme(
            self, form, change='create', previous_version=None):
        """Update the morphological analysis-related attributes of every form
        containing the input form as morpheme.

        Update the values of the ``morpheme_break_ids``, ``morpheme_gloss_ids``,
        ``syntactic_category_string``, and ``break_gloss_category`` attributes
        of each form that contains the input form in its morphological
        analysis, i.e., each form whose ``morpheme_break`` value contains the
        input form's ``morpheme_break`` value as a morpheme or whose
        ``morpheme_gloss`` value contains the input form's ``morpheme_gloss``
        line as a gloss.  If the input form is not lexical (i.e., if it
        contains the space character or a morpheme delimiter), then no updates
        occur.

        :param form: a form model object.
        :param str change: indicates whether the form has just been deleted or
            created/updated.
        :param dict previous_version: a representation of the form prior to
            update.
        :returns: ``None``
        """
        if self.is_lexical(form):
            # Here we construct the query to get all forms that may have been
            # affected by the change to the lexical item (i.e., form).
            morpheme_delimiters = self.db.get_morpheme_delimiters()
            escaped_morpheme_delimiters = [
                h.esc_RE_meta_chars(d) for d in morpheme_delimiters]
            if (    len(escaped_morpheme_delimiters) == 1 and not
                    escaped_morpheme_delimiters[0]):
                start_patt = '(%s)' % '|'.join([' ', '^'])
                end_patt = '(%s)' % '|'.join([' ', '$'])
            else:
                start_patt = '(%s)' % '|'.join(
                    escaped_morpheme_delimiters + [' ', '^'])
                end_patt = '(%s)' % '|'.join(
                    escaped_morpheme_delimiters + [' ', '$'])
            morpheme_patt = '%s%s%s' % (
                start_patt, form.morpheme_break, end_patt)
            gloss_patt = '%s%s%s' % (start_patt, form.morpheme_gloss, end_patt)
            disjunctive_conditions = [
                Form.morpheme_break.op('regexp')(morpheme_patt),
                Form.morpheme_gloss.op('regexp')(gloss_patt)]
            matches_query = self.request.dbsession.query(Form).options(
                subqueryload(Form.syntactic_category))
            # Updates entail a wider range of possibly affected forms
            if previous_version and self.is_lexical(previous_version):
                if previous_version['morpheme_break'] != form.morpheme_break:
                    morpheme_patt_pv = '%s%s%s' % (
                        start_patt, previous_version['morpheme_break'],
                        end_patt)
                    disjunctive_conditions.append(
                        Form.morpheme_break.op('regexp')(morpheme_patt_pv))
                if previous_version['morpheme_gloss'] != form.morpheme_gloss:
                    gloss_patt_pv = '%s%s%s' % (
                        start_patt, previous_version['morpheme_gloss'],
                        end_patt)
                    disjunctive_conditions.append(
                        Form.morpheme_gloss.op('regexp')(gloss_patt_pv))
            matches_query = matches_query.filter(or_(*disjunctive_conditions))
            #matches = [f for f in matches_query.all() if f.id != form.id]
            matches = matches_query.all()
            if change == 'delete':
                self.update_morpheme_references_of_forms(
                    matches, morpheme_delimiters, deleted_lexical_items=[form])
            else:
                self.update_morpheme_references_of_forms(
                    matches, morpheme_delimiters, lexical_items=[form])

    def form_is_foreign_word(self, form_model):
        foreign_word_tag = self.db.get_foreign_word_tag()
        if foreign_word_tag in form_model.tags:
            return True
        return False

    def is_lexical(self, form):
        """Return True if the input form is lexical, i.e, if neither its
        morpheme break nor its morpheme gloss lines contain the space character
        or any of the morpheme delimiters.  Note: designed to work on dict
        representations of forms also.
        """
        delimiters = self.db.get_morpheme_delimiters() + [' ']
        try:
            return (bool(form.morpheme_break) and
                    bool(form.morpheme_gloss) and not (
                        set(delimiters) & set(form.morpheme_break) and
                        set(delimiters) & set(form.morpheme_gloss)))
        except AttributeError:
            return (bool(form['morpheme_break']) and
                    bool(form['morpheme_gloss']) and not (
                        set(delimiters) & set(form['morpheme_break']) and
                        set(delimiters) & set(form['morpheme_gloss'])))
        except:
            return False


def update_has_changed_the_analysis(form, form_dict):
    """Return ``True`` if the update from form_dict to form has changed the
    morphological analysis of the form.
    """
    try:
        old_syntactic_category_name = form_dict['syntactic_category']\
            .get('name')
    except AttributeError:
        old_syntactic_category_name = None
    return (
        form.morpheme_break != form_dict['morpheme_break'] or
        form.morpheme_gloss != form_dict['morpheme_gloss'] or
        form.break_gloss_category != form_dict['break_gloss_category'] or
        getattr(form.syntactic_category, 'name', None) !=
        old_syntactic_category_name
    )


def join(bgc, morpheme_delimiters, bgc_delimiter):
    """Convert a break-gloss-category tuple into a delimited string.

    Join the break-gloss-category 3-tuple ``bgc`` using the delimiter
    string.  If ``bgc`` contains only morpheme/word delimiters, then the
    first such delimiter is returned.

    :param bgc: the morpheme as phonemic form, gloss and category.
    :type bgc: list
    :param list morpheme_delimiters: morpheme delimiters as strings.
    :type morpheme_delimiters: list
    :param bgc_delimiter: delimiter used to join the elements of the morpheme.
    :type bgc_delimiter: str
    :returns: a string representation of the morpheme.

    Examples::

        >>> join(['le', 'the', 'Det'], ['-', '=', ' '], '|')
        'le|the|Det'

        >>> join(['-', '-', '-'], ['-', '=', ' '], '|')
        '-'

        >>> join(['=', '-', '='], ['-', '=', ' '], '|')
        '='
    """
    if (bgc[0] in morpheme_delimiters and
            bgc[1] in morpheme_delimiters and
            bgc[2] in morpheme_delimiters):
        return bgc[0]
    return bgc_delimiter.join(bgc)


def _split(pattern, string):
    """Split string ``string`` into a list of strings using regex ``pattern``.
    * In Python 3.5, ``re.split`` will raise ``ValueError`` if ``pattern`` is
      an empty string.
    * In Python 3.7, ``re.split`` will return some crazy shit if pattern is an
      empty string (sigh.)
    """
    if pattern in ('', '()'):
        return [string]
    try:
        return re.split(pattern, string)
    except ValueError:
        return [string]


def morphemic_analysis_is_consistent(**kwargs):
    """Determine whether a morphemic analysis is consistent.

    :param dict kwargs: contains the morphological data in various
        pre-processed states.
    :returns: ``True`` if the morphemic analysis is consistent;
        ``False`` otherwise.

    "Consistent" means that the ``morpheme_break`` and
    ``morpheme_gloss`` values of ``kargs`` are not empty, there are
    equal numbers of morpheme break and morpheme gloss "words" and each
    morpheme break word has the same number of morphemes as its
    morpheme gloss counterpart.
    """
    try:
        return (
            kwargs['morpheme_break'] != '' and
            kwargs['morpheme_gloss'] != '' and
            len(kwargs['mb_words']) == len(kwargs['mg_words']) and
            [len(_split(kwargs['morpheme_splitter'], mbw)) for mbw in
             kwargs['mb_words']] ==
            [len(_split(kwargs['morpheme_splitter'], mgw)) for mgw in
             kwargs['mg_words']])
    except Exception as error:
        LOGGER.debug('error in morphemic_analysis_is_consistent')
        LOGGER.debug(error)
        LOGGER.debug("kwargs['morpheme_splitter'] %s",
                     kwargs['morpheme_splitter'])
        raise


def get_category_from_partial_match(morpheme_matches, gloss_matches):
    """Return a syntactic category name for a partially matched
    morpheme.

    :param list morpheme_matches: forms matching the morpheme's
        transcription.
    :param list gloss_matches: forms matching the morpheme's gloss.
    :returns: the category name of the first morpheme match, else that
        of the first gloss match, else the value of
        ``UNKNOWN_CATEGORY``, i.e,. ``'?'``.
    """
    morpheme_syncats = [getattr(m.syntactic_category, 'name', None) for m in
                        morpheme_matches]
    gloss_syncats = [getattr(g.syntactic_category, 'name', None) for g in
                     gloss_matches]
    categories = morpheme_syncats + gloss_syncats + [UNKNOWN_CATEGORY]
    return list(filter(None, categories))[0]


def get_break_gloss_category(morpheme_delimiters, morpheme_break,
                             morpheme_gloss, syntactic_category_string,
                             bgc_delimiter):
    """Return a ``break_gloss_category`` string, e.g.,
    'le|the|Det-s|PL|Num chien|dog|N-s|PL|Num'.
    """
    try:
        delimiters = [' '] + morpheme_delimiters
        splitter = '([%s])' % ''.join([h.esc_RE_meta_chars(d) for d in
                                       delimiters])
        mb_split = filter(None, _split(splitter, morpheme_break))
        mg_split = filter(None, _split(splitter, morpheme_gloss))
        sc_split = filter(
            None, _split(splitter, syntactic_category_string))
        break_gloss_category = zip(mb_split, mg_split, sc_split)
        return ''.join([join(bgc, delimiters, bgc_delimiter) for bgc in
                        break_gloss_category])
    except TypeError:
        return None


class FakeForm(object):

    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            setattr(self, key, val)


class FakeSyntacticCategory(object):

    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            setattr(self, key, val)


def get_fake_form(quadruple):
    """Return ``quadruple`` as a form-like object.

    :param tuple quadruple: ``(id, mb, mg, sc)``.
    :returns: a :class:`FakeForm` instance.
    """
    fake_syntactic_category = FakeSyntacticCategory(name=quadruple[3])
    fake_form = FakeForm(
        id=quadruple[0],
        morpheme_break=quadruple[1],
        morpheme_gloss=quadruple[2],
        syntactic_category=fake_syntactic_category
    )
    return fake_form
