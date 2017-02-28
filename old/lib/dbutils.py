"""Database-related utilities for view classes. Everything from old/utils.py
that involves the SQLA session should be moved here.

"""

from collections import namedtuple
import os
import re
from uuid import UUID

from formencode.schema import Schema
from formencode.validators import Int
from sqlalchemy.orm import subqueryload, joinedload
from sqlalchemy.sql import or_, not_, desc, asc

from old.lib.utils import esc_RE_meta_chars
import old.models as old_models
from old.models.meta import Base


class PaginatorSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = False
    items_per_page = Int(not_empty=True, min=1)
    page = Int(not_empty=True, min=1)


##########################################################################
# Eager loading of model queries
##########################################################################

# It appears that SQLAlchemy does not query the db to retrieve a relational
# scalar when the foreign key id col value is NULL. Therefore, eager loading
# on relational scalars is pointless if not wasteful. However, collections
# that will always be accessed should always be eager loaded.


def get_eagerloader(model_name):
    return locals().get('eagerload_' + model_name, lambda x: x)


def eagerload_form(query):
    return query.options(
        #subqueryload(old_models.Form.elicitor),
        subqueryload(old_models.Form.enterer),   # All forms *should* have enterers
        subqueryload(old_models.Form.modifier),
        #subqueryload(old_models.Form.verifier),
        #subqueryload(old_models.Form.speaker),
        #subqueryload(old_models.Form.elicitation_method),
        #subqueryload(old_models.Form.syntactic_category),
        #subqueryload(old_models.Form.source),
        joinedload(old_models.Form.translations),
        joinedload(old_models.Form.files),
        joinedload(old_models.Form.tags))


def eagerload_application_settings(query):
    return query.options(
        subqueryload(old_models.ApplicationSettings.input_orthography),
        subqueryload(old_models.ApplicationSettings.output_orthography),
        subqueryload(old_models.ApplicationSettings.storage_orthography)
    )


def eagerload_collection(query, eagerload_forms=False):
    """Eagerload the relational attributes of collections most likely to
    have values.
    subqueryload(old_models.Collection.speaker),
    subqueryload(old_models.Collection.elicitor),
    subqueryload(old_models.Collection.source),
    """
    if eagerload_forms:
        return query.options(
            subqueryload(old_models.Collection.enterer),
            subqueryload(old_models.Collection.modifier),
            subqueryload(old_models.Collection.forms),
            joinedload(old_models.Collection.tags),
            joinedload(old_models.Collection.files))
    else:
        return query.options(
            subqueryload(old_models.Collection.enterer),
            subqueryload(old_models.Collection.modifier),
            joinedload(old_models.Collection.tags),
            joinedload(old_models.Collection.files))


def eagerload_corpus(query, eagerload_forms=False):
    """Eagerload the relational attributes of corpora most likely to have
    values.
    """
    if eagerload_forms:
        return query.options(
            subqueryload(old_models.Corpus.enterer),
            subqueryload(old_models.Corpus.modifier),
            subqueryload(old_models.Corpus.forms),
            joinedload(old_models.Corpus.tags))
    else:
        return query.options(
            subqueryload(old_models.Corpus.enterer),
            subqueryload(old_models.Corpus.modifier),
            joinedload(old_models.Corpus.tags))


def eagerload_file(query):
    return query.options(
        subqueryload(old_models.File.enterer),
        subqueryload(old_models.File.elicitor),
        subqueryload(old_models.File.speaker),
        subqueryload(old_models.File.parent_file),
        joinedload(old_models.File.tags),
        joinedload(old_models.File.forms))


def eagerload_form_search(query):
    # return query.options(subqueryload(old_models.FormSearch.enterer))
    return query


def eagerload_phonology(query):
    return query.options(
        subqueryload(old_models.Phonology.enterer),
        subqueryload(old_models.Phonology.modifier))


