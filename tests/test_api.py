import unittest
from fastapi.testclient import TestClient
from apps.api.main import app


class TestFastAPIRestAPI(unittest.TestCase):
    """
    Test suite for FastAPI REST API endpoints.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_root_endpoint(self):
        """
        Verify root endpoint returns service metadata and links.
        """
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("docs_url"), "/docs")
        self.assertEqual(data.get("health_check"), "/api/v1/health")

    def test_swagger_docs_accessible(self):
        """
        Verify Swagger UI documentation page is accessible.
        """
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_health_endpoint(self):
        """
        Verify /api/v1/health endpoint connects to Core Healthcheck and DB.
        """
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("healthy", data)
        self.assertIn("checks", data)
        self.assertIn("database", data["checks"])
        self.assertTrue(data["checks"]["database"]["ok"])

    def test_nonexistent_route_404(self):
        """
        Verify undefined routes return 404 Not Found.
        """
        response = self.client.get("/api/v1/undefined-endpoint")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
