#!/usr/bin/env python
'''
Importing data from XML provided by Conference Centre for Economics, France
'''
from __future__ import absolute_import, division, print_function

# Make sure we can import stuff from util/
# This script needs to be run from the root of the DeepSpeech repository
import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))

from util.importers import get_importers_parser, get_validate_label, get_counter, get_imported_samples, print_import_report

import csv
import sox
import argparse
import subprocess
import progressbar
import unicodedata
import math
import decimal
import re
import xml.etree.ElementTree as ET

from os import path
from multiprocessing import Pool
from util.downloader import SIMPLE_BAR
from util.text import Alphabet
from util.helpers import secs_to_hours
from num2words import num2words

FIELDNAMES = ['wav_filename', 'wav_filesize', 'transcript']
SAMPLE_RATE = 16000
CHANNELS = 1
BIT_DEPTH = 16
MAX_SECS = 10

def maybe_normalize_for_digits(label):
    # first, try to identify numbers like "50 000", "260 000"
    if ' ' in label:
        if any(s.isdigit() for s in label):
            thousands = re.compile(r'(\d{1,3}(?:\s*\d{3})*(?:,\d+)?)')
            maybe_thousands = thousands.findall(label)
            if len(maybe_thousands) > 0:
                while True:
                    (label, r) = re.subn(r'(\d)\s(\d{3})', '\\1\\2', label)
                    if r == 0:
                        break

    new_label = []
    for s in label.split(' '):
        if any(i.isdigit() for i in s):
            s = s.replace(',', '.') # num2words requires '.' for floats
            s = s.replace('"', '')  # clean some data, num2words would choke on 1959"

            last_c = s[-1]
            if not last_c.isdigit(): # num2words will choke on '0.6.', '24 ?'
                s = s[:-1]

            if any(i.isalpha() for i in s): # So we have any(isdigit()) **and** any(sialpha), like "3D"
                ns = []
                for c in s:
                    nc = c
                    if c.isdigit(): # convert "3" to "trois-"
                        nc = num2words(c, lang='fr') + "-"
                    ns.append(nc)
                s = "".join(s)
            else:
                try:
                    s = num2words(s, lang='fr')
                except decimal.InvalidOperation as ex:
                    print('decimal.InvalidOperation: "{}"'.format(s))
                    raise ex
        new_label.append(s)
    return " ".join(new_label)

def maybe_normalize_for_specials_chars(label):
    label = label.replace('%', 'pourcents')
    label = label.replace('/', ', ') # clean intervals like 2019/2022 to "2019 2022"
    label = label.replace('-', ', ') # clean intervals like 70-80 to "70 80"
    return label

def maybe_normalize_for_anglicisms(label):
    label = label.replace('B2B', 'B to B')
    label = label.replace('B2C', 'B to C')
    return label

def maybe_normalize(label):
    label = maybe_normalize_for_specials_chars(label)
    label = maybe_normalize_for_anglicisms(label)
    label = maybe_normalize_for_digits(label)
    return label

