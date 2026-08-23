import unittest
import os
import json
from pydantic import ValidationError
from src.core.config_loader import (
    get_doctype_file_path,
    load_doc_type_schema,
    load_doc_type_classify_schema,
    load_doc_type_prompt,
    load_doc_type_classify_prompt,
    load_doc_type_rules,
)
from src.core.initializer import validate_doc_type_config, validate_settings_config
from src.core.schemas.settings_schema import SystemSettingsModel


class TestDynamicDocTypeConfig(unittest.TestCase):
    """
    Tests for Dynamic DocType File Mapping in settings.json with Pure Fail-Fast semantics.
    """

    def test_get_doctype_file_path_success(self):
        """Verify get_doctype_file_path correctly resolves all 5 file keys."""
        keys = ["classify_prompt", "classify_schema", "extract_prompt", "extract_schema", "extract_rules"]
        for key in keys:
            path = get_doctype_file_path("expense_receipt", key)
            self.assertTrue(os.path.exists(path), f"Path does not exist: {path}")

    def test_load_all_doc_type_files(self):
        """Verify specialized fail-fast loaders successfully parse doc_type files."""
        classify_prompt = load_doc_type_classify_prompt("expense_receipt")
        self.assertIsInstance(classify_prompt, str)
        self.assertTrue(len(classify_prompt) > 0)

        classify_schema = load_doc_type_classify_schema("expense_receipt")
        self.assertIsInstance(classify_schema, dict)
        self.assertEqual(classify_schema.get("type"), "OBJECT")
        self.assertIn("tax_id", classify_schema.get("properties", {}))

        extract_prompt = load_doc_type_prompt("expense_receipt")
        self.assertIsInstance(extract_prompt, str)

        extract_schema = load_doc_type_schema("expense_receipt")
        self.assertIsInstance(extract_schema, dict)

        extract_rules = load_doc_type_rules("expense_receipt")
        self.assertIsInstance(extract_rules, dict)

    def test_unknown_doctype_fails_fast(self):
        """Verify unknown doc_type raises KeyError immediately without fallback."""
        with self.assertRaises(KeyError) as ctx:
            get_doctype_file_path("non_existent_doc_type", "classify_prompt")
        self.assertIn("non_existent_doc_type", str(ctx.exception))

    def test_unknown_file_key_fails_fast(self):
        """Verify unknown file key raises KeyError immediately without fallback."""
        with self.assertRaises(KeyError) as ctx:
            get_doctype_file_path("expense_receipt", "unknown_custom_file_key")
        self.assertIn("unknown_custom_file_key", str(ctx.exception))

    def test_missing_disk_file_fails_fast(self):
        """Verify referencing a missing file on disk raises FileNotFoundError."""
        with open("configs/settings.json", "r", encoding="utf-8") as f:
            settings_dict = json.load(f)

        # Temporarily mock a fake filename in settings dict
        temp_settings = json.loads(json.dumps(settings_dict))
        temp_settings["doc_types"][0]["files"]["classify_prompt"] = "ghost_prompt_file_that_does_not_exist.txt"

        import uuid
        import tempfile
        temp_settings_file = os.path.join(tempfile.gettempdir(), f"temp_test_settings_{uuid.uuid4().hex[:8]}.json").replace("\\", "/")
        with open(temp_settings_file, "w", encoding="utf-8") as f:
            json.dump(temp_settings, f)

        try:
            with self.assertRaises(FileNotFoundError):
                get_doctype_file_path("expense_receipt", "classify_prompt", settings_path=temp_settings_file)
        finally:
            if os.path.exists(temp_settings_file):
                os.remove(temp_settings_file)

    def test_pydantic_schema_enforces_files_map(self):
        """Verify Pydantic SystemSettingsModel rejects doc_types without files map."""
        with open("configs/settings.json", "r", encoding="utf-8") as f:
            valid_settings = json.load(f)

        # 1. Valid settings passes
        model = SystemSettingsModel.model_validate(valid_settings)
        self.assertIsNotNone(model)

        # 2. Incomplete files map raises ValidationError
        invalid_settings = json.loads(json.dumps(valid_settings))
        del invalid_settings["doc_types"][0]["files"]["classify_schema"]

        with self.assertRaises(ValidationError):
            SystemSettingsModel.model_validate(invalid_settings)

    def test_validate_doc_type_config_routine(self):
        """Verify initializer validate_doc_type_config checks all 5 files."""
        is_valid, errors = validate_doc_type_config("expense_receipt")
        self.assertTrue(is_valid, f"Validation errors: {errors}")
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
