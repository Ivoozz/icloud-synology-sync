import requests
import logging
import io
from typing import Generator

logger = logging.getLogger(__name__)

class GeneratorFile(io.RawIOBase):
    def __init__(self, generator: Generator[bytes, None, None]):
        self.generator = generator
        self.leftover = b""

    def readable(self):
        return True

    def readinto(self, b):
        try:
            n = len(b)
            chunk = self.leftover
            if not chunk:
                chunk = next(self.generator)
            
            if len(chunk) > n:
                b[:n] = chunk[:n]
                self.leftover = chunk[n:]
                return n
            else:
                b[:len(chunk)] = chunk
                self.leftover = b""
                return len(chunk)
        except StopIteration:
            return 0

class SynologyPhotosAPI:
    """
    Wrapper for Synology Photos API (DSM 7+).
    """
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.sid = None

    def login(self) -> bool:
        """Authenticates with the Synology DSM to obtain an SID."""
        url = f"{self.base_url}/webapi/auth.cgi"
        params = {
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "login",
            "account": self.username,
            "passwd": self.password,
            "session": "Photos",
            "format": "sid"
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                self.sid = data["data"]["sid"]
                return True
            else:
                logger.error(f"Login failed: {data.get('error')}")
                return False
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False

    def ping(self) -> bool:
        """Checks connectivity to the Synology API."""
        url = f"{self.base_url}/webapi/entry.cgi"
        params = {
            "api": "SYNO.Foto.Info",
            "version": "1",
            "method": "get",
            "_sid": self.sid
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    def upload_stream(self, generator: Generator[bytes, None, None], filename: str) -> bool:
        """Uploads a photo stream to Synology Photos."""
        if not self.sid:
            if not self.login():
                return False

        url = f"{self.base_url}/webapi/entry.cgi"
        # Synology Photos upload typically uses SYNO.Foto.Upload.Item
        # and requires multipart/form-data.
        # We wrap the generator in a file-like object for requests.
        gen_file = GeneratorFile(generator)
        
        files = {
            'file': (filename, gen_file, 'image/jpeg')
        }
        data = {
            'api': 'SYNO.Foto.Upload.Item',
            'version': '1',
            'method': 'upload',
            '_sid': self.sid,
            'dest_folder_path': '/Photos/MobileBackup/iCloudSync' # Placeholder path
        }
        
        try:
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            return response.json().get("success", False)
        except Exception as e:
            logger.error(f"Failed to upload {filename} via stream: {e}")
            return False

    def list_photos(self):
        """Lists photos from the library."""
        url = f"{self.base_url}/webapi/entry.cgi"
        params = {
            "api": "SYNO.Foto.Browse.Item",
            "version": "1",
            "method": "list",
            "offset": 0,
            "limit": 500,
            "_sid": self.sid
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                return data["data"]["list"]
            return []
        except Exception as e:
            logger.error(f"Failed to list photos: {e}")
            return []

    def delete_file(self, syno_id: str) -> bool:
        """Deletes a file by its Synology ID."""
        url = f"{self.base_url}/webapi/entry.cgi"
        params = {
            "api": "SYNO.Foto.Browse.Item",
            "version": "1",
            "method": "delete",
            "id": [syno_id],
            "_sid": self.sid
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"Failed to delete file {syno_id}: {e}")
            return False

    def file_exists(self, syno_id: str) -> bool:
        """Checks if a file exists on the NAS."""
        url = f"{self.base_url}/webapi/entry.cgi"
        params = {
            "api": "SYNO.Foto.Browse.Item",
            "version": "1",
            "method": "get",
            "id": syno_id,
            "_sid": self.sid
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"Error checking file existence for {syno_id}: {e}")
            return False
