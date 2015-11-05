#!/usr/bin/env python
"""Small library for working with MinION data
"""

from __future__ import print_function
from numpy import log2, power
from itertools import islice, izip
import subprocess
from serviceCourse.sequenceTools import reverse_complement
from serviceCourse.parsers import read_fasta
import os
import h5py
import sys


def kmer_iterator(dna, k):
    for i in range(len(dna)):
        kmer = dna[i:(i+k)]
        if len(kmer) == k:
            yield kmer


def orient_read_with_bwa(bwa_index, query):
    # align with bwa
    bwa_dir = "/Users/Rand/projects/BGCs/submodules/bwa/"  # todo require bwa in path remove this
    command = "{bwaDir}bwa mem -x ont2d {index} {query}".format(bwaDir=bwa_dir, index=bwa_index,
                                                                query=query)
    # this is a small SAM file that comes from bwa
    aln = subprocess.check_output(command.split())
    aln = aln.split("\t") # split

    return int(aln[7])

def get_bwa_index(reference, dest):
    bwa = Bwa(reference)
    bwa.build_index(dest)
    bwa_ref_index = dest + "temp_bwaIndex"
    return bwa_ref_index


def make_npRead_and_2d_seq(fast5, npRead_dest, twod_read_dest):
    """process a MinION .fast5 file into a npRead file for use with signalAlign also extracts
    the 2D read into fasta format
    """
    # setup
    out_file = open(npRead_dest, 'w')
    temp_fasta = open(twod_read_dest, "w")

    # load and transform
    npRead = NanoporeRead(fast5)
    npRead.get_2D_event_map()
    npRead.transform_events(npRead.template_events, npRead.template_drift)
    npRead.transform_events(npRead.complement_events, npRead.complement_drift)

    # output

    # line 1
    print(len(npRead.twoD_read_sequence), end=' ', file=out_file) # 2D read length
    print(len(npRead.template_events), end=' ', file=out_file)    # nb of template events
    print(len(npRead.complement_events), end=' ', file=out_file)  # nb of complement events
    print(npRead.template_scale, end=' ', file=out_file)          # template scale
    print(npRead.template_shift, end=' ', file=out_file)          # template shift
    print(npRead.template_var, end=' ', file=out_file)            # template var
    print(npRead.template_scale_sd, end=' ', file=out_file)       # template scale_sd
    print(npRead.template_var_sd, end=' ', file=out_file)         # template var_sd
    print(npRead.complement_scale, end=' ', file=out_file)        # complement scale
    print(npRead.complement_shift, end=' ', file=out_file)        # complement shift
    print(npRead.complement_var, end=' ', file=out_file)          # complement var
    print(npRead.complement_scale_sd, end=' ', file=out_file)     # complement scale_sd
    print(npRead.complement_var_sd, end='\n', file=out_file)      # complement var_sd

    # line 2
    print(npRead.twoD_read_sequence, end='\n', file=out_file)

    # line 3
    for _ in npRead.template_event_map:
        print(_, end=' ', file=out_file)
    print("", end="\n", file=out_file)

    # line 4
    for mean, start, stdev, length in npRead.template_events:
        print(mean, stdev, length, sep=' ', end=' ', file=out_file)
    print("", end="\n", file=out_file)

    # line 5
    for _ in npRead.complement_event_map:
        print(_, end=' ', file=out_file)
    print("", end="\n", file=out_file)

    # line 6
    for mean, start, stdev, length in npRead.complement_events:
        print(mean, stdev, length, sep=' ', end=' ', file=out_file)
    print("", end="\n", file=out_file)

    # make temp read
    npRead.extract_2d_read(temp_fasta)
    npRead.close()
    return


def make_temp_sequence(fasta, forward, destination):
    """extract the sequence from a fasta and put into a simple file that is used by signalAlign
    """
    out_file = open(destination, "w")
    for header, comment, sequence in read_fasta(fasta):
        if forward is False:
            sequence = reverse_complement(sequence)
        print(sequence, end='\n', file=out_file)


class Bwa(object):
    """run BWA easily
    """
    def __init__(self, target):
        self.target = target
        self.bwa_dir = "/Users/Rand/projects/BGCs/submodules/bwa/"
        self.db_handle = ''

    def build_index(self, destination):
        # make a place to put the database
        path_to_bwa_index = destination

        # build database
        self.db_handle = path_to_bwa_index + '/temp_bwaIndex'
        os.system("{0}bwa index -p {1} {2}".format(self.bwa_dir, self.db_handle, self.target))

    def run(self, query):
        # run alignment
        os.system("{0}bwa mem -x ont2d {1} {2}".format(self.bwa_dir, self.db_handle, query))


