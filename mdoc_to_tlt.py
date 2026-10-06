#!/usr/bin/env python3
"""
Extract tilt angles from an MDOC file and write them as a .tlt file.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


Z_RE = re.compile(r"(?m)^\[ZValue\s*=\s*(\d+)\]\s*$")
TILT_RE = re.compile(
    r"(?mi)^\s*TiltAngle\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*$"
)


@dataclass(frozen=True)
class TiltRecord:
    block_index: int
    zvalue: int
    tilt: float


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def parse_mdoc(path: Path) -> list[TiltRecord]:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(Z_RE.finditer(text))
    if not matches:
        fail(f"No [ZValue = ...] blocks found in MDOC: {path}")

    records: list[TiltRecord] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block_text = text[match.start() : end]
        tilt_match = TILT_RE.search(block_text)
        if tilt_match is None:
            fail(f"No TiltAngle found for ZValue={match.group(1)} in {path}")
        records.append(
            TiltRecord(
                block_index=index,
                zvalue=int(match.group(1)),
                tilt=float(tilt_match.group(1)),
            )
        )
    return records


def order_records(records: list[TiltRecord], order: str) -> list[TiltRecord]:
    if order == "block":
        return list(records)
    if order == "zvalue":
        return sorted(records, key=lambda item: item.zvalue)
    if order == "tilt-ascending":
        return sorted(records, key=lambda item: (item.tilt, item.zvalue))
    if order == "tilt-descending":
        return sorted(records, key=lambda item: (-item.tilt, item.zvalue))
    fail(f"Unknown order: {order}")
    raise AssertionError("unreachable")


def format_tilt(tilt: float, decimals: int, strip_trailing_zeros: bool) -> str:
    text = f"{tilt:.{decimals}f}"
    if strip_trailing_zeros and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract tilt angles from MDOC into a .tlt file.")
    parser.add_argument("--mdoc", type=Path, required=True, help="Input MDOC file.")
    parser.add_argument("--output", type=Path, required=True, help="Output .tlt file.")
    parser.add_argument(
        "--order",
        choices=("block", "zvalue", "tilt-ascending", "tilt-descending"),
        default="block",
        help="Ordering of angles in the output .tlt file.",
    )
    parser.add_argument(
        "--decimals",
        type=int,
        default=2,
        help="Number of decimals to write.",
    )
    parser.add_argument(
        "--strip-trailing-zeros",
        action="store_true",
        help="Strip trailing zeros and a trailing decimal point when possible.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.mdoc.exists():
        fail(f"MDOC file does not exist: {args.mdoc}")
    if args.output.exists() and not args.overwrite:
        fail(f"Output file already exists: {args.output}. Use --overwrite.")
    if args.decimals < 0:
        fail("--decimals must be 0 or greater.")

    records = order_records(parse_mdoc(args.mdoc), args.order)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        format_tilt(record.tilt, args.decimals, args.strip_trailing_zeros)
        for record in records
    ]
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(lines)} tilt angles to: {args.output}")
    print(f"Order: {args.order}")
    if lines:
        print(f"First angle: {lines[0]}")
        print(f"Last angle:  {lines[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
