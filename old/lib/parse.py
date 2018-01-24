#!/usr/bin/python

# Copyright 2016 Joel Dunham
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Basic command-line interface to a configured, compiled and exported OLD
parser.

Usage:

    $ ./parse.py wordi (wordj ... wordn)

This script is intended to be included in the .zip archive returned by an OLD
application when GET /morphologicalparsers/id/export is requested on the fully
generated and compiled morphological parser with id ``id``.  It expects all
requisite files for the parser and its sub-objects (e.g., the compiled
morphophonology foma script, the pickled LM Trie, the lexicon and dictionary
pickle files, if needed, etc.) as well as a configuration pickle file (i.e.,
config.pickle) to be present in the current working directory.

The code for the parser functionality is all located in ``parser.py``, which is
the same as that used by an OLD web application.

Note that the included simplelm module is a somewhat modified version from that
available at <<URL>>.
"""

import os
import sys
import pickle

# Alter the module search path so that the directory containing this script is
# in it. This is necessary for the importation of the local ``parser`` module.
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(SCRIPT_DIR)

import parser
if not 'PhonologyFST' in dir(parser):
    # Import the *local* parser module
    import imp
    PARSER_MODULE_PATH = os.path.join(SCRIPT_DIR, 'parser.py')
    parser = imp.load_source(os.path.dirname(__file__), PARSER_MODULE_PATH)

CONFIG_FILE = 'config.pickle'
CONFIG_PATH = os.path.join(SCRIPT_DIR, CONFIG_FILE)
CACHE_FILE = 'cache.pickle'
CACHE_PATH = os.path.join(SCRIPT_DIR, CACHE_FILE)

def get_config():
    with open(CONFIG_PATH, 'rb') as filei:
        return pickle.load(filei)

def get_phonology():
    return parser.PhonologyFST(
        parent_directory = SCRIPT_DIR,
        word_boundary_symbol = get_config()['phonology']['word_boundary_symbol']
    )

def get_morphology():
    return parser.MorphologyFST(
        parent_directory = SCRIPT_DIR,
        word_boundary_symbol = get_config()['morphology']['word_boundary_symbol'],
        rare_delimiter = get_config()['morphology']['rare_delimiter'],
        rich_upper = get_config()['morphology']['rich_upper'],
        rich_lower = get_config()['morphology']['rich_lower'],
        rules_generated = get_config()['morphology']['rules_generated']
    )

def get_language_model():
    return parser.LanguageModel(
        parent_directory = SCRIPT_DIR,
        rare_delimiter = get_config()['language_model']['rare_delimiter'],
        start_symbol = get_config()['language_model']['start_symbol'],
        end_symbol = get_config()['language_model']['end_symbol'],
        categorial = get_config()['language_model']['categorial']
    )

def get_parser():
    return parser.MorphologicalParser(
        parent_directory = SCRIPT_DIR,
        word_boundary_symbol = get_config()['parser']['word_boundary_symbol'],
        morpheme_delimiters = get_config()['parser']['morpheme_delimiters'],
        phonology = phonology,
        morphology = morphology,
        language_model = language_model,
        cache = parser.Cache(path=CACHE_PATH)
    )

if __name__ == '__main__':

    for input_ in sys.argv[1:]:
        parse = get_parser().pretty_parse(input_)[input_]
        if parse:
            print('%s %s' % (input_, ' '.join(parse)))
        else:
            print('%s No parse' % input_)
