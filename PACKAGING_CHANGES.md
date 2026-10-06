# Preparation bundle provenance

Source: author-supplied tiltseries_protocol_gui_bundle_final directory, received 5 October 2026. No release/commit or license file was supplied. SOURCE_SHA256SUMS.txt records the nine original files. The original directory was not modified.

prepare_warp_tiltseries.py, mdoc_to_tlt.py and tiltseries_protocol_gui.py are byte-identical to the supplied code. The packaged adaptation changes only:
- Launcher: selects warp-tilt-prep-new consistently with the environment file, fails clearly when Conda is absent and resolves the GUI script relative to the launcher.
- Environment: explicitly lists tk for Tkinter; retains the supplied other dependencies. This file is not a fully pinned environment lock.
- Documentation: aligns the environment name and replaces local Markdown links with relative links.
- Example preset: starts in dry-run mode and sets the SubFramePath prefix to frames for consistency with the CLI wrapper.

The GUI itself retains its original defaults. Explicitly set the prefix, order and preview count when not loading the packaged preset. Original preset defaults are not claimed to be universal scientific settings.

Authors must assign an appropriate license and version identifier before public software deposit. No license has been invented or applied by this packaging step.

## Standalone repository preparation

Prepared from the preserved supplementary-software copy on 6 October 2026,
while the original network volume was unavailable. Application Python files
remain unchanged. Added a repository README, data exclusions and validation
notes; moved the synthetic test to a standalone layout; clarified ordering
guidance and removed references to an unbundled notebook and example acquisition
parameters from the script guide. No experimental data or manuscript files are
included.
