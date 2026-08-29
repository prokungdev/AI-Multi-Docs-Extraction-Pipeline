"""
Unit test suite for Express Destination Target Adapter & Target Adapter Registry (Phase 3).
Verifies:
- Date transformation from CE YYYY-MM-DD to Thai Buddhist Era DD/MM/YY
- RefBillNo tail truncation to max 14 characters
- VatType to Express VatTypeId (2, 1, 0)
- WithholdingTaxNo generation in format YY/MM/NNN
- Full transformation matching the 3 real-world user scenarios (Grab, SPX, Shopee)
- Fail-fast dynamic strategy resolution via TargetAdapterRegistry
"""

import unittest
from src.infrastructure.core.constants import VatType, TargetSystemId
from src.application.exporters import (
    ExpressTargetAdapter,
    TargetAdapterRegistry,
)


class TestExpressTargetAdapter(unittest.TestCase):
    """
    Unit test suite for Express OE screen RPA adapter transformation logic.
    """

    def setUp(self):
        self.adapter = ExpressTargetAdapter()

    def test_01_date_formatting_ce_to_thai_be(self):
        """Test formatting ISO Common Era dates to Thai Buddhist Era DD/MM/YY."""
        self.assertEqual(self.adapter.format_date("2026-07-30"), "30/07/69")
        self.assertEqual(self.adapter.format_date("2025-12-01"), "01/12/68")
        self.assertEqual(self.adapter.format_date("2024-01-15"), "15/01/67")
        self.assertEqual(self.adapter.format_date(""), "")
        self.assertEqual(self.adapter.format_date(None), "")

    def test_02_ref_bill_no_tail_truncation(self):
        """Test tail truncation of RefBillNo exceeding Express 14 character limit."""
        # Short string (under 14 chars) -> unchanged
        self.assertEqual(self.adapter.truncate_ref_bill_no("TAX-1234"), "TAX-1234")
        self.assertEqual(self.adapter.truncate_ref_bill_no("12345678901234"), "12345678901234")

        # Long string (22 chars) -> last 14 chars
        raw_long = "TAX-2026-07-30-001234"
        self.assertEqual(len(self.adapter.truncate_ref_bill_no(raw_long)), 14)
        self.assertEqual(self.adapter.truncate_ref_bill_no(raw_long), raw_long[-14:])

    def test_03_vat_type_mapping(self):
        """Test mapping canonical VatType to Express VatTypeId integer codes."""
        self.assertEqual(self.adapter.map_vat_type_id(VatType.EXCLUSIVE.value), 2)
        self.assertEqual(self.adapter.map_vat_type_id("EXCLUSIVE"), 2)

        self.assertEqual(self.adapter.map_vat_type_id(VatType.INCLUSIVE.value), 1)
        self.assertEqual(self.adapter.map_vat_type_id("INCLUSIVE"), 1)

        self.assertEqual(self.adapter.map_vat_type_id(VatType.NO_VAT.value), 0)
        self.assertEqual(self.adapter.map_vat_type_id("NO_VAT"), 0)

    def test_04_withholding_tax_no_generation(self):
        """Test generating WithholdingTaxNo in format YY/MM/NNN from voucher_no."""
        # Voucher OE260730002 -> 26/07/002
        self.assertEqual(
            self.adapter.generate_withholding_tax_no("OE260730002", "2026-07-30"),
            "26/07/002"
        )
        self.assertEqual(
            self.adapter.generate_withholding_tax_no("OE260815099", "2026-08-15"),
            "26/08/099"
        )
        self.assertIsNone(self.adapter.generate_withholding_tax_no(None))

    def test_05_grabtaxi_real_world_scenario(self):
        """
        Scenario 1: Grabtaxi (Thailand)
        - VendorCode: G0001
        - Expense: ค่าบริการ (95-5310-19)
        - VatType: EXCLUSIVE (2)
        - WHT: 3% (WithholdingTaxNo generated)
        """
        voucher = {
            "voucher_no": "OE260730002",
            "voucher_date": "2026-07-30",
            "ref_doc_no": "GRAB-TAX-INV-2026-00008899",
            "ref_doc_date": "2026-07-30",
            "vendor_code": "G0001",
            "vendor_name": "Grabtaxi (Thailand) Co., Ltd.",
            "subtotal_amount": 1939.50,
            "vat_type": VatType.EXCLUSIVE.value,
            "vat_rate": 7.0,
            "vat_amount": 135.77,
            "wht_amount": 58.19,
            "net_amount": 2075.27,
            "items": [
                {
                    "line_number": 1,
                    "account_code": "95-5310-19",
                    "account_name": "ค่าบริการและที่ปรึกษา",
                    "department_code": "",
                    "amount": 1939.50,
                    "description": "Grab Taxi Service",
                }
            ]
        }
        merchant_cfg = {
            "vendor_code": "G0001",
            "merchant_name": "Grabtaxi (Thailand) Co., Ltd.",
            "default_expense_type": "ค่าบริการ",
            "default_vat_type": "EXCLUSIVE",
            "has_wht": 1,
            "default_wht_rate": 3.0,
        }

        payload = self.adapter.transform_voucher(voucher, merchant_config=merchant_cfg)

        self.assertEqual(payload["voucher_no"], "OE260730002")
        self.assertEqual(payload["voucher_date"], "30/07/69")
        self.assertEqual(payload["vendor_code"], "G0001")
        self.assertEqual(payload["vat_type_id"], 2)
        self.assertEqual(payload["vat_amount"], 135.77)
        self.assertEqual(payload["subtotal"], 1939.50)
        self.assertEqual(payload["wht_no"], "26/07/002")
        self.assertEqual(payload["wht_rate"], 3.0)
        self.assertEqual(payload["wht_amount"], 58.19)
        self.assertEqual(len(payload["ref_bill_no"]), 14)
        self.assertEqual(len(payload["lines"]), 1)
        self.assertEqual(payload["lines"][0]["account_code"], "95-5310-19")

    def test_06_spx_express_real_world_scenario(self):
        """
        Scenario 2: SPX Express (Thailand)
        - VendorCode: อ0022
        - Expense: ค่าขนส่ง (95-5200-05)
        - VatType: NO_VAT (0)
        - WHT: 0 (No WithholdingTaxNo)
        """
        voucher = {
            "voucher_no": "OE260730003",
            "voucher_date": "2026-07-30",
            "ref_doc_no": "SPX-998877",
            "ref_doc_date": "2026-07-30",
            "vendor_code": "อ0022",
            "vendor_name": "SPX Express (Thailand) Co., Ltd.",
            "subtotal_amount": 450.00,
            "vat_type": VatType.NO_VAT.value,
            "vat_rate": 0.0,
            "vat_amount": 0.0,
            "wht_amount": 0.0,
            "net_amount": 450.00,
            "items": [
                {
                    "line_number": 1,
                    "account_code": "95-5200-05",
                    "account_name": "ค่าขนส่งสินค้า",
                    "department_code": "",
                    "amount": 450.00,
                    "description": "SPX Shipping",
                }
            ]
        }
        merchant_cfg = {
            "vendor_code": "อ0022",
            "merchant_name": "SPX Express (Thailand) Co., Ltd.",
            "default_expense_type": "ค่าขนส่ง",
            "default_vat_type": "NO_VAT",
            "has_wht": 0,
            "default_wht_rate": 0.0,
        }

        payload = self.adapter.transform_voucher(voucher, merchant_config=merchant_cfg)

        self.assertEqual(payload["vendor_code"], "อ0022")
        self.assertEqual(payload["vat_type_id"], 0)
        self.assertEqual(payload["vat_amount"], 0.0)
        self.assertIsNone(payload["wht_no"])
        self.assertEqual(payload["wht_amount"], 0.0)
        self.assertEqual(payload["lines"][0]["account_code"], "95-5200-05")

    def test_07_shopee_real_world_scenario(self):
        """
        Scenario 3: Shopee (Thailand)
        - VendorCode: S0002
        - Expense: ค่าบริการ (95-5310-19)
        - VatType: INCLUSIVE (1)
        - WHT: 0 (No WithholdingTaxNo)
        """
        voucher = {
            "voucher_no": "OE260730004",
            "voucher_date": "2026-07-30",
            "ref_doc_no": "SHOPEE-INV-001",
            "ref_doc_date": "2026-07-30",
            "vendor_code": "S0002",
            "vendor_name": "Shopee (Thailand) Co., Ltd.",
            "subtotal_amount": 1000.00,
            "vat_type": VatType.INCLUSIVE.value,
            "vat_rate": 7.0,
            "vat_amount": 65.42,
            "wht_amount": 0.0,
            "net_amount": 1000.00,
            "items": [
                {
                    "line_number": 1,
                    "account_code": "95-5310-19",
                    "account_name": "ค่าบริการและที่ปรึกษา",
                    "department_code": "",
                    "amount": 1000.00,
                }
            ]
        }
        merchant_cfg = {
            "vendor_code": "S0002",
            "merchant_name": "Shopee (Thailand) Co., Ltd.",
            "default_expense_type": "ค่าบริการ",
            "default_vat_type": "INCLUSIVE",
            "has_wht": 0,
            "default_wht_rate": 0.0,
        }

        payload = self.adapter.transform_voucher(voucher, merchant_config=merchant_cfg)

        self.assertEqual(payload["vendor_code"], "S0002")
        self.assertEqual(payload["vat_type_id"], 1)
        self.assertIsNone(payload["wht_no"])
        self.assertEqual(payload["lines"][0]["account_code"], "95-5310-19")

    def test_08_target_adapter_registry_resolution(self):
        """Test resolving target adapters dynamically via TargetAdapterRegistry."""
        adapter = TargetAdapterRegistry.get_adapter("EXPRESS")
        self.assertIsInstance(adapter, ExpressTargetAdapter)

        # Default fallback without arguments
        default_adapter = TargetAdapterRegistry.get_adapter()
        self.assertIsInstance(default_adapter, ExpressTargetAdapter)

        # Unknown adapter fails fast with KeyError
        with self.assertRaises(KeyError):
            TargetAdapterRegistry.get_adapter("UNKNOWN_SYSTEM_XYZ")
