import os
import shutil
import uuid
from src.infrastructure.common.logger import logger

from src.infrastructure.common.config_loader import (
    load_system_settings,
    resolve_doc_type,
    resolve_company_code,
    get_company_storage_dir,
    get_company_pipeline_folder,
    get_image_processing_config,
    get_supported_extensions,
    get_ai_provider_config,
)
from src.infrastructure.persistence import (
    calculate_file_hash,
    check_duplicate_document,
    create_batch,
    create_page,
    get_company_by_code,
)
from src.infrastructure.common.constants import (
    DocumentStatusCode,
    MerchantStatusCode,
    PipelineStageFolder,
    EntityIdPrefix,
    generate_entity_id,
)
from src.infrastructure.pdf.image_service import split_pdf, process_raw_image, format_page_filename
from src.application.usecases.classifier import classify_document
from src.infrastructure.storage.storage_manager import storage_manager


def _register_preprocessed_page(
    batch_id: str,
    page_number: int,
    image_path: str,
    created_pages: list,
    chunk_index: int = 1,
) -> str:
    """Helper to record preprocessed page record in database and tracking list."""
    page_id = generate_entity_id(EntityIdPrefix.PAGE)
    create_page(
        page_id=page_id,
        batch_id=batch_id,
        page_number=page_number,
        image_path=image_path,
        status_code=DocumentStatusCode.PREPROCESSED,
        chunk_index=chunk_index,
    )
    created_pages.append(image_path)
    return page_id


