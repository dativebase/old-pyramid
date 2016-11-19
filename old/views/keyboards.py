"""Keyboards View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Keyboards(Resources):
    """Generate responses to requests on keyboard resources."""

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
            'keyboard': h.normalize(data['keyboard'])
        }

    def _get_create_data(self, data):
        create_data = self._get_update_data(self._get_user_data(data))
        create_data['enterer'] = create_data['modifier']
        create_data['datetime_entered'] = create_data['datetime_modified']
        return create_data

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow(),
            'modifier': self.logged_in_user
        })
        return user_data
