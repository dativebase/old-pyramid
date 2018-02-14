================================================================================
Introduction
================================================================================

An OLD web service consists of a data structure for storing the artifacts of
linguistic fieldwork and analysis and a read-write interface to that data
structure.

A major design principle of the OLD is that as much work as possible
should be delegated to the user-facing applications so that the OLD web service
can focus on providing secure and responsive multi-user concurrent access to
a central data structure.  In some cases, technological restrictions currently
inherent to particular platforms (e.g., the inability of browser-based JavaScript
applications to call external programs) have required server-side implementation
of features that might otherwise be implemented client-side (e.g., morphological
parsing, PDF creation using TeX).

The diagram below illustrates the core components of an OLD application.

.. image:: _static/OLD_diagram_med_level.png
   :align: center

When an OLD web application receives HTTP requests, the Routes component decides
which Pylons controller will handle the request.  This decision is based on the
HTTP method of the request and the URL.  Routes and the controllers conspire to
create a RESTful interface to the data structure *qua* a set of resources.  That
is, a POST request to ``www.xyz-old.org/forms`` will be interpreted as a request
to create a new form resource while the same URL with a GET method will be
interpreted as a request to read (i.e., retrieve) all of the form resources.
The first request will be routed to the ``create`` action (i.e., method) of the
``forms`` controller (i.e., class) while the second will be routed to the
``index`` action of that same controller.  The authentication, authorization,
input validation, data processing, linguistic analysis and database updates and
queries are all handled by the controllers.

As illustrated in the diagram, the Routes and Controllers components can be
conceptually grouped together as the *interface* of an OLD web service.  The
:ref:`interface` section details this interface.

SQLAlchemy provides an abstraction over the tables and relations of the
underlying database.  Tables, their columns and the relations between them
(i.e., the schema) are declared using Python data structures called *models* and
interaction with the database is accomplished entirely via these.  This not only
simplifies interaction with the database (from the Python programmer's point of
view) but also makes it easier to use different RDBMSs (e.g., SQLite, MySQL)
with minimal changes to the application logic.

As illustrated in the diagram, the Models and RDBMS components can be
conceptually grouped together as the *data structure* of an OLD web service.
The :ref:`data-structure` section describes and argues for the utility of the
data structure of the OLD.
