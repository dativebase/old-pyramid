"""Syntactic Categories View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Syntacticcategories(Resources):
    """Generate responses to requests on syntactic category resources."""

    def _get_new_edit_collections(self):
        return ('syntactic_category_types',)

    def _post_update(self, syntactic_category, previous_resource_dict):
        self._update_forms_referencing_this_category(syntactic_category)

    def _post_delete(self, syntactic_category):
        self._update_forms_referencing_this_category(syntactic_category)

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'type': data['type'],
            'description': h.normalize(data['description'])
        }

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data

    def _update_forms_referencing_this_category(self, syntactic_category):
        """Update all forms that reference a syntactic category.
        :param syntactic_category: a syntactic category model object.
        :returns: ``None``
        .. note::
            This function is only called when a syntactic category is deleted or
            when its name is changed.
        """
        from old.views.forms import Forms
        form_view = Forms(self.request)
        forms_of_this_category = syntactic_category.forms
        for form in forms_of_this_category:
            form_view.update_forms_containing_this_form_as_morpheme(form)
