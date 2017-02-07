import os
import re


__version__ = '2.0.0'


RSRC_TO_DIR = {
    'file': 'files',
    'files': 'files',
    'reduced_files': os.path.join('files', 'reduced_files'),
    'users': 'users',
    'user': 'users',
    'corpora': 'corpora',
    'corpus': 'corpora',
    'phonologies': 'phonologies',
    'phonology': 'phonologies',
    'morphologies': 'morphologies',
    'morphology': 'morphologies',
    'morphological_parsers': 'morphological_parsers',
    'morphologicalparsers': 'morphological_parsers',
    'morphologicalparser': 'morphological_parsers',
    'morpheme_language_models': 'morpheme_language_models',
    'morphemelanguagemodels': 'morpheme_language_models',
    'morphemelanguagemodel': 'morpheme_language_models'
}


RSRC_TO_SUBDIR = {
    'corpora': 'corpus',
    'corpus': 'corpus',
    'phonologies': 'phonology',
    'phonology': 'phonology',
    'morphologies': 'morphology',
    'morphology': 'morphology',
    'morphological_parsers': 'morphological_parser',
    'morphologicalparsers': 'morphological_parser',
    'morphologicalparser': 'morphological_parser',
    'morpheme_language_models': 'morpheme_language_model',
    'morphemelanguagemodels': 'morpheme_language_model',
    'morphemelanguagemodel': 'morpheme_language_model'
}


ALLOWED_FILE_TYPES = (
    #'text/plain',
    #'application/x-latex',
    #'application/msword',
    #'application/vnd.ms-powerpoint',
    #'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    #'application/vnd.oasis.opendocument.text',
    'application/pdf',
    'image/gif',
    'image/jpeg',
    'image/png',
    'audio/mpeg',
    'audio/ogg',
    'audio/x-wav',
    'video/mpeg',
    'video/mp4',
    'video/ogg',
    'video/quicktime',
    'video/x-ms-wmv'
)


UTTERANCE_TYPES = (
    'None',
    'Object Language Utterance',
    'Metalanguage Utterance',
    'Mixed Utterance'
)


COLLECTION_TYPES = (
    'story',
    'elicitation',
    'paper',
    'discourse',
    'other'
)


# Corpus formats -- determine how a corpus is rendered as a file, e.g., a
# treebank will output a file containing representations of phrase structure for
# each form in the corpus and the file will be called ``corpus_1.tbk`` ...
CORPUS_FORMATS = {
    'treebank': {
        'extension': 'tbk',
        'suffix': '',
        'writer': lambda f: '(TOP-%d %s)\n' % (f.id, f.syntax)
    },
    'transcriptions only': {
        'extension': 'txt',
        'suffix': '_transcriptions',
        'writer': lambda f: '%s\n' % f.transcription
    }
}


# This is the regex for finding form references in the contents of collections.
FORM_REFERENCE_PATTERN = re.compile(r'[Ff]orm\[([0-9]+)\]')


# This is the regex for finding collection references in the contents of collections.
#COLLECTION_REFERENCE_PATTERN = re.compile('[cC]ollection[\(\[](\d+)[\)\]]')
COLLECTION_REFERENCE_PATTERN = re.compile('[cC]ollection[\[\(](\d+)[\]\)]')


MARKUP_LANGUAGES = (
    'reStructuredText',
    'Markdown',
)


# Subject to change!  Or maybe these should be user-definable ...
SYNTACTIC_CATEGORY_TYPES = (
    'lexical',
    'phrasal',
    'sentential'
)


FORM_STATUSES = (
    'tested',
    'requires testing'
)


USER_ROLES = (
    'viewer',
    'contributor',
    'administrator'
)


VALIDATION_VALUES = (
    'None',
    'Warning',
    'Error'
)


# How long to wait (in seconds) before terminating a process that is trying to
# compile a foma script.
PHONOLOGY_COMPILE_TIMEOUT = 30


# Give foma morphology scripts 30 minutes to compile
MORPHOLOGY_COMPILE_TIMEOUT = 60 * 3000


# Give foma morphological parser scripts 60 minutes to compile
MORPHOLOGICAL_PARSER_COMPILE_TIMEOUT = 60 * 60


MORPHEME_LANGUAGE_MODEL_GENERATE_TIMEOUT = 60 * 15

# The word boundary symbol is used in foma FST scripts to denote the beginning
# or end of a word, i.e., it can be referred to in phonological rules, e.g.,
# define semivowelDrop glides -> 0 || "#" _;$ The system will wrap inputs in
# this symbol when applying a phonology against them.
WORD_BOUNDARY_SYMBOL = '#'


MORPHOLOGY_SCRIPT_TYPES = (
    'regex',
    'lexc'
)


# String to use when a morpheme's category cannot be determined
UNKNOWN_CATEGORY = '?'


# Default delimiter: used to delimit break-gloss-category strings in the
# ``break_gloss_category`` attribute.
DEFAULT_DELIMITER = '|'


# Rare delimiter: used to delimit morphemes shapes from glosses in foma lexica.
RARE_DELIMITER = '\u2980'


LANGUAGE_MODEL_TOOLKITS = {
    'mitlm': {
        'smoothing_algorithms': ['ML', 'FixKN', 'FixModKN', 'FixKNn', 'KN',
                                 'ModKN', 'KNn'], # cf. http://code.google.com/p/mitlm/wiki/Tutorial
        'executable': 'estimate-ngram'
    }
}

LM_START = '<s>'
LM_END = '</s>'


UNAUTHORIZED_MSG = {
    'error': 'You are not authorized to access this resource.'
}


UNAUTHENTICATED_MSG = {
    'error': 'Authentication is required to access this resource.'
}


JSONDecodeErrorResponse = {
    'error': 'JSON decode error: the parameters provided were not valid'
             ' JSON.'
}


# ISO datetime format string. Use this instead of isoformat because we want to
# ignore milliseconds on purpose. Reason: stupid MySQL doesn't support them in
# standard versions.
ISO_STRFTIME = '%Y-%m-%dT%H:%M:%S'
