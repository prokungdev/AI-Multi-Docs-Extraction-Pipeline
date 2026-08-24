import os
import json
import asyncio
from dotenv import load_dotenv
from src.infrastructure.common.logger import logger

from src.infrastructure.common.config_loader import (
    load_system_settings,
    get_default_doc_type,
    get_default_company_code,
    get_company_pipeline_folder,
    get_ai_provider_config,
)
from src.infrastructure.persistence import (
    get_unextracted_batches,
    get_batch_pages,
    update_page_status,
    get_company_by_code,
    get_unextracted_chunks_for_batch,
    get_pages_by_chunk,
    update_chunk_pages_status,
)
from src.infrastructure.common.constants import DocumentStatusCode
from src.application.usecases.extractor import extract_document_data, async_extract_document_data
from src.application.dtos.document_dto import DocumentStatus
from src.application.pipeline.pipeline_helpers import merge_chunk_payloads
from src.infrastructure.common.utils import chunk_list


def extract_documents(
    doc_type: str = None,
    source: str = None,
    company_code: str = None
) -> dict:
    """
    Stage 3: AI Document Extraction with Smart Chunk-Level Checkpointing.
    Extracts structured JSON data per chunk, tracks chunk status in DB, and supports resuming.
    """
    logger.info("Starting Stage 3 (Extract): Extracting Structured Data via Multimodal AI (Smart Checkpointing)")

    load_dotenv()
    settings = load_system_settings()
    comp_code = company_code or get_default_company_code()
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    ai_cfg = get_ai_provider_config(settings)
    max_images = ai_cfg.get("max_images_per_request", 50)
    target_doc_type = doc_type or get_default_doc_type()

    from src.infrastructure.storage.storage_manager import storage_manager
    queue_dir = storage_manager.get_processing_dir(comp_code, target_doc_type)

    try:
        batches = get_unextracted_batches(
            [DocumentStatus.PREPROCESSED.value, DocumentStatus.PENDING.value, DocumentStatus.FAILED.value],
            company_id=company_id
        )

        if not batches:
            logger.info(f"No unextracted batches found to process for company '{comp_code}'.")
            return {"success": True, "batches_processed": 0, "documents_extracted": 0}

        logger.info(f"Found {len(batches)} batch(es) to extract with AI for company '{comp_code}'...")

        success_batches = 0
        total_docs = 0

        for b in batches:
            batch_id = b["batch_id"]
            pdf_name = b["original_pdf_name"]
            storage_path = b["storage_path"]

            # Resolve source
            folder_name = os.path.basename(storage_path)
            from src.infrastructure.common.constants import DefaultIdentifier
            batch_source = DefaultIdentifier.NO_TAX_LABEL if folder_name in (DefaultIdentifier.NO_TAX_LABEL, DefaultIdentifier.NO_TAX_ID, "_uncategorized") else folder_name
            if source and source != batch_source:
                continue

            pages = get_batch_pages(batch_id)
            if not pages:
                continue

            unextracted_chunks = set(get_unextracted_chunks_for_batch(batch_id))
            all_chunk_indexes = sorted(list(set(p.get("chunk_index", 1) for p in pages)))

            logger.info(
                f"\n--- Extracting Batch: {batch_id} ({pdf_name}) | Total Chunks: {len(all_chunk_indexes)} | Pending Chunks: {len(unextracted_chunks)} [Company: {comp_code}] ---"
            )

            chunks_cache_dir = os.path.join(queue_dir, "_chunks", batch_id).replace("\\", "/")
            os.makedirs(chunks_cache_dir, exist_ok=True)

            chunk_payloads = []
            batch_failed = False

            for chunk_idx in all_chunk_indexes:
                cached_chunk_file = os.path.join(chunks_cache_dir, f"chunk_{chunk_idx}.json").replace("\\", "/")

                # If chunk already extracted and cached, load from cache (Resume bypass)
                if chunk_idx not in unextracted_chunks and os.path.exists(cached_chunk_file):
                    try:
                        with open(cached_chunk_file, "r", encoding="utf-8") as f:
                            chunk_payloads.append(json.load(f))
                        logger.info(f"Loaded cached result for Batch '{batch_id}' Chunk #{chunk_idx}.")
                        continue
                    except Exception:
                        pass  # If cache file corrupt, fall back to re-extracting

                # Fetch pages for this chunk
                chunk_page_records = get_pages_by_chunk(batch_id, chunk_idx)
                chunk_images = [p["image_path"] for p in chunk_page_records if os.path.exists(p["image_path"])]

                if not chunk_images:
                    logger.warning(f"No valid image files found on disk for Batch '{batch_id}' Chunk #{chunk_idx}")
                    continue

                try:
                    logger.info(f"Sending AI extraction request for Batch '{batch_id}' Chunk #{chunk_idx} ({len(chunk_images)} pages)...")
                    payload = extract_document_data(
                        image_paths=chunk_images,
                        source=batch_source,
                        doc_type=target_doc_type,
                        batch_id=batch_id,
                        chunk_index=chunk_idx,
                        company_id=company_id,
                    )

                    # Save chunk checkpoint
                    with open(cached_chunk_file, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)

                    update_chunk_pages_status(batch_id, chunk_idx, DocumentStatusCode.EXTRACTED)
                    chunk_payloads.append(payload)
                    logger.info(f"Chunk #{chunk_idx} of Batch '{batch_id}' extracted and checkpointed successfully.")

                except Exception as ex_err:
                    logger.error(f"AI extraction failed for Batch '{batch_id}' Chunk #{chunk_idx}: {ex_err}")
                    update_chunk_pages_status(batch_id, chunk_idx, DocumentStatusCode.FAILED, error_reason=str(ex_err))
                    batch_failed = True
                    break

            if batch_failed or len(chunk_payloads) < len(all_chunk_indexes):
                logger.warning(f"Batch '{batch_id}' partially completed or failed. Progress saved for retry/resume.")
                continue

            # Merge all chunks into final document payload
            merged_payload = merge_chunk_payloads(chunk_payloads)

            # Save final JSON in company 04_processing
            source_queue_dir = os.path.join(queue_dir, batch_source).replace("\\", "/")
            os.makedirs(source_queue_dir, exist_ok=True)

            for p in pages:
                image_basename = os.path.splitext(os.path.basename(p["image_path"]))[0]
                json_path = os.path.join(source_queue_dir, f"{image_basename}.json").replace("\\", "/")
                with open(json_path, "w", encoding="utf-8") as qf:
                    json.dump(merged_payload, qf, ensure_ascii=False, indent=2)

            # Clean up chunk checkpoint directory after successful merge
            try:
                import shutil
                if os.path.exists(chunks_cache_dir):
                    shutil.rmtree(chunks_cache_dir)
            except Exception:
                pass

            logger.info(f"All {len(all_chunk_indexes)} chunks completed & merged for Batch '{batch_id}'. Status: EXTRACTED.")
            success_batches += 1
            total_docs += 1

        return {"success": True, "batches_processed": success_batches, "documents_extracted": total_docs}

    except Exception as e:
        logger.error(f"Error during AI extraction stage: {e}")
        return {"success": False, "error": str(e)}


