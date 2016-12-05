#!/usr/bin/python

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

"""This executable updates an OLD 0.2.7 MySQL database and makes it compatible
with the OLD 1.0a2 data structure

Usage:

    $ ./old_update_db_0.2.7_1.1.py \
        -d mysql_db_name \
        -u mysql_username \
        -p mysql_password \
        [-f mysql_dump_file_path] \
        [--default-morphemes]

The script will print out a list of warnings or reminders to hand-edit some of
the data, as necessary.

The username and password supplied must have full db access, i.e., permission
to create, drop and alter databases, tables, etc.

If the optional ``mysql_dump_file_path`` parameter is not supplied,
ensure that your MySQL server contains an OLD 0.2.7 database called
``mysql_db_name``. If the dump file path paramter is supplied, this script
will drop any database called ``mysql_db_name``, recreate it and populate it
with the data from the dump file.

Please ensure that your MySQL installation is set up to use UTF-8 throughout.
This will probably mean making changes to your MySQL configuration file
(/etc/mysql/my.cnf in Debian systems), cf.
http://cameronyule.com/2008/07/configuring-mysql-to-use-utf-8/.

This script will change any non-UTF-8 databases, tables and columns to UTF-8
following the procedure outlined at
https://codex.wordpress.org/Converting_Database_Character_Sets.  It will also
perform unicode canonical decompositional normalization on all the data.

Notes on character sets

Get info on the system generally:

    $ show variables like "collation%";
    $ show variables like "character_set%";

Get info on the databases:

    $ select schema_name, default_character_set_name, default_collation_name from information_schema.schemata;

Get info on the tables:

    $ select table_name, table_collation from information_schema.tables where table_schema="...";

Get info on the columns:

    $ select column_name, collation_name from information_schema.columns where table_schema="..." and table_name="...";

select table_name, column_name, collation_name from information_schema.columns where table_schema='old_test' order by table_name and column_name;
"""

import os
import sys
import re
import string
import subprocess
import datetime
import unicodedata
from random import choice, shuffle
from uuid import uuid4
from sqlalchemy import create_engine, MetaData, Table, bindparam
from docutils.core import publish_parts
from passlib.hash import pbkdf2_sha512
try:
    import json
except ImportError:
    import simplejson as json

