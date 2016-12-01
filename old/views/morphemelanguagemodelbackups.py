import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Morphemelanguagemodelbackups(ReadonlyResources):

    def __init__(self, request):
        self.model_name = 'MorphemeLanguageModelBackup'
        self.hmn_member_name = 'morpheme language model backup'
        super().__init__(request)
