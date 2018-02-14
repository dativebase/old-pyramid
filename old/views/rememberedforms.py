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

"""Contains the :class:`Rememberedforms` view and its auxiliary functions.

.. module:: rememberedforms
   :synopsis: Contains the remembered forms view and its auxiliary functions.

"""

import logging
import json
from formencode.validators import Invalid
from sqlalchemy.orm import subqueryload

from old.lib.constants import (
    JSONDecodeErrorResponse
)
import old.lib.helpers as h
from old.models import (
    Form,
    User
)
from old.lib.schemata import FormIdsSchemaNullable
from old.lib.SQLAQueryBuilder import OLDSearchParseError
from old.lib.dbutils import (
    add_pagination,
    get_eagerloader
)
from old.views.resources import (
    Resources,
    SchemaState
)

LOGGER = logging.getLogger(__name__)


class Rememberedforms(Resources):
    """Generate responses to requests on remembered forms resources.

    REST Controller styled on the Atom Publishing Protocol.

    .. note::

        Remembered forms is a pseudo-REST-ful resource.  Remembered forms are
        stored in the ``userform`` many-to-many table (cf. ``model/user.py``)
        which defines the contents of a user's ``remembered_forms`` attribute
        (as well as the contents of a form's ``memorizers`` attribute). A user's
        remembered forms are not affected by requests to the user resource.
        Instead, the remembered forms resource handles modification, retrieval
        and search of a user's remembered forms.

        Overview of the interface:

        * ``GET /rememberedforms/id``
        * ``UPDATE /rememberedforms/id``
        * ``SEARCH /rememberedforms/id``
    """

    def __init__(self, request):
        self.model_name = 'Form'
        self.model_cls = Form
        super().__init__(request)

    def show(self):
        """Return a user's remembered forms.

        :URL: ``GET /rememberedforms/id`` with optional query string parameters
            for ordering and pagination.
        :param str id: the ``id`` value of a user model.
        :returns: a list form models.

        .. note::

            Any authenticated user is authorized to access this resource.
            Restricted forms are filtered from the array on a per-user basis.
        """
        id_ = self.request.matchdict['id']
        LOGGER.info('Returning the forms remembered by user %d.', id_)
        user = self.request.dbsession.query(User).get(int(id_))
        if not user:
            self.request.response.status_int = 404
            msg = 'There is no user with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        query = get_eagerloader('Form')(
            self.request.dbsession.query(Form))\
                .filter(Form.memorizers.contains(user))
        get_params = dict(self.request.GET)
        try:
            query = self.add_order_by(query, get_params)
            query = self._filter_restricted_models(query)
            LOGGER.info('Returned the forms remembered by user %d.', user.id)
            return add_pagination(query, get_params)
        except Invalid as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}

    def update(self):
        """Update a user's remembered forms and return them.

        - URL: ``PUT /rememberedforms/id``
        - Request body: JSON object of the form ``{"forms": [...]}`` where the
          array contains the form ``id`` values that will constitute the
          user's ``remembered_forms`` collection after update.

        :param str id: the ``id`` value of the user model whose
         ``remembered_forms`` attribute is to be updated.
        :returns: the list of remembered forms of the user.

        .. note:: Administrators can update any user's remembered forms;
           non-administrators can only update their own.
        """
        id_ = self.request.matchdict['id']
        LOGGER.info('Attempting to update the forms remembered by user %d.',
                    id_)
        user = self.request.dbsession.query(
            User).options(subqueryload(User.remembered_forms)).get(id_)
        schema = FormIdsSchemaNullable
        if not user:
            self.request.response.status_int = 404
            msg = 'There is no user with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            values = json.loads(
                self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            LOGGER.warning(JSONDecodeErrorResponse)
            return JSONDecodeErrorResponse
        state = SchemaState(
            full_dict=values,
            db=self.db,
            id=id_)
        try:
            data = schema.to_python(values, state)
        except Invalid as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}
        forms = [f for f in data['forms'] if f]
        unrestricted_users = self.db.get_unrestricted_users()
        unrestricted_forms = [
            f for f in forms
            if self.logged_in_user.is_authorized_to_access_model(
                f, unrestricted_users)]
        if set(user.remembered_forms) != set(unrestricted_forms):
            user.remembered_forms = unrestricted_forms
            user.datetime_modified = h.now()
            LOGGER.info('Updated the forms remembered by user %d.', id_)
            return user.remembered_forms
        self.request.response.status_int = 400
        msg = ('The update request failed because the submitted data were not'
               ' new.')
        LOGGER.warning(msg)
        return {'error': msg}

    def search(self):
        """Return the remembered forms of a user that match the input JSON
        query.
        :URL: ``SEARCH /rememberedforms/id`` (or ``POST /rememberedforms/id/search``).
        :param str id: the ``id`` value of the user whose remembered forms are searched.
        :request body: A JSON object of the form::

                {"query": {"filter": [ ... ], "order_by": [ ... ]},
                 "paginator": { ... }}

            where the ``order_by`` and ``paginator`` attributes are optional.
        """
        id_ = self.request.matchdict['id']
        LOGGER.info('Attempting to search over the forms remembered by user'
                    ' %d.', id_)
        user = self.request.dbsession.query(User).get(int(id_))
        if not user:
            self.request.response.status_int = 404
            msg = 'There is no user with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            python_search_params  = json.loads(
                self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            LOGGER.warning(JSONDecodeErrorResponse)
            return JSONDecodeErrorResponse
        query = get_eagerloader('Form')(
            self.query_builder.get_SQLA_query(python_search_params.get('query')))
        query = query.filter(Form.memorizers.contains(user))
        query = self._filter_restricted_models(query)
        try:
            ret = add_pagination(query, python_search_params.get('paginator'))
            LOGGER.info('Performed search over the forms remembered by user'
                        ' %d.', id_)
            return ret
        except (OLDSearchParseError, Invalid) as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}
        except Exception:
            self.request.response.status_int = 400
            msg = ('The specified search parameters generated an invalid'
                   ' database query')
            LOGGER.warning(msg)
            return {'error': msg}

    def _get_create_data(self, data):
        pass

    def _get_update_data(self, user_data):
        pass

    def _get_user_data(self, data):
        pass
