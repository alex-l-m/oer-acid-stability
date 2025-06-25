import sys
import re
import json
import gzip
from time import time
from hashlib import md5
import pandas as pd
from pymatgen.analysis.pourbaix_diagram import PourbaixDiagram
from monty.json import MontyDecoder

# Optional argument to split into jobs
if len(sys.argv) == 1:
    print('No job number provided, making diagrams for all element combinations')
    job_number = None
    njobs = None
if len(sys.argv) == 2:
    raise ValueError('If you provide a job number, you must also provide the total number of jobs')
if len(sys.argv) == 3:
    print(f'Running job {sys.argv[1]} of {sys.argv[2]}')
    job_number = int(sys.argv[1])
    njobs = int(sys.argv[2])
if len(sys.argv) > 3:
    raise ValueError('Too many arguments provided; expected 0 or 2 arguments')

# Pourbaix diagram tutorial:
# https://matgenb.materialsvirtuallab.org/2017/12/15/Plotting-a-Pourbaix-Diagram.html

def safeint(r):
    '''Safe conversion to an integer'''
    n = int(r)
    if abs(n - r) > 1e-5:
        raise ValueError(f'Value {r} is not close to an integer')
    return n

def json2pourbaix(json_text):
    '''Convert the text of a JSON file containing PourbaixEntry objects into a
    list of objects'''
    outlist = json.loads(json_text, cls=MontyDecoder)
    return outlist

def string2job(instr, njobs):
    '''Given a string, determine the job number of the job that will process
    that string'''
    hashed = md5(instr.encode('utf-8')).hexdigest()
    return int(hashed, 16) % njobs

# Rows for an output table of elements entries and energies
data_tbl_rows = []

# Pourbaix diagram construction information rows
diagram_tbl_rows = []

intbl_path = 'pourbaix_downloads.csv'
# Header row:
# symbols,n_entries,download_time,entries_outpath,error
intbl = pd.read_csv(intbl_path)

# Decide names of output files
if job_number is not None:
    # Save the data for this job to a file
    diagram_outpath = f'pourbaix_diagrams_{job_number}.csv'
    data_outpath = f'pourbaix_data_{job_number}.csv'
else:
    diagram_outpath = 'pourbaix_diagrams.csv'
    data_outpath = 'pourbaix_data.csv'

# If the output files are already there, read them. Otherwise, create empty
# tables
try:
    old_diagram_tbl = pd.read_csv(diagram_outpath)
    prev_symbols = set(old_diagram_tbl['symbols'].tolist())
except (FileNotFoundError, pd.errors.EmptyDataError):
    old_diagram_tbl = pd.DataFrame()
    prev_symbols = set()
try:
    old_data_tbl = pd.read_csv(data_outpath)
except (FileNotFoundError, pd.errors.EmptyDataError):
    old_data_tbl = pd.DataFrame()

