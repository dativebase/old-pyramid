# Copyright 2016 Joel Dunham
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Contains the :class:`FilesView` and its auxiliary functions.

.. module:: files
   :synopsis: Contains the files view and its auxiliary functions.

"""

import datetime
import json
import logging
from mimetypes import guess_type
from random import sample
import os
import shutil
from string import digits, ascii_letters

from formencode.validators import Invalid
from pyramid.response import FileResponse

from old.lib.constants import (
    JSONDecodeErrorResponse,
    UNAUTHORIZED_MSG,
)
import old.lib.helpers as h
from old.lib.schemata import (
    FileCreateWithBase64EncodedFiledataSchema,
    FileCreateWithFiledataSchema,
    FileExternallyHostedSchema,
    FileSubintervalReferencingSchema,
    FileUpdateSchema,
)
from old.lib.resize import save_reduced_copy
from old.models import File
from old.views.resources import (
    Resources,
    SchemaState
)


LOGGER = logging.getLogger(__name__)


# JSON/Base64 file upload caps out at ~20MB
MAX_BASE64_SIZE = 20971520


class InvalidFieldStorageObjectError(Exception):
    pass


class Files(Resources):
    """Generate responses to requests on file resources."""

    def create(self):
        """Create a new file resource and return it.

        - URL: ``POST /files``
        - request body: JSON object *or* conventional POST parameters containing
          the attribute values of the new file.
        - content type: ``application/json`` *or* ``multipart/form-data``.

        :returns: the newly created file.

        .. note:: The ``Files`` view completely overrides the public ``create``
           method of ``Resources`` because files are special. There are three
           types of file and four types of file creation request.

           1. **Local file with** ``multipart/form-data`` **content type.**
              File data are in the request body and the file metadata are
              structured as conventional POST parameters.

           2. **Local file with** ``application/json`` **content type.**
              File data are Base64-encoded and are contained in the same JSON
              object as the metadata, in the request body.

           3. **Subinterval-referencing file with** ``application/json``
              **content type.** All parameters provided in a JSON object. No
              file data are present; the ``id`` value of an existing
              *audio/video* parent file must be provided in the
              ``parent_file`` attribute; values for ``start`` and ``end``
              attributes are also required.

           4. **Externally hosted file with** ``application/json``
              **content-type.** All parameters provided in a JSON object. No
              file data are present; the value of the ``url`` attribute is a
              valid URL where the file data are being served.
        """
        LOGGER.info('Attempting to create a new file.')
        try:
            if self.request.content_type == 'application/json':
                if len(self.request.body) > MAX_BASE64_SIZE:
                    self.request.response.status_int = 400
                    LOGGER.warning('User tried to upload a >20M file using'
                                   ' base64-encoded bytes in JSON')
                    return {'error': 'The request body is too large; use the'
                                     ' multipart/form-data Content-Type when'
                                     ' uploading files greater than 20MB.'}
                try:
                    values = json.loads(
                        self.request.body.decode(self.request.charset))
                except ValueError:
                    self.request.response.status_int = 400
                    LOGGER.warning('Malformed JSON')
                    return JSONDecodeErrorResponse
                if 'base64_encoded_file' in values:
                    resource = self._create_base64_file(values)
                elif 'url' in values:
                    resource = self._create_externally_hosted_file(values)
                else:
                    resource = self._create_subinterval_referencing_file(values)
            else:
                try:
                    resource = self._create_plain_file()
                except InvalidFieldStorageObjectError:
                    self.request.response.status_int = 400
                    msg = ('The attempted multipart/form-data file upload'
                           ' failed.')
                    LOGGER.warning(msg)
                    return {'error': msg}
            resource.lossy_filename = save_reduced_copy(
                resource, self.request.registry.settings)
            self.request.dbsession.add(resource)
            self.request.dbsession.flush()
            self._post_create(resource)
            LOGGER.info('Created new file %s.', resource.id)
            return resource.get_dict()
        except Invalid as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}

    def update(self):
        """Update a file and return it. Note: like the ``create`` method, the
        ``update`` method for file models is special so we completely override
        the super-class's implementation.

        - URL: ``PUT /files/id``
        - Request body: JSON object representing the file with updated attribute
          values.

        :param id_: the ``id`` value of the file to be updated.
        :type id_: str
        :returns: the updated file model.
        """
        file_, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to update file %s.', id_)
        if not file_:
            self.request.response.status_int = 404
            msg = 'There is no {} with id {}'.format(self.member_name, id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if self._model_access_unauth(file_) is not False:
            self.request.response.status_int = 403
            LOGGER.warning(UNAUTHORIZED_MSG)
            return UNAUTHORIZED_MSG
        try:
            if getattr(file_, 'parent_file', None):
                file_ = self._update_subinterval_referencing_file(file_)
            elif getattr(file_, 'url', None):
                file_ = self._update_externally_hosted_file(file_)
            else:
                file_ = self._update_file(file_)
            # file will be False if there are no changes
            if file_:
                self.request.dbsession.add(file_)
                self.request.dbsession.flush()
                LOGGER.info('Updated file %s.', id_)
                return file_.get_dict()
            self.request.response.status_int = 400
            msg = ('The update request failed because the submitted data were'
                   ' not new.')
            LOGGER.warning(msg)
            return {'error': msg}
        except ValueError:
            self.request.response.status_int = 400
            LOGGER.warning(JSONDecodeErrorResponse)
            return JSONDecodeErrorResponse
        except Invalid as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}

    # Because file creation is special, the following three abtract methods are
    # not useful and need to be declared vacuously.

    def _get_user_data(self, data):
        pass

    def _get_create_data(self, data):
        pass

    def _get_update_data(self, user_data):
        pass

    def _filter_query(self, query_obj):
        return self._filter_restricted_models(query_obj)

    def _model_access_unauth(self, resource_model):
        """Ensure that only authorized users can access the provided
        ``resource_model``.
        """
        unrestricted_users = self.db.get_unrestricted_users()
        if not self.logged_in_user.is_authorized_to_access_model(
                resource_model, unrestricted_users):
            return True
        return False

    def _delete_unauth(self, file_):
        """Only administrators and a file's enterer can delete a file."""
        if (    self.logged_in_user.role == 'administrator' or
                file_.enterer.id == self.logged_in_user.id):
            return False
        return True

    # Special private methods for file creation and update.

    def _create_base64_file(self, data):
        """Create a local file using data from a ``Content-Type:
        application/json`` request.
        :param dict data: the data to create the file model.
        :param str data['base64_encoded_file']: Base64-encoded file data.
        :returns: an SQLAlchemy model object representing the file.
        """
        data['MIME_type'] = ''  # during validation, the schema will set a proper
                                # value based on the base64_encoded_file or
                                # filename attribute
        schema = FileCreateWithBase64EncodedFiledataSchema()
        state = SchemaState(
            full_dict=data,
            db=self.db,
            logged_in_user=self.logged_in_user
        )
        data = schema.to_python(data, state)
        file_ = File(
            MIME_type=data['MIME_type'],
            filename=h.normalize(data['filename'])
        )
        file_ = self._add_standard_metadata(file_, data)
        # Write the file to disk (making sure it's unique and thereby potentially)
        # modifying file.filename; and calculate file.size.
        # base64-decoded during validation
        file_data = data['base64_encoded_file']
        files_path = h.get_old_directory_path(
            'files', self.request.registry.settings)
        file_path = os.path.join(files_path, file_.filename)
        file_object, file_path = _get_unique_file_path(file_path)
        file_.filename = os.path.split(file_path)[-1]
        file_.name = file_.filename
        file_object.write(file_data)
        file_object.close()
        file_data = None
        file_.size = os.path.getsize(file_path)
        file_ = _restrict_file_by_forms(file_)
        return file_

    def _create_externally_hosted_file(self, data):
        """Create an externally hosted file.
        :param dict data: the data to create the file model.
        :param str data['url']: a valid URL where the file data are served.
        :returns: an SQLAlchemy model object representing the file.
        Optional keys of the data dictionary, not including the standard
        metadata ones, are ``name``, ``password`` and ``MIME_type``.
        """
        data['password'] = data.get('password') or ''
        schema = FileExternallyHostedSchema()
        data = schema.to_python(data)
        # User-inputted string data
        file_ = File(
            name=h.normalize(data['name']),
            password=data['password'],
            MIME_type=data['MIME_type'],
            url=data['url']
        )
        file_ = self._add_standard_metadata(file_, data)
        file_ = _restrict_file_by_forms(file_)
        return file_

    def _create_subinterval_referencing_file(self, data):
        """Create a subinterval-referencing file.
        :param dict data: the data to create the file model.
        :param int data['parent_file']: the ``id`` value of an audio/video file
            model.
        :param float/int data['start']: the start of the interval in seconds.
        :param float/int data['end']: the end of the interval in seconds.
        :returns: an SQLAlchemy model object representing the file.
        A value for ``data['name']`` may also be supplied.
        """
        data['name'] = data.get('name') or ''
        schema = FileSubintervalReferencingSchema()
        state = SchemaState(
            full_dict=data,
            db=self.db,
            logged_in_user=self.logged_in_user
        )
        data = schema.to_python(data, state)
        # Data unique to referencing subinterval files
        file_ = File(
            parent_file=data['parent_file'],
            # Name defaults to the parent file's filename if nothing provided by
            # user
            name=h.normalize(data['name']) or data['parent_file'].filename,
            start=data['start'],
            end=data['end'],
            MIME_type=data['parent_file'].MIME_type
        )
        file_ = self._add_standard_metadata(file_, data)
        file_ = _restrict_file_by_forms(file_)
        return file_

    def _create_plain_file(self):
        """Create a local file using data from a ``Content-Type:
        multipart/form-data`` request.
        :param request.POST['filedata']: a ``cgi.FieldStorage`` object
            containing the file data.
        :param str request.POST['filename']: the name of the binary file.
        :returns: an SQLAlchemy model object representing the file.
        .. note::
            The validator expects ``request.POST`` to encode list input via the
            ``formencode.variabledecode.NestedVariables`` format. E.g., a list
            of form ``id`` values would be provided as values to keys with
            names like ``'forms-0'``, ``'forms-1'``, ``'forms-2'``, etc.
        """
        values = dict(self.request.params)
        filedata = self.request.POST.get('filedata')
        if not hasattr(filedata, 'file'):
            raise InvalidFieldStorageObjectError(
                'POST filedata has no "file" attribute')
        if not values.get('filename'):
            values['filename'] = os.path.split(filedata.filename)[-1]
        state = SchemaState(
            full_dict={},
            db=self.db,
            filedata_first_KB=filedata.value[:1024])
        schema = FileCreateWithFiledataSchema()
        data = schema.to_python(values, state)
        file_ = File(
            filename=h.normalize(data['filename']),
            MIME_type=data['MIME_type']
        )
        files_path=h.get_old_directory_path('files', self.request.registry.settings)
        file_path = os.path.join(files_path, file_.filename)
        file_object, file_path = _get_unique_file_path(file_path)
        file_.filename = os.path.split(file_path)[-1]
        file_.name = file_.filename
        shutil.copyfileobj(filedata.file, file_object)
        filedata.file.close()
        file_object.close()
        file_.size = os.path.getsize(file_path)
        file_ = self._add_standard_metadata(file_, data)
        return file_

    def _update_subinterval_referencing_file(self, file_):
        """Update a subinterval-referencing file model.
        :param file_: a file model object to update.
        :param request.body: a JSON object containing the data for updating the
            file.
        :returns: the file model or, if the file has not been updated, ``False``.
        """
        changed = False
        schema = FileSubintervalReferencingSchema()
        data = json.loads(self.request.body.decode(self.request.charset))
        data['name'] = data.get('name') or ''
        state = SchemaState(
            full_dict=data,
            db=self.db,
            logged_in_user=self.logged_in_user)
        data = schema.to_python(data, state)
        # Data unique to referencing subinterval files

        changed = file_.set_attr('parent_file', data['parent_file'], changed)
        changed = file_.set_attr(
            'name',
            (h.normalize(data['name']) or file_.parent_file.filename),
            changed
        )
        changed = file_.set_attr('start', data['start'], changed)
        changed = file_.set_attr('end', data['end'], changed)
        file_, changed = _update_standard_metadata(file_, data, changed)
        if changed:
            file_.datetime_modified = datetime.datetime.utcnow()
            return file_
        return changed

    def _update_externally_hosted_file(self, file_):
        """Update an externally hosted file model.
        :param file_: a file model object to update.
        :param request.body: a JSON object containing the data for updating the
            file.
        :returns: the file model or, if the file has not been updated,
            ``False``.
        """
        changed = False
        data = json.loads(self.request.body.decode(self.request.charset))
        data['password'] = data.get('password') or ''
        data = FileExternallyHostedSchema().to_python(data)
        # Data unique to referencing subinterval files
        changed = file_.set_attr('url', data['url'], changed)
        changed = file_.set_attr('name', h.normalize(data['name']), changed)
        changed = file_.set_attr('password', data['password'], changed)
        changed = file_.set_attr('MIME_type', data['MIME_type'], changed)
        file_, changed = _update_standard_metadata(file_, data, changed)
        if changed:
            file_.datetime_modified = datetime.datetime.utcnow()
            return file_
        return changed

    def _update_file(self, file_):
        """Update a local file model.
        :param file_: a file model object to update.
        :param request.body: a JSON object containing the data for updating the
            file.
        :returns: the file model or, if the file has not been updated,
            ``False``.
        """
        changed = False
        schema = FileUpdateSchema()
        data = json.loads(self.request.body.decode(self.request.charset))
        state = SchemaState(
            full_dict=data,
            db=self.db,
            logged_in_user=self.logged_in_user)
        data = schema.to_python(data, state)
        file_, changed = _update_standard_metadata(file_, data, changed)
        if changed:
            file_.datetime_modified = datetime.datetime.utcnow()
            return file_
        return changed

    def _add_standard_metadata(self, file_, data):
        """Add the standard metadata to the file model using the data dictionary.
        :param file_: file model object
        :param dict data: dictionary containing file attribute values.
        :returns: the updated file model object.
        """
        file_.description = h.normalize(data['description'])
        file_.utterance_type = data['utterance_type']
        file_.date_elicited = data['date_elicited']
        if data['elicitor']:
            file_.elicitor = data['elicitor']
        if data['speaker']:
            file_.speaker = data['speaker']
        file_.tags = [t for t in data['tags'] if t]
        file_.forms = [f for f in data['forms'] if f]
        now = h.now()
        file_.datetime_entered = now
        file_.datetime_modified = now
        file_.enterer = self.logged_in_user
        return file_

    def _get_new_edit_collections(self):
        """Returns the names of the collections that are required in order to
        create a new, or edit an existing, file.
        """
        return (
            'allowed_file_types',  # constant in lib/constants.py
            'speakers',
            'tags',
            'users',
            'utterance_types'  # constant in lib/constants.py
        )

    def _pre_delete(self, file_model):
        """Delete the digital file prior to deleting the database file data."""
        if getattr(file_model, 'filename', None):
            file_path = os.path.join(
                h.get_old_directory_path(
                    'files', self.request.registry.settings),
                file_model.filename)
            os.remove(file_path)
        if getattr(file_model, 'lossy_filename', None):
            file_path = os.path.join(
                h.get_old_directory_path(
                    'reduced_files', self.request.registry.settings),
                file_model.lossy_filename)
            os.remove(file_path)

    def serve(self):
        """Return the file data (binary stream) of the file."""
        return self._serve()

    def serve_reduced(self):
        """Return the reduced-size file data (binary stream) of the file."""
        return self._serve(reduced=True)

    def _serve(self, reduced=False):
        """Serve the content (binary data) of a file.
        :param bool reduced: toggles serving of file data or reduced-size file
            data.
        """
        file_, id_ = self._model_from_id(eager=True)
        if not file_:
            self.request.response.status_int = 404
            return {'error': 'There is no file with id %s' % id_}
        if self._model_access_unauth(file_) is not False:
            self.request.response.status_int = 403
            return UNAUTHORIZED_MSG
        if getattr(file_, 'parent_file', None):
            file_ = file_.parent_file
        elif getattr(file_, 'url', None):
            self.request.response.status_int = 400
            return {
                'error': 'The content of file %s is stored elsewhere at %s' % (
                    id_, file_.url)}
        files_dir = h.get_old_directory_path('files',
                                             self.request.registry.settings)
        if reduced:
            filename = getattr(file_, 'lossy_filename', None)
            if not filename:
                self.request.response.status_int = 404
                return {
                    'error': 'There is no size-reduced copy of file %s' %
                             id_}
            file_path = os.path.join(files_dir, 'reduced_files', filename)
            content_type = guess_type(filename)[0]
        else:
            file_path = os.path.join(files_dir, file_.filename)
            content_type = file_.MIME_type
        return FileResponse(
            file_path,
            request=self.request,
            content_type=content_type)


