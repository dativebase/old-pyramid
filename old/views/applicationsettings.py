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

"""Contains the :class:`Applicationsettings` view and its auxiliary functions.

.. module:: applicationsettings
   :synopsis: Contains the application settings view and its auxiliary
    functions.
"""

import logging
import datetime

from sqlalchemy.sql import asc

import old.lib.helpers as h
from old.views.resources import Resources


LOGGER = logging.getLogger(__name__)


class Applicationsettings(Resources):
    """Generate responses to requests on application settings resources.
    REST Controller styled on the Atom Publishing Protocol.
    The most recently created application settings resource is considered to be
    the *active* one.
    .. note::
       The ``h.jsonify`` decorator converts the return value of the methods to
       JSON.
    .. note::
       Only administrators are authorized to create, update or delete
       application settings resources.
    """

    def __init__(self, request):
        self.model_name = 'ApplicationSettings'
        self.member_name = 'application_settings'
        self.hmn_member_name = 'application settings'
        super().__init__(request)

    def index(self):
        """Get all application settings resources.
        :URL: ``GET /applicationsettings``
        :returns: a list of all application settings resources.
        Note: no ordering or pagination possible on this resource fetch. Why?
        """
        LOGGER.info('Reading all %s', self.hmn_member_name)
        return self._eagerload_model(
            self.request.dbsession.query(self.model_cls)).order_by(
                asc(self.model_cls.id)).all()

    def _get_new_edit_collections(self):
        """Return a sequence of strings representing the names of the
        collections (typically resource collections) that are required in order
        to create a new, or edit an existing, resource of the given type. For
        many resources, an empty typle is fine, but for others an override
        returning a tuple of collection names from the keys of
        ``self.resource_collections`` will be required.
        """
        return (
            'users',
            'orthographies',
            'languages'
            )

    def _distinct(self, attr, new_val, existing_val):
        if attr in ('unrestricted_users',):
            if set(new_val) == set(existing_val):
                return False
            return True
        else:
            return new_val != existing_val

    def _get_user_data(self, data):
        return {
            'object_language_name': data['object_language_name'],
            'object_language_id': data['object_language_id'],
            'metalanguage_name': data['metalanguage_name'],
            'metalanguage_id': data['metalanguage_id'],
            'metalanguage_inventory': h.normalize(
                h.remove_all_white_space(data['metalanguage_inventory'])),
            'orthographic_validation': data['orthographic_validation'],
            'narrow_phonetic_inventory': h.normalize(
                h.remove_all_white_space(data['narrow_phonetic_inventory'])),
            'narrow_phonetic_validation': data['narrow_phonetic_validation'],
            'broad_phonetic_inventory': h.normalize(
                h.remove_all_white_space(data['broad_phonetic_inventory'])),
            'broad_phonetic_validation': data['broad_phonetic_validation'],
            'morpheme_break_is_orthographic': data[
                'morpheme_break_is_orthographic'],
            'morpheme_break_validation': data['morpheme_break_validation'],
            'phonemic_inventory': h.normalize(
                h.remove_all_white_space(data['phonemic_inventory'])),
            'morpheme_delimiters': h.normalize(
                data['morpheme_delimiters']),
            'punctuation': h.normalize(
                h.remove_all_white_space(data['punctuation'])),
            'grammaticalities': h.normalize(
                h.remove_all_white_space(data['grammaticalities'])),
            # Many-to-One
            'storage_orthography': data['storage_orthography'],
            'input_orthography': data['input_orthography'],
            'output_orthography': data['output_orthography'],
            # Many-to-Many Data: unrestricted_users
            'unrestricted_users': [u for u in data['unrestricted_users'] if u]
        }

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data
