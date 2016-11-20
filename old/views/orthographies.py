"""Orthographies View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Orthographies(Resources):

    def _update_unauth(self, resource_model):
        """Update (and delete) on an orthography is permitted only if that
        orthography is not referenced in the current application settings.
        """
        if self.logged_in_user == 'administrator':
            return False
        app_set = self.db.current_app_set
        if resource_model in (
                app_set.storage_orthography,
                app_set.input_orthography,
                app_set.output_orthography):
            return True
        return False

    def _delete_unauth(self, resource_model):
        return self._update_unauth(resource_model)

    def _update_unauth_msg_obj(self):
        return {
            'error': 'Only administrators are permitted to update orthographies'
                     ' that are used in the active application settings.'
        }

    def _delete_unauth_msg_obj(self):
        return {
            'error': 'Only administrators are permitted to delete orthographies'
                     ' that are used in the active application settings.'
        }

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'orthography': h.normalize(data['orthography']),
            'lowercase': data['lowercase'],
            'initial_glottal_stops': data['initial_glottal_stops']
        }

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data
