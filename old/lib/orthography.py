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

"""
Orthography module describes an Orthography class that represents the
orthography of a given language.

OrthographyTranslator facilitates conversion of text in orthography A into
orthography B; takes two Orthography objects at initialization.

This module is adapted and generalized from one written by Patrick Littell
for the conversion of Kwak'wala strings between its many orthographies.

"""

import re


class Orthography:
    """The Orthography class represents an orthography used to transcribe a
    language.

    Required as input is a comma-delimited string of graphs.  Graphs are
    represented by strings of one or more unicode characters.  Order of graphs
    is important for sorting words or Forms of the language under study.

    Graph variants (allographs?) should be grouped together with brackets.

    E.g., orthography_as_string = u'[a,a\u0301],b,c,d'

    The above orthography string represents an orthography where u'a' and
    u'a\u0301' are both ranked first, u'b' second, u'c' third, etc.

    Idiosyncratic arguments are in **kwargs, e.g.,:
     - lowercase: whether or not the orthography is all-lowercase
     - initial_glottal_stops: whether it represents glottal stops (assumed to be
       u'7' in the input orthography) word initially.

    """

    def remove_all_white_space(self, string):
        """Remove all spaces, newlines and tabs."""
        string = string.replace('\n', '')
        string = string.replace('\t', '')
        string = string.replace(' ', '') 
        return string

    def str2bool(self, string):
        if string == '1':
            return True
        elif string == '0':
            return False
        else:
            return string

    def __init__(self, orthography_as_string, **kwargs):
        """Get core attributes; primarily, the orthography in various datatypes.
        """
        self.orthography_as_string = self.remove_all_white_space(orthography_as_string)
        self.orthography_as_list = self.get_orthography_as_list(
            self.orthography_as_string)
        self.orthography_as_dict = self.get_orthography_as_dict(
            self.orthography_as_string)
        self.lowercase = self.get_kwargs_arg(kwargs, 'lowercase', True)
        self.initial_glottal_stops = self.get_kwargs_arg(kwargs,
                                                    'initial_glottal_stops', True)

    def __repr__(self):
        return 'Orthography Object\n\t%s: %s\n\t%s: %s\n\n%s\n\n%s\n\n%s\n\n' % (
            '# graph types',
            len(self.orthography_as_list),
            '# graphs',
            len(self.orthography_as_dict),
            self.orthography_as_string,
            str(self.orthography_as_list),
            str(self.orthography_as_dict)
        )

    def get_orthography_as_list(self, orthography):
        """Returns orthography as a list of lists.

        E.g.,   u'[a,a\u0301],b,c,d'    becomes
                [[u'a',u'a\u0301'],[u'b'],[u'c'],[u'd']]

        """

        in_brackets = False
        result = u''
        for char in orthography:
            if char == u'[':
                in_brackets = True
                char = u''
            elif char == u']':
                in_brackets = False
                char = u''
            if in_brackets and char == u',':
                result += u'|'
            else:
                result += char
        temp = result.split(',')
        result = [item.split('|') for item in temp]
        return result

    def get_orthography_as_dict(self, orthography):
        """Returns orthography as a dictionary of graphs to ranks.

        E.g.,   u'[a,a\u0301],b,c,d'    becomes
                {u'a': 0, u'a\u0301': 0, u'b': 1, u'c': 2, u'd': 3}

        """

        in_brackets = False
        result = u''
        for char in orthography:
            if char == u'[':
                in_brackets = True
                char = u''
            elif char == u']':
                in_brackets = False
                char = u''
            if in_brackets and char == u',':
                result += u'|'
            else:
                result += char
        temp = result.split(',')
        result = {}
        for string in temp:
            for x in string.split('|'):
                result[x] = temp.index(string)
        return result

    def get_kwargs_arg(self, kwargs, key, default=None):
        """Return **kwargs[key] as a boolean, else return default."""
        if key in kwargs:
            return self.str2bool(kwargs[key])
        else:
            return default


