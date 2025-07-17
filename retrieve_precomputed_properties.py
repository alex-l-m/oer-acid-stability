'''Retrieve the additional properties I'm interested in, namely the energy
above hull, the bandgap, and the "Synthesizable" star from the web display, for
every material in the materials project (with no arguments given) or for
materials in with ids given by rows in a text file (if the path to the text
file is provided as an argument)'''

import argparse
import pandas as pd
from mp_api.client import MPRester

parser = argparse.ArgumentParser(description='Retrieve properties from Materials Project.')
parser.add_argument('-i', '--ids', type=str, default=None,
                    help='Path to a text file containing Materials Project IDs (one per line). If omitted, downloads data for all materials.')

args = parser.parse_args()

# Read IDs from file if provided
if args.ids:
    with open(args.ids, 'r') as f:
        mp_ids = [line.strip() for line in f if line.strip()]
else:
    mp_ids = None

# When running without an input file, I get:
# pydantic_core._pydantic_core.ValidationError
# "Tips for Large Downloads" has example code without the document model
# https://docs.materialsproject.org/downloading-data/using-the-api/tips-for-large-downloads
# Jason Munro recommended this to someone as a workaround to issues on the
# Materials Project's side:
# https://matsci.org/t/validation-error-when-trying-to-query/51811
# Therefire, adding arguments monty_decode and use_document_model
with MPRester(monty_decode=False, use_document_model=False) as mpr:
    # Retrieve summaries with just the properties I'm interested in, band gap,
    # energy above hull, and synthesizability
    # num_chunks = None means return all possible values
    # That's the default but setting it like that just in case
    # If I use a too large a list of specific target materials I get:
    # ValueError: List of material/molecule IDs provided is too long. Consider removing the ID filter to automatically pull data for all IDs and filter locally.
    # Explained here:
    # https://docs.materialsproject.org/downloading-data/using-the-api/tips-for-large-downloads
    # Avoidable by not specifying a list of inputs, in which case mp_ids is None
    # I assume this is the docs page for the search function:
    # https://materialsproject.github.io/api/_autosummary/mp_api.client.routes.materials.summary.SummaryRester.html#mp_api.client.routes.materials.summary.SummaryRester.search
    # Shows the default argument for material_ids is None, so giving None as an
    # argument should be the same as leaving the argument out
    # When mp_ids is None, I get this warning:
    # /home/alexlm/miniconda3/envs/chem/lib/python3.12/site-packages/mp_api/client/core/client.py:519: UserWarning: Ignoring `fields` argument: All fields are always included when no query is provided.
    # This is obliquely mentioned in the Tips for Large Downloads
    # https://docs.materialsproject.org/downloading-data/using-the-api/tips-for-large-downloads
    # > Additionally, we've optimized downloads of full collections such that
    # > they're often more efficient and faster than providing long lists of
    # > material_ids or fields.
    # However, it doesn't seem to hurt to include the fields argument, so just
    # including it in any case
    entries = mpr.materials.summary.search(
            material_ids=mp_ids,
            fields=['material_id', 'band_gap', 'energy_above_hull',
                'theoretical', 'deprecated', 'composition'],
            num_chunks = None)
# Create list of rows for the output table of properties
property_rows = []
# Create a list of rows for the output table of compositions
composition_rows = []
for entry in entries:
    # RETRIEVE PROPERTIES
    this_property_row = dict()
    this_property_row['material_id'] = entry['material_id']
    this_property_row['band_gap'] = entry['band_gap']
    this_property_row['energy_above_hull'] = entry['energy_above_hull']
    this_property_row['deprecated'] = entry['deprecated']
    # Theoretical is a boolean; it's the negation of the "Synthesizable"
    # property indicated with a star in the web interface:
    # https://matsci.org/t/obtain-star-materials/51386/2
    # It actually just means the material isn't present in ICSD:
    # https://matsci.org/t/how-is-the-theoretical-tag-determined/3527
    this_property_row['theoretical'] = entry['theoretical']
    property_rows.append(this_property_row)

    # RETRIEVE COMPOSITION
    # Ideally I would use reduced composition, but without the document model I
    # don't see how
    these_composition_rows = \
            [{'material_id': entry['material_id'],
                'element': key,
                'amount': value} \
             for key, value \
             in entry['composition'].items()]
    composition_rows.extend(these_composition_rows)

# Save a csv file with the table constructed from the property rows
outpath = 'precomputed_properties.csv.gz'
property_df = pd.DataFrame(property_rows)
property_df.to_csv(outpath, index=False)
# Also save a csv file containing the compositions
composition_outpath = 'compositions.csv.gz'
composition_df = pd.DataFrame(composition_rows)
composition_df.to_csv(composition_outpath, index=False)
