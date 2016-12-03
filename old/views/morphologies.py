import codecs
import json
import os
import pickle
from uuid import uuid4

from formencode.validators import Invalid
from pyramid.response import FileResponse

from old.models import MorphologyBackup
from old.lib.foma_worker import FOMA_WORKER_Q
import old.lib.helpers as h
import old.lib.constants as oldc
from old.lib.schemata import MorphemeSequencesSchema
from old.views.resources import Resources


class Morphologies(Resources):

    def show(self):
        """Morphologies have a special ``show``:
        :GET param str script: if set to '1', the script will be returned with
            the morphology
        :GET param str lexicon: if set to '1', the lexicon (dict) will be
            returned with the morphology
        """
        morphology, id_ = self._model_from_id(eager=True)
        if not morphology:
            self.request.response.status_int = 404
            return {'error': self._rsrc_not_exist(id_)}
        if self._model_access_unauth(morphology) is not False:
            self.request.response.status_int = 403
            return oldc.UNAUTHORIZED_MSG
        morphology_dict = morphology.get_dict()
        if self.request.GET.get('script') == '1':
            morphology_script_path = morphology.get_file_path('script')
            if os.path.isfile(morphology_script_path):
                morphology_dict['script'] = codecs.open(
                    morphology_script_path, mode='r', encoding='utf8').read()
            else:
                morphology_dict['script'] = ''
        if self.request.GET.get('lexicon') == '1':
            morphology_lexicon_path = morphology.get_file_path('lexicon')
            if os.path.isfile(morphology_lexicon_path):
                morphology_dict['lexicon'] = pickle.load(
                    open(morphology_lexicon_path, 'rb'))
            else:
                morphology_dict['lexicon'] = {}
        return morphology_dict

    def generate_and_compile(self):
        """Generate the morphology's script and compile it as a foma FST.
        :URL: ``PUT /morphologies/<id>/generate_and_compile``
        :param str id: the ``id`` value of the morphology whose script will be
            compiled.
        :returns: if the morphology exists and foma is installed, the morphology
            model is returned;  ``GET /morphologies/id`` must be polled to
            determine when and how the compilation task has terminated.
        .. note::
            The script is compiled asynchronously in a worker thread. See
            :mod:`old.lib.foma_worker`.
        """
        return self.generate_and_compile_morphology()

    def generate(self):
        """Generate the morphology's script -- do not compile it.
        :URL: ``PUT /morphologies/compile/id``
        :param str id: the ``id`` value of the morphology whose script will be
            compiled.
        :returns: if the morphology exists and foma is installed, the morphology
            model is returned;  ``GET /morphologies/id`` must be polled to
            determine when the generation task has terminated.
        """
        return self.generate_and_compile_morphology(compile_=False)

    def generate_and_compile_morphology(self, compile_=True):
        morphology, id_ = self._model_from_id(eager=True)
        if not morphology:
            self.request.response.status_int = 404
            return {'error': 'There is no morphology with id %s' % id}
        if compile_ and not h.foma_installed():
            self.request.response.status_int = 400
            return {'error': 'Foma and flookup are not installed.'}
        FOMA_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'generate_and_compile_morphology',
            'args': {
                'morphology_id': morphology.id,
                'compile': compile_,
                'user_id': self.logged_in_user.id,
                'timeout': oldc.MORPHOLOGY_COMPILE_TIMEOUT,
                'config_path': self.request.registry.settings['__file__'],
            }
        })
        return morphology

    def servecompiled(self):
        """Serve the compiled foma script of the morphology.
        :URL: ``PUT /morphologies/servecompiled/id``
        :param str id: the ``id`` value of a morphology.
        :returns: a stream of bytes -- the compiled morphology script.
        """
        morphology, id_ = self._model_from_id(eager=True)
        if not morphology:
            self.request.response.status_int = 404
            return {'error': 'There is no morphology with id %s' % id_}
        if not h.foma_installed():
            self.request.response.status_int = 400
            return {'error': 'Foma and flookup are not installed.'}
        compiled_path = morphology.get_file_path('binary')
        if not os.path.isfile(compiled_path):
            self.request.response.status_int = 400
            return {'error': 'Morphology %d has not been compiled yet.' % (
                morphology.id,)}
        return FileResponse(
            compiled_path,
            request=self.request)
        # content_type=content_type)  TODO: what is content type?

    def applydown(self):
        """Call foma apply down on the input in the request body using a
        morphology.
        :URL: ``PUT /morphologies/applydown/id``
        :param str id: the ``id`` value of the morphology that will be used.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphology exists and foma is installed, a JSON object
            of the form ``{t1: [p1t1, p2t1, ...], ...}`` where ``t1`` is a
            transcription from the request body and ``p1t1``, ``p2t1``, etc. are
            outputs of ``t1`` after apply down.
        """
        return self.apply('down')

    def applyup(self):
        """Call foma apply up on the input in the request body using a
        morphology.
        :URL: ``PUT /morphologies/applyup/id``
        :param str id: the ``id`` value of the morphology that will be used.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphology exists and foma is installed, a JSON object
            of the form ``{t1: [p1t1, p2t1, ...], ...}`` where ``t1`` is a
            transcription from the request body and ``p1t1``, ``p2t1``, etc. are
            outputs of ``t1`` after apply up.
        """
        return self.apply('up')

    def apply(self, direction):
        """Call foma apply in the direction of ``direction`` on the input in
        the request body using a morphology.
        :param str id: the ``id`` value of the morphology that will be used.
        :param str direction: the direction of foma application.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphology exists and foma is installed, a JSON object
            of the form ``{t1: [p1t1, p2t1, ...], ...}`` where ``t1`` is a
            transcription from the request body and ``p1t1``, ``p2t1``, etc. are
            outputs of ``t1`` after apply up/down.
        """
        morphology, id_ = self._model_from_id(eager=True)
        if not morphology:
            self.request.response.status_int = 404
            return {'error': 'There is no morphology with id %s' % id_}
        if not h.foma_installed():
            self.request.response.status_int = 400
            return {'error': 'Foma and flookup are not installed.'}
        morphology_binary_path = morphology.get_file_path('binary')
        if not os.path.isfile(morphology_binary_path):
            self.request.response.status_int = 400
            return {'error': 'Morphology %d has not been compiled yet.' % (
                morphology.id,)}
        try:
            inputs = json.loads(self.request.body.decode(self.request.charset))
            inputs = MorphemeSequencesSchema.to_python(inputs)
            inputs = [h.normalize(i) for i in inputs['morpheme_sequences']]
            return morphology.apply(direction, inputs)
        except ValueError:
            self.request.response.status_int = 400
            return oldc.JSONDecodeErrorResponse
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}

    def _post_create(self, morphology):
        morphology.make_directory_safely(morphology.directory)

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
            'lexicon_corpus': data['lexicon_corpus'],
            'rules_corpus': data['rules_corpus'],
            'script_type': data['script_type'],
            'extract_morphemes_from_rules_corpus':
                data['extract_morphemes_from_rules_corpus'],
            'rules': data['rules'],
            'rich_upper': data['rich_upper'],
            'rich_lower': data['rich_lower'],
            'include_unknowns': data['include_unknowns']
        }

    def _get_create_data(self, data):
        user_data = self._get_user_data(data)
        now = h.now()
        user_model = self.logged_in_user
        user_data.update({
            'parent_directory': h.get_old_directory_path(
                'morphologies', self.request.registry.settings),
            # TODO: the Pylons app implied that this constant could change...
            'word_boundary_symbol': oldc.WORD_BOUNDARY_SYMBOL,
            'rare_delimiter': oldc.RARE_DELIMITER,
            'morpheme_delimiters': self.db.get_morpheme_delimiters(type_='str'),
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

    def _get_new_edit_collections(self):
        return ('corpora',)

    def _backup_resource(self, morphology_dict):
        morphology_backup = MorphologyBackup()
        morphology_backup.vivify(morphology_dict)
        self.request.dbsession.add(morphology_backup)

    def _post_delete(self, morphology):
        morphology.remove_directory()
