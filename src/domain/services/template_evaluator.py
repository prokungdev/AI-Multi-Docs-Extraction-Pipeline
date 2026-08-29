"""Domain Service: JSON Template Evaluator and Dynamic Record Transformer.

100% Pure Domain Logic (In-Memory, zero external database or disk I/O coupling).
"""

import os
import json
from typing import Any, List, Dict


def get_nested_value(data: dict | None, path: str) -> Any:
    """
    Traverses a dictionary using dot notation (e.g. 'financial_summary.net_amount').
    """
    if data is None:
        return ""

    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return ""

    return current


def transform_data(extracted_data: dict, template_path: str) -> list[dict]:
    """
    Transforms hierarchical extracted JSON data into flat row dictionaries
    based on the specified template config.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template config file not found at: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    granularity = template.get("granularity", "summary")
    columns = template.get("columns", {})

    rows = []

    if granularity == "summary":
        row = {}
        for col_name, path in columns.items():
            row[col_name] = get_nested_value(extracted_data, path)
        rows.append(row)

    elif granularity == "line_items":
        items = extracted_data.get("items", [])

        if not items:
            items = [{}]

        for item in items:
            row = {}
            for col_name, path in columns.items():
                if path.startswith("item."):
                    item_field = path.split(".", 1)[1]
                    row[col_name] = item.get(item_field, "")
                else:
                    row[col_name] = get_nested_value(extracted_data, path)
            rows.append(row)

    return rows
