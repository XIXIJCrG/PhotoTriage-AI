import unittest
from unittest.mock import Mock, patch

from core.providers import (
    DEFAULT_PROVIDER_TYPE,
    OPENAI_COMPATIBLE_PROVIDER,
    OPENROUTER_FREE_BASE_URL,
    OPENROUTER_FREE_MODEL,
    OpenAICompatibleVisionProvider,
    auth_headers,
    chat_completions_url,
    default_provider_settings,
    models_url,
    normalize_base_url,
)


class TestProviderUrls(unittest.TestCase):
    def test_normalize_full_chat_endpoint(self):
        self.assertEqual(
            normalize_base_url("https://example.com/v1/chat/completions"),
            "https://example.com/v1",
        )

    def test_chat_completions_url(self):
        self.assertEqual(
            chat_completions_url("https://example.com/v1"),
            "https://example.com/v1/chat/completions",
        )

    def test_models_url_from_full_endpoint(self):
        self.assertEqual(
            models_url("https://example.com/v1/chat/completions"),
            "https://example.com/v1/models",
        )

    def test_auth_headers(self):
        self.assertEqual(auth_headers("sk-test"), {"Authorization": "Bearer sk-test"})
        self.assertIsNone(auth_headers(""))

    def test_default_provider_is_free_cloud_preset(self):
        provider, base_url, model = default_provider_settings()
        self.assertEqual(DEFAULT_PROVIDER_TYPE, OPENAI_COMPATIBLE_PROVIDER)
        self.assertEqual(provider, OPENAI_COMPATIBLE_PROVIDER)
        self.assertEqual(base_url, OPENROUTER_FREE_BASE_URL)
        self.assertEqual(model, OPENROUTER_FREE_MODEL)


class TestOpenAICompatibleVisionProvider(unittest.TestCase):
    def test_analyze_encoded_image_does_not_retry_fatal_http_status(self):
        """401/403 等鉴权错误不应盲目重试,避免浪费额度和等待。"""
        resp = Mock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        resp.headers = {}

        provider = OpenAICompatibleVisionProvider(
            base_url="https://example.com/v1",
            model="vision-model",
            max_retries=2,
        )
        with patch("core.providers.requests.post", return_value=resp) as post:
            result = provider.analyze_encoded_image("abc", "prompt")

        self.assertFalse(result.ok)
        self.assertIn("HTTP 401", result.error)
        self.assertEqual(post.call_count, 1)

    def test_analyze_encoded_image_adds_local_thinking_flag(self):
        """本地 provider 保留 disable thinking 参数,云端 provider 不加。"""
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "{}"}}]}

        provider = OpenAICompatibleVisionProvider(
            base_url="http://127.0.0.1:8080/v1",
            model="local-model",
            provider_type="local",
        )
        with patch("core.providers.requests.post", return_value=resp) as post:
            result = provider.analyze_encoded_image("abc", "prompt")

        self.assertTrue(result.ok)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})

    def test_check_connection_returns_requested_model_when_present(self):
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"data": [{"id": "a"}, {"id": "target"}]}

        provider = OpenAICompatibleVisionProvider(
            base_url="https://example.com/v1",
            model="target",
        )
        with patch("core.providers.requests.get", return_value=resp):
            ok, info = provider.check_connection()

        self.assertTrue(ok)
        self.assertEqual(info, "target")

    def test_openrouter_headers_include_app_identity(self):
        provider = OpenAICompatibleVisionProvider(
            base_url="https://openrouter.ai/api/v1",
            model="openrouter/free",
            api_key="sk-test",
        )
        headers = provider.headers()
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertIn("github.com/XIXIJCrG/PhotoTriage-AI", headers["HTTP-Referer"])
        self.assertEqual(headers["X-Title"], "PhotoTriage AI")


if __name__ == "__main__":
    unittest.main()
