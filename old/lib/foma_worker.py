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

from paste.deploy import appconfig
import transaction

import old.lib.constants as oldc
import old.lib.helpers as h
import old.models as old_models
from old.models import (
    get_engine,
    get_session_factory,
    get_tm_session,
)


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
    """Define the foma worker.
    """
    def run(self):
        LOGGER.debug('run called in FomaWorkerThread instance')
        while True:
            msg = FOMA_WORKER_Q.get()
            try:
                LOGGER.debug('FomaWorkerThread trying to call %s',
                             msg.get('func'))
                globals()[msg.get('func')](**msg.get('args'))
            except Exception as error:
                LOGGER.warning('Unable to process in worker thread: %s', error)
            LOGGER.debug('FormaWorkerThread calling task_done on FOMA_WORKER_Q')
            FOMA_WORKER_Q.task_done()


def start_foma_worker():
    """Called in :mod:`onlinelinguisticdatabase.config.environment.py`.
    """
    LOGGER.debug('starting forma worker 1')
    foma_worker = FomaWorkerThread()
    foma_worker.setDaemon(True)
    foma_worker.start()
    LOGGER.debug('starting forma worker 2')
    foma_worker2 = FomaWorkerThread()
    foma_worker2.setDaemon(True)
    foma_worker2.start()


def get_dbsession(config_path):
    config_dir, config_file = os.path.split(config_path)
    settings = appconfig('config:{}'.format(config_file),
                         relative_to=config_dir)
    engine = get_engine(settings)
    session_factory = get_session_factory(engine)
    return get_tm_session(session_factory, transaction.manager)


################################################################################
# PHONOLOGY
################################################################################


def compile_phonology(**kwargs):
    """Compile the foma script of a phonology and save it to the db with values
    that indicate compilation success.
    """

    mylogger = logging.getLogger(__name__)
    mylogger.addHandler(HANDLER)
    mylogger.setLevel(logging.DEBUG)

    mylogger.debug('FOX IN COMPILE PHONOLOGY')
    mylogger.debug(kwargs)
    with transaction.manager:
        mylogger.debug('FOX getting dbsession')
        dbsession = get_dbsession(kwargs['config_path'])
        mylogger.debug('FOX got dbsession')
        mylogger.debug(dbsession)
        phonology = dbsession.query(
            old_models.Phonology).get(kwargs['phonology_id'])
        mylogger.debug('FOX got phonology')
        mylogger.debug(phonology)
        phonology.compile(kwargs['timeout'])
        mylogger.debug('FOX compiled')
        phonology.datetime_modified = h.now()
        phonology.modifier_id = kwargs['user_id']
        #transaction.commit()
        dbsession.flush()
        mylogger.debug('FOX committed to db')


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
    morphology = kwargs['dbsession'].query(
        old_models.Morphology).get(kwargs['morphology_id'])
    try:
        morphology.write(oldc.UNKNOWN_CATEGORY)
    except Exception as error:
        LOGGER.warning(error)
    if kwargs.get('compile', True):
        try:
            morphology.compile(kwargs['timeout'])
        except Exception as error:
            LOGGER.warning(error)
    morphology.generate_attempt = str(uuid4())
    morphology.modifier_id = kwargs['user_id']
    morphology.datetime_modified = h.now()
    kwargs['dbsession'].flush()


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
    langmod = kwargs['dbsession'].query(
        old_models.MorphemeLanguageModel).get(
            kwargs['morpheme_language_model_id'])
    trie_path = langmod.get_file_path('trie')
    trie_mod_time = langmod.get_modification_time(trie_path)
    langmod.generate_succeeded = False
    try:
        langmod.write_corpus()
    except Exception as error:
        langmod.generate_message = 'Error writing the corpus file. %s' % error
    try:
        langmod.write_vocabulary()
    except Exception as error:
        langmod.generate_message = 'Error writing the vocabulary file. %s' % error
    try:
        langmod.write_arpa(kwargs['timeout'])
    except Exception as error:
        langmod.generate_message = 'Error writing the ARPA file. %s' % error
    try:
        langmod.generate_trie()
    except Exception as error:
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
    kwargs['dbsession'].flush()


def compute_perplexity(**kwargs):
    """Evaluate the LM by attempting to calculate its perplexity and changing
    some attribute values to reflect the attempt.
    """
    langmod = kwargs['dbsession'].query(
        old_models.MorphemeLanguageModel).get(
            kwargs['morpheme_language_model_id'])
    timeout = kwargs['timeout']
    iterations = 5
    try:
        langmod.perplexity = langmod.compute_perplexity(timeout, iterations)
    except Exception:
        langmod.perplexity = None
    if langmod.perplexity is None:
        langmod.perplexity_computed = False
    else:
        langmod.perplexity_computed = True
    langmod.perplexity_attempt = str(uuid4())
    langmod.modifier_id = kwargs['user_id']
    langmod.datetime_modified = h.now()
    kwargs['dbsession'].flush()


################################################################################
# MORPHOLOGICAL PARSER (MORPHOPHONOLOGY)
################################################################################


def generate_and_compile_parser(**kwargs):
    """Write the parser's morphophonology FST script to file and compile it if
    ``compile_`` is True.  Generate the language model and pickle it.
    """
    parser = kwargs['dbsession'].query(old_models.MorphologicalParser).get(
        kwargs['morphological_parser_id'])
    parser.changed = False
    parser.write()
    if kwargs.get('compile', True):
        parser.compile(kwargs['timeout'])
    parser.modifier_id = kwargs['user_id']
    parser.datetime_modified = h.now()
    if parser.changed:
        parser.cache.clear(persist=True)
    kwargs['dbsession'].flush()
