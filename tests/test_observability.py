import unittest

from observability import capture_exception, init_sentry, scrub_event


class ScrubEventTest(unittest.TestCase):
    def test_removes_request_body_and_headers(self):
        event = {
            "request": {
                "url": "https://example.test/api/miniapp",
                "data": '{"init_data": "query_id=AAA&hash=BBB"}',
                "headers": {"Authorization": "Bearer secret"},
                "cookies": {"session": "abc"},
                "query_string": "init_data=query_id%3DAAA",
            }
        }
        result = scrub_event(event, {})
        request = result["request"]
        for key in ("data", "headers", "cookies", "query_string"):
            self.assertNotIn(key, request)

    def test_masks_bot_token_in_url(self):
        event = {
            "request": {"url": "https://api.telegram.org/bot123456:AAHsecret/sendMessage"}
        }
        result = scrub_event(event, {})
        self.assertNotIn("AAHsecret", result["request"]["url"])
        self.assertIn("/bot<token>", result["request"]["url"])

    def test_masks_init_data_in_query(self):
        event = {
            "request": {
                "url": "https://example.test/v3?init_data=user%3D1%26hash%3Dabcdef&lang=ru"
            }
        }
        result = scrub_event(event, {})
        url = result["request"]["url"]
        self.assertNotIn("abcdef", url)
        self.assertIn("lang=ru", url)

    def test_masks_sensitive_extra_and_breadcrumbs(self):
        event = {
            "extra": {"init_data": "secret", "admin_token": "secret", "note": "ok"},
            "breadcrumbs": {
                "values": [
                    {
                        "message": "GET https://example.test/x?token=abc",
                        "data": {
                            "url": "https://example.test/x?token=abc",
                            "headers": {"Cookie": "sid=1"},
                            "cookies": {"sid": "1"},
                        },
                    }
                ]
            },
        }
        result = scrub_event(event, {})
        self.assertEqual(result["extra"]["init_data"], "[Filtered]")
        self.assertEqual(result["extra"]["admin_token"], "[Filtered]")
        self.assertEqual(result["extra"]["note"], "ok")
        breadcrumb = result["breadcrumbs"]["values"][0]
        self.assertNotIn("headers", breadcrumb["data"])
        self.assertNotIn("cookies", breadcrumb["data"])
        self.assertNotIn("abc", breadcrumb["data"]["url"])

    def test_removes_user_personal_fields(self):
        event = {"user": {"id": "1", "username": "user", "email": "a@b.c", "ip_address": "1.2.3.4"}}
        result = scrub_event(event, {})
        self.assertEqual(result["user"], {"id": "1"})

    def test_handles_event_without_request(self):
        event = {"message": "boom"}
        self.assertEqual(scrub_event(event, {}), event)


class SentryInitTest(unittest.TestCase):
    def test_disabled_without_dsn(self):
        self.assertFalse(init_sentry("test", dsn=""))
        self.assertFalse(init_sentry("test", dsn="   "))

    def test_capture_is_noop_without_init(self):
        self.assertFalse(capture_exception(RuntimeError("test")))


if __name__ == "__main__":
    unittest.main()
