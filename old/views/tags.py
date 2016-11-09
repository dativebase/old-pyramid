"""Tags View
"""
import datetime
import json
import logging

from formencode.validators import Invalid

from old.views.resources import Resources
from old.lib.schemata import TagSchema
import old.lib.helpers as h
from old.models import Tag


LOGGER = logging.getLogger(__name__)


class Tags(Resources):
    """Generate responses to requests on tag resources."""

    def index(self):
        """Get all tag resources.

        :URL: ``GET /tags`` with optional query string parameters for
            ordering and pagination.
        :returns: a list of all tag resources.

        .. note::

           See :func:`utils.add_order_by` and :func:`utils.add_pagination` for
           the query string parameters that effect ordering and pagination.
        """
        try:
            query = self.request.dbsession.query(Tag)
            query = h.add_order_by(query, dict(self.request.GET),
                                   self.query_builder)
            return h.add_pagination(query, dict(self.request.GET))
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}

    # @h.authorize(['administrator', 'contributor'])
    def create(self):
        """Create a new tag resource and return it.

        :URL: ``POST /tags``
        :request body: JSON object representing the tag to create.
        :returns: the newly created tag.
        """
        schema = TagSchema()
        try:
            values = json.loads(self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return h.JSONDecodeErrorResponse
        try:
            state = h.get_state_object(
                dbsession=self.request.dbsession,
                logged_in_user=self.request.session.get('user', {}))
            data = schema.to_python(values, state)
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}
        tag = create_new_tag(data)
        self.request.dbsession.add(tag)
        self.request.dbsession.flush()
        return tag

    # @h.authorize(['administrator', 'contributor'])
    def new(self):
        """Return the data necessary to create a new tag.

        :URL: ``GET /tags/new``.
        :returns: an empty dictionary.
        """
        return {}

    # @h.authorize(['administrator', 'contributor'])
    def update(self):
        """Update a tag and return it.

        :URL: ``PUT /tags/<id>``
        :Request body: JSON object representing the tag with updated attribute
            values.
        :param str id: the ``id`` value of the tag to be updated.
        :returns: the updated tag model.
        """
        id_ = self.request.matchdict['id']
        tag = self.request.dbsession.query(Tag).get(int(id_))
        if not tag:
            self.request.response.status_int = 404
            return {'error': 'There is no tag with id %s' % id_}
        schema = TagSchema()
        try:
            values = json.loads(self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return h.JSONDecodeErrorResponse
        state = h.get_state_object(
            values=values,
            dbsession=self.request.dbsession,
            logged_in_user=self.request.session.get('user', {}))
        state.id = id_
        try:
            data = schema.to_python(values, state)
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}
        tag = update_tag(tag, data)
        # tag will be False if there are no changes (cf. update_tag).
        if not tag:
            self.request.response.status_int = 400
            return {'error': 'The update request failed because the submitted'
                             ' data were not new.'}
        self.request.dbsession.add(tag)
        self.request.dbsession.flush()
        return tag

    # @h.authorize(['administrator', 'contributor'])
    def delete(self):
        """Delete an existing tag and return it.

        :URL: ``DELETE /tags/<id>``
        :param str id: the ``id`` value of the tag to be deleted.
        :returns: the deleted tag model.
        """
        id_ = self.request.matchdict['id']
        tag = self.request.dbsession.query(Tag).get(id_)
        if not tag:
            self.request.response.status_int = 404
            return {'error': 'There is no tag with id %s' % id_}
        if tag.name in ('restricted', 'foreign word'):
            self.request.response.status_int = 403
            return {'error': 'The restricted and foreign word tags cannot be'
                             ' deleted.'}
        self.request.dbsession.delete(tag)
        return tag

    def show(self):
        """Return a tag.

        :URL: ``GET /tags/<id>``
        :param str id: the ``id`` value of the tag to be returned.
        :returns: a tag model object.
        """
        id_ = self.request.matchdict['id']
        tag = self.request.dbsession.query(Tag).get(id_)
        if not tag:
            self.request.response.status_int = 404
            return {'error': 'There is no tag with id %s' % id_}
        return tag

    # @h.authorize(['administrator', 'contributor'])
    def edit(self):
        """Return a tag resource and the data needed to update it.

        :URL: ``GET /tags/edit``
        :param str id: the ``id`` value of the tag that will be updated.
        :returns: a dictionary of the form::

                {"tag": {...}, "data": {...}}

            where the value of the ``tag`` key is a dictionary representation
            of the tag and the value of the ``data`` key is an empty
            dictionary.
        """
        id_ = self.request.matchdict['id']
        tag = self.request.dbsession.query(Tag).get(id_)
        if not tag:
            self.request.response.status_int = 404
            return {'error': 'There is no tag with id %s' % id_}
        return {'data': {}, 'tag': tag}


###############################################################################
# Tag Create & Update Functions
###############################################################################

def create_new_tag(data):
    """Create a new tag.

    :param dict data: the data for the tag to be created.
    :returns: an SQLAlchemy model object representing the tag.
    """
    tag = Tag()
    tag.name = h.normalize(data['name'])
    tag.description = h.normalize(data['description'])
    tag.datetime_modified = datetime.datetime.utcnow()
    return tag


def update_tag(tag, data):
    """Update a tag.

    :param tag: the tag model to be updated.
    :param dict data: representation of the updated tag.
    :returns: the updated tag model or, if ``changed`` has not been set
        to ``True``, ``False``.
    """
    changed = False
    changed = tag.set_attr('name', h.normalize(data['name']), changed)
    changed = tag.set_attr('description', h.normalize(data['description']),
                           changed)
    if changed:
        tag.datetime_modified = datetime.datetime.utcnow()
        return tag
    return changed
