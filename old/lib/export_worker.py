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

"""This module contains some multithreading worker and queue logic for
long-running processes related to the creation of OLD exports.

The export worker can only run a callable that is a global in
:mod:`old.lib.export_worker` and which takes keyword arguments.  Example usage::

    from old.lib.export_worker import EXPORT_WORKER_Q
    EXPORT_WORKER_Q.put({
        'id': h.generate_salt(),
        'func': 'generate_export',
        'args': {
            'export_id': export.id,
            'user_id': self.logged_in_user.id,
            'config_path': self.request.registry.settings['__file__'],
        }
    })

Cf. http://www.chrismoos.com/2009/03/04/pylons-worker-threads.

For an introduction to Python threading, see
http://www.ibm.com/developerworks/aix/library/au-threadingpython/.
"""

import logging
import os
import queue
import threading
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from paste.deploy import appconfig
import transaction

import old.lib.constants as oldc
import old.lib.helpers as h
import old.models as old_models
from old.models.morphologicalparser import Cache
from old.models import (
    get_engine,
    get_session_factory,
    get_tm_session,
)


LOGGER = logging.getLogger(__name__)
HANDLER = logging.FileHandler('exportworker.log')
FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
HANDLER.setFormatter(FORMATTER)
LOGGER.addHandler(HANDLER)
LOGGER.setLevel(logging.DEBUG)


################################################################################
# WORKER THREAD & QUEUE
################################################################################


EXPORT_WORKER_Q = queue.Queue(1)


class ExportWorkerThread(threading.Thread):
    """Define the export worker."""

    def run(self):
        while True:
            msg = EXPORT_WORKER_Q.get()
            try:
                LOGGER.debug('ExportWorkerThread trying to call %s',
                             msg.get('func'))
                globals()[msg.get('func')](**msg.get('args'))
            except Exception as error:
                LOGGER.warning('Unable to process in worker thread: %s %s',
                               error.__class__.__name__, error)
            EXPORT_WORKER_Q.task_done()


def start_export_worker():
    """Called in ``main`` of :mod:`old.__init__.py`."""
    export_worker = ExportWorkerThread()
    export_worker.setDaemon(True)
    export_worker.start()
    export_worker2 = ExportWorkerThread()
    export_worker2.setDaemon(True)
    export_worker2.start()


def get_dbsession_from_settings(settings):
    engine = get_engine(settings)
    session_factory = get_session_factory(engine)
    return get_tm_session(session_factory, transaction.manager)


def get_dbsession(config_path):
    config_dir, config_file = os.path.split(config_path)
    settings = appconfig('config:{}'.format(config_file),
                         relative_to=config_dir)
    return get_dbsession_from_settings(settings)


def get_local_logger():
    local_logger = logging.getLogger(__name__)
    local_logger.addHandler(HANDLER)
    local_logger.setLevel(logging.DEBUG)
    return local_logger


################################################################################
# PHONOLOGY
################################################################################


def compile_phonology(**kwargs):
    """Compile the export script of a phonology and save it to the db with values
    that indicate compilation success.
    """
    with transaction.manager:
        dbsession = get_dbsession(kwargs['config_path'])
        phonology = dbsession.query(
            old_models.Phonology).get(kwargs['phonology_id'])
        phonology.compile(kwargs['timeout'])
        phonology.datetime_modified = h.now()
        phonology.modifier_id = kwargs['user_id']
        transaction.commit()


################################################################################
# MORPHOLOGY
################################################################################


def generate_and_compile_morphology(**kwargs):
    """Generate a export script for a morphology and (optionally) compile it.
    :param int kwargs['morphology_id']: id of a morphology.
    :param bool kwargs['compile']: if True, the script will be generated *and*
        compiled.
    :param int kwargs['user_id']: id of the user model performing the
        generation/compilation.
    :param float kwargs['timeout']: how many seconds to wait before killing the
        export compile process.
    """
    with transaction.manager:
        dbsession = get_dbsession(kwargs['config_path'])
        morphology = dbsession.query(
            old_models.Morphology).get(kwargs['morphology_id'])
        try:
            morphology.write(oldc.UNKNOWN_CATEGORY)
        except Exception as error:
            LOGGER.error('Exception when calling `write` on morphology: %s %s',
                         error.__class__.__name__, error)
        if kwargs.get('compile', True):
            try:
                morphology.compile(kwargs['timeout'])
            except Exception as error:
                LOGGER.error('Exception when calling `compile` on morphology:'
                             ' %s %s', error.__class__.__name__, error)
        morphology.generate_attempt = str(uuid4())
        morphology.modifier_id = kwargs['user_id']
        morphology.datetime_modified = h.now()
        transaction.commit()


