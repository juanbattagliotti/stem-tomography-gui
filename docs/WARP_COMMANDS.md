# Warp commands for STEM tomography

This guide follows the Warp stages of the supplied STEM preparation protocol:
GUI-prepared TIFF images and MDOC files → Warp import → stacks for IMOD alignment
→ alignment import → full and odd/even tomograms → optional Noise2Map denoising.

The commands below are **templates, not ready-to-run scripts**. Replace each
`<PLACEHOLDER>` with the value for your dataset and installation, and replace
`path/to/...` with your paths. Angle brackets are notation, not shell syntax to
paste unchanged. No example numeric values, Slurm directives, resource requests,
or scheduler wrappers are included. Flags without placeholders are switches.

Run these commands in an environment containing WarpTools (and Noise2Map for the
last step). These programs are installed separately from the preparation GUI.
Record the software version used and check each command's `--help` output against
that installation. The guide preserves the command structure of the supplied
protocol; it is not a claim that the commands have been executed on your dataset.

## Before starting

Use the [illustrated GUI guide](README_GUI.md) to prepare one TIFF per tilt and
its rewritten MDOC. Confirm the image-to-angle mapping before importing the data.
The directory name `frames` follows Warp terminology; here it contains individual
STEM projections, not dose-fractionated movie frames. Make sure MDOC
`SubFramePath` entries resolve to the intended images. Use consistent paths
throughout, preferably absolute paths when executing the completed commands.

## 1. Create settings for the projection images

```text
WarpTools create_settings \
  --output path/to/warp_fs.settings \
  --folder_data path/to/frames \
  --folder_processing path/to/warp_fs \
  --extension "*.tif" \
  --angpix <INPUT_PIXEL_SIZE_ANGSTROM> \
  --exposure <EXPOSURE>
```

This creates the settings file linking the prepared images to a Warp processing
directory.

- `--output`: settings file to create.
- `--folder_data`: directory containing the prepared TIFF images.
- `--folder_processing`: directory for Warp image-processing metadata and outputs.
- `--extension`: input filename pattern; change it if your input format differs.
- `--angpix`: physical sampling of the input images in Å per pixel.
- `--exposure`: acquisition exposure/dose metadata required by Warp. Use the
  quantity and units expected by your installed version; do not substitute an
  arbitrary example or a dwell time in incompatible units.

## 2. Export projection averages

```text
WarpTools fs_export_micrographs \
  --settings path/to/warp_fs.settings \
  --average_halves \
  --averages \
  --perdevice <PROCESSES_PER_DEVICE>
```

This runs the projection export stage used by the protocol.

- `--settings`: image settings created in step 1.
- `--averages`: requests exported average images.
- `--average_halves`: requests frame-half exports where supported by the input
  and installed Warp version. It is retained from the protocol, but it does not
  create independent movie-frame observations from a single STEM projection.
  The restoration pairs in this workflow come from tilt splitting in step 7.
- `--perdevice`: application-level processing concurrency per device. Select it
  for the available hardware; this is not a Slurm resource allocation.

Inspect the exported images before continuing, particularly when importing
single-image TIFFs through Warp's frame-series processing interface.

## 3. Import tilt-series metadata

```text
WarpTools ts_import \
  --mdocs path/to/mdoc \
  --frameseries path/to/warp_fs \
  --tilt_exposure <EXPOSURE_PER_TILT> \
  --min_intensity <MINIMUM_INTENSITY_THRESHOLD> \
  --output path/to/tomostar
```

This connects the MDOC acquisition records with the processed projection images
and creates the tilt-series STAR metadata used downstream.

- `--mdocs`: directory containing the rewritten MDOC files.
- `--frameseries`: processing directory associated with the projection images,
  not the raw TIFF directory.
- `--tilt_exposure`: exposure/dose per tilt in the units expected by Warp.
- `--min_intensity`: intensity-based inclusion threshold. Select it for the data
  and inspect which projections are retained; the protocol's example is not a
  universal cutoff.
- `--output`: destination for the generated `.tomostar` files.

## 4. Create tilt-series settings

```text
WarpTools create_settings \
  --output path/to/warp_ts.settings \
  --folder_processing path/to/warp_ts \
  --folder_data path/to/tomostar \
  --extension "*.tomostar" \
  --angpix <INPUT_PIXEL_SIZE_ANGSTROM> \
  --exposure <EXPOSURE> \
  --tomo_dimensions <X>x<Y>x<Z>
```

This defines the tilt-series processing project and reconstruction volume extent.

