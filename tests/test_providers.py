import unittest

from core.providers import auth_headers, chat_completions_url, models_url, normalize_base_url


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


if __name__ == "__main__":
    unittest.main()