# update_SQL holds the SQL statements that create the 1.0 tables missing in 0.2.7 and
# alter the existing tables.
update_SQL = '''
-- Create the applicationsettingsuser table
CREATE TABLE `applicationsettingsuser` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `applicationsettings_id` int(11) DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `applicationsettings_id` (`applicationsettings_id`),
  KEY `user_id` (`user_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

-- Create the orthography table
CREATE TABLE `orthography` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `orthography` text,
  `lowercase` tinyint(1) DEFAULT NULL,
  `initial_glottal_stops` tinyint(1) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

-- Modify the application_settings table as needed
RENAME TABLE application_settings TO applicationsettings;
UPDATE applicationsettings
    SET morphemeBreakIsObjectLanguageString=1
    WHERE morphemeBreakIsObjectLanguageString='yes';
UPDATE applicationsettings
    SET morphemeBreakIsObjectLanguageString=0
    WHERE morphemeBreakIsObjectLanguageString!='yes';
ALTER TABLE applicationsettings
    -- The following CONVERT clause may change TEXTs to MEDIUMTEXTS, cf. http://bugs.mysql.com/bug.php?id=31291
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE objectLanguageId object_language_id VARCHAR(3) DEFAULT NULL,
    CHANGE objectLanguageName object_language_name VARCHAR(255) DEFAULT NULL,
    CHANGE metaLanguageId metalanguage_id VARCHAR(3) DEFAULT NULL,
    CHANGE metaLanguageName metalanguage_name VARCHAR(255) DEFAULT NULL,
    CHANGE metaLanguageOrthography metalanguage_inventory TEXT,
    CHANGE orthographicValidation orthographic_validation VARCHAR(7) DEFAULT NULL,
    CHANGE punctuation punctuation TEXT,
    CHANGE narrPhonInventory narrow_phonetic_inventory TEXT,
    CHANGE narrPhonValidation narrow_phonetic_validation VARCHAR(7) DEFAULT NULL,
    CHANGE broadPhonInventory broad_phonetic_inventory TEXT,
    CHANGE broadPhonValidation broad_phonetic_validation VARCHAR(7) DEFAULT NULL,
    CHANGE morphemeBreakIsObjectLanguageString morpheme_break_is_orthographic tinyint(1) DEFAULT NULL,
    CHANGE morphPhonValidation morpheme_break_validation VARCHAR(7) DEFAULT NULL,
    CHANGE morphPhonInventory phonemic_inventory TEXT,
    CHANGE morphDelimiters morpheme_delimiters VARCHAR(255) DEFAULT NULL,
    DROP COLUMN headerImageName,
    DROP COLUMN colorsCSS,
    ADD storage_orthography_id int(11) DEFAULT NULL,
    ADD input_orthography_id int(11) DEFAULT NULL,
    ADD output_orthography_id int(11) DEFAULT NULL,
    ADD KEY (storage_orthography_id),
    ADD KEY (input_orthography_id),
    ADD KEY (output_orthography_id);

-- Change the collection table
ALTER TABLE collection
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE datetimeEntered datetime_entered datetime DEFAULT NULL,
    CHANGE dateElicited date_elicited date DEFAULT NULL,
    MODIFY contents TEXT,
    MODIFY description TEXT,
    ADD COLUMN UUID VARCHAR(36) DEFAULT NULL,
    ADD COLUMN markup_language VARCHAR(100) DEFAULT NULL,
    ADD COLUMN html TEXT,
    ADD COLUMN modifier_id INT(11) DEFAULT NULL,
    ADD COLUMN contents_unpacked TEXT,
    ADD KEY (modifier_id);
UPDATE collection SET markup_language = 'restructuredText';

-- Change the collectionbackup TABLE
ALTER TABLE collectionbackup
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE datetimeEntered datetime_entered datetime DEFAULT NULL,
    CHANGE dateElicited date_elicited date DEFAULT NULL,
    ADD COLUMN UUID VARCHAR(36) DEFAULT NULL,
    ADD COLUMN markup_language VARCHAR(100) DEFAULT NULL,
    ADD COLUMN html TEXT,
    ADD COLUMN modifier TEXT,
    MODIFY speaker TEXT,
    MODIFY elicitor TEXT,
    MODIFY enterer TEXT,
    MODIFY description TEXT,
    MODIFY contents TEXT,
    MODIFY source TEXT,
    MODIFY files TEXT,
    ADD COLUMN forms TEXT,
    ADD COLUMN tags TEXT;
UPDATE collectionbackup SET markup_language = 'restructuredText';

ALTER TABLE collectionfile
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL;

ALTER TABLE collectionform
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL;

CREATE TABLE `collectiontag` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `collection_id` int(11) DEFAULT NULL,
  `tag_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `collection_id` (`collection_id`),
  KEY `tag_id` (`tag_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `corpus` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `UUID` varchar(36) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `description` text,
  `content` longtext,
  `enterer_id` int(11) DEFAULT NULL,
  `modifier_id` int(11) DEFAULT NULL,
  `form_search_id` int(11) DEFAULT NULL,
  `datetime_entered` datetime DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `enterer_id` (`enterer_id`),
  KEY `modifier_id` (`modifier_id`),
  KEY `form_search_id` (`form_search_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `corpusbackup` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `corpus_id` int(11) DEFAULT NULL,
  `UUID` varchar(36) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `type` varchar(255) DEFAULT NULL,
  `description` text,
  `content` longtext,
  `enterer` text,
  `modifier` text,
  `form_search` text,
  `datetime_entered` datetime DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  `tags` text,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `corpusfile` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `corpus_id` int(11) DEFAULT NULL,
  `filename` varchar(255) DEFAULT NULL,
  `format` varchar(255) DEFAULT NULL,
  `creator_id` int(11) DEFAULT NULL,
  `modifier_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  `datetime_created` datetime DEFAULT NULL,
  `restricted` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `corpus_id` (`corpus_id`),
  KEY `creator_id` (`creator_id`),
  KEY `modifier_id` (`modifier_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `corpusform` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `corpus_id` int(11) DEFAULT NULL,
  `form_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `corpus_id` (`corpus_id`),
  KEY `form_id` (`form_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `corpustag` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `corpus_id` int(11) DEFAULT NULL,
  `tag_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `corpus_id` (`corpus_id`),
  KEY `tag_id` (`tag_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

ALTER TABLE elicitationmethod
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    MODIFY description TEXT;

ALTER TABLE file
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE datetimeEntered datetime_entered datetime DEFAULT NULL,
    CHANGE dateElicited date_elicited date DEFAULT NULL,
    CHANGE MIMEtype MIME_type VARCHAR(255) DEFAULT NULL,
    CHANGE utteranceType utterance_type VARCHAR(255) DEFAULT NULL,
    ADD COLUMN filename VARCHAR(255) DEFAULT NULL,
    ADD COLUMN lossy_filename VARCHAR(255) DEFAULT NULL,
    MODIFY description TEXT,
    CHANGE embeddedFileMarkup url VARCHAR(255) DEFAULT NULL,
    CHANGE embeddedFilePassword password VARCHAR(255) DEFAULT NULL,
    ADD COLUMN parent_file_id INT(11) DEFAULT NULL,
    ADD COLUMN start FLOAT DEFAULT NULL,
    ADD COLUMN end FLOAT DEFAULT NULL,
    ADD KEY (parent_file_id),
    ADD UNIQUE (filename),
    DROP INDEX name;

CREATE TABLE `filetag` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `file_id` int(11) DEFAULT NULL,
  `tag_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `file_id` (`file_id`),
  KEY `tag_id` (`tag_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

ALTER TABLE form
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE datetimeEntered datetime_entered datetime DEFAULT NULL,
    CHANGE dateElicited date_elicited date DEFAULT NULL,
    CHANGE phoneticTranscription phonetic_transcription VARCHAR(255) DEFAULT NULL,
    CHANGE narrowPhoneticTranscription narrow_phonetic_transcription VARCHAR(255) DEFAULT NULL,
    CHANGE morphemeBreak morpheme_break VARCHAR(255) DEFAULT NULL,
    CHANGE morphemeGloss morpheme_gloss VARCHAR(255) DEFAULT NULL,
    CHANGE syntacticCategoryString syntactic_category_string VARCHAR(255) DEFAULT NULL,
    CHANGE breakGlossCategory break_gloss_category VARCHAR(1023) DEFAULT NULL,
    ADD COLUMN UUID VARCHAR(36) DEFAULT NULL,
    MODIFY comments TEXT,
    CHANGE speakerComments speaker_comments TEXT,
    CHANGE morphemeBreakIDs morpheme_break_ids TEXT,
    CHANGE morphemeGlossIDs morpheme_gloss_ids TEXT,
    ADD COLUMN syntax VARCHAR(1023) DEFAULT NULL,
    ADD COLUMN semantics VARCHAR(1023) DEFAULT NULL,
    ADD COLUMN status VARCHAR(40) DEFAULT NULL,
    ADD COLUMN modifier_id INT(11) DEFAULT NULL,
    ADD KEY (modifier_id);
UPDATE form SET status='tested';

ALTER TABLE formbackup
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE datetimeEntered datetime_entered datetime DEFAULT NULL,
    CHANGE dateElicited date_elicited date DEFAULT NULL,
    CHANGE phoneticTranscription phonetic_transcription VARCHAR(255) DEFAULT NULL,
    CHANGE narrowPhoneticTranscription narrow_phonetic_transcription VARCHAR(255) DEFAULT NULL,
    CHANGE morphemeBreak morpheme_break VARCHAR(255) DEFAULT NULL,
    CHANGE morphemeGloss morpheme_gloss VARCHAR(255) DEFAULT NULL,
    CHANGE syntacticCategoryString syntactic_category_string VARCHAR(255) DEFAULT NULL,
    CHANGE breakGlossCategory break_gloss_category VARCHAR(1023) DEFAULT NULL,
    ADD COLUMN UUID VARCHAR(36) DEFAULT NULL,
    MODIFY comments TEXT,
    CHANGE speakerComments speaker_comments TEXT,
    CHANGE morphemeBreakIDs morpheme_break_ids TEXT,
    CHANGE morphemeGlossIDs morpheme_gloss_ids TEXT,
    MODIFY elicitor TEXT,
    MODIFY enterer TEXT,
    MODIFY verifier TEXT,
    MODIFY speaker TEXT,
    CHANGE elicitationMethod elicitation_method TEXT,
    CHANGE syntacticCategory syntactic_category TEXT,
    MODIFY source TEXT,
    MODIFY files TEXT,
    CHANGE keywords tags TEXT,
    CHANGE glosses translations TEXT,
    ADD COLUMN syntax VARCHAR(1023) DEFAULT NULL,
    ADD COLUMN semantics VARCHAR(1023) DEFAULT NULL,
    ADD COLUMN status VARCHAR(40) DEFAULT NULL,
    ADD COLUMN modifier TEXT;
UPDATE formbackup SET status='tested';

ALTER TABLE formfile
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL;

CREATE TABLE `formsearch` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `search` text,
  `description` text,
  `enterer_id` int(11) DEFAULT NULL,
  `datetime_modified` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `enterer_id` (`enterer_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

RENAME TABLE formkeyword TO formtag;
ALTER TABLE formtag
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE keyword_id tag_id INT(11) DEFAULT NULL,
    ADD KEY (tag_id);

RENAME TABLE gloss TO translation;
ALTER TABLE translation
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE gloss transcription TEXT NOT NULL,
    CHANGE glossGrammaticality grammaticality VARCHAR(255) DEFAULT NULL;

RENAME TABLE keyword TO tag;
ALTER TABLE tag
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    MODIFY description TEXT,
    ADD UNIQUE (name);

ALTER TABLE language
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL;

CREATE TABLE `morphemelanguagemodel` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `corpus_id` int(11) DEFAULT NULL,
    `enterer_id` int(11) DEFAULT NULL,
    `modifier_id` int(11) DEFAULT NULL,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `generate_succeeded` tinyint(1) DEFAULT NULL,
    `generate_message` varchar(255) DEFAULT NULL,
    `generate_attempt` varchar(36) DEFAULT NULL,
    `perplexity` float DEFAULT NULL,
    `perplexity_attempt` varchar(36) DEFAULT NULL,
    `perplexity_computed` tinyint(1) DEFAULT NULL,
    `toolkit` varchar(10) DEFAULT NULL,
    `order` int(11) DEFAULT NULL,
    `smoothing` varchar(30) DEFAULT NULL,
    `vocabulary_morphology_id` int(11) DEFAULT NULL,
    `restricted` tinyint(1) DEFAULT NULL,
    `categorial` tinyint(1) DEFAULT NULL,
    `morpheme_delimiters` varchar(255) DEFAULT NULL,
    `parent_directory` varchar(255) DEFAULT NULL,
    `rare_delimiter` varchar(10) DEFAULT NULL,
    `start_symbol` varchar(10) DEFAULT NULL,
    `end_symbol` varchar(10) DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `corpus_id` (`corpus_id`),
    KEY `enterer_id` (`enterer_id`),
    KEY `modifier_id` (`modifier_id`),
    KEY `vocabulary_morphology_id` (`vocabulary_morphology_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `morphemelanguagemodelbackup` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `morphemelanguagemodel_id` int(11) DEFAULT NULL,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `corpus` text,
    `enterer` text,
    `modifier` text,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `generate_succeeded` tinyint(1) DEFAULT NULL,
    `generate_message` varchar(255) DEFAULT NULL,
    `generate_attempt` varchar(36) DEFAULT NULL,
    `perplexity` float DEFAULT NULL,
    `perplexity_attempt` varchar(36) DEFAULT NULL,
    `perplexity_computed` tinyint(1) DEFAULT NULL,
    `toolkit` varchar(10) DEFAULT NULL,
    `order` int(11) DEFAULT NULL,
    `smoothing` varchar(30) DEFAULT NULL,
    `vocabulary_morphology` text,
    `restricted` tinyint(1) DEFAULT NULL,
    `categorial` tinyint(1) DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `morphologicalparser` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `phonology_id` int(11) DEFAULT NULL,
    `morphology_id` int(11) DEFAULT NULL,
    `language_model_id` int(11) DEFAULT NULL,
    `enterer_id` int(11) DEFAULT NULL,
    `modifier_id` int(11) DEFAULT NULL,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `compile_succeeded` tinyint(1) DEFAULT NULL,
    `compile_message` varchar(255) DEFAULT NULL,
    `compile_attempt` varchar(36) DEFAULT NULL,
    `generate_succeeded` tinyint(1) DEFAULT NULL,
    `generate_message` varchar(255) DEFAULT NULL,
    `generate_attempt` varchar(36) DEFAULT NULL,
    `parent_directory` varchar(255) DEFAULT NULL,
    `persist_cache` tinyint(1) DEFAULT NULL,
    `morphology_rare_delimiter` varchar(10) DEFAULT NULL,
    `morphology_rich_upper` tinyint(1) DEFAULT NULL,
    `morphology_rules_generated` text,
    `language_model_start_symbol` varchar(10) DEFAULT NULL,
    `language_model_end_symbol` varchar(10) DEFAULT NULL,
    `language_model_categorial` tinyint(1) DEFAULT NULL,
    `morpheme_delimiters` varchar(255) DEFAULT NULL,
    `morphology_rich_lower` tinyint(1) DEFAULT NULL,
    `word_boundary_symbol` varchar(10) DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `phonology_id` (`phonology_id`),
    KEY `morphology_id` (`morphology_id`),
    KEY `language_model_id` (`language_model_id`),
    KEY `enterer_id` (`enterer_id`),
    KEY `modifier_id` (`modifier_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `morphologicalparserbackup` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `morphologicalparser_id` int(11) DEFAULT NULL,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `phonology` text,
    `morphology` text,
    `language_model` text,
    `enterer` text,
    `modifier` text,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `compile_succeeded` tinyint(1) DEFAULT NULL,
    `compile_message` varchar(255) DEFAULT NULL,
    `compile_attempt` varchar(36) DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `morphology` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `script_type` varchar(5) DEFAULT NULL,
    `lexicon_corpus_id` int(11) DEFAULT NULL,
    `rules_corpus_id` int(11) DEFAULT NULL,
    `enterer_id` int(11) DEFAULT NULL,
    `modifier_id` int(11) DEFAULT NULL,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `compile_succeeded` tinyint(1) DEFAULT NULL,
    `compile_message` varchar(255) DEFAULT NULL,
    `compile_attempt` varchar(36) DEFAULT NULL,
    `generate_attempt` varchar(36) DEFAULT NULL,
    `extract_morphemes_from_rules_corpus` tinyint(1) DEFAULT NULL,
    `rules_generated` text,
    `rules` text,
    `rich_upper` tinyint(1) DEFAULT NULL,
    `rich_lower` tinyint(1) DEFAULT NULL,
    `include_unknowns` tinyint(1) DEFAULT NULL,
    `parent_directory` varchar(255) DEFAULT NULL,
    `word_boundary_symbol` varchar(10) DEFAULT NULL,
    `rare_delimiter` varchar(10) DEFAULT NULL,
    `morpheme_delimiters` varchar(255) DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `lexicon_corpus_id` (`lexicon_corpus_id`),
    KEY `rules_corpus_id` (`rules_corpus_id`),
    KEY `enterer_id` (`enterer_id`),
    KEY `modifier_id` (`modifier_id`)
) ENGINE=MyISAM AUTO_INCREMENT=3 DEFAULT CHARSET=utf8;

CREATE TABLE `morphologybackup` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `morphology_id` int(11) DEFAULT NULL,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `script_type` varchar(5),
    `lexicon_corpus` text,
    `rules_corpus` text,
    `enterer` text,
    `modifier` text,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `compile_succeeded` tinyint(1) DEFAULT NULL,
    `compile_message` varchar(255) DEFAULT NULL,
    `compile_attempt` varchar(36) DEFAULT NULL,
    `generate_attempt` varchar(36) DEFAULT NULL,
    `extract_morphemes_from_rules_corpus` tinyint(1) DEFAULT NULL,
    `rules` text,
    `rich_upper` tinyint(1) DEFAULT NULL,
    `include_unknowns` tinyint(1) DEFAULT NULL,
    `rich_lower` tinyint(1) DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

ALTER TABLE page
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    ADD COLUMN html TEXT,
    CHANGE markup markup_language VARCHAR(100) DEFAULT NULL,
    MODIFY content TEXT;
UPDATE page SET markup_language='restructuredText';

CREATE TABLE `parse` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `transcription` varchar(1000) DEFAULT NULL,
    `parse` text,
    `parser_id` int(11) DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `candidates` text,
    PRIMARY KEY (`id`),
    KEY `parser_id` (`parser_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

ALTER TABLE phonology
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE datetimeEntered datetime_entered datetime DEFAULT NULL,
    ADD COLUMN UUID VARCHAR(36) DEFAULT NULL,
    MODIFY description TEXT,
    MODIFY script TEXT,
    ADD COLUMN compile_succeeded tinyint(1) DEFAULT NULL,
    ADD COLUMN compile_message VARCHAR(255) DEFAULT NULL,
    ADD COLUMN compile_attempt VARCHAR(36) DEFAULT NULL,
    ADD COLUMN parent_directory varchar(255) DEFAULT NULL,
    ADD COLUMN word_boundary_symbol varchar(10) DEFAULT NULL,
    ADD FOREIGN KEY (modifier_id) REFERENCES user(id),
    ADD FOREIGN KEY (enterer_id) REFERENCES user(id);

CREATE TABLE `phonologybackup` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `phonology_id` int(11) DEFAULT NULL,
    `UUID` varchar(36) DEFAULT NULL,
    `name` varchar(255) DEFAULT NULL,
    `description` text,
    `script` text,
    `enterer` text,
    `modifier` text,
    `datetime_entered` datetime DEFAULT NULL,
    `datetime_modified` datetime DEFAULT NULL,
    `compile_succeeded` tinyint(1) DEFAULT NULL,
    `compile_message` varchar(255) DEFAULT NULL,
    `compile_attempt` varchar(36) DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

ALTER TABLE source
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    ADD COLUMN `crossref_source_id` int(11) DEFAULT NULL,
    ADD COLUMN `type` varchar(20) DEFAULT NULL,
    ADD COLUMN `key` varchar(1000) DEFAULT NULL,
    ADD COLUMN `address` varchar(1000) DEFAULT NULL,
    ADD COLUMN `annote` text,
    ADD COLUMN `author` varchar(255) DEFAULT NULL,
    ADD COLUMN `booktitle` varchar(255) DEFAULT NULL,
    ADD COLUMN `chapter` varchar(255) DEFAULT NULL,
    ADD COLUMN `crossref` varchar(1000) DEFAULT NULL,
    ADD COLUMN `edition` varchar(255) DEFAULT NULL,
    ADD COLUMN `editor` varchar(255) DEFAULT NULL,
    ADD COLUMN `howpublished` varchar(255) DEFAULT NULL,
    ADD COLUMN `institution` varchar(255) DEFAULT NULL,
    ADD COLUMN `journal` varchar(255) DEFAULT NULL,
    ADD COLUMN `key_field` varchar(255) DEFAULT NULL,
    ADD COLUMN `month` varchar(100) DEFAULT NULL,
    ADD COLUMN `note` varchar(1000) DEFAULT NULL,
    ADD COLUMN `number` varchar(100) DEFAULT NULL,
    ADD COLUMN `organization` varchar(255) DEFAULT NULL,
    ADD COLUMN `pages` varchar(100) DEFAULT NULL,
    ADD COLUMN `publisher` varchar(255) DEFAULT NULL,
    ADD COLUMN `school` varchar(255) DEFAULT NULL,
    ADD COLUMN `series` varchar(255) DEFAULT NULL,
    ADD COLUMN `type_field` varchar(255) DEFAULT NULL,
    ADD COLUMN `url` varchar(1000) DEFAULT NULL,
    ADD COLUMN `volume` varchar(100) DEFAULT NULL,
    ADD COLUMN `affiliation` varchar(255) DEFAULT NULL,
    ADD COLUMN `abstract` varchar(1000) DEFAULT NULL,
    ADD COLUMN `contents` varchar(255) DEFAULT NULL,
    ADD COLUMN `copyright` varchar(255) DEFAULT NULL,
    ADD COLUMN `ISBN` varchar(20) DEFAULT NULL,
    ADD COLUMN `ISSN` varchar(20) DEFAULT NULL,
    ADD COLUMN `keywords` varchar(255) DEFAULT NULL,
    ADD COLUMN `language` varchar(255) DEFAULT NULL,
    ADD COLUMN `location` varchar(255) DEFAULT NULL,
    ADD COLUMN `LCCN` varchar(20) DEFAULT NULL,
    ADD COLUMN `mrnumber` varchar(25) DEFAULT NULL,
    ADD COLUMN `price` varchar(100) DEFAULT NULL,
    ADD COLUMN `size` varchar(255) DEFAULT NULL,
    ADD KEY (crossref_source_id);

ALTER TABLE speaker
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE firstName first_name VARCHAR(255) DEFAULT NULL,
    CHANGE lastName last_name VARCHAR(255) DEFAULT NULL,
    ADD COLUMN markup_language VARCHAR(100) DEFAULT NULL,
    CHANGE speakerPageContent page_content TEXT,
    ADD COLUMN html TEXT;
UPDATE speaker SET markup_language='restructuredText';

ALTER TABLE syntacticcategory
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    ADD COLUMN `type` VARCHAR(60) DEFAULT NULL,
    MODIFY description TEXT;

ALTER TABLE `user`
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL,
    CHANGE firstName first_name VARCHAR(255) DEFAULT NULL,
    CHANGE lastName last_name VARCHAR(255) DEFAULT NULL,
    ADD COLUMN salt VARCHAR(255) DEFAULT NULL,
    MODIFY role VARCHAR(100) DEFAULT NULL,
    ADD COLUMN markup_language VARCHAR(100) DEFAULT NULL,
    CHANGE personalPageContent page_content TEXT,
    ADD COLUMN html TEXT,
    ADD COLUMN input_orthography_id INT(11) DEFAULT NULL,
    ADD COLUMN output_orthography_id INT(11) DEFAULT NULL,
    ADD KEY (input_orthography_id),
    ADD KEY (output_orthography_id),
    DROP COLUMN collectionViewType;
UPDATE user SET markup_language='restructuredText';

ALTER TABLE userform
    CONVERT TO CHARACTER SET utf8,
    CHANGE datetimeModified datetime_modified datetime DEFAULT NULL;

'''.strip()