def _get_unique_file_path(file_path):
    """Get a unique file path.
    :param str file_path: an absolute file path.
    :returns: a tuple whose first element is the open file object and whose
        second is the unique file path as a unicode string.
    """
    file_path_parts = os.path.splitext(file_path)
    while True:
        try:
            file_descriptor = os.open(
                file_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return os.fdopen(file_descriptor, 'wb'), file_path
        except (OSError, IOError):
            pass
        file_path = '%s_%s%s' % (
            file_path_parts[0][:230],
            ''.join(sample(digits + ascii_letters, 8)),
            file_path_parts[1])


def _restrict_file_by_forms(file_):
    """Restrict the entire file if it is associated to restricted forms.
    :param file_: a file model object.
    :returns: the file model object potentially tagged as "restricted".
    """
    tags = [f.tags for f in file_.forms]
    tags = [tag for tag_list in tags for tag in tag_list]
    restricted_tags = [tag for tag in tags if tag.name == 'restricted']
    if restricted_tags:
        restricted_tag = restricted_tags[0]
        if restricted_tag not in file_.tags:
            file_.tags.append(restricted_tag)
    return file_


def _update_standard_metadata(file_, data, changed):
    """Update the standard metadata attributes of the input file.
    :param file_: a file model object to be updated.
    :param dict data: the data used to update the file model.
    :param bool changed: indicates whether the file has been changed.
    :returns: a tuple whose first element is the file model and whose second is
        the boolean ``changed``.
    """
    changed = file_.set_attr(
        'description', h.normalize(data['description']), changed)
    changed = file_.set_attr(
        'utterance_type', h.normalize(data['utterance_type']), changed)
    changed = file_.set_attr('date_elicited', data['date_elicited'], changed)
    changed = file_.set_attr('elicitor', data['elicitor'], changed)
    changed = file_.set_attr('speaker', data['speaker'], changed)
    # Many-to-Many Data: tags & forms
    # Update only if the user has made changes.
    forms_to_add = [f for f in data['forms'] if f]
    tags_to_add = [t for t in data['tags'] if t]
    if set(forms_to_add) != set(file_.forms):
        file_.forms = forms_to_add
        changed = True
        # Cause the entire file to be tagged as restricted if any one of its
        # forms are so tagged.
        tags = [f.tags for f in file_.forms]
        tags = [tag for tag_list in tags for tag in tag_list]
        restricted_tags = [tag for tag in tags if tag.name == 'restricted']
        if restricted_tags:
            restricted_tag = restricted_tags[0]
            if restricted_tag not in tags_to_add:
                tags_to_add.append(restricted_tag)
    if set(tags_to_add) != set(file_.tags):
        file_.tags = tags_to_add
        changed = True
    return file_, changed
