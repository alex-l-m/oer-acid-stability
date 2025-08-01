'''Retrieve PourbaixEntry objects from the Materials Project, serialize as json, and save as gzipped files, for diagram construction later. Entries are saved to the directory "pourbaix_entries", with filename {chemsys}.json.gz, and can be loaded using pymatgen's MontyDecoder. In addition, a table of data about the downloads is saved, called "pourbaix_downloads.csv.gz". Optionally, a job number and total number of jobs can be specified as arguments, to parallelize the download over multiple invocations of the script. In this case, each will save the json files to the same output folder, but the output table will be "pourbaix_downloads_{job_number}.csv".'''
import sys
from glob import glob
import functools
from hashlib import md5
import gzip
from os import mkdir
import os.path
import json
from time import time, sleep
from http.client import IncompleteRead
from requests.exceptions import (HTTPError, RetryError, ChunkedEncodingError,
                                ConnectionError, Timeout)
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import ProtocolError
import pandas as pd
from mp_api.client import MPRester
from mp_api.client.core.client import MPRestError
from monty.json import MontyEncoder

# Optional argument to split into jobs
if len(sys.argv) == 1:
    print('No job number provided, downloading all Pourbaix entries')
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

# Directory for saving serialized Pourbaix entries
outdir = 'pourbaix_entries'
try:
    mkdir(outdir)
except FileExistsError:
    pass

# Set the path of the output table containing information about the downloads
if job_number is None:
    outtbl_path = 'pourbaix_downloads.csv.gz'
else:
    outtbl_path = f'pourbaix_downloads_{job_number}.csv.gz'

# If it exists already, initialize output table with its data. Otherwise,
# initialize an empty table
try:
    prev_output = pd.read_csv(outtbl_path)
except (FileNotFoundError, pd.errors.EmptyDataError):
    prev_output = pd.DataFrame(columns=['symbols', 'n_entries', 'download_time',
                                        'entries_outpath', 'error'])

# Check if there's already saved output tables from a previous run, and load
# them if so. It's important to load all output files in case the number of
# jobs was changed, in which case this job's task may already have been done in
# a different job number's output file
# Glob captures numbered output (where * is "_[number]") and un-numbered output
# (where * is empty)
prev_output_files = glob('pourbaix_downloads*.csv.gz')
prev_symbols = set()
for this_prev_output_file in prev_output_files:
    try:
        this_prev_output = pd.read_csv(this_prev_output_file)
        # Set of chemsys's previously downloaded
        this_prev_symbols = set(this_prev_output['symbols'].tolist())
        prev_symbols.update(this_prev_symbols)
    except pd.errors.EmptyDataError:
        continue

def pourbaix2json(pourbaix_entries):
    '''Convert a list of entry objects to text'''
    # Use the Monty encoder to convert to a json string
    text = json.dumps(pourbaix_entries, cls=MontyEncoder)
    return text

def string2job(instr, njobs):
    '''Given a string, determine the job number of the job that will process
    that string'''
    hashed = md5(instr.encode('utf-8')).hexdigest()
    return int(hashed, 16) % njobs

# Download information rows
download_tbl_rows = []

# Make a set of all symbol combinations present in a previously saved list of
# compositions
compositions = pd.read_csv('compositions.csv.gz')
raw_symbol_combinations = set(
        frozenset(tbl.element.tolist())
        for material_id, tbl
        in compositions.groupby('material_id'))
# Redundant to include H and O, compounds with H and O will be
# considered during construction of the Pourbaix diagram
reduced_symbol_combinations = set(
        frozenset(symbol
                for symbol in combination
                if symbol not in frozenset(['H', 'O']))
        for combination in raw_symbol_combinations)
# This creates another problem: if H and O are the only symbols present, we'll
# get the empty set. So filter that out
symbol_combinations = set(
        combination
        for combination in reduced_symbol_combinations
        if len(combination) > 0)
