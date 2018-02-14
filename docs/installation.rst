.. _installation-section:

================================================================================
Installation & Configuration
================================================================================

This section explains how to get, install and configure an OLD application.  An
overview of the process:

#. Download and install the OLD.
#. Generate an OLD config file and edit it.
#. Run the setup command to create the database tables and directory structure.
#. Serve the application and test that it is working properly.

Note that these installation instructions assume a Unix-like system, e.g.,
Linux or Mac OS X.  If you are using Windows [#f1]_, please refer to the Pylons
or the virtualenv documentation for instructions on how to create and activate
a Python virtual environment and install and download a Pylons application.


QuickStart
--------------------------------------------------------------------------------

For the impatient, here is the quickest way to install, configure and serve an
OLD application.  Before blindly issuing the following commands, however, it is
recommended that you read the detailed instructions in the following sections ::

    virtualenv --no-site-packages env
    source env/bin/activate
    easy_install onlinelinguisticdatabase
    mkdir xyzold
    cd xyzold
    paster make-config onlinelinguisticdatabase production.ini
    paster setup-app production.ini
    paster serve production.ini

Open a new terminal window and run the basic test script to ensure that the OLD
application is being served and is operating correctly::

    python _requests_tests.py

You should see ``All requests tests passed.`` as output.  Congratulations.


Download
--------------------------------------------------------------------------------

Pre-packaged eggs of stable OLD releases can be downloaded from the
`Python Package Index <http://pypi.python.org/pypi/onlinelinguisticdatabase>`_.

The easiest way to get and install the OLD is via the Python command-line
program Easy Install.  Before issuing the following command, read the
:ref:`virtual-env` and consider installing the OLD in a virtual environment.
To download and install the OLD with Easy Install, run::

    sudo easy_install onlinelinguisticdatabase

For developers, the full source code for the OLD can be found on
`GitHub <https://github.com/jrwdunham/old.>`_.  To clone the OLD repository,
first install `Git <http://git-scm.com/>`_ and then run::

    git clone git://github.com/jrwdunham/old.git

See below for detailed instructions.


Install
--------------------------------------------------------------------------------


.. _virtual-env:

Create a virtual Python environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It is recommended that the OLD be installed in a virtual Python environment.  A
virtual environment is an isolated Python environment within which you can
install the OLD and its dependencies without inadvertently rendering other
programs unworkable by, say, upgrading *their* dependencies in incompatible
ways.  If you do not want to install the OLD and its dependencies in a virtual
environment, skip this section.

Use `virtualenv <http://www.virtualenv.org>`_ to create a virtual Python
environment.  First, follow the steps on the aforementioned web site to
install virtualenv.  If you already have ``easy_install`` or ``pip`` installed,
you can just run one of the following commands at the terminal::

    pip install virtualenv
    easy_install virtualenv

Otherwise, you can download the ``virtualenv`` archive, decompress it, move into
the directory and install it manually, i.e., ::

    cd virtualenv-X.X
    python setup.py install

Once virtualenv is installed, create a virtual environment in a directory called
``env`` (or any other name) with the following command::

    virtualenv --no-site-packages env

The virtual environment set up in ``env`` is packaged with a program called
``easy_install`` which, as its name suggests, makes it easy to install Python
packages and their dependencies.  We will use the virtual environment's version
of ``easy_install`` to install the OLD and its dependencies into the virtual
environment.

There are two ways to do this.  The more explicit and verbose way is to specify
the path to the executables in the virtual environment directory.  That is, to
run the virtual environment's ``python``, ``easy_install`` or ``pip``
executables, you would run one of the following commands. ::

    /path/to/env/bin/python
    /path/to/env/bin/easy_install
    /path/to/env/bin/pip

The easier way (on Posix systems) is to activate the Python virtual environment
by running the ``source`` command with the path to the ``activate`` executable
in your virtual environment as its first argument.  That is, run::

    source /path/to/env/bin/activate

If the above command was successful, you should see the name of your virtual
environment directory in parentheses to the left of your command prompt, e.g.,
``(env)username@host:~$``.  Now invoking ``python``, ``easy_install``,
``paster``, ``pip``, etc. will run the relevant executable in your virtual
environment.


Install the OLD
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The easiest way to install the OLD is via
`Easy Install <http://peak.telecommunity.com/DevCenter/EasyInstall>`_, as in
the command below.  (Note that from this point on I am assuming that you have
activated a virtual environment in one of the two ways described above or have
elected not to use a virtual environment.) ::

    easy_install onlinelinguisticdatabase

You can also use ``pip`` to install it::

    pip install onlinelinguisticdatabase

Once the install has completed, you should see ``Finished processing
dependencies for onlinelinguisticdatabase``.  (If you used ``pip``, you will see
something like ``Successfully installed onlinelinguisticdatabase``.)  This means
that the OLD and all of its dependencies have been successfully installed.

If you have downloaded the OLD source code and need to install the dependencies,
then move to the root directory of the source, i.e., the one containing the
``setup.py`` file, and run::

    python setup.py develop


Configure
--------------------------------------------------------------------------------

.. _gen-config:

Generate the config file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once the OLD is installed, it is necessary to configure it.  This is done by
generating a default config file and making any desired changes.  When the OLD's
setup script is run, several directories will be created in the same directory
as the config file.  Therefore, it is a good idea to create the config file in
its own directory.  I use the convention of naming production systems using the
`ISO 639-3 <http://www-01.sil.org/iso639-3/codes.asp>`_ three-character id of
the object language.  To illustrate, I will use the fictitious language id *xyz*
and will name the directory ``xyzold``, the MySQL database ``xyzold`` and the
MySQL user ``xyzuser``.  If following this convention, replace "xyz" with the Id
of the language your OLD application will be documenting.  To make a new
directory called ``xyzold`` and change to it, issue the following commands. ::

    mkdir xyzold
    cd xyzold

The first step in configuring the OLD is creating a config file.  To create a
config file named ``production.ini``, run::

    paster make-config onlinelinguisticdatabase production.ini

By default, the OLD is set to serve at 127.0.0.1 on port 5000, the Pylons
interactive debugger is turned off and the database (RDBMS) is set to
`SQLite <http://www.sqlite.org/>`_ (a database called ``production.db`` will be
created in the current directory). These defaults are good for verifying that
everything is working ok.  On a production system you will need to change the
``host`` and ``port`` values in the config file as well as set the database to
`MySQL <http://www.mysql.com/>`_. If you want to get up and running with MySQL
right away, see the :ref:`mysql-config` section; otherwise, continue on to
:ref:`edit-config`.

Developers will not need to generate a config file.  The ``test.ini`` and
``development.ini`` config file should already be present in the root directory
of the source.  See the :ref:`developers` section for details.


.. _mysql-config:

Set up MySQL/MySQLdb
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The OLD can be configured to use either MySQL or SQLite as its relational
database management system (RDBMS).

While SQLite is easy to install (both the SQLite library and the ``pysqlite``
language binding are built into the Python language), it is not recommended for
multi-user concurrent production systems.  Therefore, a production OLD setup
should have MySQL installed.  The following instructions assume that you have
successfully installed the MySQL server on your system.

First login to MySQL as root::

    mysql -u root -p<root_password>

Then create a database to store your OLD data::

    mysql> create database xyzold default character set utf8;

Now create a MySQL user with sufficient access to the above-created database.
In the first command, ``xyzuser`` is the username and ``4R5gvC9x`` is the
password. ::

    mysql> create user 'xyzuser'@'localhost' identified by '4R5gvC9x';
    mysql> grant select, insert, update, delete, create, drop on xyzold.* to 'xyzuser'@'localhost';
    mysql> quit;

Make sure that the above commands worked::

    mysql -u xyzuser -p4R5gvC9x
    mysql> use xyzold;
    mysql> show tables;

Now MySQL is set up with a database called ``xyzold`` (with UTF-8 as its default
character set) and a user ``xyzuser`` who has access to ``xyzold``.  The next
step is to make sure that the python module ``MySQLdb`` is installed.  Enter a
Python prompt (using your virtual environment, if applicable) and check::

    python
    >>> import MySQLdb

If you see no output, then ``MySQLdb`` is installed.  If you see ``ImportError:
No module named MySQLdb``, then you need to install ``MySQLdb``.

Installing ``MySQLdb`` can be tricky.  On some Linux distributions, it is
necessary to first install ``python-dev``.  On distros with the Advanced
Packaging Tool, you can run the following command. ::

    apt-get install python-dev

Once ``python-dev`` is installed, run the following to install ``MySQLdb``
(remembering to activate the virtual environment, if necessary). ::

    easy_install MySQL-python

Note that it is also possible to use ``easy_install`` to install ``MySQLdb`` at
the same time as you install the OLD.  Instead of running ``easy_install
onlinelinguisticdatabase`` as above, run the following command::

    easy_install onlinelinguisticdatabase[MySQL]


.. _edit-config:

Edit the config file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The config file (whose creation was described in :ref:`gen-config`) is where an
OLD app is configured.  Open the config file (e.g., ``production.ini``) and make
any desired changes.  While the config file is self-documenting, this section
supplements that documentation.

(Note that once the OLD is downloaded and installed, it may be used to run
several distinct OLD web services, e.g., for different languages.  To do this,
repeat the configuration steps with different settings.  For example, to create
two OLD web services, one for language *xyz* and one for language *abc*, create
two directories, ``xyzold`` and ``abcold``, generate a config file in each, and
edit each config file appropriately, following these instructions.)

The host and port where the application will be served are configured here.
The defaults of ``127.0.0.1`` (i.e., localhost) and ``5000`` are fine for
initial setup and testing.  During deployment and server configuration, the host
will certainly need to be changed and the port probably also.

The ``set debug = false`` line should be left as is on a production setup.
However, for initial testing it is a good idea to comment out this line with a
hash mark (i.e., ``#set debug = false``) so that errors can be debugged.  When
the line is commented out and an error occurs, Pylons will generate a detailed
error report with a web interface that can be accessed by navigating to the link
printed to the console (i.e., stderr).

The ``sqlalchemy.url`` parameter will need to be changed, depending on the
relational database setup needed.  If SQLite will be used, then the
``sqlalchemy.url = sqlite:///production.db`` line should remain uncommented.
Change the database name, if desired; i.e., change ``production.db`` to, say,
``mydb.sql``.

If MySQL will be used, then the first step is to comment out the SQLite line,
and uncomment the *two* MySQL lines::

    #sqlalchemy.url = sqlite:///production.db
    sqlalchemy.url = mysql://username:password@localhost:3306/dbname
    sqlalchemy.pool_recycle = 3600

Then, change the first MySQL line so that it contains the appropriate values for
your MySQL setup.  E.g., using the example setup from :ref:`mysql-config` would
involve changing it to the following::

    sqlalchemy.url = mysql://xyzuser:4R5gvC9x@localhost:3306/xyzold

The only other values you may want to change are ``password_reset_smtp_server``,
``create_reduced_size_file_copies`` and ``preferred_lossy_audio_format``.

Uncomment the ``password_reset_smtp_server = smtp.gmail.com`` line if you want
the system to send emails using a Gmail account specified in a separate
``gmail.ini`` config file.

Set ``create_reduced_size_file_copies`` to ``0`` if you do *not* want the system
to create copies of images and .wav files with reduced sizes.  Note that in
order for the reduced-copies functionality to succeed with images and .wav files
it is necessary to install the Python Imaging Library (PIL) and FFmpeg,
respectively (see the :ref:`soft-dependecies` section below).

Finally, set the ``preferred_lossy_audio_format`` to ``mp3`` instead of ``ogg``
if you would like to create .mp3 copies of your users' .wav files instead of
.ogg ones. (Note that a default installation of FFmpeg may not be able to
convert .wav to .mp3 without installation of some additional libraries.)


Setup
--------------------------------------------------------------------------------

Once the OLD has been installed and a config file has been created and edited,
it is time to run the ``setup`` command.  This will generate the tables in the
database, insert some defaults (e.g., some users and useful tags) and create
the requisite directory structure.  To set up an OLD application, move to the
directory containing the config file (e.g., ``xyzold`` containing
``production.ini``) and run the ``paster setup-app`` command::

    cd xyzold
    paster setup-app production.ini

If successful, the output should be ``Running setup_app() from
onlinelinguisticdatabase.websetup``.  By default, the OLD sends logs to
``application.log`` so if you run ``cat application.log`` you should see
something like the following. ::

    Environment loaded.
    Retrieving ISO-639-3 languages data.
    Creating a default administrator, contributor and viewer.
    Tables created.
    Creating default home and help pages.
    Generating default application settings.
    Creating some useful tags and categories.
    Adding defaults.
    OLD successfully set up.

If you now enter the database and poke around, you will see that the tables have
been created and the defaults inserted. ::

    mysql -u xyzuser -p4R5gvC9x
    mysql> use xyzold;
    mysql> show tables;
    mysql> select username from user;

You should also see two new directories (``analysis`` and ``files``), the
application log file ``application.log`` and Python script
``_requests_tests.py``.


.. _serve:

Serve
--------------------------------------------------------------------------------

To begin serving an OLD application, use Paster's ``serve`` command::

    paster serve production.ini

The output should be something like the following. ::

    Starting server in PID 7938.
    serving on http://127.0.0.1:5000

If you visit ``http://127.0.0.1:5000`` in a web browser, you should see
``{"error": "The resource could not be found."}`` displayed.  If you visit 
``http://127.0.0.1:5000/forms`` in a web browser, you should see
``{"error": "Authentication is required to access this resource."}``.  These
error responses are to be expected: the first because no resource was specified
in the request URL and the second because authentication is required before
forms can be read.  Congratulations, this means an OLD application has
successfully been set up and is being served locally.

When ``paster setup-app`` is run, a Python script called ``_requests_tests.py``
is created in the current working directory.  This script uses the Python
Requests module to test that a live OLD application is working correctly.
Assuming that you have run ``paster serve`` and an OLD application is being
served locally on port 5000, running the following command will run the
``_requests_tests`` script::

    python _requests_tests.py

If everything is working correctly, you should see ``All requests tests
passed.``  (Note that if you have changed the config file, i.e., the host or
port values, then you will need to change the values of the ``host`` and/or
``port`` variables in ``_requests_tests.py`` to match.)


.. _soft-dependecies:

Soft dependencies
--------------------------------------------------------------------------------

In order to create smaller copies of image files and .wav files, the OLD uses
the `Python Imaging Library (PIL) <http://www.pythonware.com/products/pil/>`_
and the `FFmpeg <http://www.ffmpeg.org/>`_ command-line program.  If you would
like your OLD application to automatically create reduced-size images and lossy
(i.e., .ogg or .mp3) copies of .wav files, then these programs should be
downloaded and installed using the instructions on the above-linked pages.  I
provide brief instructions here.

In order to allow the specification of phonologies as finite-state transducers,
the OLD uses the command-line programs
`foma and flookup <http://code.google.com/p/foma/>`_.  See the linked
page for installation instructions.

In order to search OLD treebank corpora,
`Tgrep2 <http://tedlab.mit.edu/~dr/Tgrep2/>`_ must be installed. 

NLTK may be used for some OLD functionality.

PIL
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To install PIL, download and decompress the
`source <http://www.pythonware.com/products/pil/#pil117>`_.  Then move into the
root folder and run ``setup.py install`` (remembering to use your ``virtualenv``
Python executable, if necessary)::

    cd Imaging-1.1.7
    python setup.py install

.. note::

    I experienced difficulties installing PIL in this way such that jpeg
    functionality was not working.  To correctly install PIL, I did::
    
        cd Imaging-1.1.7
        ~/env/bin/python setup.py build_ext -i
        ~/env/bin/python selftests.py
        ~/env/bin/python setup.py install

The OLD accepts .jpg, .png and .gif image file uploads.  If you want to test
whether the PIL install can resize all of these formats, create a test file of
each format and run something like the following.  If successful, you will have
created a smaller version of each image::

    >>> import Image
    >>> im = Image.open('large_image.jpg')
    >>> im.thumbnail((500, 500), Image.ANTIALIAS)
    >>> im.save('small_image.jpg')


FFmpeg
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

FFmpeg is a command-line tool that can convert .wav files to the lossy formats
.ogg and .mp3.  It can be somewhat tricky to install FFmpeg properly and some
installs will not support .mp3 creation by default.  For Debian 6.0 (Squeeze), I
can recommend
`this tutorial <http://www.e-rave.nl/installing-ffmpeg-on-debian-squeeze-and-newer>`_.

Once ``ffmpeg`` is installed, you can check whether .wav-to-.ogg and
.wav-to-.mp3 conversion is working by ensuring you have a file called
``old_test.wav`` in the current directory and issuing the following commands::

    ffmpeg -i old_test.wav old_test.ogg
    ffmpeg -i old_test.wav old_test.mp3

If successful, you will have created a .ogg and a .mp3 version of your .wav
file.


Deploy
--------------------------------------------------------------------------------

Deploying an OLD application means getting a domain name, serving the
application on the world wide web and setting up some admin scripts.  There are
many possible ways to achieve this.  In my production systems I have followed
the approach of using Apache to proxy requests to Pylons as described in
`Chapter 21: Deployment <http://pylonsbook.com/en/1.1/deployment.html>`_ of
`The Pylons Book`_ and have had success with that.  I
review that approach here.

Assuming Apache 2, ``mod_proxy`` and ``mod_proxy_http`` are installed, you
first enable the latter two::

    sudo a2enmod proxy
    sudo a2enmod proxy_http

Then you create a config file such as the one below in
``/etc/apache2/sites-available/`` or in the equivalent location for your
platform.  I used the config file below for an OLD application deployed for
documenting the Okanagan language.  The domain name is *okaold.org*.  I saved
the file as ``/etc/apache2/sites-available/okaold.org`` and  created the error
logs directory, i.e., ``/home/old/log``.  The only configuration necessary for
the *OLD* config file (i.e., the ``production.ini`` file whose creation was
detailed in :ref:`gen-config`) is to ensure that the ``host`` variable is set to
``localhost`` and the ``port`` variable is set to ``8081``. ::

    NameVirtualHost *
    # OKA - Okanagan
    <VirtualHost *>
        ServerName okaold.org
        ServerAlias www.okaold.org
    
        # Logfiles
        ErrorLog /home/old/log/error.log
        CustomLog /home/old/log/access.log combined
                                                 
        # Proxy
        ProxyPreserveHost On
        ProxyPass / http://localhost:8081/ retry=5
        ProxyPassReverse / http://localhost:8081/
        <Proxy *>
            Order deny,allow
            Allow from all
        </Proxy>
    </VirtualHost>

Now you can start serving the OLD application with Paster.  In order to keep the
server running after you exit the shell, you must invoke ``paster serve`` in
daemon mode, as follows::

    paster serve --daemon production.ini start

Now disable the default Apache configuration, enable the virtual host config
file just created (in this case ``okaold.org``) and restart Apache::

    sudo a2dissite default
    sudo a2ensite okaold.org
    sudo /etc/init.d/apache2 restart

You might also want the ``paster serve`` script to log error messages, which you
can do by specifying a file to log to using the ``--log-file`` option.  You can
also use the ``--pid-file`` option to store the process ID of the running server
in a file so that other tools know which server is running::

    paster serve --daemon --pid-file=/home/old/okaold.pid --log-file=/home/old/log/paster-okaold.log production.ini start

As well as specifying ``start``, you can use a similar command with ``stop`` or
``restart`` to stop or restart the running daemon, respectively.

The Pylons Book also explains how to
`Create init scripts <http://pylonsbook.com/en/1.1/deployment.html#creating-init-scripts>`_
and how to use ``crontab`` to restart a paster server that is serving an
OLD/Pylons application (should that) ever be necessary.  See the referenced
sections for details.

You may also wish to write admin scripts to monitor an OLD application to ensure
that it is functioning properly and to email you if not.  I may include a guide
for doing that at some future data.

Finally, it is a good idea to make regular backups of the database and the
``files`` and ``analysis`` directories of your OLD application.  In my
production systems I have used
`MySQL database replication <http://www.howtoforge.com/mysql_database_replication>`_
to create a mirror of my production database on a second server in a different
location.  I then use the standard Unix utility ``rsync`` to create live copies
of the ``files`` and ``analysis`` directories on that same second server.
A Python script is run periodically on the second server to perform a ``mysqldump``
of the relevant databases.  I will further document my backup setup at a later
date.


.. _developers:

Developers
--------------------------------------------------------------------------------

This section provides an overview of the OLD for developers.  It covers (1) how
to download the source and install the dependencies, (2) the structure of the
source, (3) how to write and compile the documentation to HTML and PDF, (4) the
creation of Python version-specific virtual environments and (5) the building of
OLD releases as eggs or archives.

For detailed documentation on developing a Pylons application, consult the
excellent documentation for the Pylons framework, i.e., `The Pylons Book`_.


Download & depencency installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This subsection details how to get the OLD source and install its dependencies.
To download the most up-to-date source code, make sure you have
`Git <http://git-scm.com/>`_ installed and run::

    git clone git://github.com/jrwdunham/old.git

To install the dependencies, move to the newly created ``old`` directory and
run::

    python setup.py develop


Directory structure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``onlinelinguisticdatabase`` directory contains all of the files and
directories that will be packaged into the final distribution.  Its
subdirectories are ``config``, ``controllers``, ``lib``, ``model``, ``public``,
and ``tests``.  This section gives an overview of the contents of these
directories and the ``websetup.py`` file.

The ``websetup.py`` file controls how an OLD application is set up.  That is,
when ``paster setup-app config_file.ini`` is run (or when ``nosetests`` is run),
the contents of ``websetup.py`` determine what database tables are created, what
defaults are entered into them and what directories are created.

The ``config`` directory houses the ``deployment.ini_tmpl`` and ``routing.py``
files.  The former is the template used to generate the config file when
something like ``paster make-config production.ini`` is run.  The ``routing.py``
module is where the mappings from URL paths to OLD controller actions are
specified.  When a new controller is created or the interface to an existing
controller needs to be changed, the ``routing.py`` file must be edited.

The ``controllers`` directory holds a module for each OLD controller.  For
example, the ``controllers/forms.py`` module defines a ``FormsController``
class; the methods of this class (the controller's *actions*) return values
which determine the content of particular responses.  The ``index`` method
(action) of the ``FormsController`` class, for example, returns a list of all
form models in the database; since ``config/routing.py`` maps ``GET /forms`` to
``FormsController.index``, it is this list of forms that is returned when
``GET /forms`` is requested.

The ``lib`` directory holds modules that define functionality used by multiple
controllers.  The ``utils.py`` module defines a large number of widely-used
functions, classes and data structures; these are made available in controllers
under the ``h`` namespace, e.g., the value of ``h.markupLanguages`` is the list
of valid markup language string values, as defined in ``utils.py``.  The
``auth.py`` script holds the decorators that control authentication and
authorization.  The ``schemata.py`` module contains the validators that are
applied against user input.  The other modules in the ``lib`` directory are
mentioned in this document where appropriate; consult the docstrings for more
information.

The ``model`` directory contains a module for each SQLAlchemy model used by the
OLD.  For example, ``model/file.py`` houses the ``File`` class which defines the
attributes of the file model and their implementation as columns and relations
in a relational database.  The ``model/model.py`` is special; it defines the
``Model`` class from which all of the other models inherit a number of methods.
Note that in order to make a model available in the
``onlinelinguisticdatabase.model`` namespace, it must be imported in
``model/__init__.py``.

The ``public`` directory may contain static files, HTML, CSS and JavaScript.
Since the client-side OLD application has not yet been implemented, the
``public`` directory contains, at present, only the ``iso_639_3_languages_data``
which stores the tab-delimited files containing the ISO-639-3 dataset.

The ``tests`` directory contains all of the test modules.  When the
``nosetests`` command is run, it is the modules here that define the tests.  For
example, ``tests/functional/test_forms.py`` defines a ``TestFormsController``
class whose methods test the various actions (or functionalities) of the forms
controller.  For example, the ``test_create`` method of the
``TestFormsController`` class simulates ``POST /forms`` requests and confirms
that the system behaves as expected.  When testing new funcionality, new tests
should be defined in ``tests/functional`` or existing tests should be
supplemented.  Note the ``_toggle_tests.py`` script which does not define tests
but provides an easy way to turn large numbers of them on or off.  For example,
``./onlinelinguisticdatabase/tests/functional/_toggle_tests.py on`` will turn
all tests on and
``./onlinelinguisticdatabase/tests/functional/_toggle_tests.py off`` will turn
them all off.  See its docstrings for further usage instructions.  Finally, the
``tests`` directory also contains the ``_requests_tests.py`` script which
defines some simple tests (using the Requests module) which (as described in the
:ref:`serve` section) can be run on a live OLD application to ensure that it is
working correctly.

The ``websetup.py`` module defines the ``setup_app`` function that is called
when the OLD is set up, i.e., when ``paster setup-app config_file.ini`` is
issued.  The behaviour of the setup process is determined by the name of the
config file.  If ``test.ini`` is the config file (as is the case when
``nosetests`` is run), then test-specific setup will be performed, i.e., all
database tables will be dropped and then re-created.  Otherwise, only the tables
that do not already exist will be created.


Documentation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This section reviews the OLD documentation creation process.  The OLD
documentation (i.e., this document) is written using
`Sphinx <http://sphinx-doc.org/>`_ and the reStructuredText lightweight markup
language.  In order to edit and build the documentation, Sphinx must be
installed::

    easy_install sphinx

The reStructuredText source files for the OLD documentation are the
``.rst``-suffixed files in the ``docs`` directory.  The
`Sphinx documentation <http://sphinx-doc.org/contents.html>`_ has a good
overview of the reStructuredText syntax.  Once the source files have been
edited, build the documentation HTML (in ``docs/_build/html``) by moving to the
``docs`` directory and running::

    sphinx-build -b html . ./_build/html

To generate a LaTeX version of the documentation in ``docs/_build/latex``, run
(from the ``docs`` directory)::

    sphinx-build -b latex . ./_build/latex

If ``pdflatex`` is installed [#f2]_, generate a PDF of the documentation by moving to
``docs/_build/latex`` and running::

    pdflatex -interaction=nonstopmode OLD.tex


Virtualenv & Python distros
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order to test whether the OLD works on different Python versions or to build
distributions for those versions, it is necessary to create virtual environments
for each such Python distribution.

The `pythonbrew <https://pypi.python.org/pypi/pythonbrew/>`_ utility facilitates
the building and installation of different Pythons in a user's home directory.
Install ``pythonbrew`` using the instructions on its web site.

Now run ``pythonbrew install`` to install the desired Pythons.  For example, to
install Python 2.4.6, 2.5.6 and 2.7.3, run::

    pythonbrew install 2.4.6
    pythonbrew install 2.5.6
    pythonbrew install 2.7.3

Once complete, new Python executables should be installed in
``~/.pythonbrew/pythons/Python-2.4.6``, ``~/.pythonbrew/pythons/Python-2.5.6``,
etc.  For example, to launch the Python 2.5.6 interactive console, run::

    ~/.pythonbrew/pythons/Python-2.5.6/bin/python

To create a virtual environment using one of these Pythons, run ``virtualenv``
with the ``-p`` option followed by the path to the desired Python executable.
It is also a good idea to choose a name for the virtual environment that makes
it easy to tell what version of Python it uses.  For example::

    virtualenv -p ~/.pythonbrew/pythons/Python-2.5.6/bin/python env-2.5.6

Make sure that the new virtual environment has the correct python::

    ~/env-2.5.6/bin/python --version

Note that the OLD works with Python 2.6 and 2.7 but not with 2.4 or 2.5.  It has
not been tested with Python 3.


Releases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This section explains how to build stable OLD releases and how to upload them to
PyPI.

To build an egg or a source distribution of a stable release, run the following
two commands, respectively::

    python setup.py bdist_egg
    python setup.py sdist

Each of these commands will create a new archive in the ``dist`` directory.

In order to build an OLD egg distribution and upload it to PyPI in one command,
run the following command.  (Note that you will need the OLD's PyPI password in
order to be permitted to do this.) ::

    python setup.py bdist_egg register upload

To create and upload the source distribution to PyPI (so that, e.g., Pip can be
used to install the OLD), run::

    python setup.py sdist register upload



.. [#f1] The OLD has not been tested on Windows.  Some alterations to the source
   may be required in order to get it running on a Windows OS.  To be clear,
   this does *not* mean that users running a Windows OS will not be able to use
   a production OLD web application.  A live OLD application is a web service
   and users with any operating system should be able to interact with it,
   assuming an internet connection is available.  What this does mean is that
   the OLD, as is, may not run on a Windows *server*.

.. [#f2] See `this page <http://www.charlietanksley.net/philtex/basics-of-latex-from-the-command-line/>`_
   for an overview of how to use the TeX command-line utilities.

.. _`The Pylons Book`: <http://pylonsbook.com/>
