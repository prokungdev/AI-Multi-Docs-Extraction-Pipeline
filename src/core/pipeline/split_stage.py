import os
import shutil
import uuid
from loguru import logger

from src.core.config_loader import (
    load_system_settings,
    get_default_domain,
    is_source_active,
    get_image_processing_config,
    get_supported_extensions,
)
from src.core.db import (
    calculate_file_hash,
    check_duplicate_document,
    create_batch,
    create_page,
)
from src.core.models import DocumentStatus
from src.core.pdf_splitter import split_pdf, process_raw_image, format_page_filename
from src.core.source_matcher import match_source


def split_and_match(domain: str = None, input_file: str = None, input_pdf: str = None) -> list[dict]:
    """
    Stage 2: Split multi-page PDFs or process raw images into optimized page images and match merchant source.
    """
    logger.info("Starting Stage 2 (Split & Match): Processing Files & Matching Sources")

    if input_file is None and input_pdf is not None:
        input_file = input_pdf

    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    if domain is None:
        domain = get_default_domain()

    img_cfg = get_image_processing_config(settings)
    supported_exts = get_supported_extensions(settings)
    processing_fmt = img_cfg["processing_format"]
    jpeg_quality = img_cfg["jpeg_quality"]
    max_dim = img_cfg["max_dimension"]
    dpi = img_cfg["dpi"]
    filename_pattern = img_cfg.get("split_filename_pattern") or img_cfg.get(
        "filename_pattern", "{domain}_{source}_{original_filename}_{batch_id}_p{page_no}"
    )

    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    inbox_dir = os.path.join(domain_storage, "01_raw_inbox").replace("\\", "/")
    split_dir = os.path.join(domain_storage, "02_split_pages").replace("\\", "/")

    os.makedirs(inbox_dir, exist_ok=True)
    os.makedirs(split_dir, exist_ok=True)

    # Identify files to process
    files_to_process = []
    if input_file:
        if os.path.exists(input_file):
            files_to_process.append(input_file)
        else:
            logger.error(f"Input file not found: {input_file}")
            return []
    else:
        for root_dir, _, files in os.walk(inbox_dir):
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in supported_exts and not file.startswith("."):
                    files_to_process.append(os.path.join(root_dir, file).replace("\\", "/"))

    if not files_to_process:
        logger.info(f"No valid document files {supported_exts} found in raw inbox to process.")
        return []

    logger.info(f"Found {len(files_to_process)} document file(s) to process.")
    results = []

    for file_path in files_to_process:
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        is_pdf = file_ext == ".pdf"

        logger.info(f"\n--- Processing: {filename} ({'PDF Document' if is_pdf else 'Direct Image'}) ---")

        # 1. Check Duplicate
        file_hash = calculate_file_hash(file_path)
        is_duplicate, dup_meta = check_duplicate_document(file_hash)
        if is_duplicate:
            logger.warning(
                f"Duplicate document detected! Already processed in Batch '{dup_meta['batch_id']}' (Status: '{dup_meta['status']}')"
            )
            continue

        # 2. Match Source
        matched_source = match_source(file_path, domain=domain, settings=settings)
        logger.info(f"Matched source: '{matched_source}'")

        # Check source active state
        if not is_source_active(domain, matched_source):
            logger.warning(f"Source '{matched_source}' is currently DEACTIVATED in DB. Routing to '_uncategorized'.")
            matched_source = "_uncategorized"

        # 3. Resolve destination folder and move original file
        dest_folder = os.path.join(inbox_dir, matched_source).replace("\\", "/")
        os.makedirs(dest_folder, exist_ok=True)
        dest_file_path = os.path.join(dest_folder, filename).replace("\\", "/")

        if os.path.abspath(file_path) != os.path.abspath(dest_file_path):
            shutil.move(file_path, dest_file_path)

        # 4. Process Pages (PDF Splitting or Direct Image Processing)
        batch_id = str(uuid.uuid4())
        created_pages = []

        if is_pdf:
            try:
                page_images = split_pdf(
                    pdf_path=dest_file_path,
                    output_dir=split_dir,
                    dpi=dpi,
                    image_format=processing_fmt,
                    quality=jpeg_quality,
                    max_dimension=max_dim,
                )
                total_pages = len(page_images)
            except Exception as e:
                logger.error(f"Failed to split PDF '{filename}': {e}")
                continue

            create_batch(
                batch_id=batch_id,
                original_pdf_name=filename,
                total_pages=total_pages,
                storage_path=dest_folder,
                file_hash=file_hash,
            )

            for idx, temp_img_path in enumerate(page_images, start=1):
                page_id = str(uuid.uuid4())
                page_filename = format_page_filename(
                    pattern=filename_pattern,
                    domain=domain,
                    source=matched_source,
                    original_filename=filename,
                    page_no=idx,
                    batch_id=batch_id,
                    image_format=processing_fmt,
                )
                final_img_path = os.path.join(split_dir, page_filename).replace("\\", "/")

                if os.path.exists(temp_img_path):
                    if os.path.exists(final_img_path):
                        os.remove(final_img_path)
                    os.rename(temp_img_path, final_img_path)

                create_page(
                    page_id=page_id,
                    batch_id=batch_id,
                    page_number=idx,
                    image_path=final_img_path,
                    status_code=DocumentStatus.PREPROCESSED.value,
                )
                created_pages.append(final_img_path)
        else:
            # Standalone raw image
            total_pages = 1
            page_id = str(uuid.uuid4())
            page_filename = format_page_filename(
                pattern=filename_pattern,
                domain=domain,
                source=matched_source,
                original_filename=filename,
                page_no=1,
                batch_id=batch_id,
                image_format=processing_fmt,
            )
            final_img_path = os.path.join(split_dir, page_filename).replace("\\", "/")

            try:
                process_raw_image(
                    image_path=dest_file_path,
                    output_dir=split_dir,
                    output_filename=page_filename,
                    image_format=processing_fmt,
                    quality=jpeg_quality,
                    max_dimension=max_dim,
                )
            except Exception as e:
                logger.error(f"Failed to process raw image '{filename}': {e}")
                continue

            create_batch(
                batch_id=batch_id,
                original_pdf_name=filename,
                total_pages=total_pages,
                storage_path=dest_folder,
                file_hash=file_hash,
            )

            create_page(
                page_id=page_id,
                batch_id=batch_id,
                page_number=1,
                image_path=final_img_path,
                status_code=DocumentStatus.PREPROCESSED.value,
            )
            created_pages.append(final_img_path)

        logger.info(f"Registered Batch '{batch_id}' with {total_pages} page(s) as PREPROCESSED.")
        results.append(
            {
                "batch_id": batch_id,
                "filename": filename,
                "matched_source": matched_source,
                "total_pages": total_pages,
                "page_images": created_pages,
            }
        )

    return results
