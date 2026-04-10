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
    def test_login_normalizes_apple_credentials(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = False
        mock_pyicloud.return_value = mock_instance

        api = ICloudPhotosAPI(
            apple_id="  test@example.com  ",
            password="  pass- word  "
        )

        self.assertTrue(api.login())
        mock_pyicloud.assert_called_once_with("test@example.com", "pass- word")

    @patch('src.icloud_api.PyiCloudService')
    def test_login_requires_2fa(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = True
        mock_instance.requires_2sa = False
        mock_pyicloud.return_value = mock_instance
        
        self.assertFalse(self.api.login())
        self.assertTrue(self.api.requires_2fa)

    @patch('src.icloud_api.PyiCloudService')
    def test_login_requires_2sa(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = False
        mock_instance.requires_2sa = True
        mock_pyicloud.return_value = mock_instance

        self.assertFalse(self.api.login())
        self.assertTrue(self.api.requires_2sa)

    @patch('src.icloud_api.PyiCloudService')
    def test_verify_2fa_success(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = True
        mock_instance.requires_2sa = False
        mock_instance.validate_2fa_code.return_value = True
        mock_instance.is_trusted_session = False
        mock_instance.trust_session.return_value = True
        mock_pyicloud.return_value = mock_instance

        self.assertFalse(self.api.login())
        self.assertTrue(self.api.verify_2fa("123456"))
        mock_instance.validate_2fa_code.assert_called_once_with("123456")

    @patch('src.icloud_api.PyiCloudService')
    def test_verify_2fa_failure(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = True
        mock_instance.requires_2sa = False
        mock_instance.validate_2fa_code.return_value = False
        mock_instance.is_trusted_session = True
        mock_pyicloud.return_value = mock_instance

        self.assertFalse(self.api.login())
        self.assertFalse(self.api.verify_2fa("111111"))

    @patch('src.icloud_api.PyiCloudService')
    def test_2fa_can_request_trusted_device_code(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = True
        mock_instance.requires_2sa = False
        mock_instance.two_factor_delivery_method = "trusted_device"
        mock_instance.two_factor_delivery_notice = ""
        mock_instance.trusted_devices = [{"deviceName": "iPhone"}]
        mock_instance.send_verification_code.return_value = True
        mock_instance.request_2fa_code.return_value = True
        mock_pyicloud.return_value = mock_instance

        self.assertFalse(self.api.login())
        self.assertTrue(self.api.request_2fa_code())
        self.assertEqual(self.api.two_factor_delivery_method, "trusted_device")
        self.assertTrue(self.api.send_2sa_verification_code(0))

    @patch('src.icloud_api.PyiCloudService')
    def test_2sa_send_and_verify_success(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = False
        mock_instance.requires_2sa = True
        mock_instance.trusted_devices = [{"deviceName": "iPhone"}]
        mock_instance.send_verification_code.return_value = True
        mock_instance.validate_verification_code.return_value = True
        mock_pyicloud.return_value = mock_instance

        self.assertFalse(self.api.login())
        self.assertTrue(self.api.send_2sa_verification_code(0))
        self.assertTrue(self.api.verify_2sa("123456", 0))

    @patch('src.icloud_api.PyiCloudService')
    def test_2sa_verify_failure(self, mock_pyicloud):
        mock_instance = MagicMock()
        mock_instance.requires_2fa = False
        mock_instance.requires_2sa = True
        mock_instance.trusted_devices = [{"deviceName": "iPhone"}]
        mock_instance.send_verification_code.return_value = True
        mock_instance.validate_verification_code.return_value = False
        mock_pyicloud.return_value = mock_instance

        self.assertFalse(self.api.login())
        self.assertTrue(self.api.send_2sa_verification_code(0))
        self.assertFalse(self.api.verify_2sa("111111", 0))

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
