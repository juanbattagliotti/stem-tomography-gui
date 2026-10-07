#!/usr/bin/env python3
"""
Prepare MRC tilt-series stacks and MDOC files for Warp.

For each MRC/MDOC pair this script:
1. Reads the MRC stack directly.
2. Writes one TIFF per tilt into a Warp-style frames/ folder.
3. Rewrites the MDOC so each [ZValue = ...] block has a matching
   SubFramePath = frames/<name>_<tilt>.tif entry.

The default slice mapping follows the manual Fiji/notebook protocol where the
first TIFF/MRC slice is assumed to be the lowest tilt angle. Use --slice-order
zvalue only when you know stack section 0 corresponds to MDOC ZValue 0.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Iterable

import numpy as np
from PIL import Image


MRC_MODE_DTYPES = {
    0: ("i1", "8-bit signed integer"),
    1: ("i2", "16-bit signed integer"),
    2: ("f4", "32-bit floating point"),
    6: ("u2", "16-bit unsigned integer"),
    12: ("f2", "16-bit floating point"),
}

MRC_EXTENSIONS = (".mrc", ".mrcs", ".st")
MDOC_EXTENSIONS = (".mdoc",)

Z_RE = re.compile(r"(?m)^\[ZValue\s*=\s*(\d+)\]\s*$")
TILT_RE = re.compile(
    r"(?mi)^\s*TiltAngle\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*$"
)
SUBFRAME_LINE_RE = re.compile(r"(?mi)^\s*SubFramePath\s*=.*(?:\r?\n)?")
NUM_SUBFRAMES_RE = re.compile(r"(?mi)^(\s*NumSubFrames\s*=\s*[^\r\n]*(?:\r?\n)?)")
TILT_LINE_RE = re.compile(r"(?mi)^(\s*TiltAngle\s*=\s*[^\r\n]*(?:\r?\n)?)")
Z_HEADER_LINE_RE = re.compile(r"^(\[ZValue[^\r\n]*(?:\r?\n)?)")


@dataclass(frozen=True)
class MrcHeader:
    nx: int
    ny: int
    nz: int
    mode: int
    dtype: np.dtype
    endian: str
    nsymbt: int
    mapc: int
    mapr: int
    maps: int
    data_offset: int


@dataclass(frozen=True)
class ZBlock:
    index: int
    zvalue: int
    start: int
    end: int
    text: str
    tilt: float


@dataclass(frozen=True)
class Pair:
    mrc: Path
    mdoc: Path
    name: str


@dataclass(frozen=True)
class ProcessResult:
    name: str
    mrc: Path
    mdoc: Path
    output_mdoc: Path
    frames_dir: Path
    frame_count: int
    min_tilt: float
    max_tilt: float
    slice_order: str


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sanitize_name(value: str) -> str:
    value = value.replace(",", "p")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^A-Za-z0-9._+-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("._")
    return value or "tiltseries"


def normalize_key(value: str) -> str:
    value = value.lower()
    for suffix in ("_warp", ".mrc", ".mrcs", ".st", ".ali"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return re.sub(r"[^a-z0-9]+", "", value)


def mdoc_match_keys(path: Path) -> set[str]:
    name = path.name
    if name.lower().endswith(".mdoc"):
        name = name[:-5]
    variants = {name, Path(name).stem}
    more = set()
    for item in variants:
        for suffix in ("_warp", ".mrc", ".mrcs", ".st", ".ali"):
            if item.lower().endswith(suffix):
                more.add(item[: -len(suffix)])
    variants |= more
    return {normalize_key(item) for item in variants if normalize_key(item)}


def collect_files(root: Path, extensions: tuple[str, ...], recursive: bool) -> list[Path]:
    if not root.exists():
        fail(f"Input folder does not exist: {root}")
    iterator: Iterable[Path] = root.rglob("*") if recursive else root.glob("*")
    files = [
        p
        for p in iterator
        if p.is_file() and p.suffix.lower() in extensions
    ]
    return sorted(files, key=lambda p: str(p).lower())


def pairs_from_csv(csv_path: Path) -> list[Pair]:
    if not csv_path.exists():
        fail(f"Pairs CSV does not exist: {csv_path}")
    pairs: list[Pair] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"mrc", "mdoc"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            fail("Pairs CSV must have at least these columns: mrc, mdoc")
        for row_number, row in enumerate(reader, start=2):
            mrc_value = (row.get("mrc") or "").strip()
            mdoc_value = (row.get("mdoc") or "").strip()
            if not mrc_value or not mdoc_value:
                fail(f"Missing mrc or mdoc value in pairs CSV row {row_number}")
            mrc = Path(mrc_value)
            mdoc = Path(mdoc_value)
            if not mrc.is_absolute():
                mrc = csv_path.parent / mrc
            if not mdoc.is_absolute():
                mdoc = csv_path.parent / mdoc
            name = sanitize_name((row.get("name") or "").strip() or mrc.stem)
            pairs.append(Pair(mrc=mrc, mdoc=mdoc, name=name))
    return pairs


def discover_pairs(
    mrc_dir: Path,
    mdoc_dir: Path,
    recursive: bool,
    ignore_unmatched: bool,
) -> list[Pair]:
    mrc_files = collect_files(mrc_dir, MRC_EXTENSIONS, recursive)
    mdoc_files = collect_files(mdoc_dir, MDOC_EXTENSIONS, recursive)
    if not mrc_files:
        fail(f"No MRC stack files found in: {mrc_dir}")
    if not mdoc_files:
        fail(f"No MDOC files found in: {mdoc_dir}")

    mdocs_by_key: dict[str, list[Path]] = {}
    for mdoc in mdoc_files:
        for key in mdoc_match_keys(mdoc):
            mdocs_by_key.setdefault(key, []).append(mdoc)

    pairs: list[Pair] = []
    unmatched_mrc: list[Path] = []
    used_mdocs: set[Path] = set()

    for mrc in mrc_files:
        key = normalize_key(mrc.stem)
        candidates = sorted(set(mdocs_by_key.get(key, [])), key=lambda p: str(p).lower())
        if len(candidates) == 1:
            mdoc = candidates[0]
            pairs.append(Pair(mrc=mrc, mdoc=mdoc, name=sanitize_name(mrc.stem)))
            used_mdocs.add(mdoc)
        elif len(candidates) > 1:
            names = "\n  ".join(str(p) for p in candidates)
            fail(f"Multiple MDOC candidates match {mrc}:\n  {names}\nUse --pairs-csv.")
        else:
            unmatched_mrc.append(mrc)

    unused_mdocs = [p for p in mdoc_files if p not in used_mdocs]
    if (unmatched_mrc or unused_mdocs) and not ignore_unmatched:
        message_parts = []
        if unmatched_mrc:
            message_parts.append(
                "MRC files without an MDOC match:\n  "
                + "\n  ".join(str(p) for p in unmatched_mrc)
            )
        if unused_mdocs:
            message_parts.append(
                "MDOC files without an MRC match:\n  "
                + "\n  ".join(str(p) for p in unused_mdocs)
            )
        message_parts.append("Use --pairs-csv for explicit pairing, or --ignore-unmatched.")
        fail("\n\n".join(message_parts))

    if not pairs:
        fail("No MRC/MDOC pairs found.")
    return pairs


def load_pairs(args: argparse.Namespace) -> list[Pair]:
    if args.pairs_csv:
        return pairs_from_csv(args.pairs_csv)
    if args.mrc or args.mdoc:
        if not args.mrc or not args.mdoc:
            fail("--mrc and --mdoc must be used together.")
        if len(args.mrc) != len(args.mdoc):
            fail("--mrc and --mdoc must be provided the same number of times.")
        names = args.name or []
        if names and len(names) != len(args.mrc):
            fail("--name must be provided once per --mrc/--mdoc pair, or not at all.")
        return [
            Pair(
                mrc=mrc,
                mdoc=mdoc,
                name=sanitize_name(names[index] if names else mrc.stem),
            )
            for index, (mrc, mdoc) in enumerate(zip(args.mrc, args.mdoc))
        ]

    input_root = args.input or Path(".")
    mrc_dir = args.mrc_dir or input_root
    mdoc_dir = args.mdoc_dir or input_root
    return discover_pairs(mrc_dir, mdoc_dir, args.recursive, args.ignore_unmatched)


def read_mrc_header(path: Path, mode0_unsigned: bool) -> MrcHeader:
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(1024)
    if len(header) < 1024:
        fail(f"MRC file is smaller than a 1024-byte header: {path}")

    for endian in ("<", ">"):
        nx, ny, nz, mode = struct.unpack(endian + "4i", header[0:16])
        mapc, mapr, maps = struct.unpack(endian + "3i", header[64:76])
        nsymbt = struct.unpack(endian + "i", header[92:96])[0]
        if nx <= 0 or ny <= 0 or nz <= 0:
            continue
        if mode not in MRC_MODE_DTYPES:
            continue
        dtype_code = "u1" if mode == 0 and mode0_unsigned else MRC_MODE_DTYPES[mode][0]
        dtype = np.dtype(dtype_code)
        if dtype.itemsize > 1:
            dtype = dtype.newbyteorder(endian)
        data_offset = 1024 + nsymbt
        expected_bytes = nx * ny * nz * dtype.itemsize
        if nsymbt < 0 or data_offset < 1024:
            continue
        if data_offset + expected_bytes <= size:
            return MrcHeader(
                nx=nx,
                ny=ny,
                nz=nz,
                mode=mode,
                dtype=dtype,
                endian=endian,
                nsymbt=nsymbt,
                mapc=mapc,
                mapr=mapr,
                maps=maps,
                data_offset=data_offset,
            )

    fail(
        f"Could not parse a supported MRC stack header from {path}. "
        f"Supported MRC modes are: {sorted(MRC_MODE_DTYPES)}"
    )
    raise AssertionError("unreachable")


def open_mrc_stack(path: Path, mode0_unsigned: bool) -> tuple[MrcHeader, np.memmap]:
    header = read_mrc_header(path, mode0_unsigned)
    data = np.memmap(
        path,
        dtype=header.dtype,
        mode="r",
        offset=header.data_offset,
        shape=(header.nz, header.ny, header.nx),
        order="C",
    )
    return header, data


def parse_mdoc(path: Path) -> tuple[str, list[ZBlock]]:
    text = read_text(path)
    matches = list(Z_RE.finditer(text))
    if not matches:
        fail(f"No [ZValue = ...] blocks found in MDOC: {path}")

    blocks: list[ZBlock] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block_text = text[match.start() : end]
        tilt_match = TILT_RE.search(block_text)
        if tilt_match is None:
            fail(f"No TiltAngle found for ZValue={match.group(1)} in {path}")
        blocks.append(
            ZBlock(
                index=index,
                zvalue=int(match.group(1)),
                start=match.start(),
                end=end,
                text=block_text,
                tilt=float(tilt_match.group(1)),
            )
        )
    return text, blocks


def order_blocks(blocks: list[ZBlock], slice_order: str) -> list[ZBlock]:
    if slice_order == "zvalue":
        return sorted(blocks, key=lambda block: block.zvalue)
    if slice_order == "block":
        return list(blocks)
    if slice_order == "tilt-ascending":
        return sorted(blocks, key=lambda block: (block.tilt, block.zvalue))
    if slice_order == "tilt-descending":
        return sorted(blocks, key=lambda block: (-block.tilt, block.zvalue))
    fail(f"Unknown slice order: {slice_order}")
    raise AssertionError("unreachable")


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def ensure_line_break(line: str, newline: str) -> str:
    return line if line.endswith(("\n", "\r")) else line + newline


def insert_after(pattern: re.Pattern[str], block: str, insertion: str, newline: str) -> str | None:
    def repl(match: re.Match[str]) -> str:
        return ensure_line_break(match.group(1), newline) + insertion

    updated, count = pattern.subn(repl, block, count=1)
    return updated if count else None


def update_block_text(
    block: str,
    subframe_path: str,
    newline: str,
    ensure_num_subframes: bool,
) -> str:
    block = SUBFRAME_LINE_RE.sub("", block)
    subframe_line = f"SubFramePath = {subframe_path}{newline}"

    if NUM_SUBFRAMES_RE.search(block):
        updated = insert_after(NUM_SUBFRAMES_RE, block, subframe_line, newline)
        if updated is not None:
            return updated

    if ensure_num_subframes:
        insertion = f"NumSubFrames = 1{newline}{subframe_line}"
    else:
        insertion = subframe_line

    updated = insert_after(TILT_LINE_RE, block, insertion, newline)
    if updated is not None:
        return updated

    updated = insert_after(Z_HEADER_LINE_RE, block, insertion, newline)
    if updated is not None:
        return updated

    return block + ensure_line_break("", newline) + insertion


def rewrite_mdoc(
    text: str,
    blocks: list[ZBlock],
    subframe_paths: dict[int, str],
    ensure_num_subframes: bool,
) -> str:
    newline = detect_newline(text)
    chunks: list[str] = []
    pos = 0
    for block in blocks:
        chunks.append(text[pos : block.start])
        chunks.append(
            update_block_text(
                block.text,
                subframe_paths[block.index],
                newline,
                ensure_num_subframes,
            )
        )
        pos = block.end
    chunks.append(text[pos:])
    return "".join(chunks)


def angle_tag(angle: float, decimals: int) -> str:
    return f"{angle:.{decimals}f}"


def join_subframe_path(prefix: str, filename: str) -> str:
    prefix = prefix.strip().replace("\\", "/")
    if prefix in ("", "."):
        return filename
    return f"{prefix.rstrip('/')}/{filename}"


def native_array(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array)
    if array.dtype.isnative or array.dtype.itemsize == 1:
        return array
    return array.byteswap().view(array.dtype.newbyteorder("="))


def stack_min_max(data: np.memmap) -> tuple[float, float]:
    minimum = float("inf")
    maximum = float("-inf")
    for index in range(data.shape[0]):
        section = np.asarray(data[index], dtype=np.float32)
        finite = np.isfinite(section)
        if not finite.any():
            continue
        section_values = section[finite]
        minimum = min(minimum, float(section_values.min()))
        maximum = max(maximum, float(section_values.max()))
    if not np.isfinite(minimum) or not np.isfinite(maximum):
        fail("Cannot scale stack because all values are NaN or infinite.")
    if minimum == maximum:
        maximum = minimum + 1.0
    return minimum, maximum


def convert_for_tiff(
    array: np.ndarray,
    output_dtype: str,
    scale_range: tuple[float, float] | None,
) -> np.ndarray:
    array = native_array(array)
    if output_dtype == "preserve":
        if array.dtype == np.dtype("float16"):
            return array.astype(np.float32)
        if array.dtype == np.dtype("int8"):
            return array.astype(np.int16)
        return array

    if output_dtype == "float32":
        return array.astype(np.float32)

    if output_dtype in {"uint8", "uint16"}:
        if scale_range is None:
            fail("Internal error: scaling range missing for integer output.")
        low, high = scale_range
        array32 = np.asarray(array, dtype=np.float32)
        scaled = (array32 - low) / (high - low)
        scaled = np.clip(scaled, 0.0, 1.0)
        if output_dtype == "uint8":
            return np.rint(scaled * 255.0).astype(np.uint8)
        return np.rint(scaled * 65535.0).astype(np.uint16)

    fail(f"Unsupported output dtype: {output_dtype}")
    raise AssertionError("unreachable")


def save_tiff(array: np.ndarray, path: Path, compression: str) -> None:
    image = Image.fromarray(array)
    kwargs = {"format": "TIFF"}
    if compression != "none":
        kwargs["compression"] = compression
    image.save(path, **kwargs)


def check_targets(paths: list[Path], overwrite: bool) -> None:
    if overwrite:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        preview = "\n  ".join(str(path) for path in existing[:20])
        extra = "" if len(existing) <= 20 else f"\n  ... and {len(existing) - 20} more"
        fail(f"Refusing to overwrite existing output files:\n  {preview}{extra}\nUse --overwrite.")


def print_preview(name: str, preview_rows: list[tuple[int, str, str]], total: int) -> None:
    print(f"\n{name}: previewing {min(len(preview_rows), total)} of {total} frame mappings")
    for stack_index, tilt, filename in preview_rows:
        print(f"  stack[{stack_index:04d}] tilt {tilt:>8} -> {filename}")


def process_pair(args: argparse.Namespace, pair: Pair) -> ProcessResult:
    if not pair.mrc.exists():
        fail(f"MRC stack does not exist: {pair.mrc}")
    if not pair.mdoc.exists():
        fail(f"MDOC file does not exist: {pair.mdoc}")

    header, stack = open_mrc_stack(pair.mrc, args.mode0_unsigned)
    text, blocks = parse_mdoc(pair.mdoc)
    if stack.shape[0] != len(blocks):
        fail(
            f"Slice/MDOC count mismatch for {pair.name}: "
            f"MRC has {stack.shape[0]} sections, MDOC has {len(blocks)} ZValue blocks."
        )

    if (header.mapc, header.mapr, header.maps) != (1, 2, 3):
        print(
            f"WARNING: {pair.mrc.name} has nonstandard MRC axis mapping "
            f"MAPC/MAPR/MAPS={header.mapc}/{header.mapr}/{header.maps}. "
            "The script assumes stack sections are stored as Z,Y,X."
        )

    ordered = order_blocks(blocks, args.slice_order)
    scale_range = None
    if args.output_dtype in {"uint8", "uint16"}:
        print(f"{pair.name}: calculating global stack min/max for {args.output_dtype} scaling...")
        scale_range = stack_min_max(stack)
        print(f"{pair.name}: scaling range {scale_range[0]:.6g} to {scale_range[1]:.6g}")

    frames_dir = args.output / args.frames_subdir
    mdoc_dir = args.output / args.mdoc_subdir
    output_mdoc = mdoc_dir / f"{pair.name}{args.output_mdoc_suffix}.mdoc"

    subframe_paths: dict[int, str] = {}
    frame_targets: list[Path] = []
    filename_seen: dict[str, ZBlock] = {}
    preview_rows: list[tuple[int, str, str]] = []

    for stack_index, block in enumerate(ordered):
        tag = angle_tag(block.tilt, args.angle_decimals)
        filename = f"{pair.name}_{tag}.tif"
        if filename in filename_seen:
            other = filename_seen[filename]
            fail(
                f"Duplicate output filename {filename} for tilt angles "
                f"{other.tilt} and {block.tilt}. Increase --angle-decimals."
            )
        filename_seen[filename] = block
        subframe_paths[block.index] = join_subframe_path(args.subframe_prefix, filename)
        frame_targets.append(frames_dir / filename)
        if len(preview_rows) < args.preview_count:
            preview_rows.append((stack_index, tag, filename))

    if args.dry_run:
        print_preview(pair.name, preview_rows, len(ordered))
        print(f"  output MDOC would be: {output_mdoc}")
        return ProcessResult(
            name=pair.name,
            mrc=pair.mrc,
            mdoc=pair.mdoc,
            output_mdoc=output_mdoc,
            frames_dir=frames_dir,
            frame_count=len(ordered),
            min_tilt=min(block.tilt for block in blocks),
            max_tilt=max(block.tilt for block in blocks),
            slice_order=args.slice_order,
        )

    check_targets(frame_targets + [output_mdoc], args.overwrite)
    frames_dir.mkdir(parents=True, exist_ok=True)
    mdoc_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"\n{pair.name}: writing {len(ordered)} TIFF frames from "
        f"{header.nx}x{header.ny}x{header.nz} MRC mode {header.mode}"
    )
    for stack_index, (block, target) in enumerate(zip(ordered, frame_targets), start=1):
        image = convert_for_tiff(stack[stack_index - 1], args.output_dtype, scale_range)
        save_tiff(image, target, args.compression)
        if stack_index == 1 or stack_index == len(ordered) or stack_index % args.progress_every == 0:
            print(f"  {stack_index:4d}/{len(ordered)} {target.name}")

    updated_mdoc = rewrite_mdoc(text, blocks, subframe_paths, args.ensure_num_subframes)
    output_mdoc.write_text(updated_mdoc, encoding="utf-8")
    print(f"{pair.name}: wrote Warp MDOC {output_mdoc}")

    return ProcessResult(
        name=pair.name,
        mrc=pair.mrc,
        mdoc=pair.mdoc,
        output_mdoc=output_mdoc,
        frames_dir=frames_dir,
        frame_count=len(ordered),
        min_tilt=min(block.tilt for block in blocks),
        max_tilt=max(block.tilt for block in blocks),
        slice_order=args.slice_order,
    )


def write_summary(output: Path, results: list[ProcessResult]) -> Path:
    summary_path = output / "prepare_warp_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "name",
                "mrc",
                "mdoc_in",
                "mdoc_out",
                "frames_dir",
                "frame_count",
                "min_tilt",
                "max_tilt",
                "slice_order",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.name,
                    result.mrc,
                    result.mdoc,
                    result.output_mdoc,
                    result.frames_dir,
                    result.frame_count,
                    result.min_tilt,
                    result.max_tilt,
                    result.slice_order,
                ]
            )
    return summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-convert MRC tilt stacks to TIFF frames and rewrite MDOCs for Warp."
    )
    input_group = parser.add_argument_group("inputs")
    input_group.add_argument("--input", type=Path, help="Folder containing matching MRC and MDOC files.")
    input_group.add_argument("--mrc-dir", type=Path, help="Folder containing MRC stacks.")
    input_group.add_argument("--mdoc-dir", type=Path, help="Folder containing MDOC files.")
    input_group.add_argument("--recursive", action="store_true", help="Search input folders recursively.")
    input_group.add_argument("--pairs-csv", type=Path, help="CSV with columns mrc,mdoc and optional name.")
    input_group.add_argument("--mrc", type=Path, action="append", help="Single MRC path. Repeat for more pairs.")
    input_group.add_argument("--mdoc", type=Path, action="append", help="Single MDOC path. Repeat for more pairs.")
    input_group.add_argument("--name", action="append", help="Output base name for a --mrc/--mdoc pair.")
    input_group.add_argument(
        "--ignore-unmatched",
        action="store_true",
        help="When auto-discovering, ignore unpaired MRC or MDOC files.",
    )

    output_group = parser.add_argument_group("outputs")
    output_group.add_argument("--output", type=Path, required=True, help="Warp prep output folder.")
    output_group.add_argument("--frames-subdir", default="frames", help="Output subfolder for TIFF frames.")
    output_group.add_argument("--mdoc-subdir", default="mdoc", help="Output subfolder for rewritten MDOCs.")
    output_group.add_argument(
        "--subframe-prefix",
        default=None,
        help="Path prefix written in MDOC SubFramePath. Default: same as --frames-subdir.",
    )
    output_group.add_argument(
        "--output-mdoc-suffix",
        default="_warp",
        help="Suffix appended to rewritten MDOC names before .mdoc.",
    )
    output_group.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    output_group.add_argument("--dry-run", action="store_true", help="Print planned mappings without writing files.")

    mapping_group = parser.add_argument_group("mapping")
    mapping_group.add_argument(
        "--slice-order",
        choices=("zvalue", "block", "tilt-ascending", "tilt-descending"),
        default="tilt-ascending",
        help=(
            "How stack slice 0..N is assigned to MDOC blocks. "
            "Default tilt-ascending reproduces the manual protocol; "
            "use zvalue only when stack section 0 is MDOC ZValue 0."
        ),
    )
    mapping_group.add_argument(
        "--angle-decimals",
        type=int,
        default=1,
        help="Decimals used in output filenames, e.g. 1 gives -60.0.",
    )
    mapping_group.add_argument(
        "--ensure-num-subframes",
        action="store_true",
        help="Insert NumSubFrames = 1 when a ZValue block does not already have it.",
    )

    image_group = parser.add_argument_group("image conversion")
    image_group.add_argument(
        "--output-dtype",
        choices=("preserve", "float32", "uint16", "uint8"),
        default="preserve",
        help="TIFF dtype. preserve keeps source values when Pillow supports them.",
    )
    image_group.add_argument(
        "--compression",
        choices=("none", "tiff_lzw", "tiff_deflate"),
        default="none",
        help="TIFF compression.",
    )
    image_group.add_argument(
        "--mode0-unsigned",
        action="store_true",
        help="Read MRC mode 0 as uint8 instead of int8.",
    )

    run_group = parser.add_argument_group("run behavior")
    run_group.add_argument("--preview-count", type=int, default=8, help="Mappings to print in dry runs.")
    run_group.add_argument("--progress-every", type=int, default=25, help="Progress print interval.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.frames_subdir.startswith("/") or args.mdoc_subdir.startswith("/"):
        fail("--frames-subdir and --mdoc-subdir must be relative folder names.")
    if args.subframe_prefix is None:
        args.subframe_prefix = args.frames_subdir
    if args.angle_decimals < 0:
        fail("--angle-decimals must be 0 or greater.")
    if args.progress_every < 1:
        fail("--progress-every must be 1 or greater.")
    if args.preview_count < 0:
        fail("--preview-count must be 0 or greater.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(args)

    pairs = load_pairs(args)
    print(f"Found {len(pairs)} MRC/MDOC pair(s).")
    for pair in pairs:
        print(f"  {pair.name}: {pair.mrc} + {pair.mdoc}")

    results: list[ProcessResult] = []
    for pair in pairs:
        results.append(process_pair(args, pair))

    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)
        summary = write_summary(args.output, results)
        print(f"\nDone. Summary written to {summary}")
        print(f"Warp frames folder: {args.output / args.frames_subdir}")
        print(f"Warp MDOC folder:   {args.output / args.mdoc_subdir}")
    else:
        print("\nDry run complete. No files were written.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("\nInterrupted.")