try:
    for row in intbl.itertuples():
        # The data from the table that I'm going to use
        inpath = row.entries_outpath
        # Actually not a formula, just which elements are present, but
        # concatenated like a formula
        # I probably should have separated with dashes, so it doesn't look like
        # a formula, and of course not used the "formula" variable name
        formula = row.symbols

        # Skip if this one has been downloaded already
        if formula in prev_symbols:
            print(f'Skipping {formula} because it has been downloaded already')
            continue

        # Separate the elements in the formula into a list
        single_symbol_regex = re.compile('[A-Z][a-z]?')
        current_symbols = single_symbol_regex.findall(formula)

        # The formulas that couldn't be downloaded because the data is
        # unavailable are still recorded in the table to avoid retrying the
        # download. These will be recognizable because the path to the entry
        # will be missing. If this is the case, skip this iteration of the loop
        if pd.isna(inpath):
            continue

        # Skip if this formula is a part of this job
        if job_number is not None:
            # Get the job number for this formula
            formula_job_number = string2job(formula, njobs)
            if formula_job_number != job_number:
                continue

        # Create a list of PourbaixEntry objects from text saved during download
        json_text = gzip.open(inpath, 'rt').read()
        pourbaix_entries = json2pourbaix(json_text)

        solid_entries = [entry \
                         for entry in pourbaix_entries \
                         if entry.phase_type == 'Solid']

        # Sampling one specific point: pH=0, voltage = 1.23
        pH = 0
        V = 1.23
        # Precomputed Pourbaix diagrams
        # These are created inside the loop because they're based on the list
        # of entries retrieved
        pourbaix_diagrams = dict()
        for pourbaix_entry in solid_entries:
            this_data_row = dict()
            this_data_row['symbols'] = ''.join(current_symbols)
            this_data_row['name'] = pourbaix_entry.name
            this_data_row['entry_id'] = pourbaix_entry.entry_id

            # ACID STABILITY
            # Determine the composition of the entry, including only the metal
            # atoms, and create a dictionary of normalized fractions for
            # creating a temporary Pourbaix diagram
            # Using integers for hashability
            unnormalized_composition = \
                    {key.symbol: safeint(value)
                     for key, value in pourbaix_entry.composition.reduced_composition.items() \
                     if key.symbol in current_symbols}
            composition_total = sum(unnormalized_composition.values())
            normalized_composition = \
                    {key: value / composition_total \
                     for key, value in unnormalized_composition.items()}
            # Probably better to use it without normalization
            hashable_composition = \
                    frozenset(unnormalized_composition.items())
            # Create a temporary Pourbaix diagram with the correct composition
            try:
                pourbaix_diagram = pourbaix_diagrams[hashable_composition]
            except KeyError:
                # Time construction of the diagram since I'm not sure if it's
                # fast
                diagram_time_start = time()

                # Construct the Pourbaix diagram
                pourbaix_diagram = PourbaixDiagram(
                    entries=pourbaix_entries,
                # PourbaixDiagram documentation:
                # https://pymatgen.org/pymatgen.analysis.html#pymatgen.analysis.pourbaix_diagram.PourbaixDiagram
                # Says of "filter_solids" that it "generally leads to the most
                # accurate Pourbaix diagrams"
                    filter_solids=True,
                    comp_dict=normalized_composition)

                diagram_time_end = time()

                # Save the diagram so that I don't have to construct it again
                # for the same composition
                pourbaix_diagrams[hashable_composition] = pourbaix_diagram

                # Save the timing information to an output table
                diagram_time = diagram_time_end - diagram_time_start
                this_diagram_tbl_row = this_data_row.copy()
                this_diagram_tbl_row['diagram_time'] = diagram_time
                diagram_tbl_rows.append(this_diagram_tbl_row)

            # I'm sure the lookup time is short, but timing it just in case
            lookup_start = time()
            energy = pourbaix_diagram.get_decomposition_energy(pourbaix_entry, pH, V)
            this_data_row['decomposition_energy'] = energy
            lookup_end = time()
            lookup_time = lookup_end - lookup_start
            this_data_row['decomposition_energy_lookup_time'] = lookup_time

            energy_v0 = pourbaix_diagram.get_decomposition_energy(pourbaix_entry, pH, 0)
            this_data_row['decomposition_energy_v0'] = energy_v0

            # WRAPPING UP
            data_tbl_rows.append(this_data_row)

finally:
    new_data_tbl = pd.DataFrame(data_tbl_rows)
    combined_data_tbl = pd.concat([old_data_tbl, new_data_tbl],
                                  ignore_index=True)
    combined_data_tbl.to_csv(data_outpath, index=False)
    new_diagram_tbl = pd.DataFrame(diagram_tbl_rows)
    combined_diagram_tbl = pd.concat([old_diagram_tbl, new_diagram_tbl],
                                      ignore_index=True)
    combined_diagram_tbl.to_csv(diagram_outpath, index=False)
