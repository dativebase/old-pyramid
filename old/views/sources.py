import datetime

import old.lib.helpers as h
from old.views.resources import Resources


class Sources(Resources):

    def _get_new_edit_collections(self):
        return ('types',)

    def _get_mandatory_collections(self):
        return ('types',)

    def _get_user_data(self, data):
        return {
            'type': h.normalize(data['type']),
            'key': h.normalize(data['key']),
            'address': h.normalize(data['address']),
            'annote': h.normalize(data['annote']),
            'author': h.normalize(data['author']),
            'booktitle': h.normalize(data['booktitle']),
            'chapter': h.normalize(data['chapter']),
            'crossref': h.normalize(data['crossref']),
            'edition': h.normalize(data['edition']),
            'editor': h.normalize(data['editor']),
            'howpublished': h.normalize(data['howpublished']),
            'institution': h.normalize(data['institution']),
            'journal': h.normalize(data['journal']),
            'key_field': h.normalize(data['key_field']),
            'month': h.normalize(data['month']),
            'note': h.normalize(data['note']),
            'number': h.normalize(data['number']),
            'organization': h.normalize(data['organization']),
            'pages': h.normalize(data['pages']),
            'publisher': h.normalize(data['publisher']),
            'school': h.normalize(data['school']),
            'series': h.normalize(data['series']),
            'title': h.normalize(data['title']),
            'type_field': h.normalize(data['type_field']),
            'url': data['url'],
            'volume': h.normalize(data['volume']),
            'year': data['year'],
            'affiliation': h.normalize(data['affiliation']),
            'abstract': h.normalize(data['abstract']),
            'contents': h.normalize(data['contents']),
            'copyright': h.normalize(data['copyright']),
            'ISBN': h.normalize(data['ISBN']),
            'ISSN': h.normalize(data['ISSN']),
            'keywords': h.normalize(data['keywords']),
            'language': h.normalize(data['language']),
            'location': h.normalize(data['location']),
            'LCCN': h.normalize(data['LCCN']),
            'mrnumber': h.normalize(data['mrnumber']),
            'price': h.normalize(data['price']),
            'size': h.normalize(data['size']),
            'file': data['file'],
            'crossref_source': data['crossref_source']
        }

    def _get_create_data(self, data):
        return self._get_update_data(self._get_user_data(data))

    def _get_update_data(self, user_data):
        user_data.update({
            'datetime_modified': datetime.datetime.utcnow()
        })
        return user_data
