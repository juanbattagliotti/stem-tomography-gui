# Validation

The synthetic preparation check was run during repository preparation on
6 October 2026. It exercises the command-line preparation and angle-extraction
scripts with a small float32 MRC stack and deliberately different metadata block,
ZValue and angle orders.

Checks cover dry-run behavior, output pixel values, image-to-angle assignments,
rewritten paths, preserved metadata block order, the summary file, extracted angle
lists, refusal to overwrite existing outputs and unchanged raw input files.

The three application Python scripts are byte-identical to the preserved
author-supplied bundle. `SOURCE_SHA256SUMS.txt` describes the original supplied
files, including original documentation and packaging files that have since been
adapted; it is not a checksum manifest of the current repository.

Interactive GUI operation, creation of a fresh Conda environment, downstream GPU
processing, and performance on experimental datasets were not tested during this
repository preparation. The synthetic check is a software integrity check, not
scientific validation.
