import os
from src.infrastructure.common.logger import logger

from src.infrastructure.common.config_loader import load_system_settings, get_default_doc_type
from src.infrastructure.persistence import reset_pipeline_database


def reset_pipeline_data(
    doc_type: str = None,
    clear_storage_temp: bool = True,
    clear_database: bool = True,
    clear_documents_only: bool = False
) -> dict:
    """
    Resets the pipeline for a fresh interactive test run.
    - Drops/recreates all database tables and re-seeds initial data if clear_database is True.
    - Cleans temporary files in 03_preprocess and 04_processing if clear_storage_temp is True.
    """
    logger.info("Resetting Pipeline Data (Fresh Start)")

    settings = load_system_settings()
    storage_root = settings.get("storage_root", "storage")
    target_doc_type = doc_type or get_default_doc_type()

    res = {"database_reset": False, "storage_cleaned": False, "deleted_files_count": 0}

    # 1. Reset Database
    if clear_database:
        db_res = reset_pipeline_database(clear_documents_only=clear_documents_only)
        res["database_reset"] = (db_res.get("status") == "SUCCESS")

    # 2. Clean temporary pipeline storage across companies (02_raw_data, 03_preprocess, 04_processing)
    if clear_storage_temp:
        import shutil
        from src.infrastructure.storage.storage_manager import storage_manager
        comp_root = os.path.join(storage_manager.root, "companies").replace("\\", "/")
        deleted_count = 0

        if os.path.exists(comp_root):
            for c in os.listdir(comp_root):
                # Clean 02_raw_data: delete PENDING, IGNORED, and all merchant folders except NO_TAXID & .gitkeep
                raw_dir = storage_manager.get_raw_data_dir(c, target_doc_type)
                if os.path.exists(raw_dir):
                    for item in os.listdir(raw_dir):
                        item_path = os.path.join(raw_dir, item).replace("\\", "/")
                        if item.startswith(".gitkeep"):
                            continue
                        if item == "0000000000000_no_taxid":
                            for f in os.listdir(item_path):
                                if not f.startswith(".gitkeep"):
                                    try:
                                        os.remove(os.path.join(item_path, f))
                                        deleted_count += 1
                                    except Exception:
                                        pass
                        else:
                            if os.path.isdir(item_path):
                                for _, _, files in os.walk(item_path):
                                    deleted_count += len([f for f in files if not f.startswith(".gitkeep")])
                                shutil.rmtree(item_path, ignore_errors=True)
                            else:
                                try:
                                    os.remove(item_path)
                                    deleted_count += 1
                                except Exception:
                                    pass

                # Clean 03_preprocess and 04_processing
                for get_dir_fn in [storage_manager.get_preprocess_dir, storage_manager.get_processing_dir]:
                    folder = get_dir_fn(c, target_doc_type)
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
        logger.info(f"Cleaned {deleted_count} temporary files across raw_data, preprocess, and processing queues.")

    return res
