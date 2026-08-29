import os
import shutil
import unittest
import uuid
import pytest

from src.infrastructure.core.healthcheck import (
    run_healthcheck,
    check_database_status,
    check_api_ready,
)
from src.infrastructure.core.config import load_system_settings
from src.infrastructure.database.engine import get_db_session
from src.infrastructure.database.models import Company


class TestHealthcheckServices(unittest.TestCase):
    """
    Test suite for System Healthcheck and Readiness diagnostics.
    """

    def setUp(self):
        self.settings = load_system_settings()
        self._orig_api_key = os.environ.get("GEMINI_API_KEY")
        self._orig_free_key = os.environ.get("GEMINI_API_KEY_FREE")
        os.environ["GEMINI_API_KEY"] = "mock_api_key_for_healthcheck_test"
        os.environ["GEMINI_API_KEY_FREE"] = "mock_api_key_for_healthcheck_test"

    def tearDown(self):
        if self._orig_api_key is not None:
            os.environ["GEMINI_API_KEY"] = self._orig_api_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

        if self._orig_free_key is not None:
            os.environ["GEMINI_API_KEY_FREE"] = self._orig_free_key
        else:
            os.environ.pop("GEMINI_API_KEY_FREE", None)

    def test_01_database_status_check(self):
        """Test database connection status check."""
        ok, msg = check_database_status()
        self.assertTrue(ok)
        self.assertIn("Connected", msg)

    def test_02_api_ready_check(self):
        """Test AI API readiness check."""
        ok, msg, remedies = check_api_ready(self.settings)
        self.assertTrue(ok)
        self.assertEqual(len(remedies), 0)

    def test_03_full_run_healthcheck(self):
        """Test lightweight run_healthcheck execution payload."""
        results = run_healthcheck()
        self.assertIn("healthy", results)
        self.assertIn("status", results)
        self.assertIn("checks", results)
        self.assertIn("database", results["checks"])
        self.assertIn("api_ready", results["checks"])
        self.assertIn("storage_ready", results["checks"])
        self.assertTrue(results["healthy"])
        self.assertEqual(results["status"], "OK")


class TestSystemConfigurationValidation(unittest.TestCase):
    """
    Test suite for Strict Fail-Fast Validation of settings.json schema & thresholds.
    """

    def setUp(self):
        import json
        import tempfile
        self.temp_dir = tempfile.gettempdir()
        self.valid_settings_path = "configs/settings.json"
        with open(self.valid_settings_path, "r", encoding="utf-8") as f:
            self.valid_dict = json.load(f)

    def _write_temp_settings(self, data: dict) -> str:
        import json
        import tempfile
        tmp_path = os.path.join(self.temp_dir, f"test_settings_{uuid.uuid4().hex[:8]}.json")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return tmp_path

    def test_01_valid_production_settings(self):
        """Test that production settings.json is 100% valid."""
        from src.application.usecases.initializer import validate_settings_config
        is_valid, errors = validate_settings_config(self.valid_settings_path)
        self.assertTrue(is_valid, f"Expected production settings to be valid, got errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_02_missing_thresholds_fails(self):
        """Test that missing validation_thresholds fails immediately."""
        from src.application.usecases.initializer import validate_settings_config
        import copy
        bad_dict = copy.deepcopy(self.valid_dict)
        del bad_dict["validation_thresholds"]
        tmp_path = self._write_temp_settings(bad_dict)
        try:
            is_valid, errors = validate_settings_config(tmp_path)
            self.assertFalse(is_valid)
            self.assertTrue(any("validation_thresholds" in e for e in errors))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_03_invalid_dpi_range_fails(self):
        """Test that DPI outside 72-600 fails immediately."""
        from src.application.usecases.initializer import validate_settings_config
        import copy
        bad_dict = copy.deepcopy(self.valid_dict)
        bad_dict["image_processing"]["dpi"] = 10
        tmp_path = self._write_temp_settings(bad_dict)
        try:
            is_valid, errors = validate_settings_config(tmp_path)
            self.assertFalse(is_valid)
            self.assertTrue(any("DPI must be between 72 and 600" in e for e in errors))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_04_missing_pattern_placeholder_fails(self):
        """Test that filename pattern missing {page_no} fails."""
        from src.application.usecases.initializer import validate_settings_config
        import copy
        bad_dict = copy.deepcopy(self.valid_dict)
        bad_dict["image_processing"]["split_filename_pattern"] = "{doc_type}_{tax_id}_static"
        tmp_path = self._write_temp_settings(bad_dict)
        try:
            is_valid, errors = validate_settings_config(tmp_path)
            self.assertFalse(is_valid)
            self.assertTrue(any("page_no" in e for e in errors))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_05_missing_active_doc_types_fails(self):
        """Test that missing active doc_types fails."""
        from src.application.usecases.initializer import validate_settings_config
        import copy
        bad_dict = copy.deepcopy(self.valid_dict)
        for d in bad_dict.get("doc_types", []):
            d["is_active"] = False
        tmp_path = self._write_temp_settings(bad_dict)
        try:
            is_valid, errors = validate_settings_config(tmp_path)
            self.assertFalse(is_valid)
            self.assertTrue(any("No active doc_types configured" in e for e in errors))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_06_threshold_hierarchy_inversion_fails(self):
        """Test that inverted confidence thresholds fail cross-field validation."""
        from src.application.usecases.initializer import validate_settings_config
        import copy
        bad_dict = copy.deepcopy(self.valid_dict)
        bad_dict["validation_thresholds"]["confidence_low"] = 0.90
        bad_dict["validation_thresholds"]["confidence_high"] = 0.70
        tmp_path = self._write_temp_settings(bad_dict)
        try:
            is_valid, errors = validate_settings_config(tmp_path)
            self.assertFalse(is_valid)
            self.assertTrue(any("Invalid threshold hierarchy" in e for e in errors))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_07_pricing_parity_mismatch_fails(self):
        """Test that configuring active AI model missing from pricing table fails."""
        from src.application.usecases.initializer import validate_settings_config
        import copy
        bad_dict = copy.deepcopy(self.valid_dict)
        bad_dict["ai_provider"]["gemini"]["model_name"] = "unpriced-experimental-model"
        tmp_path = self._write_temp_settings(bad_dict)
        try:
            is_valid, errors = validate_settings_config(tmp_path)
            self.assertFalse(is_valid)
            self.assertTrue(any("missing pricing configuration" in e for e in errors))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_08_storage_write_permission_probe(self):
        """Test environment validation and write permission probes."""
        from src.application.usecases.initializer import validate_environment
        messages = validate_environment(self.valid_settings_path)
        # Should not have write errors on standard local directories
        self.assertFalse(any("is not writable" in m for m in messages))


if __name__ == "__main__":
    unittest.main()

