import os
from src.core.logger import logger

from src.core.config_loader import load_system_settings, get_default_doc_type
from src.core.db import reset_pipeline_database


def reset_pipeline_data(
    doc_type: str = None,
    clear_storage_temp: bool = True,
    clear_database: bool = True
) -> dict:
    """
    Resets the pipeline for a fresh interactive test run.
    - Clears transactional document database tables if clear_database is True.
    - Cleans temporary files in 02_split_pages and 03_processing_queue if clear_storage_temp is True.
    """
    logger.info("Resetting Pipeline Data (Fresh Start)")

    settings = load_system_settings()
    storage_root = settings.get("storage_root", "storage")
    target_doc_type = doc_type or get_default_doc_type()

    res = {"database_reset": False, "storage_cleaned": False, "deleted_files_count": 0}

    # 1. Reset Database
    if clear_database:
        db_res = reset_pipeline_database(clear_documents_only=True)
        res["database_reset"] = db_res.get("success", False)

    # 2. Clean temporary pipeline storage across companies
    if clear_storage_temp:
        from src.core.storage_manager import storage_manager
        comp_root = os.path.join(storage_manager.root, "companies").replace("\\", "/")
        folders_to_clean = []
        if os.path.exists(comp_root):
            for c in os.listdir(comp_root):
                folders_to_clean.append(storage_manager.get_preprocess_dir(c, target_doc_type))
                folders_to_clean.append(storage_manager.get_processing_dir(c, target_doc_type))

        deleted_count = 0
        for folder in folders_to_clean:
            if os.path.exists(folder):
                for root_dir, _, files in os.walk(folder):
                    for file in files:
                        if not file.startswith(".gitkeep"):
                            try:
                                os.remove(os.path.join(root_dir, file))
                                deleted_count += 1
                            except Exception as fe:
                                logger.warning(f"Could not remove temporary file {file}: {fe}")

        res["storage_cleaned"] = True
        res["deleted_files_count"] = deleted_count
        logger.info(f"Cleaned {deleted_count} temporary files from preprocess and processing queues.")

    return res