def write_update_executable(mysql_update_script_name, here):
    """Write the contents of update_SQL to an executable and return the path to it."""
    mysql_update_script = os.path.join(here, mysql_update_script_name)
    if os.path.exists(mysql_update_script):
        os.remove(mysql_update_script)
    with open(mysql_update_script, 'w') as f:
        f.write(update_SQL)
    os.chmod(mysql_update_script, 0744)
    return mysql_update_script

def write_recreate_executable(mysql_recreate_script_name, here):
    """Create the MySQL recreate script, an .sql file that drops/recreates the
    database and loads the dump file.

    """
    mysql_recreate_script = os.path.join(here, mysql_recreate_script_name)
    if not os.path.exists(mysql_recreate_script):
        with open(mysql_recreate_script, 'w') as f:
            pass
        os.chmod(mysql_recreate_script, 0744)
    return mysql_recreate_script

# cleanup_SQL performs the final modifications on the database, dropping 
# the columns that were retained in update_SQL.
cleanup_SQL = '''
ALTER TABLE applicationsettings
    DROP COLUMN objectLanguageOrthography1Name,
    DROP COLUMN objectLanguageOrthography1,
    DROP COLUMN OLO1Lowercase,
    DROP COLUMN OLO1InitialGlottalStops,
    DROP COLUMN objectLanguageOrthography2Name,
    DROP COLUMN objectLanguageOrthography2,
    DROP COLUMN OLO2Lowercase,
    DROP COLUMN OLO2InitialGlottalStops,
    DROP COLUMN objectLanguageOrthography3Name,
    DROP COLUMN objectLanguageOrthography3,
    DROP COLUMN OLO3Lowercase,
    DROP COLUMN OLO3InitialGlottalStops,
    DROP COLUMN objectLanguageOrthography4Name,
    DROP COLUMN objectLanguageOrthography4,
    DROP COLUMN OLO4Lowercase,
    DROP COLUMN OLO4InitialGlottalStops,
    DROP COLUMN objectLanguageOrthography5Name,
    DROP COLUMN objectLanguageOrthography5,
    DROP COLUMN OLO5Lowercase,
    DROP COLUMN OLO5InitialGlottalStops,
    DROP COLUMN storageOrthography,
    DROP COLUMN defaultInputOrthography,
    DROP COLUMN defaultOutputOrthography,
    DROP COLUMN unrestrictedUsers;

ALTER TABLE collectionbackup
    DROP COLUMN backuper;

ALTER TABLE file
    MODIFY url VARCHAR(255) DEFAULT NULL;

ALTER TABLE formbackup
    DROP COLUMN backuper;

ALTER TABLE source
    DROP COLUMN authorFirstName,
    DROP COLUMN authorLastName,
    DROP COLUMN fullReference;

ALTER TABLE user
    DROP COLUMN inputOrthography,
    DROP COLUMN outputOrthography;

'''.strip()

