================================================================================
About
================================================================================

The Online Linguistic Database (OLD) is software for linguistic fieldwork and
language documentation. It facilitates the collaborative storing, searching,
processing and analyzing of linguistic fieldwork data.

Linguistic fieldwork stands to benefit significantly from inter-researcher
collaboration and data-sharing. The OLD arose as a response to a lack of
multi-user cross-platform tools for language documentation and analysis.


Purpose
--------------------------------------------------------------------------------

The OLD seeks to facilitate achievement of the following objectives.

#. Language data can be shared easily between researchers.
#. Language data are intelligently structured (balancing an allowance for
   theoretical and methodological variation with capacity for easy retrieval
   and re-purposing.)
#. Language data are highly searchable.
#. Access to language data can be controlled via authentication and
   authorization.
#. Language data can be re-purposed. E.g., word list data recorded, transcribed
   and analyzed by a phonetician can be used by a syntactician, anthropologist,
   educator and/or community member.
#. Language data are digitized and available for digital processing, e.g.,
   parsing, automated information extraction, corpus analysis, comparative
   cross-linguistic analysis.


What is it?
--------------------------------------------------------------------------------

The OLD is a program for creating collaborative language documentation *web
services* [#f1]_. A web service is like a web site or web application in that
it runs on a web server and responds to HTTP requests. However, a web
service differs from a traditional web application because it is designed to
be accessed by other programs and not (directly) by human users.

The benefit of this design strategy is that a single web service can form a
useful component of a variety of different applications with different goals.
For example, an OLD web service for language *L* could serve data to a mobile
application that helps users to learn *L*.  At the same time, researchers could
be collaboratively entering, searching and processing data on the OLD web
service via a desktop application and/or a browser-based one.

`Dative`_ is a browser-based graphical user interface to the OLD.

The OLD is intended to be set up on a web server. However, it can also easily
be installed on a personal computer for development or experimentation. For
detailed installation instructions see the :ref:`installation-section` section.

The OLD is, at its core, a database-driven application. It is essentially an
interface to a relational database with a specific data structure, or schema.
The schema was designed with the goals of linguistic fieldwork in mind. An OLD
web service receives input in the form of HTTP requests with parameters encoded
(usually) as JavaScript Object Notation (JSON). The application logic
authenticates and authorizes the request and then, depending on the type of
request, queries or updates the database and returns an HTTP response with JSON
in the response body. This is illustrated in the diagram below.

.. image:: _static/OLD_diagram_high_level.png
   :align: center


Core features
--------------------------------------------------------------------------------

#. User authentication and authorization.
#. Multi-user resource creation, retrieval, update and deletion (where a
   "resource" is something like a linguistic form or a syntactic category).
#. Input validation (e.g., ensuring that morpheme segmentation strings do not
   contain characters outside of a specified phonemic inventory and set of
   morpheme delimiters).
#. Application-wide settings, i.e., validation settings, specifications of
   inventories & orthographies, object and meta-language identification, etc.
#. Data processing (e.g., copying and reduction of image and audio files,
   generation of category strings based on the categories of component
   morphemes, phrase-morpheme auto-linking, etc.)
#. Resource search, i.e., open-ended, nested boolean search with substring,
   exact and regular expression matches against specified fields.
#. Linguistic analysis: phonology & corpora specification, automatic
   morphological modeling and morphological parser creation, syntactic parser
   specification & generation.


Technologies
--------------------------------------------------------------------------------

The OLD is written in Python 3 [#f2]_, using the `Pyramid`_ web framework. It
exposes a RESTful JSON API. The relational database management system (RDBMS)
may be MySQL or SQLite. `SQLAlchemy`_ provides a Pythonic interface (ORM) to the
RDBMS.


Who should read this manual?
--------------------------------------------------------------------------------

This document will be of use to anyone wishing to understand the inner workings
of the OLD.

It will be useful, in particular, to system administrators who want to know how
to acquire, configure, install and serve an OLD web service.

It will also be useful to developers who would like to contribute to the code or
create user-facing applications that interact with OLD web services.  Developers
will also benefit from reading the API documentation.

End users who wish to know more about the data structures of the OLD or its
linguistic analysis and language processing components will also find this
manual helpful. Typically, end users of the OLD will interact with OLD instances
through the `Dative`_ interface.


License
--------------------------------------------------------------------------------

The OLD is open source software licensed under
`Apache 2.0 <http://www.apache.org/licenses/LICENSE-2.0.txt>`_.



.. [#f1] Note that this is a break from previous versions of the OLD.  In
   versions 0.1 through 0.2.7, the OLD was a traditional web application, i.e.,
   it served HTML pages as user interface and expected user input as HTML form
   requests.

.. [#f2] The OLD works with Python 3 (3.4, 3.5 and 3.6). It does not run on
   Python 2.

.. _`Pyramid`: https://trypyramid.com/
.. _`SQLAlchemy`: https://www.sqlalchemy.org/
.. _`Dative`: http://www.dative.ca/
