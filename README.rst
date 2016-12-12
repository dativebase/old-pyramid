================================================================================
  The Online Linguistic Database (OLD)
================================================================================

.. image:: https://travis-ci.org/jrwdunham/old-pyramid.svg?branch=master
    :target: https://travis-ci.org/jrwdunham/old-pyramid

.. image:: OLD-logo.png

The Online Linguistic Database (OLD) is software for linguistic fieldwork. It
helps groups of linguists, language documenters, and/or language community
members to collaboratively build a web-accessible database of their language
data.

Note: this is the OLD written using the Pyramid framework and is the version
that will be used for current and future development. For the Pylons framework
OLD, see the `Pylons OLD source`_


For detailed information, see the `OLD Web Site`_ or the `Official OLD
Documentation`_.

Dative_ is a GUI for the OLD. See the `Dative source code`_, `Dative's web
site`_, or the `Dative app`_ for more information.


Features
================================================================================

- Collaboration and data sharing
- Advanced search
- Automatic morpheme cross-referencing
- Configurable validation
- Morphological parser & phonology builder
- Text creation
- User access control
- Documentation
- Open source
- Graphical User Interface: Dative
- RESTful JSON API


Technical
================================================================================

The OLD is software for creating RESTful web services that send and receive
data in JSON format. It is written in Python using the `Pyramid web framework`_
and a MySQL database.


Installation
===============================================================================

The Pyramid version of the OLD will be on PyPI soon. Until then, it can be
installed from source::

    $ virtualenv -p /path/to/python3/executable env
    $ source env/bin/activate
    $ git clone git@github.com:jrwdunham/old-pyramid.git
    $ cd old-pyramid
    $ pip install -e ".[testing]"

Create the database tables and directory structure::

    $ initialize_old_db development.ini

Serve::

    $ pserve development.ini

Now if you navigate to http://localhost:6543/ you should see a big JSON object
that describes the OLD's API. If you install _`Dative`, you can use it to
interact with the OLD.

To run the tests::

    $ pytest


To Do
===============================================================================

- Tests in test_forms_search.py are failing because of interaction with other
  tests: the initialize "test" needs to make sure the db is in the correct
  state.



.. _`OLD Web Site`: http://www.onlinelinguisticdatabase.org/
.. _`Official OLD Documentation`: http://online-linguistic-database.readthedocs.org/en/latest/
.. _Dative: http://www.dative.ca/
.. _`Dative source code`: https://github.com/jrwdunham/dative/
.. _`Dative`: https://github.com/jrwdunham/dative/
.. _`Dative's web site`: http://www.dative.ca/
.. _`Dative app`: http://app.dative.ca/
.. _`Pyramid web framework`: http://www.pylonsproject.org/
.. _`Pylons OLD source`_: https://github.com/jrwdunham/old/
