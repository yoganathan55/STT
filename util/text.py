from __future__ import absolute_import, division, print_function

import codecs
import numpy as np
import re
import struct
import unicodedata

from util.flags import FLAGS
from six.moves import range

class Alphabet(object):
    def __init__(self, config_file):
        self._config_file = config_file
        self._label_to_str = {}
        self._str_to_label = {}
        self._size = 0
        if config_file:
            with codecs.open(config_file, 'r', 'utf-8') as fin:
                for line in fin:
                    if line[0:2] == '\\#':
                        line = '#\n'
                    elif line[0] == '#':
                        continue
                    self._label_to_str[self._size] = line[:-1] # remove the line ending
                    self._str_to_label[line[:-1]] = self._size
                    self._size += 1

    def _string_from_label(self, label):
        return self._label_to_str[label]

    def _label_from_string(self, string):
        try:
            return self._str_to_label[string]
        except KeyError as e:
            raise KeyError(
                'ERROR: Your transcripts contain characters (e.g. \'{}\') which do not occur in data/alphabet.txt! Use ' \
                'util/check_characters.py to see what characters are in your [train,dev,test].csv transcripts, and ' \
                'then add all these to data/alphabet.txt.'.format(string)
            ).with_traceback(e.__traceback__)

    def has_char(self, char):
        return char in self._str_to_label

    def encode(self, string):
        res = []
        for char in string:
            res.append(self._label_from_string(char))
        return res

    def decode(self, labels):
        res = ''
        for label in labels:
            res += self._string_from_label(label)
        return res

    def serialize(self):
        # Serialization format is a sequence of (key, value) pairs, where key is
        # a uint16_t and value is a uint16_t length followed by `length` UTF-8
        # encoded bytes with the label.
        res = bytearray()

        # We start by writing the number of pairs in the buffer as uint16_t.
        res += struct.pack('<H', self._size)
        for key, value in self._label_to_str.items():
            value = value.encode('utf-8')
            # struct.pack only takes fixed length strings/buffers, so we have to
            # construct the correct format string with the length of the encoded
            # label.
            res += struct.pack('<HH{}s'.format(len(value)), key, len(value), value)
        return bytes(res)

    def size(self):
        return self._size

    def config_file(self):
        return self._config_file


class UTF8Alphabet(object):
    @staticmethod
    def _string_from_label(_):
        assert False

    @staticmethod
    def _label_from_string(_):
        assert False

    @staticmethod
    def encode(string):
        # 0 never happens in the data, so we can shift values by one, use 255 for
        # the CTC blank, and keep the alphabet size = 256
        return np.frombuffer(string.encode('utf-8'), np.uint8).astype(np.int32) - 1

    @staticmethod
    def decode(labels):
        # And here we need to shift back up
        return bytes(np.asarray(labels, np.uint8) + 1).decode('utf-8', errors='replace')

    @staticmethod
    def size():
        return 255

    @staticmethod
    def serialize():
        res = bytearray()
        res += struct.pack('<h', 255)
        for i in range(255):
            # Note that we also shift back up in the mapping constructed here
            # so that the native client sees the correct byte values when decoding.
            res += struct.pack('<hh1s', i, 1, bytes([i+1]))
        return bytes(res)

    @staticmethod
    def deserialize(buf):
        size = struct.unpack('<I', buf)[0]
        assert size == 255
        return UTF8Alphabet()

    @staticmethod
    def config_file():
        return ''


def text_to_char_array(series, alphabet):
    r"""
    Given a Pandas Series containing transcript string, map characters to
    integers and return a numpy array representing the processed string.
    """
    try:
        transcript = np.asarray(alphabet.encode(series['transcript']))
        if len(transcript) == 0:
            raise ValueError('While processing: {}\nFound an empty transcript! You must include a transcript for all training data.'.format(series['wav_filename']))
        return transcript
    except KeyError as e:
        # Provide the row context (especially wav_filename) for alphabet errors
        raise ValueError('While processing: {}\n{}'.format(series['wav_filename'], e))


# The following code is from: http://hetland.org/coding/python/levenshtein.py

