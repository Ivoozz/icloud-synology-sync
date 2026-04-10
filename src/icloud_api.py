import logging
from typing import Any, Dict, Iterable, List, Optional
from pyicloud import PyiCloudService

logger = logging.getLogger(__name__)

class ICloudPhotosAPI:
    """
    Wrapper for iCloud Photos API using pyicloud.
    """
    def __init__(self, apple_id: str, password: str):
        self.apple_id = self._normalize_apple_id(apple_id)
        self.password = self._normalize_password(password)
        self.api = None
        self.requires_2fa = False
        self.last_error = ""

    @staticmethod
    def _normalize_apple_id(apple_id: str) -> str:
        return (apple_id or "").strip()

    @staticmethod
    def _normalize_password(password: str) -> str:
        return (password or "").strip()

    def login(self) -> bool:
        """
        Authenticates with iCloud.
        """
        try:
            self.api = PyiCloudService(self.apple_id, self.password)
            self.requires_2fa = bool(getattr(self.api, "requires_2fa", False))
            if self.api.requires_2fa:
                self.last_error = "Two-factor authentication required"
                logger.warning("Two-factor authentication required.")
                return False
            self.last_error = ""
            return True
        except Exception as e:
            error_text = str(e)
            self.last_error = error_text
            lowered = error_text.lower()
            if "password" in lowered or "invalid" in lowered or "authentication" in lowered:
                logger.error(
                    "iCloud login failed. Verify Apple ID and password. "
                    "If your account has 2FA enabled, complete the code verification when prompted. "
                    f"Details: {error_text}"
                )
            else:
                logger.error(f"iCloud login failed: {error_text}")
            return False

    def verify_2fa(self, code: str) -> bool:
        """
        Validates an Apple 2FA code and requests a trusted session.
        """
        if not self.api:
            self.last_error = "No active iCloud session"
            return False

        entered_code = (code or "").strip()
        if not entered_code:
            self.last_error = "No 2FA code provided"
            return False

        try:
            result = self.api.validate_2fa_code(entered_code)
            if not result:
                self.last_error = "Failed to validate 2FA code"
                logger.error(self.last_error)
                return False

            if not self.api.is_trusted_session:
                trust_result = self.api.trust_session()
                if not trust_result:
                    logger.warning("2FA code accepted, but trusted session request failed.")

            self.requires_2fa = False
            self.last_error = ""
            logger.info("iCloud 2FA verification succeeded.")
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"2FA verification failed: {self.last_error}")
            return False

    def _iter_photo_objects(self) -> Iterable[Any]:
        if not self.api:
            return []

        photos = getattr(self.api, "photos", None)
        if photos is None:
            return []

        all_photos = getattr(photos, "all", [])
        if isinstance(all_photos, dict):
            return all_photos.values()
        return all_photos

    def _find_photo(self, icloud_id: str) -> Optional[Any]:
        if not self.api:
            return None

        photos = getattr(self.api, "photos", None)
        if photos is not None:
            all_photos = getattr(photos, "all", None)
            if isinstance(all_photos, dict) and icloud_id in all_photos:
                return all_photos[icloud_id]

        for photo in self._iter_photo_objects():
            if getattr(photo, "id", None) == icloud_id:
                return photo
        return None

    def _photo_record(self, photo: Any) -> Dict[str, Any]:
        filename = (
            getattr(photo, "download_filename", None)
            or getattr(photo, "filename", None)
            or getattr(photo, "original_filename", None)
            or f"{getattr(photo, 'id', 'unknown')}.jpg"
        )
        return {
            "id": getattr(photo, "id", None),
            "filename": filename,
            "filename_hint": filename,
        }

    def list_photos(self) -> List[str]:
        """
        Returns a list of unique iCloud photo identifiers.
        """
        try:
            return [record["id"] for record in self.list_photo_records() if record.get("id")]
        except Exception as e:
            logger.error(f"Failed to list iCloud photos: {e}")
            return []

    def list_photo_records(self) -> List[Dict[str, Any]]:
        """
        Returns detailed photo metadata for reconciliation.
        """
        if not self.api:
            return []
        try:
            return [self._photo_record(photo) for photo in self._iter_photo_objects()]
        except Exception as e:
            logger.error(f"Failed to list iCloud photo records: {e}")
            return []

    def download_photo(self, icloud_id: str) -> Any:
        """
        Returns a streaming response object for the given photo ID.
        """
        if not self.api:
            return None
        try:
            photo = self._find_photo(icloud_id)
            if not photo:
                logger.error(f"Photo {icloud_id} not found in iCloud library.")
                return None
            return photo.download()
        except Exception as e:
            logger.error(f"Failed to download iCloud photo {icloud_id}: {e}")
            return None

    def delete_photo(self, icloud_id: str) -> bool:
        """
        Deletes a photo from iCloud.
        """
        if not self.api:
            return False
        try:
            photo = self._find_photo(icloud_id)
            if not photo:
                logger.error(f"Photo {icloud_id} not found in iCloud library.")
                return False
            photo.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete iCloud photo {icloud_id}: {e}")
            return False
