import logging
from typing import List, Any
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
                # Note: For a background service, App-Specific Passwords should bypass this
                # but pyicloud might still trigger it for some sessions.
                return False
            return True
        except Exception as e:
            logger.error(f"iCloud login failed: {e}")
            return False

    def list_photos(self) -> List[str]:
        """
        Returns a list of unique iCloud photo identifiers.
        """
        if not self.api:
            return []
        try:
            # We list all photos in the 'All Photos' album
            return [photo.id for photo in self.api.photos.all]
        except Exception as e:
            logger.error(f"Failed to list iCloud photos: {e}")
            return []

    def download_photo(self, icloud_id: str) -> Any:
        """
        Returns a streaming response object for the given photo ID.
        """
        if not self.api:
            return None
        try:
            photo = self.api.photos.all[icloud_id]
            return photo.download() # Returns a requests-like response object with iter_content
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
            photo = self.api.photos.all[icloud_id]
            photo.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete iCloud photo {icloud_id}: {e}")
            return False
