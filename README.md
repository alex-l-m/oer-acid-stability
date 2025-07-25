Scripts for estimating acid stability candidate catalyst materials for the oxygen evolution reaction, using entries in the Materials Project.

Just uses the Pourbaix diagram functionality from pymatgen. However, takes care of some of the issues that arise when running this analysis for a very large number of materials.

## Precomputed properties downloader script

    python retrieve_precomputed_properties.py [-i IDS]

Saves a file 'precomputed\_properties.csv.gz' containing columns corresponding to the Materials Project summary properties 'material\_id', 'band\_gap', 'energy\_above\_hull', 'deprecated', and 'theoretical'.

Also saves a file "compositions.csv.gz" which will be used by the Pourbaix entry downloader script to decide which element combinations to download.

Optional input is a text file containing a Materials Project id on each line, to download for selected entries. Without that, it will download for all entries.

## Pourbaix entry downloader script

    python retrieve_pourbaix.py [JOBNUM] [NJOBS]

For every combination retrieved in the previous step, this script downloads and saves the Pourbaix entries required to construct the diagram.

If a job number JOBNUM and total number of jobs NJOBS are provided, the script will download only a deterministic subset of these formulas. Parallelization is therefore possible by running multiple instances of the scripts with different job numbers.

## Compute decomposition energies from Pourbaix entries

    python make_pourbaix_diagrams.py [-j JOBNUM -n NJOBS] [-g GLOBAL_CONDITIONS] [-m MATERIAL_CONDITIONS] [-p PH -v VOLTAGE]

This must be run after the downloader script, in the same directory.

Assumes a file exists called 'pourbaix\_downloads.csv.gz', so if the downloader script was parallelized, the results must have been concatenated into a single file with this name.

Flexible specification of `(pH, voltage)` conditions through one or more methods:
- `-g`, `--global-conditions`: CSV file with columns `ph, voltage`, giving conditions to be used for each material.
- `-m`, `--material-conditions`: CSV file with columns `material_id, ph, voltage`, giving conditions to be used for their respective materials.
- `-p`, `--ph` and `-v`, `--voltage`: Comma-separated pH and voltage values to be used for each material; if more than one of each is given, the combinations are the Cartesian product.

At least one method must be specified. Multiple methods can be combined freely.

### Examples

Global conditions file only:

```
python make_pourbaix_diagrams.py -g global_conditions.csv
```

Material-specific conditions file only:

```
python make_pourbaix_diagrams.py -m material_conditions.csv
```

Direct specification (Cartesian product):

```
python make_pourbaix_diagrams.py --ph 0 -v 0,1.23
```

Direct with parallelization:

```
python make_pourbaix_diagrams.py --ph 0 -v 0,1.23 -j 0 -n 2
```

## Filtering redundant or duplicate entries and annotating with precomputed properties

    Rscript join.R

Requires 'pourbaix\_data.csv' in working directory, so if decomposition energy calculations were parallelized, they must have been concatenated to a single file.
