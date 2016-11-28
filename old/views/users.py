"""Users View"""
import datetime
import logging

from old.views.resources import Resources
import old.lib.helpers as h


LOGGER = logging.getLogger(__name__)


class Users(Resources):
    """Generate responses to requests on user resources."""

    def _get_new_edit_collections(self):
        return (
            'markup_languages',
            'orthographies',
            'roles'
        )

    def _get_create_dict(self, resource_model):
        return resource_model.get_full_dict()

    def _get_delete_dict(self, resource_model):
        return resource_model.get_full_dict()

    def _get_edit_dict(self, resource_model):
        return resource_model.get_full_dict()

    def _update_resource_model(self, resource_model, data):
        changed = False
        user_data = self._get_user_data(data)
        if data['password'] is not None:
            user_data['password'] = str(
                h.encrypt_password(data['password'], resource_model.salt.encode('utf8')))
        if data['username'] is not None:
            username = h.normalize(data['username'])
            if username != resource_model.username:
                h.rename_user_directory(
                    resource_model.username, username,
                    self.request.registry.settings)
            user_data['username'] = username
        for attr, val in user_data.items():
            if self._distinct(attr, val, getattr(resource_model, attr)):
                changed = True
                break
        if changed:
            for attr, val in self._get_update_data(user_data).items():
                setattr(resource_model, attr, val)
            return resource_model
        return changed

    def _get_update_state(self, values, id_, resource_model):
        """User update validation requires the to-be-updated user (as dict)
        as well as the current user.
        """
        update_state = self._get_create_state(values)
        update_state.id = id_
        update_state.user_to_update = resource_model.get_full_dict()
        update_state.user = self.logged_in_user.get_full_dict()
        return update_state

    def _post_create(self, user):
        h.create_user_directory(user, self.request.registry.settings)

    def _get_user_data(self, data):
        result = {
            'first_name': h.normalize(data['first_name']),
            'last_name': h.normalize(data['last_name']),
            'email': h.normalize(data['email']),
            'affiliation': h.normalize(data['affiliation']),
            'role': h.normalize(data['role']),
            'markup_language': h.normalize(data['markup_language']),
            'page_content': h.normalize(data['page_content']),
            'input_orthography': data['input_orthography'],
            'output_orthography': data['output_orthography']
        }
        result['html'] = h.get_HTML_from_contents(
            result['page_content'], result['markup_language'])
        return result

    def _get_create_data(self, data):
        create_data = self._get_user_data(data)
        create_data['salt'] = str(h.generate_salt())
        create_data['password'] = str(
            h.encrypt_password(data['password'], create_data['salt'].encode('utf8')))
        create_data['username'] = h.normalize(data['username'])
        create_data['datetime_modified'] = datetime.datetime.utcnow()
        return create_data

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data

    def _pre_delete(self, user):
        h.destroy_user_directory(user, self.request.registry.settings)
