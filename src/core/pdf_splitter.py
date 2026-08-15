import os
import fitz  # PyMuPDF
from loguru import logger

def split_pdf(pdf_path: str, output_dir: str, dpi: int = 150) -> list[str]:
    """
    Splits a multi-page PDF into high-quality PNG images (one per page).
    
    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where the output image files will be saved.
        dpi: Resolution of the output images. Higher means better OCR but larger files.
        
    Returns:
        A list of paths to the saved PNG image files.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Input PDF file not found at: {pdf_path}")
        
    logger.info(f"Splitting PDF: '{pdf_path}' to output directory: '{output_dir}'")
    os.makedirs(output_dir, exist_ok=True)
    
    # Get base filename of the PDF without extension
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    image_paths = []

    
    # Open the PDF document
    doc = fitz.open(pdf_path)
    
    try:
        # Iterate through each page of the PDF
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Render the page to a pixmap
            pix = page.get_pixmap(dpi=dpi)
            
            # Define output path for the page image
            output_filename = f"temp_{base_name}_page_{page_num + 1}.png"
            output_path = os.path.join(output_dir, output_filename)
            
            # Normalize path delimiters for cross-platform consistency
            output_path = os.path.abspath(output_path).replace("\\", "/")
            
            # Save the rendering as a PNG image
            pix.save(output_path)
            image_paths.append(output_path)
            
    finally:
        doc.close()
        
    logger.info(f"PDF split completed: {len(image_paths)} page(s) generated.")
    return image_paths

def extract_pdf_page_to_pdf(pdf_path: str, page_num: int, output_path: str) -> None:
    """
    Extracts a single page (1-indexed) from a PDF and saves it as a new single-page PDF file.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Input PDF file not found at: {pdf_path}")
        
    doc = fitz.open(pdf_path)
    try:
        # Convert 1-indexed page_num to 0-indexed for PyMuPDF
        idx = page_num - 1
        if idx < 0 or idx >= len(doc):
            raise IndexError(f"Page number {page_num} is out of range for PDF with {len(doc)} pages.")
            
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=idx, to_page=idx)
        new_doc.save(output_path)
        new_doc.close()
    finally:
        doc.close()


