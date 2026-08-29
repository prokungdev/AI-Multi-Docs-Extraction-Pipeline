"""Image Processing & Document Splitting Service Layer.

Handles image resizing, optimization (Lanczos), EXIF orientation, JPEG/DPI compression,
and page splitting orchestration for the document ingestion pipeline.
"""

import os
import re
import asyncio
from typing import List, Optional
from PIL import Image, ImageOps
from src.infrastructure.core.logger import logger
from .pdf_service import PDFService


def sanitize_filename_part(text: str) -> str:
    """Sanitizes string for safe filesystem usage by replacing whitespace/illegal chars with underscores."""
    if not text:
        return "unnamed"
    clean = re.sub(r'[\\/*?:"<>|\s]+', '_', str(text).strip())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean or "unnamed"


def format_page_filename(
    pattern: str = "{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}",
    doc_type: Optional[str] = None,
    tax_id: str = "",
    merchant_id: str = None,
    source: str = None,
    original_filename: str = "document",
    page_no: int = 1,
    batch_id: str = "",
    doc_no: str = "",
    image_format: str = "jpg"
) -> str:
    """Formats split page filename based on configurable pattern."""
    ext = image_format.lower().replace(".", "")
    orig_base = os.path.splitext(os.path.basename(original_filename))[0] if original_filename else "document"
    clean_orig = sanitize_filename_part(orig_base)
    effective_doc_type = doc_type or "expense_receipt"
    clean_doc_type = sanitize_filename_part(effective_doc_type)

    if tax_id and str(tax_id).strip():
        clean_tax_id = sanitize_filename_part(str(tax_id).strip())
    else:
        clean_tax_id = "no_tax"

    raw_merchant = merchant_id or source or "_uncategorized"
    clean_merchant = sanitize_filename_part(raw_merchant)
    short_batch = batch_id[:8].replace("-", "") if batch_id else ""

    try:
        formatted = pattern.format(
            doc_type=clean_doc_type,
            domain=clean_doc_type,
            tax_id=clean_tax_id,
            source=clean_merchant,
            merchant=clean_merchant,
            merchant_id=clean_merchant,
            original_filename=clean_orig,
            original_name=clean_orig,
            page_no=page_no,
            batch_id=short_batch or batch_id,
            short_batch_id=short_batch,
            doc_no=doc_no or clean_orig
        )
    except Exception as fe:
        logger.warning(f"Error formatting filename pattern '{pattern}': {fe}. Using fallback format.")
        formatted = f"{clean_doc_type}_{clean_tax_id}_{clean_orig}_{short_batch}_p{page_no}"

    clean_filename = sanitize_filename_part(formatted)
    return f"{clean_filename}.{ext}"


def resize_and_save_image(
    pil_img: Image.Image,
    output_path: str,
    image_format: str = "jpg",
    quality: int = 85,
    max_dimension: int = 1800
) -> str:
    """Resizes a PIL image using Lanczos interpolation if its dimensions exceed max_dimension."""
    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    if pil_img.mode in ("RGBA", "P", "LA"):
        rgb_img = Image.new("RGB", pil_img.size, (255, 255, 255))
        if pil_img.mode == "RGBA":
            rgb_img.paste(pil_img, mask=pil_img.split()[3])
        else:
            rgb_img.paste(pil_img.convert("RGBA"), mask=pil_img.convert("RGBA").split()[3])
        pil_img = rgb_img
    elif pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    width, height = pil_img.size
    longest_edge = max(width, height)

    if longest_edge > max_dimension:
        scale = max_dimension / float(longest_edge)
        new_width = int(width * scale)
        new_height = int(height * scale)
        pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height} (Max dim: {max_dimension})")

    fmt_upper = "JPEG" if image_format.lower() in ("jpg", "jpeg") else image_format.upper()
    save_kwargs = {"optimize": True}
    if fmt_upper in ("JPEG", "WEBP"):
        save_kwargs["quality"] = quality

    pil_img.save(output_path, format=fmt_upper, **save_kwargs)
    return output_path


