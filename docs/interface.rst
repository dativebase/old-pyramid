:tocdepth: 2

.. _interface:

================================================================================
Interface
================================================================================

This section details the RESTful interface to the OLD data structure as well as
resource search, authentication and authorization, input validation and notable
data processing functionality.  That is, it explains what kind of effect one can
expect from requesting a particular URL (with a particular HTTP method and a
particular JSON payload) of an OLD web service.


.. _restful-api:

RESTful API
--------------------------------------------------------------------------------

The OLD exposes a RESTful interface to its data structure.  In the context of
the OLD, the term *RESTful* [#f1]_ refers to the fact URLs are used consistently
to refer to OLD resources and that HTTP methods dictate the action to be
performed on the resource.  For example, URLs of the form ``/forms`` and
``/forms/id`` are always routed to the forms controller which provides the
interface for the form resources.  If the HTTP method is GET and the URL is
``/forms``, the system will *return* all form resources; the same URL with a
POST method will cause the system to *create* a new form resource (using JSON
data passed in the request body).  The URL ``/forms/id`` with a PUT method will
result in an *update* to the form resource with ``id=id`` while a DELETE method
on the same URL will cause that resource to be *deleted*.

This pattern is detailed in the following table.

+-------------+----------------+--------------------------------------+---------------------------+
| HTTP Method | URL            | Effect                               | Parameters                |
+=============+================+======================================+===========================+
| GET         | /forms         | Read all forms                       | optional GET params       |
+-------------+----------------+--------------------------------------+---------------------------+
| GET         | /forms/id      | Read form with id=id                 |                           |
+-------------+----------------+--------------------------------------+---------------------------+
| GET         | /forms/new     | Get data for creating a new form     | optional GET params       |
+-------------+----------------+--------------------------------------+---------------------------+
| GET         | /forms/id/edit | Get data for editing form with id=id | optional GET params       |
+-------------+----------------+--------------------------------------+---------------------------+
| DELETE      | /forms/id      | Delete form with id=id               |                           |
+-------------+----------------+--------------------------------------+---------------------------+
| POST        | /forms         | Create a new form                    | JSON object               |
+-------------+----------------+--------------------------------------+---------------------------+
| PUT         | /forms/id      | Update form with id=id               | JSON object               |
+-------------+----------------+--------------------------------------+---------------------------+

The benefit of this consistent interface is that, once you know what resources
the OLD exposes, it is clear how to create new ones, retrieve all or one in
particular, update one or delete one.  The resources of the OLD are listed
in the table below.

+--------------------------+-------------+-----------+--------------------+
| Resource (URL)           | SEARCH-able | Read-only | Additional actions |
+==========================+=============+===========+====================+
| applicationsettings      |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| collections              | Yes         |           | Yes                |
+--------------------------+-------------+-----------+--------------------+
| collectionbackups        | Yes         | Yes       |                    |
+--------------------------+-------------+-----------+--------------------+
| elicitationmethods       |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| files                    | Yes         |           | Yes                |
+--------------------------+-------------+-----------+--------------------+
| forms                    | Yes         |           | Yes                |
+--------------------------+-------------+-----------+--------------------+
| formbackups              | Yes         | Yes       |                    |
+--------------------------+-------------+-----------+--------------------+
| formsearchs              | Yes         |           |                    |
+--------------------------+-------------+-----------+--------------------+
| languages                | Yes         | Yes       |                    |
+--------------------------+-------------+-----------+--------------------+
| orthographies            |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| pages                    |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| phonologies              |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| rememberedforms*         | Yes         |           |                    |
+--------------------------+-------------+-----------+--------------------+
| sources                  | Yes         |           |                    |
+--------------------------+-------------+-----------+--------------------+
| speakers                 |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| syntacticcategories      |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| tags                     |             |           |                    |
+--------------------------+-------------+-----------+--------------------+
| users                    |             |           |                    |
+--------------------------+-------------+-----------+--------------------+

As indicated by the "SEARCH-able" column in the above table, some OLD resources
can be searched using a non-standard [#f2]_ SEARCH method with the relevant URL.
The table below uses the files resources to illustrate the search interface.
The details of the search feature (e.g., the format of JSON search parameters)
are laid out in the :ref:`search-old` section.

.. note::

   ``POST /resources/search`` is a synonym for ``SEARCH /resources``; this is to
   allow for search requests from clients that do not allow specification of
   non-standard HTTP methods.

+-------------+-------------------+--------------------------------------+---------------------------+
| HTTP Method | URL               | Effect                               | Parameters                |
+=============+===================+======================================+===========================+
| SEARCH      | /files            | Search files                         | JSON object               |
+-------------+-------------------+--------------------------------------+---------------------------+
| POST        | /files/search     | Search files                         | JSON object               |
+-------------+-------------------+--------------------------------------+---------------------------+
| GET         | /files/new_search | Get data for searching files         |                           |
+-------------+-------------------+--------------------------------------+---------------------------+

Requests to ``GET /resources/new_search`` return a JSON object which summarizes
the data structure of the relevant resource, thus facilitating query
construction.

For the read-only resources (cf. the third column in the resources table), the
only standard requests that are valid are ``GET /resources`` and
``GET /resources/id``.  Since these read-only resources also happen to be
searchable, the search-related requests of the table above are valid for them as
well.

The core OLD resources (i.e., forms, files and collections) deviate from the
RESTful standard in having additional valid URLs associated.  For example, the
forms resource has a ``remember`` action such that ``POST /forms/remember`` will
result in the system associating the forms referenced in the request body to
the user making the request (i.e., the user remembers those forms).  Similarly,
the files resource has a ``serve`` action such that ``GET /files/serve/id`` will
return the file data for the file with ``id=id``.  These additional actions are
described in the subsections for the relevant resources/controllers below.

Aside from those described above, the only additional valid URL/method
combinations of an OLD web service have to do with authentication and the
``login`` controller.  These are detailed in the :ref:`auth` section.

All other requests to an OLD web service will result in a response with a
sensible HTTP error code and a JSON message in the response body that gives
further information on the error.


.. _get-resources:

GET /resources
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``GET /resources``, e.g., ``GET /forms``, return all
resources of the type specified in the URL.  These requests are routed to the
``index`` action of the controller for the resource.

The order of the returned resources may be specified via "orderBy"-prefixed
parameters in the URL query string.  For example, a request such as
``GET /forms?orderByModel=Form&orderByAttribute=id&orderByDirection=desc`` will
return all form resources sorted by id in descending order.  These ordering
parameters are processed in exactly the same way as those passed as an array
during resource search requests (see :ref:`search-orderby`).

It is also possible to request that the resources returned be paginated.  This
is accomplished by passing "page" and "itemsPerPage" parameters in the URL query
string.  For example, ``GET /files?page=3&itemsPerPage=50`` will return a JSON
representation of files 101 through 150.  Of course, ordering and pagination
parameters may both be supplied in a single request.


``GET /resources/id``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``GET /resources/id``, e.g., ``GET /collections/43``,
return a JSON object representation of the resource with the specified id.
These requests are routed to the ``show`` action of the controller for the
resource.

.. _resources-new:

``GET /resources/new``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``GET /resources/new``, e.g., ``GET /forms/new``, return a
JSON object containing all of the data necessary to create new resources of the
specified type.  These requests are routed to the ``new`` action of the
controller for the relevant resource.  For example, when creating a new form
resource, it is helpful to know the set of valid grammaticality values,
elicitation method names, users, sources, etc. of the system.  Therefore, a
request to ``GET /forms/new`` will return a JSON object of the form listed
below, where the values of the attributes are arrays containing the relevant
data.

.. code-block:: javascript

    {
        "grammaticalities": [ ... ],
        "elicitationMethods": [ ... ],
        "tags": [ ... ],
        "syntacticCategories": [ ... ],
        "speakers": [ ... ],
        "users": [ ... ],
        "sources": [ ... ]
    }

This is really just a convenience that saves the trouble of making multiple
requests (e.g., to ``GET /tags``, ``GET /sources``, etc.)

Parameters in the query string can be used to alter the content of the response
so that only certain datasets are returned.  If the URL query string is
not empty, then only the attributes of the response object that have non-empty
parameters in the query string will be returned.  For example, the request
``GET /forms/new?sources=y&tags=y`` will result in a response object of the same
form as above except that only the ``sources`` and ``tags`` attributes will have
non-empty arrays for values.

If the value of a parameter in the URL query string is a valid
`ISO 8601 <http://en.wikipedia.org/wiki/ISO_8601>`_ datetime string of the form
``YYYY-MM-DDTHH:MM:SS``, then the value of the corresponding attribute in the
response object will be non-empty only so long as the input datetime does *not*
match the most recent ``datetimeModified`` value of the specified resources.
This permits the requesting of only novel data.  For example the request
``GET /forms/new?sources=2013-02-22T23:28:43`` will return nothing but source
resources and even these only if there are such that have been updated or
created more recently than 2013-02-22T23:28:43.

Some resources have very simple data structures (e.g., tags) and, therefore,
requests of the form ``GET /resources/new`` on such resources will return an
empty JSON object.


``GET /resources/id/edit``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``GET /resources/id/edit`` return the resource with the
specified id as well as all data required to update that resource.  These
requests are routed to the ``edit`` action of the relevant controller.  Such
requests can be thought of as a combination of ``GET /resources/id`` and
``GET /resources/new``.  The JSON object in the response body is of the form

.. code-block:: javascript

    {"resourceName": {...}, "data": {...}}

where the value of the ``resourceName`` attribute is the same object as that
returned by ``GET /resources/id`` and the value of the ``data`` attribute is the
same as that returned by ``GET /resources/new``.  Parameters supplied in the
URL query string have the same effect as those supplied to
``GET /resources/new`` requests (cf. :ref:`resources-new`).


``DELETE /resources/id``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``DELETE /resources/id`` result in the resource with the
specified id being deleted from the database.  Such requests are routed to the
``delete`` action of the relevant controller.  The form and collection resources
are special in that they are first saved to a backup table before being deleted;
thus these types of resources can be restored after deletion.  The response
body of a successful deletion request is a JSON object representation of the
content of the resource.  As mentioned above, only administrators and their
enterers may delete form, file and collection resources.


``POST /resources``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``POST /resources`` result in the creation of a resource of
the specified type using the data supplied as a JSON object in the request body.
These requests are routed to the ``create`` action of the relevant controller.
The input data are first validated (as detailed in :ref:`validation`).  If
successful, a JSON object representation of the newly created resource is
returned.

.. note::

   All resources receive, upon successful POST and PUT requests, a value for a
   ``datetimeModified`` attribute which is a Coordinated Universal Time (UTC)
   timestamp.  For creation requests on form, file and collection resources, the
   user who made the request is recorded in the ``enterer`` attribute of the
   resource.


``PUT /resources/id``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Requests of the form ``PUT /resources/id`` result in the updating of the
resource of the specified type with the specified id.  The data used to update
the resource are supplied as a JSON object in the request body.  These requests
are routed to the ``update`` action of the relevant controller.  As with the
POST requests described above, the input data are validated before the update
can occur.  If successful, a JSON object representation of the newly updated
resource is returned.  Upon successful update, the previous versions of form and
collection resources are saved to special backup tables of the database (i.e.,
``formbackup`` and ``collectionbackup``.)


JSON
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As a general rule, the OLD communicates via `JSON <http://www.json.org/>`_.
JSON is a widely-used standard for converting certain data types and (nested)
data structures to and from strings.  Strings, numbers, arrays (lists) and
associative arrays (dictionaries) can all be serialized to a JSON string.  For
example, a Python dictionary, i.e., a set of key/value pairs such as
``{'transcription': 'dog', 'translations': [{'transcription': 'chien'}]}`` when
converted to JSON would be
``'{"transcription": "dog", "translations": [{"transcription": "chien"}]}'``.
In most cases, when an OLD web service requires user input, that input is
expected to be JSON in the request body [#f3]_.


.. _search-old:

Search
--------------------------------------------------------------------------------

The OLD provides a powerful search interface to a subset of its resources:
collections, collectionbackups, files, forms, formbackups, formsearches,
languages, rememberedforms and sources.  This interface allows for an unlimited
number of filter expressions conjoined via boolean operators into a hierarchical
structure of unbounded depth where each filter expression references a resource
attribute, a relation and a pattern.

In terms of implementation, search expressions are JSON objects that are mapped
to SQLAlchemy query objects which produce SQL queries.  In relational
database-speak, the OLD search interface permits multi-table queries while
taking care of the joins and subqueries automatically.  The ``SQLAQueryBuilder``
class in ``lib/SQLAQueryBuilder.py`` handles the conversion from JSON search
expression objects [#f7]_ to SQLAlchemy query objects.

Valid search requests (e.g., ``SEARCH /forms``) must contain in the request body
a JSON object representing the query.  The query object has a 'query' attribute
whose value is another object which has a mandatory 'filter' attribute and an
optional 'orderBy' attribute.  The values of ``request.body.query.filter`` and
``request.body.query.orderBy`` are both arrays, the former representing the
hierarchy of filter expressions conjoined by boolean operators and the latter
representing a simple SQL ``ORDER BY`` clause::

    {
        "query": {
            "filter": [ ... ],
            "orderBy": [ ... ]
        }
    }

Filter expression syntax
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

OLD query filters are sets of simple filter expressions configured into a
hierarchical structure using negation, conjunction and disjunction.  Their
syntax is simple and can be described via the following context-free grammar.

.. productionlist::
   filterExpression: `simpleFilterExpression` | `complexFilterExpression`
   simpleFilterExpression: "[" `modelName` "," `attributeName` "," `relationName` "," `pattern` "]" |
                         : "[" `modelName` "," `attributeName` "," `attributeModelAttributeName` "," `relationName` "," `pattern` "]"
   complexFilterExpression: "[", "not" "," `filterExpression` "]" |
                          : "[", "and" "," "[" `filterExpression` ("," `filterExpression`)* "]" |
                          : "[", "or" "," "[" `filterExpression` ("," `filterExpression`)* "]"

That is, a ``filterExpression`` is either (1) a ``simpleFilterExpression`` or
(2) an array whose first element is the string "not" and whose second element is
another ``filterExpression`` or (3) an array whose first element is one of the
strings "and" or "or" and whose second element is an array of one or more
filter expressions.

Simple filter expressions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In plain English, a simple filter expression is something like "the
transcription contains the character 'a'".  A ``simpleFilterExpression`` is an
array with four or five elements.  If four, then the first is the name of an OLD
model, the second the name of a valid attribute of that model, the third a
relation and the fourth a pattern or value.  Consider the simple filter
expression below (where the forms resources are being searched, i.e.,
``SEARCH /forms``).

.. code-block:: javascript

   ["Form", "transcription", "like", "%a%"]

This expression is mapped to the SQLAlchemy ``query`` object::

   query(model.Form).filter(model.Form.transcription.like(u'%a%'))

which generates the SQL that follows.

.. code-block:: sql

   SELECT * FROM form WHERE transcription LIKE '%a%';

A request to ``SEARCH /forms`` with this ``simpleFilterExpression`` in the
request body would return all form resources whose transcription attribute
contains the character "a".

When a simple filter expression has five elements, the second is assumed to be
the name of a relational attribute, i.e., an attribute that references another
model, while the third is an attribute of the referenced model.  For example,
the ``Form`` model has an ``enterer`` attribute whose value is a ``User`` model
and a ``User`` model has a ``firstName`` attribute.  Therefore, to find all form
resources with enterers whose first name begins with "J" or "S", we construct
the simple filter expression

.. code-block:: javascript

   ["Form", "enterer", "firstName", "regex", "^[JS]"]

which maps to the SQLAlchemy query object::

   query(model.Form).filter(model.Form.enterer.has(User.firstName.op('regexp')(u'^[JS]')))

The two following simple filter expressions return all forms lacking enterers
and all forms having them, respectively.

.. code-block:: javascript

   ["Form", "enterer", "=", null]
   ["Form", "enterer", "!=", null]

Some relational attributes of OLD models reference *collections*, i.e., lists
of zero or more models of a given type.  For example, OLD forms can be
associated to one or more files, i.e., the ``Form`` model has a ``files``
attribute whose value is a collection of ``File`` objects.  Since ``File``
objects have ``id`` attributes, we can use the filter expression below to
retrieve all forms associated to files with one of the following ids: 1, 2, 33,
5.

.. code-block:: javascript

   ["Form", "files", "id", "in", [1, 2, 33, 5]]

The four-element filter expression below returns the same result set as the
five-element one one above.  This is because the OLD knows that the ``Form``
model is being queried and that the only relation between the ``Form`` and
``File`` models is captured by the ``files`` attribute of the ``Form`` model.
[#f5]_

.. code-block:: javascript

    ["File", "id", "in", [1, 2, 33, 5]]

The two following simple filter expressions return all forms lacking files
and all forms having one or more, respectively.

.. code-block:: javascript

   ["Form", "files", "=", null]
   ["Form", "files", "!=", null]


Complex filter expressions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Complex filter expressions are built from simple filter expressions using "not",
"and" and "or".

The following complex filter expression uses "not" to return all form resources
that do not have "a" in their transcriptions.

.. code-block:: javascript

   ["not", ["Form", "transcription", "like", "%a%"]]

Conjoined and disjoined filter expressions are exemplified below.

.. code-block:: javascript

   ['and', [['Form', 'transcription', 'like', '%a%'],
            ['Form', 'elicitor', 'id', '=', 13]]]
   ['or', [['Form', 'transcription', 'like', '%a%'],
           ['Form', 'dateElicited', '<', '2012-01-01']]]

Finally, an example of a complex filter expression involving multiple levels
of embedding.

.. code-block:: javascript

   ['and', [['Translation', 'transcription', 'like', '%1%'],
            ['not', ['Form', 'morphemeBreak', 'regex', '[28][5-7]']],
            ['or', [['Form', 'datetimeModified', '<', '2012-03-01T00:00:00'],
                    ['Form', 'datetimeModified', '>', '2012-01-01T00:00:00']]]]]


Filter relations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

OLD search requests permit the relations listed below.  

* equality ("=" or "__eq__")
* inequality ("!=" or "__ne__")
* like ("like" [#f6]_)
* regular expression ("regex" or "regexp")
* less than ("<" or "__lt__")
* less than or equal to ("<=" or "__le__")
* greater than (">" or "__gt__")
* greater than or equal to (">=" or "__ge__")
* one of ("in" or "in\_")

.. note::

   Some relations can be referenced by more than one name as indicated in the
   brackets.

Most of these relations should be self-explanatory.  However, the *like* and
*regular expression* relations merit further discussion.


The *like* relation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The "like" relation is simply the SQL ``LIKE`` operator.  The pattern following
the "like" relation may contain the wildcard characters "%" and "_".  The
percent sign matches zero or more of any character while the underscore matches
exactly one instance of any character.  These wildcards are illustrated via
some typical use cases below.

Find all forms whose transcription contains "t":

.. code-block:: javascript

   ["Form", "transcription", "like", "%t%"]

Find all forms whose transcription begins with "T":

.. code-block:: javascript

   ["Form", "transcription", "like", "T%"]

Find all forms whose transcription ends with "t":

.. code-block:: javascript

   ["Form", "transcription", "like", "%t"]

Find all forms that contain "k", followed by any single character, followed by
"t":

.. code-block:: javascript

   ["Form", "transcription", "like", "%k_t%"]

.. note::

   As indicated by the above examples, OLD filter expressions are
   case-sensitive.


The *regexp* relation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The "regexp" (a.k.a. "regex") relation implements regular expression matching.
[#f8]_  Regular expressions are tools for specifying complex patterns on
strings.  As with the "like" relation described above, certain characters and
constructions in "regexp" search patterns have special meanings.

By default, regular expressions perform a substring match.  That is, an OLD
filter expression like the one that follows will return all forms that contain
the string "it" anywhere in the value of their transcription attribute.

.. code-block:: javascript

   ["Form", "transcription", "regex", "it"]

We can refer to the beginning or end of the string using the anchors "^" and
"$".  For example, the following two filter expressions find all forms whose
transcription begins with "T" or ends with "s", respectively.

.. code-block:: javascript

   ["Form", "transcription", "regex", "^T"]
   ["Form", "transcription", "regex", "s$"]

The period "." matches any character.  For example, the OLD filter expression
below will match all forms that have "kat", "kit", "kst", "kqt", etc. in their
transcription values.

.. code-block:: javascript

   ["Form", "transcription", "regex", "k.t"]

It is also possible to specify a pattern that matches a limited set of
characters using character classes, i.e., sequences of characters enclosed in
square brackets.  For example, the following OLD filter expression will match
all forms whose transcription value contains "k", followed by a vowel, followed
by "t".  (Of course, unicode characters are permitted as well so accented and
IPA vowels could be specified here also.)

.. code-block:: javascript

   ["Form", "transcription", "regex", "k[aeiou]t"]

If the caret character "^" is the first character in the character class, then
the class matches any character except those it contains.  For example, the
following OLD filter expression will match all forms whose transcriptions
contain a "k", followed by *anything but* a "q" or another "k", followed by a
"t".

.. code-block:: javascript

   ["Form", "transcription", "regex", "k[^qk]t"]

The vertical bar "\|" is the alternation metacharacter.  It matches either the
string to its left or the string to its right.  For example, the following OLD
filter expression will return all forms containing a translation that contains
either "the cat ran" or "the dog ran".

.. code-block:: javascript

   ["Form", "translations", "transcription", "the (cat|dog) ran"]

Regular expressions also support quantification.  That is, it is possible to
specify that a pattern zero or one times (using "?"), zero or more times (using
"\*"), one or more times (using "+"), exactly *n* times (using "{n}"), between
*n* and *m* times (using "{n,m}") and *n* or more times (using "{n,}").

For example, to find all forms whose transcription is a single word with one
syllable whose nucleus is transcribed using exactly two vowels, an OLD filter
expression like the following might be appropriate.

.. code-block:: javascript

   ["Form", "transcription", "regex", "^[ptkmns][aeiou]{2}[ptkmns]$"]

Quantifiers could also be used to filter resources by the length of one of their
fields.  For example, to find all forms whose transcriptions contain at least
five but no more than ten characters, one could use the following OLD filter
expression.

.. code-block:: javascript

   ["Form", "transcription", "regex", "^.{5,10}$"]

.. note::

   Regular expressions will treat unicode combining characters as separate
   characters.  Since the OLD applies unicode canonical decomposition
   normalization [#f9]_ on all input, a string like "á" will be interpreted by
   the regular expression parser as containing two strings, the "a" and the
   COMBINING ACCUTE ACCENT (u+0301) character.  Keep this in mind when using
   regular expression quantifiers to filter based on string length or when using
   character sets.  In the latter case, it is usually safer to use parentheses
   and the alternation metacharacter than character sets.  To illustrate,
   consider the two examples below.  The first OLD filter expression will match
   "oao", "oio" and "óo", which is probably not what was intended.  The second
   filter expression will match "oáo" and "oío", which is probably what was
   intended.

   .. code-block:: javascript

      ["Form", "transcription", "regex", "o[áí]o"]
      ["Form", "transcription", "regex", "o(á|í)o"]


.. _search-orderby:

Ordering results
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In making a search request of an OLD web service, it is possible to specify the
order in which the results are returned.  This is accomplished by specifying
an ``orderBy`` attribute for the JSON ``query`` object that is passed as input
in the body of the request.  Remember that OLD search requests must contain an
object of the following form (where the ``orderBy`` attribute is optional).

.. code-block:: javascript

    {"query": {
        "filter": [ ... ] ,
        "orderBy": [ ... ]}}

The value of the ``orderBy`` attribute is an array containing exactly three
strings where the first is the name of a model/resource, the second the name of
an attribute of the model and the third is a direction, i.e., "asc" or "desc".
For example, the following JSON object passed in the body of a request to
``SEARCH /forms`` would return all forms whose transcription begins with "p"
ordered by id in descending order.

.. code-block:: javascript

    {"query": {
        "filter": ["Form", "transcription", "regex", "^p"],
        "orderBy": ["Form", "id", "desc"]}}



Non-standard API
--------------------------------------------------------------------------------

This section describes the valid requests that are not covered by the standard
RESTful and search interfaces documented in the previous sections.  A subset of
OLD resources possess such supplemental interfaces.  This section is organized
by resource.


.. _form-resource:

Forms
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Form resources represent linguistic forms and are the core of an OLD web
service.  The non-standard interfaces of form resources are described here.


``GET /forms/history/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``GET /forms/history/id`` are routed to the ``history`` action of
the ``forms`` controller.  Such requests return a JSON object representing the
history, or previous versions, of the form with the specified id.  The id
parameter can be the integer id or the
`Universally Unique Identifier <http://en.wikipedia.org/wiki/Universally_unique_identifier>`_
(UUID) of the form. [#f10]_  The JSON object returned is of the form

.. code-block:: javascript

    {"form": { ... }, "previousVersions": [ ... ]}

where the value of the "form" attribute is the JSON representation of the form
while the value of "previousVersions" is an array of objects representing the
previous versions of the form.  If the form has been deleted, the value of the
"form" attribute will be ``null`` and if the form has not been updated or
deleted, the value of the "previousVersions" attribute will be an empty array.


``POST /forms/remember``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``POST /forms/remember`` are routed to the ``remember`` action of
the ``forms`` controller and cause the forms referenced in the request body to
be appended to the ``rememberedForms`` collection of the user making the
request.  The expected input is an object of the form

.. code-block:: javascript

    {"forms": [id1, id2, ... ]}

where ``id1``, ``id2``, etc. are form integer ids.


``PUT /forms/update_morpheme_references``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``PUT /forms/update_morpheme_references`` regenerates values for the
``morphemeBreakIDs``, ``morphemeGlossIDs``, ``syntacticCategoryString`` and
``breakGlossCategory`` attributes of *all* forms in the system.  (See the
:ref:`morphological-processing` and :ref:`form-data-structure` sections for
details on these attributes.)  The response generated by this request contains a
JSON array of ids corresponding to the forms that were updated.  Only
administrators are authorized to make this request.

.. warning::

   It should not be necessary to request the regeneration of morpheme references
   via this request since this should already be accomplished automatically by
   the call to ``updateFormsContainingThisFormAsMorpheme`` on all successful
   update and create requests on form resources.  This interface is, therefore,
   deprecated (read: use it with caution) and may be removed in future versions
   of the OLD.


.. _file-resource:

Files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

OLD file resources are representations of binary files stored on a filesystem.
From a linguist's point of view, they are the audio/video records of linguistic
fieldwork, the images (or audio or video) used as stimuli, PDFs of relevant
papers or handouts, etc. -- anything that is relevant to a piece or a collection
of language data.  Multiple file resources can be associated to a given form or
collection resource.  Thus, for example, a form representing a sentence could be
associated to a large audio recording of an elicitation session, a smaller audio
recording of just the sentence being uttered, an image used to illustrate a
context for a speaker, etc.  See the :ref:`file-data-structure` section for more
details on files.


``GET /files/serve/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``GET /files/serve/id`` return the file data of the file resource
with the given id, assuming the authenticated user is authorized to access that
resource.  If the file with the specified id is a subinterval-referencing file,
the file data of the parent file is returned; if the file data are hosted
externally, an explanatory error message is returned.  (See the
:ref:`file-data-structure` for an explanation of subinterval-referencing and
externally hosted files.)

``GET /files/serve_reduced/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``GET /files/serve_reduced/id`` return the file content of the
reduced-size copy of the file which was created by the OLD upon file creation.
If there is no reduced-size copy of the file, the OLD returns an error message.
These requests handle subinterval-referencing and externally hosted files in the
same way as described in the above subsection.


.. _collection-resource:

Collections
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Collections are documents that can reference forms and are useful for creating
records of elicitation sessions or for writing papers using data stored on an
OLD application.  See the :ref:`collection-data-structure` section for more
details on collections.


``GET /collections/history/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``GET /collections/history/id`` are routed to the ``history`` action
of the ``collections`` controller and return a JSON object representing the
history, or previous versions, of the collection with the specified id.  The id
parameter can be the integer id or the
`Universally Unique Identifier <http://en.wikipedia.org/wiki/Universally_unique_identifier>`_
(UUID) of the collection. [#f10]_  The JSON object returned is of the form

.. code-block:: javascript

    {"collection": { ... }, "previousVersions": [ ... ]}

where the value of the "collection" attribute is the JSON representation of the
collection while the value of "previousVersions" is an array of objects
representing the previous versions of the collection.  If the collection has
been deleted, the value of the ``collection`` attribute will be ``null`` and if
the collection has not been updated or deleted, the value of the
``previousVersions`` attribute will be an empty array.



.. _application-settings-resource:

Application settings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The application-wide settings for an OLD application are stored as application
settings objects.  These resources have non-standard interfaces insofar as only
administrators are permitted to create, update or delete them.  Other types of
users can only read them, i.e., request ``GET /applicationsettings`` and
``GET /applicationsettings/id``.  The application settings resources are also
unique in that the most recently created one (i.e., that with the largest id) is
designated as the *active* application settings and is the one that affects the
behaviour of the rest of the application.  Therefore, application-wide behaviour
may be configured either by updating the active application settings resource or
by creating a new (and hence active) one.  The latter approach is recommended
since the previously created application settings resources will provide a
history of previous configurations.


Users
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

User resources represent the users (i.e., administrators, contributors and
viewers) of an OLD application.  The interface to this resource is non-standard
in that only administrators are authorized to create or delete user resources
and a user resource can only be updated by administrators and the holder of the
user account.  See the :ref:`user-data-structure` section for more details on
users.


.. _remembered-forms-interface:

Remembered forms
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each OLD user has a ``rememberedForms`` attribute whose value is a collection of
zero or more form resources that the user has memorized.  Since these
collections can grow quite large, they are treated as a resources of their own
and are not affected by interactions with user resources.  The interface to the
remembered forms resources are non-standard in that ...


``GET /rememberedforms/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``GET /rememberedforms/id`` return the array of forms remembered by
the user with the supplied id.  Such requests are routed to the ``show`` action
of the ``rememberedforms`` controller.  Ordering and pagination parameters may
be provided in the query string of this request in exactly the same way as with
standard ``GET /resources`` requests of conventional resources (cf.
:ref:`get-resources`).


``UPDATE /rememberedforms/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``UPDATE /rememberedforms/id`` are routed to the ``update`` action
and set the remembered forms of the user with the supplied id to the set of
forms referenced in the JSON array of form ids sent in the request body. This
type of request accomplishes creation, updating and deletion of a
remembered form "resource".  Only administrators and the user with the supplied
id can make licit requests to ``UPDATE /rememberedforms/id``.  As with requests
to ``POST /forms/remember``, requests to ``UPDATE /rememberedforms/id`` should
contain a JSON request body of the form ``{"forms": [16, 28, 385]}``.

.. note::

   The ``remember`` action of the forms controller has a similar, but more
   restricted, effect, i.e., requests to ``POST /forms/remember`` can add forms
   to (but not delete them from) the remembered forms collection of the user who
   makes the request.

``SEARCH /rememberedforms/id``
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Requests to ``SEARCH /rememberedforms/id`` return all form resources remembered
by the user with the supplied id and which match the JSON search filter passed
in the request body.  These requests are routed to the ``search`` action.
Requests to ``POST /rememberedforms/id/search`` have the same effect as those to
``SEARCH /rememberedforms/id``.

.. note::

   The same effect can be achieved by conjoining the filter expression
   ``["Memorizer", "id", "=", id]`` to an existing search on form resources,
   i.e., a request to ``SEARCH /forms``.


.. _auth:

Authentication & authorization
--------------------------------------------------------------------------------

Speakers of endangered languages and their communities often require that the
language data gathered by researchers not be made available to the public at
large.  Therefore, authentication (i.e., a username and password) is required in
order to access data on an OLD web service [#f4]_.

In addition to authentication, the OLD possesses a role-based system of
authorization.  The three roles are *administrator*, *contributor* and *viewer*.

Viewers are only able to perform read requests, e.g., view all form resources,
retrieve a particular file resource, search the collections resources, etc.

Contributors have read and write access to most resources, with some
restrictions.  Contributor *U1* is not permitted to delete a form, file or
collection entered by contributor *U2*.  Only administrators and *U1* can delete
a form, file or collection entered by *U1*.  In addition, only administrators
and user *U1* are permitted to update the user resource representing *U1*.

Administrators have unrestricted access to read and write any resource.  Only
administrators can create or delete users and only administrators have write
access to application settings resources.

Separate from the role-based division of users is a classification into
restricted and unrestricted users.  While administrators are, by default, always
unrestricted, the application settings can specify a subset of contributors and
viewers as unrestricted.  Only unrestricted users are permitted to access
restricted objects, i.e., forms, files or collections tagged with the
"restricted" tag.  Users not classified as unrestricted (i.e., restricted users)
are unable to access restricted objects in any way.  Since core objects can be
associated to one another (e.g., a form can be associated to multiple files),
restricted status can spread from object to object.  For example, an
unrestricted form becomes restricted as soon as it is associated to a restricted
file.

The ``login`` controller effects authentication.  Its interface is detailed in
the following table.

+-------------+-----------------------------+--------------------------------------+---------------------------+
| HTTP Method | URL                         | Effect                               | Parameters                |
+=============+=============================+======================================+===========================+
| POST        | /login/authenticate         | Attempt to authenticate              | JSON object               |
+-------------+-----------------------------+--------------------------------------+---------------------------+
| GET         | /login/logout               | De-authenticate                      |                           |
+-------------+-----------------------------+--------------------------------------+---------------------------+
| POST        | /login/email_reset_password | Email a newly generated password to  | JSON object               |
|             |                             | the user                             |                           |
+-------------+-----------------------------+--------------------------------------+---------------------------+

``POST /login/authenticate`` attempts authentication using the provided input,
i.e., a JSON object on the request body of the form
``{"username": " ... ", "password": " ... "}``.  If successful, authenticated
status is persisted across requests via a cookie-based ``session`` object where
the value of ``session['user']`` is the user model of the authenticated user.

A ``GET /login/logout`` request removes the ``'user'`` key from the ``session``
object associated with the cookie passed in the request.  That is, it
de-authenticates, or logs out, the user.

A ``POST /login/email_reset_password`` request with a JSON object in the request
body of the form ``{"username": " ... "}`` attempts to create a new, randomly
generated password for the user with the provided username and notify the user
via email of the change.  If the server is unable to send email, the password
will not be reset and a JSON error message will be returned in the response.

.. note::

   If an SMTP mail server cannot be used, it is possible (as detailed in the
   comments of the config file that is generated when ``paster make-config`` is
   run) to configure an OLD application to send email via a specified Gmail
   account.

For more details on the authentication and authorization scheme of the OLD,
please consult the API documentation and/or the source code.  Most relevant are
the ``lib/auth.py``, ``controllers/login.py``, ``controllers/forms.py``,
``controllers/files.py`` and ``controllers/oldcollections.py`` modules.


.. _validation:

Input validation
--------------------------------------------------------------------------------

When users attempt to create a new resource or update an existing one, the OLD
attempts to validate the input.  If validation fails, the status code of the
response is set to 400 and a JSON object explaining the issue(s) is returned,
i.e., an object of the form
``{'error': 'error message'}`` or
``{'errors': {'field name 1': 'error message 1', 'field name 2': 'error message 2'}}``.


Standard validation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Standard validation is validation on user input that is applied by all OLD
applications in the same way.

Some representative examples will illustrate.  All forms require some string in
their transcription field and at least one translation.  References to other OLD
resources via their ids are validated for existence; e.g., when an elicitor for
a form is specified via a user id, then validation ensures that the id
corresponds to a user in the database.  User-supplied values for date fields
must be in ``mm/dd/yyyy`` format.  Emails must be correctly formatted.  Files
uploaded must be one of the allowed file types (e.g., .jpg, .wav) of the OLD.

The Pylons controller classes that control the creation and updating of
resources ensure that all such validation is passed before these requests can
succeed.  The validators that encode these validations are written using the
`FormEncode <http://www.formencode.org>`_ library and can be found in the
``lib/schemata.py`` module of the OLD source.  For further information on input
validation, consult the :ref:`data-structure` section, the API documentation
and/or the source code.


.. _object-language-validation:

Object language validation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In addition to the standard validation described above, particular OLD
applications can control how, or whether, transcriptions of the object language
are validated.  The relevant form attributes are ``transcription``,
``phoneticTranscription``, ``narrowPhoneticTranscription`` and
``morphemeBreak``.  By configuring the OLD application's settings, adminstrators
can control what types of strings are permitted in these fields.  This is useful
for when groups of researchers want to ensure that, say, all morpheme
segmentation strings (i.e., ``morphemeBreak`` values) are restricted to
sequences of phonemes from the specified inventory plus the specified morpheme
delimiters.

The table below shows how object language transcription validation is
configured.

+-----------------------------+-----------------------------------+--------------------------+
| Form attribute              | Relevant inventory or orthography | Validation parameter     |
+=============================+===================================+==========================+
| transcription               | storageOrthography                | orthographicValidation   |
+-----------------------------+-----------------------------------+--------------------------+
| phoneticTranscription       | broadPhoneticInventory            | broadPhoneticValidation  |
+-----------------------------+-----------------------------------+--------------------------+
| narrowPhoneticTranscription | narrowPhoneticInventory           | narrowPhoneticValidation |
+-----------------------------+-----------------------------------+--------------------------+
| morphemeBreak               | phonemicInventory*                | morphemeBreakValidation  |
+-----------------------------+-----------------------------------+--------------------------+

The validation parameter column lists the attributes of the application settings
resource that control whether the form attribute in the first column should be
validated against the relevant inventory or orthography.  Each of the attributes
in the validation parameter column can have one of three possible values:
``None``, ``Warning`` or ``Error``.  Only if the attribute is set to ``Error``
will inventory/orthography-based validation occur.

For example, if the current application settings resource has
``orthographicValidation`` set to ``Error``, then input validation will ensure
that form transcriptions contain only graphemes (i.e., characters or character
sequences) from the storage orthography plus punctuation characters and the
space character.

When validation is enabled on the phonetic transcription fields, only graphs
from the specified inventory plus the space character are permitted (i.e., no
punctuation).

The ``morphemeBreak`` attribute's validation settings are slightly more complex
since it is possible to choose between the storage orthography or the phonemic
inventory when configuring validation.  This is done by setting the
``morphemeBreakIsOrthographic`` attribute of the application settings resource
to ``true`` in the former case and ``false`` in the latter.  For example,
if ``morphemeBreakIsOrthographic`` is set to ``false`` and
``morphemeBreakValidation`` is set to ``Error``, then input to the
``morphemeBreak`` field will be rejected if it contains characters outside of
the specified phonemic inventory, the specified morpheme delimiters and the
space character.

As implied in the above discussion, the application settings resource has
``morphemeDelimiters`` and ``punctuation`` attributes for specifying sets of
valid morpheme delimiters and punctuation, respectively.

Sometimes it is desirable to include foreign words in the object language
transcriptions while still permitting validation against inventories and
orthographies on these fields.  For example, in a system where ``morphemeBreak``
validation is enabled and the phonemic inventory is /p/, /t/, /k/, /i/, /a/,
/u/, it might be desirable to allow a ``morphemeBreak`` value of "ki dog katti"
but prohibit "ki dog kotti".  The OLD permits this via the special "foreign
word" tag on form resources.  When a form is tagged as a foreign word, its
transcription values affect validation.  So, if the system were to contain a
foreign word form with "dog" as its ``morphemeBreak`` value, then validation
would correctly allow both instances of "dog" in the above two examples while
disallowing the latter example because of the illicit "o" in "kotti".  The
function ``updateApplicationSettingsIfFormIsForeignWord`` is called in the
``forms`` controller upon successful create and update requests and is
responsible for updating the validators with the foreign word information.


Processing
--------------------------------------------------------------------------------

When requests cause resources to be created or updated, the OLD may perform some
additional processing that may affect the values of certain attributes of the
target resource or even of other resources.  The notable data processing
functionalities are listed below and are detailed in their own subsections.

* the generation of values for form attributes related to morphological analysis
* the updating of transcription validators when foreign words are entered
* the resolution and cacheing of collection-collection and collection-form cross-references
* the creation of reduced-size copies of the binary files of file resources



.. _morphological-processing:

Morphological processing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Values for four attributes of form resources related to morphological analysis
are generated on create and update requests.  These are the ``morphemeBreakIDs``,
``morphemeGlossIDs``, ``syntacticCategoryString`` and ``breakGlossCategory``
attributes.  The function ``compileMorphemicAnalysis`` in the ``forms``
controller is responsible for generating these values.

The values of the ``morphemeBreakIDs`` and ``morphemeGlossIDs`` attributes are
arrays that hold references to other forms that match the morphemes indicated in
the user-defined ``morphemeBreak`` and ``morphemeGloss`` attributes.  Each array
has one array per word in the relevant field, each word array has one array per
morpheme and each morpheme array has one array per match found.  Matches are
ordered triples where the first element is the id of the match, the second is
the ``morphemeBreak`` or ``morphemeGloss`` value of the match and the third is
the ``syntacticCategory.name`` of the match or ``null`` if no category is
specified.  As illustration, consider a database containing the following forms.

+----+--------------------+-----------------------+-----------------------+------------------------+
| id | transcription      | morphemeBreak         | morphemeGloss         | syntacticCategory.name |
+====+====================+=======================+=======================+========================+
| 1  | chien              | chien                 | dog                   | N                      |
+----+--------------------+-----------------------+-----------------------+------------------------+
| 2  | s                  | s                     | PL                    | Agr                    |
+----+--------------------+-----------------------+-----------------------+------------------------+
| 3  | s                  | s                     | PL                    | Num                    |
+----+--------------------+-----------------------+-----------------------+------------------------+
| 4  | le                 | le                    | the                   | D                      |
+----+--------------------+-----------------------+-----------------------+------------------------+
| 5  | cour               | cour                  | run                   | V                      |
+----+--------------------+-----------------------+-----------------------+------------------------+
| 6  | ent                | ent                   | 3.PL                  | Agr                    |
+----+--------------------+-----------------------+-----------------------+------------------------+
| 7  | les chiens courent | le-s chien-s cour-ent | the-PL dog-PL run-3PL | S                      |
+----+--------------------+-----------------------+-----------------------+------------------------+

When the form with id 7 is entered, the system will generate the following
arrays for the ``morphemeBreakIDs`` and ``morphemeGlossIDs`` attributes. ::

    morphemeBreakIDs = [
        [
            [[4, 'the', 'D']],
            [[2, 'PL', 'Agr'], [3, 'PL', 'Num']]
        ],
        [
            [[1, 'dog', 'N']],
            [[2, 'PL', 'Agr'], [3, 'PL', 'Num']]
        ],
        [
            [[5, 'run', 'V']],
            [[6, '3.PL', 'Agr']]
        ]
    ]
    morphemeGlossIDs = [
        [
            [[4, 'le', 'D']],
            [[2, 's', 'Agr'], [3, 's', 'Num']]
        ],
        [
            [[1, 'chien', 'N']],
            [[2, 's', 'Agr'], [3, 's', 'Num']]
        ],
        [
            [[5, 'cour', 'V']],
            []
        ]
    ]

.. note::

   The ``morphemeBreakIDs[0][1]`` value contains two match triples because the
   second morpheme of the first word in the ``morphemeBreak`` line, i.e., "s",
   matches two forms, i.e., the forms with ids 2 and 3.  Similarly,
   ``morphemeGlossIDs[0][1]`` contains two analogous match triples, the
   difference in this case being that the morpheme's phonemic/orthographic
   representation is listed and not its gloss.  In contrast, the morpheme break
   "ent" matches form 6, hence the single match triple in
   ``morphemeBreakIDs[2][1]``, whereas "3PL" matches nothing, hence the absence
   of matches in ``morphemeGlossIDs[2][1]``.

The purpose of the ``morphemeBreakIDs`` and ``morphemeGlossIDs`` attributes is
that they record the extent to which the morphemic analysis of a given form is
in accordance with the lexical items listed in the database.  If these values
were not generated server-side upon create and update requests, then for any 
user-facing application to display such information would require many requests
and database queries each time a form were displayed.  The information in these
two attributes is quite valuable in that it can be used to immediately inform
users when the lexical items implicit in their morphological analyses are not
yet listed in the database or when small differences in, say, glossing
conventions are masking underlying consensus in analysis.

At the same time as the ``morphemeBreakIDs`` and ``morphemeGlossIDs`` values are
generated, so too are the values for the ``syntacticCategoryString`` and
``breakGlossCategory`` attributes.  These values for our example form 7 from
above would be::

    syntacticCategoryString = 'D-Agr N-Agr V-Agr'
    breakGlossCategory = 'le|the|D-s|PL|Agr chien|dog|N-s|PL|Agr cour|run|V-ent|3PL|Agr'

The value of the ``syntacticCategoryString`` attribute is a string of syntactic
category names corresponding to the string of morphemes in the morphemic
segmentation.[#f11]_ Since the syntactic category string can be used to filter
form resources on search requests, its generation facilitates search based on
high-level morphological patterns.  For example, using the syntactic category
string, one could use regular expressions to search for all forms consisting of
an NP followed by a VP.

.. note::

   Given our example dataset, ``'D-Num N-Num V-Agr'`` is a reasonable
   (and perhaps preferable) syntactic category string value.  However, the
   system has no way of knowing this and therefore when there are two matches
   for a morpheme (as there are for "s") it arbitrarily chooses the syntactic
   category of the lexical form with the lowest id.

The value of ``breakGlossCategory`` is a string that unambiguously represents
the morphemic analysis of the form.  Each morpheme is taken to be a triplet
consisting of a phonemic representation (i.e., the ``morphemeBreak`` value), a
semantic representation (i.e., the ``morphemeGloss`` value) and a categorial
value (i.e., the ``syntacticCategory.name`` value).  These break-gloss-category
triplets are delimited by the vertical bar "\|" and each such triplet is joined
using the morpheme delimiters of the ``morphemeBreak`` value.

This attribute makes it possible to search for forms that contain a specific
morpheme.  Consider the case where one wanted to find all forms containing the
morpheme "s" glossed as "PL" of category "Num".  Performing a regular expression
search on the ``morphemeBreak`` line for the pattern :regexp:`-s( |-|$)` (i.e., "-s"
followed by a space, "-" or the end of the string) would be insufficient since
it might also find forms containing an "s" morpheme with a different gloss.
Conjoining the above regular expression filter with another on the
``morphemeGloss`` line with the pattern ``-PL( |-|$)`` would still be
insufficient since it would (contra what is desired) match a form with a
``morphemeBreak`` value of "le-s oiseau-x" and a ``morphemeGloss`` value of
"the-plrl bird-PL".  By searching the forms according to those whose
``breakGlossCategory`` value matches the regular expression
``-s\|PL\|Num( |-|$)``, one can be assured of finding all and only all the forms
containing the morpheme "s"/"PL"/"Num"

Given the above discussion, it is evident that an update to an existing
lexical form, the creation of a new one or the updating of the name of a
syntactic category may require updating the ``morphemeBreakIDs``,
``morphemeGlossIDs``, ``syntacticCategoryString`` and/or ``breakGlossCategory``
values of a number of different forms.  The OLD accomplishes this by calling
``updateFormsContainingThisFormAsMorpheme`` whenever a form is created or
updated.  This function first assesses whether the newly created/updated form is
lexical and, if so, it selects all forms whose morphological analyses implicitly
reference the lexical form and updates the relevant fields appropriately.  Care
is taken to reduce database select queries to an absolute minimum with the end
result being that the majority of calls to
``updateFormsContainingThisFormAsMorpheme`` will require only one select query,
i.e., the one to find all of the forms that reference the lexical item just
created/updated.  In addition, when the name of a (lexical) syntactic category
is changed, ``updateFormsContainingThisFormAsMorpheme`` is called on each form 
that has that category.


Foreign words
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Whenever a form is created, updated or deleted, the forms controller calls
``updateApplicationSettingsIfFormIsForeignWord``.  This function is responsible
for updating the transcription validators of the application settings if the
form is a foreign word.  As described in :ref:`object-language-validation`,
forms tagged with the "foreign word" tag will create exceptions to the
user-defined object language transcription validation.  For example, if a form
is entered with ``transcription``, ``morphemeBreak`` and ``morphemeGloss``
values of "John", "John" and "John" and is tagged as a "foreign word", then the
system will allow the string "John" to be included in the ``transcription``
field of other forms even if validation is set to reject forms whose
transcriptions contain, say, "J" or "h".

.. note::

   It is desirable to be able to enter such a lexical entry as "John" with a
   category of, say, "PN" since doing so will result in sensible
   ``syntacticCategoryString`` values for forms containing "John" in their
   ``morphemeBreak`` value.


Collection references
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``contents`` attribute of collections is a string that may contain
references to forms and other collections.  These references determine the value
of the ``contentsUnpacked``, ``html`` and ``forms`` attributes.

When the value of the ``contents`` attribute of an existing collection is
updated, the ``update`` action calls
``updateCollectionsThatReferenceThisCollection`` in order to update the 
``contentsUnpacked``, ``html`` and ``forms`` values of all of the collections
that reference the updated collection.  This same function is called when a
collection is deleted; in this case, all references to the deleted collection
are removed from any collections that were referencing it and the appropriate
values are updated.  Similarly, when a form is deleted, the ``delete`` action
calls ``updateCollectionsReferencingThisForm`` and all references to the
to-be-deleted form are removed from any collections that reference it.

See the :ref:`collection-data-structure` section for more details on collection
references and the attributes whose values depend on them.


Lossy file copies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When new file models are created with locally stored file data, the OLD may
create reduced-size copies of certain file types and store them, by default, in
``files/reduced_files/``.  Such lossy copies are created when
``create_reduced_size_file_copies`` is set to a truthy value (e.g., "1") in the
config file and if the relevant utilities are installed, i.e., for images the
Python Imaging Library and for WAV files the FFmpeg command-line utility.  See
the :ref:`soft-dependecies` and :ref:`file-data-structure` sections for more
details.



.. [#f1] See `this StackOverflow page <http://stackoverflow.com/questions/671118/what-exactly-is-restful-programming>`_
   for a discussion on what exactly REST means and read
   `Fielding's thesis <http://www.ics.uci.edu/~fielding/pubs/dissertation/fielding_dissertation.pdf>`_
   for the source of the term.

.. [#f2] The WebDAV standard includes a `SEARCH <http://www.webdav.org/specs/rfc5323.html>`_
   method so this is not entirely without precedent.

.. [#f3] In contrast to POST, PUT and DELETE requests, HTTP GET requests are
   not, canonically, supposed to possess contentful request bodies; therefore,
   when optional parameters are permissible on such requests, the OLD will
   expect GET parameters in the URL string.

.. [#f4] Future versions of the OLD may make authentication a configurable
   option, thus allowing publicization of all data.  Another possibility is that
   the system could allow users to tag some data as public and that these data
   could be accessed without authentication.  A final possibility would be to
   publicize all data but allow some data to be encrypted such that only
   authenticated users could decrypt them.

.. [#f5] Note that while the results returned will be the same, the SQLAlchemy
   query object constructed and the SQL issued to the database will be distinct.
   That is, the filter expression ``["Form", "files", "id", "in", [1, 2, 33, 5]]``
   maps to the SQLAlchemy query
   ``query(model.Form).filter(model.Form.files.any(model.File.id.in_([1, 2, 33, 5])))``
   while ``["File", "id", "in", [1, 2, 33, 5]]`` maps to
   ``fileAlias = aliased(File)`` and
   ``Session.query(Form).filter(fileAlias.id.in_([1, 2, 33, 5])).outerjoin(fileAlias, Form.files)``.

.. [#f6] Substring pattern match is effected via the SQL ``LIKE`` relation.
   TALK ABOUT WILDCARDS HERE

.. [#f7] Actually, the search actions of the relevant controllers convert the
   JSON string to a Python dictionary using the ``loads`` function of the
   ``simplejson`` module.

.. [#f8] With MySQL as RDBMS, the "regexp" relation is simply the standard MySQL
   ``REGEXP`` operator, i.e., an implementation of POSIX extended regular
   expressions.  Since SQLite does not implement a ``REGEXP`` operator, the OLD
   supplies one using the standard ``re`` Python module.  The table on
   `this page <http://www.regular-expressions.info/refflavors.html>`_ does a
   good job of detailing the difference between these two regular expression
   implementations.

.. [#f9] Cf. http://unicode.org/reports/tr15/

.. [#f10] Since some RDBMSs reuse primary key integers when a record is deleted,
   it is not possible to associate forms and collections to their backups via
   their integer id attributes.  Therefore, both form and collection resources
   have UUID attributes and are associated to their backup objects via both
   ``form_id``/``collection_id`` and ``UUID`` attributes.  The safest way,
   therefore, to request all of the backups of a given form/collection,
   therefore is to pass the UUID to the relevant ``history`` GET request.

.. [#f11] Note that the morpheme delimiters for both the
   ``syntacticCategoryString`` and ``breakGlossCategory`` values are taken,
   arbitrarily, from the ``morphemeBreak`` value.  That is, if the morphemic
   segmentation were "chien-s" and the gloss string were "dog=PL" (and "-" and
   "=" were both valid morpheme delimiters of the system), then the syntactic
   category string would be 'N-Num' and not 'N=Num'.  Similarly, the
   ``breakGlossCategory`` value would be 'chien|dog|N-s|PL|Num' and not
   'chien|dog|N=s|PL|Num'.
