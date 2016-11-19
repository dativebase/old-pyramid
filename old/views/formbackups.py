import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Formbackups(ReadonlyResources):

    def __init__(self, request):
        self.model_name = 'FormBackup'
        self.hmn_member_name = 'form backup'
        super().__init__(request)

    def _filter_query(self, query_obj):
        """Depending on the unrestrictedness of the user and the
        unrestrictedness of the forms in the query, filter it, or not.
        """
        return self._filter_restricted_models(query_obj)

    def _model_access_unauth(self, resource_model):
        """Ensure that only authorized users can access the provided
        ``resource_model``.
        """
        unrestricted_users = self.db.get_unrestricted_users()
        if not self.logged_in_user.is_authorized_to_access_model(
                resource_model, unrestricted_users):
            return True
        return False
