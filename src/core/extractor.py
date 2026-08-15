import os
import json
import copy
from PIL import Image
from google import genai
from google.genai import types
from loguru import logger


def clean_schema_for_gemini(schema: dict) -> dict:
    """
    Converts a standard JSON Schema dictionary into the OpenAPI schema format
    required by the Gemini API (e.g. uppercase types, removing root meta keys).
    """
    schema_copy = copy.deepcopy(schema)
    
    # Remove root-level metadata keys that Gemini does not support
    schema_copy.pop("$schema", None)
    schema_copy.pop("title", None)
    
    def convert_types(d):
        if not isinstance(d, dict):
            return d
            
        # Convert type values to uppercase (e.g., 'object' -> 'OBJECT')
        if "type" in d and isinstance(d["type"], str):
            d["type"] = d["type"].upper()
            
        # Recursively traverse nested items and properties
        for k, v in d.items():
            if isinstance(v, dict):
                convert_types(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        convert_types(item)
        return d
        
    return convert_types(schema_copy)

def extract_receipt_data(image_path: str, source: str, domain: str, configs_dir: str = "configs") -> dict:
    """
    Extracts structured data from an image file using Gemini 2.5 Flash and a specific
    prompt/schema configuration.
    
    Args:
        image_path: Path to the receipt image file.
        source: The merchant identifier (e.g. 'grab_thailand').
        domain: The domain folder name (e.g. 'expense_receipt').
        configs_dir: The root configuration directory.
        
    Returns:
        A dictionary containing the extracted data conforming to the domain's schema.
    """
    domain_dir = os.path.join(configs_dir, "domains", domain)
    schema_path = os.path.join(domain_dir, "schema.json")
    
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")
        
    # 1. Load and clean the schema
    with open(schema_path, "r", encoding="utf-8") as f:
        raw_schema = json.load(f)
    cleaned_schema = clean_schema_for_gemini(raw_schema)
    
    # 2. Load the source-specific prompt, falling back to _default if not found
    prompt_dir = os.path.join(domain_dir, "sources", source)
    prompt_path = os.path.join(prompt_dir, "prompt.txt")
    
    if not os.path.exists(prompt_path):
        # Fallback to _default
        prompt_path = os.path.join(domain_dir, "sources", "_default", "prompt.txt")
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")
            
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()
        
    # 3. Load the receipt image
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Receipt image not found at: {image_path}")
    image = Image.open(image_path)
    
    # 4. Initialize GenAI client and call the Gemini API with Structured Output
    client = genai.Client()
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt_text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=cleaned_schema,
            ),
        )
        
        # 5. Parse and return the JSON response
        result_text = response.text.strip()
        extracted_data = json.loads(result_text)
        return extracted_data
        
    except Exception as e:
        logger.error(f"Error during Gemini extraction: {e}")
        raise e
