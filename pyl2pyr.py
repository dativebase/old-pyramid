import re
import os
import sys
import shutil

import inflect
inflect_p = inflect.engine()
inflect_p.classical()

member_name = sys.argv[1]
if member_name == 'applicationsetting':
    model_name = 'ApplicationSettings'
elif member_name == 'elicitationmethod':
    model_name = 'ElicitationMethod'
else:
    model_name = member_name.capitalize()
member_name_pl = inflect_p.plural(member_name)

src, dst = sys.argv[2:]
if not os.path.isfile(src):
    sys.exit('There is no source file at {}'.format(src))

"""
if os.path.isfile(dst):
    if not input('Overwrite {}?'.format(dst)) == 'y':
        sys.exit('Ok. bye')
"""

REPLACE_MEMB = {
    'applicationsetting': (
        ('== application_settings.', '== db.current_app_set.'),
    )
}

REPLACE = (
    ('import simplejson as json', 'import json'),
    ('from onlinelinguisticdatabase.', 'from old.'),
    ('from old.model import ', 'from old.models import '),
    ('from old.tests import TestController, url',
        'from old.tests import TestView, add_SEARCH_to_web_test_valid_methods'),
    ('import onlinelinguisticdatabase.', 'import old.'),
    ('import old.model as model', 'import old.models as old_models'),
    ('model.', 'old_models.'),
    ('log = logging.', 'LOGGER = logging.'),
    ('log.', 'LOGGER.'),
    ('h.gen', 'omb.gen'),
    ('h.get_', 'db.get_'),
    ('Session.', 'dbsession.'),
    ('dbsession.commit', 'transaction.commit'),
    ('json.loads(response.body)', 'response.json_body'),
    ('.get(url(\'{}\')'.format(member_name_pl), '.get(url(\'index\')'),
    ('.post(url(\'{}\')'.format(member_name_pl), '.post(url(\'create\')'),
    ('.delete(url(\'{}\','.format(member_name), '.delete(url(\'delete\','),
    ('.get(url(\'{}\','.format(member_name), '.get(url(\'show\','),
    ('.put(url(\'{}\','.format(member_name), '.put(url(\'update\','),
    ('url(\'new_{}\')'.format(member_name), 'url(\'new\')'),
    ('url(\'edit_{}\','.format(member_name), 'url(\'edit\','),
    (', cls=h.JSONOLDEncoder', ''),
    ('db.get_application_settings()', 'db.current_app_set'),
    (' u\'', ' \''),
    ('=u\'', '=\''),
    (' u"', ' "'),
    ('=u"', '="'),
    ('add_default_application_settings()',
        'add_default_application_settings(dbsession)'),
    ('== None', 'is None'),
    ('== True', 'is True'),
    ('== False', 'is False'),
    (', 0744', ', 0o744'),
    ('self._add_SEARCH_to_web_test_valid_methods',
        'add_SEARCH_to_web_test_valid_methods'),
    ('self.config', 'self.settings'),
    ('unicode(', 'str('),
    ('h.clear_all_models', 'db.clear_all_models'),
    ('h.clear_all_tables', 'db.clear_all_tables'),
)

RE_REPLACE = (
    ('Test(\w+)Controller\(TestController\)', 'Test\\1View(TestView)'),
)

# Delete lines that contain these strings.
DELETE = (
    'from nose.tools import nottest',
    '@nottest',
)

# If the first string of the 2-tuple is in a line, add the lines in the second
# tuple after the line.
ADD_POST = (
    ('LOGGER = logging', ('\n',
                          '\n',
                          'url = {}._url()\n'.format(model_name),
                          '\n',
                          '\n')),
    ('import old.lib.helpers as h',
        ('import old.models.modelbuilders as omb\n',)),

    ('import json', ('\n',
                     'import transaction\n',
                     '\n',
                     'from old.lib.dbutils import DBUtils\n')),
)

DEL_POST = (
    'from old.model.meta import Session',
    'from old.old_models.meta import Session',
)


top_test_meth = False
in_test_meth = False


with open(src) as filei, open(dst, 'w') as fileo:
    result = []
    for line in filei:

        if ' def test_' in line:
            top_test_meth = True
            in_test_meth = False

        write_line = True
        for badpatt in DELETE:
            if badpatt in line:
                write_line = False
                break

        if write_line:
            for patti, patto in REPLACE:
                line = line.replace(patti, patto)
            for patti, patto in REPLACE_MEMB.get(member_name, ()):
                line = line.replace(patti, patto)
            for rei, reo in RE_REPLACE:
                line = re.sub(rei, reo, line)

            for badpatt in DEL_POST:
                if badpatt in line:
                    write_line = False
                    break

            if write_line:
                if line.strip not in DEL_POST:
                    if in_test_meth and line.strip():
                        # spaces = len(line) - len(line.strip())
                        fileo.write('    {}'.format(line))
                    else:
                        fileo.write(line)
                    for patti, adds in ADD_POST:
                        if patti in line:
                            for add in adds:
                                fileo.write(add)

        if top_test_meth and line.strip().endswith('"""'):
            top_test_meth = False
            in_test_meth = True
            fileo.write(
                '        with transaction.manager:\n')
            fileo.write(
                '            dbsession = self.get_dbsession()\n')
            fileo.write(
                '            db = DBUtils(dbsession, self.settings)\n')

