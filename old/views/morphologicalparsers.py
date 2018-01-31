import codecs
import json
import logging
import os
import pickle
from uuid import uuid4

from formencode.validators import Invalid
from pyramid.response import FileResponse

from old import db_session_factory_registry
import old.lib.constants as oldc
from old.lib.foma_worker import FOMA_WORKER_Q
import old.lib.helpers as h
from old.lib.schemata import (
    TranscriptionsSchema,
    MorphemeSequencesSchema
)
from old.models import MorphologicalParserBackup
from old.models.morphologicalparser import Cache
from old.views.resources import Resources


LOGGER = logging.getLogger(__name__)


def session_getter(settings):
    return db_session_factory_registry.get_session(settings)()


class Morphologicalparsers(Resources):

    def __init__(self, request):
        self.model_name = 'MorphologicalParser'
        self.collection_name = 'morphological_parsers'
        self.hmn_collection_name = 'morphological parsers'
        self.member_name = 'morphological_parser'
        self.hmn_member_name = 'morphological parser'
        super().__init__(request)

    def show(self):
        """Morphological parsers have a special ``show``:
        :GET param str script: if set to '1', the script will be returned with
            the morphological parser
        """
        LOGGER.info('Attempting to read a single morphological parser')
        morphparser, id_ = self._model_from_id(eager=True)
        if not morphparser:
            self.request.response.status_int = 404
            msg = self._rsrc_not_exist(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if self._model_access_unauth(morphparser) is not False:
            self.request.response.status_int = 403
            LOGGER.warning(oldc.UNAUTHORIZED_MSG)
            return oldc.UNAUTHORIZED_MSG
        morphparser_dict = morphparser.get_dict()
        if self.request.GET.get('script') == '1':
            morphparser_dir_path = h.get_model_directory_path(
                morphparser, self.request.registry.settings)
            morphparser_script_path = h.get_model_file_path(
                morphparser, morphparser_dir_path, file_type='script')
            if os.path.isfile(morphparser_script_path):
                morphparser_dict['script'] = codecs.open(
                    morphparser_script_path, mode='r', encoding='utf8').read()
            else:
                morphparser_dict['script'] = ''
        LOGGER.info('Reading morphological parser %d', id_)
        return morphparser_dict

    def generate_and_compile(self):
        """Generate the morphological parser's morphophonology script and
        compile it as a foma FST.

        :URL: ``PUT /morphologicalparsers/generate_and_compile/id``
        :param str id: the ``id`` value of the morphologicalparser whose script
            will be compiled.
        :returns: if the morphological parser exists and foma is installed, the
            morphological parser model is returned;  ``GET
            /morphologicalparsers/id`` must be polled to determine when and how
            the compilation task has terminated.
        .. note::
            The script is compiled asynchronously in a worker thread.  See
            :mod:`onlinelinguisticdatabase.lib.foma_worker`.
        """
        LOGGER.info('Attempting to generate and compile a morphological parser.')
        return self._generate_and_compile_morphparser()

    def generate(self):
        """Generate the morphological parser's morphophonology script but do
        not compile it.

        :URL: ``PUT /morphologicalparsers/generate/id``
        :param str id: the ``id`` value of the morphological parser whose
            script will be compiled.
        :returns: if the morphological parser exists and foma is installed, the
            morphological parser model is returned;  ``GET
            /morphologicalparsers/id`` must be polled to determine when the
            generation task has terminated.
        """
        LOGGER.info('Attempting to generate a morphological parser.')
        return self._generate_and_compile_morphparser(compile_=False)

    def applydown(self):
        """Call foma apply down on the input in the request body using a
        morphological parser.

        :URL: ``PUT /morphologicalparsers/applydown/id``
        :param str id: the ``id`` value of the morphological parser that will
            be used.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphological parser exists and foma is installed, a
            JSON object of the form ``{t1: [p1t1, p2t1, ...], ...}`` where
            ``t1`` is a transcription from the request body and ``p1t1``,
            ``p2t1``, etc. are outputs of ``t1`` after apply down.
        """
        LOGGER.info('Attempting to call apply down against a morphological'
                    ' parser.')
        return self._apply('down')

    def applyup(self):
        """Call foma apply up on the input in the request body using a
        morphological parser.

        :URL: ``PUT /morphologicalparsers/applyup/id``
        :param str id: the ``id`` value of the morphological parser that will
            be used.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphological parser exists and foma is installed, a
            JSON object of the form ``{t1: [p1t1, p2t1, ...], ...}`` where
            ``t1`` is a transcription from the request body and ``p1t1``,
            ``p2t1``, etc. are outputs of ``t1`` after apply up.
        """
        LOGGER.info('Attempting to call apply up against a morphological'
                    ' parser.')
        return self._apply('up')

    def parse(self):
        """Parse the input word transcriptions using the morphological parser
        with id=``id``.
        :param str id: the ``id`` value of the morphological parser that will
            be used.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphological parser exists and foma is installed, a
            JSON object of the form ``{t1: p1, t2: p2, ...}`` where ``t1`` and
            ``t2`` are transcriptions of words from the request body and ``p1``
            and ``p2`` are the most probable morphological parsers of t1 and t2.
        """
        morphparser, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to call parse against morphological parser %d',
                    id_)
        if not morphparser:
            self.request.response.status_int = 404
            msg = 'There is no morphological parser with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            inputs = json.loads(self.request.body.decode(self.request.charset))
            morphparser.cache = Cache(
                morphparser,
                self.request.registry.settings,
                session_getter
            )
            LOGGER.warning(
                [h.normalize(w) for w in
                 TranscriptionsSchema.to_python(inputs)['transcriptions']])
            parses = morphparser.parse(
                [h.normalize(w) for w in
                 TranscriptionsSchema.to_python(inputs)['transcriptions']])
            # TODO: allow for a param which causes the candidates to be
            # returned as well as/instead of only the most probable parse
            # candidate.
            LOGGER.info('Called parse against morphological parser %d', id_)
            return {transcription: parse for transcription, (parse, candidates)
                    in parses.items()}
        except ValueError:
            self.request.response.status_int = 400
            LOGGER.warning(oldc.JSONDecodeErrorResponse)
            return oldc.JSONDecodeErrorResponse
        except Invalid as error:
            self.request.response.status_int = 400
            errors = error.unpack_errors()
            LOGGER.warning(errors)
            return {'errors': errors}
        except Exception as error:
            self.request.response.status_int = 400
            msg = 'Parse request raised an error.'
            LOGGER.warning(msg, exc_info=True)
            return {'error': msg}

    def servecompiled(self):
        """Serve the compiled foma script of the morphophonology FST of the
        morphological parser.
        :URL: ``PUT /morphologicalparsers/servecompiled/id``
        :param str id: the ``id`` value of a morphological parser.
        :returns: a stream of bytes -- the compiled morphological parser
            script.
        """
        morphparser, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to serve the compiled foma script of the'
                    ' morphophonology FST of morphological parser %d.', id_)
        if not morphparser:
            self.request.response.status_int = 404
            msg = 'There is no morphological parser with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        binary_path = morphparser.get_file_path('binary')
        if not os.path.isfile(binary_path):
            self.request.response.status_int = 400
            msg = ('The morphophonology foma script of MorphologicalParser {}'
                   ' has not been compiled yet.'.format(morphparser.id))
            LOGGER.warning(msg)
            return {'error': msg}
        LOGGER.info('Served the compiled foma script of the'
                    ' morphophonology FST of morphological parser %d.', id_)
        return FileResponse(
            binary_path,
            request=self.request)

    def export(self):
        """Export the parser as a self-contained .zip archive including a
        Python interface and all required files.
        This allows a user to use the parser locally (assuming they have foma
        and MITLM installed) via the following procedure::
            $ unzip archive.zip
            $ cd archive
            $ ./parse.py chiens chats tombait
        """
        morphparser, id_ = self._model_from_id(eager=True)
        LOGGER.info('Attempting to serve the morphological parser %d as a .zip'
                    ' archive.', id_)
        if not morphparser:
            self.request.response.status_int = 404
            msg = 'There is no morphological parser with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            morphparser.cache = Cache(
                morphparser,
                self.request.registry.settings,
                session_getter
            )
            directory = morphparser.directory
            lib_path = os.path.abspath(os.path.dirname(h.__file__))
            # config.pickle is a dict used to construct the parser (see
            # lib/parse.py)
            config_ = morphparser.export()
            config_path = os.path.join(directory, 'config.pickle')
            with open(config_path, 'wb') as dfile:
                pickle.dump(config_, dfile)
            # cache.pickle is a dict encoding the cached parses of this parser
            cache_dict = morphparser.cache.export()
            cache_path = os.path.join(directory, 'cache.pickle')
            with open(cache_path, 'wb') as dfile:
                pickle.dump(cache_dict, dfile)
            # create the .zip archive, including the files of the parser, the
            # simplelm package, the parser.py module and the parse.py
            # executable.
            zip_path = os.path.join(directory, 'archive.zip')
            zip_file = h.ZipFile(zip_path, 'w')
            for file_name in os.listdir(directory):
                if (    os.path.splitext(file_name)[1] not in
                        ('.log', '.sh', '.zip') and
                        file_name != 'morpheme_language_model.pickle'):
                    zip_file.write_file(os.path.join(directory, file_name))
            zip_file.write_directory(
                os.path.join(lib_path, 'simplelm'),
                keep_dir=True)
            zip_file.write_file(os.path.join(lib_path, 'parser.py'))
            zip_file.write_file(os.path.join(lib_path, 'parse.py'))
            zip_file.close()
            LOGGER.info('Served the morphological parser %d as a .zip'
                        ' archive.', id_)
            return FileResponse(
                zip_path,
                request=self.request)
        except Exception as error:
            self.request.response.status_int = 400
            msg = ('An error occured while attempting to export morphological'
                   ' parser {}: {}'.format(id_, error))
            LOGGER.warning(msg, exc_info=True)
            return {'error': msg}

    def _apply(self, direction):
        """Call foma apply in the direction of ``direction`` on the input in
        the request body using a morphological parser.
        :param str id: the ``id`` value of the morphological parser that will
            be used.
        :param str direction: the direction of foma application.
        :Request body: JSON object of the form
            ``{'transcriptions': [t1, t2, ...]}``.
        :returns: if the morphological parser exists and foma is installed, a
            JSON object of the form ``{t1: [p1t1, p2t1, ...], ...}`` where
            ``t1`` is a transcription from the request body and ``p1t1``,
            ``p2t1``, etc. are outputs of ``t1`` after apply up/down.
        """
        morphparser, id_ = self._model_from_id(eager=True)
        if not morphparser:
            self.request.response.status_int = 404
            msg = 'There is no morphological parser with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        binary_path = morphparser.get_file_path('binary')
        if not os.path.isfile(binary_path):
            self.request.response.status_int = 400
            msg = ('The morphophonology foma script of MorphologicalParser {}'
                   ' has not been compiled yet.'.format(morphparser.id))
            LOGGER.warning(msg)
            return {'error': msg}
        try:
            inputs = json.loads(self.request.body.decode(self.request.charset))
            schema, key = {
                'up': (TranscriptionsSchema, 'transcriptions'),
                'down': (MorphemeSequencesSchema, 'morpheme_sequences')
            }.get(direction, (MorphemeSequencesSchema, 'morpheme_sequences'))
            inputs = schema.to_python(inputs)
            ret = morphparser.apply(direction, inputs[key])
            LOGGER.info('Completed apply call against morphological parser'
                        ' %d.', id_)
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

    def _generate_and_compile_morphparser(self, compile_=True):
        morphparser, id_ = self._model_from_id(eager=True)
        if not morphparser:
            self.request.response.status_int = 404
            msg = 'There is no morphological parser with id {}'.format(id_)
            LOGGER.warning(msg)
            return {'error': msg}
        if compile_ and not h.foma_installed():
            self.request.response.status_int = 400
            msg = 'Foma and flookup are not installed.'
            LOGGER.warning(msg)
            return {'error': msg}
        FOMA_WORKER_Q.put({
            'id': h.generate_salt(),
            'func': 'generate_and_compile_parser',
            'args': {
                'morphological_parser_id': morphparser.id,
                'compile': compile_,
                'user_id': self.logged_in_user.id,
                'timeout': oldc.MORPHOLOGICAL_PARSER_COMPILE_TIMEOUT,
                'config_path': self.request.registry.settings['__file__'],
                'settings': self.request.registry.settings
            }
        })
        LOGGER.info('Added generation (and possible compilation) of'
                    ' morphological parser %d to the foma worker queue.', id_)
        return morphparser

    def _post_create(self, parser):
        parser.make_directory_safely(parser.directory)

    def _post_delete(self, parser):
        parser.remove_directory()

    def _get_user_data(self, data):
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
            'phonology': data['phonology'],
            'morphology': data['morphology'],
            'language_model': data['language_model']
        }

    def _get_create_data(self, data):
        user_data = self._get_user_data(data)
        now = h.now()
        user_model = self.logged_in_user
        user_data.update({
            'parent_directory': h.get_old_directory_path(
                'morphologicalparsers', self.request.registry.settings),
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

    def _backup_resource(self, morphological_parser_dict):
        morphological_parser_backup = MorphologicalParserBackup()
        morphological_parser_backup.vivify(morphological_parser_dict)
        self.request.dbsession.add(morphological_parser_backup)

    def _get_new_edit_collections(self):
        return (
            'morpheme_language_models',
            'phonologies',
            'morphologies'
        )
