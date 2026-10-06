# START HERE

This is the shareable GUI bundle for preparing Warp tilt-series inputs from
MRC/MDOC data.

## Files In This Bundle

- `tiltseries_protocol_gui.py`: the desktop GUI
- `prepare_warp_tiltseries.py`: the conversion engine
- `mdoc_to_tlt.py`: extracts tilt angles from MDOC into a `.tlt` file
- `environment_prepare_warp.yml`: conda environment
- `launch_gui.sh`: convenience launcher
- `example_preset_tilt_ascending.json`: example preset
- `README_GUI.md`: GUI guide
- `README_prepare_warp_tiltseries.md`: script reference

## Fastest Setup

```bash
conda env create -f environment_prepare_warp.yml
conda activate warp-tilt-prep-new
python3 tiltseries_protocol_gui.py
```

Or:

```bash
bash launch_gui.sh
```

## Example Settings

- Input mode: `One input folder`
- Slice order: `tilt-ascending` only when this matches the actual stack order
- Frames subdir: `frames`
- MDOC subdir: `mdoc`
- Output MDOC suffix: `_warp`

## Typical Workflow

1. Open the GUI.
2. Select the input folder with your `.mrc/.mrcs/.st` and `.mdoc` files.
3. Choose an output folder.
4. Click `Preview Command`.
5. Optionally enable `Dry run only` to test the mapping.
6. Click `Run`.

## MDOC To TLT

If you need an angle file for ICECREAM, IsoNet, or another downstream tool:

1. Open the `MDOC To TLT Utility` section in the GUI.
2. Select the input `.mdoc`.
3. Select the output `.tlt`.
4. Keep `Angle order = block` unless you specifically need a sorted angle list.
5. Click `Write TLT`.

## Outputs

The output folder will contain:

- `frames/`: one TIFF per tilt
- `mdoc/`: rewritten Warp-ready MDOC files
- `prepare_warp_summary.csv`: processing summary