- `--folder_data`: metadata directory produced in step 3.
- `--folder_processing`: directory for tilt-series processing outputs.
- `--angpix`: input projection sampling, consistent with the image settings.
- `--exposure`: exposure metadata consistent with the acquisition and Warp's
  convention.
- `--tomo_dimensions`: volume dimensions in Warp's expected pixel convention;
  provide the three dimensions separated by `x`. Check this convention in the
  installed version before converting physical specimen dimensions to pixels.

The output sampling requested later does not justify changing the input sampling
in this settings file.

## 5. Export tilt stacks for alignment

```text
WarpTools ts_stack \
  --settings path/to/warp_ts.settings \
  --angpix <ALIGNMENT_STACK_PIXEL_SIZE_ANGSTROM> \
  --perdevice <PROCESSES_PER_DEVICE>
```

This assembles the projection images into tilt stacks for alignment in IMOD.
`--angpix` specifies the sampling of the exported alignment stack. Record it:
the alignment-import step must use the sampling at which the alignment was
actually determined.

Align the exported stacks in IMOD and inspect the alignment before continuing.
Preserve its transforms, tilt geometry and associated files together. This is a
separate alignment step, not an additional Warp command.

## 6. Import the IMOD alignments

```text
WarpTools ts_import_alignments \
  --settings path/to/warp_ts.settings \
  --alignments path/to/imod_alignment_directory \
  --alignment_angpix <ALIGNMENT_PIXEL_SIZE_ANGSTROM>
```

This transfers accepted alignment geometry back into the Warp project.

- `--alignments`: directory containing the alignment files expected by Warp.
  Preserve the naming and directory layout required by your installed version.
- `--alignment_angpix`: sampling of the images used to calculate the alignment.
  If IMOD used the stack from step 5 without further resampling, use that same
  sampling. Do not substitute the intended reconstruction sampling.

## 7. Reconstruct the full volume and odd/even halves

```text
WarpTools ts_reconstruct \
  --settings path/to/warp_ts.settings \
  --angpix <RECONSTRUCTION_PIXEL_SIZE_ANGSTROM> \
  --dont_invert \
  --perdevice <PROCESSES_PER_DEVICE> \
  --halfmap_tilts
```

This requests reconstruction at the chosen output sampling, including half maps
formed from alternating tilt images.

- `--angpix`: desired reconstruction voxel sampling in Å.
- `--dont_invert`: retains the input contrast polarity rather than applying
  contrast inversion; confirm this is appropriate for your data.
- `--halfmap_tilts`: generates paired reconstructions by splitting tilt images,
  rather than movie frames.

Keep the full, even and odd reconstructions together with their settings and
alignments. Check their dimensions, voxel size, orientation and spatial
correspondence before restoration. The halves have complementary angular
sampling and can share artifacts; their agreement is not independent proof of
structural accuracy.

This STEM workflow does not add conventional cryo-TEM phase-contrast CTF
estimation or phase-flipping commands.

## 8. Optional denoising with Warp Noise2Map

```text
Noise2Map \
  --observation1 path/to/even_tomograms \
  --observation2 path/to/odd_tomograms \
  --observation_combined path/to/full_tomograms \
  --dont_flatten_spectrum \
  --dont_augment \
  --batchsize <BATCH_SIZE> \
  --iterations <TRAINING_ITERATIONS>
```

This uses paired noisy reconstructions for denoising and supplies the corresponding
full reconstructions. Run it from the intended output working directory and
check your installed version's output behavior.

- `--observation1` and `--observation2`: directories containing corresponding
  even/odd volumes, with matching geometry and file naming as required by Noise2Map.
- `--observation_combined`: directory containing the matching full reconstructions.
- `--dont_flatten_spectrum`: disables spectrum flattening.
- `--dont_augment`: disables augmentation.
- `--batchsize`: training batch size to select for the data and available memory.
- `--iterations`: training duration to select and evaluate for the dataset.

The two disabling switches reflect the supplied protocol and should be reviewed
for the chosen processing strategy. Keep only the intended matching inputs in
these directories and compare denoised outputs with the unprocessed volumes.
Noise2Map is one restoration option; it is not designated the best method for
every specimen or biological question.

## Command reference and provenance

These templates are adapted from the author-supplied STEM protocol, with its
example values, specimen-specific paths and Slurm resources removed. Consult the
[official Warp tilt-series guide](https://github.com/warpem/warp/blob/main/docs/user_guide/warptools/quick_start_warptools_tilt_series.md)
and your installed command help for version-specific requirements. The official
cryo-ET tutorial contains processing stages that are not automatically appropriate
for HAADF-STEM.
