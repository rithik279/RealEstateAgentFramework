import hashlib
import hmac
import time

import pytest
from app.orchestrator.crypto import verify_meta_signature, verify_retell_signature


class TestMetaSignature:
    def test_valid_signature(self):
        raw_body = b'{"test": "data"}'
        app_secret = "my_app_secret"
        expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        header = f"sha256={expected}"
        assert verify_meta_signature(raw_body, app_secret, header) is True

    def test_invalid_signature(self):
        raw_body = b'{"test": "data"}'
        app_secret = "my_app_secret"
        assert verify_meta_signature(raw_body, app_secret, "sha256=bad") is False

    def test_missing_header(self):
        raw_body = b'{"test": "data"}'
        app_secret = "my_app_secret"
        assert verify_meta_signature(raw_body, app_secret, None) is False

    def test_missing_secret(self):
        raw_body = b'{"test": "data"}'
        assert verify_meta_signature(raw_body, "", "sha256=bad") is False

    def test_wrong_prefix(self):
        raw_body = b'{"test": "data"}'
        app_secret = "my_app_secret"
        digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        assert verify_meta_signature(raw_body, app_secret, digest) is False


class TestRetellSignature:
    def test_valid_signature(self):
        raw_body = "test payload"
        api_key = "key_test123"
        # Use current timestamp so expiry check passes (5-min window)
        timestamp_ms = str(int(time.time() * 1000))
        combined = (raw_body + timestamp_ms).encode()
        digest_hex = hmac.new(api_key.encode(), combined, hashlib.sha256).hexdigest()
        header = f"v={timestamp_ms},d={digest_hex}"
        result = verify_retell_signature(raw_body, api_key, header)
        assert result is True

    def test_invalid_signature(self):
        raw_body = "test payload"
        api_key = "key_test123"
        assert verify_retell_signature(raw_body, api_key, "v=1,d=bad") is False

    def test_expired_timestamp(self):
        raw_body = "test payload"
        api_key = "key_test123"
        old_ts = str(int((time.time() - 400) * 1000))
        mac = hmac.new(api_key.encode(), digestmod=hashlib.sha256)
        mac.update((raw_body + old_ts).encode())
        digest_hex = mac.hexdigest()
        header = f"v=1,d={digest_hex}"
        assert verify_retell_signature(raw_body, api_key, header) is False

    def test_missing_header(self):
        assert verify_retell_signature("body", "key", None) is False

    def test_missing_api_key(self):
        assert verify_retell_signature("body", "", "v=1,d=bad") is False

    def test_malformed_header(self):
        assert verify_retell_signature("body", "key", "bad_format") is False
