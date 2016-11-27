"""Languages View"""
import logging

from old.views.resources import ReadonlyResources


LOGGER = logging.getLogger(__name__)


class Languages(ReadonlyResources):

    def __init__(self, request):
        super().__init__(request)
        self.primary_key = 'Id'

    def _model_from_id(self, eager=False):
        """Return a particular model instance (and the id value), given the
        model id supplied in the URL path.
        """
        id_ = self.request.matchdict['id']
        if eager:
            return (
                self._eagerload_model(
                    self.request.dbsession.query(self.model_cls)).get(id_),
                id_)
        else:
            return self.request.dbsession.query(self.model_cls).get(id_), id_
