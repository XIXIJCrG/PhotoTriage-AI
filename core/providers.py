# -*- coding: utf-8 -*-
"""Provider helpers and adapters for vision chat endpoints."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

LOCAL_PROVIDER = "local"
OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"
DEFAULT_PROVIDER_TYPE = OPENAI_COMPATIBLE_PROVIDER

LOCAL_BASE_URL = "http://127.0.0.1:8080/v1"
LOCAL_MODEL = "local-vision-model"
OPENROUTER_FREE_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_FREE_MODEL = "openrouter/free"
APP_REFERER = "https://github.com/XIXIJCrG/PhotoTriage-AI"
APP_TITLE = "PhotoTriage AI"

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
    return (provider_type or DEFAULT_PROVIDER_TYPE) == LOCAL_PROVIDER


def default_provider_settings(provider_type: str | None = None) -> tuple[str, str, str]:
    """Return (provider_type, base_url, model) for a provider preset."""
    provider = provider_type or DEFAULT_PROVIDER_TYPE
    if provider == LOCAL_PROVIDER:
        return LOCAL_PROVIDER, LOCAL_BASE_URL, LOCAL_MODEL
    return OPENAI_COMPATIBLE_PROVIDER, OPENROUTER_FREE_BASE_URL, OPENROUTER_FREE_MODEL


@dataclass
class ProviderResponse:
    """Provider 调用结果。ok=False 时 error 放中文上层可直接写入 CSV。"""

    ok: bool
    content: str = ""
    error: str = ""


@dataclass
class OpenAICompatibleVisionProvider:
    """OpenAI-compatible 视觉模型适配器。

    这个类只负责请求格式、鉴权、连接测试和 HTTP 重试；
    图片预处理、JSON 解析、结果归一化仍由 triage.py 负责。
    """

    base_url: str
    model: str
    api_key: str | None = None
    provider_type: str | None = None
    api_url: str | None = None
    timeout: float = 180
    max_tokens: int = 1800
    temperature: float = 0.3
    disable_thinking: bool = True
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    retryable_http_status: frozenset[int] = frozenset({429, 500, 502, 503, 504})
    fatal_http_status: frozenset[int] = frozenset({400, 401, 403, 404})

    def completions_url(self) -> str:
        return self.api_url or chat_completions_url(self.base_url)

    def headers(self) -> dict[str, str] | None:
        headers = auth_headers(self.api_key) or {}
        if "openrouter.ai" in normalize_base_url(self.base_url).lower():
            headers.setdefault("HTTP-Referer", APP_REFERER)
            headers.setdefault("X-Title", APP_TITLE)
        return headers or None

    def check_connection(self, timeout: float = 5) -> tuple[bool, str]:
        """检查 `/models` 是否可用,返回 (ok, model_or_error)。"""
        url = models_url(self.base_url or self.api_url or "")
        headers = self.headers()
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            data = r.json()
            models = (data.get("data") or data.get("models") or [])
            if not models:
                return False, "未返回模型列表"
            names = [m.get("id") or m.get("name") for m in models if isinstance(m, dict)]
            names = [n for n in names if n]
            if self.model and self.model in names:
                return True, self.model
            return True, names[0] if names else "unknown"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"

    def analyze_encoded_image(self, image_b64: str, prompt: str) -> ProviderResponse:
        """发送已经缩放/编码后的图片,返回模型原始文本。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.disable_thinking and is_local_provider(self.provider_type):
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        headers = self.headers()
        last_err: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(self.completions_url(), json=payload, headers=headers, timeout=self.timeout)
                if r.status_code != 200:
                    last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                    if r.status_code in self.fatal_http_status:
                        return ProviderResponse(False, error=last_err)
                    if r.status_code not in self.retryable_http_status:
                        return ProviderResponse(False, error=last_err)
                    if attempt < self.max_retries:
                        self._sleep_before_retry(r, attempt)
                        continue
                    return ProviderResponse(False, error=last_err)
                content = r.json()["choices"][0]["message"]["content"]
                return ProviderResponse(True, content=content)
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(f"模型服务连接失败: {e}") from e
            except requests.exceptions.Timeout:
                last_err = f"超时 (>{self.timeout}s)"
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
        return ProviderResponse(False, error=last_err or "未知错误")

    def _sleep_before_retry(self, response: requests.Response, attempt: int) -> None:
        retry_after = response.headers.get("Retry-After") if response.headers else None
        try:
            delay = float(retry_after) if retry_after else self.retry_backoff_seconds * (2 ** attempt)
        except ValueError:
            delay = self.retry_backoff_seconds * (2 ** attempt)
        time.sleep(max(0.0, min(delay, 30.0)))