def eagerload_morpheme_language_model(query):
    return query.options(
        subqueryload(old_models.MorphemeLanguageModel.corpus),
        subqueryload(
            old_models.MorphemeLanguageModel.vocabulary_morphology),
        subqueryload(old_models.MorphemeLanguageModel.enterer),
        subqueryload(old_models.MorphemeLanguageModel.modifier))


def eagerload_morphological_parser(query):
    return query.options(
        subqueryload(old_models.MorphologicalParser.phonology),
        subqueryload(old_models.MorphologicalParser.morphology),
        subqueryload(old_models.MorphologicalParser.language_model),
        subqueryload(old_models.MorphologicalParser.enterer),
        subqueryload(old_models.MorphologicalParser.modifier))


def eagerload_morphology(query):
    return query.options(
        subqueryload(old_models.Morphology.lexicon_corpus),
        subqueryload(old_models.Morphology.rules_corpus),
        subqueryload(old_models.Morphology.enterer),
        subqueryload(old_models.Morphology.modifier))


def eagerload_user(query):
    """
    return query.options(
        #subqueryload(old_models.User.input_orthography),
        #subqueryload(old_models.User.output_orthography)
    )
    """
    return query


def minimal(models_array):
    """Return a minimal representation of the models in `models_array`.
    Right now, this means we just return the id, the datetime_entered and
    the datetime_modified. Useful for graphing data and for checking for
    updates.
    """
    return [minimal_model(model) for model in models_array]


def minimal_model(model):
    return {
        'id': model.id,
        'datetime_entered': getattr(model, 'datetime_entered', None),
        'datetime_modified': getattr(model, 'datetime_modified', None)
    }


def get_paginated_query_results(query, paginator):
    if 'count' not in paginator:
        paginator['count'] = query.count()
    start, end = _get_start_and_end_from_paginator(paginator)
    items = query.slice(start, end).all()
    if paginator.get('minimal'):
        items = minimal(items)
    else:
        items = [mod.get_dict() for mod in items]
    return {
        'paginator': paginator,
        'items': items
    }


def add_pagination(query, paginator):
    if (paginator and paginator.get('page') is not None and
            paginator.get('items_per_page') is not None):
        # raises formencode.Invalid if paginator is invalid
        paginator = PaginatorSchema.to_python(paginator)
        return get_paginated_query_results(query, paginator)
    else:
        if paginator and paginator.get('minimal'):
            return minimal(query.all())
        return query.all()


def get_model_names():
    return [mn for mn in dir(old_models) if mn[0].isupper()
            and mn not in ('Model', 'Base', 'Session', 'Engine')]


def get_last_modified(result):
    """Return a ``datetime`` instance representing the most recent
    modification of the result set in ``result``. Useful for cacheing,
    i.e., via Last-Modified header.
    """
    if 'items' in result:
        result = result['items']
    if result:
        return sorted(r.datetime_modified for r in result)[-1]\
            .strftime('%a, %d %b %Y %H:%M:%S GMT')
    return None


def _get_start_and_end_from_paginator(paginator):
    start = (paginator['page'] - 1) * paginator['items_per_page']
    return (start, start + paginator['items_per_page'])


def _filter_restricted_models_from_query(model_name, query, user):
    model_ = getattr(old_models, model_name)
    if model_name in ('FormBackup', 'CollectionBackup'):
        enterer_condition = model_.enterer.like(
            '%' + '"id": %d' % user.id + '%')
        unrestricted_condition = not_(model_.tags.like(
            '%"name": "restricted"%'))
    else:
        enterer_condition = model_.enterer == user
        unrestricted_condition = not_(model_.tags.any(
            old_models.Tag.name=='restricted'))
    return query.filter(or_(enterer_condition, unrestricted_condition))