# This is a straightforward implementation of a well-known algorithm, and thus
# probably shouldn't be covered by copyright to begin with. But in case it is,
# the author (Magnus Lie Hetland) has, to the extent possible under law,
# dedicated all copyright and related and neighboring rights to this software
# to the public domain worldwide, by distributing it under the CC0 license,
# version 1.0. This software is distributed without any warranty. For more
# information, see <http://creativecommons.org/publicdomain/zero/1.0>

def levenshtein(a, b):
    "Calculates the Levenshtein distance between a and b."
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a, b = b, a
        n, m = m, n

    current = list(range(n+1))
    for i in range(1, m+1):
        previous, current = current, [i]+[0]*n
        for j in range(1, n+1):
            add, delete = previous[j]+1, current[j-1]+1
            change = previous[j-1]
            if a[j-1] != b[i-1]:
                change = change + 1
            current[j] = min(add, delete, change)

    return current[n]

# Validate and normalize transcriptions. Returns a cleaned version of the label
# or None if it's invalid.
def validate_label(label):
    # For now we can only handle [a-z ']
    if re.search(r"[0-9]|[(<\[\]&*{]", label) is not None:
        return None

    label = label.replace("-", " ")
    label = label.replace("_", " ")
    label = re.sub("[ ]{2,}", " ", label)
    label = label.replace(".", "")
    label = label.replace(",", "")
    label = label.replace(";", "")
    label = label.replace("?", "")
    label = label.replace("!", "")
    label = label.replace(":", "")
    label = label.replace("\"", "")
    label = label.strip()
    label = label.lower()

    return label if label else None