def row2dict(row):
    """Turn an SQLA row proxy object into a dict; clone any 'id' keys to 'id_' ones."""
    row = dict([(k, normalize(v)) for k, v in dict(row).items()])
    try:
        row['id_'] = row['id']
    except Exception:
        pass
    return row

def normalize(utf8_str):
    """Return an UTF-8 encoded string decompositionally normalized using NFD."""
    try:
        result = unicodedata.normalize('NFD', unicode(utf8_str, 'utf8')).encode('utf8')
    except Exception:
        result = utf8_str
    return result

def print_(string):
    """Print to stdout immediately."""
    sys.stdout.write(string)
    sys.stdout.flush()

def get_db_to_text_script(mysql_db_name, mysql_username, mysql_password):
    """Return a string of shell/mysql commands that will write a subset of the db to stdout."""
    script = [
        "#!/bin/sh",
        "mysql -u %s -p%s -e 'select transcription, phoneticTranscription, \
                narrowPhoneticTranscription, morphemeBreak, morphemeGloss from %s.form;'" % (mysql_username, mysql_password, mysql_db_name),
        "mysql -u %s -p%s -e 'select contents from %s.collection;'" % (mysql_username, mysql_password, mysql_db_name),
        "mysql -u %s -p%s -e 'select firstName, lastName from %s.user;'" % (mysql_username, mysql_password, mysql_db_name),
        "mysql -u %s -p%s -e 'select name from %s.file;'" % (mysql_username, mysql_password, mysql_db_name),
    ]
    return '\n'.join(script)

def write_db_to_text_file(pre_data_dump_name, here, mysql_updater, db_to_text_script):
    """Write a subset of the data in the db to a text file; output will be used post-processing
    to ensure data integrity.

    """
    print_('Writing a subset of the data in %s to a text file ... ' % mysql_db_name)
    with open(mysql_updater, 'w') as f:
        f.write(db_to_text_script)
    pre_data_dump_path = os.path.join(here, pre_data_dump_name)
    with open(pre_data_dump_path, 'w') as f:
        subprocess.call([mysql_updater], shell=False, stdout=f, stderr=f)
    print 'done.'
    return pre_data_dump_path

def write_cleanup_executable(mysql_cleanup_script_name, here):
    """Write the contents of cleanup_SQL to an executable and return the path to it."""
    mysql_cleanup_script = os.path.join(here, mysql_cleanup_script_name)
    if not os.path.exists(mysql_cleanup_script ):
        with open(mysql_cleanup_script , 'w') as f:
            f.write(cleanup_SQL)
        os.chmod(mysql_cleanup_script , 0744)
    return mysql_cleanup_script

def write_charset_executable(mysql_charset_script_name, here):
    """Write to disk as an executable the file that will be used to issue the MySQL
    statements that change the character set to UTF-8 -- return the absolute path.
    """
    mysql_charset_script = os.path.join(here, mysql_charset_script_name)
    if not os.path.exists(mysql_charset_script):
        with open(mysql_charset_script, 'w') as f:
            pass
        os.chmod(mysql_charset_script, 0744)
    return mysql_charset_script

def write_updater_executable(mysql_updater_name, here):
    """Write to disk the shell script that will be used to load the various MySQL scripts.
    Return the absolute path.
    """
    mysql_updater = os.path.join(here, mysql_updater_name)
    with open(mysql_updater, 'w') as f:
        pass
    os.chmod(mysql_updater, 0744)
    return mysql_updater

def recreate_database(mysql_db_name, mysql_dump_file, mysql_username, mysql_password, mysql_updater, mysql_recreate_script):
    """Drop the database `mysql_db_name` and recreate it using the MySQL dump file.
    """
    print_('Dropping database %s, recreating it and loading the data from the '
        'dump file %s ... ' % (mysql_db_name, mysql_dump_file))

    bash_script = [
        '#!/bin/sh',
        'mysql -u %s -p%s --verbose < %s' % (
            mysql_username, mysql_password, mysql_recreate_script),
    ]

    sql_script = [
        'drop database if exists %s;' % mysql_db_name,
        'create database %s default character set utf8;' % mysql_db_name,
        'use %s;' % mysql_db_name,
        'SET NAMES utf8;',
        'SOURCE %s;' % mysql_dump_file,
        '\n'
    ]

    with open(mysql_recreate_script, 'w') as f:
        f.write('\n'.join(sql_script))
    with open(mysql_updater, 'w') as f:
        f.write('\n'.join(bash_script))
    with open(os.devnull, 'w') as devnull:
        subprocess.call([mysql_updater], shell=False, stdout=devnull, stderr=devnull)
    print 'done.'

def get_non_utf8_tables_columns(mysql_db_name, mysql_username, mysql_password):
    """Return two lists: the names of tables and columns that do not use the UTF-8 character set."""
    sqlalchemy_url = 'mysql://%s:%s@localhost:3306/information_schema' % (mysql_username, mysql_password)
    info_schema_engine = create_engine(sqlalchemy_url)
    tables_table = Table('TABLES', meta, autoload=True, autoload_with=info_schema_engine)
    columns_table = Table('COLUMNS', meta, autoload=True, autoload_with=info_schema_engine)
    select = tables_table.select().\
        where(tables_table.c.TABLE_SCHEMA == bindparam('mysql_db_name')).\
        where(tables_table.c.TABLE_COLLATION != 'utf8_general_ci')
    non_utf8_tables = [row['TABLE_NAME'] for row in 
            info_schema_engine.execute(select, {'mysql_db_name': mysql_db_name}).fetchall()]
    select = columns_table.select().\
        where(columns_table.c.TABLE_SCHEMA == bindparam('mysql_db_name')).\
        where(columns_table.c.COLLATION_NAME != 'utf8_general_ci')
    non_utf8_columns = [row['COLUMN_NAME'] for row in 
            info_schema_engine.execute(select, {'mysql_db_name': mysql_db_name}).fetchall()]
    return non_utf8_tables, non_utf8_columns

def get_database_info(mysql_db_name, mysql_username, mysql_password):
    """Return information about the character sets and collations used in the database.

    """
    columns = {}
    sqlalchemy_url = 'mysql://%s:%s@localhost:3306/information_schema' % (mysql_username, mysql_password)
    info_schema_engine = create_engine(sqlalchemy_url)
    columns_table = Table('COLUMNS', meta, autoload=True, autoload_with=info_schema_engine)
    schemata_table = Table('SCHEMATA', meta, autoload=True, autoload_with=info_schema_engine)
    db_charset = info_schema_engine.execute(schemata_table.select().where(schemata_table.c.SCHEMA_NAME==mysql_db_name)).\
        fetchall()[0]['DEFAULT_CHARACTER_SET_NAME']
    tables_table = Table('TABLES', meta, autoload=True, autoload_with=info_schema_engine)
    table_collations = dict([(r['TABLE_NAME'], r['TABLE_COLLATION']) for r in 
        info_schema_engine.execute(tables_table.select().where(tables_table.c.TABLE_SCHEMA==mysql_db_name))])
    select = columns_table.select().\
        where(columns_table.c.TABLE_SCHEMA == bindparam('mysql_db_name')).\
        where(columns_table.c.COLLATION_NAME != None)
    for row in info_schema_engine.execute(select, {'mysql_db_name': mysql_db_name}):
        columns.setdefault(row['table_name'], {})[row['COLUMN_NAME']] = (row['COLLATION_NAME'], row['COLUMN_TYPE'], row['COLUMN_KEY'])
        #tables.setdefault(row['table_name'], []).append({row['COLUMN_NAME']: (row['COLLATION_NAME'], row['COLUMN_TYPE'], row['COLUMN_KEY'])})
    return db_charset, table_collations, columns

def get_binary_column_type(column_type):
    """Return an appropriate binary column type for the input one, cf. https://codex.wordpress.org/Converting_Database_Character_Sets."""
    try:
        return {
            'char': 'binary',
            'text': 'blob',
            'tinytext': 'tinyblob',
            'mediumtext': 'mediumblob',
            'longtext': 'longblob'
        }[column_type.lower()]
    except KeyError:
        if column_type.lower().startswith('varchar('):
            return 'varbinary(%s)' % column_type[8:-1]
        return 'blob'

