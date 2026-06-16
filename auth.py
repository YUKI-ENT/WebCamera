import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class DeviceAuthManager:
    def __init__(self, devices_path: Path):
        self.devices_path = devices_path
        self.lock = threading.RLock()
        self.pending_tokens = {}
        self.devices_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.devices_path.exists():
            self._write_devices([])

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    def _hash(self, token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def _read_devices(self) -> list[dict]:
        try:
            data = json.loads(self.devices_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, FileNotFoundError):
            return []
        return data if isinstance(data, list) else []

    def _write_devices(self, devices: list[dict]) -> None:
        self.devices_path.write_text(json.dumps(devices, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def list_devices(self) -> list[dict]:
        with self.lock:
            devices = self._read_devices()
            return [
                {key: value for key, value in device.items() if key != 'token_hash'}
                for device in devices
            ]

    def create_registration_token(self, ttl_seconds: int = 300) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.pending_tokens[token] = time.time() + ttl_seconds
        return token

    def cleanup_pending_tokens(self) -> None:
        now = time.time()
        expired = [token for token, expires_at in self.pending_tokens.items() if expires_at < now]
        for token in expired:
            self.pending_tokens.pop(token, None)

    def register_device(self, registration_token: str, name: str) -> tuple[bool, str, dict | None]:
        with self.lock:
            self.cleanup_pending_tokens()
            expires_at = self.pending_tokens.pop(registration_token, None)
            if expires_at is None or expires_at < time.time():
                return False, '', None

            device_token = secrets.token_urlsafe(40)
            devices = self._read_devices()
            device = {
                'id': secrets.token_hex(8),
                'name': name.strip() or 'Unnamed device',
                'token_hash': self._hash(device_token),
                'created_at': self._now(),
                'last_seen_at': '',
                'enabled': True,
            }
            devices.append(device)
            self._write_devices(devices)
            public_device = {key: value for key, value in device.items() if key != 'token_hash'}
            return True, device_token, public_device

    def validate_device_token(self, token: str) -> bool:
        if not token:
            return False

        token_hash = self._hash(token)
        with self.lock:
            devices = self._read_devices()
            changed = False
            valid = False
            for device in devices:
                if device.get('enabled', True) and device.get('token_hash') == token_hash:
                    device['last_seen_at'] = self._now()
                    changed = True
                    valid = True
                    break
            if changed:
                self._write_devices(devices)
            return valid

    def delete_device(self, device_id: str) -> bool:
        with self.lock:
            devices = self._read_devices()
            new_devices = [device for device in devices if device.get('id') != device_id]
            if len(new_devices) == len(devices):
                return False
            self._write_devices(new_devices)
            return True

    def clear_devices(self) -> None:
        with self.lock:
            self._write_devices([])
