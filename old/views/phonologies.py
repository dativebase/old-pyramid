import json
import logging
import os
from uuid import uuid4

from formencode.validators import Invalid
from pyramid.response import FileResponse

import old.lib.constants as oldc
from old.lib.foma_worker import FOMA_WORKER_Q
import old.lib.helpers as h
from old.lib.schemata import MorphophonemicTranscriptionsSchema
from old.models import PhonologyBackup
from old.views.resources import Resources


LOGGER = logging.getLogger(__name__)


class Phonologies(Resources):

    def compile(self):
        """Compile the script of a phonology as a foma FST.
        :URL: ``PUT /phonologies/compile/id``
        :param str id: the ``id`` value of the phonology whose script will be compiled.
        :returns: if the phonology exists and foma is installed, the phonology
            model is returned;  ``GET /phonologies/id`` must be polled to
            determine when and how the compilation task has terminated.
        .. note::
            The script is compiled asynchronously in a worker thread. See
            :mod:`onlinelinguisticdatabase.lib.foma_worker`.
        """
        phonology, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to compile phonology %d', id_)
        if self.request.registry.settings.get('readonly') == '1':
            LOGGER.warning('Attempt to compile a phonology in read-only mode')
            self.request.response.status_int = 403
            return oldc.READONLY_MODE_MSG
        if not phonology:
            self.request.response.status_int = 404
            msg = 'There is no phonology with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        FOMA_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'compile_phonology',
            'args': {
                'phonology_id': phonology.id,
                'user_id': self.logged_in_user.id,
                'timeout': oldc.PHONOLOGY_COMPILE_TIMEOUT,
                'settings': self.request.registry.settings
            }
        })
        LOGGER.info('Added compilation of phonolgy %d to the foma worker'
                    ' queue.', id_)
        return phonology

    def servecompiled(self):
        """Serve the compiled foma script of the phonology.
        :URL: ``PUT /phonologies/servecompiled/id``
        :param str id: the ``id`` value of a phonology.
        :returns: a stream of bytes -- the compiled phonology script.
        """
        phonology, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to serve the compiled phonology %d', id_)
        if not phonology:
            self.request.response.status_int = 404
            msg = 'There is no phonology with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        compiled_path = phonology.get_file_path('binary')
        if not os.path.isfile(compiled_path):
            self.request.response.status_int = 400
            msg = 'Phonology {} has not been compiled yet.'.format(phonology.id)
            LOGGER.warning(msg)
            return {'error': msg}
        LOGGER.info('Served the compiled phonology %d', id_)
        return FileResponse(
            compiled_path,
            request=self.request)

    def applydown(self):
        """Apply-down (i.e., phonologize) the input in the request body using a
        phonology.
        :URL: ``PUT /phonologies/applydown/id`` (or ``PUT
            /phonologies/phonologize/id``)
        :param str id: the ``id`` value of the phonology that will be used.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the phonology exists and foma is installed, a JSON object
            of the form ``{t1: [p1t1, p2t1, ...], ...}`` where ``t1`` is a
            transcription from the request body and ``p1t1``, ``p2t1``, etc. are
            phonologized outputs of ``t1``.
        """
        phonology, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to call apply down on the compiled phonology'
                    ' %d', id_)
        if not phonology:
            self.request.response.status_int = 404
            msg = 'There is no phonology with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        binary_path = phonology.get_file_path('binary')
        if not os.path.isfile(binary_path):
            self.request.response.status_int = 400
            msg = 'Phonology {} has not been compiled yet.'.format(phonology.id)
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            inputs = json.loads(self.request.body.decode(self.request.charset))
            inputs = MorphophonemicTranscriptionsSchema.to_python(inputs)
            inputs = [h.normalize(i) for i in inputs['transcriptions']]
            ret = phonology.applydown(inputs)
            LOGGER.info('Called apply down on the compiled phonology %d', id_)
            return ret
        except ValueError:
            self.request.response.status_int = 400
            LOGGER.warning(oldc.JSONDecodeErrorResponse)
            return oldc.JSONDecodeErrorResponse
        except Invalid as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}

    def runtests(self):
        """Run the tests defined in the phonology's script against the phonology.
        A line in a phonology's script that begins with "#test" signifies a
        test.  After "#test" there should be a string of characters followed by
        "->" followed by another string of characters.  The first string is the
        underlying representation and the second is the anticipated surface
        representation.  Requests to ``GET /phonologies/runtests/id`` will cause
        the OLD to run a phonology script against its tests and return a
        dictionary detailing the expected and actual outputs of each input in
        the transcription.
        :URL: ``GET /phonologies/runtests/id``
        :param str id: the ``id`` value of the phonology that will be tested.
        :returns: if the phonology exists and foma is installed, a JSON object
            representing the results of the test.
        """
        phonology, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to run the tests defined in the compiled'
                    ' phonology %d', id_)
        if not phonology:
            self.request.response.status_int = 404
            msg = 'There is no phonology with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            test_results = phonology.run_tests()
            if test_results:
                LOGGER.info('Ran the tests defined in the compiled phonology'
                            ' %d', id_)
                return test_results
            self.request.response.status_int = 400
            msg = 'The script of phonology {} contains no tests.'.format(
                phonology.id)
            LOGGER.warning(msg)
            return {'error': msg}
        except AttributeError:
            self.request.response.status_int = 400
            msg = 'Phonology {} has not been compiled yet.'.format(phonology.id)
            LOGGER.warning(msg)
            return {'error': msg}

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
            'script': h.normalize(data['script']).replace(u'\r', u'')
        }

    def _get_create_data(self, data):
        user_data = self._get_user_data(data)
        now = h.now()
        user_model = self.logged_in_user
        user_data.update({
            'parent_directory': h.get_old_directory_path(
                'phonologies', self.request.registry.settings),
            # TODO: the Pylons app implied that this constant could change...
            'word_boundary_symbol': oldc.WORD_BOUNDARY_SYMBOL,
            'UUID': str(uuid4()),
            'enterer': user_model,
            'modifier': user_model,
            'datetime_modified': now,
            'datetime_entered': now
        })
        return user_data

    def _get_update_data(self, user_data):
        now = h.now()
        user_model = self.logged_in_user
        user_data.update({
            'datetime_modified': now,
            'modifier': user_model
        })
        return user_data

    def _backup_resource(self, phonology_dict):
        phonology_backup = PhonologyBackup()
        phonology_backup.vivify(phonology_dict)
        self.request.dbsession.add(phonology_backup)

    def _post_create(self, resource_model):
        # ``decombine`` means separate unicode combining characters from their
        # bases
        resource_model.save_script(decombine=True)

    def _post_update(self, phonology, prev_phonology_dict):
        # Note: the Pylons version was not passing ``True`` in the decombine
        # param here. Why the inconsistency?
        phonology.save_script(decombine=True)

    def _post_delete(self, phonology):
        phonology.remove_directory()
