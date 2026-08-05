import unittest

from fastapi.testclient import TestClient

from app.main import app


class DesktopRuntimeTests(unittest.TestCase):
    def test_ready_endpoint_reports_initialized_runtime(self):
        with TestClient(app) as client:
            response = client.get("/api/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertIn("version", response.json())


if __name__ == "__main__":
    unittest.main()
