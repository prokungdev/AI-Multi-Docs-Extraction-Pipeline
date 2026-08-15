import os
import json

def get_nested_value(data: dict | None, path: str) -> any:
    """
    Traverses a dictionary using dot notation (e.g. 'financial_summary.net_amount').
    
    Args:
        data: The input dictionary.
        path: The dot-notation path string.
        
    Returns:
        The value at the path, or an empty string if any key is missing.
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
    
    Args:
        extracted_data: Dict of extracted data conforming to schema.json.
        template_path: Path to the output mapping template JSON.
        
    Returns:
        A list of flattened dictionaries representing rows.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template config file not found at: {template_path}")
        
    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)
        
    granularity = template.get("granularity", "summary")
    columns = template.get("columns", {})
    
    rows = []
    
    if granularity == "summary":
        # 1 Row per receipt
        row = {}
        for col_name, path in columns.items():
            row[col_name] = get_nested_value(extracted_data, path)
        rows.append(row)
        
    elif granularity == "line_items":
        # 1 Row per item inside the receipt. Clone top-level values for each item.
        items = extracted_data.get("items", [])
        
        # If the items list is empty, create at least one row with empty item fields
        # to prevent losing top-level invoice summary details.
        if not items:
            items = [{}]
            
        for item in items:
            row = {}
            for col_name, path in columns.items():
                if path.startswith("item."):
                    # Extract the sub-field under the item (e.g. 'item.name' -> 'name')
                    item_field = path.split(".", 1)[1]
                    row[col_name] = item.get(item_field, "")
                else:
                    # Resolve top-level fields
                    row[col_name] = get_nested_value(extracted_data, path)
            rows.append(row)
            
    return rows
