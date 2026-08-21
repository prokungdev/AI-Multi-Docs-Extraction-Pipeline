import os
import json
import asyncio
from dotenv import load_dotenv
from loguru import logger

from src.core.config_loader import (
    load_system_settings,
    get_default_domain,
    get_ai_provider_config,
)
from src.core.db import (
    get_unextracted_batches,
    get_batch_pages,
    update_page_status,
)
from src.core.extractor import extract_document_data, async_extract_document_data
from src.core.models import DocumentStatus
from src.core.pipeline.helpers import merge_chunk_payloads
from src.core.utils import chunk_list


def extract_documents(domain: str = None, source: str = None) -> dict:
    """
    Stage 3: AI Document Extraction.
    Extracts structured JSON data from preprocessed images and saves to 03_processing_queue.
    """
    logger.info("Starting Stage 3 (Extract): AI Document Extraction to JSON Queue")

    load_dotenv()
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    ai_cfg = get_ai_provider_config(settings)
    max_images = ai_cfg.get("max_images_per_request", 50)
    if domain is None:
        domain = get_default_domain()

    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")
    os.makedirs(queue_dir, exist_ok=True)

    try:
        batches = get_unextracted_batches([DocumentStatus.PREPROCESSED.value, DocumentStatus.PENDING.value])

        if not batches:
            logger.info("No unextracted batches found to process.")
            return {"success": True, "batches_processed": 0, "documents_extracted": 0}

        logger.info(f"Found {len(batches)} batch(es) to extract with AI...")

        success_batches = 0
        total_docs = 0

        for b in batches:
            batch_id = b["batch_id"]
            pdf_name = b["original_pdf_name"]
            storage_path = b["storage_path"]

            # Resolve source
            folder_name = os.path.basename(storage_path)
            batch_source = "_default" if folder_name == "_uncategorized" else folder_name
            if source and source != batch_source:
                continue

            pages = get_batch_pages(batch_id)
            if not pages:
                continue

            image_paths = [p["image_path"] for p in pages if os.path.exists(p["image_path"])]
            if not image_paths:
                logger.warning(f"No valid image files found on disk for batch '{batch_id}'")
                continue

            logger.info(f"\n--- Extracting Batch: {batch_id} ({pdf_name}) | Source: '{batch_source}' ---")

            # Chunk pages if exceeding max_images
            chunks = list(chunk_list(image_paths, max_images))
            chunk_payloads = []
            failed = False

            for chunk_idx, chunk in enumerate(chunks, start=1):
                try:
                    payload = extract_document_data(
                        image_paths=chunk,
                        source=batch_source,
                        domain=domain,
                        batch_id=batch_id,
                        chunk_index=chunk_idx,
                    )
                    chunk_payloads.append(payload)
                except Exception as ex_err:
                    logger.error(f"AI extraction failed for batch '{batch_id}' chunk {chunk_idx}: {ex_err}")
                    failed = True
                    break

            if failed or not chunk_payloads:
                continue

            # Merge chunks
            merged_payload = merge_chunk_payloads(chunk_payloads)

            # Save raw extracted JSON in 03_processing_queue
            source_queue_dir = os.path.join(queue_dir, batch_source).replace("\\", "/")
            os.makedirs(source_queue_dir, exist_ok=True)

            for p in pages:
                image_basename = os.path.splitext(os.path.basename(p["image_path"]))[0]
                json_path = os.path.join(source_queue_dir, f"{image_basename}.json").replace("\\", "/")
                with open(json_path, "w", encoding="utf-8") as qf:
                    json.dump(merged_payload, qf, ensure_ascii=False, indent=2)
                update_page_status(p["page_id"], DocumentStatus.EXTRACTED.value)

            logger.info(f"AI extraction completed for batch '{batch_id}'. Status set to EXTRACTED.")
            success_batches += 1
            total_docs += 1

        return {"success": True, "batches_processed": success_batches, "documents_extracted": total_docs}

    except Exception as e:
        logger.error(f"Error during AI extraction stage: {e}")
        return {"success": False, "error": str(e)}


async def async_extract_documents(domain: str = None, source: str = None) -> dict:
    """
    Stage 3 (Async): Concurrent AI Document Extraction.
    Uses asyncio.gather and Semaphore to extract structured JSON data concurrently.
    """
    logger.info("Starting Stage 3 (Async Extract): Concurrent AI Extraction")

    load_dotenv()
    settings = load_system_settings()
    storage_root = settings.get("storage_root", "pipeline_storage")
    ai_cfg = get_ai_provider_config(settings)
    max_images = ai_cfg.get("max_images_per_request", 50)
    max_concurrent = ai_cfg.get("max_concurrent_requests", 5)

    if domain is None:
        domain = get_default_domain()

    domain_storage = os.path.join(storage_root, domain).replace("\\", "/")
    queue_dir = os.path.join(domain_storage, "03_processing_queue").replace("\\", "/")
    os.makedirs(queue_dir, exist_ok=True)

    try:
        batches = get_unextracted_batches([DocumentStatus.PREPROCESSED.value, DocumentStatus.PENDING.value])

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
            batch_source = "_default" if folder_name == "_uncategorized" else folder_name
            if source and source != batch_source:
                return False

            pages = get_batch_pages(batch_id)
            if not pages:
                return False

            image_paths = [p["image_path"] for p in pages if os.path.exists(p["image_path"])]
            if not image_paths:
                return False

            chunks = list(chunk_list(image_paths, max_images))
            chunk_payloads = []

            for chunk_idx, chunk in enumerate(chunks, start=1):
                try:
                    payload = await async_extract_document_data(
                        image_paths=chunk,
                        source=batch_source,
                        domain=domain,
                        batch_id=batch_id,
                        chunk_index=chunk_idx,
                        semaphore=semaphore,
                    )
                    chunk_payloads.append(payload)
                except Exception as ex_err:
                    logger.error(f"Async AI extraction failed for batch '{batch_id}' chunk {chunk_idx}: {ex_err}")
                    return False

            if not chunk_payloads:
                return False

            merged_payload = merge_chunk_payloads(chunk_payloads)
            source_queue_dir = os.path.join(queue_dir, batch_source).replace("\\", "/")
            os.makedirs(source_queue_dir, exist_ok=True)

            for p in pages:
                image_basename = os.path.splitext(os.path.basename(p["image_path"]))[0]
                json_path = os.path.join(source_queue_dir, f"{image_basename}.json").replace("\\", "/")
                with open(json_path, "w", encoding="utf-8") as qf:
                    json.dump(merged_payload, qf, ensure_ascii=False, indent=2)
                update_page_status(p["page_id"], DocumentStatus.EXTRACTED.value)

            logger.info(f"Async AI extraction completed for batch '{batch_id}'. Status set to EXTRACTED.")
            return True

        results = await asyncio.gather(*[process_single_batch(b) for b in batches])
        success_batches = sum(1 for r in results if r)

        return {"success": True, "batches_processed": success_batches, "documents_extracted": success_batches}

    except Exception as e:
        logger.error(f"Error during async AI extraction stage: {e}")
        return {"success": False, "error": str(e)}

