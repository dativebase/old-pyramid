"""Pages View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Pages(Resources):
    """Generate responses to requests on page resources."""

    def _get_new_edit_collections(self):
        return ('markup_languages',)

    def _get_user_data(self, data):
        result = {
            'name': h.normalize(data['name']),
            'heading': h.normalize(data['heading']),
            'markup_language': data['markup_language'],
            'content': h.normalize(data['content'])
        }
        result['html'] = h.get_HTML_from_contents(
            result['content'], result['markup_language'])
        return result

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data
