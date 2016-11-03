===============================================================================
  Online Linguistic Database README
===============================================================================


Getting Started
-------------------------------------------------------------------------------

- cd <directory containing this file>

- $VENV/bin/pip install -e .

- $VENV/bin/initialize_old_db development.ini

- $VENV/bin/pserve development.ini


Pylons 2 Pyramid Migration
-------------------------------------------------------------------------------

Done
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

├── __init__.py
├── config
│   ├── environment.py
│   ├── middleware.py
│   ├── deployment.ini_tmpl
        - WHAT TO DO ABOUT THIS? JUST COPIED IT OVER.
│   ├── routing.py

├── model
│   ├── __init__.py
        - NOT SURE WHAT TO DO WITH THIS ...
│   ├── __init__.py
│   ├── applicationsettings.py
│   ├── collection.py
│   ├── collectionbackup.py
│   ├── corpus.py
│   ├── corpusbackup.py
│   ├── elicitationmethod.py
│   ├── file.py
│   ├── form.py
│   ├── formbackup.py
│   ├── formsearch.py
│   ├── keyboard.py
│   ├── language.py
│   ├── meta.py
│   ├── model.py
│   ├── morphemelanguagemodel.py
│   ├── morphemelanguagemodelbackup.py
│   ├── morphologicalparser.py
│   ├── morphologicalparserbackup.py
│   ├── morphology.py
│   ├── morphologybackup.py
│   ├── orthography.py
│   ├── page.py
│   ├── phonology.py
│   ├── phonologybackup.py
│   ├── source.py
│   ├── speaker.py
│   ├── syntacticcategory.py
│   ├── tag.py
│   ├── translation.py
│   ├── user.py

├── controllers
│   ├── __init__.py

├── lib
│   ├── __init__.py
    ├── parser.py
    ├── pyramid_routehelper.py
│   ├── simplelm
│   │   ├── NGramStack.py
│   │   ├── README.md
│   │   ├── SimpleARPA2WFSA.py
│   │   ├── SimpleAbs.py
│   │   ├── SimpleCount.py
│   │   ├── SimpleKN.py
│   │   ├── SimpleModKN.py
│   │   ├── SimplePFracKN.py
│   │   ├── __init__.py
│   │   ├── evaluatelm.py
│   │   ├── evaluatelm.py~
│   │   ├── run-NGramLibrary.sh
│   │   └── train.corpus
│   ├── SQLAQueryBuilder.py
│   ├── app_globals.py
        - WARNING/TODO: not using this


Doing
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

├── lib
│   ├── auth.py

TODO
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

├── lib
│   ├── base.py
│   ├── bibtex.py
│   ├── foma_worker.py
│   ├── helpers.py
│   ├── orthography.py
│   ├── parse.py
│   ├── parser.py
│   ├── resize.py
│   ├── schemata.py

│   ├── simplelmc
│   ├── utils.py

├── controllers
│   ├── collectionbackups.py
│   ├── corpora.py
│   ├── corpusbackups.py
│   ├── cors.py
│   ├── elicitationmethods.py
│   ├── error.py
│   ├── files.py
│   ├── formbackups.py
│   ├── forms.py
│   ├── formsearches.py
│   ├── info.py
│   ├── keyboards.py
│   ├── languages.py
│   ├── login.py
│   ├── morphemelanguagemodelbackups.py
│   ├── morphemelanguagemodels.py
│   ├── morphologicalparserbackups.py
│   ├── morphologicalparsers.py
│   ├── morphologies.py
│   ├── morphologybackups.py
│   ├── oldcollections.py
│   ├── orthographies.py
│   ├── pages.py
│   ├── phonologies.py
│   ├── phonologybackups.py
│   ├── rememberedforms.py
│   ├── sources.py
│   ├── speakers.py
│   ├── syntacticcategories.py
│   ├── users.py

