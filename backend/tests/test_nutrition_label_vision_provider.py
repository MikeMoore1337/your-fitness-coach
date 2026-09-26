from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from fitminiapp_api.core.config import Settings, settings
from fitminiapp_api.nutrition_label import vision


def _settings_base() -> dict[str, object]:
    return {
        "app_env": "dev",
        "app_name": "Your Fitness Coach",
        "app_debug": False,
        "secret_key": "test-secret",
        "access_token_expire_minutes": 60,
        "refresh_token_expire_days": 30,
        "database_url": "sqlite://",
        "telegram_bot_token": "test-token",
    }


def _extraction_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "source_language": "ru",
        "label_format": "ru_standard",
        "source_basis": "per_100_g",
        "serving_amount": None,
        "serving_unit": None,
    }
    values = {
        "energy_kcal": 250.0,
        "energy_kj": 1046.0,
        "protein_g": 10.0,
        "fat_g": 5.0,
        "saturated_fat_g": None,
        "trans_fat_g": None,
        "carbohydrate_g": 30.0,
        "sugars_g": 12.0,
        "added_sugars_g": None,
        "fiber_g": None,
        "salt_g": 0.5,
        "sodium_mg": 200.0,
        "cholesterol_mg": None,
    }
    payload.update(values)
    return payload


class _Response:
    status_code = 200

    def __init__(self, content: str) -> None:
        self._payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": content},
                }
            ]
        }

    def json(self):
        return self._payload


def test_groq_vision_adapter_uses_strict_schema_and_returns_canonical(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, endpoint, *, headers, json):
            captured["endpoint"] = endpoint
            captured["headers"] = headers
            captured["payload"] = json
            return _Response(json_module.dumps(_extraction_payload(), separators=(",", ":")))

    json_module = json
    monkeypatch.setattr(vision.httpx, "Client", _Client)
    adapter = vision.GroqNutritionLabelVisionAdapter(
        api_key="test-key",
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        model="qwen/qwen3.8-27b",
        proxy_url="socks5://host.docker.internal:1081",
        max_output_tokens=1536,
    )

    proposal = adapter.recognize(
        b"\x89PNG\r\n\x1a\nsynthetic",
        timeout_seconds=8,
        max_response_bytes=vision.VISION_MAX_RESPONSE_BYTES,
    )
    canonical = vision.validate_vision_proposal(
        proposal,
        provider_class=adapter.provider_class,
        model_class=adapter.model_class,
        prompt_version=adapter.prompt_version,
    )

    assert canonical.source_basis == "per_100_g"
    assert canonical.normalized_facts.energy_kcal is not None
    assert canonical.normalized_facts.energy_kcal.value == 250
    assert canonical.normalized_facts.protein_g is not None
    assert canonical.normalized_facts.protein_g.value == 10
    assert canonical.metadata.provider == "groq"
    assert canonical.requires_user_review is True

    client_kwargs = captured["client_kwargs"]
    assert isinstance(client_kwargs, dict)
    assert client_kwargs["proxy"] == "socks5://host.docker.internal:1081"
    assert client_kwargs["trust_env"] is False
    assert client_kwargs["follow_redirects"] is False

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen/qwen3.8-27b"
    assert payload["reasoning_effort"] == "none"
    assert payload["store"] is False
    assert payload["max_completion_tokens"] == 1536
    response_format = payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])

    messages = payload["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_groq_vision_adapter_does_not_expose_provider_error_body(monkeypatch) -> None:
    class _ErrorResponse:
        status_code = 403

        def json(self):
            return {"secret": "provider-body-must-not-be-consumed"}

    class _Client:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, endpoint, *, headers, json):
            del endpoint, headers, json
            return _ErrorResponse()

    monkeypatch.setattr(vision.httpx, "Client", _Client)
    adapter = vision.GroqNutritionLabelVisionAdapter(
        api_key="test-key",
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        model="qwen/qwen3.8-27b",
        proxy_url="",
        max_output_tokens=1536,
    )

    with pytest.raises(OSError, match="vision_provider_http_error"):
        adapter.recognize(
            b"\x89PNG\r\n\x1a\nsynthetic",
            timeout_seconds=8,
            max_response_bytes=vision.VISION_MAX_RESPONSE_BYTES,
        )


def test_vision_settings_fail_closed_until_zdr_is_verified() -> None:
    base = _settings_base()
    with pytest.raises(ValidationError, match="zdr_verified"):
        Settings(
            **base,
            nutrition_label_vision_enabled=True,
            nutrition_label_vision_provider="groq",
            groq_api_key="test-key",
        )

    configured = Settings(
        **base,
        nutrition_label_vision_enabled=True,
        nutrition_label_vision_provider="groq",
        nutrition_label_vision_data_policy="zdr_verified",
        nutrition_label_vision_proxy_url="socks5://host.docker.internal:1081",
        groq_api_key="test-key",
    )
    assert configured.nutrition_label_vision_model == "qwen/qwen3.8-27b"
    assert configured.nutrition_label_vision_proxy_url == "socks5://host.docker.internal:1081"

    with pytest.raises(ValidationError, match="NUTRITION_LABEL_VISION_PROXY_URL"):
        Settings(
            **base,
            nutrition_label_vision_proxy_url="socks5://user:secret@proxy.example:1080",
        )

    prod = {
        **base,
        "app_env": "prod",
        "secret_key": "p" * 40,
        "bot_internal_token": "b" * 40,
    }
    with pytest.raises(ValidationError, match="Preview"):
        Settings(
            **prod,
            nutrition_label_vision_enabled=True,
            nutrition_label_vision_provider="groq",
            nutrition_label_vision_data_policy="zdr_verified",
            groq_api_key="test-key",
        )


def test_vision_adapter_factory_is_disabled_without_verified_policy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "nutrition_label_vision_enabled", True)
    monkeypatch.setattr(settings, "nutrition_label_vision_kill_switch", False)
    monkeypatch.setattr(settings, "nutrition_label_vision_provider", "groq")
    monkeypatch.setattr(settings, "nutrition_label_vision_data_policy", "disabled")

    assert vision.build_vision_fallback_adapter() is None