class DBUtils:
    """Mixin for resource (view) classes (and anything with access to the
    request) that provides access to the database via a ``dbsession`` attribute.
    """

    def __init__(self, dbsession, settings=None):
        self.dbsession = dbsession
        if settings:
            self.settings = settings
        else:
            self.settings = {}
        self._current_app_set = None
        self._foreign_word_transcriptions = None

    @property
    def current_app_set(self):
        """The ApplicationSettings model with the highest id is considered the
        current one.
        """
        if not self._current_app_set:
            self._current_app_set = self.get_current_app_set()
        return self._current_app_set

    def get_current_app_set(self):
        """Use this to get the current application settings, without
        in-thread/memory caching.
        """
        return self.dbsession.query(
            old_models.ApplicationSettings).order_by(
                desc(old_models.ApplicationSettings.id)).first()

    def get_object_language_id(self):
        return getattr(self.current_app_set, 'object_language_id', 'old')

    def get_grammaticalities(self):
        return getattr(self.current_app_set, 'grammaticalities_list', [])

    def get_morpheme_delimiters(self, type_='list'):
        """Return the morpheme delimiters from app settings as an object of
        type ``type_``."""
        if type_ == 'list':
            return getattr(self.current_app_set, 'morpheme_delimiters_list', [])
        return getattr(self.current_app_set, 'morpheme_delimiters', '')

    def get_unrestricted_users(self):
        """Return the list of unrestricted users in the current application
        settings.
        """
        return getattr(self.current_app_set, 'unrestricted_users', [])

    def get_restricted_tag(self):
        return self.dbsession.query(old_models.Tag).filter(
            old_models.Tag.name == 'restricted').first()

    def user_is_unrestricted(self, user):
        """Return True if the user is an administrator, unrestricted or there
        is no restricted tag.
        """
        if user.role == 'administrator':
            return True
        elif not self.get_restricted_tag():
            return True
        elif user in self.get_unrestricted_users():
            return True
        else:
            return False

    def get_foreign_words(self):
        """Return the forms that are tagged with a 'foreign word' tag. This is
        useful for input validation as foreign words may contain otherwise
        illicit characters/graphemes.
        """
        foreign_word_tag = self.get_foreign_word_tag()
        if foreign_word_tag:
            return self.dbsession.query(old_models.Form).filter(
                old_models.Form.tags.contains(foreign_word_tag)).all()
        return []

    def get_foreign_word_tag(self):
        return self.dbsession.query(old_models.Tag).filter(
            old_models.Tag.name=='foreign word').first()

    def get_foreign_word_tag_id(self):
        return self.get_foreign_word_tag().id

    @property
    def foreign_word_transcriptions(self):
        """Returns a 4-tuple (foreign_word_narrow_phonetic_transcriptions,
        foreign_word_broad_phonetic_transcriptions,
        foreign_word_orthographic_transcriptions,
        foreign_word_morphemic_transcriptions) where each element is a list of
        transcriptions (narrow phonetic, broad phonetic, orthographic,
        morphemic) of foreign words.
        """
        if not self._foreign_word_transcriptions:
            foreign_words = self.get_foreign_words()
            foreign_word_narrow_phonetic_transcriptions = []
            foreign_word_broad_phonetic_transcriptions = []
            foreign_word_orthographic_transcriptions = []
            foreign_word_morphemic_transcriptions = []
            for fw in foreign_words:
                if fw.narrow_phonetic_transcription:
                    foreign_word_narrow_phonetic_transcriptions.append(
                        fw.narrow_phonetic_transcription)
                if fw.phonetic_transcription:
                    foreign_word_broad_phonetic_transcriptions.append(
                        fw.phonetic_transcription)
                if fw.morpheme_break:
                    foreign_word_morphemic_transcriptions.append(fw.morpheme_break)
                foreign_word_orthographic_transcriptions.append(fw.transcription)
            FWTrans = namedtuple('FWTrans', ['narrow_phonetic',
                                             'broad_phonetic',
                                             'orthographic',
                                             'morpheme_break'])
            self._foreign_word_transcriptions = FWTrans(
                foreign_word_narrow_phonetic_transcriptions,
                foreign_word_broad_phonetic_transcriptions,
                foreign_word_orthographic_transcriptions,
                foreign_word_morphemic_transcriptions
            )
        return self._foreign_word_transcriptions

    ###########################################################################
    # Convenience getters for resource collections
    ###########################################################################

    def get_all_models(self):
        return {mn: self.get_models_by_name(mn) for mn in
                get_model_names()}

    def get_collections(self):
        return self.get_models_by_name('Collection', True)

    def get_corpora(self, sort_by_id_asc=False):
        return self.get_models_by_name('Corpus', sort_by_id_asc)

    def get_elicitation_methods(self, sort_by_id_asc=False):
        return self.get_models_by_name('ElicitationMethod', sort_by_id_asc)

    def get_files(self):
        return self.get_models_by_name('File', True)

    def get_form_searches(self, sort_by_id_asc=False):
        return self.get_models_by_name('FormSearch', sort_by_id_asc)

    def get_forms(self, paginator=None, eagerload=False):
        form_query = self.dbsession.query(old_models.Form)\
            .order_by(asc(old_models.Form.id))
        if eagerload:
            form_query = eagerload_form(form_query)
        if paginator:
            start, end = _get_start_and_end_from_paginator(paginator)
            return form_query.slice(start, end).all()
        return form_query.all()

    def get_languages(self, sort_by_id_asc=False):
        return self.get_models_by_name('Language', sort_by_id_asc)

    def get_orthographies(self, sort_by_id_asc=False):
        return self.get_models_by_name('Orthography', sort_by_id_asc)

    def get_pages(self, sort_by_id_asc=False):
        return self.get_models_by_name('Page', sort_by_id_asc)

    def get_phonologies(self, sort_by_id_asc=False):
        return self.get_models_by_name('Phonology', sort_by_id_asc)

    def get_sources(self, sort_by_id_asc=False):
        return self.get_models_by_name('Source', sort_by_id_asc)

    def get_speakers(self, sort_by_id_asc=False):
        return self.get_models_by_name('Speaker', sort_by_id_asc)

    def get_syntactic_categories(self, sort_by_id_asc=False):
        return self.get_models_by_name('SyntacticCategory', sort_by_id_asc)

    def get_tags(self, sort_by_id_asc=False):
        return self.get_models_by_name('Tag', sort_by_id_asc)

    def get_users(self, sort_by_id_asc=False):
        return self.get_models_by_name('User', sort_by_id_asc)

    def get_forms_user_can_access(self, user, paginator=None):
        query = _filter_restricted_models_from_query(
            'Form',
            self.dbsession.query(old_models.Form),
            user
        ).order_by(asc(old_models.Form.id))
        if paginator:
            start, end = _get_start_and_end_from_paginator(paginator)
            return query.slice(start, end).all()
        return query.all()

    def get_mini_dicts_getter(self, model_name, sort_by_id_asc=False):
        def func():
            models = self.get_models_by_name(model_name, sort_by_id_asc)
            return [m.get_mini_dict() for m in models]
        return func

    def get_models_by_name(self, model_name, sort_by_id_asc=False):
        return self.get_query_by_model_name(model_name, sort_by_id_asc).all()

    def get_query_by_model_name(self, model_name, sort_by_id_asc=False):
        model_ = getattr(old_models, model_name)
        if sort_by_id_asc:
            return self.dbsession.query(model_)\
                .order_by(asc(getattr(model_, 'id')))
        return self.dbsession.query(model_)

    def clear_all_models(self, retain=('Language',)):
        """Convenience function for removing all OLD models from the database.
        The retain parameter is a list of model names that should not be cleared.
        """
        for model_name in get_model_names():
            if model_name not in retain:
                models = self.get_models_by_name(model_name)
                for model in models:
                    self.dbsession.delete(model)
        self.dbsession.flush()

    def clear_all_tables(self, retain=()):
        """Like ``clear_all_models`` above, except **much** faster."""
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in retain:
                print('deleting table ', table.name)
                self.dbsession.execute(table.delete())
        self.dbsession.flush()

    def get_model_and_previous_versions(self, model_name, id_):
        """Return a model and its previous versions.
        :param str model_name: a model name, e.g., 'Form'
        :param str id_: the ``id`` or ``UUID`` value of the model whose history
            is requested.
        :returns: a tuple whose first element is the model and whose second
            element is a list of the model's backup models.
        """
        model_ = None
        previous_versions = []
        try:
            id_ = int(id_)
            # add eagerload function ...
            model_ = get_eagerloader(model_name)(
                self.dbsession.query(getattr(old_models, model_name))).get(id_)
            if model_:
                previous_versions = self.get_backups_by_UUID(model_name,
                                                             model_.UUID)
            else:
                previous_versions = self.get_backups_by_model_id(model_name, id_)
        except ValueError:
            try:
                model_UUID = str(UUID(id_))
                model_ = self.get_model_by_UUID(model_name, model_UUID)
                previous_versions = self.get_backups_by_UUID(model_name,
                                                             model_UUID)
            except (AttributeError, ValueError):
                pass    # id_ is neither an integer nor a UUID
        return model_, previous_versions

    def get_model_by_UUID(self, model_name, uuid_):
        """Return the first (and only, hopefully) model of type
        ``model_name`` with ``uuid_``.
        """
        return get_eagerloader(model_name)(
            self.dbsession.query(getattr(old_models, model_name)))\
            .filter(getattr(old_models, model_name).UUID==uuid_).first()

    def get_backups_by_UUID(self, model_name, uuid_):
        """Return all backup models of the model with ``model_name`` using the
        ``uuid_`` value.
        """
        backup_model = getattr(old_models, model_name + 'Backup')
        return self.dbsession.query(backup_model).\
            filter(backup_model.UUID==uuid_).\
            order_by(desc(backup_model.id)).all()

    def get_backups_by_model_id(self, model_name, model_id):
        """Return all backup models of the model with ``model_name`` using the
        ``id`` value of the model.
        .. warning::
            Unexpected data may be returned (on an SQLite backend) if primary
            key ids of deleted models are recycled.
        """
        backup_model = getattr(old_models, model_name + 'Backup')
        return self.dbsession.query(backup_model)\
            .filter(
                getattr(backup_model, model_name.lower() + '_id')==model_id)\
            .order_by(desc(backup_model.id)).all()

    def get_most_recent_modification_datetime(self, model_name):
        """Return the most recent datetime_modified attribute for the model
        with the provided model_name.  If the model_name is not recognized,
        return None.
        """
        old_model = getattr(old_models, model_name, None)
        if old_model:
            return self.dbsession.query(old_model).order_by(
                desc(old_model.datetime_modified)).first().datetime_modified
        return old_model

    def filter_restricted_models(self, model_name, query, user):
        if self.user_is_unrestricted(user):
            return query
        else:
            return _filter_restricted_models_from_query(model_name, query, user)

    def get_morpheme_splitter(self):
        """Return a function that will split words into morphemes."""
        morpheme_splitter = lambda x: [x]  # default, word is morpheme
        morpheme_delimiters = self.get_morpheme_delimiters()
        if morpheme_delimiters:
            morpheme_splitter = re.compile(
                '([%s])' % ''.join([esc_RE_meta_chars(d) for d in
                                    morpheme_delimiters])).split
        return morpheme_splitter

    def get_normative_language_id(self, lang_type, app_set,
                                  force_lang_id=False):
        """Attempt to return the ISO 639-3 3-character language Id for the
        language of type ``lang_type``, i.e., the object language or the
        metalanguage. If Id is unavailable, return the language name. If that
        is unavailable, return the empty string.
        """
        if lang_type == 'object':
            lang_id = app_set.object_language_id
            lang_name = app_set.object_language_name.strip()
        else:
            lang_id = app_set.metalanguage_id
            lang_name = app_set.metalanguage_name.strip()
        # Here we test to make sure that the lang_id is an actual ISO 639-3
        # 3-char language Id in the database. However, if we are testing we
        # will not have the ISO database fully populated; hence the following
        # hack:
        if lang_id and force_lang_id:
            return lang_id, True
        Language = old_models.Language
        language_model = self.request.dbsession.query(
            Language).filter(Language.Id == lang_id).first()
        if language_model:
            return lang_id, True
        else:
            return lang_name, False
