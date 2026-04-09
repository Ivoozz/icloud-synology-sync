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

    def _request(self, method: str, path: str, *, params=None, data=None, files=None, timeout=10):
        url = f"{self.base_url}{path}"
        request_kwargs = {"params": params, "data": data, "files": files, "timeout": timeout}
        request_kwargs = {key: value for key, value in request_kwargs.items() if value is not None}
        return requests.request(method, url, **request_kwargs)

    def _api_params(self, api, version, method, **extra):
        params = {
            "api": api,
            "version": str(version),
            "method": method,
            "_sid": self.sid,
        }
        params.update(extra)
        return params

    def _ensure_login(self) -> bool:
        if self.sid:
            return True
        return self.login()

    def login(self) -> bool:
        """Authenticates with the Synology DSM to obtain an SID."""
        try:
            response = self._request(
                "GET",
                "/webapi/auth.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "version": "3",
                    "method": "login",
                    "account": self.username,
                    "passwd": self.password,
                    "session": "Photos",
                    "format": "sid",
                },
            )
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
        try:
            if not self._ensure_login():
                return False
            response = self._request(
                "GET",
                "/webapi/entry.cgi",
                params=self._api_params("SYNO.Foto.Info", 1, "get"),
            )
            response.raise_for_status()
            data = response.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    def upload_stream(self, generator: Generator[bytes, None, None], filename: str) -> bool:
        """Uploads a photo stream to Synology Photos."""
        if not self._ensure_login():
            return False

        url = f"{self.base_url}/webapi/entry.cgi"
        gen_file = GeneratorFile(generator)

        files = {
            'file': (filename, gen_file, 'image/jpeg')
        }
        data = {
            'api': 'SYNO.Foto.Upload.Item',
            'version': '1',
            'method': 'upload',
            '_sid': self.sid,
            'dest_folder_path': '/Photos/MobileBackup/iCloudSync'
        }

        try:
            response = requests.post(url, data=data, files=files, timeout=60)
            if response.status_code == 401:
                self.sid = None
                if not self.login():
                    return False
                data['_sid'] = self.sid
                response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            result = response.json()
            if not result.get("success", False):
                logger.error(f"Synology upload rejected for {filename}: {result}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to upload {filename} via stream: {e}")
            return False

    def list_photos(self):
        """Lists photos from the library."""
        try:
            if not self._ensure_login():
                return []
            response = self._request(
                "GET",
                "/webapi/entry.cgi",
                params=self._api_params("SYNO.Foto.Browse.Item", 1, "list", offset=0, limit=500),
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                return data.get("data", {}).get("list", [])
            return []
        except Exception as e:
            logger.error(f"Failed to list photos: {e}")
            return []

    def delete_file(self, syno_id: str) -> bool:
        """Deletes a file by its Synology ID."""
        try:
            if not self._ensure_login():
                return False
            response = self._request(
                "GET",
                "/webapi/entry.cgi",
                params=self._api_params("SYNO.Foto.Browse.Item", 1, "delete", id=[syno_id]),
            )
            response.raise_for_status()
            data = response.json()
            success = data.get("success", False)
            if not success:
                logger.error(f"Synology delete rejected for {syno_id}: {data}")
            return success
        except Exception as e:
            logger.error(f"Failed to delete file {syno_id}: {e}")
            return False

    def file_exists(self, syno_id: str) -> bool:
        """Checks if a file exists on the NAS."""
        try:
            if not self._ensure_login():
                return False
            response = self._request(
                "GET",
                "/webapi/entry.cgi",
                params=self._api_params("SYNO.Foto.Browse.Item", 1, "get", id=syno_id),
            )
            response.raise_for_status()
            data = response.json()
            return data.get("success", False)
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", None) == 404:
                return False
            logger.error(f"Error checking file existence for {syno_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking file existence for {syno_id}: {e}")
            return False
