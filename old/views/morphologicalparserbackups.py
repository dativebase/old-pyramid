import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Morphologicalparserbackups(ReadonlyResources):

    def __init__(self, request):
        self.model_name = 'MorphologicalParserBackup'
        self.hmn_member_name = 'morphological parser backup'
        super().__init__(request)
