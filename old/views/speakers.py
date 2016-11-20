"""Speakers View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Speakers(Resources):
    """Generate responses to requests on speaker resources."""

    def _get_new_edit_collections(self):
        return ('markup_languages',)

    def _get_user_data(self, data):
        result = {
            'first_name': h.normalize(data['first_name']),
            'last_name': h.normalize(data['last_name']),
            'dialect': h.normalize(data['dialect']),
            'page_content': h.normalize(data['page_content']),
            'markup_language': h.normalize(data['markup_language'])
        }
        result['html'] = h.get_HTML_from_contents(
            result['page_content'], result['markup_language'])
        return result

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data
