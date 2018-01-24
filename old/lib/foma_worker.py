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

"""This module contains some multithreading worker and queue logic plus the
functionality -- related to foma compilation ang LM estimation -- that the
worther thread initiates.

The the foma worker compiles foma FST phonology, morphology and morphophonology
scripts and estimates morpheme language models.  Having a worker perform these
tasks in a separate thread from that processing the HTTP request allows us to
immediately respond to the user.

The foma worker can only run a callable that is a global in
:mod:`old.lib.foma_worker` and which takes keyword
arguments.  Example usage::

    from old.lib.foma_worker import FOMA_WORKER_Q
    FOMA_WORKER_Q.put({
        'id': h.generate_salt(),
        'func': 'compile_foma_script',
        'args': {
            'model_name': 'Phonology',
            'model_id': phonology.id,
            'script_dir_path': phonology_dir_path,
            'user_id': session['user'].id,
            'verification_string': 'defined phonology: ',
            'timeout': h.phonology_compile_timeout
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
from sqlalchemy.orm import sessionmaker, scoped_session
from paste.deploy import appconfig

import old.lib.constants as oldc
import old.lib.helpers as h
import old.models as old_models
from old.models.morphologicalparser import Cache

LOGGER = logging.getLogger(__name__)
HANDLER = logging.FileHandler('fomaworker.log')
FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
HANDLER.setFormatter(FORMATTER)
LOGGER.addHandler(HANDLER)
LOGGER.setLevel(logging.DEBUG)


################################################################################
# WORKER THREAD & QUEUE
################################################################################


FOMA_WORKER_Q = queue.Queue(1)


class FomaWorkerThread(threading.Thread):
    """Define the foma worker."""

    def run(self):
        while True:
            msg = FOMA_WORKER_Q.get()
            try:
                LOGGER.debug('FomaWorkerThread trying to call %s',
                             msg.get('func'))
                globals()[msg.get('func')](**msg.get('args'))
            except Exception as error:
                LOGGER.warning('Unable to process in worker thread: %s %s',
                               error.__class__.__name__, error)
            FOMA_WORKER_Q.task_done()


def start_foma_worker():
    """Called in ``main`` of :mod:`old.__init__.py`."""
    foma_worker = FomaWorkerThread()
    foma_worker.setDaemon(True)
    foma_worker.start()
    foma_worker2 = FomaWorkerThread()
    foma_worker2.setDaemon(True)
    foma_worker2.start()


def get_dbsession_from_settings(settings):
    return scoped_session(
        old_models.get_session_factory(old_models.get_engine(settings)))


def get_local_logger():
    local_logger = logging.getLogger(__name__)
    local_logger.addHandler(HANDLER)
    local_logger.setLevel(logging.DEBUG)
    return local_logger


################################################################################
# PHONOLOGY
################################################################################


def compile_phonology(**kwargs):
    """Compile the foma script of a phonology and save it to the db with values
    that indicate compilation success.
    """
    try:
        dbsession = get_dbsession_from_settings(kwargs['settings'])()
        phonology = dbsession.query(
            old_models.Phonology).get(kwargs['phonology_id'])
        phonology.compile(kwargs['timeout'])
        phonology.datetime_modified = h.now()
        phonology.modifier_id = kwargs['user_id']
    finally:
        dbsession.commit()
        dbsession.close()


################################################################################
# MORPHOLOGY
################################################################################


def generate_and_compile_morphology(**kwargs):
    """Generate a foma script for a morphology and (optionally) compile it.
    :param int kwargs['morphology_id']: id of a morphology.
    :param bool kwargs['compile']: if True, the script will be generated *and*
        compiled.
    :param int kwargs['user_id']: id of the user model performing the
        generation/compilation.
    :param float kwargs['timeout']: how many seconds to wait before killing the
        foma compile process.
    """
    try:
        dbsession = get_dbsession_from_settings(kwargs['settings'])()
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
    finally:
        dbsession.commit()
        dbsession.close()


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
    try:
        dbsession = get_dbsession_from_settings(kwargs['settings'])()
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
    finally:
        dbsession.commit()
        dbsession.close()


def compute_perplexity(**kwargs):
    """Evaluate the LM by attempting to calculate its perplexity and changing
    some attribute values to reflect the attempt.
    """
    try:
        dbsession = get_dbsession_from_settings(kwargs['settings'])()
        langmod = dbsession.query(
            old_models.MorphemeLanguageModel).get(
                kwargs['morpheme_language_model_id'])
        timeout = kwargs['timeout']
        iterations = 5
        try:
            langmod.perplexity = langmod.compute_perplexity(timeout, iterations)
        except Exception as error:
            LOGGER.error('Exception when calling `compute_perplexity` on'
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
    finally:
        dbsession.commit()
        dbsession.close()


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
    try:
        dbsession = get_dbsession_from_settings(kwargs['settings'])
        parser = dbsession.query(old_models.MorphologicalParser).get(
            kwargs['morphological_parser_id'])
        cache = Cache(parser, kwargs['settings'], get_dbsession_from_settings)
        parser.cache = cache
        parser.changed = False
        parser.write()
        dbsession.commit()
        if kwargs.get('compile', True):
            parser.compile(kwargs['timeout'])
        parser.modifier_id = kwargs['user_id']
        parser.datetime_modified = h.now()
        #parser.changed = True  # TESTS SHOULD PASS WITHOUT THIS!
        if parser.changed:
            parser.cache.clear(persist=True)
        dbsession.add(parser)
    finally:
        dbsession.commit()
        dbsession.close()
