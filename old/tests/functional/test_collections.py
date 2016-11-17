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
from time import sleep
from uuid import uuid4

from sqlalchemy.sql import desc
import transaction

import old.lib.constants as oldc
from old.lib.dbutils import DBUtils
import old.lib.helpers as h
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder
import old.models.modelbuilders as omb
import old.models as old_models
from old.models import Collection
from old.tests import TestView, add_SEARCH_to_web_test_valid_methods


LOGGER = logging.getLogger(__name__)


# Recreate the Pylons ``url`` global function that gives us URL paths for a
# given (resource) route name plus path variables as **kwargs
url = Collection._url()
forms_url = old_models.Form._url()
files_url = old_models.File._url()


MARKUP_LANGUAGE_TO_FUNC = {
    'reStructuredText': h.rst2html,
    'Markdown': h.md2html
}


class TestCollectionsView(TestView):

    def tearDown(self):
        super().tearDown(dirs_to_clear=['reduced_files_path', 'files_path'])

    def test_index(self):
        """Tests that GET /collections returns a JSON array of collections with
        expected values.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Test that the restricted tag is working correctly.
            # First get the users.
            users = db.get_users()
            contributor_id = [u for u in users if u.role == 'contributor'][0].id

            # Then add a contributor and a restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            my_contributor = omb.generate_default_user()
            my_contributor_first_name = 'Mycontributor'
            my_contributor.first_name = my_contributor_first_name
            dbsession.add_all([restricted_tag, my_contributor])
            transaction.commit()
            my_contributor = dbsession.query(old_models.User).filter(
                old_models.User.first_name == my_contributor_first_name).first()
            my_contributor_id = my_contributor.id
            restricted_tag = db.get_restricted_tag()

            # Then add the default application settings with my_contributor as
            # the only unrestricted user.
            application_settings = omb.generate_default_application_settings()
            application_settings.unrestricted_users = [my_contributor]
            dbsession.add(application_settings)
            transaction.commit()

            # Finally, issue two POST requests to create two default collections
            # with the *default* contributor as the enterer.  One collection will be
            # restricted and the other will not be.
            extra_environ = {'test.authentication.id': contributor_id}

            # Create the restricted collection.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Restricted Collection',
                'tags': [db.get_tags()[0].id]    # the restricted tag should be
                                                 # the only one
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                     extra_environ)
            resp = response.json_body
            restricted_collection_id = resp['id']

            # Create the unrestricted collection.
            params = self.collection_create_params.copy()
            params.update({'title': 'Unrestricted Collection'})
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            extra_environ)
            resp = response.json_body

            # Expectation: the administrator, the default contributor (qua
            # enterer) and the unrestricted my_contributor should all be able
            # to view both collections. The viewer will only receive the
            # unrestricted collection.

            # An administrator should be able to view both collections.
            extra_environ = {'test.authentication.role': 'administrator'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2
            assert resp[0]['title'] == 'Restricted Collection'
            assert response.content_type == 'application/json'

            # The default contributor (qua enterer) should also be able to view
            # both collections.
            extra_environ = {'test.authentication.id': contributor_id}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2

            # Mycontributor (an unrestricted user) should also be able to view
            # both collections.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2

            # A (not unrestricted) viewer should be able to view only one
            # collection.
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 1

            # Remove Mycontributor from the unrestricted users list and access
            # to the second collection will be denied.
            application_settings = db.current_app_set
            application_settings.unrestricted_users = []
            dbsession.add(application_settings)
            transaction.commit()

            # Mycontributor (no longer an unrestricted user) should now *not* be
            # able to view the restricted collection.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 1

            # Remove the restricted tag from the collection and the viewer should
            # now be able to view it too.
            restricted_collection = dbsession.query(old_models.Collection).get(
                restricted_collection_id)
            restricted_collection.tags = []
            dbsession.add(restricted_collection)
            transaction.commit()
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 2

            # Clear all Collections (actually, everything but the tags, users and
            # languages)
            db.clear_all_models(['User', 'Tag', 'Language'])

            # Now add 100 collections.  The even ones will be restricted, the odd ones not.
            def create_collection_from_index(index):
                collection = old_models.Collection()
                collection.title = 'title %d' % index
                return collection
            collections = [create_collection_from_index(i) for i in range(1, 101)]
            dbsession.add_all(collections)
            transaction.commit()
            collections = db.get_models_by_name('Collection', True)
            restricted_tag = db.get_restricted_tag()
            for collection in collections:
                if int(collection.title.split(' ')[1]) % 2 == 0:
                    collection.tags.append(restricted_tag)
                dbsession.add(collection)
            transaction.commit()
            collections = db.get_models_by_name('Collection', True)    # ordered by Collection.id ascending

            # An administrator should be able to retrieve all of the collections.
            extra_environ = {'test.authentication.role': 'administrator'}
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp) == 100
            assert resp[0]['title'] == 'title 1'
            assert resp[0]['id'] == collections[0].id

            # Test the paginator GET params.
            paginator = {'items_per_page': 23, 'page': 3}
            response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp['items']) == 23
            assert resp['items'][0]['title'] == collections[46].title

            # Test the order_by GET params.
            order_by_params = {'order_by_model': 'Collection', 'order_by_attribute': 'title',
                        'order_by_direction': 'desc'}
            response = self.app.get(url('index'), order_by_params,
                            headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            result_set = sorted([c.title for c in collections], reverse=True)
            assert result_set == [f['title'] for f in resp]

            # Test the order_by *with* paginator.
            params = {'order_by_model': 'Collection', 'order_by_attribute': 'title',
                        'order_by_direction': 'desc', 'items_per_page': 23, 'page': 3}
            response = self.app.get(url('index'), params,
                            headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert result_set[46] == resp['items'][0]['title']
            assert response.content_type == 'application/json'

            # The default viewer should only be able to see the odd numbered collections,
            # even with a paginator.
            items_per_page = 7
            page = 7
            paginator = {'items_per_page': items_per_page, 'page': page}
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp['items']) == items_per_page
            assert resp['items'][0]['title'] == 'title %d' % (
                ((items_per_page * (page - 1)) * 2) + 1)

            # Expect a 400 error when the order_by_direction param is invalid
            order_by_params = {'order_by_model': 'Collection', 'order_by_attribute': 'title',
                        'order_by_direction': 'descending'}
            response = self.app.get(url('index'), order_by_params, status=400,
                headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert resp['errors']['order_by_direction'] == "Value must be one of: asc; desc (not 'descending')"

            # Expect the default BY id ASCENDING ordering when the order_by_model/Attribute
            # param is invalid.
            order_by_params = {'order_by_model': 'Collectionissimo', 'order_by_attribute': 'tutelage',
                        'order_by_direction': 'desc'}
            response = self.app.get(url('index'), order_by_params,
                headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert resp[0]['id'] == collections[0].id

            # Expect a 400 error when the paginator GET params are, empty, not
            # integers or are integers that are less than 1
            paginator = {'items_per_page': 'a', 'page': ''}
            response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                    extra_environ=extra_environ, status=400)
            resp = response.json_body
            assert resp['errors']['items_per_page'] == 'Please enter an integer value'
            assert resp['errors']['page'] == 'Please enter a value'
            assert response.content_type == 'application/json'

            paginator = {'items_per_page': 0, 'page': -1}
            response = self.app.get(url('index'), paginator, headers=self.json_headers,
                                    extra_environ=extra_environ, status=400)
            resp = response.json_body
            assert resp['errors']['items_per_page'] == 'Please enter a number that is 1 or greater'
            assert resp['errors']['page'] == 'Please enter a number that is 1 or greater'

    def test_create(self):
        """Tests that POST /collections correctly creates a new collection."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Pass some mal-formed JSON to test that a 400 error is returned.
            params = '"a'   # Bad JSON
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['error'] == 'JSON decode error: the parameters provided were not valid JSON.'

            # Create some test tags
            tag1 = old_models.Tag()
            tag2 = old_models.Tag()
            restricted_tag = omb.generate_restricted_tag()
            tag1.name = 'tag 1'
            tag2.name = 'tag 2'
            dbsession.add_all([tag1, tag2, restricted_tag])
            dbsession.flush()
            tag1_id = tag1.id
            tag2_id = tag2.id
            restricted_tag_id = restricted_tag.id
            transaction.commit()

            # Create some test files
            wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
            params = self.file_create_params.copy()
            params.update({
                'filename': 'old_test.wav',
                'base64_encoded_file': b64encode(open(wav_file_path, 'rb').read()).decode('utf8')
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            file1_id = resp['id']

            jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
            jpg_file_base64 = b64encode(open(jpg_file_path, 'rb').read()).decode('utf8')
            params = self.file_create_params.copy()
            params.update({
                'filename': 'old_test.jpg',
                'base64_encoded_file': jpg_file_base64
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            file2_id = resp['id']

            # Create some test forms
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'transcription 1',
                'translations': [{'transcription': 'translation 1', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers,
                                     self.extra_environ_admin)
            resp = response.json_body
            form1_id = resp['id']

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'transcription 2',
                'translations': [{'transcription': 'translation 2', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            form2_id = resp['id']

            # Create a test collection.
            md_contents1 = '\n'.join([
                '### Chapter 1',
                '',
                '#### Section 1',
                '',
                '* Item 1',
                '* Item 2',
                '',
                '#### Section 2',
                '',
                'form[%d]' % form1_id,
                'form[%d]' % form2_id
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Chapter 1',
                'markup_language': 'Markdown',
                'contents': md_contents1,
                'files': [file1_id, file2_id],
                'tags': [tag1_id, tag2_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            collection1_id = resp['id']
            collection_count = dbsession.query(old_models.Collection).count()
            assert type(resp) == type({})
            assert resp['title'] == 'Chapter 1'
            assert resp['enterer']['first_name'] == 'Admin'
            assert resp['html'] == MARKUP_LANGUAGE_TO_FUNC['Markdown'](md_contents1)
            assert sorted([f['id'] for f in resp['files']]) == sorted([file1_id, file2_id])
            assert sorted([t['id'] for t in resp['tags']]) == sorted([tag1_id, tag2_id])
            assert sorted([f['id'] for f in resp['forms']]) == sorted([form1_id, form2_id])
            assert collection_count == 1
            assert response.content_type == 'application/json'

            # Create two more forms
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'transcription 3',
                'translations': [{'transcription': 'translation 3', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            form3_id = resp['id']

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'transcription 4',
                'translations': [{'transcription': 'translation 4', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            form4_id = resp['id']

            # Create a second collection, one that references the first.
            md_contents2 = '\n'.join([
                '## Book 1',
                '',
                'collection[%d]' % collection1_id,
                '',
                '### Chapter 2',
                '',
                'form[%d]' % form3_id
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Book 1',
                'markup_language': 'Markdown',
                'contents': md_contents2
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            collection2_id = resp['id']
            collection_count = dbsession.query(old_models.Collection).count()
            collection2_contents_unpacked = md_contents2.replace(
                'collection[%d]' % collection1_id, md_contents1)
            assert type(resp) == type({})
            assert resp['title'] == 'Book 1'
            assert resp['enterer']['first_name'] == 'Admin'
            assert resp['contents_unpacked'] == collection2_contents_unpacked
            assert resp['html'] == MARKUP_LANGUAGE_TO_FUNC['Markdown'](collection2_contents_unpacked)
            assert resp['files'] == []
            assert resp['tags'] == []
            assert sorted([f['id'] for f in resp['forms']]) == sorted([form1_id, form2_id, form3_id])
            assert collection_count == 2
            assert response.content_type == 'application/json'

            # Create a third collection, one that references the second and, thereby,
            # the third also.
            md_contents3 = '\n'.join([
                '# Title',
                '',
                'collection(%d)' % collection2_id,
                '',
                '## Book 2',
                '',
                '### Chapter 3',
                '',
                'form[%d]' % form4_id
            ])
            params3 = self.collection_create_params.copy()
            params3.update({
                'title': 'Novel',
                'markup_language': 'Markdown',
                'contents': md_contents3
            })
            params3 = json.dumps(params3)
            response = self.app.post(url('create'), params3, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            collection3_id = resp['id']
            collection_count = dbsession.query(old_models.Collection).count()
            collection3_contents_unpacked = md_contents3.replace(
                'collection(%d)' % collection2_id, collection2_contents_unpacked)
            assert type(resp) == type({})
            assert resp['title'] == 'Novel'
            assert resp['enterer']['first_name'] == 'Admin'
            assert resp['contents_unpacked'] == collection3_contents_unpacked
            assert resp['html'] == MARKUP_LANGUAGE_TO_FUNC['Markdown'](collection3_contents_unpacked)
            assert resp['files'] == []
            assert resp['tags'] == []
            assert sorted([f['id'] for f in resp['forms']]) == sorted([form1_id, form2_id, form3_id, form4_id])
            assert collection_count == 3
            assert response.content_type == 'application/json'

            # First attempt to update the third collection with no new data and
            # expect to fail.
            response = self.app.put(url('update', id=collection3_id), params3,
                self.json_headers, self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['error'] == 'The update request failed because the submitted data were not new.'

            # Now update the first collection by restricting it and updating its
            # contents.  Show that these changes propagate up to all collections that
            # reference collection 1 and that the values of the datetime_modified,
            # forms and html (and contents_unpacked) attributes of these other
            # collections are updated also.
            collection2 = dbsession.query(old_models.Collection).get(collection2_id)
            collection2_form_ids = [f.id for f in collection2.forms]
            collection2_datetime_modified = collection2.datetime_modified
            collection2_HTML = collection2.html
            collection2_backups_count = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection2_id).count()
            collection3 = dbsession.query(old_models.Collection).get(collection3_id)
            collection3_form_ids = [f.id for f in collection3.forms]
            collection3_datetime_modified = collection3.datetime_modified
            collection3_HTML = collection3.html
            collection3_backups_count = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection3_id).count()
            sleep(1)
            md_contents1 = '\n'.join([
                '### Chapter 1',
                '',
                '#### Section 1',
                '',
                '* Item 1',
                '* Item 2',
                '',
                '#### Section 2',
                '',
                'form[%d]' % form2_id    # THE CHANGE: reference to form1 has been removed
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Chapter 1',
                'markup_language': 'Markdown',
                'contents': md_contents1,
                'files': [file1_id, file2_id],
                'tags': [tag1_id, tag2_id, restricted_tag_id]   # ANOTHER CHANGE: restrict this collection
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=collection1_id), params,
                self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            new_collection2 = dbsession.query(old_models.Collection).get(collection2_id)
            new_collection2_form_ids = [f.id for f in new_collection2.forms]
            new_collection2_datetime_modified = new_collection2.datetime_modified
            new_collection2_HTML = new_collection2.html
            new_collection2_contents = new_collection2.contents
            new_collection2_backups = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection2_id).all()
            new_collection2_backups_count = len(new_collection2_backups)
            new_collection3 = dbsession.query(old_models.Collection).get(collection3_id)
            new_collection3_form_ids = [f.id for f in new_collection3.forms]
            new_collection3_datetime_modified = new_collection3.datetime_modified
            new_collection3_HTML = new_collection3.html
            new_collection3_backups = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection3_id).all()
            new_collection3_backups_count = len(new_collection3_backups)
            assert form1_id not in [f['id'] for f in resp['forms']]
            assert sorted(collection2_form_ids) != sorted(new_collection2_form_ids)
            assert form1_id in collection2_form_ids
            assert form1_id not in new_collection2_form_ids
            assert collection2_datetime_modified != new_collection2_datetime_modified
            assert collection2_HTML != new_collection2_HTML
            assert sorted(collection3_form_ids) != sorted(new_collection3_form_ids)
            assert form1_id in collection3_form_ids
            assert form1_id not in new_collection3_form_ids
            assert collection3_datetime_modified != new_collection3_datetime_modified
            assert collection3_HTML != new_collection3_HTML
            # Show that backups are made too
            assert new_collection2_backups_count == collection2_backups_count + 1
            assert new_collection3_backups_count == collection3_backups_count + 1
            assert form1_id not in [f.id for f in new_collection2.forms]
            assert form1_id in json.loads(new_collection2_backups[0].forms)
            assert form1_id not in [f.id for f in new_collection3.forms]
            assert form1_id in json.loads(new_collection3_backups[0].forms)

            # Show that a vacuous update of the third collection with no new data
            # will again fail.
            response = self.app.put(url('update', id=collection3_id), params3,
                self.json_headers, self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['error'] == 'The update request failed because the submitted data were not new.'

            # Show how collection deletion propagates.  That is, deleting the first
            # collection will result in a deletion of all references to that collection
            # in the contents of other collections.

            # Delete the first collection and show that the contents value of the
            # second collection no longer references it, i.e., the first.
            response = self.app.delete(url('delete', id=collection1_id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            old_collection2_contents = new_collection2_contents
            new_collection2 = dbsession.query(old_models.Collection).get(collection2_id)
            new_collection2_contents = new_collection2.contents
            collection1_ref = 'collection[%d]' % collection1_id
            old_collection2_backups_count = new_collection2_backups_count
            new_collection2_backups = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection2_id).\
                order_by(desc(old_models.CollectionBackup.id)).all()
            new_collection2_backups_count = len(new_collection2_backups)
            assert collection1_ref in old_collection2_contents
            assert collection1_ref not in new_collection2_contents
            assert new_collection2_backups_count == old_collection2_backups_count + 1
            assert collection1_ref in new_collection2_backups[0].contents

            # Now if we perform an irrelevant update on the third collection, everything
            # will work fine because the reference to the now nonexistent first collection
            # in the contents of the second collection has been removed.  Without deletion
            # propagation, an InvalidCollectionReferenceError would have been raised and
            # an error response would have been returned.
            params3 = json.loads(params3)
            params3.update({'title': 'A Great Novel'})
            params3 = json.dumps(params3)
            response = self.app.put(url('update', id=collection3_id), params3,
                                    self.json_headers, self.extra_environ_admin)

            # Now show that when a form that is referenced in a collection is deleted,
            # the contents of that collection are edited so that the reference to the
            # deleted form is removed.  This edit causes the appropriate changes to
            # the attributes of the affected collections as well as all of the collections
            # that reference those collections
            collection2 = dbsession.query(old_models.Collection).get(collection2_id)
            collection3 = dbsession.query(old_models.Collection).get(collection3_id)
            collection2_contents = collection2.contents
            collection2_HTML = collection2.html
            collection2_forms = [f.id for f in collection2.forms]
            collection3_forms = [f.id for f in collection3.forms]
            collection3_contents_unpacked = collection3.contents_unpacked
            collection3_HTML = collection3.html
            collection2_backups_count = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection2_id).count()
            collection3_backups_count = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection3_id).count()
            response = self.app.delete(forms_url('delete', id=form3_id), headers=self.json_headers,
                                    extra_environ=self.extra_environ_admin)
            new_collection2 = dbsession.query(old_models.Collection).get(collection2_id)
            new_collection3 = dbsession.query(old_models.Collection).get(collection3_id)
            new_collection2_contents = new_collection2.contents
            new_collection2_forms = [f.id for f in new_collection2.forms]
            new_collection2_HTML = new_collection2.html
            new_collection3_forms = [f.id for f in new_collection3.forms]
            new_collection3_contents_unpacked = new_collection3.contents_unpacked
            new_collection3_HTML = new_collection3.html
            new_collection2_backups_count = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection2_id).count()
            new_collection3_backups_count = dbsession.query(old_models.CollectionBackup).\
                filter(old_models.CollectionBackup.collection_id == collection3_id).count()
            assert 'form[%d]' % form3_id in collection2_contents
            assert 'form[%d]' % form3_id in collection2_HTML
            assert 'form[%d]' % form3_id in collection3_contents_unpacked
            assert 'form[%d]' % form3_id in collection3_HTML
            assert 'form[%d]' % form3_id not in new_collection2_contents
            assert 'form[%d]' % form3_id not in new_collection2_HTML
            assert 'form[%d]' % form3_id not in new_collection3_contents_unpacked
            assert 'form[%d]' % form3_id not in new_collection3_HTML
            assert form3_id in collection2_forms
            assert form3_id in collection3_forms
            assert form3_id not in new_collection2_forms
            assert form3_id not in new_collection3_forms
            assert new_collection2_backups_count == collection2_backups_count + 1
            assert new_collection3_backups_count == collection3_backups_count + 1

    def test_create_invalid(self):
        """Tests that POST /collections with invalid input returns an appropriate error."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Empty title should raise error
            collection_count = dbsession.query(old_models.Collection).count()
            params = self.collection_create_params.copy()
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert resp['errors']['title'] == 'Please enter a value'
            assert new_collection_count == collection_count

            # Exceeding length restrictions should return errors also.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test create invalid title' * 100,
                'url': 'test_create_invalid_url' * 100
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            too_long_error = 'Enter a value not more than 255 characters long'
            assert resp['errors']['title'] == too_long_error
            assert resp['errors']['url'] == 'The input is not valid'
            assert new_collection_count == collection_count
            assert response.content_type == 'application/json'

            # Add some default application settings and set
            # app_globals.application_settings.
            application_settings = omb.generate_default_application_settings()
            dbsession.add(application_settings)
            transaction.commit()
            extra_environ = self.extra_environ_admin.copy()

            # Create a collection with an invalid type, markup_language and url
            bad_URL = 'bad&url'
            bad_markup_language = 'rtf'
            bad_collection_type = 'novella'
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test create invalid title',
                'url': bad_URL,
                'markup_language': bad_markup_language,
                'type': bad_collection_type
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ=extra_environ, status=400)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert resp['errors']['url'] == 'The input is not valid'
            assert resp['errors']['markup_language'] == \
                "Value must be one of: reStructuredText; Markdown (not 'rtf')"
            assert resp['errors']['type'] == \
                "Value must be one of: story; elicitation; paper; discourse; other (not 'novella')"
            assert new_collection_count == collection_count
            assert response.content_type == 'application/json'

            # Create a collection with a valid type, markup_language and url
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test create valid title',
                'url': 'good-url/really',
                'markup_language': 'reStructuredText',
                'type': 'paper'
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert resp['url'] == 'good-url/really'
            assert resp['type'] == 'paper'
            assert resp['markup_language'] == 'reStructuredText'
            assert new_collection_count == collection_count + 1

            # Create a collection with some invalid many-to-one data, i.e., speaker
            # enterer, etc.
            bad_id = 109
            bad_int = 'abc'
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test create invalid title',
                'speaker': bad_id,
                'elicitor': bad_int,
                'source': bad_int
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ=extra_environ, status=400)
            resp = response.json_body
            collection_count = new_collection_count
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert resp['errors']['speaker'] == \
                'There is no speaker with id %d.' % bad_id
            assert resp['errors']['elicitor'] == 'Please enter an integer value'
            assert resp['errors']['source'] == 'Please enter an integer value'
            assert new_collection_count == collection_count
            assert response.content_type == 'application/json'

            # Now create a collection with some *valid* many-to-one data, i.e.,
            # speaker, elicitor, source.
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([speaker, source])
            dbsession.flush()
            speaker_first_name = speaker.first_name
            source_year = source.year
            transaction.commit()
            contributor = dbsession.query(old_models.User).filter(
                old_models.User.role=='contributor').first()
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test create title',
                'speaker': db.get_speakers()[0].id,
                'elicitor': contributor.id,
                'source': db.get_sources()[0].id
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert resp['source']['year'] == source_year    # etc. ...
            assert resp['speaker']['first_name'] == speaker_first_name
            assert resp['elicitor']['first_name'] == contributor.first_name
            assert new_collection_count == collection_count + 1

    def test_relational_restrictions(self):
        """Tests that the restricted tag works correctly with respect to relational attributes of collections.

        That is, tests that (a) users are not able to access restricted forms or
        files via collection.forms and collection.files respectively since
        collections associated to restricted forms or files are automatically
        tagged as restricted; and (b) a restricted user cannot append a restricted
        form or file to a collection."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            admin = self.extra_environ_admin.copy()
            contrib = self.extra_environ_contrib.copy()

            # Create a test collection.
            params = self.collection_create_params.copy()
            original_title = 'test_update_title'
            params.update({'title': original_title})
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, admin)
            resp = response.json_body
            collection_count = dbsession.query(old_models.Collection).count()
            assert resp['title'] == original_title
            assert collection_count == 1

            # Now create the restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            dbsession.add(restricted_tag)
            dbsession.flush()
            restricted_tag_id = restricted_tag.id
            transaction.commit()

            # Then create two files, one restricted and one not ...
            wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
            wav_file_base64 = b64encode(open(wav_file_path, 'rb').read()).decode('utf8')
            params = self.file_create_params.copy()
            params.update({
                'filename': 'restricted_file.wav',
                'base64_encoded_file': wav_file_base64,
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params, self.json_headers, admin)
            resp = response.json_body
            restricted_file_id = resp['id']

            params = self.file_create_params.copy()
            params.update({
                'filename': 'unrestricted_file.wav',
                'base64_encoded_file': wav_file_base64
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params, self.json_headers, admin)
            resp = response.json_body
            unrestricted_file_id = resp['id']

            # ... and create two forms, one restricted and one not.
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'restricted',
                'translations': [{'transcription': 'restricted', 'grammaticality': ''}],
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            restricted_form_id = resp['id']

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'unrestricted',
                'translations': [{'transcription': 'unrestricted', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            unrestricted_form_id = resp['id']

            # Now, as a (restricted) contributor, attempt to create a collection and
            # associate it to a restricted file -- expect to fail.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test',
                'files': [restricted_file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    contrib, status=400)
            resp = response.json_body
            assert 'You are not authorized to access the file with id %d.' % restricted_file_id in \
                resp['errors']['files']
            assert response.content_type == 'application/json'

            # Now, as a (restricted) contributor, attempt to create a collection
            # that embeds via reference a restricted form -- expect to fail here also.
            md_contents = '\n'.join([
                'Chapter',
                '=======',
                '',
                'Section',
                '-------',
                '',
                '* Item 1',
                '* Item 2',
                '',
                'Section containing forms',
                '------------------------',
                '',
                'form[%d]' % restricted_form_id
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test',
                'markup_language': 'Markdown',
                'contents': md_contents
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    contrib, status=400)
            resp = response.json_body
            assert 'You are not authorized to access the form with id %d.' % restricted_form_id in \
                resp['errors']['forms']

            # Now, as a (restricted) contributor, attempt to create a collection and
            # associate it to an unrestricted file -- expect to succeed.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test',
                'files': [unrestricted_file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, contrib)
            resp = response.json_body
            unrestricted_collection_id = resp['id']
            assert resp['title'] == 'test'
            assert resp['files'][0]['name'] == 'unrestricted_file.wav'
            assert response.content_type == 'application/json'

            # Now, as a (restricted) contributor, attempt to create a collection that
            # embeds via reference an unrestricted file -- expect to succeed.
            md_contents = '\n'.join([
                'Chapter',
                '=======',
                '',
                'Section',
                '-------',
                '',
                '* Item 1',
                '* Item 2',
                '',
                'Section containing forms',
                '------------------------',
                '',
                'form[%d]' % unrestricted_form_id
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test',
                'markup_language': 'Markdown',
                'contents': md_contents
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, contrib)
            resp = response.json_body
            assert resp['forms'][0]['transcription'] == 'unrestricted'

            # Now, as a(n unrestricted) administrator, attempt to create a collection
            # and associate it to a restricted file -- expect (a) to succeed and (b) to
            # find that the form is now restricted.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test',
                'files': [restricted_file_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, admin)
            resp = response.json_body
            indirectly_restricted_collection1_id = resp['id']
            assert resp['title'] == 'test'
            assert resp['files'][0]['name'] == 'restricted_file.wav'
            assert 'restricted' in [t['name'] for t in resp['tags']]
            assert response.content_type == 'application/json'

            # Now, as a(n unrestricted) administrator, attempt to create a collection
            # that embeds via reference a restricted form -- expect to succeed here also.
            md_contents = '\n'.join([
                'Chapter',
                '=======',
                '',
                'Section',
                '-------',
                '',
                '* Item 1',
                '* Item 2',
                '',
                'Section containing forms',
                '------------------------',
                '',
                'form[%d]' % restricted_form_id
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test',
                'markup_language': 'Markdown',
                'contents': md_contents
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers, admin)
            resp = response.json_body
            indirectly_restricted_collection2_id = resp['id']
            assert resp['title'] == 'test'
            assert resp['forms'][0]['transcription'] == 'restricted'
            assert 'restricted' in [t['name'] for t in resp['tags']]
            assert response.content_type == 'application/json'

            # Now show that the indirectly restricted collections are inaccessible to
            # unrestricted users.
            response = self.app.get(url('index'), headers=self.json_headers,
                                    extra_environ=contrib)
            resp = response.json_body
            assert indirectly_restricted_collection1_id not in [c['id'] for c in resp]
            assert indirectly_restricted_collection2_id not in [c['id'] for c in resp]

            # Now, as a(n unrestricted) administrator, create a collection.
            unrestricted_collection_params = self.collection_create_params.copy()
            unrestricted_collection_params.update({'title': 'test'})
            params = json.dumps(unrestricted_collection_params)
            response = self.app.post(url('create'), params, self.json_headers, admin)
            resp = response.json_body
            unrestricted_collection_id = resp['id']
            assert resp['title'] == 'test'

            # As a restricted contributor, attempt to update the unrestricted collection
            # just created by associating it to a restricted file -- expect to fail.
            unrestricted_collection_params.update({'files': [restricted_file_id]})
            params = json.dumps(unrestricted_collection_params)
            response = self.app.put(url('update', id=unrestricted_collection_id), params,
                                    self.json_headers, contrib, status=400)
            resp = response.json_body
            assert 'You are not authorized to access the file with id %d.' % restricted_file_id in \
                resp['errors']['files']

            # As an unrestricted administrator, attempt to update an unrestricted collection
            # by associating it to a restricted file -- expect to succeed.
            response = self.app.put(url('update', id=unrestricted_collection_id), params,
                                    self.json_headers, admin)
            resp = response.json_body
            assert resp['id'] == unrestricted_collection_id
            assert 'restricted' in [t['name'] for t in resp['tags']]
            assert response.content_type == 'application/json'

            # Now show that the newly indirectly restricted collection is also
            # inaccessible to an unrestricted user.
            response = self.app.get(url('show', id=unrestricted_collection_id),
                    headers=self.json_headers, extra_environ=contrib, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'

            h.clear_directory_of_files(self.files_path)

    def test_new(self):
        """Tests that GET /collection/new returns an appropriate JSON object for creating a new OLD collection.

        The properties of the JSON object are 'speakers', 'users', 'tags',
        'sources', 'collection_types', 'markup_languages' and their values are
        arrays/lists.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Unauthorized user ('viewer') should return a 401 status code on the
            # new action, which requires a 'contributor' or an 'administrator'.
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('new'), extra_environ=extra_environ,
                                    status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'
            assert response.content_type == 'application/json'

            # Add some test data to the database.
            application_settings = omb.generate_default_application_settings()
            foreign_word_tag = omb.generate_foreign_word_tag()
            restricted_tag = omb.generate_restricted_tag()
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([application_settings, foreign_word_tag, restricted_tag,
                            speaker, source])
            transaction.commit()

            # Get the data currently in the db (see websetup.py for the test data).
            data = {
                'speakers': db.get_mini_dicts_getter('Speaker')(),
                'users': db.get_mini_dicts_getter('User')(),
                'tags': db.get_mini_dicts_getter('Tag')(),
                'sources': db.get_mini_dicts_getter('Source')()
            }

            # JSON.stringify and then re-Python-ify the data.  This is what the data
            # should look like in the response to a simulated GET request.
            data = json.loads(json.dumps(data))

            # GET /collection/new without params.  Without any GET params,
            # /collection/new should return a JSON array for every store.
            response = self.app.get(url('new'),
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['tags'] == data['tags']
            assert resp['speakers'] == data['speakers']
            assert resp['users'] == data['users']
            assert resp['sources'] == data['sources']
            assert set(resp['collection_types']) == set(oldc.COLLECTION_TYPES)
            assert set(resp['markup_languages']) == set(oldc.MARKUP_LANGUAGES)
            assert response.content_type == 'application/json'

            # GET /new_collection with params.  Param values are treated as strings, not
            # JSON.  If any params are specified, the default is to return a JSON
            # array corresponding to store for the param.  There are three cases
            # that will result in an empty JSON array being returned:
            # 1. the param is not specified
            # 2. the value of the specified param is an empty string
            # 3. the value of the specified param is an ISO 8601 UTC datetime
            #    string that matches the most recent datetime_modified value of the
            #    store in question.
            params = {
                # Value is empty string: 'speakers' will not be in response.
                'speakers': '',
                # Value is any string: 'sources' will be in response.
                'sources': 'anything can go here!',
                # Value is ISO 8601 UTC datetime string that does not match the most
                # recent Tag.datetime_modified value: 'tags' *will* be in
                # response.
                'tags': datetime.datetime.utcnow().isoformat(),
                # Value is ISO 8601 UTC datetime string that does match the most
                # recent SyntacticCategory.datetime_modified value:
                # 'syntactic_categories' will *not* be in response.
                'users': db.get_most_recent_modification_datetime('User').isoformat()
            }
            response = self.app.get(url('new'), params,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['speakers'] == []
            assert resp['sources'] == data['sources']
            assert resp['tags'] == data['tags']
            assert resp['users'] == []
            assert response.content_type == 'application/json'

    def test_update(self):
        """Tests that PUT /collections/id correctly updates an existing collection."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            collection_count = dbsession.query(old_models.Collection).count()

            # Add the default application settings and the restricted tag.
            restricted_tag = omb.generate_restricted_tag()
            application_settings = omb.generate_default_application_settings()
            dbsession.add_all([application_settings, restricted_tag])
            transaction.commit()
            restricted_tag = db.get_restricted_tag()
            restricted_tag_id = restricted_tag.id

            # Create a collection to update.
            params = self.collection_create_params.copy()
            original_title = 'test_update_title'
            params.update({
                'title': original_title,
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            id = int(resp['id'])
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert resp['title'] == original_title
            assert new_collection_count == collection_count + 1

            # As a viewer, attempt to update the restricted collection we just created.
            # Expect to fail.
            extra_environ = {'test.authentication.role': 'viewer'}
            params = self.collection_create_params.copy()
            params.update({'title': 'Updated!'})
            params = json.dumps(params)
            response = self.app.put(url('update', id=id), params,
                self.json_headers, extra_environ, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'

            # As a restricted contributor, attempt to update the restricted
            # collection we just created.  Expect to fail.
            extra_environ = {'test.authentication.role': 'contributor'}
            params = self.collection_create_params.copy()
            params.update({'title': 'Updated!'})
            params = json.dumps(params)
            response = self.app.put(url('update', id=id), params,
                self.json_headers, extra_environ, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'
            assert response.content_type == 'application/json'

            # As an administrator now, update the collection just created and expect to
            # succeed.
            orig_backup_count = dbsession.query(old_models.CollectionBackup).count()
            params = self.collection_create_params.copy()
            params.update({'title': 'Updated!'})
            params = json.dumps(params)
            response = self.app.put(url('update', id=id), params,
                                    self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            new_backup_count = dbsession.query(old_models.CollectionBackup).count()
            assert resp['title'] == 'Updated!'
            assert new_collection_count == collection_count + 1
            assert orig_backup_count + 1 == new_backup_count
            backup = dbsession.query(old_models.CollectionBackup)\
                .filter(old_models.CollectionBackup.UUID==resp['UUID'])\
                .order_by(desc(old_models.CollectionBackup.id)).first()
            assert backup.datetime_modified.isoformat() <= resp['datetime_modified']
            assert backup.title == original_title
            assert response.content_type == 'application/json'

            # Attempt an update with no new data.  Expect a 400 error
            # and response['errors'] = {'no change': The update request failed
            # because the submitted data were not new.'}.
            orig_backup_count = dbsession.query(old_models.CollectionBackup).count()
            response = self.app.put(url('update', id=id), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
            new_backup_count = dbsession.query(old_models.CollectionBackup).count()
            resp = response.json_body
            assert orig_backup_count == new_backup_count
            assert 'the submitted data were not new' in resp['error']
            assert response.content_type == 'application/json'

            # Now update our form by adding a many-to-one datum, viz. a speaker
            speaker = omb.generate_default_speaker()
            dbsession.add(speaker)
            transaction.commit()
            speaker = db.get_speakers()[0]
            speaker_id = speaker.id
            speaker_first_name = speaker.first_name
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Another title',
                'speaker': speaker_id
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=id), params, self.json_headers,
                                    extra_environ=extra_environ)
            resp = response.json_body
            assert resp['speaker']['first_name'] == speaker_first_name
            assert response.content_type == 'application/json'

            # Test the updating of many-to-many data.

            collection_count_at_start = dbsession.query(old_models.Collection).count()

            # Create some more tags
            tag1 = old_models.Tag()
            tag2 = old_models.Tag()
            tag1.name = 'tag 1'
            tag2.name = 'tag 2'
            dbsession.add_all([tag1, tag2])
            dbsession.flush()
            tag1_id = tag1.id
            tag2_id = tag2.id
            transaction.commit()

            # Create some test files
            wav_file_path = os.path.join(self.test_files_path, 'old_test.wav')
            params = self.file_create_params.copy()
            params.update({
                'filename': 'old_test.wav',
                'base64_encoded_file': b64encode(open(wav_file_path, 'rb').read()).decode('utf8')
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            file1_id = resp['id']

            jpg_file_path = os.path.join(self.test_files_path, 'old_test.jpg')
            jpg_file_base64 = b64encode(open(jpg_file_path, 'rb').read()).decode('utf8')
            params = self.file_create_params.copy()
            params.update({
                'filename': 'old_test.jpg',
                'base64_encoded_file': jpg_file_base64
            })
            params = json.dumps(params)
            response = self.app.post(files_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            file2_id = resp['id']

            # Create some test forms
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'transcription 1',
                'translations': [{'transcription': 'translation 1', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            form1_id = resp['id']

            params = self.form_create_params.copy()
            params.update({
                'transcription': 'transcription 2',
                'translations': [{'transcription': 'translation 2', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            form2_id = resp['id']

            # Create a test collection.
            md_contents = '\n'.join([
                'Chapter',
                '=======',
                '',
                'Section',
                '-------',
                '',
                '* Item 1',
                '* Item 2',
                '',
                'Section containing forms',
                '------------------------',
                '',
                'form[%d]' % form1_id,
                'form[%d]' % form2_id
            ])
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test_create_title',
                'markup_language': 'Markdown',
                'contents': md_contents,
                'files': [file1_id, file2_id],
                'tags': [restricted_tag_id, tag1_id, tag2_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin)
            resp = response.json_body
            created_collection_id = resp['id']
            collection_count = dbsession.query(old_models.Collection).count()
            assert resp['title'] == 'test_create_title'
            assert resp['enterer']['first_name'] == 'Admin'
            assert resp['html'] == MARKUP_LANGUAGE_TO_FUNC['Markdown'](md_contents)
            assert sorted([f['id'] for f in resp['files']]) == sorted([file1_id, file2_id])
            assert sorted([t['id'] for t in resp['tags']]) == sorted([tag1_id, tag2_id, restricted_tag_id])
            assert sorted([f['id'] for f in resp['forms']]) == sorted([form1_id, form2_id])
            assert collection_count == collection_count_at_start + 1
            assert response.content_type == 'application/json'

            # Attempt to update the collection we just created by merely changing the
            # order of the ids for the many-to-many attributes -- expect to fail.
            tags = [t.id for t in db.get_tags()]
            tags.reverse()
            files = [f.id for f in db.get_files()]
            files.reverse()
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test_create_title',
                'markup_language': 'Markdown',
                'contents': md_contents,
                'tags': tags,
                'files': files
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=created_collection_id), params,
                            self.json_headers, self.extra_environ_admin, status=400)
            resp = response.json_body
            assert resp['error'] == \
                'The update request failed because the submitted data were not new.'
            assert response.content_type == 'application/json'

            # Now update by removing one of the files and expect success.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test_create_title',
                'markup_language': 'Markdown',
                'contents': md_contents,
                'tags': tags,
                'files': files[0:1]
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=created_collection_id), params,
                            self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            assert new_collection_count == collection_count
            assert len(resp['files']) == 1
            assert restricted_tag.name in [t['name'] for t in resp['tags']]
            assert response.content_type == 'application/json'

            # Attempt to create a form with some *invalid* files and tags and fail.
            params = self.collection_create_params.copy()
            params.update({
                'title': 'test_create_title',
                'markup_language': 'Markdown',
                'contents': md_contents,
                'tags': [1000, 9875, 'abcdef'],
                'files': [44, '1t']
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    self.extra_environ_admin, status=400)
            collection_count = new_collection_count
            new_collection_count = dbsession.query(old_models.Collection).count()
            resp = response.json_body
            assert new_collection_count == collection_count
            assert 'Please enter an integer value' in resp['errors']['files']
            assert 'There is no file with id 44.' in resp['errors']['files']
            assert 'There is no tag with id 1000.' in resp['errors']['tags']
            assert 'There is no tag with id 9875.' in resp['errors']['tags']
            assert 'Please enter an integer value' in resp['errors']['tags']
            assert response.content_type == 'application/json'

    def test_delete(self):
        """Tests that DELETE /collections/id deletes the collection with id=id and returns a JSON representation.

        If the id is invalid or unspecified, then JSON null or a 404 status code
        are returned, respectively.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            original_contributor_id = dbsession.query(old_models.User).filter(
                old_models.User.role=='contributor').first().id
            # Add some objects to the db: a default application settings, a speaker,
            # a tag, a file ...
            application_settings = omb.generate_default_application_settings()
            speaker = omb.generate_default_speaker()
            my_contributor = omb.generate_default_user()
            my_contributor.username = 'uniqueusername'
            tag = old_models.Tag()
            tag.name = 'default tag'
            file = omb.generate_default_file()
            dbsession.add_all([application_settings, speaker, my_contributor, tag, file])
            dbsession.flush()
            tag_id = tag.id
            file_id = file.id
            speaker_id = speaker.id
            speaker_first_name = speaker.first_name
            transaction.commit()
            my_contributor = dbsession.query(old_models.User).filter(
                old_models.User.username=='uniqueusername').first()
            my_contributor_id = my_contributor.id
            my_contributor_first_name = my_contributor.first_name

            # Add a form for testing
            params = self.form_create_params.copy()
            params.update({
                'transcription': 'test_delete_transcription',
                'translations': [{'transcription': 'test_delete_translation', 'grammaticality': ''}]
            })
            params = json.dumps(params)
            response = self.app.post(forms_url('create'), params, self.json_headers, self.extra_environ_admin)
            resp = response.json_body
            form_id = resp['id']

            # Count the original number of collections and collection_backups.
            collection_count = dbsession.query(old_models.Collection).count()
            collection_backup_count = dbsession.query(old_models.CollectionBackup).count()

            # First, as my_contributor, create a collection to delete.
            md_contents = '\n'.join([
                'Chapter',
                '=======',
                '',
                'Section',
                '-------',
                '',
                '* Item 1',
                '* Item 2',
                '',
                'Section containing forms',
                '------------------------',
                '',
                'form[%d]' % form_id
            ])
            extra_environ = {'test.authentication.id': my_contributor_id}
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Test Delete',
                'speaker': speaker_id,
                'tags': [tag_id],
                'files': [file_id],
                'markup_language': 'Markdown',
                'contents': md_contents
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                                    extra_environ)
            resp = response.json_body
            to_delete_id = resp['id']
            assert resp['title'] == 'Test Delete'
            assert resp['speaker']['first_name'] == speaker_first_name
            assert resp['tags'][0]['name'] == 'default tag'
            assert resp['files'][0]['name'] == 'test_file_name'
            assert resp['forms'][0]['transcription'] == 'test_delete_transcription'

            # Now count the collections and collection_backups.
            new_collection_count = dbsession.query(old_models.Collection).count()
            new_collection_backup_count = dbsession.query(old_models.CollectionBackup).count()
            assert new_collection_count == collection_count + 1
            assert new_collection_backup_count == collection_backup_count

            # Now, as the default contributor, attempt to delete the my_contributor-
            # entered collection we just created and expect to fail.
            extra_environ = {'test.authentication.id': original_contributor_id}
            response = self.app.delete(url('delete', id=to_delete_id),
                                    extra_environ=extra_environ, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'
            assert response.content_type == 'application/json'

            # As my_contributor, attempt to delete the collection we just created and
            # expect to succeed.  Show that models related via many-to-many relations
            # (e.g., tags and files) and via many-to-one relations (e.g., speakers)
            # are not deleted.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.delete(url('delete', id=to_delete_id),
                                    extra_environ=extra_environ)
            resp = response.json_body
            new_collection_count = dbsession.query(old_models.Collection).count()
            new_collection_backup_count = dbsession.query(old_models.CollectionBackup).count()
            tag_of_deleted_collection = dbsession.query(old_models.Tag).get(
                resp['tags'][0]['id'])
            file_of_deleted_collection = dbsession.query(old_models.File).get(
                resp['files'][0]['id'])
            speaker_of_deleted_collection = dbsession.query(old_models.Speaker).get(
                resp['speaker']['id'])
            assert isinstance(tag_of_deleted_collection, old_models.Tag)
            assert isinstance(file_of_deleted_collection, old_models.File)
            assert isinstance(speaker_of_deleted_collection, old_models.Speaker)
            assert new_collection_count == collection_count
            assert new_collection_backup_count == collection_backup_count + 1
            assert response.content_type == 'application/json'

            # The deleted collection will be returned to us, so the assertions from above
            # should still hold true.
            assert resp['title'] == 'Test Delete'

            # Trying to get the deleted collection from the db should return None
            deleted_collection = dbsession.query(old_models.Collection).get(to_delete_id)
            assert deleted_collection == None

            # The backed up collection should have the deleted collection's attributes
            backed_up_collection = dbsession.query(old_models.CollectionBackup).filter(
                old_models.CollectionBackup.UUID==resp['UUID']).first()
            assert backed_up_collection.title == resp['title']
            modifier = json.loads(backed_up_collection.modifier)
            assert modifier['first_name'] == my_contributor_first_name
            backed_up_speaker = json.loads(backed_up_collection.speaker)
            assert backed_up_speaker['first_name'] == speaker_first_name
            assert backed_up_collection.datetime_entered.isoformat() == resp['datetime_entered']
            assert backed_up_collection.UUID == resp['UUID']
            assert response.content_type == 'application/json'

            # Delete with an invalid id
            id = 9999999999999
            response = self.app.delete(url('delete', id=id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin,
                status=404)
            assert 'There is no collection with id %s' % id in response.json_body['error']
            assert response.content_type == 'application/json'

            # Delete without an id
            response = self.app.delete(url('delete', id=''), status=404,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'The resource could not be found.'
            assert response.content_type == 'application/json'

    def test_show(self):
        """Tests that GET /collection/id returns a JSON collection object, null or 404
        depending on whether the id is valid, invalid or unspecified, respectively.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # First add a collection.
            collection = old_models.Collection()
            collection.title = 'Title'
            dbsession.add(collection)
            transaction.commit()
            collection_id = db.get_models_by_name('Collection')[0].id

            # Invalid id
            id = 100000000000
            response = self.app.get(url('show', id=id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin,
                status=404)
            resp = response.json_body
            assert 'There is no collection with id %s' % id in response.json_body['error']
            assert response.content_type == 'application/json'

            # No id
            response = self.app.get(url('show', id=''), status=404,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == \
                'The resource could not be found.'
            assert response.content_type == 'application/json'

            # Valid id
            response = self.app.get(url('show', id=collection_id), headers=self.json_headers,
                                    extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['title'] == 'Title'
            assert response.content_type == 'application/json'

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
            dbsession.flush()
            my_contributor_id = my_contributor.id
            restricted_tag_id = restricted_tag.id
            transaction.commit()

            # Then add the default application settings with my_contributor as the
            # only unrestricted user.
            application_settings = omb.generate_default_application_settings()
            application_settings.unrestricted_users = [my_contributor]
            dbsession.add(application_settings)
            transaction.commit()
            # Finally, issue a POST request to create the restricted collection with
            # the *default* contributor as the enterer.
            extra_environ = {'test.authentication.id': contributor_id}
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Test Restricted Tag',
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            extra_environ)
            resp = response.json_body
            restricted_collection_id = resp['id']
            # Expectation: the administrator, the default contributor (qua enterer)
            # and the unrestricted my_contributor should all be able to view the collection.
            # The viewer should get a 403 error when attempting to view this collection.
            extra_environ = {'test.authentication.role': 'administrator'}
            response = self.app.get(url('show', id=restricted_collection_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            # The default contributor (qua enterer) should be able to view this collection.
            extra_environ = {'test.authentication.id': contributor_id}
            response = self.app.get(url('show', id=restricted_collection_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            # Mycontributor (an unrestricted user) should be able to view this
            # restricted collection.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.get(url('show', id=restricted_collection_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            # A (not unrestricted) viewer should *not* be able to view this collection.
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('show', id=restricted_collection_id),
                headers=self.json_headers, extra_environ=extra_environ, status=403)
            # Remove Mycontributor from the unrestricted users list and access will be denied.
            application_settings = db.current_app_set
            application_settings.unrestricted_users = []
            dbsession.add(application_settings)
            transaction.commit()
            # Mycontributor (no longer an unrestricted user) should now *not* be
            # able to view this restricted collection.
            extra_environ = {'test.authentication.id': my_contributor_id}
            response = self.app.get(url('show', id=restricted_collection_id),
                headers=self.json_headers, extra_environ=extra_environ, status=403)
            assert response.content_type == 'application/json'

            # Remove the restricted tag from the collection and the viewer should now be
            # able to view it too.
            restricted_collection = dbsession.query(old_models.Collection).get(restricted_collection_id)
            restricted_collection.tags = []
            dbsession.add(restricted_collection)
            transaction.commit()
            extra_environ = {'test.authentication.role': 'viewer'}
            response = self.app.get(url('show', id=restricted_collection_id),
                            headers=self.json_headers, extra_environ=extra_environ)
            assert response.content_type == 'application/json'

    def test_edit(self):
        """Tests that GET /collections/id/edit returns a JSON object of data necessary to edit the collection with id=id.

        The JSON object is of the form {'collection': {...}, 'data': {...}} or
        {'error': '...'} (with a 404 status code) depending on whether the id is
        valid or invalid/unspecified, respectively.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Add the default application settings and the restricted tag.
            application_settings = omb.generate_default_application_settings()
            restricted_tag = omb.generate_restricted_tag()
            dbsession.add_all([restricted_tag, application_settings])
            transaction.commit()
            restricted_tag = db.get_restricted_tag()
            # Create a restricted collection.
            collection = old_models.Collection()
            collection.title = 'Test'
            collection.tags = [restricted_tag]
            dbsession.add(collection)
            dbsession.flush()
            restricted_collection_id = collection.id
            transaction.commit()

            # As a (not unrestricted) contributor, attempt to call edit on the
            # restricted collection and expect to fail.
            extra_environ = {'test.authentication.role': 'contributor'}
            response = self.app.get(url('edit', id=restricted_collection_id),
                                    extra_environ=extra_environ, status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'
            assert response.content_type == 'application/json'

            # Not logged in: expect 401 Unauthorized
            response = self.app.get(url('edit', id=restricted_collection_id), status=401)
            resp = response.json_body
            assert resp['error'] == 'Authentication is required to access this resource.'
            assert response.content_type == 'application/json'

            # Invalid id
            id = 9876544
            response = self.app.get(url('edit', id=id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin,
                status=404)
            assert 'There is no collection with id %s' % id in response.json_body['error']
            assert response.content_type == 'application/json'

            # No id
            response = self.app.get(url('edit', id=''), status=404,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            assert response.json_body['error'] == 'The resource could not be found.'
            assert response.content_type == 'application/json'

            # Valid id
            response = self.app.get(url('edit', id=restricted_collection_id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['collection']['title'] == 'Test'
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
            foreign_word_tag = omb.generate_foreign_word_tag()
            speaker = omb.generate_default_speaker()
            source = omb.generate_default_source()
            dbsession.add_all([application_settings, foreign_word_tag, speaker, source])
            transaction.commit()

            # Get the data currently in the db (see websetup.py for the test data).
            data = {
                'speakers': db.get_mini_dicts_getter('Speaker')(),
                'users': db.get_mini_dicts_getter('User')(),
                'tags': db.get_mini_dicts_getter('Tag')(),
                'sources': db.get_mini_dicts_getter('Source')()
            }

            # JSON.stringify and then re-Python-ify the data.  This is what the data
            # should look like in the response to a simulated GET request.
            data = json.loads(json.dumps(data))

            params = {
                # Value is a non-empty string: 'tags' will be in response.
                'tags': 'give me some tags!',
                # Value is empty string: 'speakers' will not be in response.
                'speakers': '',
                # Value is ISO 8601 UTC datetime string that does not match the most
                # recent Source.datetime_modified value: 'sources' *will* be in
                # response.
                'sources': datetime.datetime.utcnow().isoformat(),
                # Value is ISO 8601 UTC datetime string that does match the most
                # recent User.datetime_modified value: 'users' will *not* be in response.
                'users': db.get_most_recent_modification_datetime('User').isoformat()
            }
            response = self.app.get(url('edit', id=restricted_collection_id), params,
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert resp['data']['tags'] == data['tags']
            assert resp['data']['speakers'] == []
            assert resp['data']['users'] == []
            assert resp['data']['sources'] == data['sources']
            assert set(resp['data']['collection_types']) == set(oldc.COLLECTION_TYPES)
            assert set(resp['data']['markup_languages']) == set(oldc.MARKUP_LANGUAGES)
            assert response.content_type == 'application/json'

            # Invalid id with GET params.  It should still return 'null'.
            params = {
                # If id were valid, this would cause a speakers array to be returned
                # also.
                'speakers': 'True',
            }
            response = self.app.get(url('edit', id=id), params,
                                extra_environ=self.extra_environ_admin, status=404)
            assert 'There is no collection with id %s' % id in response.json_body['error']

    def test_history(self):
        """Tests that GET /collections/id/history returns the collection with id=id and its previous incarnations.

        The JSON object returned is of the form
        {'collection': collection, 'previous_versions': [...]}.
        """
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            # Add some test data to the database.
            application_settings = omb.generate_default_application_settings()
            source = omb.generate_default_source()
            restricted_tag = omb.generate_restricted_tag()
            file1 = omb.generate_default_file()
            file1.name = 'file1'
            file2 = omb.generate_default_file()
            file2.name = 'file2'
            speaker = omb.generate_default_speaker()
            dbsession.add_all([application_settings, source, restricted_tag, file1,
                            file2, speaker])
            dbsession.flush()
            speaker_id = speaker.id
            restricted_tag_id = restricted_tag.id
            tag_ids = [restricted_tag_id]
            file1_id = file1.id
            file2_id = file2.id
            file_ids = [file1_id, file2_id]
            transaction.commit()

            # Create a restricted collection (via request) as the default contributor
            users = db.get_users()
            contributor_id = [u for u in users if u.role=='contributor'][0].id
            administrator_id = [u for u in users if u.role=='administrator'][0].id

            extra_environ = {'test.authentication.role': 'contributor'}
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Created by the Contributor',
                'elicitor': contributor_id,
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            extra_environ)
            collection_count = dbsession.query(old_models.Collection).count()
            resp = response.json_body
            collection_id = resp['id']
            collection_UUID = resp['UUID']
            assert collection_count == 1
            assert response.content_type == 'application/json'

            # Update our collection (via request) as the default administrator
            extra_environ = {'test.authentication.role': 'administrator'}
            params = self.collection_create_params.copy()
            params.update({
                'url': 'find/me/here',
                'title': 'Updated by the Administrator',
                'speaker': speaker_id,
                'tags': tag_ids + [None, ''], # None and '' ('') will be ignored by collections.update_collection
                'enterer': administrator_id  # This should change nothing.
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=collection_id), params,
                            self.json_headers, extra_environ)
            resp = response.json_body
            collection_count = dbsession.query(old_models.Collection).count()
            assert collection_count == 1
            assert response.content_type == 'application/json'

            # Finally, update our collection (via request) as the default contributor.
            extra_environ = {'test.authentication.role': 'contributor'}
            params = self.collection_create_params.copy()
            params.update({
                'title': 'Updated by the Contributor',
                'speaker': speaker_id,
                'tags': tag_ids,
                'files': file_ids
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=collection_id), params,
                            self.json_headers, extra_environ)
            resp = response.json_body
            collection_count = dbsession.query(old_models.Collection).count()
            assert collection_count == 1
            assert response.content_type == 'application/json'

            # Now get the history of this collection.
            extra_environ = {'test.authentication.role': 'contributor'}
            response = self.app.get(
                url('history', id=collection_id),
                headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert 'collection' in resp
            assert 'previous_versions' in resp
            first_version = resp['previous_versions'][1]
            second_version = resp['previous_versions'][0]
            current_version = resp['collection']
            assert first_version['title'] == 'Created by the Contributor'
            assert first_version['elicitor']['id'] == contributor_id
            assert first_version['enterer']['id'] == contributor_id
            assert first_version['modifier']['id'] == contributor_id
            # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
            # so the test will fail/be inconsistent with <
            assert first_version['datetime_modified'] <= second_version['datetime_modified']
            assert first_version['speaker'] == None
            assert [t['id'] for t in first_version['tags']] == [restricted_tag_id]
            assert first_version['files'] == []
            assert response.content_type == 'application/json'

            assert second_version['title'] == 'Updated by the Administrator'
            assert second_version['elicitor'] == None
            assert second_version['enterer']['id'] == contributor_id
            assert second_version['modifier']['id'] == administrator_id
            assert second_version['datetime_modified'] <= current_version['datetime_modified']
            assert second_version['speaker']['id'] == speaker_id
            assert sorted([t['id'] for t in second_version['tags']]) == sorted(tag_ids)
            assert second_version['files'] == []

            assert current_version['title'] == 'Updated by the Contributor'
            assert current_version['elicitor'] == None
            assert current_version['enterer']['id'] == contributor_id
            assert current_version['speaker']['id'] == speaker_id
            assert current_version['modifier']['id'] == contributor_id
            assert sorted([t['id'] for t in current_version['tags']]) == sorted(tag_ids)
            assert sorted([f['id'] for f in current_version['files']]) == sorted(file_ids)

            # Attempt to get the history of the just-entered restricted collection as a
            # viewer and expect to fail with 403.
            extra_environ_viewer = {'test.authentication.role': 'viewer'}
            response = self.app.get(
                url('history', id=collection_id),
                headers=self.json_headers, extra_environ=extra_environ_viewer,
                status=403)
            resp = response.json_body
            assert resp['error'] == 'You are not authorized to access this resource.'

            # Attempt to call history with an invalid id and an invalid UUID and
            # expect 404 errors in both cases.
            bad_id = 103
            bad_UUID = str(uuid4())
            response = self.app.get(
                url('history', id=bad_id),
                headers=self.json_headers, extra_environ=extra_environ,
                status=404)
            resp = response.json_body
            assert resp['error'] == 'No collections or collection backups match %d' % bad_id
            response = self.app.get(
                url('history', id=bad_UUID),
                headers=self.json_headers, extra_environ=extra_environ,
                status=404)
            resp = response.json_body
            assert resp['error'] == 'No collections or collection backups match %s' % bad_UUID

            # Now delete the collection ...
            response = self.app.delete(url('delete', id=collection_id),
                            headers=self.json_headers, extra_environ=extra_environ)

            # ... and get its history again, this time using the collection's UUID
            response = self.app.get(
                url('history', id=collection_UUID),
                headers=self.json_headers, extra_environ=extra_environ)
            by_UUID_resp = response.json_body
            assert by_UUID_resp['collection'] == None
            assert len(by_UUID_resp['previous_versions']) == 3
            first_version = by_UUID_resp['previous_versions'][2]
            second_version = by_UUID_resp['previous_versions'][1]
            third_version = by_UUID_resp['previous_versions'][0]
            assert first_version['title'] == 'Created by the Contributor'
            assert first_version['elicitor']['id'] == contributor_id
            assert first_version['enterer']['id'] == contributor_id
            assert first_version['modifier']['id'] == contributor_id
            # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
            # so the test will fail/be inconsistent with <
            assert first_version['datetime_modified'] <= second_version['datetime_modified']
            assert first_version['speaker'] == None
            assert [t['id'] for t in first_version['tags']] == [restricted_tag_id]
            assert first_version['files'] == []

            assert second_version['title'] == 'Updated by the Administrator'
            assert second_version['elicitor'] == None
            assert second_version['enterer']['id'] == contributor_id
            assert second_version['modifier']['id'] == administrator_id
            # Should be <; however, MySQL<5.6.4 does not support microseconds in datetimes 
            # so the test will fail/be inconsistent with <
            assert second_version['datetime_modified'] <= third_version['datetime_modified']
            assert second_version['speaker']['id'] == speaker_id
            assert sorted([t['id'] for t in second_version['tags']]) == sorted(tag_ids)
            assert second_version['files'] == []

            assert third_version['title'] == 'Updated by the Contributor'
            assert third_version['elicitor'] == None
            assert third_version['enterer']['id'] == contributor_id
            assert third_version['modifier']['id'] == contributor_id
            assert third_version['speaker']['id'] == speaker_id
            assert sorted([t['id'] for t in third_version['tags']]) == sorted(tag_ids)
            assert sorted([f['id'] for f in third_version['files']]) == sorted(file_ids)

            # Get the deleted collection's history again, this time using its id.  The 
            # response should be the same as the response received using the UUID.
            response = self.app.get(
                url('history', id=collection_id),
                headers=self.json_headers, extra_environ=extra_environ)
            by_collection_id_resp = response.json_body
            assert by_collection_id_resp == by_UUID_resp

            # Create a new restricted collection as an administrator.
            params = self.collection_create_params.copy()
            params.update({
                'title': '2nd collection restricted',
                'tags': [restricted_tag_id]
            })
            params = json.dumps(params)
            response = self.app.post(url('create'), params, self.json_headers,
                            self.extra_environ_admin)
            resp = response.json_body
            collection_count = dbsession.query(old_models.Collection).count()
            collection_id = resp['id']
            collection_UUID = resp['UUID']
            assert collection_count == 1

            # Update the just-created collection by removing the restricted tag.
            params = self.collection_create_params.copy()
            params.update({
                'title': '2nd collection unrestricted',
                'tags': []
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=collection_id), params,
                            self.json_headers, self.extra_environ_admin)
            resp = response.json_body

            # Now update it in another way.
            params = self.collection_create_params.copy()
            params.update({
                'title': '2nd collection unrestricted updated',
                'tags': []
            })
            params = json.dumps(params)
            response = self.app.put(url('update', id=collection_id), params,
                            self.json_headers, self.extra_environ_admin)
            resp = response.json_body

            # Get the history of the just-entered restricted collection as a
            # contributor and expect to receive only the '2nd collection' version in the
            # previous_versions.
            response = self.app.get(
                url('history', id=collection_id),
                headers=self.json_headers, extra_environ=extra_environ)
            resp = response.json_body
            assert len(resp['previous_versions']) == 1
            assert resp['previous_versions'][0]['title'] == \
                '2nd collection unrestricted'
            assert resp['collection']['title'] == '2nd collection unrestricted updated'
            assert response.content_type == 'application/json'

            # Now get the history of the just-entered restricted collection as an
            # administrator and expect to receive both backups.
            response = self.app.get(
                url('history', id=collection_id),
                headers=self.json_headers, extra_environ=self.extra_environ_admin)
            resp = response.json_body
            assert len(resp['previous_versions']) == 2
            assert resp['previous_versions'][0]['title'] == \
                '2nd collection unrestricted'
            assert resp['previous_versions'][1]['title'] == \
                '2nd collection restricted'
            assert resp['collection']['title'] == '2nd collection unrestricted updated'
            assert response.content_type == 'application/json'

    def test_new_search(self):
        """Tests that GET /collections/new_search returns the search parameters for searching the collections resource."""
        with transaction.manager:
            dbsession = self.get_dbsession()
            db = DBUtils(dbsession, self.settings)

            query_builder = SQLAQueryBuilder(
                dbsession, 'Collection', settings=self.settings)
            response = self.app.get(url('new_search'), headers=self.json_headers,
                                    extra_environ=self.extra_environ_view)
            resp = response.json_body
            assert resp['search_parameters'] == query_builder.get_search_parameters()