def write_charset_executable_content(mysql_charset_script, mysql_db_name, mysql_username, mysql_password,
        db_charset, table_collations, columns):
    """Write a series of MySQL commands to the file at the path in mysql_charset_script; these commands will alter
    the tables and columns (and the db) so that they use the UTF-8 character set.
    """
    with open(mysql_charset_script, 'w') as f:
        if db_charset != 'utf8':
            f.write('ALTER DATABASE %s CHARACTER SET utf8;\n\n' % mysql_db_name)
        #for table_name, columns in columns_with_collations.items():
        for table_name, table_collation in table_collations.items():
            if not table_collation == 'utf8_general_ci':
                f.write('ALTER TABLE %s CHARACTER SET utf8;\n\n' % table_name)
            non_utf8_columns = dict([(c_name, (c_type, c_key)) for c_name, (c_coll, c_type, c_key) in
                columns.get(table_name, {}).items() if c_coll != 'utf8_general_ci'])
            if non_utf8_columns:
                indices = [(c_name, c_key) for c_name, (c_type, c_key) in non_utf8_columns.items() if c_key]
                f.write('ALTER TABLE %s\n' % table_name)
                if indices:
                    for c_name, c_key in indices:
                        if c_key == 'PRI':
                            f.write('  DROP PRIMARY KEY,\n')
                        else:
                            f.write('  DROP INDEX %s,\n' % c_name)
                f.write('  %s;\n\n' % ',\n  '.join(
                    ['CHANGE `%s` `%s` %s' % (c_name, c_name, get_binary_column_type(c_type))
                     for c_name, (c_type, c_key) in non_utf8_columns.items()]))
        for table_name, columns_dict in columns.items():
            non_utf8_columns = dict([(c_name, (c_type, c_key)) for c_name, (c_coll, c_type, c_key) in
                columns_dict.items() if c_coll != 'utf8_general_ci'])
            indices = [(c_name, c_key) for c_name, (c_type, c_key) in non_utf8_columns.items() if c_key]
            if non_utf8_columns:
                f.write('ALTER TABLE %s\n' % table_name)
                f.write('  %s' % ',\n  '.join(
                    ['CHANGE `%s` `%s` %s CHARACTER SET utf8' % (c_name, c_name, c_type) for c_name, (c_type, c_key) in non_utf8_columns.items()]))
                if indices:
                    f.write(',\n')
                    for index, (c_name, c_key) in enumerate(indices):
                        if c_key == 'PRI':
                            f.write('  ADD PRIMARY KEY (`%s`)' % c_name)
                        else:
                            f.write('  ADD UNIQUE (`%s`)' % c_name)
                        if index == len(indices) - 1:
                            f.write(';\n\n')
                        else:
                            f.write(',\n')
                else:
                    f.write(';\n\n')

def change_db_charset_to_utf8(mysql_db_name, mysql_charset_script, mysql_username, mysql_password,
        mysql_updater, db_charset, table_collations, columns):
    """Run the executable at `mysql_charset_script` in order to change the character set of the db to UTF-8.
    Note that this was not working correctly.  We need to make sure that MySQL is using UTF-8 everywhere, see 
    this web page for how to do that: http://cameronyule.com/2008/07/configuring-mysql-to-use-utf-8/.

    """
    print_('Changing the character set of the database to UTF-8 ... ')
    write_charset_executable_content(mysql_charset_script, mysql_db_name, mysql_username, mysql_password,
        db_charset, table_collations, columns)
    script = [
        "#!/bin/sh",
        "mysql -u %s -p%s %s < %s" % (mysql_username, mysql_password, mysql_db_name, mysql_charset_script),
    ]
    with open(mysql_updater, 'w') as f:
        f.write('\n'.join(script))
    with open(os.devnull, 'w') as devnull:
        subprocess.call([mysql_updater], shell=False, stdout=devnull, stderr=devnull)
    print 'done.'

def perform_preliminary_update(mysql_db_name, mysql_update_script, mysql_username, mysql_password, mysql_updater):
    """Perform the preliminary update of the db by calling the executable at ``mysql_update_script``."""
    print_('Running the MySQL update script ... ')
    mysql_script_content = '#!/bin/sh\nmysql -u %s -p%s %s < %s' % (mysql_username, mysql_password, mysql_db_name, mysql_update_script)
    with open(mysql_updater, 'w') as f:
        f.write(mysql_script_content)
    with open(os.devnull, 'w') as devnull:
        subprocess.call([mysql_updater], shell=False, stdout=devnull, stderr=devnull)
    print 'done.'

def extract_orthographies_from_application_settings(applicationsettings):
    orthographies = []
    for i in range(1,6):
        if applicationsettings['objectLanguageOrthography%d' % i]:
            orthographies.append({
                'orthography': applicationsettings['objectLanguageOrthography%d' % i],
                'name': applicationsettings['objectLanguageOrthography%dName' % i],
                'lowercase': applicationsettings['OLO%dLowercase' % i],
                'initial_glottal_stops': applicationsettings['OLO%dInitialGlottalStops' % i],
                'datetime_modified': applicationsettings['datetime_modified'],
            })
    return orthographies

def fix_orthography_table(engine, orthography_table, application_settings_collation):
    """Create some orthography rows using all of the unique orthographies implicit in the applicationsettings table."""
    print_('Fixing the orthography table ... ')
    if application_settings_collation.startswith('latin'):
        engine.execute('set names utf8;')
    else:
        engine.execute('set names latin1;')
    applicationsettings = engine.execute(applicationsettings_table.select()).fetchall()
    orthographies_dict = {}
    for applicationsetting in applicationsettings:
        orthographies = extract_orthographies_from_application_settings(applicationsetting)
        for orthography in orthographies:
            orthographies_dict.setdefault(
                (normalize(orthography['name']), normalize(orthography['orthography']),
                 orthography['lowercase'], orthography['initial_glottal_stops']), []).\
                append(orthography['datetime_modified'])
    buffer1 = []
    for (name, orthography, lowercase, initial_glottal_stops), dts in orthographies_dict.items():
        dts = [x for x in dts if x]
        if dts:
            max_dt_modified = max(dts)
        else:
            max_dt_modified = now_string
        buffer1.append({'name': name, 'orthography': orthography, 'lowercase': lowercase,
            'initial_glottal_stops': initial_glottal_stops, 'datetime_modified': max_dt_modified})
    engine.execute('set names utf8;')
    if buffer1:
        insert = orthography_table.insert().values(**dict([(k, bindparam(k)) for k in buffer1[0]]))
        engine.execute(insert, buffer1)
    print 'done.'

def get_orthographies_by_name(engine):
    """Return a dict form orthography names to the largest id corresponding to an orthography with that name."""
    orthographies = {}
    engine.execute('set names utf8;')
    query = 'SELECT id, name FROM orthography;'
    result = engine.execute(query).fetchall()
    for id, name in result:
        orthographies.setdefault(name, []).append(id)
    for name, ids in orthographies.items():
        orthographies[name] = max(ids)
    return orthographies

def collation2charset(collation):
    return {'utf8_general_ci': 'utf8'}.get(collation, 'latin1')

def fix_applicationsettings_table(engine, applicationsettings_table, user_table, now_string, table_collations):
    """Fix the applicationsettings table: create the orthography and unrestricted_users relations."""
    print_('Fixing the applicationsettings table ... ')
    msgs = []
    orthographies = get_orthographies_by_name(engine)
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    users = engine.execute(user_table.select()).fetchall()
    user_ids = [u['id'] for u in users]
    buffer1 = []
    for row in engine.execute(applicationsettings_table.select()):
        # Convert the orthography references by name to foreign key id references
        values = row2dict(row)
        if row['storageOrthography']:
            orthography_id = getOrthographyReferenced(values['storageOrthography'], values, orthographies)
            if orthography_id:
                values['storage_orthography_id'] = orthography_id
        if row['defaultInputOrthography']:
            orthography_id = getOrthographyReferenced(values['defaultInputOrthography'], values, orthographies)
            if orthography_id:
                values['input_orthography_id'] = orthography_id
        if row['defaultOutputOrthography']:
            orthography_id = getOrthographyReferenced(values['defaultOutputOrthography'], values, orthographies)
            if orthography_id:
                values['output_orthography_id'] = orthography_id
        buffer1.append(values)
        try:
            unrestricted_user_ids = json.loads(values['unrestrictedUsers'])
            for user_id in unrestricted_user_ids:
                if user_id in user_ids:
                    engine.execute(
                        "INSERT INTO applicationsettingsuser (applicationsettings_id, user_id, datetime_modified) VALUES (%d, %d, '%s');" % (
                        values['id'], user_id, now_string))
                else:
                    msgs.append('WARNING: user %d was listed as unrestricted but this user does not exist.\n' % user_id)
        except Exception:
            pass
    if buffer1:
        engine.execute('set names utf8;')
        update = applicationsettings_table.update().where(applicationsettings_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0].keys() if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'
    return msgs

