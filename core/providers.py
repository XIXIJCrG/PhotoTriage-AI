# -*- coding: utf-8 -*-
"""Provider helpers for OpenAI-compatible vision chat endpoints."""
from __future__ import annotations

LOCAL_PROVIDER = "local"
OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"

SUPPORTED_PROVIDERS = {
    LOCAL_PROVIDER: "Local llama.cpp",
    OPENAI_COMPATIBLE_PROVIDER: "OpenAI Compatible API",
}


def normalize_base_url(value: str | None) -> str:
    """Return a provider base URL ending before `/chat/completions`."""
    url = (value or "").strip().rstrip("/")
    if url.endswith("/v1/chat/completions"):
        return url[: -len("/chat/completions")]
    if url.endswith("/chat/completions"):
        return url[: -len("/chat/completions")]
    return url


def chat_completions_url(base_url: str) -> str:
    url = normalize_base_url(base_url)
    if not url:
        return ""
    return f"{url}/chat/completions"


def models_url(base_url: str) -> str:
    url = normalize_base_url(base_url)
    if not url:
        return ""
    return f"{url}/models"


def auth_headers(api_key: str | None) -> dict[str, str] | None:
    key = (api_key or "").strip()
    if not key:
        return None
    return {"Authorization": f"Bearer {key}"}


def is_local_provider(provider_type: str | None) -> bool:
    return (provider_type or LOCAL_PROVIDER) == LOCAL_PROVIDER
