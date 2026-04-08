import unittest
import responses
from src.synology_api import SynologyPhotosAPI

class TestSynologyPhotosAPI(unittest.TestCase):
    def setUp(self):
        self.api = SynologyPhotosAPI(
            base_url="https://synology.example.com",
            username="testuser",
            password="testpassword"
        )

    @responses.activate
    def test_ping_success(self):
        # Mock Login
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/auth.cgi",
            json={"success": True, "data": {"sid": "test-sid"}},
            status=200
        )
        
        # Mock Ping
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/entry.cgi",
            json={"success": True},
            status=200
        )
        
        self.api.login()
        self.assertTrue(self.api.ping())

    @responses.activate
    def test_list_photos_success(self):
        # Mock Login
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/auth.cgi",
            json={"success": True, "data": {"sid": "test-sid"}},
            status=200
        )
        # Mock List Photos
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/entry.cgi",
            json={
                "success": True,
                "data": {
                    "list": [{"id": 123, "filename": "photo1.jpg"}]
                }
            },
            status=200
        )
        self.api.login()
        photos = self.api.list_photos()
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]["filename"], "photo1.jpg")

    @responses.activate
    def test_file_exists_success(self):
        # Mock Login
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/auth.cgi",
            json={"success": True, "data": {"sid": "test-sid"}},
            status=200
        )
        # Mock File Exists (Item Get)
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/entry.cgi",
            json={"success": True, "data": {"item": {"id": 123}}},
            status=200
        )
        self.api.login()
        self.assertTrue(self.api.file_exists(123))

    @responses.activate
    def test_delete_file_success(self):
        # Mock Login
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/auth.cgi",
            json={"success": True, "data": {"sid": "test-sid"}},
            status=200
        )
        # Mock Delete
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/entry.cgi",
            json={"success": True},
            status=200
        )
        self.api.login()
        self.assertTrue(self.api.delete_file(123))

    @responses.activate
    def test_upload_stream_success(self):
        # Mock Login
        responses.add(
            responses.GET,
            "https://synology.example.com/webapi/auth.cgi",
            json={"success": True, "data": {"sid": "test-sid"}},
            status=200
        )
        # Mock Upload
        responses.add(
            responses.POST,
            "https://synology.example.com/webapi/entry.cgi",
            json={"success": True, "data": {"id": 456}},
            status=200
        )
        self.api.login()
        
        def mock_generator():
            yield b"fake image data"
            
        self.assertTrue(self.api.upload_stream(mock_generator(), "test.jpg"))

if __name__ == "__main__":
    unittest.main()
