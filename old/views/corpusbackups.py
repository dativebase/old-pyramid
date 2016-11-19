import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Corpusbackups(ReadonlyResources):
    """Generate responses to requests on corpus backup resources.
    .. note::
        Corpus backups are created when updating and deleting corpora;
        they cannot be created directly and they should never be deleted.  This
        controller facilitates searching and getting of corpus backups only.
    """

    def __init__(self, request):
        self.model_name = 'CorpusBackup'
        self.hmn_member_name = 'corpus backup'
        super().__init__(request)

    def _model_access_unauth(self, resource_model):
        """Ensure that only authorized users can access the provided
        ``resource_model``.
        """
        unrestricted_users = self.db.get_unrestricted_users()
        if not self.logged_in_user.is_authorized_to_access_model(
                resource_model, unrestricted_users):
            return True
        return False
