library(tidyverse)

# Function to separate element symbols, which are recognizable because they
# begin with a capital letter
# Input is a string, output is a vector of strings
sepsym <- function(str) str_extract_all(str, '[A-Z][a-z]*')[[1]]
# Function to check if all symbols are contained within a second string
hasall <- Vectorize(function(symbols, name)
{
    all(sepsym(symbols) %in% sepsym(name))
})
# Regex for a symbol string of up to three elements
three_elem_regex <- '([A-Z][a-z]?)([A-Z][a-z]?)?([A-Z][a-z]?)?'
# Regex indicating the character after an element in a name
elem_end_regex <- '([A-Z]|$|[0-9])'
# Regex for recognizing the material id in a Pourbaix entry id
# mvc is an obsolete identifier prefix but still in some of the results I get
# from PourbaixEntry objects. It's in the FAQ
# https://docs.materialsproject.org/frequently-asked-questions
core_regex = '^(mp|mvc)-\\d+'
pourbaix_tbl <- read_csv('pourbaix_data.csv', col_types = cols(
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
    # This brought it from over a million rows down to around three thousand in
    # a test run on a subset
    mutate(elem1 = str_extract(symbols, three_elem_regex, group = 1),
           elem2 = str_extract(symbols, three_elem_regex, group = 2),
           elem3 = str_extract(symbols, three_elem_regex, group = 3)) |>
    # This will have to be changed if I include more than three elements
    filter(str_detect(name, str_c(elem1, elem_end_regex)) &
           (is.na(elem2) | str_detect(name, str_c(elem2, elem_end_regex))) &
           (is.na(elem3) | str_detect(name, str_c(elem3, elem_end_regex)))) |>
    select(-elem1, -elem2, -elem3) |>
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

write_csv(combined_tbl, 'pourbaix_annotated.csv')