def fix_user_table(engine, user_table):
    """Generate new values for password, salt, html, input_orthography_id and output_orthography_id."""
    print_('Fixing the user table ... ')
    msgs = []
    orthographies = get_orthographies_by_name(engine)
    try:
        engine.execute('set names utf8;')
        current_application_settings = engine.execute('SELECT * FROM applicationsettings ORDER BY id DESC LIMIT 1;').fetchall()[0]
    except Exception:
        current_application_settings = None
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    buffer1 = []
    for row in engine.execute(user_table.select()):
        values = row2dict(row)
        last_name = values['last_name']
        first_name = values['first_name']
        values['html'] = rst2html(values['page_content'])
        values['salt'] = generateSalt()
        new_password = generatePassword()
        values['password'] = encryptPassword(new_password, values['salt'])
        msgs.append('%s %s (%s) now has the password %s' % (first_name, last_name, values['email'], new_password))
        if values['role'] not in ('administrator', 'contributor', 'viewer'):
            msgs.append('User %d (%s %s) had an invalid role (%s); now changed to viewer' % (values['id'], first_name, last_name, values['role']))
            values['role'] = 'viewer'
        values['input_orthography_id'] = values['output_orthography_id'] = None
        if current_application_settings:
            if values['inputOrthography']:
                orthography_name = current_application_settings['objectLanguageOrthography%sName' % values['inputOrthography'].split()[-1]]
                values['input_orthography_id'] = orthographies.get(orthography_name, None)
            if values['outputOrthography']:
                orthography_name = current_application_settings['objectLanguageOrthography%sName' % values['outputOrthography'].split()[-1]]
                values['output_orthography_id'] = orthographies.get(orthography_name, None)
        buffer1.append(values)
    engine.execute('set names utf8;')
    if buffer1:
        update = user_table.update().where(user_table.c.id==bindparam('id_')).\
            values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'
    return msgs

