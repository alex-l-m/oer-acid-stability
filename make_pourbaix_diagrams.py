import re
import json
import gzip
from time import time
from hashlib import md5
import itertools
import argparse
import pandas as pd
from pymatgen.analysis.pourbaix_diagram import PourbaixDiagram
from monty.json import MontyDecoder

parser = argparse.ArgumentParser(description='Decomposition energies from a Pourbaix diagram.')

parser.add_argument('-j', '--job-number', type=int, default=None,
                    help='Job number for parallel runs (starting from 0)')
parser.add_argument('-n', '--njobs', type=int, default=None,
                    help='Total number of parallel jobs')

# Optional global conditions CSV
parser.add_argument('-g', '--global-conditions', type=str, default=None,
                    help='Path to CSV file with columns ph,voltage for global conditions')

# Optional material-specific conditions CSV
parser.add_argument('-m', '--material-conditions', type=str, default=None,
                    help='Path CSV file with columns material_id,ph,voltage for material-specific conditions')

# Optional direct conditions from command line
parser.add_argument('-p', '--ph', type=str, default=None,
                    help='Single or comma-separated pH values')
parser.add_argument('-v', '--voltage', type=str, default=None,
                    help='Single comma-separated voltage values (Cartesian product with pH values will be used)')

args = parser.parse_args()

# Initialize empty data structures to hold conditions
global_conditions = []
material_conditions = dict()

# Check at least one condition source is provided
if not (args.global_conditions is not None or
        args.material_conditions is not None or
        (args.ph is not None and args.voltage is not None)):
    raise ValueError('You must specify at least one method for conditions: global file, material-specific file, or direct --ph and --voltage arguments.')

# Read global conditions file if provided
if args.global_conditions is not None:
    global_df = pd.read_csv(args.global_conditions)
    global_cols = set(global_df.columns)
    if 'ph' not in global_cols or 'voltage' not in global_cols:
        raise ValueError('Global conditions file must have columns "ph" and "voltage".')
    global_conditions.extend(zip(global_df.ph, global_df.voltage))

# Add Cartesian product of conditions directly from the command line if provided
if (args.ph is not None) and (args.voltage is not None):
    ph_list = [float(p) for p in args.ph.split(',')]
    voltage_list = [float(v) for v in args.voltage.split(',')]
    global_conditions.extend(itertools.product(ph_list, voltage_list))
elif (args.ph is not None) or (args.voltage is not None):
    raise ValueError('You must specify both --ph and --voltage if specifying conditions directly.')

# Read material-specific conditions file if provided
if args.material_conditions:
    material_df = pd.read_csv(args.material_conditions)
    material_cols = set(material_df.columns)
    if 'material_id' not in material_cols or 'ph' not in material_cols or 'voltage' not in material_cols:
        raise ValueError('Material conditions file must have columns "material_id", "ph", and "voltage".')
    for material_id, df in material_df.groupby('material_id'):
        if material_id not in material_conditions:
            material_conditions[material_id] = []
        material_conditions[material_id].extend(zip(df.ph, df.voltage))

# Optional argument to split into jobs
if (args.job_number is None) != (args.njobs is None):
    raise ValueError('You must specify both --job-number and --njobs, or neither.')

if args.job_number is None:
    job_number = None
    njobs = None
else:
    if args.job_number < 0 or args.job_number >= args.njobs:
        raise ValueError('job-number must be in range [0, njobs - 1]')
    print(f'Running job number {args.job_number} of {args.njobs} jobs')
    job_number = args.job_number
    njobs = args.njobs

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

intbl_path = 'pourbaix_downloads.csv.gz'
# Header row:
# symbols,n_entries,download_time,entries_outpath,error
intbl = pd.read_csv(intbl_path)

# Decide names of output files
if job_number is not None:
    # Save the data for this job to a file
    diagram_outpath = f'pourbaix_diagrams_{job_number}.csv.gz'
    data_outpath = f'pourbaix_data_{job_number}.csv.gz'
