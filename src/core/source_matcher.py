import os
import json
import re
import pymupdf as fitz
from PIL import Image
from google import genai
from google.genai import types
from loguru import logger


def load_merchant_rules(domain: str, configs_dir: str = "configs") -> dict:
    """
    Loads rules.json for each merchant source under configs/domains/{domain}/sources/.
    
    Returns:
        A dictionary mapping source names to their rules (keywords and tax_ids).
    """
    sources_dir = os.path.join(configs_dir, "domains", domain, "sources")
    if not os.path.exists(sources_dir):
        return {}
        
    merchant_rules = {}
    for entry in os.listdir(sources_dir):
        entry_path = os.path.join(sources_dir, entry)
        if os.path.isdir(entry_path) and not entry.startswith("_"):
            rules_path = os.path.join(entry_path, "rules.json")
            if os.path.exists(rules_path):
                try:
                    with open(rules_path, "r", encoding="utf-8") as f:
                        merchant_rules[entry] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading rules for source {entry}: {e}")
                    
    return merchant_rules

def match_source_by_filename(filename: str, merchant_rules: dict) -> str | None:
    """
    Attempts to match a source by checking if the filename starts with one of the defined prefixes.
    
    Returns:
        The matched source name, or None.
    """
    filename_lower = filename.lower()
    for source, rules in merchant_rules.items():
        prefixes = rules.get("file_prefixes", [])
        for prefix in prefixes:
            if prefix and filename_lower.startswith(prefix.lower()):
                return source
    return None


def match_source_by_text(text: str, merchant_rules: dict) -> str | None:
    """
    Attempts to match a source by performing a case-insensitive check of keywords
    and Tax IDs on the provided text.
    
    Returns:
        The matched source name, or None if no match is found.
    """
    if not text.strip():
        return None
        
    normalized_text = text.lower()
    
    # First pass: Match by Tax ID (usually more specific than keywords)
    for source_name, rules in merchant_rules.items():
        tax_ids = rules.get("tax_ids", [])
        for tax_id in tax_ids:
            # Check for tax ID with or without spaces/dashes
            clean_tax_id = tax_id.replace(" ", "").replace("-", "")
            clean_text = normalized_text.replace(" ", "").replace("-", "")
            if clean_tax_id in clean_text:
                return source_name
                
    # Second pass: Match by keywords
    for source_name, rules in merchant_rules.items():
        keywords = rules.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in normalized_text:
                return source_name
                
    return None

def match_source_by_vision(image_path: str, merchant_rules: dict, settings: dict = None) -> str:
    """
    Fallback classifier using Gemini Vision. Sends the receipt image
    along with candidate rules to identify the source merchant.
    
    Returns:
        The identified source name, or '_default' if undetermined.
    """
    if settings is None:
        from src.core.config_loader import load_system_settings
        settings = load_system_settings()
        
    ai_cfg = settings.get("ai_provider", {})
    provider = ai_cfg.get("active_provider", "gemini")
    provider_cfg = ai_cfg.get(provider, {})
    model_name = provider_cfg.get("model_name", "gemini-3.5-flash")
    api_key_env = provider_cfg.get("api_key_env", "GEMINI_API_KEY")
    api_key = os.getenv(api_key_env)
    
    if not api_key:
        logger.warning(f"API key environment variable '{api_key_env}' is not set. Cannot perform vision source matching.")
        return "_default"
        
    client = genai.Client(api_key=api_key)
    
    # Format candidate merchants and rules for the model prompt
    rules_summary = ""
    for source_name, rules in merchant_rules.items():
        rules_summary += f"- {source_name}: Keywords={rules.get('keywords', [])}, Tax IDs={rules.get('tax_ids', [])}\n"
        
    prompt = f"""
    You are a document classifier. Analyze the provided receipt image and classify it into one of the following candidate merchant sources.
    
    Candidate Merchant Sources and Matching Rules:
    {rules_summary}
    
    Instructions:
    - Compare the merchant name, logo, tax ID, or items in the image against the rules above.
    - If a match is found, reply with ONLY the matching merchant identifier string.
    - If the receipt does not match any candidate rules, reply with '_default'.
    - Do not output any explanation or extra text. Output exactly one word.
    """
    
    try:
        image = Image.open(image_path)
        response = client.models.generate_content(
            model=model_name,
            contents=[image, prompt]
        )
        matched_source = response.text.strip().lower()
        
        # Verify the returned source is one of our candidate sources
        if matched_source in merchant_rules:
            return matched_source
            
    except Exception as e:
        logger.error(f"Error during Gemini Vision source matching: {e}")
        
    return "_default"

def match_source(file_path: str, domain: str, first_page_image_path: str | None = None, settings: dict = None) -> str:
    """
    Matches the source of the document (PDF or Image) by first extracting digital text,
    and then falling back to Gemini Vision classification if text extraction fails.
    
    Args:
        file_path: Path to the input file (can be PDF or PNG/JPG image).
        domain: The domain category (e.g. 'expense_receipt').
        first_page_image_path: Optional path to the pre-rendered first page image of a PDF
                               (used for vision fallback).
        settings: Optional system settings dictionary.
                               
    Returns:
        The matched merchant source identifier, or '_default'.
    """
    if settings is None:
        from src.core.config_loader import load_system_settings
        settings = load_system_settings()
        
    merchant_rules = load_merchant_rules(domain)
    if not merchant_rules:
        return "_default"
        
    filename = os.path.basename(file_path)
    
    # 1. Match by filename prefix (Instant, local)
    matched_source = match_source_by_filename(filename, merchant_rules)
    if matched_source:
        logger.info(f"Matched source '{matched_source}' by filename prefix for '{filename}'")
        return matched_source
        
    extracted_text = ""
    
    # 2. Try to extract digital text if it's a PDF
    if file_path.lower().endswith(".pdf"):
        try:
            doc = fitz.open(file_path)
            # Combine text from all pages (or just the first page to be fast)
            for page in doc:
                extracted_text += page.get_text()
            doc.close()
        except Exception as e:
            logger.warning(f"Failed to extract digital text from PDF: {e}")
            
    # 2. Local matching on text
    matched_source = match_source_by_text(extracted_text, merchant_rules)
    if matched_source:
        return matched_source
        
    # 3. Vision-based matching fallback (Optional based on use_ai_fallback_matching config)
    img_cfg = settings.get("image_processing", {}) or settings.get("archiving", {})
    use_ai_fallback = img_cfg.get("use_ai_fallback_matching", True)
        
    if use_ai_fallback:
        logger.info("Local matching failed. Falling back to AI Vision classification using Page 1 image...")
        if file_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".tiff")):
            return match_source_by_vision(file_path, merchant_rules, settings=settings)
        elif first_page_image_path and os.path.exists(first_page_image_path):
            return match_source_by_vision(first_page_image_path, merchant_rules, settings=settings)
            
    return "_default"
