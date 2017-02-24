# Copyright 2017 Joel Dunham
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

"""Contains the :class:`ExportView` for exporting the entire data set.
Current targetted export format: Bagged JSON-LD.

Sprint 1---Basic:

    X export of entire data set
    X access files (.jsonld, media files) over HTTP
    X download entire export as zipped bag (https://en.wikipedia.org/wiki/BagIt)
    - separate export thread
    - fully public in exports/public/

- Options
  - entire data set, fully public
  - entire data set, fully private
  - entire data set, fully public, private parts encrypted
  - partial data set, fully public, private parts removed

- Public vs Private exports in distinct directories:

  - exports/public/
  - exports/private/

  - The server will be configured to serve everything in exports/public/
    openly. In contrast, access to exports/private/ would be routed through the
    standard OLD/Pyramid auth mechanism.

- Directory structure and archive of entire export (.7z, .tar.gz, .zip)?
  - choose one or offer several options?

- BagIt Specification Conformance
  - https://en.wikipedia.org/wiki/BagIt
  - https://github.com/LibraryOfCongress/bagit-python

- Export type "Partially Encrypted":

  - GnuPG encryption private/public key-based encryption
  - No encryption is the default
  - Special tags used for encrypting specified resources

    - During export creation, user specifies "export encryption prefix", which
      is an OLD tag prefix, e.g., "export-2017-02-01-encrypt"
    - During export, if a resource is tagged with a tag that begins with the
      the "export encryption prefix", then it is encrypted with access
      determined by the suffix of the tag name.
    - For example, "export-2017-02-01-encrypt:all" would mean that all users on
      the OLD instance with known public GPG keys would be able to decrypt.
    - For example, "export-2017-02-01-encrypt:username1,username2" would mean
      that only users with the usernames "username1" and "username2" would be
      able to decrypt that particular resource.
    - Encryption tagging would have to generalize from OLD file resources to
      the associated digital/binary file content. Similarly for other resources
      which are one-to-one associated to binary files, e.g., morphological
      parsers, corpora.

Requirements:

1. Exports are resources that can be:

   a. Created
   b. Read (singleton or collection)
   c. Deleted (if admin)

2. An OLD export is:
   - a .zip file containing all of the data in an OLD at a particular
     moment in time.
   - files are organized according to the bag-it specification
   - the database is serialized to JSON-LD
   - the export should be importable into another OLD system

3. Created in a separate thread.
   - the client must poll the OLD in order to determine when the export is
     complete.
   - the export should be saved to disk and be efficiently retrievable (a
     static asset, with or without authentication required, see
     http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/assets.html)
   - checked for consistency and repaired, if necessary
     how? get all lastmod times for all resources prior to export
     generation and then re-check them prior to export save?

"""

import json
import logging
import mimetypes
import os
from uuid import uuid4

import pyramid.httpexceptions as exc
from pyramid.response import FileResponse
from sqlalchemy.sql import asc, desc, or_, and_
from sqlalchemy.orm import subqueryload
from sqlalchemy.inspection import inspect

from old.lib.constants import (
    DEFAULT_DELIMITER,
    FORM_REFERENCE_PATTERN,
    JSONDecodeErrorResponse,
    UNAUTHORIZED_MSG,
    UNKNOWN_CATEGORY,
    __version__,
)
from old.lib.dbutils import get_last_modified
import old.lib.helpers as h
from old.lib.introspectmodel import get_old_schema
from old.lib.export_worker import EXPORT_WORKER_Q
from old.lib.schemata import FormIdsSchema
import old.models as old_models
from old.views.resources import (
    Resources,
    SchemaState
)


LOGGER = logging.getLogger(__name__)
NO_UPDATE = {'error': 'Exports cannot be updated.'}