├── model
│   ├── db_update_scripts
│   │   ├── 0.2.7_1.0a1
│   │   │   └── old_update_db_0.2.7_1.0a1.py
│   │   ├── 0.2.7_1.0a2
│   │   │   └── old_update_db_0.2.7_1.0a1.py
│   │   ├── 0.2.7_1.1
│   │   │   ├── mysql_dump_loader.sh
│   │   │   ├── old_charset_db_0.2.7_1.1.sql
│   │   │   ├── old_cleanup_db_0.2.7_1.1.sql
│   │   │   ├── old_recreate_db_0.2.7_1.1.sql
│   │   │   ├── old_update_db_0.2.7_1.1.py
│   │   │   └── old_update_db_0.2.7_1.1.sql
│   │   ├── 1.1_1.2.3
│   │   │   ├── old_update_db_1.1_1.2.3.py
│   │   │   ├── old_update_db_1.1_1.2.3.sql
│   │   │   └── tmp.sh
│   │   ├── 1.2.4_1.2.5
│   │   │   └── old_update_db_1.2.4_1.2.5.py
│   │   └── makemigrations.py

├── public
│   └── iso_639_3_languages_data
│       ├── iso_639_3.tab
│       └── iso_639_3_trunc.tab
├── syncs.sqlite
├── tests
│   ├── __init__.py
│   ├── __init__.py.bk
│   ├── data
│   │   ├── datasets
│   │   │   ├── loremipsum_100.txt
│   │   │   ├── loremipsum_1000.txt
│   │   │   ├── loremipsum_10000.txt
│   │   │   ├── loremipsum_100_mysql.sql
│   │   │   └── loremipsum_30000.txt
│   │   ├── files
│   │   │   ├── illicit.html
│   │   │   ├── illicit.wav
│   │   │   ├── large_image.gif
│   │   │   ├── large_image.jpg
│   │   │   ├── large_image.png
│   │   │   ├── old_test.jpg
│   │   │   ├── old_test.ogg
│   │   │   └── old_test.wav
│   │   ├── morphophonologies
│   │   │   ├── blaold_morphophonology.foma
│   │   │   └── blaold_morphophonology.script
│   │   └── phonologies
│   │       ├── test_phonology.script
│   │       ├── test_phonology_large.script
│   │       ├── test_phonology_malformed.script
│   │       ├── test_phonology_medium.script
│   │       ├── test_phonology_no_phonology.script
│   │       └── test_phonology_no_tests.script
│   ├── functional
│   │   ├── __init__.py
│   │   ├── _toggle_tests.py
│   │   ├── test_applicationsettings.py
│   │   ├── test_collectionbackups.py
│   │   ├── test_corpora.py
│   │   ├── test_corpora_large.py
│   │   ├── test_corpusbackups.py
│   │   ├── test_elicitationmethods.py
│   │   ├── test_files.py
│   │   ├── test_files_search.py
│   │   ├── test_formbackups.py
│   │   ├── test_forms.py
│   │   ├── test_forms_search.py
│   │   ├── test_formsearches.py
│   │   ├── test_languages.py
│   │   ├── test_login.py
│   │   ├── test_morphemelanguagemodelbackups.py
│   │   ├── test_morphemelanguagemodels.py
│   │   ├── test_morphologicalparsers.py
│   │   ├── test_morphologies.py
│   │   ├── test_morphologybackups.py
│   │   ├── test_oldcollections.py
│   │   ├── test_oldcollections_search.py
│   │   ├── test_orthographies.py
│   │   ├── test_pages.py
│   │   ├── test_phonologies.py
│   │   ├── test_phonologybackups.py
│   │   ├── test_rememberedforms.py
│   │   ├── test_sources.py
│   │   ├── test_speakers.py
│   │   ├── test_syntacticcategories.py
│   │   ├── test_tags.py
│   │   ├── test_users.py
│   ├── scripts
│   │   └── _requests_tests.py
│   ├── sync
│   ├── test_models.py
├── websetup.py


- Change ``import simplejson as json`` to just ``import json``

- Add Copyright:

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

