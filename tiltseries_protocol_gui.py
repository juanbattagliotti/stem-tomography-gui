#!/usr/bin/env python3
"""
Small desktop GUI for prepare_warp_tiltseries.py.

This wraps the existing command-line tool so users can browse for files,
preview the command, save/load presets, and run the Warp preparation step
without building a long shell command by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


SLICE_ORDERS = ("tilt-ascending", "tilt-descending", "zvalue", "block")
OUTPUT_DTYPES = ("preserve", "float32", "uint16", "uint8")
COMPRESSIONS = ("none", "tiff_lzw", "tiff_deflate")
PRESET_VERSION = 1
TLT_ORDERS = ("block", "zvalue", "tilt-ascending", "tilt-descending")


class TiltPrepGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Warp Tilt-Series Preparation")
        self.root.geometry("1260x860")
        self.root.minsize(1080, 760)

        self.base_dir = Path(__file__).resolve().parent
        self.process: subprocess.Popen[str] | None = None
        self.worker_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._build_variables()
        self._build_layout()
        self._populate_defaults()
        self._update_mode_visibility()
        self._schedule_queue_poll()

    def _build_variables(self) -> None:
        python_default = sys.executable or "python3"
        script_default = self.base_dir / "prepare_warp_tiltseries.py"
        tlt_script_default = self.base_dir / "mdoc_to_tlt.py"
        output_default = self.base_dir / "warp_prep_output"

        self.python_var = tk.StringVar(value=str(python_default))
        self.script_var = tk.StringVar(value=str(script_default))
        self.tlt_script_var = tk.StringVar(value=str(tlt_script_default))
        self.input_mode_var = tk.StringVar(value="single_input")

        self.input_dir_var = tk.StringVar()
        self.mrc_dir_var = tk.StringVar()
        self.mdoc_dir_var = tk.StringVar()
        self.pairs_csv_var = tk.StringVar()

        self.output_dir_var = tk.StringVar(value=str(output_default))
        self.frames_subdir_var = tk.StringVar(value="frames")
        self.mdoc_subdir_var = tk.StringVar(value="mdoc")
        self.subframe_prefix_var = tk.StringVar()
        self.output_mdoc_suffix_var = tk.StringVar(value="_warp")

        self.slice_order_var = tk.StringVar(value="tilt-ascending")
        self.angle_decimals_var = tk.StringVar(value="1")
        self.preview_count_var = tk.StringVar(value="8")
        self.progress_every_var = tk.StringVar(value="25")

        self.output_dtype_var = tk.StringVar(value="preserve")
        self.compression_var = tk.StringVar(value="none")

        self.recursive_var = tk.BooleanVar(value=True)
        self.ignore_unmatched_var = tk.BooleanVar(value=False)
        self.ensure_num_subframes_var = tk.BooleanVar(value=False)
        self.mode0_unsigned_var = tk.BooleanVar(value=False)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)

        self.extra_args_var = tk.StringVar()
        self.tlt_mdoc_var = tk.StringVar()
        self.tlt_output_var = tk.StringVar()
        self.tlt_order_var = tk.StringVar(value="block")
        self.tlt_decimals_var = tk.StringVar(value="2")
        self.tlt_strip_zeros_var = tk.BooleanVar(value=False)
        self.tlt_overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready.")

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        self.form_parent = ttk.Frame(outer)
        self.form_parent.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.form_parent.columnconfigure(0, weight=1)
        self.form_parent.rowconfigure(0, weight=1)

        canvas = tk.Canvas(self.form_parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.form_parent, orient="vertical", command=canvas.yview)
        self.form_frame = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        self.form_frame.columnconfigure(0, weight=1)

        self.form_window = canvas.create_window((0, 0), window=self.form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.form_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(self.form_window, width=event.width),
        )

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        self._build_form_sections(self.form_frame)
        self._build_right_panel(right)

    def _build_form_sections(self, parent: ttk.Frame) -> None:
        self._add_runtime_section(parent).pack(fill="x", pady=(0, 8))
        self._add_input_section(parent).pack(fill="x", pady=(0, 8))
        self._add_output_section(parent).pack(fill="x", pady=(0, 8))
        self._add_mapping_section(parent).pack(fill="x", pady=(0, 8))
        self._add_image_section(parent).pack(fill="x", pady=(0, 8))
        self._add_flags_section(parent).pack(fill="x", pady=(0, 8))
        self._add_extra_section(parent).pack(fill="x", pady=(0, 8))
        self._add_tlt_section(parent).pack(fill="x", pady=(0, 8))

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        button_frame = ttk.LabelFrame(parent, text="Actions", padding=10)
        button_frame.grid(row=0, column=0, sticky="ew")
        for column in range(4):
            button_frame.columnconfigure(column, weight=1)

        ttk.Button(button_frame, text="Preview Command", command=self.preview_command).grid(
            row=0, column=0, padx=(0, 6), sticky="ew"
        )
        ttk.Button(button_frame, text="Run", command=self.run_command).grid(
            row=0, column=1, padx=6, sticky="ew"
        )
        ttk.Button(button_frame, text="Stop", command=self.stop_command).grid(
            row=0, column=2, padx=(6, 0), sticky="ew"
        )
        ttk.Button(button_frame, text="Write TLT", command=self.run_tlt_command).grid(
            row=0, column=3, padx=(6, 0), sticky="ew"
        )

        preset_frame = ttk.LabelFrame(parent, text="Presets", padding=10)
        preset_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        preset_frame.columnconfigure(0, weight=1)
        preset_frame.rowconfigure(0, weight=1)

        preset_buttons = ttk.Frame(preset_frame)
        preset_buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(preset_buttons, text="Save Preset", command=self.save_preset).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(preset_buttons, text="Load Preset", command=self.load_preset).pack(side="left")

        self.command_text = tk.Text(
            preset_frame,
            wrap="word",
            height=10,
            font=("Menlo", 11),
        )
        self.command_text.pack(fill="both", expand=True)

        log_frame = ttk.LabelFrame(parent, text="Run Log", padding=10)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            state="disabled",
            height=24,
            font=("Menlo", 11),
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

        status = ttk.Label(parent, textvariable=self.status_var, anchor="w")
        status.grid(row=4, column=0, sticky="ew", pady=(8, 0))

    def _add_runtime_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Runtime", padding=10)
        frame.columnconfigure(1, weight=1)
        self._entry_row(
            frame,
            row=0,
            label="Python",
            variable=self.python_var,
            browse="file",
            filetypes=[("Python", "python*"), ("All files", "*")],
        )
        self._entry_row(
            frame,
            row=1,
            label="Script",
            variable=self.script_var,
            browse="file",
            filetypes=[("Python", "*.py"), ("All files", "*")],
        )
        return frame

    def _add_input_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Inputs", padding=10)
        frame.columnconfigure(0, weight=1)

        mode_frame = ttk.Frame(frame)
        mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for column in range(3):
            mode_frame.columnconfigure(column, weight=1)

        ttk.Radiobutton(
            mode_frame,
            text="One input folder",
            variable=self.input_mode_var,
            value="single_input",
            command=self._update_mode_visibility,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Separate MRC and MDOC folders",
            variable=self.input_mode_var,
            value="split_input",
            command=self._update_mode_visibility,
        ).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Pairs CSV",
            variable=self.input_mode_var,
            value="pairs_csv",
            command=self._update_mode_visibility,
        ).grid(row=0, column=2, sticky="w")

        self.input_mode_frames: dict[str, ttk.Frame] = {}

        single = ttk.Frame(frame)
        single.columnconfigure(1, weight=1)
        self._entry_row(single, 0, "Input folder", self.input_dir_var, browse="dir")
        self.input_mode_frames["single_input"] = single

        split = ttk.Frame(frame)
        split.columnconfigure(1, weight=1)
        self._entry_row(split, 0, "MRC folder", self.mrc_dir_var, browse="dir")
        self._entry_row(split, 1, "MDOC folder", self.mdoc_dir_var, browse="dir")
        self.input_mode_frames["split_input"] = split

        csv_frame = ttk.Frame(frame)
        csv_frame.columnconfigure(1, weight=1)
        self._entry_row(
            csv_frame,
            0,
            "Pairs CSV",
            self.pairs_csv_var,
            browse="file",
            filetypes=[("CSV", "*.csv"), ("All files", "*")],
        )
        self.input_mode_frames["pairs_csv"] = csv_frame

        for mode_frame_widget in self.input_mode_frames.values():
            mode_frame_widget.grid(row=1, column=0, sticky="ew")

        return frame

    def _add_output_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Output", padding=10)
        frame.columnconfigure(1, weight=1)
        self._entry_row(frame, 0, "Output folder", self.output_dir_var, browse="dir")
        self._entry_row(frame, 1, "Frames subdir", self.frames_subdir_var)
        self._entry_row(frame, 2, "MDOC subdir", self.mdoc_subdir_var)
        self._entry_row(frame, 3, "SubFramePath prefix", self.subframe_prefix_var)
        self._entry_row(frame, 4, "Output MDOC suffix", self.output_mdoc_suffix_var)
        return frame

    def _add_mapping_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Mapping", padding=10)
        frame.columnconfigure(1, weight=1)
        self._combo_row(frame, 0, "Slice order", self.slice_order_var, SLICE_ORDERS)
        self._entry_row(frame, 1, "Angle decimals", self.angle_decimals_var)
        self._entry_row(frame, 2, "Preview count", self.preview_count_var)
        self._entry_row(frame, 3, "Progress every", self.progress_every_var)
        return frame

    def _add_image_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Image Conversion", padding=10)
        frame.columnconfigure(1, weight=1)
        self._combo_row(frame, 0, "Output dtype", self.output_dtype_var, OUTPUT_DTYPES)
        self._combo_row(frame, 1, "Compression", self.compression_var, COMPRESSIONS)
        return frame

    def _add_flags_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Flags", padding=10)
        for column in range(2):
            frame.columnconfigure(column, weight=1)

        ttk.Checkbutton(frame, text="Recursive search", variable=self.recursive_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(frame, text="Ignore unmatched files", variable=self.ignore_unmatched_var).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Checkbutton(
            frame,
            text="Insert NumSubFrames = 1 when missing",
            variable=self.ensure_num_subframes_var,
        ).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(frame, text="Treat mode 0 as unsigned", variable=self.mode0_unsigned_var).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Checkbutton(frame, text="Overwrite existing output", variable=self.overwrite_var).grid(
            row=2, column=0, sticky="w"
        )
        ttk.Checkbutton(frame, text="Dry run only", variable=self.dry_run_var).grid(
            row=2, column=1, sticky="w"
        )
        return frame

    def _add_extra_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Extra CLI Arguments", padding=10)
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="Optional. Use this only for advanced flags not exposed in the GUI.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self._entry_row(frame, 1, "Extra args", self.extra_args_var)
        return frame

    def _add_tlt_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="MDOC To TLT Utility", padding=10)
        frame.columnconfigure(1, weight=1)
        self._entry_row(
            frame,
            0,
            "TLT script",
            self.tlt_script_var,
            browse="file",
            filetypes=[("Python", "*.py"), ("All files", "*")],
        )
        self._entry_row(
            frame,
            1,
            "Input MDOC",
            self.tlt_mdoc_var,
            browse="file",
            filetypes=[("MDOC", "*.mdoc"), ("All files", "*")],
        )
        self._entry_row(
            frame,
            2,
            "Output TLT",
            self.tlt_output_var,
            browse="save",
            filetypes=[("TLT", "*.tlt"), ("Text", "*.txt"), ("All files", "*")],
        )
        self._combo_row(frame, 3, "Angle order", self.tlt_order_var, TLT_ORDERS)
        self._entry_row(frame, 4, "Decimals", self.tlt_decimals_var)

        flags = ttk.Frame(frame)
        flags.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        flags.columnconfigure(0, weight=1)
        flags.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            flags,
            text="Strip trailing zeros",
            variable=self.tlt_strip_zeros_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            flags,
            text="Overwrite existing TLT",
            variable=self.tlt_overwrite_var,
        ).grid(row=0, column=1, sticky="w")
        return frame

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse: str | None = None,
        filetypes: list[tuple[str, str]] | None = None,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        if browse is not None:
            ttk.Button(
                parent,
                text="Browse",
                command=lambda: self._browse_path(variable, browse, filetypes),
            ).grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=4)

    def _combo_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=4)

    def _browse_path(
        self,
        variable: tk.StringVar,
        browse: str,
        filetypes: list[tuple[str, str]] | None,
    ) -> None:
        current = variable.get().strip()
        initial = current or str(self.base_dir)
        if browse == "dir":
            selected = filedialog.askdirectory(initialdir=initial)
        elif browse == "save":
            selected = filedialog.asksaveasfilename(initialdir=initial, filetypes=filetypes)
        else:
            selected = filedialog.askopenfilename(initialdir=initial, filetypes=filetypes)
        if selected:
            variable.set(selected)

    def _populate_defaults(self) -> None:
        self.preview_command()

    def _update_mode_visibility(self) -> None:
        current = self.input_mode_var.get()
        for mode, frame in self.input_mode_frames.items():
            if mode == current:
                frame.grid()
            else:
                frame.grid_remove()
        self.preview_command()

    def _collect_numeric(self, value: str, label: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{label} cannot be empty.")
        int(stripped)
        return stripped

    def build_command(self) -> list[str]:
        python_path = self.python_var.get().strip()
        script_path = self.script_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not python_path:
            raise ValueError("Python path cannot be empty.")
        if not script_path:
            raise ValueError("Script path cannot be empty.")
        if not output_dir:
            raise ValueError("Output folder cannot be empty.")

        command = [python_path, script_path]

        mode = self.input_mode_var.get()
        if mode == "single_input":
            input_dir = self.input_dir_var.get().strip()
            if not input_dir:
                raise ValueError("Input folder cannot be empty.")
            command.extend(["--input", input_dir])
        elif mode == "split_input":
            mrc_dir = self.mrc_dir_var.get().strip()
            mdoc_dir = self.mdoc_dir_var.get().strip()
            if not mrc_dir or not mdoc_dir:
                raise ValueError("MRC folder and MDOC folder are both required.")
            command.extend(["--mrc-dir", mrc_dir, "--mdoc-dir", mdoc_dir])
        elif mode == "pairs_csv":
            pairs_csv = self.pairs_csv_var.get().strip()
            if not pairs_csv:
                raise ValueError("Pairs CSV path cannot be empty.")
            command.extend(["--pairs-csv", pairs_csv])
        else:
            raise ValueError(f"Unsupported input mode: {mode}")

        command.extend(["--output", output_dir])

        self._append_if_value(command, "--frames-subdir", self.frames_subdir_var.get().strip(), "frames")
        self._append_if_value(command, "--mdoc-subdir", self.mdoc_subdir_var.get().strip(), "mdoc")
        self._append_if_value(
            command,
            "--subframe-prefix",
            self.subframe_prefix_var.get().strip(),
            None,
        )
        self._append_if_value(
            command,
            "--output-mdoc-suffix",
            self.output_mdoc_suffix_var.get().strip(),
            "_warp",
        )

        command.extend(["--slice-order", self.slice_order_var.get().strip() or "tilt-ascending"])
        command.extend(["--angle-decimals", self._collect_numeric(self.angle_decimals_var.get(), "Angle decimals")])
        command.extend(["--preview-count", self._collect_numeric(self.preview_count_var.get(), "Preview count")])
        command.extend(
            ["--progress-every", self._collect_numeric(self.progress_every_var.get(), "Progress every")]
        )
        command.extend(["--output-dtype", self.output_dtype_var.get().strip() or "preserve"])
        command.extend(["--compression", self.compression_var.get().strip() or "none"])

        self._append_flag(command, "--recursive", self.recursive_var.get())
        self._append_flag(command, "--ignore-unmatched", self.ignore_unmatched_var.get())
        self._append_flag(command, "--ensure-num-subframes", self.ensure_num_subframes_var.get())
        self._append_flag(command, "--mode0-unsigned", self.mode0_unsigned_var.get())
        self._append_flag(command, "--overwrite", self.overwrite_var.get())
        self._append_flag(command, "--dry-run", self.dry_run_var.get())

        extra_args = self.extra_args_var.get().strip()
        if extra_args:
            command.extend(shlex.split(extra_args))

        return command

    def build_tlt_command(self) -> list[str]:
        python_path = self.python_var.get().strip()
        script_path = self.tlt_script_var.get().strip()
        mdoc_path = self.tlt_mdoc_var.get().strip()
        output_path = self.tlt_output_var.get().strip()

        if not python_path:
            raise ValueError("Python path cannot be empty.")
        if not script_path:
            raise ValueError("TLT script path cannot be empty.")
        if not mdoc_path:
            raise ValueError("Input MDOC cannot be empty.")
        if not output_path:
            raise ValueError("Output TLT cannot be empty.")

        command = [
            python_path,
            script_path,
            "--mdoc",
            mdoc_path,
            "--output",
            output_path,
            "--order",
            self.tlt_order_var.get().strip() or "block",
            "--decimals",
            self._collect_numeric(self.tlt_decimals_var.get(), "TLT decimals"),
        ]

        if self.tlt_strip_zeros_var.get():
            command.append("--strip-trailing-zeros")
        if self.tlt_overwrite_var.get():
            command.append("--overwrite")
        return command

    def _append_if_value(
        self,
        command: list[str],
        flag: str,
        value: str,
        default: str | None,
    ) -> None:
        if not value:
            return
        if default is not None and value == default:
            return
        command.extend([flag, value])

    def _append_flag(self, command: list[str], flag: str, enabled: bool) -> None:
        if enabled:
            command.append(flag)

    def preview_command(self) -> None:
        try:
            command = self.build_command()
            rendered = shlex.join(command)
            self.command_text.delete("1.0", "end")
            self.command_text.insert("1.0", rendered)
            self.status_var.set("Command preview updated.")
        except Exception as exc:  # noqa: BLE001
            self.command_text.delete("1.0", "end")
            self.command_text.insert("1.0", f"Cannot build command yet:\n{exc}")
            self.status_var.set("Waiting for required inputs.")

    def run_command(self) -> None:
        if self.process is not None:
            messagebox.showinfo("Already running", "A job is already running in this window.")
            return

        try:
            command = self.build_command()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Cannot run", str(exc))
            return

        self.preview_command()
        self._clear_log()
        self._append_log("Running command:\n" + shlex.join(command) + "\n\n")

        self.status_var.set("Running...")
        self.worker_thread = threading.Thread(
            target=self._run_subprocess,
            args=(command,),
            daemon=True,
        )
        self.worker_thread.start()

    def run_tlt_command(self) -> None:
        if self.process is not None:
            messagebox.showinfo("Already running", "A job is already running in this window.")
            return

        try:
            command = self.build_tlt_command()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Cannot write TLT", str(exc))
            return

        self._clear_log()
        self._append_log("Running TLT conversion:\n" + shlex.join(command) + "\n\n")
        self.status_var.set("Writing TLT...")
        self.worker_thread = threading.Thread(
            target=self._run_subprocess,
            args=(command,),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_subprocess(self, command: list[str]) -> None:
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.output_queue.put(("log", line))
            returncode = self.process.wait()
            if returncode == 0:
                self.output_queue.put(("status", "Finished successfully."))
            else:
                self.output_queue.put(("status", f"Finished with exit code {returncode}."))
        except FileNotFoundError as exc:
            self.output_queue.put(("status", f"Launch failed: {exc}"))
        except Exception as exc:  # noqa: BLE001
            self.output_queue.put(("status", f"Unexpected error: {exc}"))
        finally:
            self.output_queue.put(("done", ""))

    def stop_command(self) -> None:
        if self.process is None:
            self.status_var.set("Nothing is running.")
            return
        self.process.terminate()
        self._append_log("\nStopping process...\n")
        self.status_var.set("Stopping...")

    def _schedule_queue_poll(self) -> None:
        self.root.after(150, self._poll_queue)

    def _poll_queue(self) -> None:
        while True:
            try:
                kind, payload = self.output_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._append_log(payload)
            elif kind == "status":
                self.status_var.set(payload)
                self._append_log("\n" + payload + "\n")
            elif kind == "done":
                self.process = None
                self.worker_thread = None

        self.root.after(150, self._poll_queue)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def save_preset(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save preset",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*")],
            initialdir=str(self.base_dir),
        )
        if not path:
            return

        payload = {
            "preset_version": PRESET_VERSION,
            "python": self.python_var.get(),
            "script": self.script_var.get(),
            "tlt_script": self.tlt_script_var.get(),
            "input_mode": self.input_mode_var.get(),
            "input_dir": self.input_dir_var.get(),
            "mrc_dir": self.mrc_dir_var.get(),
            "mdoc_dir": self.mdoc_dir_var.get(),
            "pairs_csv": self.pairs_csv_var.get(),
            "output_dir": self.output_dir_var.get(),
            "frames_subdir": self.frames_subdir_var.get(),
            "mdoc_subdir": self.mdoc_subdir_var.get(),
            "subframe_prefix": self.subframe_prefix_var.get(),
            "output_mdoc_suffix": self.output_mdoc_suffix_var.get(),
            "slice_order": self.slice_order_var.get(),
            "angle_decimals": self.angle_decimals_var.get(),
            "preview_count": self.preview_count_var.get(),
            "progress_every": self.progress_every_var.get(),
            "output_dtype": self.output_dtype_var.get(),
            "compression": self.compression_var.get(),
            "recursive": self.recursive_var.get(),
            "ignore_unmatched": self.ignore_unmatched_var.get(),
            "ensure_num_subframes": self.ensure_num_subframes_var.get(),
            "mode0_unsigned": self.mode0_unsigned_var.get(),
            "overwrite": self.overwrite_var.get(),
            "dry_run": self.dry_run_var.get(),
            "extra_args": self.extra_args_var.get(),
            "tlt_mdoc": self.tlt_mdoc_var.get(),
            "tlt_output": self.tlt_output_var.get(),
            "tlt_order": self.tlt_order_var.get(),
            "tlt_decimals": self.tlt_decimals_var.get(),
            "tlt_strip_zeros": self.tlt_strip_zeros_var.get(),
            "tlt_overwrite": self.tlt_overwrite_var.get(),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.status_var.set(f"Preset saved: {path}")

    def load_preset(self) -> None:
        path = filedialog.askopenfilename(
            title="Load preset",
            filetypes=[("JSON", "*.json"), ("All files", "*")],
            initialdir=str(self.base_dir),
        )
        if not path:
            return

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.python_var.set(payload.get("python", self.python_var.get()))
        self.script_var.set(payload.get("script", self.script_var.get()))
        self.tlt_script_var.set(payload.get("tlt_script", self.tlt_script_var.get()))
        self.input_mode_var.set(payload.get("input_mode", self.input_mode_var.get()))
        self.input_dir_var.set(payload.get("input_dir", ""))
        self.mrc_dir_var.set(payload.get("mrc_dir", ""))
        self.mdoc_dir_var.set(payload.get("mdoc_dir", ""))
        self.pairs_csv_var.set(payload.get("pairs_csv", ""))
        self.output_dir_var.set(payload.get("output_dir", self.output_dir_var.get()))
        self.frames_subdir_var.set(payload.get("frames_subdir", "frames"))
        self.mdoc_subdir_var.set(payload.get("mdoc_subdir", "mdoc"))
        self.subframe_prefix_var.set(payload.get("subframe_prefix", ""))
        self.output_mdoc_suffix_var.set(payload.get("output_mdoc_suffix", "_warp"))
        self.slice_order_var.set(payload.get("slice_order", "tilt-ascending"))
        self.angle_decimals_var.set(payload.get("angle_decimals", "1"))
        self.preview_count_var.set(payload.get("preview_count", "8"))
        self.progress_every_var.set(payload.get("progress_every", "25"))
        self.output_dtype_var.set(payload.get("output_dtype", "preserve"))
        self.compression_var.set(payload.get("compression", "none"))
        self.recursive_var.set(payload.get("recursive", True))
        self.ignore_unmatched_var.set(payload.get("ignore_unmatched", False))
        self.ensure_num_subframes_var.set(payload.get("ensure_num_subframes", False))
        self.mode0_unsigned_var.set(payload.get("mode0_unsigned", False))
        self.overwrite_var.set(payload.get("overwrite", False))
        self.dry_run_var.set(payload.get("dry_run", False))
        self.extra_args_var.set(payload.get("extra_args", ""))
        self.tlt_mdoc_var.set(payload.get("tlt_mdoc", ""))
        self.tlt_output_var.set(payload.get("tlt_output", ""))
        self.tlt_order_var.set(payload.get("tlt_order", "block"))
        self.tlt_decimals_var.set(payload.get("tlt_decimals", "2"))
        self.tlt_strip_zeros_var.set(payload.get("tlt_strip_zeros", False))
        self.tlt_overwrite_var.set(payload.get("tlt_overwrite", False))
        self._update_mode_visibility()
        self.preview_command()
        self.status_var.set(f"Preset loaded: {path}")


def main() -> int:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    TiltPrepGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