def validate_label_fr(label):
    label = unicodedata.normalize('NFKC', label)

    if re.search(r"[0-9]", label) is not None:
        return None

    if '*' in label:
        return None

    skip_foreign_chars = [
        'い',
        'た',
        'つ',
        'ぬ',
        'の',
        '乃',
        '京',
        '北',
        '扬',
        '星',
        '术',
        '杜',
        '美',
        '馆',
    ]

    for skip in skip_foreign_chars:
        if skip in label:
            return None

    label = label.strip()
    label = label.lower()

    label = label.replace("=", "")
    label = label.replace("|", "")
    label = label.replace("-", " ")
    label = label.replace("–", " ")
    label = label.replace("—", " ")
    label = label.replace("’", " ")
    label = label.replace("^", "e")
    #label = label.replace("'", " ")
    label = label.replace("º", "degré")
    label = label.replace("…", " ")
    label = label.replace("_", " ")
    label = label.replace(".", "")
    label = label.replace(",", "")
    label = label.replace("?", "")
    label = label.replace("!", "")
    label = label.replace("\"", "")
    label = label.replace("(", "")
    label = label.replace(")", "")
    label = label.replace("{", "")
    label = label.replace("}", "")
    label = label.replace("/", " ")
    label = label.replace(":", "")
    label = label.replace(";", "")
    label = label.replace("«", "")
    label = label.replace("»", "")
    label = label.replace("%", "")
    label = label.replace("`", "")
    label = label.replace("°", "degré")
    label = label.replace("+", "plus")
    label = label.replace("±", "plus ou moins")
    label = label.replace("·", "")
    label = label.replace("×", "")

    label = label.replace("ă", "a")
    label = label.replace("ắ", "a")
    label = label.replace("ầ", "a")
    label = label.replace("å", "a")
    label = label.replace("ä", "a")
    label = label.replace("ą", "a")
    label = label.replace("ā", "a")
    label = label.replace("ả", "a")
    label = label.replace("ạ", "a")
    label = label.replace("ậ", "a")
    #label = label.replace("æ", "")
    label = label.replace("ć", "c")
    label = label.replace("č", "c")
    label = label.replace("ċ", "c")
    label = label.replace("đ", "d")
    label = label.replace("ḍ", "d")
    label = label.replace("ð", "o")
    label = label.replace("ễ", "e")
    label = label.replace("ě", "e")
    label = label.replace("ė", "e")
    label = label.replace("ę", "e")
    label = label.replace("ē", "e")
    label = label.replace("ệ", "e")
    label = label.replace("ğ", "g")
    label = label.replace("ġ", "g")
    label = label.replace("ħ", "h")
    label = label.replace("ʻ", "")
    label = label.replace("ì", "i")
    label = label.replace("ī", "i")
    label = label.replace("ị", "")
    label = label.replace("ı", "un")
    label = label.replace("ľ", "l'")
    label = label.replace("ļ", "l")
    label = label.replace("ł", "")
    label = label.replace("ǹ", "n")
    label = label.replace("ň", "n")
    label = label.replace("ṅ", "n")
    label = label.replace("ņ", "n")
    label = label.replace("ṇ", "n")
    label = label.replace("ŏ", "o")
    label = label.replace("ồ", "o")
    label = label.replace("ổ", "o")
    label = label.replace("ő", "o")
    label = label.replace("õ", "o")
    label = label.replace("ø", "o")
    label = label.replace("ǫ", "o")
    label = label.replace("ơ", "")
    label = label.replace("ợ", "")
    label = label.replace("ộ", "o")
    label = label.replace("ř", "r")
    label = label.replace("ś", "s")
    label = label.replace("š", "s")
    label = label.replace("ş", "s")
    label = label.replace("ṣ", "s")
    label = label.replace("ș", "s")
    label = label.replace("ß", "ss")
    label = label.replace("ť", "t")
    label = label.replace("ṭ", "t")
    label = label.replace("ț", "t")
    label = label.replace("ṯ", "t")
    label = label.replace("ú", "u")
    label = label.replace("ų", "u")
    label = label.replace("ư", "u")
    label = label.replace("ử", "u")
    label = label.replace("ʉ", "")
    label = label.replace("ý", "y")
    label = label.replace("ỳ", "y")
    label = label.replace("ź", "z")
    label = label.replace("ž", "z")
    label = label.replace("ż", "z")
    label = label.replace("þ", "")
    label = label.replace("ʼ", "")
    label = label.replace("ʾ", "")
    label = label.replace("ʿ", "")
    label = label.replace("ǃ", "")
    label = label.replace("δ", "delta")
    label = label.replace("ζ", "")
    label = label.replace("κ", "kappa")
    label = label.replace("ν", "")
    label = label.replace("π", "pi")
    label = label.replace("σ", "sigma")
    label = label.replace("τ", "tau")
    label = label.replace("υ", "")
    label = label.replace("ω", "omega")
    label = label.replace("а", "a")
    label = label.replace("г", "r")
    label = label.replace("е", "e")
    label = label.replace("з", "")
    label = label.replace("и", "")
    label = label.replace("к", "")
    label = label.replace("м", "")
    label = label.replace("н", "")
    label = label.replace("ҫ", "c")
    label = label.replace("я", "")
    label = label.replace("א", "")
    label = label.replace("ደ", "")
    label = label.replace("ጠ", "")

    label = label.replace("α", "alpha")
    label = label.replace("γ", "gamma")
    label = label.replace("μ", "mu")


    label = label.replace("‘", "")
    label = label.replace("“", "")
    label = label.replace("”", "")
    label = label.replace("„", "")
    label = label.replace("†", "")
    label = label.replace("′", "")
    label = label.replace("‹", "")
    label = label.replace("›", "")
    label = label.replace("⁄", "")
    label = label.replace("∅", "")
    label = label.replace("∈", "")
    label = label.replace("∞", "")
    label = label.replace("≥", "")
    label = label.replace("☉", "")
    label = label.replace("ː", "")
    label = label.replace("§", "paragraphe")
    label = label.replace("$", "dollars")
    label = label.replace("£", "livres")
    label = label.replace("€", "euros")
    label = label.replace("β", "beta")
    label = label.replace("σ", "gamma")
    label = label.replace("½", "demi")
    label = label.replace("¼", "quart")
    label = label.replace("&", "et")
    label = label.replace("æ", "é")
    label = label.replace("nºˢ", "numéros")
    label = label.replace("nº", "numéro")
    label = label.replace("n°", "numéro")
    label = label.replace("         ", " ")
    label = label.replace("        ", " ")
    label = label.replace("       ", " ")
    label = label.replace("      ", " ")
    label = label.replace("     ", " ")
    label = label.replace("    ", " ")
    label = label.replace("   ", " ")
    label = label.replace("  ", " ")

    label = label.replace(u"\u0301", "")
    label = label.replace(u"\u0307", "")
    label = label.replace(u"\u0320", "")
    label = label.replace(u"\u0331", "")

    label = label.strip()
    label = label.lower()

    return label if label else None
