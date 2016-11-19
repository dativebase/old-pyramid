import datetime

import old.lib.helpers as h
from old.views.resources import Resources


class Elicitationmethods(Resources):

    def __init__(self, request):
        self.model_name = 'ElicitationMethod'
        self.hmn_member_name = 'elicitation method'
        super().__init__(request)

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description'])
        }

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data['datetime_modified'] = datetime.datetime.utcnow()
        return user_data
