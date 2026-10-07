# START HERE

This is the shareable GUI bundle for preparing Warp tilt-series inputs from
MRC/MDOC data.

## Project Layout

- `src/stem_tomography_gui/`: the desktop GUI and command-line utilities
- `docs/GUI.md`: illustrated GUI guide
- `docs/prepare_warp_tiltseries.md`: preparation-engine reference
- `docs/warp_commands.md`: downstream Warp command templates
- `tests/test_preparation.py`: synthetic end-to-end pipeline check

## Fastest Setup

```bash
uv run stem-tomography-gui
```

`uv` creates the project environment and installs its dependencies
automatically. See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)
if the `uv` command is not yet available.

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
