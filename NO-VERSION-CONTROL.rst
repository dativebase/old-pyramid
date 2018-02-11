
30 days * 8 hours (per day) = 240 hours
$10,000

240 hours / 5 hours per week = 48 weeks 


DativeBase Estimate: Offline Functionality
================================================================================

This is an estimate for what it would take to make DativeBase work offline.

First, some definitions: DativeBase is Dative and the OLD working together to
provide a unified linguistic fieldwork and analysis experience. The Online
Linguistic Database (OLD) is a server-side application. It builds an HTTP API
that can expose multiple OLD instances. An OLD instance is a linguistic database
(and application settings) stored as a MySQL (or SQLite) database and a
directory on disk. Dative is a browser-based GUI application that can provide
a user interface to one or more OLD instances.

Offline functionality means being able to use DativeBase without an Internet
connection. This should happen transparently and fluidly.

At the highest level, the task can be bifurcated into these two tasks (ordered
by increasing difficulty):

1. Make it easy to deploy DativeBase as a Desktop Application, i.e., implement ("DativeTop?")
   (targetting Mac OS, Windows and Linux in priority order).
2. Handle synchronization after offline state mutation. 


Database Mutations
================================================================================

old/views/morphemelanguagemodels.py
234:        self.request.dbsession.add(langmod_backup)

old/views/auth.py
124:            request.dbsession.add(user)
126:            request.dbsession.rollback()
137:                request.dbsession.rollback()

old/views/files.py
136:            self.request.dbsession.add(resource)
137:            self.request.dbsession.flush()
177:                self.request.dbsession.add(file_)
178:                self.request.dbsession.flush()

old/views/phonologies.py
219:        self.request.dbsession.add(phonology_backup)

old/views/morphologies.py
278:        self.request.dbsession.add(morphology_backup)

old/views/forms.py
97:        self.request.dbsession.add(form_backup)
166:        self.request.dbsession.add(form_model)
354:        self.request.dbsession.add(user_model)
355:        self.request.dbsession.flush()
462:                self.request.dbsession.execute('set names utf8;')
466:            self.request.dbsession.execute(update, form_buffer)
468:            self.request.dbsession.add_all(formbackup_buffer)
469:            self.request.dbsession.flush()

old/views/collections.py
126:        self.request.dbsession.add(resource)
127:        self.request.dbsession.flush()
201:        self.request.dbsession.add(resource_model)
202:        self.request.dbsession.flush()
279:        self.request.dbsession.add(collection_backup)
501:            self.request.dbsession.add_all(collections_referencing_this_collection)
502:            self.request.dbsession.flush()
589:        self.request.dbsession.add(collection)
590:        self.request.dbsession.flush()

old/views/resources.py
455:        self.request.dbsession.add(resource)
456:        self.request.dbsession.flush()
520:        self.request.dbsession.add(resource_model)
521:        self.request.dbsession.flush()
586:        self.request.dbsession.delete(resource_model)
587:        self.request.dbsession.flush()

old/views/corpora.py
438:        self.request.dbsession.add(corpus_backup)
602:        self.request.dbsession.flush()

old/views/morphologicalparsers.py
419:        self.request.dbsession.add(morphological_parser_backup)