class OrthographyTranslator:
    """Takes two Orthography instances and generates a translate method
    for converting strings form the first orthography to the second.
    """

    def __init__(self, input_orthography, output_orthography):
        self.input_orthography = input_orthography
        self.output_orthography = output_orthography

        # If input and output orthography objects are incompatible for
        #  translation, raise an OrthographyCompatibilityError.

        if [len(x) for x in self.input_orthography.orthography_as_list] != \
            [len(x) for x in self.output_orthography.orthography_as_list]:
            raise OrthographyCompatibilityError()

        self.prepare_regexes()

    def print_(self):
        for key in self.replacements:
            print('%s\t%s' % (key, self.replacements[key]))

    def get_replacements(self):
        """Create a dictionary with a key for each graph in the input
        orthography; each such key has as value a graph in the output orthography.

        Note: the input orthography may have more than one correspondent in the
        output orthography.  If this is the case, the default is for the system
        to use the first correspondent and ignore all subsequent ones.  This
        means that the order of graphs entered by the user on the Settings page
        may have unintended consequences for translation...
        """

        replacements = {}
        for i in range(len(self.input_orthography.orthography_as_list)):
            graph_type_list = self.input_orthography.orthography_as_list[i]
            for j in range(len(graph_type_list)):
                if graph_type_list[j] not in replacements:
                    replacements[graph_type_list[j]] = \
                        self.output_orthography.orthography_as_list[i][j]
        self.replacements = replacements

    def make_replacements_case_sensitive(self):
        """Update replacements to contain (programmatically) capitalized inputs
        and outputs.

        """

        new_replacements = {}
        for key in self.replacements:
            if not self.is_capital(key):
                capital = self.capitalize(key)
                if capital and capital not in self.replacements:
                    # if output orthography is lc, map uc input orthography
                    #  graphs to lc outputs, otherwise to uc outputs
                    if self.output_orthography.lowercase:
                        new_replacements[capital] = self.replacements[key]
                    else:
                        new_replacements[capital] = \
                            self.capitalize(self.replacements[key])
        self.replacements.update(new_replacements)

    def prepare_regexes(self):
        """Generate the regular expressions for doing character substitutions
        on the input string that will convert it into the output orthography.

        """

        # build a dictionary representing the mapping between input and output
        #  orthographies

        self.get_replacements()

        # 4 Possibilities for .lowercase attribute:
        #  1. io.lc = True, oo.lc = True: do nothing (Default)
        #  2. io.lc = True, oo.lc = False: do nothing (I guess we could
        #   capitalize the first word of sentences, but I'm not gonna right now ...)
        #  3. io.lc = False, oo.lc = True: map lc to lc and uc to lc
        #  4. io.lc = False, oo.lc = False: map lc to lc and uc to uc
        
        if not self.input_orthography.lowercase:
            self.make_replacements_case_sensitive()
        
        # Sort the keys according to length, longest words first, to prevent
        #  parts of n-graphs from being found-n-replaced before the n-graph is.
        
        self.replacement_keys = self.replacements.keys()
        self.replacement_keys.sort(lambda x,y:len(y)-len(x))
        
        # This is the pattern that does most of the work
        #  It matches a string in metalanguage tags ("<ml>" and "</ml>") or
        #  a key from self.replacements
        
        self.regex = re.compile(
            "<ml>.*?</ml>|(" + "|".join(self.replacement_keys) + ")"
        )
        
        # If the output orthography doesn't represent initial glottal stops,
        #  but the input orthography does, compile a regex to remove them from
        #  the input orthography.  That way, the replacement operation won't
        #  create initial glottal stops in the output (Glottal stops are assumed
        #  to be represented by "7".)

        if self.input_orthography.initial_glottal_stops and \
            not self.output_orthography.initial_glottal_stops:
            self.initial_glottal_stop_remover = re.compile("""( |^|(^| )'|")7""")

    # This and the constructor will be the only functions other modules will
    #  need to use;
    #  given a string in the input orthography,
    #  returns the string in the output orthography.

    def translate(self, text):
        """Takes text as input and returns it in the output orthography."""
        if self.input_orthography.lowercase:
            text = self.make_lowercase(text)
        if self.input_orthography.initial_glottal_stops and \
            not self.output_orthography.initial_glottal_stops:
            text = self.initial_glottal_stop_remover.sub("\\1", text)
        return self.regex.sub(lambda x:self.get_replacement(x.group()), text)

    # We can't just replace each match from self.regex with its value in
    #  self.replacements, because some matches are metalangauge strings that
    #  should not be altered (except to remove the <ml> tags...)

    def get_replacement(self, string):
        """If string DOES NOT begin with "<ml>" and end with "</ml>", then treat
        it as an object language input orthography graph and return
        self.replacements[string].

        If string DOES begin with "<ml>" and end with "</ml>", then treat it as 
        a metalanguage string and return it with the "<ml>" and "</ml>" tags.
        """
        if string[:4] == '<ml>' and string[-5:] == '</ml>':
            return string
        else:
            return self.replacements[string]

    # The built-in methods lower(), upper(), isupper(), capitalize(), etc.
    #  don't do exactly what we need here

    def make_lowercase(self, string):
        """Return the string in lowercase except for the substrings enclosed
        in metalanguage tags."""
        patt = re.compile("<ml>.*?</ml>|.")
        def get_replacement(string):
            if string[:4] == '<ml>' and string[-5:] == '</ml>':
                return string
            else:
                return string.lower()
        return patt.sub(lambda x:get_replacement(x.group()), string)

    def capitalize(self, str):
        """If str contains an alpha character, return str with first alpha
        capitalized; else, return empty string.
        """
        result = ""
        for i in range(len(str)):
            if str[i].isalpha(): return str[:i] + str[i:].capitalize()
        return result

    def is_capital(self, str):
        """Returns true only if first alpha character found is uppercase."""
        for char in str:
            if char.isalpha():
                return char.isupper()
        return False


class OrthographyCompatibilityError(Exception):
    def __str__(self):
        return 'An OrthographyTranslator could not be created: the two input ' + \
        'orthographies are incompatible.'


class CustomSorter():
    """Takes an Orthography instance and generates a method for sorting a list
    of Forms according to the order of graphs in the orthography.

    """

    def __init__(self, orthography):
        self.orthography = orthography

    def remove_white_space(self, word):
        return word.replace(' ', '').lower()

    def get_integer_tuple(self, word):
        """Takes a word and returns a tuple of integers representing the rank of
        each graph in the word.  A list of such tuples can then be quickly
        sorted by a Pythonic list's sort() method.

        Since graphs are not necessarily Python characters, we have to replace
        each graph with its rank, starting with the longest graphs first.
        """

        graphs = self.orthography.orthography_as_dict.keys()
        graphs.sort(key=len)
        graphs.reverse()

        for graph in graphs: 
            word = unicode(word.replace(graph,
                            '%s,' % self.orthography.orthography_as_dict[graph]))

        # Filter out anything that is not a digit or a comma
        word = filter(lambda x: x in '01234546789,', word)

        return tuple([int(x) for x in word[:-1].split(',') if x])

    def sort(self, forms):
        """Take a list of OLD Forms and return it sorted according to the order
        of graphs in CustomSorter().orthography.
        """
        temp = [(self.get_integer_tuple(self.remove_white_space(form.transcription)),
                 form) for form in forms]
        temp.sort()
        return [x[1] for x in temp]