def get_proceding_kmers(kmer, alphabet="ACGT"):
    proceding_kmers = []
    suffix = kmer[1:]
    for n in alphabet:
        proceding_kmers.append(n + suffix)
    return proceding_kmers


class NanoporeRead(object):
    def __init__(self, fast_five_file):
        # load the fast5
        self.fastFive = h5py.File(fast_five_file, 'r')

        # get the 2D read sequence
        twoD_read_sequence_address = "/Analyses/Basecall_2D_000/BaseCalled_2D/Fastq"

        #self.twoD_read_sequence = self.fastFive[twoD_read_sequence_address][()].split()[2]
        if twoD_read_sequence_address in self.fastFive:
            self.twoD_read_sequence = self.fastFive[twoD_read_sequence_address][()].split()[2]
            self.twoD_id = self.fastFive[twoD_read_sequence_address][()].split()[0:2][0][1:]

        # get the 2D alignment table
        twoD_alignment_table_address = "/Analyses/Basecall_2D_000/BaseCalled_2D/Alignment"
        if twoD_alignment_table_address in self.fastFive:
            self.twoD_alignment_table = self.fastFive[twoD_alignment_table_address]
            self.kmer_length = len(self.twoD_alignment_table[0][2])

        # need the event tables for comparing probs
        template_event_table_address = '/Analyses/Basecall_2D_000/BaseCalled_template/Events'
        if template_event_table_address in self.fastFive:
            self.template_event_table = self.fastFive[template_event_table_address]
            self.template_events = [[e[0], e[1], e[2], e[3]]  # mean, start, stdev, length
                                    for e in self.template_event_table]

        complement_event_table_address = '/Analyses/Basecall_2D_000/BaseCalled_complement/Events'
        if complement_event_table_address in self.fastFive:
            self.complement_event_table = self.fastFive[complement_event_table_address]
            self.complement_events = [[e[0], e[1], e[2], e[3]]  # mean, start, stdev, length
                                      for e in self.complement_event_table]

        # need the scale and shift
        template_model_address = "/Analyses/Basecall_2D_000/BaseCalled_template/Model"
        if template_model_address in self.fastFive:
            self.template_scale = self.fastFive[template_model_address].attrs["scale"]
            self.template_shift = self.fastFive[template_model_address].attrs["shift"]
            self.template_drift = self.fastFive[template_model_address].attrs["drift"]
            self.template_var = self.fastFive[template_model_address].attrs["var"]
            self.template_scale_sd = self.fastFive[template_model_address].attrs["scale_sd"]
            self.template_var_sd = self.fastFive[template_model_address].attrs["var_sd"]

        complement_model_address = "/Analyses/Basecall_2D_000/BaseCalled_complement/Model"
        if complement_model_address in self.fastFive:
            self.complement_scale = self.fastFive[complement_model_address].attrs["scale"]
            self.complement_shift = self.fastFive[complement_model_address].attrs["shift"]
            self.complement_drift = self.fastFive[complement_model_address].attrs["drift"]
            self.complement_var = self.fastFive[complement_model_address].attrs["var"]
            self.complement_scale_sd = self.fastFive[complement_model_address].attrs["scale_sd"]
            self.complement_var_sd = self.fastFive[complement_model_address].attrs["var_sd"]

        self.template_event_map = []
        self.complement_event_map = []

    def get_strand_event_map(self):
        """Maps the events from the template and complement strands to their base called kmers the map
        generated by this function is called the "strand_event_map" because it only works for mapping the
        strand read (1D read) to to it's events
        """
        def make_map(events):
            event_map = [0]
            previous_prob = 0
            for i, line in islice(enumerate(events), 1, None):
                move = line[6]
                this_prob = line[8]
                if move == 1:
                    event_map.append(i)
                if move > 1:
                    for skip in xrange(move - 1):
                        event_map.append(i - 1)
                    event_map.append(i)
                if move == 0:
                    if this_prob > previous_prob:
                        event_map[-1] = i
                previous_prob = this_prob
            final_event_index = [event_map[-1]]
            padding = final_event_index * 5 # make this a kmer-measured thing
            event_map = event_map + padding
            return event_map
        self.template_strand_event_map = make_map(self.template_event_table)
        self.complement_strand_event_map = make_map(self.complement_event_table)
        return

    def get_2D_event_map(self):
        """Maps the kmers in the 2D basecalled read to events in the template and complement strand reads
        """
        # initialize
        alignment_row = 0
        prev_alignment_kmer = ''
        nb_template_gaps = 0
        previous_complement_event = None
        previous_template_event = None

        # go thought the kmers in the read sequence and match up the events
        for i, seq_kmer in enumerate(kmer_iterator(self.twoD_read_sequence, self.kmer_length)):
            # assign the current row's kmer
            current_alignment_kmer = self.twoD_alignment_table[alignment_row][2]

            # in the situation where there is a repeat kmer in the alignment then
            # we want to pick the best event to kmer alignment, TODO implement this
            # right now we just use the first alignment
            while current_alignment_kmer == prev_alignment_kmer:
                alignment_row += 1
                current_alignment_kmer = self.twoD_alignment_table[alignment_row][2]

            # a match
            if seq_kmer == current_alignment_kmer:
                template_event = self.twoD_alignment_table[alignment_row][0]
                complement_event = self.twoD_alignment_table[alignment_row][1]

                # handle template event
                # if there is a gap, count it and don't add anything to the map
                if template_event == -1:

                    nb_template_gaps += 1
                # if there is an aligned event
                if template_event != -1:
                    # if it is an aligned event and there are no gaps, add it
                    # to the map
                    if nb_template_gaps == 0:

                        self.template_event_map.append(template_event)
                        # update
                        previous_template_event = template_event
                    # if there were gaps in the alignment we have to add 'best guess'
                    # event alignments to the map which is the current aligned event
                    if nb_template_gaps > 0:

                        self.template_event_map += [template_event] * (nb_template_gaps + 1)
                        # reset template gaps
                        nb_template_gaps = 0
                        # update
                        previous_template_event = template_event

                # handle complement event
                # if there is a gap, add the last aligned complement event to the map
                if complement_event == -1:
                    self.complement_event_map.append(previous_complement_event)
                # if there is an aligned complement event add it to the map
                if complement_event != -1:
                    self.complement_event_map.append(complement_event)
                    # update the most recent aligned complement event
                    previous_complement_event = complement_event

                # update previous alignment kmer and increment alignment row
                prev_alignment_kmer = current_alignment_kmer
                alignment_row += 1
                continue

            # not a match, meaning that this kmer in the read sequence is not
            # in the event alignment but we need to assign an event to it so
            # we use the heuristic that we use the alignment of the most
            # recent aligned events to this base
            if seq_kmer != current_alignment_kmer:
                self.template_event_map.append(previous_template_event)
                self.complement_event_map.append(previous_complement_event)
                continue

        # fill in the final events for the partial last kmer
        for _ in xrange(self.kmer_length - 1):
            self.template_event_map += [previous_template_event] * (nb_template_gaps + 1)
            self.complement_event_map.append(previous_complement_event)
            nb_template_gaps = 0

        # check that we have mapped all of the bases in the 2D read
        assert(len(self.template_event_map) == len(self.twoD_read_sequence))
        assert(len(self.complement_event_map) == len(self.twoD_read_sequence))
        return

    def list_twoD_event_map(self):
        """Print out tab separated mapping of the strand events to the 2D kmers
        """
        for te, ce, kmer in izip(self.template_event_map, self.complement_event_map,
                                 kmer_iterator(self.twoD_read_sequence, self.kmer_length)):
            print(te, ce, kmer, sep="\t")

    def transform_events(self, events, drift):
        """Adjust event means by drift
        """
        start_time = events[0][1]
        for event in events:
            delta_time = event[1] - start_time
            event[0] -= (delta_time * drift)
        return

    def extract_2d_read(self, destination):
        print(">", self.twoD_id, sep="", end="\n", file=destination)
        print(self.twoD_read_sequence, end="\n", file=destination)

    def close(self):
        self.fastFive.close()


