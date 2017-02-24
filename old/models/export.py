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

"""Export model"""

import logging

from sqlalchemy import Column, Sequence, ForeignKey
from sqlalchemy.types import (
    Integer,
    Unicode,
    UnicodeText,
    DateTime,
    Boolean
)
from sqlalchemy.orm import relation

from .meta import Base


LOGGER = logging.getLogger(__name__)


class Export(Base):
    """An export represents the export of the data in an OLD instance.

    Provenance information using PROV ontology: "This export was created by an
    activity of export creation, which started at datetime X and ended at
    datetime Y, and which used a software agent, i.e., a specific OLD instance."

    @prefix foaf: <http://xmlns.com/foaf/0.1/> .
    @prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
    @prefix dcterms: <http://purl.org/dc/terms/> .
    @prefix prov:    <http://www.w3.org/ns/prov#> .

    :this_export
      a prov:Entity;
      prov:wasGeneratedBy :old_dataset_creation;
      dcterms:title "<ExportName>"^^xsd:string;
    .

    :old_dataset_creation
      a prov:Activity;
      prov:generated :this_export;
      prov:used :old_instance;
      prov:startedAtTime "2012-04-15T13:00:00-04:00"^^xsd:dateTime;
      prov:endedAtTime "2012-04-15T13:00:00-04:00"^^xsd:dateTime;
    .

    :old_instance
      a prov:SoftwareAgent;
      foaf:name "<LanguageName> OLD (<version>) at <URL>";
    .

    TODOs:
    - For http://purl.org/dc/terms/rightsHolder
      - *** look into rightsstatements.org ***
      - look at Europeanna rights statements
    """

    __tablename__ = 'export'

    def __repr__(self):
        return '<Export (%s)>' % self.id

    id = Column(Integer, Sequence('export_seq_id', optional=True),
                primary_key=True)
    UUID = Column(Unicode(36))
    # The "name" of the export is the dc_title; see below.
    public = Column(
        Boolean, default=False,
        doc='A public export is made accessible on the Internet for all to'
        ' access. By default, OLD exports are not public. A non-public export is'
        ' accessible only to account holders of the OLD it is a part of.')
    enterer_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'))
    enterer = relation(
        'User', primaryjoin='Export.enterer_id==User.id',
        doc='The OLD user who created the export.')
    datetime_entered = Column(DateTime)
    datetime_modified = Column(DateTime)
    generate_succeeded = Column(
        Boolean, default=False,
        doc='Indicates whether the attempt to generate the export was'
        ' successful or not.')
    generate_message = Column(
        Unicode(255),
        doc='String that indicates what happened in the attempt to generate the'
        ' export.')
    generate_attempt = Column(
        Unicode(36),
        doc='A UUID value that is updated when the attempt to generate the'
        ' export has ended. A change in this value indicates that the generate'
        ' attempt is over.')

    # Export Metadata

    # BagIt reserved metadata elements:

    # Default to export creator's affiliation
    source_organization = Column(
        Unicode(510),
        doc='BagIt Source-Organization: Organization transferring the content.'
            ' See https://tools.ietf.org/html/draft-kunze-bagit-08#section-2.2.2')
    organization_address = Column(
        Unicode(510),
        doc='BagIt Organization-Address: Mailing address of the organization.'
            ' See https://tools.ietf.org/html/draft-kunze-bagit-08#section-2.2.2')
    # Default to export creator's full name
    contact_name = Column(
        Unicode(510),
        doc='BagIt Contact-Name: Person at the source organization who is'
            ' responsible for the content transfer. See'
            ' https://tools.ietf.org/html/draft-kunze-bagit-08#section-2.2.2')
    contact_phone = Column(
        Unicode(510),
        doc='BagIt Contact-Phone: International format telephone number of'
            ' person or position responsible. See'
            ' https://tools.ietf.org/html/draft-kunze-bagit-08#section-2.2.2')
    # Default to export creator's email
    contact_email = Column(
        Unicode(510),
        doc='BagIt Contact-Email: Fully qualified email address of person or'
            ' position responsible. See'
            ' https://tools.ietf.org/html/draft-kunze-bagit-08#section-2.2.2')

    # Dublin Core (DCMI) terms
    # These should all be from the 15 core DCMI properties
    # dc: http://purl.org/dc/elements/1.1/

    # http://purl.org/dc/elements/1.1/contributor
    # Contains an auto-generated value, which is a meaningfully ordered list
    # of dc:contributor names as a JSON array. See export_worker.py for how
    # it is generated on a per-export basis during export generation:
    # essentially all speakers, elicitors, enterers and modifiers are listed
    # here.
    # TODO: potentially allow for export-creator override of this value.
    dc_contributor = Column(
        UnicodeText,
        doc='Contributor: An entity responsible for making contributions to'
        ' the resource.')

    # http://purl.org/dc/elements/1.1/creator
    # Contains an auto-generated value, which is the list of speakers and then
    # elicitors, as strings. See export_worker.py for how it is generated on a
    # per-export basis: essentially all speakers and elicitors.
    dc_creator = Column(
        UnicodeText,
        doc='Creator: An entity primarily responsible for making the resource.')

    # http://purl.org/dc/elements/1.1/publisher
    dc_publisher = Column(
        UnicodeText,
        doc='Publisher: An entity responsible for making the resource'
            ' available.')

    # http://purl.org/dc/elements/1.1/date
    # Note: also using PROV OWL ontology for the started at and ended at
    # datetimes of the dataset creation activity. See export_worker.py.
    dc_date = Column(
        Unicode(510),
        doc='Date: A point or period of time associated with an event in the'
        ' lifecycle of the resource.')

    # http://purl.org/dc/elements/1.1/description
    dc_description = Column(
        Unicode(510),
        doc='Description: An account of the resource.')

    # http://purl.org/dc/elements/1.1/format
    dc_format = Column(
        Unicode(510),
        doc='Format: The file format, physical medium, or dimensions of the'
        ' resource.')

    # http://purl.org/dc/elements/1.1/identifier
    dc_identifier = Column(
        Unicode(510),
        doc='Identifier: An unambiguous reference to the resource within a'
        ' given context.')

    # http://purl.org/dc/elements/1.1/language
    dc_language = Column(
        Unicode(510),
        doc='Language: A language of the resource.')

    # http://purl.org/dc/elements/1.1/relation
    dc_relation = Column(
        Unicode(510),
        doc='A related resource.')

    # http://purl.org/dc/elements/1.1/coverage
    dc_coverage = Column(
        Unicode(510),
        doc='The spatial or temporal topic of the resource, the spatial'
            ' applicability of the resource, or the jurisdiction under which'
            ' the resource is relevant.')

    # http://purl.org/dc/elements/1.1/rights
    dc_rights = Column(
        UnicodeText,
        doc='Rights: Information about rights held in and over the resource.')

    # http://purl.org/dc/elements/1.1/subject
    # - Ideas:
    #   - keywords: linguistics, language documentation, linguistic fieldwork,
    #     linguistic theory, endangered languages, etc.
    #   - Use library of congress controlled vocabulary items
    #   - look for more specific linguistic controlled vocabulary items
    dc_subject = Column(
        Unicode(510),
        doc='Subject: The topic of the resource.')

    # http://purl.org/dc/elements/1.1/title
    # - Ideas: the name of the export.
    dc_title = Column(
        Unicode(510),
        doc='Title: A name given to the resource.')

    # http://purl.org/dc/elements/1.1/type
    # - Ideas: default to DataSet, i.e., http://purl.org/dc/dcmitype/Dataset
    dc_type = Column(
        Unicode(510),
        doc='Type: The nature or genre of the resource.',
        default='Dataset')

    # DCTERMS: dcterms: http://purl.org/dc/terms/ --- HOLDING OFF ON THESE for
    # now because they are not simple literal values and will not be processed
    # intelligently in the AM metadata.csv file (for example). See
    # http://wiki.dublincore.org/index.php/User_Guide/Publishing_Metadata
    # for handy examples of using the following.

    """

    # http://purl.org/dc/terms/accrualMethod
    # Default: references the OLD instance used to build the data set.
    # type: Property
    # domain: Collection
    # range: MethodOfAccrual
    dcterms_accrual_method = Column(
        Unicode(510),
        doc='Accrual Method: The method by which items are added to a'
        ' collection.')

    # http://purl.org/dc/terms/replaces
    # Default: reference the next oldest (public, successfully generated) data
    # set, if there is one.
    # type: Property
    # This property is intended to be used with non-literal values.
    dcterms_replaces = Column(
        Unicode(510),
        doc='Replaces: A related resource that is supplanted, displaced, org'
        ' superseded by the described resource.')

    # http://purl.languageorg/dc/terms/bibliographicCitation
    # - Ideas: a bibliographic citation, i.e., how should this data set be
    #   cited, e.g., "Creator1Lastname et al. 2017. LanguageName OLD data set.
    #   Last retrieved on Feb 15, 2017 at https://..."
    # type: Property
    # domain: BibliographicResource
    # range: literal
    dcterms_bibliographic_citation = Column(
        Unicode(510),
        doc='Bibliographic Citation: A bibliographic reference for the'
        ' resource.')

    # http://purl.org/dc/terms/license
    # type: Property
    # range: LicenseDocument
    dcterms_license = Column(
        UnicodeText,
        doc='A legal document giving official permission to do something with'
        ' the resource.')

    # http://purl.org/dc/terms/rightsHolder
    # type: Property
    # range: Agent
    dcterms_rights_holder = Column(
        Unicode(510),
        doc='Rights Holder: A person or organization owning or managing rights'
        ' over the resource.')

    # http://purl.org/dc/terms/references
    # - this field could be used for the source attribute of old forms and for
    #   the entire data set
    # type: Property
    # This property is intended to be used with non-literal values.
    dcterms_references = Column(
        Unicode(510),
        doc='References: A related resource that is referenced, cited, or'
        ' otherwise pointed to by the described resource.')
    """

    def get_dict(self):
        return {
            'id': self.id,
            'UUID': self.UUID,
            'public': self.public,
            'enterer': self.get_mini_user_dict(self.enterer),
            'datetime_entered': self.datetime_entered,
            'datetime_modified': self.datetime_modified,
            'generate_succeeded': self.generate_succeeded,
            'generate_message': self.generate_message,
            'generate_attempt': self.generate_attempt,
            # BagIt metadata
            'source_organization': self.source_organization,
            'organization_address': self.organization_address,
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'contact_email': self.contact_email,
            # Dublin Core (dc:) terms http://purl.org/dc/elements/1.1/
            'dc_contributor': self.dc_contributor,
            'dc_creator': self.dc_creator,
            'dc_publisher': self.dc_publisher,
            'dc_date': self.dc_date,
            'dc_description': self.dc_description,
            'dc_format': self.dc_format,
            'dc_identifier': self.dc_identifier,
            'dc_language': self.dc_language,
            'dc_relation': self.dc_relation,
            'dc_coverage': self.dc_coverage,
            'dc_rights': self.dc_rights,
            'dc_subject': self.dc_subject,
            'dc_title': self.dc_title,
            'dc_type': self.dc_type
        }