################################################################################
# MORPHEME LANGUAGE MODEL
################################################################################


def generate_language_model(**kwargs):
    """Write the requisite files (corpus, vocab, ARPA, LMTrie) of a morpheme LM
    to disk.
    :param str kwargs['morpheme_language_model_id']: ``id`` value of a morpheme
        LM.
    :param int/float kwargs['timeout']: seconds to allow for ARPA file creation.
    :param str kwargs['user_id']: ``id`` value of an OLD user.
    :returns: ``None``; side-effect is to change relevant attributes of LM
        object.
    """
    with transaction.manager:
        dbsession = get_dbsession(kwargs['config_path'])
        langmod = dbsession.query(
            old_models.MorphemeLanguageModel).get(
                kwargs['morpheme_language_model_id'])
        trie_path = langmod.get_file_path('trie')
        trie_mod_time = langmod.get_modification_time(trie_path)
        langmod.generate_succeeded = False
        try:
            langmod.write_corpus()
        except Exception as error:
            LOGGER.error('Exception when calling `write_corpus` on language'
                         ' model: %s %s', error.__class__.__name__, error)
            langmod.generate_message = 'Error writing the corpus file. %s' % error
        try:
            langmod.write_vocabulary()
        except Exception as error:
            LOGGER.error('Exception when calling `write_vocabulary` on language'
                         ' model: %s %s', error.__class__.__name__, error)
            langmod.generate_message = 'Error writing the vocabulary file. %s' % error
        try:
            langmod.write_arpa(kwargs['timeout'])
        except Exception as error:
            LOGGER.error('Exception when calling `write_arpa` on language'
                         ' model: %s %s', error.__class__.__name__, error)
            langmod.generate_message = 'Error writing the ARPA file. %s' % error
        try:
            langmod.generate_trie()
        except Exception as error:
            LOGGER.error('Exception when calling `generate_trie` on language'
                         ' model: %s %s', error.__class__.__name__, error)
            langmod.generate_message = 'Error generating the LMTrie instance. %s' % error
        else:
            if langmod.get_modification_time(trie_path) != trie_mod_time:
                langmod.generate_succeeded = True
                langmod.generate_message = 'Language model successfully generated.'
            else:
                langmod.generate_message = 'Error generating the LMTrie instance.'
        langmod.generate_attempt = str(uuid4())
        langmod.modifier_id = kwargs['user_id']
        langmod.datetime_modified = h.now()
        transaction.commit()


def compute_perplexity(**kwargs):
    """Evaluate the LM by attempting to calculate its perplexity and changing
    some attribute values to reflect the attempt.
    """
    with transaction.manager:
        dbsession = get_dbsession(kwargs['config_path'])
        langmod = dbsession.query(
            old_models.MorphemeLanguageModel).get(
                kwargs['morpheme_language_model_id'])
        timeout = kwargs['timeout']
        iterations = 5
        try:
            langmod.perplexity = langmod.compute_perplexity(timeout, iterations)
        except Exception as error:
            LOGGER.error('Exception when calling `comput_perplexity` on'
                         ' language model: %s %s', error.__class__.__name__,
                         error)
            langmod.perplexity = None
        if langmod.perplexity is None:
            langmod.perplexity_computed = False
        else:
            langmod.perplexity_computed = True
        langmod.perplexity_attempt = str(uuid4())
        langmod.modifier_id = kwargs['user_id']
        langmod.datetime_modified = h.now()
        transaction.commit()


################################################################################
# MORPHOLOGICAL PARSER (MORPHOPHONOLOGY)
################################################################################

def generate_and_compile_parser(**kwargs):
    """Write the parser's morphophonology FST script to file and compile it if
    ``compile_`` is True.  Generate the language model and pickle it.
    """
    config_dir, config_file = os.path.split(kwargs['config_path'])
    settings = appconfig('config:{}'.format(config_file),
                         relative_to=config_dir)
    engine = create_engine(settings['sqlalchemy.url'])
    dbsession = sessionmaker(bind=engine)()
    parser = dbsession.query(old_models.MorphologicalParser).get(
        kwargs['morphological_parser_id'])
    cache = Cache(parser, settings, get_dbsession_from_settings)
    parser.cache = cache
    parser.changed = False
    parser.write()
    dbsession.commit()
    if kwargs.get('compile', True):
        parser.compile(kwargs['timeout'])
    parser.modifier_id = kwargs['user_id']
    parser.datetime_modified = h.now()
    if parser.changed:
        parser.cache.clear(persist=True)
    dbsession.add(parser)
    dbsession.commit()

