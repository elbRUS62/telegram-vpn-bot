import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from handlers.menu import show_main_menu


class StartPhotoTest(unittest.IsolatedAsyncioTestCase):
    async def test_welcome_uses_photo(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=123, first_name="Test"),
            answer_photo=AsyncMock(),
            answer=AsyncMock(),
        )

        with (
            patch("database.get_user", new=AsyncMock(return_value=None)),
            patch("handlers.menu.main_inline_menu", return_value="keyboard"),
            patch("handlers.menu.is_admin_user", return_value=False),
        ):
            await show_main_menu(message, with_photo=True)

        message.answer_photo.assert_awaited_once()
        message.answer.assert_not_called()

    async def test_menu_without_photo_uses_text(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=123, first_name="Test"),
            answer_photo=AsyncMock(),
            answer=AsyncMock(),
        )

        with (
            patch("database.get_user", new=AsyncMock(return_value=None)),
            patch("handlers.menu.main_inline_menu", return_value="keyboard"),
            patch("handlers.menu.is_admin_user", return_value=False),
        ):
            await show_main_menu(message, with_photo=False)

        message.answer_photo.assert_not_called()
        message.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