class Exports(Resources):
    """Generate responses to requests on export resources."""

    def generate(self):
        """After creating the export database model, the user must issue a PUT
        request to /exports/<id>/generate in order to call this method and
        generate the actual export on disk. This triggers export creation in a
        separate thread. The user must then poll GET /exports/<id> until the
        generate_attempt attribute of the export has changed.
        """
        export, id_ = self._model_from_id(eager=True)
        if not export:
            self.request.response.status_int = 404
            return {'error': 'There is no export with id %s' % id}
        EXPORT_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'generate_export',
            'args': {
                'export_id': id_,
                'user_id': self.logged_in_user.id,
                'settings': self.request.registry.settings
            }
        })
        return export

    def private_exports(self):
        """Private exports require authentication prior to access. This method
        handles GET requests to /private/-prefixed paths.
        """
        path = self.request.matchdict['path']
        LOGGER.debug('path provided to private_exports: %s', path)
        exports_dir_path = self.request.registry.settings['exports_dir']
        path = os.path.join(exports_dir_path, 'private', path)
        if os.path.isfile(path):
            filetype = mimetypes.guess_type(path, strict=False)[0]
            return FileResponse(
                path,
                request=self.request,
                content_type=filetype)
        else:
            raise exc.HTTPNotFound()

    # Export resources CANNOT be updated:
    def update(self):
        self.request.response.status_int = 404
        return NO_UPDATE

    def edit(self):
        self.request.response.status_int = 404
        return NO_UPDATE

    # TODO: when a user attempts to create an export and one is currently being
    # generated, we should maybe warn them of that prior to creating a new one...

    def _get_create_data(self, data):
        """Get the data required to create a new export as a dict."""
        user_data = self._get_user_data(data)

        # Add default (BagIt & DC) metadata values. In some cases, the user can
        # supply these values but in other cases they are always system-generated.

        UUID = str(uuid4())
        now = h.now()
        created_timestamp = int(now.timestamp())
        created_xsd = h.utc_datetime2xsd(now)
        user_model = self.logged_in_user
        lang_name = self.db.current_app_set.get_object_language_rep()

        # BagIt metadata

        # Source-Organization defaults to export creator's affiliation
        if not user_data['source_organization'] and user_model.affiliation:
            user_data['source_organization'] = user_model.affiliation
        # Contact-Name defaults to export creator's full name
        if not user_data['contact_name']:
            user_data['contact_name'] = '{} {}'.format(
                user_model.first_name, user_model.last_name)
        # Contact-Email defaults to export creator's email
        if not user_data['contact_name']:
            user_data['contact_email'] = user_model.email

        # Dublin Core (dc) metadata about the export / the data set

        # dc:identifier is always system-generated. Should we include the
        # ISO 639-3 language code of the object language in this id (if
        # available)?
        user_data['dc_identifier'] = 'old-export-{}-{}'.format(
            UUID, created_timestamp)

        # Create a default dc:title if the user has not supplied one.
        if not user_data['dc_title'].strip():
            if lang_name:
                user_data['dc_title'] = (
                    'Data Set of Linguistic Data on Language {} (created by the'
                    ' Online Linguistic Database)'.format(lang_name))
            else:
                user_data['dc_title'] = (
                    'Data Set of Linguistic Data {} (created by the Online'
                    ' Linguistic Database)'.format(UUID))

        # Create a default dc:description if the user has not supplied one.
        if not user_data['dc_description'].strip():
            if lang_name:
                user_data['dc_description'] = (
                    'A data set of linguistic data on language {}. This data set'
                    ' was created using the Online Linguistic Database (OLD),'
                    ' software for linguistic fieldwork, language documentation'
                    ' and linguistic analysis. The data set was exported to its'
                    ' present state on {}.'.format(lang_name, created_xsd))
            else:
                user_data['dc_description'] = (
                    'A data set of linguistic data. This data set'
                    ' was created using the Online Linguistic Database (OLD),'
                    ' software for linguistic fieldwork, language documentation'
                    ' and linguistic analysis. The data set was exported to its'
                    ' present state on {}.'.format(created_xsd))

        # Note: at present, the user cannot manually specify DC contributor or
        # creator values. These values are automatically generated during
        # export generation from the speakers, elicitors, enterers and
        # modifiers of the resources in the data set.

        # dc_publisher defaults to string describing this OLD instance.
        app_set = self.db.current_app_set
        old_instance_uri = self.request.registry.settings['uri']
        old_instance_name = h.get_old_instance_descriptive_name(
            app_set, old_instance_uri, __version__)
        if not user_data['dc_publisher']:
            user_data['dc_publisher'] = old_instance_name

        # TODO: implement dcterms_accrual_method
        # Create a default dcterms:accrualMethod if the user has not supplied
        # one. Here we reference the OLD instance used to build the data set.
        # if not user_data['accrual_method']:
        #     user_data['accrual_method'] = (
        #         'Resources (items) were added to this data set by means of the'
        #         ' {}.'.format(old_instance_name))

        # Note: dc_date is valuated in export_worker.py at the same time as the
        # prov: metadata.

        # Create a default dc:relation if the user has not supplied one. Here
        # we reference the URI of the most recent public exported data set of
        # the current OLD.
        # TODO: currently just references the dc:identifier. We need this to be
        # the actual URI for dereferencing the exported data set.
        # TODO: this will/can be more accurately modelled in future work via
        # dcterms:replaces
        if not user_data['dc_relation'] and user_data['public']:
            Export = old_models.Export
            last_public_generated_export = self.request.dbsession.query(
                Export).filter(and_(
                    Export.public == True,
                    Export.generate_succeeded == True)).order_by(
                        desc(Export.datetime_modified)).first()
            if last_public_generated_export:
                user_data['dc_relation'] = last_public_generated_export.dc_identifier

        user_data['dc_format'] = 'Zipped Bag (BagIt) containing JSON-LD.'

        # TODO: Use library of congress controlled vocabulary items or for more
        # domain/linguistics-specific controlled vocabulary items
        if not user_data['dc_subject']:
            user_data['dc_subject'] = json.dumps([
                'linguistics',
                'language docmentation',
                'linguistic fieldwork',
                'linguistic analysis'
            ])

        # Note: dc:bibliographicCitation is populated in export_worker.py if
        # the user does not supply it.

        # dc:language, if not supplied by the export creator, is a JSON array
        # of ISO 639-3 language Ids (object and meta), hopefully, or at the
        # very least their human-readable names.
        if not user_data['dc_language']:
            norm_obj_lang_id = self._get_normative_language_id(
                'object', self.db.current_app_set)
            norm_meta_lang_id = self._get_normative_language_id(
                'meta', self.db.current_app_set)
            languages = [lid for lid in [norm_obj_lang_id, norm_meta_lang_id]
                         if lid]
            if languages:
                user_data['dc_language'] = json.dumps(languages)

        # dc:rights, if not supplied by the export creator, is by default
        # a CC BY-SA license (if export is public) i.e., Creative Commons, by
        # attribution, share-alike license, which means that the rights
        # holder(s) assert copyright and only require that they be attributed
        # for their work and that others who reuse their work must do so under
        # the same license. This is the most restrictive of the "Free
        # Cultural Works" licenses. See
        # https://creativecommons.org/share-your-work/public-domain/freeworks/
        # for discussion.
        # https://creativecommons.org/licenses/by-sa/3.0/legalcode
        # TODO: this will/can be more accurately modelled in future work via
        # dcterms:license.
        if not user_data['dc_rights']:
            user_data['dc_rights'] = (
                'https://creativecommons.org/licenses/by-sa/3.0/legalcode')

        # Note: the model already defaults dc_type to the literal "Dataset"

        """
        'dc_subject': data['dc_subject'],
        """

        user_data.update({
            'UUID': UUID,
            'datetime_entered': now,
            'enterer': user_model,
            'generate_succeeded': False,
            'generate_message': '',
            'generate_attempt': str(uuid4())
        })
        return user_data

    # TODO: will generate override a user-supplied dc_contributor value?
    # TODO: will generate override a user-supplied dc_creator value?

    def _get_user_data(self, data):
        return {
            'public': data['public'],
            # BagIt metadata
            'source_organization': data['source_organization'],
            'organization_address': data['organization_address'],
            'contact_name': data['contact_name'],
            'contact_phone': data['contact_phone'],
            'contact_email': data['contact_email'],
            # Dublin Core Metadata Element Set Version 1.1 (dc:)
            'dc_contributor': data['dc_contributor'],
            'dc_creator': data['dc_creator'],
            'dc_publisher': data['dc_publisher'],
            'dc_date': data['dc_date'],
            'dc_description': data['dc_description'],
            'dc_relation': data['dc_relation'],
            'dc_coverage': data['dc_coverage'],
            'dc_language': data['dc_language'],
            'dc_rights': data['dc_rights'],
            'dc_subject': data['dc_subject'],
            'dc_title': data['dc_title'],
            'dc_type': data['dc_type']
        }

    def _get_update_data(self, user_data):
        return {}

    def _get_normative_language_id(self, lang_type, app_set):
        """Attempt to return the ISO 639-3 3-character language Id for the language
        of type ``lang_type``, i.e., the object language or the metalanguage. If Id
        is unavailable, return the language name. If that is unavailable, return
        the empty string.
        """
        if lang_type == 'object':
            lang_id = app_set.object_language_id
            lang_name = app_set.object_language_name.strip()
        else:
            lang_id = app_set.metalanguage_id
            lang_name = app_set.metalanguage_name.strip()
        Language = old_models.Language
        language_model = self.request.dbsession.query(
            Language).filter(Language.Id == lang_id).first()
        if language_model:
            return lang_id
        else:
            return lang_name
