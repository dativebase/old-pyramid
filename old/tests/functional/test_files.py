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

from base64 import b64encode
import datetime
import json
import logging
import os
import pprint

from mimetypes import guess_type
try:
    import Image
except ImportError:
    try:
        from PIL import Image
    except ImportError:
        Image = None

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import File
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods

LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = File._url(old_name=TestView.old_name)
forms_url = old_models.Form._url(old_name=TestView.old_name)


class TestFilesView(TestView):

    def tearDown(self):
        super().tearDown(dirs_to_clear=['files_path', 'reduced_files_path'])

    def test_index(self):
        """Tests that GET /files returns a JSON array of files with expected
        values.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Test that the restricted tag is working correctly.
        # First get the users.
        users = db.get_users()
        contributor_id = [u for u in users if u.role ==
                            'contributor'][0].id

        # Then add a contributor and a restricted tag.
        restricted_tag = omb.generate_restricted_tag()
        my_contributor = omb.generate_default_user()
        my_contributor_first_name = 'Mycontributor'
        my_contributor.first_name = my_contributor_first_name
        dbsession.add_all([restricted_tag, my_contributor])
        dbsession.commit()
        my_contributor = dbsession.query(old_models.User).filter(
            old_models.User.first_name == my_contributor_first_name).first()
        my_contributor_id = my_contributor.id
        restricted_tag = db.get_restricted_tag()

        # Then add the default application settings with my_contributor as
        # the only unrestricted user.
        application_settings = omb.generate_default_application_settings()
        application_settings.unrestricted_users = [my_contributor]
        dbsession.add(application_settings)
        dbsession.commit()

        # Finally, issue two POST requests to create two default files with the
        # *default* contributor as the enterer.  One file will be restricted and
        # the other will not be.
        extra_environ = {'test.authentication.id': contributor_id}

        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        with open(wav_file_path, 'rb') as f:
            wav_file_base64_encoded = b64encode(f.read()).decode('utf8')

        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64_encoded = b64encode(f.read()).decode('utf8')

        # Create the restricted file.
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'test_restricted_file.wav',
            'base64_encoded_file': wav_file_base64_encoded,
            'tags': [db.get_tags()[0].id]    # the restricted tag should be
                                                # the only one
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                        extra_environ)
        resp = response.json_body
        restricted_file_id = resp['id']

        # Create the unrestricted file.
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'test_unrestricted_file.jpg',
            'base64_encoded_file': jpg_file_base64_encoded
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                        extra_environ)
        resp = response.json_body

        # Expectation: the administrator, the default contributor (qua enterer)
        # and the unrestricted my_contributor should all be able to view both files.
        # The viewer will only receive the unrestricted file.

        # An administrator should be able to view both files.
        extra_environ = {'test.authentication.role': 'administrator'}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 2
        assert resp[0]['filename'] == 'test_restricted_file.wav'
        assert resp[1]['filename'] == 'test_unrestricted_file.jpg'
        assert response.content_type == 'application/json'

        # The default contributor (qua enterer) should also be able to view both
        # files.
        extra_environ = {'test.authentication.id': contributor_id}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 2

        # Mycontributor (an unrestricted user) should also be able to view both
        # files.
        extra_environ = {'test.authentication.id': my_contributor_id}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 2

        # A (not unrestricted) viewer should be able to view only one file.
        extra_environ = {'test.authentication.role': 'viewer'}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 1

        # Remove Mycontributor from the unrestricted users list and access to
        # the second file will be denied.
        application_settings = db.current_app_set
        application_settings.unrestricted_users = []
        dbsession.add(application_settings)
        dbsession.commit()

        # Mycontributor (no longer an unrestricted user) should now *not* be
        # able to view the restricted file.
        extra_environ = {'test.authentication.id': my_contributor_id}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 1

        # Remove the restricted tag from the file and the viewer should now be
        # able to view it too.
        restricted_file = dbsession.query(old_models.File).get(restricted_file_id)
        restricted_file.tags = []
        dbsession.add(restricted_file)
        dbsession.commit()
        extra_environ = {'test.authentication.role': 'viewer'}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 2

        # Clear all Files (actually, everything but the tags, users and languages)
        db.clear_all_models(['User', 'Tag', 'Language'])

        # Now add 100 files.  The even ones will be restricted, the odd ones not.
        # These files will be deficient, i.e., have no binary data or MIME_type
        # but that's ok ...
        def create_file_from_index(index):
            file = old_models.File()
            file.filename = 'name_%d.jpg' % index
            return file
        files = [create_file_from_index(i) for i in range(1, 101)]
        dbsession.add_all(files)
        dbsession.commit()
        files = db.get_files()
        restricted_tag = db.get_restricted_tag()
        for file in files:
            if int(file.filename.split('_')[1].split('.')[0]) % 2 == 0:
                file.tags.append(restricted_tag)
            dbsession.add(file)
        dbsession.commit()
        files = db.get_files()    # ordered by File.id ascending

        # An administrator should be able to retrieve all of the files.
        extra_environ = {'test.authentication.role': 'administrator'}
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp) == 100
        assert resp[0]['filename'] == 'name_1.jpg'
        assert resp[0]['id'] == files[0].id

        # Test the paginator GET params.
        paginator = {'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp['items']) == 23
        assert resp['items'][0]['filename'] == files[46].filename

        # Test the order_by GET params.
        order_by_params = {'order_by_model': 'File', 'order_by_attribute': 'filename',
                    'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
                        headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        result_set = sorted([f.filename for f in files], reverse=True)
        assert result_set == [f['filename'] for f in resp]
        assert response.content_type == 'application/json'

        # Test the order_by *with* paginator.
        params = {'order_by_model': 'File', 'order_by_attribute': 'filename',
                    'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
        response = self.app.get(url('index'), params,
                        headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert result_set[46] == resp['items'][0]['filename']

        # The default viewer should only be able to see the odd numbered files,
        # even with a paginator.
        items_per_page = 7
        page = 7
        paginator = {'items_per_page': items_per_page, 'page': page}
        extra_environ = {'test.authentication.role': 'viewer'}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ)
        resp = response.json_body
        assert len(resp['items']) == items_per_page
        assert resp['items'][0]['filename'] == 'name_%d.jpg' % (
            ((items_per_page * (page - 1)) * 2) + 1)

        # Expect a 400 error when the order_by_direction param is invalid
        order_by_params = {'order_by_model': 'File', 'order_by_attribute': 'filename',
                    'order_by_direction': 'descending'}
        response = self.app.get(url('index'), order_by_params, status=400,
            headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"

        # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
        # param is invalid.
        order_by_params = {'order_by_model': 'Fileage', 'order_by_attribute': 'nom',
                    'order_by_direction': 'desc'}
        response = self.app.get(url('index'), order_by_params,
            headers=self.json_headers, extra_environ=extra_environ)
        resp = response.json_body
        assert resp[0]['id'] == files[0].id

        # Expect a 400 error when the paginator GET params are empty, not
        # specified or integers that are less than 1
        paginator = {'items_per_page': 'a', 'page': ''}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter an integer value'
        assert resp['errors']['page'] == 'Please enter a value'

        paginator = {'items_per_page': 0, 'page': -1}
        response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                extra_environ=extra_environ, status=400)
        resp = response.json_body
        assert resp['errors']['items_per_page'] == 'Please enter a number that is 1 or greater'
        assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'
        assert response.content_type == 'application/json'

    def test_create(self):
        """Tests that POST /files correctly creates a new file."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        ########################################################################
        # base64-encoded file creation
        ########################################################################

        # Pass some mal-formed JSON to test that a 400 error is returned.
        params = '"a'   # Bad JSON
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['error'] == 'JSON decode error: the parameters provided were not valid JSON.'

        # Create a test audio file.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        wav_file_size = os.path.getsize(wav_file_path)
        params = self.file_create_params_base64.copy()

        with open(wav_file_path, 'rb') as f:
            wav_file_base64 = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'old_test.wav',
            'base64_encoded_file': wav_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert resp['filename'] == 'old_test.wav'
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 1
        assert response.content_type == 'application/json'

        # Create a test image file.
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        jpg_file_size = os.path.getsize(jpg_file_path)
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')

        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        file_id = an_image_id = resp['id']
        assert resp['filename'] == 'old_test.jpg'
        assert resp['MIME_type'] == 'image/jpeg'
        assert resp['size'] == jpg_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 2

        # Create a test image file with many-to-many relations, i.e., tags and
        # forms.  First create a couple of tags.
        tag1 = old_models.Tag()
        tag1.name = 'tag 1'
        tag2 = old_models.Tag()
        tag2.name = 'tag 2'
        restricted_tag = omb.generate_restricted_tag()
        dbsession.add_all([tag1, tag2, restricted_tag])
        dbsession.flush()
        tag1_id = tag1.id
        tag2_id = tag2.id
        restricted_tag_id = restricted_tag.id
        dbsession.commit()

        # Then create a form to associate.
        params = self.form_create_params.copy()
        params.update({
            'transcription': 'test',
            'translations': [{'transcription': 'test', 'grammaticality': ''}]
        })
        params = json.dumps(params)
        response = self.app.post(forms_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        form_id = resp['id']

        # Now create the file with forms and tags
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64,
            'tags': [tag1_id, tag2_id],
            'forms': [form_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert resp['filename'][:9] == 'old_test_'
        assert resp['MIME_type'] == 'image/jpeg'
        assert resp['size'] == jpg_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert sorted([t['id'] for t in resp['tags']]) == sorted([tag1_id, tag2_id])
        assert resp['forms'][0]['transcription'] == 'test'
        assert file_count == 3

        # Invalid input
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        wav_file_size = os.path.getsize(wav_file_path)
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': '',                    # empty; not allowed
            'base64_encoded_file': '',        # empty; not allowed
            'utterance_type': 'l' * 1000,   # too long
            'date_elicited': '31/12/2012',   # wrong format
            'speaker': 200                  # invalid id
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert 'Value must be one of: None; Object Language Utterance; Metalanguage Utterance; Mixed Utterance' in \
            resp['errors']['utterance_type']
        assert resp['errors']['speaker'] == 'There is no speaker with id 200.'
        assert resp['errors']['date_elicited'] == 'Please enter a month from 1 to 12'
        assert resp['errors']['filename'] == 'Please enter a value'
        assert resp['errors']['base64_encoded_file']== 'Please enter a value'
        assert file_count == 3
        assert response.content_type == 'application/json'

        # Create an audio file with unicode characters.  Show that spaces are
        # replaced with underscores and that apostrophes and quotation marks are
        # removed.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        wav_file_size = os.path.getsize(wav_file_path)
        params = self.file_create_params_base64.copy()
        with open(wav_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': '\u201Cold te\u0301st\u201D.wav',
            'base64_encoded_file': base64_encoded_file,
            'tags': [restricted_tag_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        a_wav_file_id = resp['id']
        file_count = dbsession.query(old_models.File).count()
        assert '\u201Cold_te\u0301st\u201D.wav' in os.listdir(self.files_path)
        assert resp['filename'] == '\u201Cold_te\u0301st\u201D.wav'
        assert resp['name'] == resp['filename']     # name value set in files controller, user can't change this
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 4
        assert restricted_tag_id in [t['id'] for t in resp['tags']]
        assert response.content_type == 'application/json'

        # Attempt to create an illicit file type (.html) but with a valid
        # extension (.wav).  Expect an error, i.e., validation detects that
        # the file is really html, despite the misleading extension.
        # WARNING: this (type of) test will fail if python-magic (and its
        # dependency libmagic) is not installed. This is because the file
        # create validator will not recognize this file as HTML pretending
        # to be WAV
        files_dir_list = os.listdir(self.files_path)
        html_file_path = os.path.join(self.test_files_path, 'illicit.html')
        with open(html_file_path, 'rb') as f:
            html_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'pretend_its_wav.wav',
            'base64_encoded_file': html_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        new_files_dir_list = os.listdir(self.files_path)
        assert file_count == 4
        assert resp['errors'] == "The file extension does not match the file's true type (audio/x-wav vs. text/html, respectively)."
        assert files_dir_list == new_files_dir_list

        ###################################################################
        # multipart/form-data file creation
        ###################################################################

        # Upload a file using the multipart/form-data Content-Type and a
        # POST request to /files. Here we do not supply a filename POST
        # param so the files controller creates one based on the path
        # automatically included in filedata. The controller removes the
        # path separators of its os when it creates the filename; however
        # path separators from a foreign os may remain in the generated
        # filename.
        params = self.file_create_params_MPFD.copy()
        response = self.app.post(
            url('create'), params, extra_environ=self.extra_environ_admin,
            upload_files=[('filedata', wav_file_path)])
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert resp['filename'] in os.listdir(self.files_path)
        assert resp['filename'][:8] == 'old_test'
        assert resp['name'] == resp['filename']     # name value set in files controller, user can't change this
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 5
        assert response.content_type == 'application/json'

        # Upload a file using the multipart/form-data Content-Type and a POST
        # request to /files.  Here we do supply a filename and some metadata.
        params = self.file_create_params_MPFD.copy()
        params.update({
            'filename': 'wavfile.wav',
            'description': 'multipart/form-data',
            'date_elicited': '12/03/2011',    # mm/dd/yyyy
            'utterance_type': 'Mixed Utterance',
            'tags-0': tag1_id,
            'tags-1': tag2_id,
            'forms-0': form_id
        })
        response = self.app.post(url('create'), params, extra_environ=self.extra_environ_admin,
                                upload_files=[('filedata', wav_file_path)])
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert 'wavfile.wav' in os.listdir(self.files_path)
        assert resp['filename'] == 'wavfile.wav'
        assert resp['name'] == resp['filename']     # name value set in files controller, user can't change this
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert sorted([t['id'] for t in resp['tags']]) == sorted([tag1_id, tag2_id])
        assert resp['forms'][0]['id'] == form_id
        assert resp['utterance_type'] == 'Mixed Utterance'
        assert resp['description'] == 'multipart/form-data'
        assert resp['date_elicited'] == '2011-12-03'
        assert file_count == 6
        assert response.content_type == 'application/json'

        # Upload using multipart/form-data and attempt to pass a malicious
        # filename; the path separator should be removed from the filename.  If
        # the separator were not removed, this filename could cause the file to
        # be written to the parent directory of the files directory
        params = self.file_create_params_MPFD.copy()
        params.update({'filename': '../wavfile.wav'})
        response = self.app.post(url('create'), params, extra_environ=self.extra_environ_admin,
            upload_files=[('filedata', wav_file_path)])
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        binary_files_list = os.listdir(self.files_path)
        binary_files_list_count = len(binary_files_list)
        assert '..wavfile.wav' in binary_files_list
        assert resp['filename'] == '..wavfile.wav'
        assert resp['name'] == resp['filename']     # name value set in files controller, user can't change this
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 7
        assert response.content_type == 'application/json'

        # Upload using multipart/form-data and attempt to pass an invalid file
        # type (.html) but with a valid extension (.wav).  Expect an error.
        html_file_path = os.path.join(self.test_files_path, 'illicit.html')
        files_dir_list = os.listdir(self.files_path)
        params = self.file_create_params_MPFD.copy()
        params.update({'filename': 'pretend_its_wav.wav'})
        response = self.app.post(url('create'), params, extra_environ=self.extra_environ_admin,
            upload_files=[('filedata', html_file_path)], status=400)
        resp = response.json_body
        new_file_count = dbsession.query(old_models.File).count()
        new_files_dir_list = os.listdir(self.files_path)
        assert file_count == new_file_count
        assert resp['errors'] == "The file extension does not match the file's true type (audio/x-wav vs. text/html, respectively)."
        assert files_dir_list == new_files_dir_list

        # Try the same as above but instead of providing a deceitful filename in
        # the POST params, upload a file with a false extension.
        html_file_path = os.path.join(self.test_files_path, 'illicit.wav')
        files_dir_list = new_files_dir_list
        params = self.file_create_params_MPFD.copy()
        response = self.app.post(url('create'), params, extra_environ=self.extra_environ_admin,
            upload_files=[('filedata', html_file_path)], status=400)
        resp = response.json_body
        new_file_count = dbsession.query(old_models.File).count()
        new_files_dir_list = os.listdir(self.files_path)
        assert file_count == new_file_count
        assert resp['errors'] == "The file extension does not match the file's true type (audio/x-wav vs. text/html, respectively)."
        assert files_dir_list == new_files_dir_list

        ########################################################################
        # Subinterval-Referencing File
        ########################################################################

        # Create a subinterval-referencing audio file; reference one of the wav
        # files created earlier.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': a_wav_file_id,
            'name': 'subinterval_x',
            'start': 1.3,
            'end': 2.6
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        new_binary_files_list = os.listdir(self.files_path)
        new_binary_files_list_count = len(new_binary_files_list)
        subinterval_referencing_id = resp['id']
        assert new_binary_files_list_count == binary_files_list_count
        assert '\u201Cold_te\u0301st\u201D.wav' in new_binary_files_list
        assert 'subinterval_x' not in new_binary_files_list
        assert resp['filename'] is None
        assert resp['parent_file']['filename'] == '\u201Cold_te\u0301st\u201D.wav'
        assert resp['name'] == 'subinterval_x'
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] is None
        assert resp['parent_file']['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert resp['start'] == 1.3
        assert isinstance(resp['start'], float)
        assert resp['end'] == 2.6
        assert isinstance(resp['end'], float)
        assert file_count == 8
        assert response.content_type == 'application/json'

        # Attempt to create another subinterval-referencing audio file; fail
        # because name is too long, parent_file is empty, start is not a number
        # and end is unspecified
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'name': 'subinterval_x' * 200,
            'start': 'a',
            'end': None
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert file_count == 8   # unchanged
        assert resp['errors']['parent_file'] == 'An id corresponding to an existing audio or video file must be provided.'
        assert resp['errors']['start'] == 'Please enter a number'
        assert resp['errors']['end'] == 'Please enter a value'
        assert resp['errors']['name'] == 'Enter a value not more than 255 characters long'

        # Attempt to create another subinterval-referencing audio file; fail
        # because the contributor is not authorized to access the restricted parent_file.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': a_wav_file_id,
            'name': 'subinterval_y',
            'start': 3.75,
            'end': 4.999
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_contrib, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert file_count == 8
        assert resp['errors']['parent_file'] == 'You are not authorized to access the file with id %d.' % a_wav_file_id

        # Create another subinterval-referencing audio file; this one's parent is
        # restricted.  Note that it does not itself become restricted.  Note also
        # that a name is not required.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': a_wav_file_id,
            'start': 3.75,
            'end': 4.999
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert file_count == 9
        assert resp['parent_file']['id'] == a_wav_file_id
        assert 'restricted' not in [t['name'] for t in resp['tags']]
        assert resp['name'] == resp['parent_file']['name']

        # Attempt to create another subinterval-referencing file; fail because
        # the parent file is not an A/V file.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': an_image_id,
            'name': 'subinterval_y',
            'start': 3.75,
            'end': 4.999
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert file_count == 9
        assert resp['errors']['parent_file'] == 'File %d is not an audio or a video file.' % an_image_id

        # Attempt to create another subinterval-referencing file; fail because
        # the parent file id is invalid
        bad_id = 1000009252345345
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': bad_id,
            'name': 'subinterval_y',
            'start': 3.75,
            'end': 4.999
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert file_count == 9
        assert resp['errors']['parent_file'] == 'There is no file with id %d.' % bad_id

        # Attempt to create another subinterval-referencing file; fail because
        # the parent file id is itself a subinterval-referencing file
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': subinterval_referencing_id,
            'name': 'subinterval_y',
            'start': 3.75,
            'end': 4.999
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert file_count == 9
        assert resp['errors']['parent_file'] == 'The parent file cannot itself be a subinterval-referencing file.'

        # Attempt to create a subinterval-referencing audio file; fail because
        # start >= end.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': a_wav_file_id,
            'name': 'subinterval_z',
            'start': 1.3,
            'end': 1.3
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert response.content_type == 'application/json'
        assert resp['errors'] == 'The start value must be less than the end value.'

        ########################################################################
        # externally hosted file creation
        ########################################################################

        # Create a valid externally hosted file
        params = self.file_create_params_ext_host.copy()
        url_ = 'http://vimeo.com/54144270'
        params.update({
            'url': url_,
            'name': 'externally hosted file',
            'MIME_type': 'video/mpeg',
            'description': 'A large video file I didn\'t want to upload here.'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['description'] == 'A large video file I didn\'t want to upload here.'
        assert resp['url'] == url_

        # Attempt to create an externally hosted file with invalid params
        params = self.file_create_params_ext_host.copy()
        url_ = 'http://vimeo/541442705414427054144270541442705414427054144270'  # Invalid url
        params.update({
            'url': url_,
            'name': 'invalid externally hosted file',
            'MIME_type': 'video/gepm',      # invalid MIME_type
            'description': 'A large video file, sadly invalid.'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['MIME_type'] == 'The file upload failed because the file type video/gepm is not allowed.'
        # WARNING: wasn't an assertion in Pylons OLD ...
        assert (resp['errors']['url'] == 'You must provide a full domain'
                ' name (like vimeo.com)')

        # Attempt to create an externally hosted file with different invalid params
        params = self.file_create_params_ext_host.copy()
        params.update({
            'url': '',   # shouldn't be empty
            'name': 'invalid externally hosted file' * 200,    # too long
            'password': 'a87XS.1d9X837a001W2w3a87XS.1d9X837a001W2w3' * 200,    # too long
            'description': 'A large video file, sadly invalid.'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['url'] == 'Please enter a value'
        assert resp['errors']['password'] == 'Enter a value not more than 255 characters long'
        assert resp['errors']['name'] ==  'Enter a value not more than 255 characters long'

        # Show that the name param is optional
        params = self.file_create_params_ext_host.copy()
        url_ = 'http://vimeo.com/54144270'
        params.update({
            'url': url_,
            'MIME_type': 'video/mpeg',
            'description': 'A large video file I didn\'t want to upload here.'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == ''

    def test_relational_restrictions(self):
        """Tests that the restricted tag works correctly with respect to
        relational attributes of files.

        That is, tests that (a) file.forms does not return restricted forms to
        restricted users and (b) a restricted user cannot append a restricted
        form to file.forms."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        admin = self.extra_environ_admin.copy()
        contrib = self.extra_environ_contrib.copy()

        # Create a test audio file.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        wav_file_size = os.path.getsize(wav_file_path)
        params = self.file_create_params_base64.copy()
        with open(wav_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'old_test.wav',
            'base64_encoded_file': base64_encoded_file
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert resp['filename'] == 'old_test.wav'
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 1
        assert response.content_type == 'application/json'

        # First create the restricted tag.
        restricted_tag = omb.generate_restricted_tag()
        dbsession.add(restricted_tag)
        dbsession.flush()
        restricted_tag_id = restricted_tag.id
        dbsession.commit()

        # Then create two forms, one restricted and one not.
        params = self.form_create_params.copy()
        params.update({
            'transcription': 'restricted',
            'translations': [{'transcription': 'restricted', 'grammaticality': ''}],
            'tags': [restricted_tag_id]
        })
        params = json.dumps(params)
        response = self.app.post(forms_url('create'), params, self.json_headers,
                                admin)
        resp = response.json_body
        restricted_form_id = resp['id']

        params = self.form_create_params.copy()
        params.update({
            'transcription': 'unrestricted',
            'translations': [{'transcription': 'unrestricted', 'grammaticality': ''}]
        })
        params = json.dumps(params)
        response = self.app.post(forms_url('create'), params, self.json_headers,
                                admin)
        resp = response.json_body
        unrestricted_form_id = resp['id']

        # Now, as a (restricted) contributor, attempt to create a file and
        # associate it to a restricted form -- expect to fail.
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        jpg_file_size = os.path.getsize(jpg_file_path)
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64,
            'forms': [restricted_form_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                contrib, status=400)
        resp = response.json_body
        assert 'You are not authorized to access the form with id %d.' % restricted_form_id in \
            resp['errors']['forms']

        # Now, as a (restricted) contributor, attempt to create a file and
        # associate it to an unrestricted form -- expect to succeed.
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        jpg_file_size = os.path.getsize(jpg_file_path)
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64,
            'forms': [unrestricted_form_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                contrib)
        resp = response.json_body
        unrestricted_file_id = resp['id']
        assert resp['filename'] == 'old_test.jpg'
        assert resp['forms'][0]['transcription'] == 'unrestricted'

        # Now, as a(n unrestricted) administrator, attempt to create a file and
        # associate it to a restricted form -- expect (a) to succeed and (b) to
        # find that the file is now restricted.
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64,
            'forms': [restricted_form_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, admin)
        resp = response.json_body
        indirectly_restricted_file_id = resp['id']
        assert resp['filename'][:8] == 'old_test'
        assert resp['forms'][0]['transcription'] == 'restricted'
        assert 'restricted' in [t['name'] for t in resp['tags']]

        # Now show that the indirectly restricted files are inaccessible to
        # unrestricted users.
        response = self.app.get(url('index'), headers=self.json_headers,
                                extra_environ=contrib)
        resp = response.json_body
        assert indirectly_restricted_file_id not in [f['id'] for f in resp]

        # Now, as a(n unrestricted) administrator, create a file.
        unrestricted_file_params = self.file_create_params_base64.copy()
        unrestricted_file_params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64
        })
        params = json.dumps(unrestricted_file_params)
        response = self.app.post(url('create'), params, self.json_headers, admin)
        resp = response.json_body
        unrestricted_file_id = resp['id']
        assert resp['filename'][:8] == 'old_test'
        assert response.content_type == 'application/json'

        # As a restricted contributor, attempt to update the unrestricted file
        # just created by associating it to a restricted form -- expect to fail.
        unrestricted_file_params.update({'forms': [restricted_form_id]})
        params = json.dumps(unrestricted_file_params)
        response = self.app.put(url('update', id=unrestricted_file_id), params,
                                self.json_headers, contrib, status=400)
        resp = response.json_body
        assert 'You are not authorized to access the form with id %d.' % restricted_form_id in \
            resp['errors']['forms']
        assert response.content_type == 'application/json'

        # As an unrestricted administrator, attempt to update an unrestricted file
        # by associating it to a restricted form -- expect to succeed.
        response = self.app.put(url('update', id=unrestricted_file_id), params,
                                self.json_headers, admin)
        resp = response.json_body
        assert resp['id'] == unrestricted_file_id
        assert 'restricted' in [t['name'] for t in resp['tags']]

        # Now show that the newly indirectly restricted file is also
        # inaccessible to an unrestricted user.
        response = self.app.get(url('show', id=unrestricted_file_id),
                headers=self.json_headers, extra_environ=contrib, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

    def test_create_large(self):
        """Tests that POST /files correctly creates a large file.

        WARNING 1: long-running test.

        WARNING: 2: if a large file named old_test_long.wav does not exist in
        ``tests/data/files``, this test will pass vacuously.  I don't want to
        include such a large file in the code base so this file needs to be
        created if one wants this test to run.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        file_count = new_file_count = dbsession.query(
            old_models.File).count()

        # Try to create a file with a > 20 MB file as content using
        # JSON/Base64 encoding and expect to fail because the file is too
        # big.
        long_wav_filename = 'old_test_long.wav'
        long_wav_file_path = os.path.join(
            self.test_files_path, long_wav_filename)
        if os.path.exists(long_wav_file_path):
            long_wav_file_size = os.path.getsize(long_wav_file_path)
            params = self.file_create_params_base64.copy()
            with open(long_wav_file_path, 'rb') as f:
                base64_encoded_file = b64encode(f.read()).decode('utf8')
            params.update({
                'filename': long_wav_filename,
                'base64_encoded_file': base64_encoded_file
            })
            params = json.dumps(params)
            response = self.app.post(
                url('create'), params, self.json_headers,
                self.extra_environ_admin, status=400)
            resp = response.json_body
            new_file_count = dbsession.query(old_models.File).count()
            assert file_count == new_file_count
            assert (resp['error'] == 'The request body is too large; use'
                    ' the multipart/form-data Content-Type when uploading'
                    ' files greater than 20MB.')
            assert response.content_type == 'application/json'

        # Try to create a file with a ~6MB .wav file as content using
        # JSON/Base64 encoding and expect to succeed because the file is <
        # 20MB.
        medium_wav_filename = 'old_test_medium.wav'
        medium_wav_file_path = os.path.join(
            self.test_files_path, medium_wav_filename)
        if os.path.exists(medium_wav_file_path):
            old_reduced_dir_list = os.listdir(self.reduced_files_path)
            medium_wav_file_size = os.path.getsize(medium_wav_file_path)
            params = self.file_create_params_base64.copy()
            with open(medium_wav_file_path, 'rb') as f:
                base64_encoded_file = b64encode(f.read()).decode('utf8')
            params.update({
                'filename': medium_wav_filename,
                'base64_encoded_file': base64_encoded_file
            })
            params = json.dumps(params)
            response = self.app.post(
                url('create'), params, self.json_headers,
                self.extra_environ_admin)
            resp = response.json_body
            file_count = new_file_count
            new_file_count = dbsession.query(old_models.File).count()
            new_reduced_dir_list = os.listdir(self.reduced_files_path)
            lossy_filename = '%s.%s' % (
                os.path.splitext(medium_wav_filename)[0],
                self.config.get('preferred_lossy_audio_format', 'ogg'))
            assert file_count + 1 == new_file_count
            assert resp['filename'] == medium_wav_filename
            assert resp['MIME_type'] == 'audio/x-wav'
            assert resp['size'] == medium_wav_file_size
            assert resp['enterer']['first_name'] == 'Admin'
            assert response.content_type == 'application/json'
            assert lossy_filename not in old_reduced_dir_list
            if (    self.create_reduced_size_file_copies and
                    h.command_line_program_installed('ffmpeg')):
                assert resp['lossy_filename'] == lossy_filename
                assert lossy_filename in new_reduced_dir_list
            else:
                assert resp['lossy_filename'] is None
                assert lossy_filename not in new_reduced_dir_list

        # Create the large (> 20MB) .wav file from above using the
        # multipart/form-data POST method.
        if os.path.exists(long_wav_file_path):
            long_wav_file_size = os.path.getsize(long_wav_file_path)
            params = self.file_create_params_MPFD.copy()
            params.update({'filename': long_wav_filename})
            response = self.app.post(
                url('create'), params,
                extra_environ=self.extra_environ_admin,
                upload_files=[('filedata', long_wav_file_path)])
            resp = response.json_body
            file_count = new_file_count
            new_file_count = dbsession.query(old_models.File).count()
            new_reduced_dir_list = os.listdir(self.reduced_files_path)
            lossy_filename = '%s.%s' % (
                os.path.splitext(long_wav_filename)[0],
                self.config.get('preferred_lossy_audio_format', 'ogg'))
            assert file_count + 1 == new_file_count
            assert resp['filename'] == long_wav_filename
            assert resp['MIME_type'] == 'audio/x-wav'
            assert resp['size'] == long_wav_file_size
            assert resp['enterer']['first_name'] == 'Admin'
            assert response.content_type == 'application/json'
            assert lossy_filename not in old_reduced_dir_list
            if (    self.create_reduced_size_file_copies and
                    h.command_line_program_installed('ffmpeg')):
                assert resp['lossy_filename'] == lossy_filename
                assert lossy_filename in new_reduced_dir_list
            else:
                assert resp['lossy_filename'] is None
                assert lossy_filename not in new_reduced_dir_list

    def test_new(self):
        """Tests that GET /file/new returns an appropriate JSON object for creating a new OLD file.

        The properties of the JSON object are 'tags', 'utterance_types',
        'speakers'and 'users' and their values are arrays/lists.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Unauthorized user ('viewer') should return a 403 status code on the
        # new action, which requires a 'contributor' or an 'administrator'.
        extra_environ = {'test.authentication.role': 'viewer'}
        response = self.app.get(url('new'), extra_environ=extra_environ,
                                status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Add some test data to the database.
        application_settings = omb.generate_default_application_settings()
        restricted_tag = omb.generate_restricted_tag()
        speaker = omb.generate_default_speaker()
        dbsession.add_all([application_settings, restricted_tag, speaker])
        dbsession.commit()

        # Get the data currently in the db (see websetup.py for the test data).
        data = {
            'tags': db.get_mini_dicts_getter('Tag')(),
            'speakers': db.get_mini_dicts_getter('Speaker')(),
            'users': db.get_mini_dicts_getter('User')(),
            'utterance_types': oldc.UTTERANCE_TYPES,
            'allowed_file_types': oldc.ALLOWED_FILE_TYPES
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        # GET /file/new without params.  Without any GET params, /file/new
        # should return a JSON array for every store.
        response = self.app.get(url('new'),
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['tags'] == data['tags']
        assert resp['speakers'] == data['speakers']
        assert resp['users'] == data['users']
        assert resp['utterance_types'] == data['utterance_types']
        assert resp['allowed_file_types'] == data['allowed_file_types']
        assert response.content_type == 'application/json'

        # GET /new_file with params.  Param values are treated as strings, not
        # JSON.  If any params are specified, the default is to return a JSON
        # array corresponding to store for the param.  There are three cases
        # that will result in an empty JSON array being returned:
        # 1. the param is not specified
        # 2. the value of the specified param is an empty string
        # 3. the value of the specified param is an ISO 8601 UTC datetime
        #    string that matches the most recent datetime_modified value of the
        #    store in question.
        params = {
            # Value is any string: 'speakers' will be in response.
            'speakers': 'anything can go here!',
            # Value is ISO 8601 UTC datetime string that does not match the most
            # recent User.datetime_modified value: 'users' *will* be in
            # response.
            'users': datetime.datetime.utcnow().isoformat(),
            # Value is ISO 8601 UTC datetime string that does match the most
            # recent Tag.datetime_modified value: 'tags' will *not* be in response.
            'tags': db.get_most_recent_modification_datetime('Tag').isoformat()
        }
        response = self.app.get(url('new'), params,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['tags'] == []
        assert resp['speakers'] == data['speakers']
        assert resp['users'] == data['users']
        assert resp['utterance_types'] == data['utterance_types']
        assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /files/id correctly updates an existing file."""

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        file_count = dbsession.query(old_models.File).count()

        # Add the default application settings and the restricted tag.
        restricted_tag = omb.generate_restricted_tag()
        application_settings = omb.generate_default_application_settings()
        dbsession.add_all([application_settings, restricted_tag])
        dbsession.commit()
        restricted_tag = db.get_restricted_tag()
        restricted_tag_id = restricted_tag.id

        # Create a file to update.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        wav_file_size = os.path.getsize(wav_file_path)
        params = self.file_create_params_base64.copy()

        original_name = 'test_update_name.wav'
        with open(wav_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': original_name,
            'tags': [restricted_tag.id],
            'description': 'description',
            'base64_encoded_file': base64_encoded_file
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        id_ = int(resp['id'])
        new_file_count = dbsession.query(old_models.File).count()
        assert resp['filename'] == original_name
        assert new_file_count == file_count + 1

        # As a viewer, attempt to update the restricted file we just created.
        # Expect to fail.
        extra_environ = {'test.authentication.role': 'viewer'}
        params = self.file_create_params_base64.copy()
        params.update({
            'description': 'A file that has been updated.',
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=id_), params,
            self.json_headers, extra_environ, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # As an administrator now, update the file just created and expect to
        # succeed.
        params = self.file_create_params_base64.copy()
        params.update({
            'description': 'A file that has been updated.'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=id_), params,
                                self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        new_file_count = dbsession.query(old_models.File).count()
        assert resp['description'] == 'A file that has been updated.'
        assert resp['tags'] == []
        assert new_file_count == file_count + 1
        assert response.content_type == 'application/json'

        # Attempt an update with no new data.  Expect a 400 error
        # and response['errors'] = {'no change': The update request failed
        # because the submitted data were not new.'}.
        response = self.app.put(url('update', id=id_), params, self.json_headers,
                                self.extra_environ_admin, status=400)
        resp = response.json_body
        assert 'the submitted data were not new' in resp['error']

        # Add a speaker and some tags to the db.
        speaker = omb.generate_default_speaker()
        tag1 = old_models.Tag()
        tag1.name = 'tag 1'
        tag2 = old_models.Tag()
        tag2.name = 'tag 2'
        dbsession.add_all([speaker, tag1, tag2])
        dbsession.flush()
        tag1_id = tag1.id
        tag2_id = tag2.id
        dbsession.commit()
        speaker = db.get_speakers()[0]
        speaker_id = speaker.id

        # Now update our file by adding a many-to-one datum, viz. a speaker
        params = self.file_create_params_base64.copy()
        params.update({'speaker': speaker.id})
        params = json.dumps(params)
        response = self.app.put(url('update', id=id_), params, self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['speaker']['first_name'] == speaker.first_name

        # Finally, update the file by adding some many-to-many data, i.e., tags
        params = self.file_create_params_base64.copy()
        params.update({'tags': [tag1_id, tag2_id]})
        params = json.dumps(params)
        response = self.app.put(url('update', id=id_), params, self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert sorted([t['name'] for t in resp['tags']]) == ['tag 1', 'tag 2']

        ########################################################################
        # Updating "Plain Files"
        ########################################################################

        # Create a file using the multipart/form-data POST method.
        params = self.file_create_params_MPFD.copy()
        params.update({'filename': 'multipart.wav'})
        response = self.app.post(url('create'), params, extra_environ=self.extra_environ_admin,
                                upload_files=[('filedata', wav_file_path)])
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        plain_file_id = resp['id']
        assert resp['filename'] == 'multipart.wav'
        assert resp['filename'] in os.listdir(self.files_path)
        assert resp['name'] == resp['filename']     # name value set in files controller, user can't change this
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['enterer']['first_name'] == 'Admin'
        assert response.content_type == 'application/json'

        # Update the plain file by adding some metadata.
        params = self.file_create_params_base64.copy()
        params.update({
            'tags': [tag1_id, tag2_id],
            'description': 'plain updated',
            'date_elicited': '01/01/2000',
            'speaker': speaker_id,
            'utterance_type': 'Metalanguage Utterance'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=plain_file_id), params, self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert sorted([t['name'] for t in resp['tags']]) == ['tag 1', 'tag 2']
        assert resp['description'] == 'plain updated'
        assert resp['speaker']['id'] == speaker_id
        assert resp['filename'] == resp['name'] == 'multipart.wav'
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['enterer']['first_name'] == 'Admin'
        assert response.content_type == 'application/json'

        ########################################################################
        # Update a subinterval-referencing file
        ########################################################################

        # Create a subinterval-referencing audio file; reference one of the wav
        # files created earlier.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': plain_file_id,
            'name': 'anyname',
            'start': 13.3,
            'end': 26.89,
            'tags': [tag1_id],
            'description': 'subinterval-referencing file',
            'date_elicited': '01/01/2000',
            'speaker': speaker_id,
            'utterance_type': 'Object Language Utterance'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_contrib)
        resp = response.json_body
        subinterval_referencing_id = resp['id']
        assert resp['filename'] is None
        assert resp['name'] == 'anyname'
        assert resp['parent_file']['filename'] == 'multipart.wav'
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] is None
        assert resp['parent_file']['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Contributor'
        assert resp['start'] == 13.3
        assert isinstance(resp['start'], float)
        assert resp['end'] == 26.89
        assert isinstance(resp['end'], float)
        assert resp['tags'][0]['id'] == tag1_id
        assert response.content_type == 'application/json'

        # Update the subinterval-referencing file.
        params = self.file_create_params_base64.copy()
        params.update({
            'parent_file': plain_file_id,
            'start': 13.3,
            'end': 26.89,
            'tags': [],
            'description': 'abc to def',
            'date_elicited': '01/01/2010',
            'utterance_type': 'Metalanguage Utterance'
        })
        params = json.dumps(params)
        response = self.app.put(
            url('update', id=subinterval_referencing_id), params,
            self.json_headers, extra_environ=self.extra_environ_contrib)
        resp = response.json_body
        assert resp['parent_file']['id'] == plain_file_id
        assert resp['name'] == resp['parent_file']['name']
        assert resp['tags'] == []
        assert resp['description'] == 'abc to def'
        assert resp['speaker'] is None
        assert resp['MIME_type'] == 'audio/x-wav'
        assert response.content_type == 'application/json'

        # Attempt a vacuous update and expect an error message.
        response = self.app.put(
            url('update', id=subinterval_referencing_id), params,
            self.json_headers, extra_environ=self.extra_environ_contrib,
            status=400)
        resp = response.json_body
        assert resp['error'] == 'The update request failed because the submitted data were not new.'

        # Now restrict the parent file and verify that the child file does not
        # thereby become restricted.  This means that the metadata of a restricted
        # parent file may accessible to restricted users via the child file;
        # however, this is ok since the serve action still will not allow
        # the contents of the restricted file to be served to the restricted users.
        params = self.file_create_params_base64.copy()
        params.update({
            'tags': [tag1_id, tag2_id, restricted_tag_id],
            'description': 'plain updated',
            'date_elicited': '01/01/2000',
            'speaker': speaker_id,
            'utterance_type': 'Metalanguage Utterance'
        })
        params = json.dumps(params)
        response = self.app.put(url('update', id=plain_file_id), params,
                    self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert 'restricted' in [t['name'] for t in resp['tags']]

        SRFile = dbsession.query(old_models.File).get(subinterval_referencing_id)
        assert 'restricted' not in [t.name for t in SRFile.tags]

        ########################################################################
        # externally hosted file creation
        ########################################################################

        # Create a valid externally hosted file
        url_ = 'http://vimeo.com/54144270'
        params = self.file_create_params_ext_host.copy()
        params.update({
            'url': url_,
            'name': 'externally hosted file',
            'MIME_type': 'video/mpeg',
            'description': 'A large video file I didn\'t want to upload here.'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['description'] == 'A large video file I didn\'t want to upload here.'
        assert resp['url'] == url_

        # Update the externally hosted file
        params = self.file_create_params_ext_host.copy()
        params.update({
            'url': url_,
            'name': 'externally hosted file',
            'password': 'abc',
            'MIME_type': 'video/mpeg',
            'description': 'A large video file I didn\'t want to upload here.',
            'date_elicited': '12/29/1987'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        assert resp['date_elicited'] == '1987-12-29'
        assert resp['password'] == 'abc'

        # Attempt to update the externally hosted file with invalid params.
        params = self.file_create_params_ext_host.copy()
        params.update({
            'url': 'abc',      # Invalid
            'name': 'externally hosted file' * 200,    # too long
            'MIME_type': 'zooboomafoo',                 # invalid
            'description': 'A large video file I didn\'t want to upload here.',
            'date_elicited': '1987/12/29'               # wrong format
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin, status=400)
        resp = response.json_body
        assert resp['errors']['MIME_type'] == 'The file upload failed because the file type zooboomafoo is not allowed.'
        assert resp['errors']['url'] == 'You must provide a full domain name (like abc.com)'
        assert resp['errors']['name'] == 'Enter a value not more than 255 characters long'
        assert resp['errors']['date_elicited'] == 'Please enter the date in the form MM/DD/YYYY'

    def test_delete(self):
        """Tests that DELETE /files/id deletes the file with id=id and returns a JSON representation.

        If the id is invalid or unspecified, then JSON null or a 404 status code
        are returned, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add some objects to the db: a default application settings, a speaker
        # and a tag.
        application_settings = omb.generate_default_application_settings()
        speaker = omb.generate_default_speaker()
        my_contributor = omb.generate_default_user()
        my_contributor.username = 'uniqueusername'
        tag = old_models.Tag()
        tag.name = 'default tag'
        dbsession.add_all([application_settings, speaker, my_contributor, tag])
        dbsession.flush()
        tag_id = tag.id
        speaker_id = speaker.id
        dbsession.commit()
        my_contributor = dbsession.query(old_models.User).filter(
            old_models.User.username=='uniqueusername').first()
        my_contributor_id = my_contributor.id

        # Count the original number of files
        file_count = dbsession.query(old_models.File).count()

        # First, as my_contributor, create a file to delete.
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        extra_environ = {'test.authentication.id': my_contributor_id}
        params = self.file_create_params_base64.copy()
        with open(jpg_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'test_delete.jpg',
            'base64_encoded_file': base64_encoded_file,
            'speaker': speaker_id,
            'tags': [tag_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                extra_environ)
        resp = response.json_body
        to_delete_id = resp['id']
        to_delete_name = resp['filename']
        assert resp['filename'] == 'test_delete.jpg'
        assert resp['tags'][0]['name'] == 'default tag'

        # Now count the files
        new_file_count = dbsession.query(old_models.File).count()
        assert new_file_count == file_count + 1

        # Now, as the default contributor, attempt to delete the my_contributor-
        # entered file we just created and expect to fail.
        extra_environ = {'test.authentication.role': 'contributor'}
        response = self.app.delete(url('delete', id=to_delete_id),
                                extra_environ=extra_environ, status=403)
        resp = response.json_body
        file_that_was_not_deleted = dbsession.query(old_models.File).get(to_delete_id)
        file_path = os.path.join(self.files_path, to_delete_name)
        assert os.path.exists(file_path)
        assert file_that_was_not_deleted is not None
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # As my_contributor, attempt to delete the file we just created and
        # expect to succeed.
        extra_environ = {'test.authentication.id': my_contributor_id}
        response = self.app.delete(url('delete', id=to_delete_id),
                                extra_environ=extra_environ)
        resp = response.json_body
        new_file_count = dbsession.query(old_models.File).count()
        tag_of_deleted_file = dbsession.query(old_models.Tag).get(
            resp['tags'][0]['id'])
        speaker_of_deleted_file = dbsession.query(old_models.Speaker).get(
            resp['speaker']['id'])
        assert isinstance(tag_of_deleted_file, old_models.Tag)
        assert isinstance(speaker_of_deleted_file, old_models.Speaker)
        assert new_file_count == file_count

        # The deleted file will be returned to us, so the assertions from
        # above should still hold true.
        file_that_was_deleted = dbsession.query(
            old_models.File).get(to_delete_id)
        file_path = os.path.join(self.files_path, to_delete_name)

        assert not os.path.exists(file_path), '{} does exist'.format(file_path)
        assert 'old_test.jpg' not in os.listdir(self.files_path)
        assert file_that_was_deleted is None
        assert resp['filename'] == 'test_delete.jpg'

        # Delete with an invalid id
        id_ = 9999999999999
        response = self.app.delete(url('delete', id=id_),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no file with id %s' % id_ in response.json_body['error']
        assert response.content_type == 'application/json'

        # Delete without an id
        response = self.app.delete(url('delete', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Create and delete a file with unicode characters in the file name
        extra_environ = {'test.authentication.id': my_contributor_id}
        params = self.file_create_params_base64.copy()
        with open(jpg_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': '\u201Cte\u0301st delete\u201D.jpg',
            'base64_encoded_file': base64_encoded_file,
            'speaker': speaker_id,
            'tags': [tag_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, extra_environ)
        resp = response.json_body
        to_delete_id = resp['id']
        to_delete_name = resp['filename']
        assert resp['filename'] == '\u201Cte\u0301st_delete\u201D.jpg'
        assert resp['tags'][0]['name'] == 'default tag'
        assert '\u201Cte\u0301st_delete\u201D.jpg' in os.listdir(self.files_path)
        response = self.app.delete(url('delete', id=to_delete_id), extra_environ=extra_environ)
        resp = response.json_body
        assert '\u201Cte\u0301st_delete\u201D.jpg' not in os.listdir(self.files_path)

        # Create a file, create a subinterval-referencing file that references
        # it and then delete the parent file.  Show that the child files become
        # "orphaned" but are not deleted.  Use case: user has uploaded an incorrect
        # parent file; must delete parent file, create a new one and then update
        # child files' parent_file attribute.

        # Create the parent WAV file.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        params = self.file_create_params_base64.copy()
        with open(wav_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'parent.wav',
            'base64_encoded_file': base64_encoded_file
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        parent_id = resp['id']
        parent_filename = resp['filename']
        parent_lossy_filename = resp['lossy_filename']

        # Create a subinterval-referencing audio file; reference one of the wav
        # files created earlier.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': parent_id,
            'name': 'child',
            'start': 1,
            'end': 2,
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, self.extra_environ_admin)
        resp = response.json_body
        child_id = resp['id']
        assert resp['parent_file']['id'] == parent_id

        # Show that the child file still exists after the parent has been deleted.
        assert parent_filename in os.listdir(self.files_path)
        if self.create_reduced_size_file_copies and h.command_line_program_installed('ffmpeg'):
            assert parent_lossy_filename in os.listdir(self.reduced_files_path)
        response = self.app.delete(url('delete', id=parent_id), extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert parent_filename not in os.listdir(self.files_path)
        assert parent_lossy_filename not in os.listdir(self.reduced_files_path)
        assert resp['filename'] == 'parent.wav'

        parent = dbsession.query(old_models.File).get(parent_id)
        assert parent is None

        child = dbsession.query(old_models.File).get(child_id)
        assert child is not None
        assert child.parent_file is None

        # Delete the child file
        response = self.app.delete(url('delete', id=child_id), extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['name'] == 'child'

    def test_show(self):
        """Tests that GET /files/id returns a JSON file object, null or 404
        depending on whether the id is valid, invalid or unspecified,
        respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # First create a test image file.
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        jpg_file_size = os.path.getsize(jpg_file_path)
        params = self.file_create_params_base64.copy()
        with open(jpg_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': base64_encoded_file
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        file_id = resp['id']
        assert resp['filename'] == 'old_test.jpg'
        assert resp['MIME_type'] == 'image/jpeg'
        assert resp['size'] == jpg_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert file_count == 1

        # Then create a form associated to the image file just created and make sure
        # we can access the form via the file.forms backreference.
        params = self.form_create_params.copy()
        params.update({
            'transcription': 'test',
            'translations': [{'transcription': 'test', 'grammaticality': ''}],
            'files': [file_id]
        })
        params = json.dumps(params)
        response = self.app.post(forms_url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        assert isinstance(resp, dict)
        assert resp['transcription'] == 'test'
        assert resp['translations'][0]['transcription'] == 'test'
        assert resp['morpheme_break_ids'] is None
        assert resp['enterer']['first_name'] == 'Admin'
        assert resp['files'][0]['filename'] == 'old_test.jpg'

        # GET the image file and make sure we see the associated form.
        response = self.app.get(url('show', id=file_id), headers=self.json_headers,
                                extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['forms'][0]['transcription'] == 'test'
        assert resp['filename'] == 'old_test.jpg'
        assert response.content_type == 'application/json'

        # Invalid id
        id = 100000000000
        response = self.app.get(url('show', id=id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        resp = response.json_body
        assert 'There is no file with id %s' % id in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('show', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Now test that the restricted tag is working correctly.
        # First get the default contributor's id.
        users = db.get_users()
        contributor_id = [u for u in users if u.role == 'contributor'][0].id

        # Then add another contributor and a restricted tag.
        restricted_tag = omb.generate_restricted_tag()
        my_contributor = omb.generate_default_user()
        my_contributor_first_name = 'Mycontributor'
        my_contributor.first_name = my_contributor_first_name
        my_contributor.username = 'uniqueusername'
        dbsession.add_all([restricted_tag, my_contributor])
        dbsession.commit()
        my_contributor = dbsession.query(old_models.User).filter(
            old_models.User.first_name == my_contributor_first_name).first()
        my_contributor_id = my_contributor.id

        # Then add the default application settings with my_contributor as the
        # only unrestricted user.
        application_settings = omb.generate_default_application_settings()
        application_settings.unrestricted_users = [my_contributor]
        dbsession.add(application_settings)
        dbsession.commit()

        # Finally, issue a POST request to create the restricted file with
        # the *default* contributor as the enterer.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        extra_environ = {'test.authentication.id': contributor_id}
        params = self.file_create_params_base64.copy()
        with open(wav_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'old_test.wav',
            'base64_encoded_file': base64_encoded_file,
            'tags': [db.get_tags()[0].id]    # the restricted tag should be the only one
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                        extra_environ)
        resp = response.json_body
        restricted_file_id = resp['id']
        # Expectation: the administrator, the default contributor (qua enterer)
        # and the unrestricted my_contributor should all be able to view the file.
        # The viewer should get a 403 error when attempting to view this file.
        # An administrator should be able to view this file.
        extra_environ = {'test.authentication.role': 'administrator'}
        response = self.app.get(url('show', id=restricted_file_id),
                        headers=self.json_headers, extra_environ=extra_environ)
        # The default contributor (qua enterer) should be able to view this file.
        extra_environ = {'test.authentication.id': contributor_id}
        response = self.app.get(url('show', id=restricted_file_id),
                        headers=self.json_headers, extra_environ=extra_environ)
        # Mycontributor (an unrestricted user) should be able to view this
        # restricted file.
        extra_environ = {'test.authentication.id': my_contributor_id}
        response = self.app.get(url('show', id=restricted_file_id),
                        headers=self.json_headers, extra_environ=extra_environ)
        # A (not unrestricted) viewer should *not* be able to view this file.
        extra_environ = {'test.authentication.role': 'viewer'}
        response = self.app.get(url('show', id=restricted_file_id),
            headers=self.json_headers, extra_environ=extra_environ, status=403)
        # Remove Mycontributor from the unrestricted users list and access will be denied.
        application_settings = db.current_app_set
        application_settings.unrestricted_users = []
        dbsession.add(application_settings)
        dbsession.commit()
        # Mycontributor (no longer an unrestricted user) should now *not* be
        # able to view this restricted file.
        extra_environ = {'test.authentication.id': my_contributor_id}
        response = self.app.get(url('show', id=restricted_file_id),
            headers=self.json_headers, extra_environ=extra_environ, status=403)
        # Remove the restricted tag from the file and the viewer should now be
        # able to view it too.
        restricted_file = dbsession.query(old_models.File).get(restricted_file_id)
        restricted_file.tags = []
        dbsession.add(restricted_file)
        dbsession.commit()
        extra_environ = {'test.authentication.role': 'viewer'}
        response = self.app.get(url('show', id=restricted_file_id),
                        headers=self.json_headers, extra_environ=extra_environ)
        assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /files/id/edit returns a JSON object of data necessary to edit the file with id=id.

        The JSON object is of the form {'file': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Add the default application settings and the restricted tag.
        application_settings = omb.generate_default_application_settings()
        restricted_tag = omb.generate_restricted_tag()
        dbsession.add_all([restricted_tag, application_settings])
        dbsession.commit()
        restricted_tag = db.get_restricted_tag()
        contributor = [u for u in db.get_users() if u.role == 'contributor'][0]
        contributor_id = contributor.id

        # Create a restricted file.
        wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
        extra_environ = {'test.authentication.id': contributor_id}
        params = self.file_create_params_base64.copy()
        with open(wav_file_path, 'rb') as f:
            base64_encoded_file = b64encode(f.read()).decode('utf8')
        params.update({
            'filename': 'old_test.wav',
            'base64_encoded_file': base64_encoded_file,
            'tags': [restricted_tag.id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                        self.extra_environ_admin)
        resp = response.json_body
        restricted_file_id = resp['id']

        # As a (not unrestricted) contributor, attempt to call edit on the
        # restricted form and expect to fail.
        extra_environ = {'test.authentication.role': 'contributor'}
        response = self.app.get(url('edit', id=restricted_file_id),
                                extra_environ=extra_environ, status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Not logged in: expect 401 Unauthorized
        response = self.app.get(url('edit', id=restricted_file_id), status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'

        # Invalid id
        id_ = 9876544
        response = self.app.get(url('edit', id=id_),
            headers=self.json_headers, extra_environ=self.extra_environ_admin,
            status=404)
        assert 'There is no file with id %s' % id_ in response.json_body['error']
        assert response.content_type == 'application/json'

        # No id
        response = self.app.get(url('edit', id=''), status=404,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        assert response.json_body['error'] == \
            'The resource could not be found.'

        # Valid id
        response = self.app.get(url('edit', id=restricted_file_id),
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['file']['filename'] == 'old_test.wav'
        assert response.content_type == 'application/json'

        # Valid id with GET params.  Param values are treated as strings, not
        # JSON.  If any params are specified, the default is to return a JSON
        # array corresponding to store for the param.  There are three cases
        # that will result in an empty JSON array being returned:
        # 1. the param is not specified
        # 2. the value of the specified param is an empty string
        # 3. the value of the specified param is an ISO 8601 UTC datetime
        #    string that matches the most recent datetime_modified value of the
        #    store in question.

        # Add some test data to the database.
        application_settings = omb.generate_default_application_settings()
        speaker = omb.generate_default_speaker()
        tag = old_models.Tag()
        tag.name = 'name'
        dbsession.add_all([application_settings, speaker, tag])
        dbsession.commit()

        # Get the data currently in the db (see websetup.py for the test data).
        data = {
            'tags': db.get_mini_dicts_getter('Tag')(),
            'speakers': db.get_mini_dicts_getter('Speaker')(),
            'users': db.get_mini_dicts_getter('User')(),
            'utterance_types': oldc.UTTERANCE_TYPES,
            'allowed_file_types': oldc.ALLOWED_FILE_TYPES
        }
        # JSON.stringify and then re-Python-ify the data.  This is what the data
        # should look like in the response to a simulated GET request.
        data = json.loads(json.dumps(data))

        params = {
            # Value is a non-empty string: 'users' will be in response.
            'users': 'give me some users!',
            # Value is empty string: 'speakers' will not be in response.
            'speakers': '',
            # Value is ISO 8601 UTC datetime string that does not match the most
            # recent Tag.datetime_modified value: 'tags' *will* be in response.
            'tags': datetime.datetime.utcnow().isoformat(),
        }
        response = self.app.get(url('edit', id=restricted_file_id), params,
            headers=self.json_headers, extra_environ=self.extra_environ_admin)
        resp = response.json_body
        assert resp['data']['tags'] == data['tags']
        assert resp['data']['speakers'] == []
        assert resp['data']['users'] == data['users']
        assert resp['data']['utterance_types'] == data['utterance_types']
        assert response.content_type == 'application/json'

        # Invalid id with GET params.  It should still return 'null'.
        params = {
            # If id were valid, this would cause a speakers array to be returned
            # also.
            'speakers': 'True',
        }
        response = self.app.get(url('edit', id=id_), params,
                            extra_environ=self.extra_environ_admin, status=404)
        assert 'There is no file with id %s' % id_ in response.json_body['error']

    def test_serve(self):
        """Tests that GET /files/id/serve returns the file with name id from
        the permanent store, i.e., from onlinelinguisticdatabase/files/.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        extra_environ_admin = {'test.authentication.role': 'administrator'}
        extra_environ_contrib = {'test.authentication.role': 'contributor'}

        # Create a restricted wav file.
        restricted_tag = omb.generate_restricted_tag()
        dbsession.add(restricted_tag)
        dbsession.flush()
        restricted_tag_id = restricted_tag.id
        dbsession.commit()
        test_files_path = self.test_files_path
        wav_filename = 'old_test.wav'
        wav_file_path = os.path.join(test_files_path, wav_filename)
        wav_file_size = os.path.getsize(wav_file_path)
        with open(wav_file_path, 'rb') as f:
            wav_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': wav_filename,
            'base64_encoded_file': wav_file_base64,
            'tags': [restricted_tag_id]
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, extra_environ_admin)
        resp = response.json_body
        wav_filename = resp['filename']
        wav_file_id = resp['id']

        # Retrieve the file data as the admin who entered it
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, wav_file_id),
            headers=self.json_headers, extra_environ=extra_environ_admin)
        response_base64 = b64encode(response.body)
        assert wav_file_base64.encode('utf8') == response_base64
        assert guess_type(wav_filename)[0] == response.headers['Content-Type']
        assert wav_file_size == int(response.headers['Content-Length'])

        # Attempt to retrieve the file without authentication and expect to
        # fail (401).
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, wav_file_id),
            headers=self.json_headers, status=401)
        resp = response.json_body
        assert resp['error'] == 'Authentication is required to access this resource.'
        assert response.content_type == 'application/json'

        # Attempt to retrieve the restricted file data as the contrib and
        # expect to fail.
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, wav_file_id),
            headers=self.json_headers, extra_environ=extra_environ_contrib,
            status=403)
        resp = response.json_body
        assert resp['error'] == 'You are not authorized to access this resource.'
        assert response.content_type == 'application/json'

        # Attempt to serve an externally hosted file and expect a 400
        # status response.

        # Create a valid externally hosted file
        params = self.file_create_params_ext_host.copy()
        url_ = 'http://vimeo.com/54144270'
        params.update({
            'url': url_,
            'name': 'externally hosted file',
            'MIME_type': 'video/mpeg',
            'description': 'A large video file I didn\'t want to upload'
                            ' here.'
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        eh_file_id = resp['id']

        # Attempt to retrieve the externally hosted file's "data" and
        # expect a 400 response.
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, eh_file_id),
            headers=self.json_headers, extra_environ=extra_environ_admin,
            status=400)
        resp = response.json_body
        assert isinstance(resp, dict)
        assert resp['error'] == 'The content of file %s is stored elsewhere at %s' % (eh_file_id, url_)
        assert response.content_type == 'application/json'

        # Request the content of a subinterval-referencing file and expect
        # to receive the file data from its parent_file

        # Create a subinterval-referencing audio file; reference the wav
        # created above.
        params = self.file_create_params_sub_ref.copy()
        params.update({
            'parent_file': wav_file_id,
            'name': 'subinterval_x',
            'start': 1.3,
            'end': 2.6
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        sr_file_id = resp['id']

        # Retrieve the parent file's file data when requesting that of the
        # child.
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, sr_file_id),
            headers=self.json_headers, extra_environ=extra_environ_admin)
        response_base64 = b64encode(response.body)
        assert wav_file_base64.encode('utf8') == response_base64
        assert guess_type(wav_filename)[0] == response.headers['Content-Type']

        # Retrieve the reduced file data of the wav file created above.
        if (    self.create_reduced_size_file_copies and
                h.command_line_program_installed('ffmpeg')):
            response = self.app.get(
                '/{}/files/{}/serve_reduced'.format(self.old_name, wav_file_id),
                headers=self.json_headers,
                extra_environ=extra_environ_admin)
            response_base64 = b64encode(response.body)
            assert len(wav_file_base64) > len(response_base64)
            assert response.content_type == guess_type('x.%s' % self.preferred_lossy_audio_format)[0]

        else:
            response = self.app.get(
                '/{}/files/{}/serve_reduced'.format(self.old_name, wav_file_id),
                headers=self.json_headers,
                extra_environ=extra_environ_admin, status=404)
            resp = response.json_body
            assert resp['error'] == 'There is no size-reduced copy of file %s' % wav_file_id
            assert response.content_type == 'application/json'

        # Retrieve the reduced file of the wav-subinterval-referencing file above
        if self.create_reduced_size_file_copies and h.command_line_program_installed('ffmpeg'):
            response = self.app.get(
                '/{}/files/{}/serve_reduced'.format(self.old_name, sr_file_id),
                headers=self.json_headers,
                extra_environ=extra_environ_admin)

            sr_response_base64 = b64encode(response.body)
            assert len(wav_file_base64) > len(sr_response_base64)
            assert sr_response_base64 == response_base64
            assert response.content_type == guess_type('x.%s' % self.preferred_lossy_audio_format)[0]
        else:
            response = self.app.get(
                '/{}/files/{}/serve_reduced'.format(self.old_name, sr_file_id),
                headers=self.json_headers,
                extra_environ=extra_environ_admin, status=404)
            resp = response.json_body
            assert resp['error'] == 'There is no size-reduced copy of file %s' % sr_file_id
            assert response.content_type == 'application/json'

        # Create an image file and retrieve its contents and resized contents
        jpg_filename = 'large_image.jpg'
        jpg_file_path = os.path.join(test_files_path, jpg_filename)
        jpg_file_size = os.path.getsize(jpg_file_path)
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': jpg_filename,
            'base64_encoded_file': jpg_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, extra_environ_admin)
        resp = response.json_body
        jpg_filename = resp['filename']
        jpg_file_id = resp['id']

        # Get the image file's contents
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, jpg_file_id),
            headers=self.json_headers, extra_environ=extra_environ_admin)
        response_base64 = b64encode(response.body)
        assert jpg_file_base64.encode('utf8') == response_base64
        assert guess_type(jpg_filename)[0] == response.headers['Content-Type']
        assert jpg_file_size == int(response.headers['Content-Length'])

        # Get the reduced image file's contents
        if self.create_reduced_size_file_copies and Image:
            response = self.app.get(
                '/{}/files/{}/serve_reduced'.format(self.old_name, jpg_file_id),
                headers=self.json_headers,
                extra_environ=extra_environ_admin)
            response_base64 = b64encode(response.body)
            assert len(jpg_file_base64) > len(response_base64)
            assert guess_type(jpg_filename)[0] == response.headers['Content-Type']
        else:
            response = self.app.get(
                '/{}/files/{}/serve_reduced'.format(self.old_name, jpg_file_id),
                headers=self.json_headers,
                extra_environ=extra_environ_admin, status=404)
            resp = response.json_body
            assert resp['error'] == 'There is no size-reduced copy of file %s' % jpg_file_id

        # Attempt to get the reduced contents of a file that has none (i.e., no
        # lossy_filename value) and expect to fail.

        # Create a .ogg file and retrieve its contents and fail to retrieve its resized contents
        ogg_filename = 'old_test.ogg'
        ogg_file_path = os.path.join(test_files_path, ogg_filename)
        ogg_file_size = os.path.getsize(ogg_file_path)
        with open(ogg_file_path, 'rb') as f:
            ogg_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': ogg_filename,
            'base64_encoded_file': ogg_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers, extra_environ_admin)
        resp = response.json_body
        ogg_filename = resp['filename']
        ogg_file_id = resp['id']

        # Get the .ogg file's contents
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, ogg_file_id),
            headers=self.json_headers, extra_environ=extra_environ_admin)
        response_base64 = b64encode(response.body)
        assert ogg_file_base64.encode('utf8') == response_base64
        assert guess_type(ogg_filename)[0] == response.headers['Content-Type']
        assert ogg_file_size == int(response.headers['Content-Length'])

        # Attempt to get the reduced image file's contents and expect to fail
        response = self.app.get(
            '/{}/files/{}/serve_reduced'.format(self.old_name, ogg_file_id),
            headers=self.json_headers, extra_environ=extra_environ_admin,
            status=404)
        resp = response.json_body
        assert resp['error'] == 'There is no size-reduced copy of file %s' % ogg_file_id

        # Invalid id
        response = self.app.get(
            '/{}/files/{}/serve'.format(self.old_name, 123456789012),
            headers=self.json_headers, extra_environ=extra_environ_admin,
            status=404)
        resp = response.json_body
        assert resp['error'] == 'There is no file with id 123456789012'

    def test_file_reduction(self):
        """Verifies that reduced-size copies of image and wav files are created
        in files/reduced_files and that the names of these reduced-size files
        is returned as the lossy_filename attribute.

        Note that this test will fail if create_reduced_size_file_copies is set
        to 0 in the config file.
        """
        def get_size(path):
            return os.stat(path).st_size

        if not self.create_reduced_size_file_copies:
            assert False
        if not Image:
            assert False

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)

        # Create a JPG file that will not be reduced because it is already
        # small enough
        jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
        jpg_file_size = os.path.getsize(jpg_file_path)
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')

        params = self.file_create_params_base64.copy()
        params.update({
            'filename': 'old_test.jpg',
            'base64_encoded_file': jpg_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        file_count = dbsession.query(old_models.File).count()
        assert resp['filename'] == 'old_test.jpg'
        assert resp['MIME_type'] == 'image/jpeg'
        assert resp['size'] == jpg_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert resp['lossy_filename'] is None
        assert file_count == 1
        assert len(os.listdir(self.reduced_files_path)) == 0

        # Create a large JPEG file and expect a reduced-size .jpg to be
        # created in files/reduced_files.
        filename = 'large_image.jpg'
        jpg_file_path = os.path.join(self.test_files_path, filename)
        jpg_reduced_file_path = os.path.join(
            self.reduced_files_path, filename)
        with open(jpg_file_path, 'rb') as f:
            jpg_file_base64 = b64encode(f.read()).decode('utf8')

        params = self.file_create_params_base64.copy()
        params.update({
            'filename': filename,
            'base64_encoded_file': jpg_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        new_file_count = dbsession.query(old_models.File).count()
        assert new_file_count == file_count + 1
        assert resp['filename'] == filename
        assert resp['MIME_type'] == 'image/jpeg'
        assert resp['enterer']['first_name'] == 'Admin'
        if self.create_reduced_size_file_copies and Image:
            assert resp['lossy_filename'] == filename
            assert resp['lossy_filename'] in os.listdir(self.reduced_files_path)
            assert get_size(jpg_file_path) > get_size(jpg_reduced_file_path)
        else:
            assert resp['lossy_filename'] is None
            assert not os.path.isfile(jpg_reduced_file_path)

        # Create a large GIF file and expect a reduced-size .gif to be created in
        # files/reduced_files.
        filename = 'large_image.gif'
        gif_file_path = os.path.join(self.test_files_path, filename)
        gif_reduced_file_path = os.path.join(self.reduced_files_path, filename)
        with open(gif_file_path, 'rb') as f:
            gif_file_base64 = b64encode(f.read()).decode('utf8')

        params = self.file_create_params_base64.copy()
        params.update({
            'filename': filename,
            'base64_encoded_file': gif_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                self.extra_environ_admin)
        resp = response.json_body
        file_count = new_file_count
        new_file_count = dbsession.query(old_models.File).count()
        assert new_file_count == file_count + 1
        assert resp['filename'] == filename
        assert resp['MIME_type'] == 'image/gif'
        assert resp['enterer']['first_name'] == 'Admin'
        if self.create_reduced_size_file_copies and Image:
            assert resp['lossy_filename'] == filename
            assert resp['lossy_filename'] in os.listdir(self.reduced_files_path)
            assert get_size(gif_file_path) > get_size(gif_reduced_file_path)
        else:
            assert resp['lossy_filename'] is None
            assert not os.path.isfile(gif_reduced_file_path)

        # Create a large PNG file and expect a reduced-size .png to be created in
        # files/reduced_files.
        filename = 'large_image.png'
        png_file_path = os.path.join(self.test_files_path, filename)
        png_reduced_file_path = os.path.join(self.reduced_files_path, filename)
        params = self.file_create_params_MPFD.copy()
        params.update({'filename': filename})
        response = self.app.post(url('create'), params,
                                extra_environ=self.extra_environ_admin,
                                upload_files=[('filedata', png_file_path)])
        resp = response.json_body
        file_count = new_file_count
        new_file_count = dbsession.query(old_models.File).count()
        assert new_file_count == file_count + 1
        assert resp['filename'] == filename
        assert resp['MIME_type'] == 'image/png'
        assert resp['enterer']['first_name'] == 'Admin'
        if self.create_reduced_size_file_copies and Image:
            assert resp['lossy_filename'] == filename
            assert resp['lossy_filename'] in os.listdir(self.reduced_files_path)
            assert get_size(png_file_path) > get_size(png_reduced_file_path)
        else:
            assert resp['lossy_filename'] is None
            assert not os.path.isfile(png_reduced_file_path)

        # Test copying .wav files to .ogg/.mp3

        format_ = self.preferred_lossy_audio_format

        # Create a WAV file for which an .ogg/.mp3 Vorbis copy will be
        # created in files/reduced_files.
        filename = 'old_test.wav'
        lossy_filename = '%s.%s' % (os.path.splitext(filename)[0], format_)
        lossy_file_path = os.path.join(
            self.reduced_files_path, lossy_filename)
        wav_file_path = os.path.join(self.test_files_path, filename)
        wav_file_size = os.path.getsize(wav_file_path)
        with open(wav_file_path, 'rb') as f:
            wav_file_base64 = b64encode(f.read()).decode('utf8')
        params = self.file_create_params_base64.copy()
        params.update({
            'filename': filename,
            'base64_encoded_file': wav_file_base64
        })
        params = json.dumps(params)
        response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
        resp = response.json_body
        file_count = new_file_count
        new_file_count = dbsession.query(old_models.File).count()
        assert resp['filename'] == filename
        assert resp['MIME_type'] == 'audio/x-wav'
        assert resp['size'] == wav_file_size
        assert resp['enterer']['first_name'] == 'Admin'
        assert new_file_count == file_count + 1
        if (    self.create_reduced_size_file_copies and
                h.command_line_program_installed('ffmpeg')):
            assert resp['lossy_filename'] == lossy_filename, (
                '{} != {}'.format(resp['lossy_filename'], lossy_filename))
            assert (resp['lossy_filename'] in
                    os.listdir(self.reduced_files_path))
            assert get_size(wav_file_path) > get_size(lossy_file_path)
        else:
            assert resp['lossy_filename'] is None
            assert not os.path.isfile(lossy_file_path)

    def test_new_search(self):
        """Tests that GET /files/new_search returns the search parameters for
        searching the files resource.
        """

        dbsession = self.dbsession
        db = DBUtils(dbsession, self.settings)
        query_builder = SQLAQueryBuilder(
            dbsession, 'File', settings=self.settings)
        response = self.app.get(
            url('new_search'), headers=self.json_headers,
            extra_environ=self.extra_environ_view)
        resp = response.json_body
        assert (resp['search_parameters'] ==
                query_builder.get_search_parameters())
