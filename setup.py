import re
import os
import sys

from setuptools import setup, find_packages

# Set the version of this OLD using the version variable here. The following
# lines then modify the info.py controller so that it stores the appropriate
# version.
VERSION = '2.0.0'

p = re.compile('(^\s*[\'"]version[\'"]:\s*[\'"])([0-9\.]+)([\'"].*$)')
wd = os.path.dirname(os.path.realpath(__file__))
infopth = os.path.join(wd, 'old', 'views', 'info.py')
lines = []


def fixer(match):
    return '%s%s%s' % (match.group(1), VERSION, match.group(3))


with open(infopth) as f:
    for line in f:
        if p.search(line):
            lines.append(p.sub(fixer, line))
        else:
            lines.append(line)

with open(infopth, 'w') as f:
    f.write(''.join(lines))


pkgfile = os.path.join(wd, 'old', '__init__.py')
lines = []

with open(pkgfile) as f:
    for line in f:
        if line.startswith('__version__'):
            lines.append('__version__ = \'%s\'\n' % VERSION)
        else:
            lines.append(line)

with open(pkgfile, 'w') as f:
    f.write(''.join(lines))

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.rst')) as f:
    README = f.read()

with open(os.path.join(here, 'CHANGES.txt')) as f:
    CHANGES = f.read()


requires = [
    'docutils',
    'formencode',
    'inflect',
    'markdown',
    'passlib',
    'Pillow',
    'pyramid',
    'pyramid_beaker',
    'pyramid_debugtoolbar',
    'pyramid_jinja2',
    # 'python-magic',
    'requests',
    'SQLAlchemy',
    'waitress',
]

tests_require = [
    'WebTest >= 1.3.1',  # py3 compat
    'pylint',
    'pytest',  # includes virtualenv
    'pytest-cov',
]

setup(name='old',
      version=VERSION,
      description=(
        'A program for building web services that facilitate collaborative'
        ' storing, searching, processing and analyzing of linguistic fieldwork'
        ' data.'),
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pyramid",
          "Intended Audience :: Developers",
          "Intended Audience :: Education",
          "Intended Audience :: Science/Research",
          "License :: OSI Approved :: Apache Software License",
          "Natural Language :: English",
          "Programming Language :: Python",
          "Topic :: Database :: Front-Ends",
          "Topic :: Education"
      ],
      author='Joel Dunham',
      author_email='jrwdunham@gmail.com',
      url='http://www.onlinelinguisticdatabase.org',
      keywords='web wsgi bfg pylons pyramid language linguistics documentation',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      extras_require={
          'testing': tests_require,
          # 'MySQL': ["mysql-python>-1.2"]  # TODO: no mysql-python in Python3
      },
      install_requires=requires,
      entry_points="""\
      [paste.app_factory]
      main = old:main
      [console_scripts]
      initialize_old = old.scripts.initialize:main
      """)