class NanoporeModel(object):
    def __init__(self, fast5File):
        self.fastFive = h5py.File(fast5File, "r")
        self.stay_prob = 0
        self.skip_prob_bins = []
        self.model_name = ''
        self.model = None

    def export_model(self, destination_path):
        """Exports the model to a file. Format:
        line 1: [correlation coefficient] [level_mean] [level_sd] [noise_mean] 
                    [noise_sd] [noise_lambda ] (.../kmer) \n
        line 2: skip bins \n
        line 3: [correlation coefficient] [level_mean] [level_sd, scaled] 
                    [noise_mean] [noise_sd] [noise_lambda ] (.../kmer) \n
        """
        def calculate_lambda(noise_mean, noise_stdev):
            return (power(noise_mean, 3)) / (power(noise_stdev, 2))

        if self.model is None:
            print("This method is meant to be used as part of the child class TemplateModel or ComplementModel",
                  file=sys.stderr)
        # output the model for cPecan to a file
        model_path = destination_path + self.model_name
        out_file = open(model_path, 'w')

        # line 1
        print("0", end=' ', file=out_file) # placeholder for correlation parameter
        for kmer, level_mean, level_stdev, sd_mean, sd_stdev, weight in self.model:
            lam = calculate_lambda(sd_mean, sd_stdev)
            print(level_mean, level_stdev, sd_mean, sd_stdev, lam, end=' ', file=out_file)
        print("", end="\n", file=out_file)
        # line 2
        for _ in self.skip_prob_bins:
            print(_, end=' ', file=out_file)
        print("", end="\n", file=out_file)
        # line 3
        print("0", end=' ', file=out_file) # placeholder for correlation parameter
        for kmer, level_mean, level_stdev, sd_mean, sd_stdev, weight in self.model:
            lam = calculate_lambda(sd_mean, sd_stdev)
            print(level_mean, (level_stdev*1.75), sd_mean, sd_stdev, lam, end=' ', file=out_file)
        print("", end="\n", file=out_file)
        return

    def get_model_dict(self):
        # check
        if self.model is None:
            print("This method is meant to be used as part of the child class TemplateModel or ComplementModel",
                  file=sys.stderr)
        # go through the model and build a lookup table
        model_dict = {}
        for kmer, level_mean, level_stdev, sd_mean, sd_stdev, weight in self.model:
            model_dict[kmer] = (level_mean, level_stdev, sd_mean, sd_stdev)
        return model_dict


