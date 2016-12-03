===============================================================================
  Online Linguistic Database README
===============================================================================

TODO: Tests in test_forms_search.py are failing because of interaction with
other tests: the initialize "test" needs to make sure the db is in the correct
state.


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
│   ├── applicationsettings.py
│   ├── collectionbackups.py
│   ├── corpora.py
│   ├── corpusbackups.py
│   ├── cors.py
│   ├── elicitationmethods.py
│   ├── files.py
│   ├── forms.py
│   ├── formbackups.py
│   ├── formsearches.py
│   ├── info.py
│   ├── oldcollections.py
│   ├── keyboards.py
│   ├── languages.py
│   ├── login.py
│   ├── morphologies.py
│   ├── morphologybackups.py
│   ├── morphemelanguagemodelbackups.py
│   ├── morphemelanguagemodels.py
│   ├── orthographies.py
│   ├── pages.py
│   ├── phonologies.py
│   ├── phonologybackups.py
│   ├── rememberedforms.py
│   ├── sources.py
│   ├── speakers.py
│   ├── syntacticcategories.py
│   ├── users.py

├── lib
│   ├── __init__.py
│   ├── auth.py
│   ├── base.py
│   ├── bibtex.py
│   ├── foma_worker.py
│   ├── helpers.py
│   ├── orthography.py
│   ├── parse.py
    ├── parser.py
    ├── pyramid_routehelper.py TODO: DELETE
│   ├── resize.py
│   ├── schemata.py
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
│   ├── utils.py
│   ├── app_globals.py
        - WARNING/TODO: not using this

├── public
│   └── iso_639_3_languages_data
│       ├── iso_639_3.tab
│       └── iso_639_3_trunc.tab

├── tests

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
│   │   ├── __init__.py (empty)
│   │   ├── _toggle_tests.py (no longer necessary, I think)
|   │   ├── test_auth.py
│   │   ├── test_applicationsettings.py
|   │   ├── test_collectionbackups.py
|   │   ├── test_collections.py (test_oldcollections.py)
│   │   ├── test_collections_search.py (test_oldcollections_search.py)
|   │   ├── test_corpora.py
│   │   ├── test_corpora_large.py
|   │   ├── test_corpusbackups.py
│   │   ├── test_elicitationmethods.py
|   │   ├── test_files.py
│   │   ├── test_files_search.py
│   │   ├── test_formbackups.py
|   │   ├── test_forms.py
│   │   ├── test_formsearches.py
│   │   ├── test_forms_search.py
│   │   ├── test_languages.py
│   │   ├── test_login.py => test_auth.py
│   │   ├── test_morphemelanguagemodelbackups.py
│   │   ├── test_morphemelanguagemodels.py
│   │   ├── test_morphologies.py
│   │   ├── test_morphologybackups.py
│   │   ├── test_orthographies.py
│   │   ├── test_pages.py
│   │   ├── test_phonologies.py
│   │   ├── test_phonologybackups.py
│   │   ├── test_rememberedforms.py
│   │   ├── test_sources.py
│   │   ├── test_speakers.py
│   │   ├── test_syntacticcategories.py
|   │   └── test_tags.py
│   │   ├── test_users.py


Doing
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

├── controllers
│   ├── morphologicalparserbackups.py
│   ├── morphologicalparsers.py
│   ├── functional
│   │   ├── test_morphologicalparsers.py

../../env/bin/python ./../pyl2pyr.py morphologicalparser ~/Documents/old/onlinelinguisticdatabase/tests/functional/test_morphologicalparsers.py tests/functional/test_morphologicalparsers.py


TODO
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

├── controllers
│   ├── error.py ??? ...

├── tests
│   ├── __init__.py
│   ├── __init__.py.bk
│   ├── sync
│   ├── test_models.py


│   ├── scripts
│   │   └── _requests_tests.py

├── syncs.sqlite

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

├── websetup.py

