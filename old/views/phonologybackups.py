import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Phonologybackups(ReadonlyResources):

    def __init__(self, request):
        self.model_name = 'PhonologyBackup'
        self.hmn_member_name = 'phonology backup'
        super().__init__(request)
