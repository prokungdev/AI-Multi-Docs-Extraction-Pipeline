import unittest
import os
import json
from pydantic import ValidationError
from src.infrastructure.core.config import (
    load_doc_type_schema,
    load_doc_type_classify_schema,
    load_doc_type_prompt,
    load_doc_type_classify_prompt,
    load_doc_type_rules,
)
from src.domain.doc_types import DocTypeRegistry, get_doc_type
from src.application.usecases.initializer import validate_doc_type_config, validate_settings_config
from src.application.dtos.settings_dto import SystemSettingsModel


class TestDynamicDocTypeConfig(unittest.TestCase):
    """
    Tests for DocType asset loading and initializer validation routines.
    """

    def test_load_all_doc_type_files(self):
        """Verify specialized fail-fast loaders successfully parse doc_type files via DocTypeRegistry."""
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
            load_doc_type_prompt("non_existent_doc_type")
        self.assertIn("non_existent_doc_type", str(ctx.exception))

    def test_validate_doc_type_config_routine(self):
        """Verify initializer validate_doc_type_config checks all assets."""
        is_valid, errors = validate_doc_type_config("expense_receipt")
        self.assertTrue(is_valid, f"Validation errors: {errors}")
        self.assertEqual(len(errors), 0)

        # Non existent doc_type
        invalid_res, invalid_errs = validate_doc_type_config("ghost_doc_type")
        self.assertFalse(invalid_res)
        self.assertTrue(len(invalid_errs) > 0)


if __name__ == "__main__":
    unittest.main()