async def async_extract_documents(
    doc_type: str = None,
    source: str = None,
    company_code: str = None
) -> dict:
    """
    Stage 3 (Async): Concurrent AI Document Extraction with Smart Chunk Checkpointing.
    """
    logger.info("Starting Stage 3 (Async Extract): Concurrent AI Extraction (Smart Checkpointing)")

    load_dotenv()
    settings = load_system_settings()
    comp_code = company_code or get_default_company_code()
    comp_info = get_company_by_code(comp_code)
    company_id = comp_info["company_id"] if comp_info else None

    ai_cfg = get_ai_provider_config(settings)
    max_images = ai_cfg.get("max_images_per_request", 50)
    max_concurrent = ai_cfg.get("max_concurrent_requests", 5)

    target_doc_type = doc_type or get_default_doc_type()

    from src.infrastructure.storage.storage_manager import storage_manager
    queue_dir = storage_manager.get_processing_dir(comp_code, target_doc_type)

    try:
        batches = get_unextracted_batches(
            [DocumentStatus.PREPROCESSED.value, DocumentStatus.PENDING.value, DocumentStatus.FAILED.value],
            company_id=company_id
        )

        if not batches:
            logger.info("No unextracted batches found to process.")
            return {"success": True, "batches_processed": 0, "documents_extracted": 0}

        logger.info(f"Found {len(batches)} batch(es) to extract concurrently (Concurrency Limit: {max_concurrent})...")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_single_batch(b: dict) -> bool:
            batch_id = b["batch_id"]
            pdf_name = b["original_pdf_name"]
            storage_path = b["storage_path"]

            folder_name = os.path.basename(storage_path)
            from src.infrastructure.common.constants import DefaultIdentifier
            batch_source = DefaultIdentifier.NO_TAX_LABEL if folder_name in (DefaultIdentifier.NO_TAX_LABEL, DefaultIdentifier.NO_TAX_ID, "_uncategorized") else folder_name
            if source and source != batch_source:
                return False

            pages = get_batch_pages(batch_id)
            if not pages:
                return False

            unextracted_chunks = set(get_unextracted_chunks_for_batch(batch_id))
            all_chunk_indexes = sorted(list(set(p.get("chunk_index", 1) for p in pages)))

            chunks_cache_dir = os.path.join(queue_dir, "_chunks", batch_id).replace("\\", "/")
            os.makedirs(chunks_cache_dir, exist_ok=True)

            chunk_payloads = []

            for chunk_idx in all_chunk_indexes:
                cached_chunk_file = os.path.join(chunks_cache_dir, f"chunk_{chunk_idx}.json").replace("\\", "/")

                if chunk_idx not in unextracted_chunks and os.path.exists(cached_chunk_file):
                    try:
                        with open(cached_chunk_file, "r", encoding="utf-8") as f:
                            chunk_payloads.append(json.load(f))
                        continue
                    except Exception:
                        pass

                chunk_page_records = get_pages_by_chunk(batch_id, chunk_idx)
                chunk_images = [p["image_path"] for p in chunk_page_records if os.path.exists(p["image_path"])]

                if not chunk_images:
                    continue

                try:
                    payload = await async_extract_document_data(
                        image_paths=chunk_images,
                        source=batch_source,
                        doc_type=target_doc_type,
                        batch_id=batch_id,
                        chunk_index=chunk_idx,
                        company_id=company_id,
                        semaphore=semaphore,
                    )

                    with open(cached_chunk_file, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)

                    update_chunk_pages_status(batch_id, chunk_idx, DocumentStatusCode.EXTRACTED)
                    chunk_payloads.append(payload)

                except Exception as ex_err:
                    logger.error(f"Async AI extraction failed for batch '{batch_id}' chunk {chunk_idx}: {ex_err}")
                    update_chunk_pages_status(batch_id, chunk_idx, DocumentStatusCode.FAILED, error_reason=str(ex_err))
                    return False

            if len(chunk_payloads) < len(all_chunk_indexes):
                return False

            merged_payload = merge_chunk_payloads(chunk_payloads)
            source_queue_dir = os.path.join(queue_dir, batch_source).replace("\\", "/")
            os.makedirs(source_queue_dir, exist_ok=True)

            for p in pages:
                image_basename = os.path.splitext(os.path.basename(p["image_path"]))[0]
                json_path = os.path.join(source_queue_dir, f"{image_basename}.json").replace("\\", "/")
                with open(json_path, "w", encoding="utf-8") as qf:
                    json.dump(merged_payload, qf, ensure_ascii=False, indent=2)

            try:
                import shutil
                if os.path.exists(chunks_cache_dir):
                    shutil.rmtree(chunks_cache_dir)
            except Exception:
                pass

            logger.info(f"Async AI extraction completed for batch '{batch_id}'. Status set to EXTRACTED.")
            return True

        results = await asyncio.gather(*[process_single_batch(b) for b in batches])
        success_batches = sum(1 for r in results if r)

        return {"success": True, "batches_processed": success_batches, "documents_extracted": success_batches}

    except Exception as e:
        logger.error(f"Error during async AI extraction stage: {e}")
        return {"success": False, "error": str(e)}