else:
    diagram_outpath = 'pourbaix_diagrams.csv.gz'
    data_outpath = 'pourbaix_data.csv.gz'

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
        chemsys = row.symbols

        # Skip if this one has been downloaded already
        if chemsys in prev_symbols:
            print(f'Skipping {chemsys} because it has been downloaded already')
            continue

        # Separate the elements in the chemsys into a list
        current_symbols = chemsys.split('-')

        # The chemsyss that couldn't be downloaded because the data is
        # unavailable are still recorded in the table to avoid retrying the
        # download. These will be recognizable because the path to the entry
        # will be missing. If this is the case, skip this iteration of the loop
        if pd.isna(inpath):
            continue

        # Skip if this chemsys is a part of this job
        if job_number is not None:
            # Get the job number for this chemsys
            chemsys_job_number = string2job(chemsys, njobs)
            if chemsys_job_number != job_number:
                continue

        # Create a list of PourbaixEntry objects from text saved during download
        json_text = gzip.open(inpath, 'rt').read()
        pourbaix_entries = json2pourbaix(json_text)

        solid_entries = [entry \
                         for entry in pourbaix_entries \
                         if entry.phase_type == 'Solid']

        # Precomputed Pourbaix diagrams
        # These are created inside the loop because they're based on the list
        # of entries retrieved
        pourbaix_diagrams = dict()
        for pourbaix_entry in solid_entries:
            partial_row = dict()
            chemsys = '-'.join(sorted(current_symbols))
            partial_row['symbols'] = chemsys
            partial_row['name'] = pourbaix_entry.name
            partial_row['entry_id'] = pourbaix_entry.entry_id

            # The conditions are the global conditions, plus the
            # material-specific conditions, if any
            conditions = global_conditions.copy()
            material_id_match = re.match(r'^(mp|mvc)-\d+', pourbaix_entry.entry_id)
            if material_id_match is not None:
                material_id = material_id_match.group(0)
            else:
                raise ValueError(f'Invalid entry_id format: {pourbaix_entry.entry_id}')
            if material_id in material_conditions.keys():
                conditions.extend(material_conditions[material_id])

            # If there's no conditions to check, we can skip this one
            if len(conditions) == 0:
                continue

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
                # Time construction of the diagram since I'm not sure if
                # it's fast
                diagram_time_start = time()

                # Construct the Pourbaix diagram
                pourbaix_diagram = PourbaixDiagram(
                    entries=pourbaix_entries,
                # PourbaixDiagram documentation:
                # https://pymatgen.org/pymatgen.analysis.html#pymatgen.analysis.pourbaix_diagram.PourbaixDiagram
                # Says of "filter_solids" that it "generally leads to the
                # most accurate Pourbaix diagrams"
                    filter_solids=True,
                    comp_dict=normalized_composition)

                diagram_time_end = time()

                # Save the diagram so that I don't have to construct it
                # again for the same composition
                pourbaix_diagrams[hashable_composition] = pourbaix_diagram

                # Save the timing information to an output table
                diagram_time = diagram_time_end - diagram_time_start
                this_diagram_tbl_row = partial_row.copy()
                this_diagram_tbl_row['diagram_time'] = diagram_time
                diagram_tbl_rows.append(this_diagram_tbl_row)
            # Looping over pH, voltage pairs
            for pH, V in conditions:
                # I'm sure the lookup time is short, but timing it just in case
                lookup_start = time()
                energy = pourbaix_diagram.get_decomposition_energy(pourbaix_entry, pH, V)
                lookup_end = time()
                lookup_time = lookup_end - lookup_start

                # Save the data for this entry and conditions
                this_data_row = partial_row.copy()
                this_data_row['ph'] = pH
                this_data_row['voltage'] = V
                this_data_row['decomposition_energy'] = energy
                this_data_row['decomposition_energy_lookup_time'] = lookup_time

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
