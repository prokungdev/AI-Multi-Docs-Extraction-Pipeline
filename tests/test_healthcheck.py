import unittest
from src.core.healthcheck import (
    run_healthcheck,
    check_database_status,
    check_api_ready
)
from src.core.config_loader import load_system_settings

class TestHealthcheck(unittest.TestCase):

    def setUp(self):
        self.settings = load_system_settings()

    def test_01_database_status_check(self):
        """Test database connection status check."""
        ok, msg = check_database_status()
        self.assertTrue(ok)
        self.assertIn("Connected", msg)
        print(f"[TEST] DB Status check passed: {msg}")

    def test_02_api_ready_check(self):
        """Test AI API readiness check."""
        ok, msg, remedies = check_api_ready(self.settings)
        self.assertTrue(ok)
        self.assertEqual(len(remedies), 0)
        print(f"[TEST] API Ready check passed: {msg}")

    def test_03_full_run_healthcheck(self):
        """Test lightweight run_healthcheck execution payload."""
        results = run_healthcheck()
        self.assertIn("healthy", results)
        self.assertIn("status", results)
        self.assertIn("checks", results)
        self.assertIn("database", results["checks"])
        self.assertIn("api_ready", results["checks"])
        self.assertTrue(results["healthy"])
        self.assertEqual(results["status"], "OK")
        print(f"[TEST] Lean System Healthcheck suite passed: Status={results['status']}")

if __name__ == "__main__":
    unittest.main()
