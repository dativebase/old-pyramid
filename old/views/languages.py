"""Languages View"""
import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Languages(ReadonlyResources):

    def __init__(self, request):
        super().__init__(request)
        self.primary_key = 'Id'
