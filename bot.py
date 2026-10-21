import os
import logging
import httpx

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("8677231120:AAHU1SJm13ry0E0Pby2yRX8EleH6gPty-BM", "")
API_KEY = os.getenv("np_live_7yqWlo5XyEArNl7f86kzjEn-wWgJ338qmoVGOykNZqY", "")
BASE_URL = os.getenv(
    "NUMBERPANEL_BASE_URL", "https://numberpanel.tech"
).rstrip("/")
GROUP_ID = os.getenv("-1004470205927", "")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/challeh61")
HELP_URL = os.getenv("HELP_URL", "https://t.me/@bluebear10")

# Configure these from the official NumberPanel API docs.
SERVICES_PATH = os.getenv(
    "NUMBERPANEL_SERVICES_PATH", "/api/services"
)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💎 𝐆𝐄𝐓 𝐍𝐔𝐌𝐁𝐄𝐑",
            callback_data="services"
        )],
        [
            InlineKeyboardButton(
                "👑 𝐌𝐘 𝐇𝐈𝐒𝐓𝐎𝐑𝐘",
                callback_data="history"
            ),
            InlineKeyboardButton(
                "🌍 𝐂𝐎𝐔𝐍𝐓𝐑𝐘",
                callback_data="countries"
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 𝐂𝐇𝐀𝐍𝐍𝐄𝐋",
                url=CHANNEL_URL
            ),
            InlineKeyboardButton(
                "💬 𝐇𝐄𝐋𝐏",
                url=HELP_URL
            ),
        ],
    ])


def back_menu():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ 𝐁𝐀𝐂𝐊", callback_data="home")
    ]])


async def api_get(path):
    headers = {
        # Confirm the required auth format in provider docs.
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            BASE_URL + path,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "╭━━━ 💎 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐍𝐔𝐌𝐁𝐄𝐑 𝐁𝐎𝐓 ━━━╮\n"
        "┃\n"
        "┃ 👑 Welcome to Premium Number Bot\n"
        "┃ ⚡ Fast & Easy Service\n"
        "┃ 🌍 Multiple Services\n"
        "┃ 🔒 Secure API Configuration\n"
        "┃\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "👇 Select an option:"
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=main_menu(),
    )


async def show_services(query):
    data = await api_get(SERVICES_PATH)

    # Adapt this parser to the actual provider response.
    if isinstance(data, list):
        services = data
    elif isinstance(data, dict):
        services = data.get("services", [])
    else:
        services = []

    keyboard = []

    for service in services[:50]:
        if not isinstance(service, dict):
            continue

        name = str(service.get("name", ""))
        code = str(service.get("id", service.get("code", "")))

        if name and code:
            keyboard.append([
                InlineKeyboardButton(
                    f"📱 {name[:45]}",
                    callback_data=f"service:{code[:35]}",
                )
            ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Back", callback_data="home")
    ])

    if not keyboard or len(keyboard) == 1:
        await query.edit_message_text(
            "⚠️ No services found. Check API documentation "
            "and credentials.",
            reply_markup=back_menu(),
        )
        return

    await query.edit_message_text(
        "💎 𝐒𝐄𝐋𝐄𝐂𝐓 𝐒𝐄𝐑𝐕𝐈𝐂𝐄\n\n"
        "Choose a service from the list:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    if query.data == "home":
        await query.edit_message_text(
            "💎 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐍𝐔𝐌𝐁𝐄𝐑 𝐁𝐎𝐓\n\n"
            "Choose an option:",
            reply_markup=main_menu(),
        )
        return

    if query.data == "services":
        try:
            await show_services(query)
        except httpx.HTTPStatusError as exc:
            log.warning("Provider returned HTTP %s",
                        exc.response.status_code)
            await query.edit_message_text(
                "⚠️ API request failed. Verify endpoint "
                "and authentication in the official docs.",
                reply_markup=back_menu(),
            )
        except Exception:
            log.exception("Could not load services")
            await query.edit_message_text(
                "⚠️ Could not load services. Check API settings.",
                reply_markup=back_menu(),
            )
        return

    if query.data == "countries":
        await query.edit_message_text(
            "🌍 Country selection requires the provider's "
            "official country-list endpoint.",
            reply_markup=back_menu(),
        )
        return

    if query.data == "history":
        await query.edit_message_text(
            "👑 Your order history is not configured yet.",
            reply_markup=back_menu(),
        )
        return

    if query.data.startswith("service:"):
        service_code = query.data.split(":", 1)[1]
        await query.edit_message_text(
            f"💎 Selected service: {service_code}\n\n"
            "Number ordering is not enabled yet. The official "
            "order endpoint and required request fields must "
            "be configured before purchases can be made.",
            reply_markup=back_menu(),
        )


async def post_group_notice(
    context: ContextTypes.DEFAULT_TYPE,
    service_name: str,
    phone_number: str,
):
    """Post an authorized number notice to the configured group."""
    if not GROUP_ID:
        return

    text = (
        "💎 𝐍𝐄𝐖 𝐍𝐔𝐌𝐁𝐄𝐑\n\n"
        f"📱 Service: {service_name}\n"
        f"☎️ Number: {phone_number}\n\n"
        "🔐 Use only for authorized verification."
    )

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    if not API_KEY:
        raise RuntimeError("Missing NUMBERPANEL_API_KEY")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))

    log.info("Premium Number Bot is starting")
    app.run_polling()


if __name__ == "__main__":
    main()
