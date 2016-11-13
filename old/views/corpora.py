import old.lib.constants as oldc
from old.views.resources import Resources


class Corpora(Resources):

    def get_word_category_sequences(self):
        """Return the category sequence types of validly morphologically
        analyzed words in the corpus with ``id``, including the id exemplars of
        said types.
        """
        corpus, id_ = self._model_from_id()
        if corpus:
            word_category_sequences = self._get_word_category_sequences(corpus)
            minimum_token_count = int(self.request.GET.get(
                'minimum_token_count', 0))
            if minimum_token_count:
                word_category_sequences = [
                    (''.join(sequence), ids) for sequence, ids in
                    word_category_sequences if len(ids) >= minimum_token_count]
            return word_category_sequences
        else:
            self.request.response.status_int = 404
            return {'error': 'There is no corpus with id %s' % id_}

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
        result = {}
        morpheme_splitter = self.db.get_morpheme_splitter()
        for form in corpus.forms:
            category_sequences, _ = form.extract_word_pos_sequences(
                oldc.UNKNOWN_CATEGORY, morpheme_splitter,
                extract_morphemes=False)
            if category_sequences:
                for category_sequence in category_sequences:
                    result.setdefault(category_sequence, []).append(form.id)
        return sorted(result.items(), key=lambda t: len(t[1]), reverse=True)
