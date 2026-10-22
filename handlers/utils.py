import io

import qrcode
from aiogram.types import BufferedInputFile

from text_utils import sanitize_email  # noqa: F401  (реэкспорт для обратной совместимости)


def make_qr_image(data: str) -> BufferedInputFile:
    """Генерирует QR-код и возвращает как файл для отправки в Telegram."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return BufferedInputFile(buf.read(), filename="skrepnet_qr.png")
