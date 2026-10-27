import warnings

import pytest
from authlib.deprecate import AuthlibDeprecationWarning

with warnings.catch_warnings():
    warnings.simplefilter("ignore", AuthlibDeprecationWarning)
    from authlib.jose import JsonWebSignature
    from authlib.jose.errors import BadSignatureError


@pytest.mark.parametrize("key", [None, b"local-test-key-for-jws-validation"])
def test_json_jws_rejects_empty_signatures(key):
    with pytest.raises(BadSignatureError):
        JsonWebSignature().deserialize_json({"payload": "dGVzdA", "signatures": []}, key)


def test_json_jws_accepts_valid_signature():
    key = b"local-test-key-for-jws-validation"
    jws = JsonWebSignature()
    token = jws.serialize_json([{"protected": {"alg": "HS256"}}], b"test", key)
    assert jws.deserialize_json(token, key)["payload"] == b"test"
