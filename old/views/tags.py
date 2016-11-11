"""Tags View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Tags(Resources):
    """Generate responses to requests on tag resources."""

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
        }

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data

    def _delete_impossible(self, tag_model):
        """Restricted and foreign word tags cannot be deleted."""
        if tag_model.name in ('restricted', 'foreign word'):
            return 'The restricted and foreign word tags cannot be deleted.'
        return False
