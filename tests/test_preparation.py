"""End-to-end checks for the synthetic tilt-series preparation pipeline.

Run from any directory with::

    python /path/to/repository/tests/test_preparation.py

The test creates a small MRC/MDOC pair and never uses experimental data or a
GPU. All generated inputs and outputs are removed when the test finishes.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
PREPARATION_MODULE = "stem_tomography_gui.prepare_warp_tiltseries"
TLT_MODULE = "stem_tomography_gui.mdoc_to_tlt"

SLICE_ORDERS = {
    "block": [0, 30, -30],
    "zvalue": [30, -30, 0],
    "tilt-ascending": [-30, 0, 30],
    "tilt-descending": [30, 0, -30],
}


def write_synthetic_mrc(path: Path) -> np.ndarray:
    """Write a three-section float32 MRC stack and return its pixel data."""
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, 4, 3, 3, 2)  # nx, ny, nz, mode
    struct.pack_into("<3i", header, 28, 4, 3, 3)  # mx, my, mz
    struct.pack_into("<3f", header, 40, 4, 3, 3)  # cell dimensions
    struct.pack_into("<3f", header, 52, 90, 90, 90)  # cell angles
    struct.pack_into("<3i", header, 64, 1, 2, 3)  # mapc, mapr, maps
    header[208:212] = b"MAP "
    header[212:216] = b"DA\0\0"

    data = np.arange(36, dtype="<f4").reshape(3, 3, 4) - 17.5
    path.write_bytes(header + data.tobytes())
    return data


def write_synthetic_mdoc(path: Path) -> None:
    """Write metadata whose block, ZValue, and tilt orders all differ."""
    records = [(2, 0), (0, 30), (1, -30)]
    blocks = "".join(
        f"[ZValue = {zvalue}]\n"
        f"TiltAngle = {angle}\n"
        "SubFramePath = obsolete.tif\n\n"
        for zvalue, angle in records
    )
    path.write_text(f"PixelSpacing = 1\n\n{blocks}", encoding="utf-8")


def file_hashes(directory: Path) -> dict[str, str]:
    """Return SHA-256 hashes keyed by filename for every file in a directory."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
    }


class PreparationPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="stem-prep-test-")
        self.base_dir = Path(self.temporary_directory.name)
        self.raw_dir = self.base_dir / "raw"
        self.raw_dir.mkdir()

        self.stack = write_synthetic_mrc(self.raw_dir / "example.mrc")
        write_synthetic_mdoc(self.raw_dir / "example.mdoc")
        self.original_hashes = file_hashes(self.raw_dir)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli(
        self,
        module: str,
        *arguments: object,
        should_succeed: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run one project CLI in a subprocess and check its exit status."""
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        python_paths = [str(SOURCE_ROOT)]
        if existing_pythonpath:
            python_paths.append(existing_pythonpath)
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)

        result = subprocess.run(
            [sys.executable, "-m", module, *map(str, arguments)],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if (result.returncode == 0) != should_succeed:
            self.fail(
                f"Command returned {result.returncode}:\n"
                f"{result.args}\n\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def preparation_arguments(self, output_dir: Path, slice_order: str) -> list[object]:
        return [
            "--input",
            self.raw_dir,
            "--output",
            output_dir,
            "--slice-order",
            slice_order,
            "--output-dtype",
            "preserve",
            "--preview-count",
            3,
        ]

    def assert_frames_match_stack(
        self,
        output_dir: Path,
        expected_angles: list[int],
    ) -> None:
        frames_dir = output_dir / "frames"
        self.assertEqual(len(list(frames_dir.glob("*.tif"))), len(expected_angles))

        for stack_index, angle in enumerate(expected_angles):
            frame_path = frames_dir / f"example_{angle:.1f}.tif"
            with Image.open(frame_path) as image:
                np.testing.assert_array_equal(np.asarray(image), self.stack[stack_index])

    def assert_mdoc_paths_are_valid(self, output_dir: Path) -> Path:
        mdoc_path = output_dir / "mdoc" / "example_warp.mdoc"
        text = mdoc_path.read_text(encoding="utf-8")

        self.assertEqual(re.findall(r"\[ZValue = (\d+)\]", text), ["2", "0", "1"])
        self.assertNotIn("obsolete.tif", text)

        blocks = re.split(r"\[ZValue = \d+\]", text)[1:]
        for block in blocks:
            angle = float(re.search(r"TiltAngle = (.*)", block).group(1))
            relative_path = re.search(r"SubFramePath = (.*)", block).group(1)
            self.assertEqual(relative_path, f"frames/example_{angle:.1f}.tif")
            self.assertTrue((output_dir / relative_path).exists())

        return mdoc_path

    def assert_tlt_angles(
        self,
        output_dir: Path,
        mdoc_path: Path,
        slice_order: str,
        expected_angles: list[int],
    ) -> None:
        tlt_path = output_dir / "angles.tlt"
        arguments = [
            "--mdoc",
            mdoc_path,
            "--output",
            tlt_path,
            "--order",
            slice_order,
        ]
        self.run_cli(TLT_MODULE, *arguments)
        self.assertEqual(
            [float(value) for value in tlt_path.read_text().split()],
            expected_angles,
        )
        self.run_cli(TLT_MODULE, *arguments, should_succeed=False)

    def test_preparation_pipeline_for_every_slice_order(self) -> None:
        for slice_order, expected_angles in SLICE_ORDERS.items():
            with self.subTest(slice_order=slice_order):
                output_dir = self.base_dir / slice_order
                arguments = self.preparation_arguments(output_dir, slice_order)

                preview = self.run_cli(PREPARATION_MODULE, *arguments, "--dry-run")
                self.assertFalse(output_dir.exists(), "Dry run wrote output")
                self.assertIn("previewing 3 of 3", preview.stdout)

                self.run_cli(PREPARATION_MODULE, *arguments)
                self.assert_frames_match_stack(output_dir, expected_angles)
                mdoc_path = self.assert_mdoc_paths_are_valid(output_dir)
                self.assertTrue((output_dir / "prepare_warp_summary.csv").exists())

                refusal = self.run_cli(
                    PREPARATION_MODULE,
                    *arguments,
                    should_succeed=False,
                )
                self.assertIn("Refusing to overwrite", refusal.stderr)
                self.assert_tlt_angles(
                    output_dir,
                    mdoc_path,
                    slice_order,
                    expected_angles,
                )

        self.assertEqual(file_hashes(self.raw_dir), self.original_hashes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