def split_pdf(
    pdf_path: str,
    output_dir: str,
    dpi: int = 150,
    image_format: str = "jpg",
    quality: int = 85,
    max_dimension: int = 1800
) -> List[str]:
    """Splits a multi-page PDF into optimized images (one per page)."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Input PDF file not found at: {pdf_path}")

    logger.info(f"Splitting PDF: '{pdf_path}' to output directory: '{output_dir}' (Format: {image_format.upper()}, DPI: {dpi})")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    ext = image_format.lower().replace(".", "")
    image_paths = []

    expected_page_count = PDFService.get_page_count(pdf_path)
    for page_num in range(expected_page_count):
        pil_img = PDFService.render_page_to_pil(pdf_path, page_index=page_num, dpi=dpi)

        output_filename = f"temp_{base_name}_page_{page_num + 1}.{ext}"
        output_path = os.path.join(output_dir, output_filename).replace("\\", "/")

        resize_and_save_image(
            pil_img=pil_img,
            output_path=output_path,
            image_format=ext,
            quality=quality,
            max_dimension=max_dimension
        )
        image_paths.append(output_path)

    if len(image_paths) != expected_page_count:
        err = f"PDF split validation error for '{pdf_path}': Expected {expected_page_count} pages, but generated {len(image_paths)} images."
        logger.error(f"[VALIDATION FAILED] {err}")
        raise ValueError(err)

    for img_p in image_paths:
        if not os.path.exists(img_p) or os.path.getsize(img_p) == 0:
            err = f"PDF split validation error: Generated image missing or 0-bytes at '{img_p}'."
            logger.error(f"[VALIDATION FAILED] {err}")
            raise ValueError(err)

    logger.info(f"[PASS] PDF split validated: Exactly {len(image_paths)}/{expected_page_count} page(s) generated as .{ext}.")
    return image_paths


def process_raw_image(
    image_path: str,
    output_dir: str,
    output_filename: Optional[str] = None,
    image_format: str = "jpg",
    quality: int = 85,
    max_dimension: int = 1800
) -> str:
    """Processes a standalone raw image file and saves it to output_dir."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image file not found at: {image_path}")

    os.makedirs(output_dir, exist_ok=True)
    ext = image_format.lower().replace(".", "")

    if output_filename is None:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        output_filename = f"temp_{base_name}_page_1.{ext}"
    elif not output_filename.lower().endswith(f".{ext}"):
        output_filename = f"{os.path.splitext(output_filename)[0]}.{ext}"

    output_path = os.path.join(output_dir, output_filename).replace("\\", "/")

    with Image.open(image_path) as pil_img:
        resize_and_save_image(
            pil_img=pil_img,
            output_path=output_path,
            image_format=ext,
            quality=quality,
            max_dimension=max_dimension
        )

    logger.info(f"Processed raw image '{os.path.basename(image_path)}' -> '{output_path}'")
    return output_path


def extract_pdf_page_to_pdf(pdf_path: str, page_num: int, output_path: str) -> None:
    """Extracts a single page from a PDF and saves it as a new single-page PDF file."""
    PDFService.extract_page_to_pdf(pdf_path=pdf_path, page_num=page_num, output_path=output_path)


class ImageService:
    """Standardized Image Processing & Page Splitting Service Adapter."""
    sanitize_filename_part = staticmethod(sanitize_filename_part)
    format_page_filename = staticmethod(format_page_filename)
    resize_and_save_image = staticmethod(resize_and_save_image)
    split_pdf = staticmethod(split_pdf)
    process_raw_image = staticmethod(process_raw_image)
    extract_pdf_page_to_pdf = staticmethod(extract_pdf_page_to_pdf)


async def async_split_pdf(
    pdf_path: str,
    output_dir: str,
    dpi: int = 150,
    image_format: str = "jpg",
    quality: int = 85,
    max_dimension: int = 1800
) -> List[str]:
    """Asynchronously splits a multi-page PDF into optimized images."""
    return await asyncio.to_thread(
        split_pdf,
        pdf_path=pdf_path,
        output_dir=output_dir,
        dpi=dpi,
        image_format=image_format,
        quality=quality,
        max_dimension=max_dimension
    )


async def async_process_raw_image(
    image_path: str,
    output_dir: str,
    output_filename: Optional[str] = None,
    image_format: str = "jpg",
    quality: int = 85,
    max_dimension: int = 1800
) -> str:
    """Asynchronously processes a raw image."""
    return await asyncio.to_thread(
        process_raw_image,
        image_path=image_path,
        output_dir=output_dir,
        output_filename=output_filename,
        image_format=image_format,
        quality=quality,
        max_dimension=max_dimension
    )
