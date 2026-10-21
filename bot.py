
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_KEY = os.getenv("NUMBERPANEL_API_KEY", "")
GROUP_ID = os.getenv("GROUP_ID", "")
BASE_URL = os.getenv(
    "NUMBERPANEL_BASE_URL", "https://numberpanel.tech"
).rstrip("/")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/challeh61")
HELP_URL = os.getenv("HELP_URL", "https://t.me/bluebear10")

SERVICES_PATH = "/api/services"
COUNTRIES_PATH = "/api/countries"
NUMBERS_PATH = "/api/my_numbers"
OTP_HISTORY_PATH = "/api/my_otps"


def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💎 GET NUMBER", callback_data="services"
        )],
        [
            InlineKeyboardButton(
                "🌍 COUNTRIES", callback_data="countries"
            ),
            InlineKeyboardButton(
                "👑 MY HISTORY", callback_data="history"
            ),
        ],
        [
            InlineKeyboardButton("📢 CHANNEL", url=CHANNEL_URL),
            InlineKeyboardButton("💬 HELP", url=HELP_URL),
        ],
    ])


def back_button():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ BACK", callback_data="home")
    ]])


async def api_request(method, path, **kwargs):
    headers = {"Accept": "application/json"}

    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.request(
            method,
            BASE_URL + path,
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()


def get_items(data, *keys):
    """Accept common JSON list response formats."""
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "╭━━━ 💎 PREMIUM NUMBER BOT ━━━╮\n"
        "┃\n"
        "┃ 👑 Welcome!\n"
        "┃ ⚡ Fast service menu\n"
        "┃ 🌍 Available services & countries\n"
        "┃ 🔐 Secure configuration\n"
        "┃\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "👇 Select an option:"
    )

    await update.effective_message.reply_text(
        text, reply_markup=menu()
    )


async def show_services(query):
    data = await api_request("GET", SERVICES_PATH)
    services = get_items(data, "services", "data", "results")

    keyboard = []

    for item in services[:50]:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", ""))
        key = str(item.get("key", item.get("id", item.get("code", ""))))
        count = item.get("count", 0)

        if name and key:
            keyboard.append([InlineKeyboardButton(
                f"📱 {name[:30]} | 🔢 {count}",
                callback_data=f"service:{key[:40]}",
            )])

    keyboard.append([
        InlineKeyboardButton("⬅️ BACK", callback_data="home")
    ])

    if not keyboard or len(keyboard) == 1:
        await query.edit_message_text(
            "⚠️ No services found.\n"
            "Check the API response and account access.",
            reply_markup=back_button(),
        )
        return

    await query.edit_message_text(
        "💎 SELECT SERVICE\n\nChoose a service:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_countries(query, service=None):
    path = COUNTRIES_PATH

    if service:
        path += "?service=" + service

    data = await api_request("GET", path)
    countries = get_items(data, "countries", "data", "results")

    keyboard = []

    for country in countries[:50]:
        if not isinstance(country, dict):
            continue

        name = str(country.get(
            "name", country.get("country", "")
        ))
        code = str(country.get(
            "code", country.get("key", country.get("id", ""))
        ))

        if name and code:
            keyboard.append([InlineKeyboardButton(
                f"🌍 {name[:35]}",
                callback_data=f"country:{service or 'random'}:{code[:25]}",
            )])

    keyboard.append([
        InlineKeyboardButton("🎲 Random country",
                             callback_data=f"country:{service or 'random'}:random")
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ BACK", callback_data="home")
    ])

    await query.edit_message_text(
        "🌍 SELECT COUNTRY",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_history(query):
    data = await api_request("GET", OTP_HISTORY_PATH + "?limit=20")
    items = get_items(data, "otps", "history", "data", "results")

    if not items:
        data = await api_request("GET", NUMBERS_PATH)
        items = get_items(data, "numbers", "data", "results")

    if not items:
        await query.edit_message_text(
            "📭 No history or active numbers were returned.",
            reply_markup=back_button(),
        )
        return

    lines = ["👑 YOUR HISTORY\n"]

    for item in items[:15]:
        if not isinstance(item, dict):
            continue

        number = str(item.get("number", "Unknown"))
        service = str(item.get("service", "Unknown"))
        status = str(item.get("status", "Unknown"))

        lines.append(
            f"📱 {number[:35]}\n"
            f"💎 {service[:25]} | {status[:25]}\n"
        )

    await query.edit_message_text(
        "\n".join(lines)[:4000],
        reply_markup=back_button(),
    )


async def request_number(query, service, country):
    """Request a number through the documented provider endpoint."""
    payload = {"service": service, "country": country}

    data = await api_request(
        "POST", "/api/request_number", json=payload
    )

    if not isinstance(data, dict):
        raise ValueError("Unexpected number API response")

    number = data.get("number")
    if not number:
        message = str(data.get("message", data.get("error", "Unknown error")))
        await query.edit_message_text(
            f"⚠️ Number request failed.\n{message[:500]}",
            reply_markup=back_button(),
        )
        return

    number = str(number)
    user_text = (
        "💎 NUMBER RESPONSE\n\n"
        f"📱 Service: {service}\n"
        f"☎️ Number: {number}\n\n"
        "Use only for accounts and verification workflows "
        "you are authorized to test."
    )

    await query.edit_message_text(
        user_text, reply_markup=back_button()
    )

    # Group receives a masked number, not the full number.
    if GROUP_ID:
        masked = number
        if len(number) > 5:
            masked = number[:5] + "*" * (len(number) - 5)

        try:
            await query.get_bot().send_message(
                chat_id=GROUP_ID,
                text=(
                    "💎 NEW NUMBER NOTICE\n\n"
                    f"📱 Service: {service}\n"
                    f"☎️ Number: {masked}"
                ),
            )
        except Exception:
            log.exception("Could not send group notice")


async def handle_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()
    action = query.data

    try:
        if action == "home":
            await query.edit_message_text(
                "💎 PREMIUM NUMBER BOT\n\nChoose an option:",
                reply_markup=menu(),
            )

        elif action == "services":
            await show_services(query)

        elif action == "countries":
            await show_countries(query)

        elif action == "history":
            await show_history(query)

        elif action.startswith("service:"):
            service = action.split(":", 1)[1]
            context.user_data["selected_service"] = service
            await show_countries(query, service)

        elif action.startswith("country:"):
            _, service, country = action.split(":", 2)

            if service == "random":
                service = context.user_data.get("selected_service")

            if not service:
                await query.edit_message_text(
                    "⚠️ Select a service first.",
                    reply_markup=back_button(),
                )
                return

            await request_number(query, service, country)

    except httpx.HTTPStatusError as exc:
        log.warning("API returned HTTP %s", exc.response.status_code)
        await query.edit_message_text(
            f"⚠️ Provider API returned HTTP "
            f"{exc.response.status_code}.\n"
            "Check the official API documentation and credentials.",
            reply_markup=back_button(),
        )

    except Exception:
        log.exception("Button handler failed")
        await query.edit_message_text(
            "⚠️ Something went wrong.\n"
            "Check the Termux log and API response format.",
            reply_markup=back_button(),
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))

    log.info("Premium Number Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