def fix_collection_table(engine, collection_table, collectionbackup_table, user_table):
    """Add UUID, html, contents_unpacked and modifier_id values to the collections.  Also,
    add UUID values to the backups of each collection.  Return a list of collection ids corresponding
    to those that reference other collections.

    .. note:: 

        There is a somewhat nasty complication that arises because of a change
        in how backupers/modifiers are recorded with backups.  In the OLD 0.2.7, every
        time a backup occurs, the backuper value of the backup is set to the user who
        made the backup and this information is not stored in the original.  In the OLD 1.0,
        creates, updates and deletes all set the modifier value to the user who performed
        the action and then this info is copied to the modifier value of the backup.  Thus we
        must perform the following transformations:

        for collection in collections:
            if collection has a backuper
                then it has been updated, so we should
                set its modifier to the user referenced in the backuper attribute of its most recent backuper
            else
                then it was created but never updated or deleted, so we should
                set its modifier to its enterer
        for collectionbackup in collectionbackups:
            if there are older backups of the same collection
                then set the modifier of the present collectionbackup to the backuper value of the most recent such sister backup
        else
            this is the first backup and its modifier should be its enterer

    """
    print_('Fixing the collection table ... ')
    collectionReferencePattern = re.compile('[cC]ollection[\[\(](\d+)[\]\)]')
    msgs = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    users = engine.execute(user_table.select()).fetchall()
    collectionbackups = engine.execute(collectionbackup_table.select()).fetchall()
    buffer1 = []
    buffer2 = []
    for row in engine.execute(collection_table.select()):
        values = row2dict(row)
        values['UUID'] = str(uuid4())
        values['html'] = rst2html(values['contents'])
        values['contents_unpacked'] = values['contents']
        backups = sorted([cb for cb in collectionbackups if cb['collection_id'] == values['id']],
                         key=lambda cb: cb['datetime_modified'])
        if backups:
            try:
                most_recent_backuper = json.loads(backups[-1]['backuper'])['id']
                if [u for u in users if u['id'] == most_recent_backuper]:
                    values['modifier_id'] = most_recent_backuper
                else:
                    values['modifier_id'] = values['enterer_id']
                    msgs.append('WARNING: there is no user with id %d to be the most recent backuper for for collection %d' % (
                        most_recent_backuper, values['id']))
            except Exception:
                msgs.append('''WARNING: there are %d backups for collection %d; however,
it was not possible to extract a backuper from the most recent one (backuper value: %s)'''.replace('\n', ' ') % (
                        len(backups), values['id'], backups[-1]['backuper']))
                values['modifier_id'] = values['enterer_id']
        else:
            values['modifier_id'] = values['enterer_id']
        if collectionReferencePattern.search(row['contents']):
            msgs.append('''WARNING: collection %d references other collections; please update this collection via the
OLD interface in order to generate appropriate html and contents_unpacked values.''' % values['id'])
        buffer1.append(values)
        for cb in backups:
            buffer2.append({'cb_id': cb['id'], 'UUID': values['UUID']})
    engine.execute('set names utf8;')
    if buffer1:
        update = collection_table.update().where(collection_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    if buffer2:
        update = collectionbackup_table.update().where(collectionbackup_table.c.id==bindparam('cb_id')).\
                values(UUID=bindparam('UUID'))
        engine.execute(update, buffer2)
    print 'done.'
    return msgs

def fix_collectionbackup_table(engine, collectionbackup_table):
    """Add html, modifier and (potentially) UUID values to the collections backups."""
    print_('Fixing the collectionbackup table ... ')
    uuidless = {} # maps collection ids to UUIDs
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    collectionbackups = engine.execute(collectionbackup_table.select()).fetchall()
    buffer1 = []
    for row in collectionbackups:
        values = row2dict(row)
        values['html'] = rst2html(values['contents'])
        backups = sorted([cb for cb in collectionbackups if cb['collection_id'] == values['collection_id']],
                         key=lambda cb: cb['datetime_modified'])
        if backups:
            most_recent_backuper = backups[-1]['backuper']
            values['modifier'] = most_recent_backuper
        else:
            values['modifier'] = row['enterer']
        # Any cbs without UUID values must be from deleted collections
        if values['UUID'] is None:
            uuid = uuidless.get(values['collection_id'], uuid4())
            uuidless[values['collection_id']] = uuid
            values['UUID'] = uuid
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8;')
        update = collectionbackup_table.update().where(collectionbackup_table.c.id==bindparam('id_')).\
                values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def fix_elicitationmethod_table(engine, elicitationmethod_table):
    print_('Fixing the elicitationmethod table ...')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(elicitationmethod_table.select()):
        values = row2dict(row)
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = elicitationmethod_table.update().where(elicitationmethod_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def fix_file_table(engine, file_table):
    """Fix the file table: if the file has a url value, append it to the description 
    value and delete it from the url value; otherwise, set the filename value to the name value.
    """
    print_('Fixing the file table ... ')
    msgs = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    files = engine.execute(file_table.select()).fetchall()
    buffer1 = []
    for row in files:
        values = row2dict(row)
        if row['url']:
            values['url'] = ''
            values['description'] = '%s %s' % (row['description'], row['url'])
            messages.append('''WARNING: the url/embeddedFileMarkup value of file %d has been appended 
to its description value.  Please alter this file by hand so that it has 
an appropriate url value'''.replace('\n', ' ') % row['id'])
            buffer1.append(values)
        else:
            values['filename'] = row['name']
            buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8;')
        update = file_table.update().where(file_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'
    return msgs

def fix_form_table(engine, form_table, formbackup_table, user_table, default_morphemes):
    """Give UUID, modifier_id values to the form table.  Also give UUID values to
    all form backups that are backups of existing forms.

    :param bool default_morphemes: if True, then forms that have no morpheme_break and no morpheme_gloss
        and whose transcription contains no space will receive a default morpheme_break value (the value
        of the transcription attribute) and a default morpheme_gloss value (the value of the first translation
        transcription with spaces replaced by periods).

    .. note::

        There is a somewhat nasty complication that arises because of a change
        in how backupers/modifiers are recorded with backups.  In the OLD 0.2.7, every 
        time a backup occurs, the backuper value of the backup is set to the user who
        made the backup and this information is not stored in the original.  In the OLD 1.0,
        creates, updates and deletes all set the modifier value to the user who performed
        the action and then this info is copied to the modifier value of the backup.  Thus we
        must perform the following transformations:
        for form in forms:
            if forms has a backuper
                then it has been updated, so we should
                set its modifier to the user referenced in the backuper attribute of its most recent backuper
            else
                then it was created but never updated or deleted, so we should
                set its modifier to its enterer
        for formbackup in formbackups:
            if there are older backups of the same form
                then set the modifier of the present formbackup to the backuper value of the most recent such sister backup
        else
            this is the first backup and its modifier should be its enterer

    """

    print_('Fixing the form table ... ')
    msgs = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    users = engine.execute(user_table.select()).fetchall()
    formbackups = engine.execute(formbackup_table.select()).fetchall()
    if default_morphemes:
        translations = dict([(row['form_id'], row['transcription']) for row in 
            engine.execute(translation_table.select().order_by(translation_table.c.id.desc())).fetchall()])
    form_update_cache = []
    formbackup_update_cache = []
    for row in engine.execute(form_table.select()):
        values = row2dict(row)
        values['UUID'] = str(uuid4())
        if default_morphemes and not values['morpheme_break'] and not values['morpheme_gloss'] and ' ' not in values['transcription']:
            values['morpheme_break'] = values['transcription']
            values['morpheme_gloss'] = translations[values['id']].replace(' ', '.')
        backups = sorted([fb for fb in formbackups if fb['form_id'] == row['id']],
                         key=lambda fb: fb['datetime_modified'])
        if backups:
            try:
                most_recent_backuper = json.loads(backups[-1]['backuper'])['id']
                if [u for u in users if u['id'] == most_recent_backuper]:
                    values['modifier_id'] = most_recent_backuper
                else:
                    values['modifier_id'] = row['enterer_id']
                    msgs.append('WARNING: there is no user %d to serve as the most recent backuper for form %d' % (most_recent_backuper, row['id']))
            except Exception:
                msgs.append('''WARNING: there are %d backups for form %d; however,
it was not possible to extract a backuper from the most recent one (backuper value: %s)'''.replace('\n', ' ') % (
                        len(backups), row['id'], backups[-1]['backuper']))
                values['modifier_id'] = row['enterer_id']
        else:
            values['modifier_id'] = row['enterer_id']
        form_update_cache.append(values)
        for fb in backups:
            formbackup_update_cache.append({'fb_id': fb['id'], 'UUID': values['UUID']})
    engine.execute('set names utf8;')
    if form_update_cache:
        update = form_table.update().where(form_table.c.id==bindparam('id_')).\
            values(**dict([(k, bindparam(k)) for k in form_update_cache[0] if k not in ('id', 'id_')]))
        engine.execute(update, form_update_cache)
    if formbackup_update_cache:
        update = formbackup_table.update().where(formbackup_table.c.id==bindparam('fb_id')).values(UUID=bindparam('UUID'))
        engine.execute(update, formbackup_update_cache)
    print 'done.'
    return msgs

def fix_formbackup_table(engine, formbackup_table):
    """Give each form a modifier value and (potentially) a UUID value also (if it doesn't have one)."""
    print_('Fixing the formbackup table ... ')
    uuidless = {} # maps form ids to UUIDs
    buffer1 = []
    formbackups = engine.execute(formbackup_table.select()).fetchall()
    for row in formbackups:
        values = row2dict(row)
        backups = sorted([fb for fb in formbackups if fb['form_id'] == values['form_id']],
                         key=lambda fb: fb['datetime_modified'])
        if backups:
            most_recent_backuper = backups[-1]['backuper']
            values['modifier'] = most_recent_backuper
        else:
            values['modifier'] = values['enterer']
        if values['UUID'] is None:
            uuid = uuidless.get(row['form_id'], uuid4())
            uuidless[row['form_id']] = uuid
            values['UUID'] = uuid
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8;')
        update = formbackup_table.update().where(formbackup_table.c.id==bindparam('id_')).\
                values(modifier=bindparam('modifier'))
        engine.execute(update, buffer1)
    print 'done.'

def fix_language_table(engine, language_table):
    """Unicode-normalize and UTF-8-ify the data in the language table."""
    print_('Fixing the language table ...')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(language_table.select()):
        values = row2dict(row)
        values['Id_'] = values['Id']
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = language_table.update().where(language_table.c.Id==bindparam('Id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('Id', 'Id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def fix_translation_table(engine, translation_table):
    """Unicode-normalize and UTF-8-ify the data in the translation table."""
    print_('Fixing the translation table ...')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(translation_table.select()):
        values = row2dict(row)
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = translation_table.update().where(translation_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def fix_page_table(engine, page_table):
    print_('Fixing the page table ...')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(page_table.select()):
        values = row2dict(row)
        values['html'] = rst2html(values['content'])
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = page_table.update().where(page_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def fix_phonology_table(engine, phonology_table, phonologybackup_table, user_table):
    """Give each phonology UUID and modifier_id values; also give the phonology backups of
    existing phonologies UUID values.

    """
    print_('Fixing the phonology table ... ')
    msgs = []
    #engine.execute('set names latin1')
    engine.execute('set names utf8;')
    users = engine.execute(user_table.select()).fetchall()
    phonologybackups = engine.execute(phonologybackup_table.select()).fetchall()
    buffer1 = []
    buffer2 = []
    for row in engine.execute(phonology_table.select()):
        values = row2dict(row)
        values['UUID'] = str(uuid4())
        backups = sorted([pb for pb in phonologybackups if pb['phonology_id'] == values['id']],
                         key=lambda pb: pb['datetime_modified'])
        if backups:
            try:
                most_recent_backuper = json.loads(backups[-1]['backuper'])['id']
                if [u for u in users if u['id'] == most_recent_backuper]:
                    values['modifier_id'] = most_recent_backuper
                else:
                    values['modifier_id'] = values['enterer_id']
                    msgs.append('There is no user %d to serve as the most recent backuper for phonology %d' % (most_recent_backuper, values['id']))
            except Exception:
                msgs.append('''WARNING: there are %d backups for phonology %d; however,
it was not possible to extract a backuper from the most recent one (backuper value: %s)'''.replace('\n', ' ') % (
                        len(backups), values['id'], backups[-1]['backuper']))
                values['modifier_id'] = values['enterer_id']
        else:
            values['modifier_id'] = values['enterer_id']
        buffer1.append(values)
        for pb in backups:
            buffer2.append({'pb_id': pb['id'], 'UUID': values['UUID']})
    update = phonologybackup_table.update().where(phonologybackup_table.c.id==bindparam('pb_id')).\
            values(UUID=bindparam('UUID'))
    engine.execute(update, buffer2)
    if buffer1:
        engine.execute('set names utf8;')
        update = phonology_table.update().where(phonology_table.c.id==bindparam('id_')).\
                values(modifier_id=bindparam('modifier_id'), UUID=bindparam('UUID'))
        engine.execute(update, buffer1)
    print 'done.'
    return msgs

def fix_phonologybackup_table(engine, phonologybackup_table):
    """Provide each phonology backup with a modifier value and (potentially) a UUID value too."""
    print_('Fixing the phonologybackup table ... ')
    uuidless = {} # maps phonology ids to UUIDs
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    phonologybackups = engine.execute(phonologybackup_table.select()).fetchall()
    for row in phonologybackups:
        values = row2dict(row)
        backups = sorted([pb for pb in phonologybackups if pb['phonology_id'] == values['phonology_id']],
                         key=lambda pb: pb['datetime_modified'])
        if backups:
            most_recent_backuper = backups[-1]['backuper']
            values['modifier'] = most_recent_backuper
        else:
            values['modifier'] = row['enterer']
        if row['UUID'] is None:
            uuid = uuidless.get(row['phonology_id'], uuid4())
            uuidless[row['phonology_id']] = uuid
            values['UUID'] = uuid
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = phonologybackup_table.update().where(phonologybackup_table.c.id==bindparam('id_')).\
                values(UUID=bindparam('UUID'), modifier=bindparam('modifier'))
        engine.execute(update, buffer1)
    print 'done.'

def fix_tag_table(engine, tag_table):
    """Warn the user about duplicate tags."""
    print_('Fixing the tag table ... ')
    msgs = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    tags = [row['name'] for row in engine.execute(tag_table.select()).fetchall()]
    duplicate_tags = set([x for x in tags if len([y for y in tags if y == x]) > 1])
    for dt in duplicate_tags:
        msgs.append('There is more than one tag named "%s"; please manually change the name of one of them.' % dt)
    buffer1 = []
    for row in engine.execute(tag_table.select()):
        values = row2dict(row)
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = tag_table.update().where(tag_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'
    return msgs

def fix_source_table(engine, source_table):
    """Create an author value and put the fullReference value in the annote field.
    Return a message explaining what was done.
    """
    print_('Fixing the source table ... ')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(source_table.select()):
        values = row2dict(row)
        first_name = values['authorFirstName']
        last_name = values['authorLastName']
        if first_name and last_name:
            author = '%s %s' % (first_name, last_name)
        else:
            author = None
        values['author'] = author
        values['annote'] = values['fullReference']
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8;')
        update = source_table.update().where(source_table.c.id==bindparam('id_')).\
                values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'
    return ['''Sources have been updated.
An author value was constructed using the authorFirstName and authorLastName values.
The fullReference value was moved to the annote attribute.
The soures will need to be updated manually.'''.replace('\n', ' ')]

def fix_speaker_table(engine, speaker_table):
    """Generate an html value for each speaker."""
    print_('Fixing the speaker table ... ')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(speaker_table.select()):
        values = row2dict(row)
        values['html'] = rst2html(values['page_content'])
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8;')
        update = speaker_table.update().where(speaker_table.c.id==bindparam('id_')).\
                values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def fix_syntacticcategory_table(engine, syntacticcategory_table):
    print_('Fixing the syntactic category table ...')
    buffer1 = []
    #engine.execute('set names latin1;')
    engine.execute('set names utf8;')
    for row in engine.execute(syntacticcategory_table.select()):
        values = row2dict(row)
        buffer1.append(values)
    if buffer1:
        engine.execute('set names utf8')
        update = syntacticcategory_table.update().where(syntacticcategory_table.c.id==bindparam('id_')).\
                    values(**dict([(k, bindparam(k)) for k in buffer1[0] if k not in ('id', 'id_')]))
        engine.execute(update, buffer1)
    print 'done.'

def cleanup_db(mysql_db_name, mysql_cleanup_script, mysql_updater, mysql_username, mysql_password):
    """Run the MySQL cleanup script against the db (cf. cleanup_SQL for the contents of this script)."""
    print_('Cleaning up ... ')
    mysql_script_content = '#!/bin/sh\nmysql -u %s -p%s %s < %s' % (mysql_username, mysql_password, mysql_db_name, mysql_cleanup_script)
    with open(mysql_updater, 'w') as f:
        f.write(mysql_script_content)
    with open(os.devnull, 'w') as devnull:
        subprocess.call([mysql_updater], shell=False, stdout=devnull, stderr=devnull)
    print 'done.'

def getOrthographyReferenced(crappyReferenceString, row, orthographies):
    """Return the id of the orthography model referenced in ``crappyReferenceString``.
    ``crappyReferenceString`` is something like "Orthography 1" or "Object Language Orthography 3"
    and ``row`` is a row in the applicationsettings table.  ``orthographies`` is a dict from
    orthography names to orthography ids.

    """
    orthographyName = row['objectLanguageOrthography%sName' % crappyReferenceString.split()[-1]]
    return orthographies.get(orthographyName, None)

def rst2html(string):
    """Covert a restructuredText string to HTML."""
    try:
        return publish_parts(unicode(string, 'utf8'), writer_name='html',
                settings_overrides={'report_level':'quiet'})['html_body'].encode('utf8')
    except:
        return string

def generateSalt():
    return str(uuid4().hex)

def encryptPassword(password, salt):
    """Use PassLib's pbkdf2 implementation to generate a hash from a password.
    Cf. http://packages.python.org/passlib/lib/passlib.hash.pbkdf2_digest.html#passlib.hash.pbkdf2_sha512
    """
    return pbkdf2_sha512.encrypt(password, salt=salt)

def generatePassword(length=12):
    """Generate a random password containing 3 UC letters, 3 LC ones, 3 digits and 3 symbols."""
    lcLetters = string.letters[:26]
    ucLetters = string.letters[26:]
    digits = string.digits
    symbols = string.punctuation.replace('\\', '')
    password = [choice(lcLetters) for i in range(3)] + \
               [choice(ucLetters) for i in range(3)] + \
               [choice(digits) for i in range(3)] + \
               [choice(symbols) for i in range(3)]
    shuffle(password)
    return ''.join(password)

def normalize_(unistr):
    """Return a unistr using decompositional normalization (NFD)."""
    try:
        return unicodedata.normalize('NFD', unistr)
    except TypeError:
        return unicodedata.normalize('NFD', unicode(unistr))
    except UnicodeDecodeError:
        return unistr

def parse_arguments(arg_list):
    result = {}
    map_ = {'-d': 'mysql_db_name', '-u': 'mysql_username', '-p': 'mysql_password',
            '-f': 'mysql_dump_file', '--default-morphemes': 'default_morphemes'}
    iterator = iter(arg_list)
    try:
        for element in iterator:
            if element in map_:
                if element == '--default-morphemes':
                    result[map_[element]] = True
                else:
                    result[map_[element]] = iterator.next()
    except Exception:
        pass
    if len(set(['mysql_db_name', 'mysql_username', 'mysql_password']) & set(result.keys())) != 3:
        sys.exit('Usage: python old_update_db_0.2.7_1.0ay.py -d mysql_db_name -u mysql_username -p mysql_password [-f mysql_dump_file] [--default-morphemes]')
    return result

if __name__ == '__main__':

    # User must supply values for mysql_db_name, mysql_username and
    # mysql_password.
    # optional argument: -p mysql_dump_file: path to a dump file
    # optional argument: --default-morphemes: if present, default morphemes
    # will be generated (see below)

    arguments = parse_arguments(sys.argv[1:])
    mysql_dump_file = arguments.get('mysql_dump_file')
    mysql_db_name = arguments.get('mysql_db_name')
    mysql_username = arguments.get('mysql_username')
    mysql_password = arguments.get('mysql_password')
    default_morphemes = arguments.get('default_morphemes', False)

    # The SQLAlchemy/MySQLdb/MySQL connection objects
    sqlalchemy_url = 'mysql://%s:%s@localhost:3306/%s' % (
        mysql_username, mysql_password, mysql_db_name)
    engine = create_engine(sqlalchemy_url)
    # try:
    #     engine.execute('SHOW TABLES;').fetchall()
    # except Exception:
    #     sys.exit('Error: the MySQL database name, username and password are not valid.')
    meta = MetaData()

    now = datetime.datetime.utcnow()
    now_string = now.isoformat().replace('T', ' ').split('.')[0]
    here = os.path.dirname(os.path.realpath(__file__))

    # The shell script that will be used multiple times to load the MySQL
    # scripts below
    mysql_updater_name = 'tmp.sh'
    mysql_updater = write_updater_executable(mysql_updater_name, here)

    # The executable that does the database drop/create and loads the dump file recreate
    mysql_recreate_script_name = 'old_recreate_db_0.2.7_1.1.sql'
    mysql_recreate_script = write_recreate_executable(mysql_recreate_script_name, here)

    # The executable that does the preliminary update
    mysql_update_script_name = 'old_update_db_0.2.7_1.1.sql'
    mysql_update_script = write_update_executable(mysql_update_script_name, here)

    # The executable that fixes the character set
    mysql_charset_script_name = 'old_charset_db_0.2.7_1.1.sql'
    mysql_charset_script = write_charset_executable(mysql_charset_script_name, here)

    # The executable that performs the final clean up
    mysql_cleanup_script_name = 'old_cleanup_db_0.2.7_1.1.sql'
    mysql_cleanup_script = write_cleanup_executable(mysql_cleanup_script_name, here)

    # If a dump file path was provided, recreate the db using it.
    if mysql_dump_file:
        if os.path.isfile(mysql_dump_file):
            recreate_database(mysql_db_name, mysql_dump_file, mysql_username,
                    mysql_password, mysql_updater, mysql_recreate_script)
        else:
            sys.exit('Error: there is no such dump file '
                '%s' % os.path.join(os.getcwd(), mysql_dump_file))

    # Get info about the database
    db_charset, table_collations, columns = get_database_info(mysql_db_name, mysql_username, mysql_password)

    # Change the character set to UTF-8
    change_db_charset_to_utf8(mysql_db_name, mysql_charset_script,
        mysql_username, mysql_password, mysql_updater, db_charset,
        table_collations, columns)

    # Perform the preliminary update of the database using ``mysql_update_script``
    perform_preliminary_update(mysql_db_name, mysql_update_script, mysql_username, mysql_password, mysql_updater)

    # print 're-created database and did preliminary update ...'
    # sys.exit(0)

    # Get info about the database post utf8 conversion
    db_charset_new, table_collations_new, columns_new = get_database_info(mysql_db_name, mysql_username, mysql_password)

    ##################################################################################
    # Now we update the values of the newly modified database Pythonically
    ##################################################################################

    applicationsettings_table = Table('applicationsettings', meta, autoload=True, autoload_with=engine)
    collection_table = Table('collection', meta, autoload=True, autoload_with=engine)
    collectionbackup_table = Table('collectionbackup', meta, autoload=True, autoload_with=engine)
    elicitationmethod_table = Table('elicitationmethod', meta, autoload=True, autoload_with=engine)
    file_table = Table('file', meta, autoload=True, autoload_with=engine)
    form_table = Table('form', meta, autoload=True, autoload_with=engine)
    formbackup_table = Table('formbackup', meta, autoload=True, autoload_with=engine)
    language_table = Table('language', meta, autoload=True, autoload_with=engine)
    orthography_table = Table('orthography', meta, autoload=True, autoload_with=engine)
    page_table = Table('page', meta, autoload=True, autoload_with=engine)
    phonology_table = Table('phonology', meta, autoload=True, autoload_with=engine)
    phonologybackup_table = Table('phonologybackup', meta, autoload=True, autoload_with=engine)
    source_table = Table('source', meta, autoload=True, autoload_with=engine)
    speaker_table = Table('speaker', meta, autoload=True, autoload_with=engine)
    syntacticcategory_table = Table('syntacticcategory', meta, autoload=True, autoload_with=engine)
    tag_table = Table('tag', meta, autoload=True, autoload_with=engine)
    translation_table = Table('translation', meta, autoload=True, autoload_with=engine)
    user_table= Table('user', meta, autoload=True, autoload_with=engine)

    messages = []
    fix_orthography_table(engine, orthography_table, table_collations['application_settings'])
    messages += fix_applicationsettings_table(engine, applicationsettings_table, user_table, now_string, table_collations)
    messages += fix_user_table(engine, user_table)
    messages += fix_collection_table(engine, collection_table, collectionbackup_table, user_table)
    fix_collectionbackup_table(engine, collectionbackup_table)
    fix_elicitationmethod_table(engine, elicitationmethod_table)
    messages += fix_file_table(engine, file_table)
    messages += fix_form_table(engine, form_table, formbackup_table, user_table, default_morphemes)
    fix_formbackup_table(engine, formbackup_table)
    fix_language_table(engine, language_table)
    fix_page_table(engine, page_table)
    messages += fix_phonology_table(engine, phonology_table, phonologybackup_table, user_table)
    fix_phonologybackup_table(engine, phonologybackup_table)
    messages += fix_tag_table(engine, tag_table)
    messages += fix_source_table(engine, source_table)
    fix_speaker_table(engine, speaker_table)
    fix_syntacticcategory_table(engine, syntacticcategory_table)
    fix_translation_table(engine, translation_table)
    cleanup_db(mysql_db_name, mysql_cleanup_script, mysql_updater, mysql_username, mysql_password)
    os.remove(mysql_updater)
    print 'OK'

    print '\n\n%s' % '\n\n'.join(messages)

    print '\nFinally, you should request forms.update_morpheme_references in order to generate valid break_gloss_category values and to regenerate the other morpheme-related values.\n\n'

    # TODO: what to do about files without lossy copies?  Create an admin-only method of the forms controller that creates
    #    lossy copies for all relevant files that lack such.
    # TODO: make sure that file names match the names of the files on the file system, i.e., post normalization...
    # TODO: verify user.input_orthography_id and user.output_orthography_id on an app that has specifications for these
    # TODO: search a live OLD app and make sure that the normalization has worked...
    # TODO: dump the schema of an altered db and make sure it matches that of a system-generated one (e.g., old_test)

    # Post-processing:
    # 1. serve the system and request form.update_morpheme_references in order to, well, do that ...
    # 2. find all forms and collections that lack enterers and give them a default enterer (cf. the BLA OLD).
    #    Then find all forms and collections lacking modifiers and give them the value of their enterers.

