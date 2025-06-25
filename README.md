Scripts for estimating acid stability candidate catalyst materials for the oxygen evolution reaction, using entries in the Materials Project.

Just uses the Pourbaix diagram functionality from pymatgen. However, takes care of some of the issues that arise when running this analysis for a very large number of materials.

# Pourbaix entry downloader script

    python retrieve_pourbaix.py [JOBNUM] [NJOBS]

For every combination of up to three elements, this script downloads and saves the Pourbaix entries required to construct the diagram. An alternative usage:

If a job number JOBNUM and total number of jobs NJOBS are provided, the script will download only a deterministic subset of these formulas. Parallelization is therefore possible by running multiple instances of the scripts with different job numbers.

# Precomputed properties downloader script

    retrieve_precomputed_properties.py

Saves a file 'precomputed\_properties.csv.gz' containing columns corresponding to the Materials Project summary properties 'material\_id', 'band\_gap', 'energy\_above\_hull', 'deprecated', and 'theoretical'.

# Compute decomposition energy from Pourbaix entries

    python make_pourbaix_diagrams.py [JOBNUM] [NJOBS]

This must be run after the downloader script, in the same directory.
