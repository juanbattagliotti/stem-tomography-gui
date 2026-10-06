# Warp Tilt-Series Preparation GUI

This folder now includes a small desktop GUI for the automated Warp-preparation
workflow.

## What It Does

The GUI runs [prepare_warp_tiltseries.py](prepare_warp_tiltseries.py) behind the scenes. It lets a user:

- browse for input/output folders
- choose the tilt-to-slice mapping mode
- set image conversion options
- preview the exact command before running it
- save and reload presets as JSON
- extract a `.tlt` angle file directly from an `.mdoc`

This is meant to replace the manual notebook-based preparation path for normal
use.

## Files

- [tiltseries_protocol_gui.py](tiltseries_protocol_gui.py): desktop GUI
- [prepare_warp_tiltseries.py](prepare_warp_tiltseries.py): conversion engine
- [mdoc_to_tlt.py](mdoc_to_tlt.py): MDOC to TLT helper
- [environment_prepare_warp.yml](environment_prepare_warp.yml): conda environment

## Setup

Create the conda environment if needed:

```bash
conda env create -f environment_prepare_warp.yml
conda activate warp-tilt-prep-new
```

## Launch

From this folder:

```bash
python3 tiltseries_protocol_gui.py
```

If your system Python does not include Tkinter, launch it from a Python
installation that does.

## Typical Use

1. Set the Python path you want to use.
2. Check that the script path points to `prepare_warp_tiltseries.py`.
3. Choose one of the three input modes:
   - one input folder
   - separate MRC and MDOC folders
   - pairs CSV
4. Pick the output folder.
5. Set `Slice order` to match the actual image stack and verify the dry-run mapping.
6. Click `Preview Command`.
7. Click `Run`.

## MDOC To TLT

The GUI also includes an `MDOC To TLT Utility` section.

Typical use:

1. Choose the input `.mdoc`.
2. Choose the output `.tlt`.
3. Leave `Angle order = block` if you want the `.tlt` to follow the MDOC block order.
4. Click `Write TLT`.

If you want the output sorted by angle, use `tilt-ascending` or `tilt-descending`.

## Notes

- `Dry run` prints the planned mappings without writing files.
- `Overwrite existing output` is off by default.
- `Extra CLI Arguments` is there for advanced cases that are not yet exposed by
  the form.
