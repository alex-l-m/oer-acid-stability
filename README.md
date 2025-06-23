Scripts for estimating acid stability candidate catalyst materials for the oxygen evolution reaction, using entries in the Materials Project.

Just uses the Pourbaix diagram functionality from pymatgen. However, takes care of some of the issues that arise when running this analysis for a very large number of materials.

# Downloader script

    python retrieve_pourbaix.py [JOBNUM] [NJOBS]

For every combination of up to three elements, this script downloads and saves the Pourbaix entries required to construct the diagram. An alternative usage:

If a job number JOBNUM and total number of jobs NJOBS are provided, the script will download only a deterministic subset of these formulas. Parallelization is therefore possible by running multiple instances of the scripts with different job numbers.
