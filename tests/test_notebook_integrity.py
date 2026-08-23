import glob
import os
import nbformat
import pytest

NOTEBOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notebooks")


def test_notebooks_exist():
    notebook_files = glob.glob(os.path.join(NOTEBOOKS_DIR, "*.ipynb"))
    assert len(notebook_files) > 0, "No notebook files found in notebooks/ directory."


@pytest.mark.parametrize(
    "notebook_path",
    glob.glob(os.path.join(NOTEBOOKS_DIR, "*.ipynb"))
)
def test_notebook_format_and_schema(notebook_path: str):
    """Ensure all Jupyter notebooks strictly comply with nbformat v4.5 and contain unique cell IDs."""
    nb = nbformat.read(notebook_path, as_version=4)

    # 1. Official schema validation
    nbformat.validate(nb)

    # 2. Enforce version 4.5+
    assert nb.nbformat == 4, f"{notebook_path} must be nbformat 4"
    assert nb.nbformat_minor >= 5, f"{notebook_path} must be nbformat_minor >= 5"

    # 3. Enforce unique cell IDs
    cell_ids = []
    for idx, cell in enumerate(nb.cells):
        cell_id = cell.get("id")
        assert cell_id is not None and len(cell_id.strip()) > 0, (
            f"Cell at index {idx} in {notebook_path} is missing a required 'id' attribute."
        )
        assert cell_id not in cell_ids, (
            f"Duplicate cell id '{cell_id}' found at index {idx} in {notebook_path}."
        )
        cell_ids.append(cell_id)
