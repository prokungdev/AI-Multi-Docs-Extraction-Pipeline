import os
import shutil
import unittest
import uuid
from fastapi.testclient import TestClient

from apps.api.main import app
from src.core.healthcheck import (
    run_healthcheck,
    check_database_status,
    check_api_ready,
)
from src.core.config_loader import load_system_settings, get_company_storage_dir
from src.core.db.connection import get_db_session
from src.core.db.models import Company


class TestHealthcheckServices(unittest.TestCase):
    """
    Test suite for System Healthcheck and Readiness diagnostics.
    """

    def setUp(self):
        self.settings = load_system_settings()

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


class TestFastAPIRestAPI(unittest.TestCase):
    """
    Test suite for FastAPI REST API endpoints and Multi-Company lifecycle.
    Fully isolated with dedicated temporary database.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        from src.core.db import initialize_db_schema, seed_initial_data
        cls.test_db_path = os.path.join(tempfile.gettempdir(), f"test_api_db_{uuid.uuid4().hex[:8]}.db").replace("\\", "/")
        os.environ["DB_PATH_OVERRIDE"] = cls.test_db_path
        initialize_db_schema()
        seed_initial_data()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        import gc
        from src.core.db.connection import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        gc.collect()
        if hasattr(cls, "test_db_path") and os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass
        if "DB_PATH_OVERRIDE" in os.environ:
            del os.environ["DB_PATH_OVERRIDE"]

    def test_root_endpoint(self):
        """Verify root endpoint returns service metadata and links."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("docs_url"), "/docs")
        self.assertEqual(data.get("health_check"), "/api/v1/health")

    def test_swagger_docs_accessible(self):
        """Verify Swagger UI documentation page is accessible."""
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_health_endpoint(self):
        """Verify /api/v1/health endpoint connects to Core Healthcheck and DB."""
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("healthy", data)
        self.assertIn("checks", data)
        self.assertIn("database", data["checks"])
        self.assertTrue(data["checks"]["database"]["ok"])

    def test_nonexistent_route_404(self):
        """Verify undefined routes return 404 Not Found."""
        response = self.client.get("/api/v1/undefined-endpoint")
        self.assertEqual(response.status_code, 404)

    def test_companies_crud_lifecycle(self):
        """Verify company listing, creation, retrieval, updating, duplicate tax_id rejection, and deletion via REST API."""
        # 1. List companies
        list_res = self.client.get("/api/v1/companies")
        self.assertEqual(list_res.status_code, 200)
        companies = list_res.json()
        self.assertIsInstance(companies, list)

        # 2. Create new company
        test_suffix = uuid.uuid4().hex[:6].upper()
        test_code = f"C_{test_suffix}"
        test_tax_id = f"01055{uuid.uuid4().hex[:8]}"[:13]
        new_payload = {
            "company_code": test_code,
            "company_name": f"Test Company {test_suffix} Ltd",
            "short_name": f"TestCo_{test_suffix}",
            "tax_id": test_tax_id,
            "branch_code": "00000"
        }
        test_dir = get_company_storage_dir(test_code)
        try:
            create_res = self.client.post("/api/v1/companies", json=new_payload)
            self.assertEqual(create_res.status_code, 201)
            created_data = create_res.json()
            self.assertEqual(created_data["company_code"], test_code)
            self.assertEqual(created_data["company_name"], f"Test Company {test_suffix} Ltd")

            # 2.1 Verify Duplicate Tax ID rejection (409 Conflict)
            dup_tax_payload = {
                "company_code": f"C_{uuid.uuid4().hex[:6].upper()}",
                "company_name": "Another Company With Same Tax ID",
                "short_name": "ANOTHER",
                "tax_id": test_tax_id,
                "branch_code": "00000"
            }
            dup_res = self.client.post("/api/v1/companies", json=dup_tax_payload)
            self.assertEqual(dup_res.status_code, 409)

            # 3. Retrieve company by code
            get_res = self.client.get(f"/api/v1/companies/{test_code}")
            self.assertEqual(get_res.status_code, 200)
            comp_data = get_res.json()
            self.assertEqual(comp_data["company_code"], test_code)
            comp_id = comp_data["company_id"]

            # 4. Update company details
            patch_res = self.client.patch(
                f"/api/v1/companies/{comp_id}",
                json={"short_name": f"TestCo_{test_suffix}_Updated"}
            )
            self.assertEqual(patch_res.status_code, 200)
            updated_data = patch_res.json()
            self.assertEqual(updated_data["short_name"], f"TestCo_{test_suffix}_Updated")

            # 5. Delete company via REST API
            del_res = self.client.delete(f"/api/v1/companies/{test_code}")
            self.assertEqual(del_res.status_code, 200)

            # 6. Verify deletion
            get_after_del = self.client.get(f"/api/v1/companies/{test_code}")
            self.assertEqual(get_after_del.status_code, 404)
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir, ignore_errors=True)


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
        from src.core.initializer import validate_settings_config
        is_valid, errors = validate_settings_config(self.valid_settings_path)
        self.assertTrue(is_valid, f"Expected production settings to be valid, got errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_02_missing_thresholds_fails(self):
        """Test that missing validation_thresholds fails immediately."""
        from src.core.initializer import validate_settings_config
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
        from src.core.initializer import validate_settings_config
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
        from src.core.initializer import validate_settings_config
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
        from src.core.initializer import validate_settings_config
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
        from src.core.initializer import validate_settings_config
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
        from src.core.initializer import validate_settings_config
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
        from src.core.initializer import validate_environment
        messages = validate_environment(self.valid_settings_path)
        # Should not have write errors on standard local directories
        self.assertFalse(any("is not writable" in m for m in messages))


if __name__ == "__main__":
    unittest.main()

