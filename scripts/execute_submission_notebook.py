"""Execute every submission cell in a fresh kernel using this Python interpreter."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import perf_counter

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager


def execute(root, *, working_directory=None):
    path = root / "notebooks/AgriPulse_813_PoC.ipynb"
    notebook = nbformat.read(path, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
            cell.metadata.pop("execution", None)
    start = perf_counter()
    # Only kernel connection/cache files live in this temporary directory.
    with tempfile.TemporaryDirectory(prefix="agripulse-kernel-") as runtime:
        manager = KernelManager(kernel_name="python3")
        manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        manager.connection_file = str(Path(runtime) / "kernel.json")
        client = NotebookClient(notebook, km=manager, timeout=180, allow_errors=False,
                                record_timing=False, resources={"metadata": {"path": str(working_directory or root)}})
        environment = dict(os.environ, IPYTHONDIR=str(Path(runtime) / "ipython"),
                           JUPYTER_RUNTIME_DIR=runtime, MPLCONFIGDIR=str(Path(runtime) / "matplotlib"))
        try:
            client.execute(env=environment, cleanup_kc=True)
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
    elapsed = perf_counter() - start
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code or any(cell.execution_count is None for cell in code):
        raise RuntimeError("Not all code cells executed")
    if not any("image/png" in output.get("data", {}) for cell in code for output in cell.outputs):
        raise RuntimeError("Notebook has no visible PNG output")
    for name in ("example_output.png", "example_summary.json"):
        if not (root / "results" / name).is_file():
            raise RuntimeError(f"Missing output: {name}")
    nbformat.validate(notebook)
    path.write_text(nbformat.writes(notebook), encoding="utf-8", newline="\n")
    return {"python_version": platform.python_version(), "notebook_runtime_seconds": round(elapsed, 3),
            "cells": len(notebook.cells), "code_cells": len(code), "gpu_required": False,
            "fresh_kernel": True, "external_network_disabled_in_notebook": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, help="Optional local verification JSON; not part of deterministic science output")
    args = parser.parse_args()
    result = execute(args.root.resolve())
    text = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8", newline="\n")
    print(text)
