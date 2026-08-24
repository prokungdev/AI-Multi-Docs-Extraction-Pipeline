"""
Unit test to verify Jupyter Notebook compliance with nbformat 4.5+ schema.
Uses standard library json parsing to avoid mandatory external dependencies.
"""

import glob
import json
import os
import pytest

# Resolve absolute path to notebooks/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOTEBOOKS_DIR = os.path.join(PROJECT_ROOT, "notebooks")
NOTEBOOK_FILES = glob.glob(os.path.join(NOTEBOOKS_DIR, "*.ipynb"))


def test_notebooks_exist():
    """Verify notebooks directory exists and contains at least one notebook."""
    assert len(NOTEBOOK_FILES) > 0, f"No notebook files found in {NOTEBOOKS_DIR}"


@pytest.mark.parametrize("notebook_path", NOTEBOOK_FILES)
def test_notebook_format_and_schema(notebook_path: str):
    """Ensure all Jupyter notebooks strictly comply with nbformat v4.5 and contain unique cell IDs."""
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb_data = json.load(f)

    # 1. Check top-level format version
    assert nb_data.get("nbformat") == 4, f"{notebook_path} must be nbformat 4"
    assert nb_data.get("nbformat_minor", 0) >= 5, f"{notebook_path} must be nbformat_minor >= 5"

    # 2. Enforce unique cell IDs across all cells
    cells = nb_data.get("cells", [])
    cell_ids = set()
    for idx, cell in enumerate(cells):
        cell_id = cell.get("id")
        assert cell_id is not None and len(str(cell_id).strip()) > 0, (
            f"Cell at index {idx} in {notebook_path} is missing a required 'id' attribute."
        )
        assert cell_id not in cell_ids, (
            f"Duplicate cell id '{cell_id}' found at index {idx} in {notebook_path}."
        )
        cell_ids.add(cell_id)
