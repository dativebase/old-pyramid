import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Morphologybackups(ReadonlyResources):

    def __init__(self, request):
        self.model_name = 'MorphologyBackup'
        self.hmn_member_name = 'morphology backup'
        super().__init__(request)
