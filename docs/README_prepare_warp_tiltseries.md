# Batch MRC/MDOC Prep For Warp

This replaces the manual part of the protocol where you:

- convert an MRC stack to TIFF
- split it in Fiji
- rename individual tilts by angle
- add `SubFramePath = frames/...` lines to the `.mdoc`

The script writes a Warp-ready folder:

```text
Warp_prep/
  frames/
    tomo1_-60.0.tif
    tomo1_-58.0.tif
    ...
  mdoc/
    tomo1_warp.mdoc
  prepare_warp_summary.csv
```

## Quick Start

Use Python 3.11 with NumPy and Pillow, or create the supplied Conda environment:

```bash
conda env create -f environment_prepare_warp.yml
conda activate warp-tilt-prep-new
```

This repository contains the GUI and command-line scripts. A notebook is not
included.

## Command-Line Setup

```bash
python3 prepare_warp_tiltseries.py \
  --input /path/to/folder_with_mrc_and_mdoc \
  --output /path/to/Warp_prep \
  --recursive \
  --dry-run
```

If the preview looks correct, run without `--dry-run`:

```bash
python3 prepare_warp_tiltseries.py \
  --input /path/to/folder_with_mrc_and_mdoc \
  --output /path/to/Warp_prep \
  --recursive
```

Use the generated `frames/` and `mdoc/` folders in your Warp workflow. Set pixel
sampling, exposure and other downstream parameters from the actual acquisition;
this preparation utility does not determine those values.

## Slice Order

The default reproduces the manual notebooks:

```bash
--slice-order tilt-ascending
```

This matches the manual Fiji/notebook assumption from the protocol, where the first TIFF or MRC slice corresponds to the lowest tilt angle.

If your stack is already in MDOC `ZValue` order, use:

```bash
--slice-order zvalue
```

If your stack is reversed, use:

```bash
--slice-order tilt-descending
```

Always check the dry-run preview before launching a full batch.

## Explicit Pairing For Many Tomograms

Automatic pairing works when MRC and MDOC filenames share the same base name. If they do not, make a CSV:

```csv
mrc,mdoc,name
/data/raw/cell1_sec1_HAADF.mrc,/data/mdoc/cell1_sec1_HAADF.mdoc,cell1_sec1_HAADF
/data/raw/cell1_sec2_HAADF.mrc,/data/mdoc/cell1_sec2_HAADF.mdoc,cell1_sec2_HAADF
```

Then run:

```bash
python3 prepare_warp_tiltseries.py \
  --pairs-csv pairs.csv \
  --output /path/to/Warp_prep \
  --dry-run
```

## Common Options

```bash
--overwrite
```

Allow replacing existing TIFFs and rewritten MDOCs.

```bash
--angle-decimals 2
```

Use more decimals in filenames if rounded tilt angles would collide.

```bash
--ensure-num-subframes
```

Insert `NumSubFrames = 1` into MDOC blocks that do not already have it.

```bash
--output-dtype uint16
```

Scale each stack globally into uint16 TIFFs. By default, the script preserves the source MRC values.

```bash
--mode0-unsigned
```

Read MRC mode 0 stacks as unsigned 8-bit data instead of signed 8-bit data.
