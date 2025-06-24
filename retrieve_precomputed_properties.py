'''Retrieve the additional properties I'm interested in, namely the
energy above hull, the bandgap, and the "Synthesizable" star from the web
display, for every material in the materials project'''

import pandas as pd
from mp_api.client import MPRester

with MPRester() as mpr:
    # Retrieve summaries with just the properties I'm interested in, band gap,
    # energy above hull, and synthesizability
    # num_chunks = None means return all possible values
    # That's the default but setting it like that just in case
    # If I use a list of specific target materials I get:
    # ValueError: List of material/molecule IDs provided is too long. Consider removing the ID filter to automatically pull data for all IDs and filter locally.
    # Explained here:
    # https://docs.materialsproject.org/downloading-data/using-the-api/tips-for-large-downloads
    # Just downloading for every material instead
    entries = mpr.materials.summary.search(\
            # The "fields" argument actually gets ignored for a bulk download
            # like this (no queries given), but doesn't do any harm so I'm
            # leaving it in
            fields=['material_id', 'band_gap', 'energy_above_hull',
                'theoretical', 'deprecated'],
            num_chunks = None)
# Create list of rows for the output table
rows = []
for entry in entries:
    this_row = dict()
    this_row['material_id'] = entry.material_id
    this_row['band_gap'] = entry.band_gap
    this_row['energy_above_hull'] = entry.energy_above_hull
    this_row['deprecated'] = entry.deprecated
    # Theoretical is a boolean; it's the negation of the "Synthesizable"
    # property indicated with a star in the web interface:
    # https://matsci.org/t/obtain-star-materials/51386/2
    # It actually just means the material isn't present in ICSD:
    # https://matsci.org/t/how-is-the-theoretical-tag-determined/3527
    this_row['theoretical'] = entry.theoretical
    rows.append(this_row)

# Save a csv file with the table constructed from the rows
outpath = 'precomputed_properties.csv.gz'
df = pd.DataFrame(rows)
df.to_csv(outpath, index=False)
