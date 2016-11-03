import inflect
from pyramid.response import Response
from pyramid.view import view_config
from old.views.resources import Resources

from sqlalchemy.exc import DBAPIError

p = inflect.engine()
p.classical()
member_name = 'tag'
collection_name = p.plural(member_name)

class Tags(Resources):
    pass
