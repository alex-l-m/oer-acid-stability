library(tidyverse)

# Regex for recognizing an element symbol
elem_regex <- '[A-Z][a-z]?'
# Regex for recognizing the material id in a Pourbaix entry id
# mvc is an obsolete identifier prefix but still in some of the results I get
# from PourbaixEntry objects. It's in the FAQ
# https://docs.materialsproject.org/frequently-asked-questions
core_regex = '^(mp|mvc)-\\d+'
pourbaix_tbl <- read_csv('pourbaix_data.csv.gz', col_types = cols(
    symbols = col_character(),
    name = col_character(),
    entry_id = col_character(),
    decomposition_energy = col_double(),
    decomposition_energy_lookup_time = col_double(),
    decomposition_energy_v0 = col_double()
)) |>
    # Get rid of the entries where a one of the elements wasn't included by
    # verifying that every one of the symbols is a substring of the name
    # Should reduce redundancy (Fe not also included under FeO)
    # In a test on a subset this brought it from about a million rows to about
    # five thousand
    filter(mapply(function(x, y) all(x %in% y),
                  str_extract_all(symbols, elem_regex),
                  str_extract_all(name, elem_regex))) |>
    # Removing duplicates
    # I don't know why I have duplicates; I really shouldn't!
    # This needs investigation
    distinct(symbols, name, entry_id, .keep_all = TRUE)

annotation_tbl <- read_csv('precomputed_properties.csv.gz', col_types = cols(
    material_id = col_character(),
    band_gap = col_double(),
    energy_above_hull = col_double(),
    deprecated = col_logical(),
    theoretical = col_logical()
))
combined_tbl <- pourbaix_tbl |>
    # Extract the material id from the entry id
    mutate(material_id = str_extract(entry_id, core_regex)) |>
    left_join(annotation_tbl, by = 'material_id', relationship = 'one-to-one') |>
    filter(!deprecated)

write_csv(combined_tbl, 'pourbaix_annotated.csv.gz')
