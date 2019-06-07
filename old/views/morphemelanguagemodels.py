import json
import logging
import os
from uuid import uuid4

from formencode.validators import Invalid
from pyramid.response import FileResponse

import old.lib.constants as oldc
from old.lib.foma_worker import FOMA_WORKER_Q
import old.lib.helpers as h
from old.lib.schemata import MorphemeSequencesSchema
from old.models import MorphemeLanguageModelBackup
from old.views.resources import Resources


LOGGER = logging.getLogger(__name__)


class Morphemelanguagemodels(Resources):

    def __init__(self, request):
        self.model_name = 'MorphemeLanguageModel'
        self.collection_name = 'morpheme_language_models'
        self.hmn_collection_name = 'morpheme language models'
        self.member_name = 'morpheme_language_model'
        self.hmn_member_name = 'morpheme language model'
        super().__init__(request)

    def generate(self):
        """Generate the files that constitute the morpheme language model,
        crucially the file that holds the pickled LM trie.
        :URL: ``PUT /morpheme_language_model/id/generate``
        :param str id: the ``id`` value of the morpheme language model whose
            files will be generated.
        :returns: the morpheme language model is returned;  ``GET
            /morpheme_language_model/id`` must be polled to determine when the
            generation task has terminated.
        """
        langmod, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to generate morpheme language model %s.', id_)
        if not langmod:
            self.request.response.status_int = 404
            msg = 'There is no morpheme language model with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        args = {
            'morpheme_language_model_id': langmod.id,
            'user_id': self.logged_in_user.id,
            'timeout': oldc.MORPHEME_LANGUAGE_MODEL_GENERATE_TIMEOUT,
            'settings': self.request.registry.settings
        }
        FOMA_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'generate_language_model',
            'args': args
        })
        LOGGER.info('Added generation of morpheme language model %d to the foma'
                    ' worker queue.', id_)
        return langmod

    def get_probabilities(self):
        """Return the probability of each sequence of morphemes passed in the
        JSON PUT params.
        :param list morpheme_sequences: space-delimited morphemes in
            form|gloss|category format wherer "|" is actually
            ``h.rare_delimiter``.
        :returns: a dictionary with morpheme sequences as keys and log
            probabilities as values.
        """
        langmod, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to get probabilities from morpheme language'
                    ' model %s.', id_)
        if not langmod:
            self.request.response.status_int = 404
            msg = 'There is no morpheme language model with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            schema = MorphemeSequencesSchema()
            values = json.loads(self.request.body.decode(self.request.charset))
            data = schema.to_python(values)
            morpheme_sequences = [
                h.normalize(ms) for ms in data['morpheme_sequences']]
            ret = langmod.get_probabilities(morpheme_sequences)
            LOGGER.info('Returned probabilities from morpheme language'
                        ' model %s.', id_)
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
        except Exception:
            self.request.response.status_int = 400
            msg = 'An error occurred while trying to generate probabilities.'
            LOGGER.exception(msg)
            return {'error': msg}

    def compute_perplexity(self):
        """Compute the perplexity of the LM's corpus according to the LM.
        Randomly divide the corpus into training and test sets multiple times
        and compute the perplexity and return the average.  See
        ``evaluate_morpheme_language_model`` in lib/foma_worker.py.
        """
        langmod, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to compute the perplexity of morpheme language'
                    ' model %s.', id_)
        if not langmod:
            self.request.response.status_int = 404
            msg = 'There is no morpheme language model with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        args = {
            'morpheme_language_model_id': langmod.id,
            'user_id': self.logged_in_user.id,
            'timeout': oldc.MORPHEME_LANGUAGE_MODEL_GENERATE_TIMEOUT,
            'settings': self.request.registry.settings
        }
        FOMA_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'compute_perplexity',
            'args': args
        })
        LOGGER.info('Added computation of perplexity of morpheme language model'
                    ' %d to the foma worker queue.', id_)
        return langmod

    def serve_arpa(self):
        """Serve the generated ARPA file of the morpheme language model.
        :URL: ``PUT /morphemelanguagemodels/serve_arpa/id``
        :param str id: the ``id`` value of a morpheme language model.
        :returns: a stream of bytes -- the ARPA file of the LM.
        """
        langmod, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to serve the ARPA file of morpheme language'
                    ' model %s.', id_)
        if not langmod:
            self.request.response.status_int = 404
            msg = 'There is no morpheme language model with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        arpa_path = langmod.get_file_path('arpa')
        if not os.path.isfile(arpa_path):
            self.request.response.status_int = 404
            msg = ('The ARPA file for morpheme language model {} has not been'
                   ' compiled yet.'.format(id_))
            LOGGER.warning(msg)
            return {'error': msg}
        if not self._authorized_to_access_arpa_file(langmod):
            self.request.response.status_int = 403
            LOGGER.warning(oldc.UNAUTHORIZED_MSG)
            return oldc.UNAUTHORIZED_MSG
        LOGGER.info('Served the ARPA file of morpheme language'
                    ' model %s.', id_)
        return FileResponse(
            arpa_path,
            request=self.request,
            content_type='text/plain')

    def _authorized_to_access_arpa_file(self, langmod):
        """Return True if user is authorized to access the ARPA file of the
        morpheme LM.
        """
        if self.logged_in_user.role == 'administrator':
            return True
        if not langmod.restricted:
            return True
        if self.logged_in_user in self.db.get_unrestricted_users():
            return True
        return False

    def _post_create(self, langmod):
        langmod.make_directory_safely(langmod.directory)

    def _post_delete(self, langmod):
        langmod.remove_directory()

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
            'vocabulary_morphology': data['vocabulary_morphology'],
            'corpus': data['corpus'],
            'toolkit': data['toolkit'],
            'order': data['order'],
            'smoothing': data['smoothing'],
            'categorial': data['categorial']
        }

    def _get_create_data(self, data):
        user_data = self._get_user_data(data)
        now = h.now()
        user_model = self.logged_in_user
        user_data.update({
            'parent_directory': h.get_old_directory_path(
                'morphemelanguagemodels', self.request.registry.settings),
            'rare_delimiter': oldc.RARE_DELIMITER,
            'start_symbol': oldc.LM_START,
            'end_symbol': oldc.LM_END,
            'morpheme_delimiters': self.db.get_morpheme_delimiters(
                type_='str'),
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

    def _backup_resource(self, langmod_dict):
        """Backup a morpheme language model.
        :param dict langmod_dict: a representation of a morpheme language model
            model.
        :returns: ``None``
        """
        langmod_backup = MorphemeLanguageModelBackup()
        langmod_backup.vivify(langmod_dict)
        self.request.dbsession.add(langmod_backup)

    def _get_new_edit_collections(self):
        return (
            'corpora',
            'morphologies',
            'toolkits',
        )

    def _get_mandatory_collections(self):
        return ('toolkits',)