class TemplateModel(NanoporeModel):
    def __init__(self, fast5File):
        super(TemplateModel, self).__init__(fast5File=fast5File)
        self.model = self.fastFive['/Analyses/Basecall_2D_000/BaseCalled_template/Model']
        self.stay_prob = log2(self.fastFive["/Analyses/Basecall_2D_000/BaseCalled_template/Model"].attrs["stay_prob"])
        self.skip_prob_bins = [0.487, 0.412, 0.311, 0.229, 0.174, 0.134, 0.115, 0.103, 0.096, 0.092,
                          0.088, 0.087, 0.084, 0.085, 0.083, 0.082, 0.085, 0.083, 0.084, 0.082,
                          0.080, 0.085, 0.088, 0.086, 0.087, 0.089, 0.085, 0.090, 0.087, 0.096]
        self.parse_model_name()

    def parse_model_name(self):
        model_name = self.fastFive["/Analyses/Basecall_2D_000/Summary/basecall_1d_template"].attrs["model_file"]
        model_name = model_name.split('/')[-1]
        self.model_name = model_name
        return


class ComplementModel(NanoporeModel):
    def __init__(self, fast5File):
        super(ComplementModel, self).__init__(fast5File=fast5File)
        self.model = self.fastFive['/Analyses/Basecall_2D_000/BaseCalled_complement/Model']
        self.stay_prob = log2(self.fastFive["/Analyses/Basecall_2D_000/BaseCalled_complement/Model"].attrs["stay_prob"])
        self.skip_prob_bins = [0.531, 0.478, 0.405, 0.327, 0.257, 0.207, 0.172, 0.154, 0.138, 0.132,
                               0.127, 0.123, 0.117, 0.115, 0.113, 0.113, 0.115, 0.109, 0.109, 0.107,
                               0.104, 0.105, 0.108, 0.106, 0.111, 0.114, 0.118, 0.119, 0.110, 0.119]
        self.parse_model_name()

    def parse_model_name(self):
        model_name = self.fastFive["/Analyses/Basecall_2D_000/Summary/basecall_1d_complement"].attrs["model_file"]
        model_name = model_name.split('/')[-1]
        self.model_name = model_name
        return
