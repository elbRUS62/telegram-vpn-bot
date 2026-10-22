import unittest

from handlers.admin import router


class AdminHandlersTest(unittest.TestCase):
    def test_admin_router_is_loaded(self):
        handlers = len(router.message.handlers) + len(router.callback_query.handlers)
        self.assertGreater(handlers, 10)


if __name__ == "__main__":
    unittest.main()
