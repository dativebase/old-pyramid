"""Contains the :class:`CorporaController` and its auxiliary functions.

.. module:: corpora
   :synopsis: Contains the corpora controller and its auxiliary functions.
"""

import codecs
from collections import defaultdict
import datetime
import json
import logging
import os
from shutil import rmtree
from subprocess import call, Popen
from uuid import uuid4

from formencode.validators import Invalid
from pyramid.response import FileResponse

import old.lib.constants as oldc
from old.lib.dbutils import (
    add_pagination,
    eagerload_form,
    _filter_restricted_models_from_query,
)
import old.lib.helpers as h
from old.models import (
    Form,
    CorpusBackup
)
from old.models.corpus import CorpusFile
from old.lib.schemata import CorpusFormatSchema
from old.lib.SQLAQueryBuilder import SQLAQueryBuilder, OLDSearchParseError
from old.views.resources import (
    Resources,
    SchemaState
)


LOGGER = logging.getLogger(__name__)


class Corpora(Resources):
    """Expose the corpus resource. Corpora have a different search pattern as
    well as some special methods/API endpoints:

    - search: return the forms from corpus ``id`` that match the input JSON
        query.
    - new_search: return the data necessary to search across the form resources
        within the corpus.
    - search_corpora: return the list of corpora that match the input JSON
        query.
    - new_search_corpora: return the data necessary to search across corpus
        resources.
    - get_word_category_sequences: return the category sequence types of
        validly morphologically analyzed words in the corpus including the id
        exemplars of said types.
    - writetofile: write the corpus to a file in the format specified in the
        request body.
    - servefile: return the corpus as a file in the format specified in the URL
        query string.
    - tgrep2: search the corpus-as-treebank using Tgrep2.
    """

    def __init__(self, request):
        super().__init__(request)
        self._forms_query_builder = None

    @property
    def forms_query_builder(self):
        """Corpora have two SQLAQueryBuilder instance attributes: the
        super-class's one for searching across corpus resources and this one,
        for searching across the forms *within* a corpus.
        """
        if not self._forms_query_builder:
            self._forms_query_builder = SQLAQueryBuilder(
                self.request.dbsession,
                'Form',
                settings=self.request.registry.settings)
        return self._forms_query_builder

    ###########################################################################
    # View Callable Methods
    ###########################################################################

    def search_corpora(self):
        """Return the list of corpora that match the input JSON query.
        :URL: ``SEARCH/POST /corpora/searchcorpora``
        :request body: A JSON object of the form::

                {"query": {"filter": [ ... ], "order_by": [ ... ]},
                 "paginator": { ... }}

            where the ``order_by`` and ``paginator`` attributes are optional.
        .. note::

            This action *does* result in a search across corpora resources.
            Contrast this with the `search` method below which allows one to
            search across the forms in a specified corpus.
        """
        return super().search()

    def search(self):
        """Return the forms from corpus ``id`` that match the input JSON query.
        :param str id: the id value of the corpus to be searched.
        :URL: ``SEARCH /corpora/id` (or ``POST /corpora/id/search``)
        :request body: A JSON object of the form::

                {"query": {"filter": [ ... ], "order_by": [ ... ]},
                 "paginator": { ... }}

            where the ``order_by`` and ``paginator`` attributes are optional.
        .. note::

            The corpora search action is different from typical search actions
            in that it does not return an array of corpora but of forms that
            are in the corpus whose ``id`` value matches ``id``.  This action
            resembles the search action of the ``Rememberedforms`` view.
        """
        corpus, id_ = self._model_from_id(eager=True)
        if not corpus:
            self.request.response.status_int = 404
            return {'error': 'There is no corpus with id %s' % id_}
        if self._model_access_unauth(corpus) is not False:
            self.request.response.status_int = 403
            return oldc.UNAUTHORIZED_MSG
        try:
            python_search_params = json.loads(
                self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return oldc.JSONDecodeErrorResponse
        try:
            query = eagerload_form(
                self.forms_query_builder.get_SQLA_query(
                    python_search_params.get('query')))
        except (OLDSearchParseError, Invalid) as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}
        except Exception as error:  # FIX: too general exception
            LOGGER.warning('Filter expression %s raised an unexpected'
                           ' exception: %s.', self.request.body, error)
            self.request.response.status_int = 400
            return {'error': 'The specified search parameters generated an'
                             'invalid database query'}
        query = query.filter(Form.corpora.contains(corpus))
        user = self.logged_in_user
        if not self.db.user_is_unrestricted(user):
            query = _filter_restricted_models_from_query(
                'Form', query, user)
        return add_pagination(query, python_search_params.get('paginator'))

    def new_searchx(self):
        """Return the data necessary to search across the form resources within
        the corpus.
        """
        return {'search_parameters':
                self.forms_query_builder.get_search_parameters()}

    def new_search_corpora(self):
        """Return the data necessary to search across corpus resources.
        .. note::

            Contrast this action with `new_search`, which returns the data
            needed to search across the forms of a corpus.
        """
        return {'search_parameters':
                self.query_builder.get_search_parameters()}

    def get_word_category_sequences(self):
        """Return the category sequence types of validly morphologically
        analyzed words in the corpus with ``id``, including the id exemplars of
        said types.
        """
        corpus, id_ = self._model_from_id()
        if not corpus:
            self.request.response.status_int = 404
            return {'error': 'There is no corpus with id %s' % id_}
        word_category_sequences = self._get_word_category_sequences(corpus)
        minimum_token_count = int(
            self.request.GET.get('minimum_token_count', 0))
        if minimum_token_count:
            word_category_sequences = [
                (''.join(sequence), ids) for sequence, ids in
                word_category_sequences if len(ids) >= minimum_token_count]
        return word_category_sequences

    def writetofile(self):
        """Write the corpus to a file in the format specified in the request
        body.
        :URL: ``PUT /corpora/id/writetofile``
        :Request body: JSON object of the form ``{"format": "..."}.``
        :param str id: the ``id`` value of the corpus.
        :returns: the modified corpus model (or a JSON error message).
        """
        corpus, id_ = self._model_from_id()
        if not corpus:
            self.request.response.status_int = 404
            return {'error': 'There is no corpus with id %s' % id_}
        schema = CorpusFormatSchema
        try:
            values = json.loads(self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return oldc.JSONDecodeErrorResponse
        try:
            format_ = schema.to_python(values)['format']
        except Invalid as error:
            self.request.response.status_int = 400
            return {'errors': error.unpack_errors()}
        return self._write_to_file(corpus, format_)

    def servefile(self):
        """Return the corpus as a file in the format specified in the URL query
        string.
        :URL: ``PUT /corpora/id/servefile/file_id``.
        :param str id: the ``id`` value of the corpus.
        :param str file_id: the ``id`` value of the corpus file.
        :returns: the file data
        """
        corpus, id_ = self._model_from_id()
        file_id = self.request.matchdict['file_id']
        if not corpus:
            self.request.response.status_int = 404
            return {'error': 'There is no corpus with id %s' % id_}
        try:
            corpus_file = [cf for cf in corpus.files
                           if cf.id == int(file_id)][0]
            corpus_file_path = os.path.join(
                self._get_corpus_dir_path(corpus),
                '%s.gz' % corpus_file.filename)
            if not os.path.isfile(corpus_file_path):
                raise IndexError
        except IndexError:
            self.request.response.status_int = 400
            return {'error': 'Unable to serve corpus file %d of corpus %d' % (
                file_id, id)}
        if not self._authorized_to_access_corpus_file(corpus_file):
            self.request.response.status_int = 403
            return oldc.UNAUTHORIZED_MSG
        return FileResponse(
            corpus_file_path,
            request=self.request,
            content_type='application/x-gzip')

    def tgrep2(self):
        """Search the corpus-as-treebank using Tgrep2.
        :URL: ``SEARCH/POST /corpora/id/tgrep2``.
        :Request body: JSON object with obligatory 'tgrep2pattern' attribute and
            optional 'paginator' and 'order_by' attributes.
        :param str id: the ``id`` value of the corpus.
        :returns: an array of forms as JSON objects
        """
        if not h.command_line_program_installed('tgrep2'):
            self.request.response.status_int = 400
            return {'error': 'TGrep2 is not installed.'}
        corpus, id_ = self._model_from_id()
        if not corpus:
            self.request.response.status_int = 404
            return {'error': 'There is no corpus with id %s' % id_}
        try:
            tbk_corpus_file_obj = [cf for cf in corpus.files
                                   if cf.format == 'treebank'][0]
            corpus_dir_path = self._get_corpus_dir_path(corpus)
            tgrep2_corpus_file_path = os.path.join(
                corpus_dir_path, '%s.t2c' % tbk_corpus_file_obj.filename)
            if not os.path.isfile(tgrep2_corpus_file_path):
                raise IndexError
        except IndexError:
            self.request.response.status_int = 400
            return {'error': 'Corpus %d has not been written to file as a'
                             ' treebank.' % id_}
        try:
            request_params = json.loads(
                self.request.body.decode(self.request.charset))
        except ValueError:
            self.request.response.status_int = 400
            return oldc.JSONDecodeErrorResponse
        try:
            tgrep2pattern = request_params['tgrep2pattern']
            assert isinstance(tgrep2pattern, str)
        except (KeyError, AssertionError):
            self.request.response.status_int = 400
            return {
                'errors': {
                    'tgrep2pattern':
                        'A tgrep2pattern attribute must be supplied and must'
                        ' have a string value'}}
        tmp_path = os.path.join(
            corpus_dir_path,
            '%s%s.txt' % (self.logged_in_user.username, h.generate_salt()))
        with open(os.devnull, "w") as fnull:
            with open(tmp_path, 'w') as stdout:
                # The -wu option causes TGrep2 to print only the root symbol of
                # each matching tree
                process = Popen(['tgrep2', '-c', tgrep2_corpus_file_path,
                                 '-wu', tgrep2pattern],
                                stdout=stdout, stderr=fnull)
                process.communicate()
        match_ids = filter(None, map(_get_form_ids_from_tgrep2_output_line, open(tmp_path, 'r')))
        with open(tmp_path, 'r') as file_:
            match_ids = filter(None,
                               map(_get_form_ids_from_tgrep2_output_line, file_))
        os.remove(tmp_path)
        if match_ids:
            query = eagerload_form(
                self.request.dbsession.query(Form)).filter(
                    Form.id.in_(match_ids))
            user = self.logged_in_user
            if not self.db.user_is_unrestricted(user):
                query = _filter_restricted_models_from_query(
                    'Form', query, user)
            query = self.add_order_by(
                query, request_params.get('order_by'),
                query_builder=self.forms_query_builder)
            result = add_pagination(query, request_params.get('paginator'))
        elif request_params.get('paginator'):
            paginator = request_params['paginator']
            paginator['count'] = 0
            result = {'paginator': paginator, 'items': []}
        else:
            result = []
        return result

    ###########################################################################
    # Private Methods Overrides of Super-class (hooks)
    ###########################################################################

    def _get_new_edit_collections(self):
        """Returns the names of the collections that are required in order to
        create a new, or edit an existing, corpus.
        """
        return (
            'corpus_formats',  # mandatory: always all returned
            'form_searches',
            'tags',
            'users'
        )

    def _get_mandatory_collections(self):
        return ('corpus_formats',)

    def _get_user_data(self, data):
        """User-provided data for creating a corpus."""
        return {
            'name': h.normalize(data['name']),
            'description': h.normalize(data['description']),
            'content': data['content'],
            'form_search': data['form_search'],
            'forms': data['forms'],
            'tags': data['tags']
        }

    def _get_create_data(self, data):
        """Data needed to create a new corpus."""
        create_data = self._get_update_data(self._get_user_data(data))
        create_data['UUID'] = str(uuid4())
        create_data['enterer'] = create_data['modifier']
        create_data['datetime_entered'] = create_data['datetime_modified']
        return create_data

    def _get_update_data(self, user_data):
        """Data needed to update an existing corpus."""
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow(),
            'modifier': self.logged_in_user
        })
        return user_data

    def _distinct(self, attr, new_val, existing_val):
        """Returns true if new and existing vals of attr are distinct."""
        if attr in ('files', 'tags'):
            if set(new_val) == set(existing_val):
                return False
            return True
        else:
            return new_val != existing_val

    def _post_create(self, corpus):
        """Create the directory to hold the various forms of the corpus written
        to disk.
        :param corpus: a corpus model object.
        :returns: an absolute path to the directory for the corpus.
        """
        corpus_dir_path = self._get_corpus_dir_path(corpus)
        h.make_directory_safely(corpus_dir_path)

    def _post_delete(self, corpus):
        self._remove_corpus_directory(corpus)

    def _backup_resource(self, corpus_dict):
        """Perform a backup of the provided ``resource_dict``, if applicable."""
        corpus_backup = CorpusBackup()
        corpus_backup.vivify(corpus_dict)
        self.request.dbsession.add(corpus_backup)

    def _get_create_state(self, values):
        """Return a SchemaState instance for validation of the corpus during
        a create request.
        """
        return SchemaState(
            full_dict=values,
            db=self.db,
            logged_in_user=self.logged_in_user,
            settings=self.request.registry.settings)

    ###########################################################################
    # Corpus-specific Private Methods
    ###########################################################################

    def _authorized_to_access_corpus_file(self, corpus_file):
        """Return True if user is authorized to access the corpus file."""
        user = self.logged_in_user
        if (    corpus_file.restricted and
                user.role != 'administrator' and
                user not in self.db.get_unrestricted_users()):
            return False
        return True

    def _get_corpus_dir_path(self, corpus):
        return os.path.join(
            h.get_old_directory_path('corpora', self.request.registry.settings),
            'corpus_%d' % corpus.id)

    def _remove_corpus_directory(self, corpus):
        """Remove the directory of the corpus model and everything in it.
        :param corpus: a corpus model object.
        :returns: an absolute path to the directory for the corpus.
        """
        try:
            corpus_dir_path = self._get_corpus_dir_path(corpus)
            rmtree(corpus_dir_path)
            return corpus_dir_path
        except Exception:
            return None

    def _get_word_category_sequences(self, corpus):
        """Return the category sequence types of validly morphologically
        analyzed words in ``corpus`` as well as the exemplars ids of said
        types. This is useful for getting a sense of which word "templates" are
        common.
        :returns: a list of 2-tuples of the form
            [(category_sequence, [id1, id2, ...]), ...]
            ordered by the number of exemplar ids in the list that is the second
            member.
        """
        result = defaultdict(list)
        morpheme_splitter = self.db.get_morpheme_splitter()
        for form in corpus.forms:
            category_sequences, _ = form.extract_word_pos_sequences(
                oldc.UNKNOWN_CATEGORY, morpheme_splitter,
                extract_morphemes=False)
            if category_sequences:
                for category_sequence in category_sequences:
                    result[category_sequence].append(form.id)
        return sorted(result.items(), key=lambda t: len(t[1]), reverse=True)

    def _write_to_file(self, corpus, format_):
        """Write the corpus to file in the specified format.
        Write the corpus to a binary file, create or update a corpus file model
        and associate it to the corpus model (if necessary).
        :param corpus: a corpus model.
        :param str format_: the format of the file to be written.
        :returns: the corpus modified appropriately (assuming success)
        :side effects: may write (a) file(s) to disk and update/create a corpus
            file model.
        .. note::
            It may be desirable/necessary to perform the corpus file writing
            asynchronously using a dedicated corpus-file-worker.
        """
        def error_msg(msg):
            return {
                'error': 'Unable to write corpus %d to file with format "%s".'
                         ' (%s)' % (corpus.id, format_, msg)}
        def update_corpus_file(corpus, filename, modifier, datetime_modified,
                               restricted):
            """Update the corpus file model of ``corpus`` that matches
            ``filename``.
            """
            corpus_file = [cf for cf in corpus.files if
                           cf.filename == filename][0]
            corpus_file.restricted = restricted
            corpus_file.modifier = modifier
            corpus_file.datetime_modified = corpus.datetime_modified = \
                datetime_modified
        def generate_new_corpus_file(corpus, filename, format_, creator,
                                     datetime_created, restricted):
            """Create a corpus file model with ``filename`` and append it to
            ``corpus.files``.
            """
            corpus_file = CorpusFile()
            corpus_file.restricted = restricted
            corpus.files.append(corpus_file)
            corpus_file.filename = filename
            corpus_file.format = format_
            corpus_file.creator = corpus_file.modifier = creator
            corpus_file.datetime_created = corpus_file.datetime_modified = \
                datetime_created
            corpus.datetime_modified = datetime_created
        def destroy_file(file_path):
            try:
                rmtree(file_path)
            except Exception:
                pass
        corpus_file_path = self._get_corpus_file_path(corpus, format_)
        update = os.path.exists(corpus_file_path)  # If True, we are upating
        restricted = False
        # Create the corpus file on the filesystem
        try:
            writer = oldc.CORPUS_FORMATS[format_]['writer']
            if corpus.form_search:  # ``form_search`` value negates any content.
                with codecs.open(corpus_file_path, 'w', 'utf8') as file_:
                    for form in corpus.forms:
                        if (    not restricted and
                                'restricted' in [t.name for t in form.tags]):
                            restricted = True
                        file_.write(writer(form))
            else:
                form_references = corpus.get_form_references(corpus.content)
                forms = {f.id: f for f in corpus.forms}
                with codecs.open(corpus_file_path, 'w', 'utf8') as file_:
                    for id_ in form_references:
                        form = forms[id_]
                        if (    not restricted and
                                'restricted' in [t.name for t in form.tags]):
                            restricted = True
                        file_.write(writer(form))
            gzipped_corpus_file_path = h.compress_file(corpus_file_path)
            _create_tgrep2_corpus_file(gzipped_corpus_file_path, format_)
        except Exception as error:
            destroy_file(corpus_file_path)
            self.request.response.status_int = 400
            return error_msg(error)
        # Update/create the corpus_file object
        try:
            now = h.now()
            user = self.logged_in_user
            corpus_filename = os.path.split(corpus_file_path)[1]
            if update:
                try:
                    update_corpus_file(corpus, corpus_filename, user, now,
                                       restricted)
                except Exception:
                    generate_new_corpus_file(corpus, corpus_filename, format_,
                                             user, now, restricted)
            else:
                generate_new_corpus_file(corpus, corpus_filename, format_,
                                         user, now, restricted)
        except Exception as error:
            destroy_file(corpus_file_path)
            self.request.response.status_int = 400
            return error_msg(error)
        self.request.dbsession.flush()
        return corpus

    def _get_corpus_file_path(self, corpus, format_):
        """Return the path to a corpus's file of the given format.
        :param corpus: a corpus model object.
        :param str format_: the format for writing the corpus file.
        :returns: an absolute path to the corpus's file.
        .. note::

            It will be necessary to figure out other formats.
        """
        ext = oldc.CORPUS_FORMATS[format_]['extension']
        sfx = oldc.CORPUS_FORMATS[format_]['suffix']
        return os.path.join(
            self._get_corpus_dir_path(corpus),
            'corpus_%d%s.%s' % (corpus.id, sfx, ext))


def _get_form_ids_from_tgrep2_output_line(line):
    try:
        return int(line.split('-')[1])
    except Exception:
        return None


def _create_tgrep2_corpus_file(gzipped_corpus_file_path, format_):
    """Use TGrep2 to create a .t2c corpus file from the gzipped file of
    phrase-structure trees.
    :param str gzipped_corpus_file_path: absolute path to the gzipped corpus
        file.
    :param str format_: the format in which the corpus has just been written to
        disk.
    :returns: the absolute path to the .t2c file or ``False``.
    """
    if format_ == u'treebank' and h.command_line_program_installed('tgrep2'):
        out_path = '%s.t2c' % os.path.splitext(gzipped_corpus_file_path)[0]
        with open(os.devnull, "w") as fnull:
            call(['tgrep2', '-p', gzipped_corpus_file_path, out_path],
                 stdout=fnull, stderr=fnull)
        if os.path.exists(out_path):
            return out_path
        return False
    return False
