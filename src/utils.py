import os
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject
from aiogram.types import Message

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
DB_NAME = os.environ["DB_NAME"]
RAW_ADMIN_IDS = os.environ["ADMIN_IDS"]
YOUTUBE_API_TOKEN = os.environ["YOUTUBE_API_TOKEN"]

none_user_id_message = "Не удалось идентифицировать пользователя. Попробуйте снова."

def get_admin_ids() -> frozenset[int]:
    try:
        admin_ids = frozenset(
            int(admin_id.strip())
            for admin_id in RAW_ADMIN_IDS.split(",")
            if admin_id.strip()
        )
    except ValueError as error:
        raise RuntimeError("ADMIN_IDS must contain comma-separated Telegram user IDs.") from error

    if not admin_ids:
        raise RuntimeError("ADMIN_IDS must contain at least one Telegram user ID.")

    return admin_ids


ADMIN_IDS = get_admin_ids()
ADMIN_TAG = os.environ["ADMIN_TAG"]
CEO = os.environ["CEO"]
RULES_DIR = Path(__file__).parent / "rules"

def get_user_id(message: Message) -> int | None:
    if message.from_user is not None:
        return message.from_user.id
    return None

async def send_message(text_list, message: Message) -> None:
    await message.answer('\n'.join(text_list), disable_web_page_preview=True, disable_notification=True)

def load_text(name: str, **values: str) -> str:
    return (RULES_DIR / f"{name}.txt").read_text(encoding="utf-8").format(**values)

async def send_to_users(
    user_ids: list[int],
    text: str,
    message: Message,
) -> tuple[int, int]:
    sent_count = 0
    failed_count = 0
    for user_id in user_ids:
        try:
            await message.bot.send_message(user_id, text, disable_notification=True) # type: ignore
        except TelegramAPIError:
            failed_count += 1
            continue
        sent_count += 1

    return sent_count, failed_count


def get_message_text(command: CommandObject) -> str | None:
    if command.args is None:
        return None

    text = command.args.strip()
    if not text or len(text) > 4096:
        return None

    return text
