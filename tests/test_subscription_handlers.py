import unittest

from handlers.subscription import router


class SubscriptionHandlersTest(unittest.TestCase):
    def test_subscription_router_is_loaded(self):
        handlers = len(router.message.handlers) + len(router.callback_query.handlers)
        self.assertGreater(handlers, 8)


if __name__ == "__main__":
    unittest.main()