def split_and_match(
    doc_type: str = None,
    input_file: str = None,
    input_pdf: str = None,
    company_code: str = None
) -> list[dict]:
    """
    Stage 2: Split multi-page PDFs or process raw images into optimized page images and match merchant source.
    """
    logger.info("Starting Stage 2 (Split & Match): Processing Files & Matching Sources")

    if input_file is None and input_pdf is not None:
        input_file = input_pdf

    settings = load_system_settings()
    comp_code = resolve_company_code(company_code)
    
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    target_doc_type = resolve_doc_type(doc_type or domain)

    img_cfg = get_image_processing_config(settings)
    ai_cfg = get_ai_provider_config(settings)
    max_images_per_chunk = ai_cfg.get("max_images_per_request", 50)
    supported_exts = get_supported_extensions(settings)
    processing_fmt = img_cfg["processing_format"]
    jpeg_quality = img_cfg["jpeg_quality"]
    max_dim = img_cfg["max_dimension"]
    dpi = img_cfg["dpi"]
    filename_pattern = img_cfg.get("split_filename_pattern") or img_cfg.get(
        "filename_pattern", "{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}"
    )

    # 1. Resolve Company-Centric Storage Paths via StoragePathManager
    drop_zone_comp_dt = storage_manager.get_drop_zone_dir(comp_code, target_doc_type)
    drop_zone_comp_root = storage_manager.get_drop_zone_dir(comp_code)
    raw_data_dir = storage_manager.get_raw_data_dir(comp_code, target_doc_type)
    split_dir = storage_manager.get_preprocess_dir(comp_code, target_doc_type)

    # Identify files to process (Scan company drop zone and approved subfolders)
    files_to_process = []
    if input_file:
        if os.path.exists(input_file):
            files_to_process.append(input_file)
        else:
            logger.error(f"Input file not found: {input_file}")
            return []
    else:
        scan_dirs = [drop_zone_comp_dt, drop_zone_comp_root]

        # Only scan approved subfolders in raw_data (exclude PENDING and IGNORED)
        if os.path.exists(raw_data_dir):
            for entry in os.listdir(raw_data_dir):
                entry_path = os.path.join(raw_data_dir, entry).replace("\\", "/")
                if os.path.isdir(entry_path) and entry not in [MerchantStatusCode.PENDING, MerchantStatusCode.IGNORED]:
                    scan_dirs.append(entry_path)

        for s_dir in scan_dirs:
            if os.path.exists(s_dir):
                for root_dir, _, files in os.walk(s_dir):
                    norm_root = root_dir.replace("\\", "/")
                    if f"/{MerchantStatusCode.PENDING}" in norm_root or f"/{MerchantStatusCode.IGNORED}" in norm_root:
                        continue
                    for file in files:
                        file_ext = os.path.splitext(file)[1].lower()
                        if file_ext in supported_exts and not file.startswith("."):
                            full_p = os.path.join(root_dir, file).replace("\\", "/")
                            if full_p not in files_to_process:
                                files_to_process.append(full_p)

    if not files_to_process:
        logger.info(f"No valid document files {supported_exts} found for company '{comp_code}'.")
        return []

    logger.info(f"Found {len(files_to_process)} document file(s) to process for company '{comp_code}'.")
    results = []

    for file_path in files_to_process:
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        is_pdf = file_ext == ".pdf"
        batch_id = generate_entity_id(EntityIdPrefix.BATCH)

        logger.info(f"\n--- Processing: {filename} ({'PDF Document' if is_pdf else 'Direct Image'}) [Batch: {batch_id}] [Company: {comp_code}] ---")

        # 1. Check Duplicate
        file_hash = calculate_file_hash(file_path)
        is_duplicate, dup_meta = check_duplicate_document(file_hash, company_id=company_id)
        if is_duplicate:
            logger.warning(
                f"Duplicate document detected! Already processed in Batch '{dup_meta['batch_id']}' (Status: '{dup_meta['status']}')"
            )
            continue

        # 2. Fast AI Classifier & Gatekeeper Routing
        from src.infrastructure.common.constants import DefaultIdentifier, PipelineAction, PipelineStageFolder
        dest_file_path = file_path
        dest_folder = os.path.dirname(file_path)
        matched_source = DefaultIdentifier.NO_TAX_LABEL
        pipeline_action = PipelineAction.PROCEED

        try:
            cls_res = classify_document(
                file_path,
                doc_type=target_doc_type,
                company_code=comp_code,
                company_id=company_id,
                batch_id=batch_id,
                configs_dir="configs",
            )
            target_folder = cls_res.get("target_folder", raw_data_dir)
            pipeline_action = cls_res.get("pipeline_action", PipelineAction.PROCEED)

            if PipelineStageFolder.DROP_ZONE in file_path or "01_raw_inbox" in file_path:
                dest_file_path = os.path.join(target_folder, filename).replace("\\", "/")
                dest_folder = target_folder
                if os.path.abspath(file_path) != os.path.abspath(dest_file_path):
                    os.makedirs(target_folder, exist_ok=True)
                    shutil.move(file_path, dest_file_path)

            matched_source = cls_res.get("folder_identifier", DefaultIdentifier.NO_TAX_LABEL)

            if pipeline_action == PipelineAction.HOLD:
                logger.warning(f"File '{filename}' held in '{target_folder}' awaiting merchant approval.")
                continue
            elif pipeline_action == PipelineAction.IGNORE:
                logger.info(f"File '{filename}' belongs to IGNORED merchant. Moving to '{target_folder}' and skipping.")
                continue
        except Exception as cl_err:
            logger.warning(f"Classifier note: {cl_err}")
            dest_file_path = file_path
            dest_folder = os.path.dirname(file_path)

        # 3. Process Pages (PDF Splitting or Direct Image Processing)
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
                company_id=company_id,
                original_pdf_name=filename,
                total_pages=total_pages,
                storage_path=dest_folder,
                file_hash=file_hash,
            )

            for idx, temp_img_path in enumerate(page_images, start=1):
                page_filename = format_page_filename(
                    pattern=filename_pattern,
                    doc_type=target_doc_type,
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

                chunk_idx = ((idx - 1) // max_images_per_chunk) + 1
                _register_preprocessed_page(
                    batch_id=batch_id,
                    page_number=idx,
                    image_path=final_img_path,
                    created_pages=created_pages,
                    chunk_index=chunk_idx,
                )
        else:
            # Standalone raw image
            total_pages = 1
            page_filename = format_page_filename(
                pattern=filename_pattern,
                doc_type=target_doc_type,
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
                company_id=company_id,
                original_pdf_name=filename,
                total_pages=total_pages,
                storage_path=dest_folder,
                file_hash=file_hash,
            )

            _register_preprocessed_page(
                batch_id=batch_id,
                page_number=1,
                image_path=final_img_path,
                created_pages=created_pages,
                chunk_index=1,
            )

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


def release_pending_merchant_files(
    doc_type: str = None,
    tax_id: str = None,
    short_name: str = None,
    company_code: str = None
) -> list[dict]:
    """
    Releases all held files for an approved merchant from 02_raw_data/PENDING/{tax_id}_{short_name}
    to 02_raw_data/{tax_id}_{short_name} and runs split_and_match on them.
    """
    target_doc_type = doc_type or get_default_doc_type()
    comp_code = company_code or get_default_company_code()
    folder_name = f"{tax_id}_{short_name}"
    pending_folder = storage_manager.get_raw_data_dir(comp_code, target_doc_type, status=MerchantStatusCode.PENDING, merchant_folder=folder_name)
    approved_folder = storage_manager.get_raw_data_dir(comp_code, target_doc_type, merchant_folder=folder_name)
    
    if not os.path.exists(pending_folder) or not os.listdir(pending_folder):
        logger.info(f"No pending folder or files found at '{pending_folder}'.")
        return []
        
    os.makedirs(approved_folder, exist_ok=True)
    moved_files = []
    
    for f in os.listdir(pending_folder):
        if not f.startswith("."):
            src_f = os.path.join(pending_folder, f).replace("\\", "/")
            dst_f = os.path.join(approved_folder, f).replace("\\", "/")
            shutil.move(src_f, dst_f)
            moved_files.append(dst_f)
            
    logger.info(f"Moved {len(moved_files)} pending files for merchant '{folder_name}' (Company: {comp_code}) to approved raw data.")
    
    # Trigger split on moved files
    results = []
    for mf in moved_files:
        res = split_and_match(doc_type=target_doc_type, input_file=mf, company_code=comp_code)
        results.extend(res)
        
    return results
