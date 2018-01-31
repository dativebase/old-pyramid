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

"""Contains the :class:`Formsearches` view.

.. module:: formsearches
   :synopsis: Contains the form searches view.
"""

import datetime
import logging

from old.lib.constants import UNAUTHORIZED_MSG
from old.views.resources import (
    Resources,
    SchemaState
)
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Formsearches(Resources):
    """Generate responses to requests on form search resources.

    REST Controller styled on the Atom Publishing Protocol.
    """

    def __init__(self, request):
        self.model_name = 'FormSearch'
        self.hmn_member_name = 'form search'
        super().__init__(request)

    def new(self):
        """GET /formsearches/new: Return the data necessary to create a new OLD
        form search.
        Note: different from (overrides) standard Resources::new: returns the
        query builder's search parameters.
        """
        LOGGER.info('Returning the data necessary to create a new OLD form'
                    ' search.')
        return {'search_parameters': self.query_builder.get_search_parameters()}

    def edit(self):
        """Also an override of Resources::edit."""
        resource_model, id_ = self._model_from_id(eager=True)
        if not resource_model:
            self.request.response.status_int = 404
            msg = 'There is no {} with id {}'.format(self.hmn_member_name, id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if self._model_access_unauth(resource_model) is not False:
            LOGGER.warning('User not authorized to access edit action on model')
            self.request.response.status_int = 403
            return UNAUTHORIZED_MSG
        data = {'search_parameters': self.query_builder.get_search_parameters()}
        LOGGER.info('Returned the data necessary to edit OLD form search %d.',
                    resource_model.id)
        return {'data': data, 'form_search': resource_model}

    def _get_create_state(self, values):
        """Return a SchemaState instance for validation of the form search
        during a create request.
        """
        return SchemaState(
            full_dict=values,
            db=self.db,
            logged_in_user=self.logged_in_user,
            settings=self.request.registry.settings)

    def _get_user_data(self, data):
        """User-provided data for creating a form search."""
        return {
            'name': h.normalize(data['name']),
            'search': data['search'],  # Note that this is purposefully not
                                       # normalized (reconsider this? ...)
            'description': h.normalize(data['description'])
        }

    def _get_create_data(self, data):
        """Data needed to create a new form search."""
        create_data = self._get_update_data(self._get_user_data(data))
        create_data['enterer'] = self.logged_in_user
        return create_data

    def _get_update_data(self, user_data):
        """Data needed to update an existing form search."""
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow(),
        })
        return user_data
