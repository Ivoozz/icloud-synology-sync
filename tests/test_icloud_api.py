import unittest
from unittest.mock import MagicMock, patch
from src.icloud_api import ICloudPhotosAPI

class TestICloudPhotosAPI(unittest.TestCase):
    def setUp(self):
        self.api = ICloudPhotosAPI(
            apple_id="test@example.com",
            password="testpassword"
        )

    @patch('src.icloud_api.PyiCloudService')
    def test_login_success(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = False
        mock_pyicloud.return_value = mock_instance
        
        self.assertTrue(self.api.login())
        self.assertEqual(self.api.api, mock_instance)

    @patch('src.icloud_api.PyiCloudService')
    def test_login_requires_2fa(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = True
        mock_pyicloud.return_value = mock_instance
        
        self.assertFalse(self.api.login())

    def test_list_photos_success(self):
        mock_api = MagicMock()
        mock_photo1 = MagicMock()
        mock_photo1.id = "id1"
        mock_photo2 = MagicMock()
        mock_photo2.id = "id2"
        mock_api.photos.all = [mock_photo1, mock_photo2]
        
        self.api.api = mock_api
        photos = self.api.list_photos()
        self.assertEqual(photos, ["id1", "id2"])

    def test_download_photo_success(self):
        mock_api = MagicMock()
        mock_photo = MagicMock()
        mock_response = MagicMock()
        mock_photo.download.return_value = mock_response
        mock_api.photos.all = {"id1": mock_photo}
        
        self.api.api = mock_api
        response = self.api.download_photo("id1")
        self.assertEqual(response, mock_response)
        mock_photo.download.assert_called_once()

    def test_delete_photo_success(self):
        mock_api = MagicMock()
        mock_photo = MagicMock()
        mock_api.photos.all = {"id1": mock_photo}
        
        self.api.api = mock_api
        self.assertTrue(self.api.delete_photo("id1"))
        mock_photo.delete.assert_called_once()

if __name__ == "__main__":
    unittest.main()