def one_sample(sample):
    file_size = -1
    frames = 0

    audio_source = sample[0]
    wav_root = sample[1]

    start_time = sample[2]
    duration = sample[3]
    label = label_filter_fun(sample[4])
    sample_id = sample[5]

    wav_filename = os.path.join(wav_root, os.path.basename(audio_source.replace('.wav', '_{:06}.wav'.format(sample_id))))
    #print(" ".join(['ffmpeg', '-i', audio_source, '-ss', str(start_time), '-t', str(duration), '-c', 'copy', wav_filename]))

    if not path.exists(wav_filename):
        subprocess.check_output(['ffmpeg', '-i', audio_source, '-ss', str(start_time), '-t', str(duration), '-c', 'copy', wav_filename], stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    file_size = path.getsize(wav_filename)
    frames = int(subprocess.check_output(['soxi', '-s', wav_filename], stderr=subprocess.STDOUT))

    counter = get_counter()
    rows = []

    if file_size == -1:
        # Excluding samples that failed upon conversion
        counter['failed'] += 1
    elif label is None:
        # Excluding samples that failed on label validation
        counter['invalid_label'] += 1
    elif int(frames/SAMPLE_RATE*1000/10/2) < len(str(label)):
        # Excluding samples that are too short to fit the transcript
        counter['too_short'] += 1
    elif frames/SAMPLE_RATE > MAX_SECS:
        # Excluding very long samples to keep a reasonable batch-size
        counter['too_long'] += 1
    else:
        # This one is good - keep it for the target CSV
        rows.append((os.path.split(wav_filename)[-1], file_size, label))
    counter['all'] += 1
    counter['total_time'] += frames

    return (counter, rows)

def _maybe_import_data(xml_file, audio_source):
    wav_root = os.path.splitext(os.path.abspath(xml_file))[0]
    if not os.path.exists(wav_root):
        os.makedirs(wav_root)

    # Get audiofile path and transcript for each sentence in tsv
    samples = []
    tree = ET.parse(xml_file)
    root = tree.getroot()
    seq_id        = 0
    this_time     = 0.0
    this_duration = 0.0
    prev_time     = 0.0
    prev_duration = 0.0
    this_text     = ""
    for child in root:
        if child.tag == 'row':
            cur_time     = float(child.attrib['timestamp'])
            cur_duration = float(child.attrib['timedur'])
            cur_text     = child.text

            if this_time == 0.0:
                this_time = cur_time

            delta    = cur_time - (prev_time + prev_duration)
            # rel_tol value is made from trial/error to try and compromise between:
            # - cutting enough to skip missing words
            # - not too short, not too long sentences
            is_close = math.isclose(cur_time, this_time + this_duration, rel_tol=2.5e-4)
            is_short = ((this_duration + cur_duration + delta) < MAX_SECS)

            # when the previous element is close enough **and** this does not
            # go over MAX_SECS, we append content
            if (is_close and is_short):
                this_duration += cur_duration + delta
                this_text     += cur_text
            else:
                samples.append((audio_source, wav_root, this_time, this_duration, this_text, seq_id))

                this_time     = cur_time
                this_duration = cur_duration
                this_text     = cur_text

                seq_id += 1

            prev_time     = cur_time
            prev_duration = cur_duration

    # Keep track of how many samples are good vs. problematic
    counter = get_counter()
    num_samples = len(samples)
    rows = []

    print('Processing XML data')
    pool = Pool()
    bar = progressbar.ProgressBar(max_value=num_samples, widgets=SIMPLE_BAR)
    for i, processed in enumerate(pool.imap_unordered(one_sample, samples), start=1):
        counter += processed[0]
        rows += processed[1]
        bar.update(i)
    bar.update(num_samples)
    pool.close()
    pool.join()


    target_csv_template = os.path.join(wav_root, os.path.basename(xml_file).replace('.xml', '_{}.csv'))
    with open(target_csv_template.format('train'), 'w') as train_csv_file:  # 80%
        with open(target_csv_template.format('dev'), 'w') as dev_csv_file:  # 10%
            with open(target_csv_template.format('test'), 'w') as test_csv_file:  # 10%
                train_writer = csv.DictWriter(train_csv_file, fieldnames=FIELDNAMES)
                train_writer.writeheader()
                dev_writer = csv.DictWriter(dev_csv_file, fieldnames=FIELDNAMES)
                dev_writer.writeheader()
                test_writer = csv.DictWriter(test_csv_file, fieldnames=FIELDNAMES)
                test_writer.writeheader()

                bar = progressbar.ProgressBar(max_value=len(rows), widgets=SIMPLE_BAR)
                for i, item in enumerate(bar(rows)):
                    i_mod = i % 10
                    if i_mod == 0:
                        writer = test_writer
                    elif i_mod == 1:
                        writer = dev_writer
                    else:
                        writer = train_writer
                    writer.writerow({'wav_filename': item[0], 'wav_filesize': item[1], 'transcript': item[2]})

    imported_samples = get_imported_samples(counter)
    assert counter['all'] == num_samples
    assert len(rows) == imported_samples

    print_import_report(counter, SAMPLE_RATE, MAX_SECS)

def _maybe_convert_wav(mp3_filename, wav_filename):
    if not path.exists(wav_filename):
        print('Converting {} to WAV file: {}'.format(mp3_filename, wav_filename))
        transformer = sox.Transformer()
        transformer.convert(samplerate=SAMPLE_RATE, n_channels=CHANNELS, bitdepth=BIT_DEPTH)
        try:
            transformer.build(mp3_filename, wav_filename)
        except sox.core.SoxError:
            pass


if __name__ == "__main__":
    PARSER = get_importers_parser(description='Import XML from Conference Centre for Economics, France')
    PARSER.add_argument('--audio', required=True, help='Path to the original MP3 audio file')
    PARSER.add_argument('--xml', required=True, help='Path to the original XML file')
    PARSER.add_argument('--filter_alphabet', help='Exclude samples with characters not in provided alphabet')
    PARSER.add_argument('--normalize', action='store_true', help='Converts diacritic characters to their base ones')

    PARAMS = PARSER.parse_args()
    validate_label = get_validate_label(PARAMS)
    ALPHABET = Alphabet(PARAMS.filter_alphabet) if PARAMS.filter_alphabet else None

    def label_filter_fun(label):
        if PARAMS.normalize:
            label = unicodedata.normalize("NFKD", label.strip()) \
                .encode("ascii", "ignore") \
                .decode("ascii", "ignore")
        label = maybe_normalize(label)
        label = validate_label(label)
        if ALPHABET and label:
            try:
                ALPHABET.encode(label)
            except KeyError:
                label = None
        return label

    """ Take a audio file, and optionally convert it to 16kHz WAV """
    wav_filename = path.splitext(PARAMS.audio)[0] + ".wav"
    _maybe_convert_wav(PARAMS.audio, wav_filename)

    _maybe_import_data(PARAMS.xml, wav_filename)