# pourbaix diagram tutorial:
# https://matgenb.materialsvirtuallab.org/2017/12/15/plotting-a-pourbaix-diagram.html
try:
    with MPRester() as mpr:
        # My internet is unreliable, so setting up a session that can handle that
        # Copy-pasting from here:
        # https://stackoverflow.com/questions/23267409/how-to-implement-retry-mechanism-into-python-requests-library
        # After running into an hours-long hang, reducing the number of retries
        # and the backup factor
        # However, that hang was right before an IP block due to exceeding the
        # rate limit, so this may not have been necessary
        inner_retries = 5
        retry = Retry(total=inner_retries,
                      read=inner_retries,
                      connect=inner_retries,
                      backoff_factor=0.5,
                      # I've actually gotten 530
                      # Seems like it's CloudFlare hitting a DNS issue, not
                      # matproj
                      # https://community.cloudflare.com/t/community-tip-fixing-error-530-error-1016-origin-dns-error/44264
                      # Not including 429, "Too Many Requests", because if I
                      # quickly retry after that, I may just get my IP banned
                      # again
                      status_forcelist=(500, 502, 503, 504, 530),
                      allowed_methods=frozenset(['GET', 'POST']),
                      raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry,
                # Not sure if this helps
                pool_maxsize = 100, pool_block = False)
        mpr.session.mount('http://', adapter)
        mpr.session.mount('https://', adapter)
        # Also adding a timeout
        # Importance of timeouts:
        # https://findwork.dev/blog/advanced-usage-python-requests-timeouts-retries-hooks
        # This method for setting them:
        # https://stackoverflow.com/a/59317604
        # After still running into hours-long hangs, using a higher timeout.
        # This is the timeout for an individual request, so I think the hang
        # was in the Retry; trying to let it wait out problems rather than run
        # into the exponentially long backups in Retry
        mpr.session.request = functools.partial(mpr.session.request, timeout=60)
        for current_symbols in symbol_combinations:
            print(f'Trying symbols: {current_symbols}')

            this_download_tbl_row = dict()
            # Sort and join by dashes to create a "chemical system" string
            # https://pymatgen.org/pymatgen.core.html?utm_source=chatgpt.com#pymatgen.core.composition.Composition.chemical_system
            # > The chemical system of a Composition, for example “O-Si” for
            # > SiO2. Chemical system is a string of a list of elements sorted
            # > alphabetically and joined by dashes, by convention for use in
            # > database keys.
            chemsys = '-'.join(sorted(current_symbols))
            this_download_tbl_row['symbols'] = chemsys

            # Skip if this one has been downloaded already
            if chemsys in prev_symbols:
                print(f'Skipping {chemsys} because it has been downloaded already')
                continue

            # Skip if this chemsys is a part of this job
            if job_number is not None:
                # Get the job number for this chemsys
                chemsys_job_number = string2job(chemsys, njobs)
                if chemsys_job_number != job_number:
                    print(f'Skipping {chemsys} because it is not part of job {job_number}')
                    continue

            download_start = time()
            outer_retries = 10
            # Long outer delay; I think these are due to connection drops on my
            # end, which can take a while to be restored
            outer_delay = 30 # seconds
            successful_download = False
            # 1-indexing attempts for printing purposes
            for attempt in range(1, outer_retries+1):
                # 1. download the entries (H and O are added automatically)
                try:
                    pourbaix_entries = mpr.get_pourbaix_entries(current_symbols)
                    successful_download = True
                    break
                except (ChunkedEncodingError, ConnectionError, ProtocolError,
                        Timeout, IncompleteRead, MPRestError) as e:
                    print(f'Download failed on attempt {attempt}/{outer_retries} to download {current_symbols}, likely due to an interrupted connection, with error {e}')
                    sleep(outer_delay)
                # ValueError on Yb
                except ValueError as e:
                    print(f'Skipping {current_symbols} due to ValueError: {e}')
                    this_download_tbl_row['error'] = str(e)
                    download_tbl_rows.append(this_download_tbl_row)
                    break
                except HTTPError as err:
                    if err.response.status_code == 429:
                        print(f"Rate limited at symbols {current_symbols}: {err}")
                        print("Pausing for 10 minutes to reset rate limit.")
                        sleep(600)  # pause 10 min
                    else:
                        print(f'Download failed on attempt {attempt}/{outer_retries} to download {current_symbols} due to HTTPError: {err}')
                        sleep(outer_delay)
                except RetryError as err:
                    print(f'Download failed on attempt {attempt}/{outer_retries} to download {current_symbols} due to RetryError: {err}')
                    sleep(outer_delay)
            if not successful_download:
                print(f'Skipping {current_symbols} after {attempt} attempts')
                # Don't add to table so it tries again when rerun
                continue
            n_entries = len(pourbaix_entries)
            this_download_tbl_row['n_entries'] = n_entries
            if n_entries == 0:
                print(f'Skipping {current_symbols} because no Pourbaix entries found')
                download_tbl_rows.append(this_download_tbl_row)
                continue
            download_end = time()
            download_time = download_end - download_start
            this_download_tbl_row['download_time'] = download_time

            print(f'Downloaded {n_entries} Pourbaix entries for {current_symbols} in {download_time:.2f} seconds')

            # Serialize and save the entries
            serialized_text = pourbaix2json(pourbaix_entries)
            entries_outpath = os.path.join(outdir, f'{chemsys}.json.gz')
            with gzip.open(entries_outpath, 'wt') as f:
                f.write(serialized_text)
                print(f'Saved {n_entries} Pourbaix entries for {current_symbols} to {entries_outpath}')
            this_download_tbl_row['entries_outpath'] = entries_outpath

            # Wrapping up
            download_tbl_rows.append(this_download_tbl_row)
finally:
    # If there was a previous output table, concatenate the rows
    # Actually, concatenate the rows in any case; if there was no previous table,
    # it will be empty
    new_output_tbl = pd.DataFrame(download_tbl_rows)
    final_output_tbl = pd.concat([prev_output, new_output_tbl], ignore_index=True)
    # Save the output table
    final_output_tbl.to_csv(outtbl_path, index=False)
