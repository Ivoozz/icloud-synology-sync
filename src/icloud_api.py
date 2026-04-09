import logging
from typing import Any, Dict, Iterable, List, Optional
from pyicloud import PyiCloudService

logger = logging.getLogger(__name__)

class ICloudPhotosAPI:
    """
    Wrapper for iCloud Photos API using pyicloud.
    """
    def __init__(self, apple_id: str, password: str):
        self.apple_id = apple_id
        self.password = password
        self.api = None

    def login(self) -> bool:
        """
        Authenticates with iCloud.
        """
        try:
            self.api = PyiCloudService(self.apple_id, self.password)
            if self.api.requires_2fa:
                logger.warning("Two-factor authentication required. Manual login might be needed once.")
                return False
            return True
        except Exception as e:
            logger.error(f"iCloud login failed: {e}")
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
