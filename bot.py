
import os
import logging
import httpx

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_KEY = os.getenv("NUMBERPANEL_API_KEY", "")
GROUP_ID = os.getenv("GROUP_ID", "")
BASE_URL = os.getenv(
    "NUMBERPANEL_BASE_URL", "https://numberpanel.tech"
).rstrip("/")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/challeh61")
HELP_URL = os.getenv("HELP_URL", "https://t.me/bluebear10")

# Verify these endpoints against NumberPanel's current API docs.
SERVICES_PATH = "/api/services"
COUNTRIES_PATH = "/api/countries"
ORDER_PATH = "/api/request_number"
POLL_PATH = "/api/latest_otp"
HISTORY_PATH = "/api/my_numbers"


def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 GET NUMBER", callback_data="services")],
        [
            InlineKeyboardButton("🌍 COUNTRY", callback_data="countries"),
            InlineKeyboardButton("👑 HISTORY", callback_data="history"),
        ],
        [InlineKeyboardButton("🔄 POLL OTP", callback_data="poll")],
        [
            InlineKeyboardButton("📢 CHANNEL", url=CHANNEL_URL),
            InlineKeyboardButton("💬 HELP", url=HELP_URL),
        ],
    ])


def back_keyboard(target="home"):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ BACK", callback_data=target)
    ]])


async def api_request(method, path, **kwargs):
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.request(
            method, BASE_URL + path, headers=headers, **kwargs
        )
        response.raise_for_status()
        return response.json()


def get_list(data, *keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "╭━━ 💎 PREMIUM NUMBER BOT ━━╮\n"
        "┃ 👑 Welcome!\n"
        "┃ 📱 Select service\n"
        "┃ 🌍 Select country\n"
        "┃ 🔄 Check OTP\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "👇 Choose an option:",
        reply_markup=home_keyboard(),
    )


async def show_services(query):
    data = await api_request("GET", SERVICES_PATH)
    services = get_list(data, "services", "data", "results")
    buttons = []

    for item in services[:50]:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", ""))
        key = str(item.get("key") or item.get("id") or item.get("code") or "")
        count = item.get("count", 0)

        if name and key:
            buttons.append([InlineKeyboardButton(
                f"📱 {name[:28]} | 🔢 {count}",
                callback_data=f"svc:{key[:35]}",
            )])

    buttons.append([InlineKeyboardButton("🏠 HOME", callback_data="home")])

    if len(buttons) == 1:
        await query.edit_message_text(
            "⚠️ No services found.",
            reply_markup=back_keyboard(),
        )
        return

    await query.edit_message_text(
        "💎 SELECT SERVICE",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def show_countries(query, service=None):
    data = await api_request("GET", COUNTRIES_PATH)
    countries = get_list(data, "countries", "data", "results")
    buttons = []

    for item in countries[:50]:
        if not isinstance(item, dict):
            continue

        name = str(
            item.get("name") or item.get("country") or item.get("title") or ""
        )
        code = str(
            item.get("code") or item.get("key")
            or item.get("id") or item.get("country_code") or ""
        )

        if name and code and service:
            buttons.append([InlineKeyboardButton(
                f"🌍 {name[:30]}",
                callback_data=f"cty:{service[:18]}:{code[:18]}",
            )])

    buttons.append([
        InlineKeyboardButton("⬅️ SERVICES", callback_data="services")
    ])

    if len(buttons) == 1:
        await query.edit_message_text(
            "⚠️ Country list পাওয়া যায়নি। API endpoint যাচাই করো।",
            reply_markup=back_keyboard(),
        )
        return

    await query.edit_message_text(
        "🌍 SELECT COUNTRY",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def order_number(query, context, service, country):
    # Confirm the real endpoint and required fields before ordering.
    data = await api_request(
        "POST",
        ORDER_PATH,
        json={"service": service, "country": country},
    )

    if not isinstance(data, dict):
        raise ValueError("Unexpected order response")

    number = data.get("number")
    if not number:
        msg = data.get("message") or data.get("error") or "No number returned"
        await query.edit_message_text(
            f"⚠️ Order failed: {str(msg)[:300]}",
            reply_markup=back_keyboard(),
        )
        return

    number = str(number)
    context.user_data["active_number"] = number
    context.user_data["active_service"] = service

    await query.edit_message_text(
        "💎 NUMBER RECEIVED\n\n"
        f"📱 Service: {service}\n"
        f"☎️ Number: {number}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 POLL OTP", callback_data="poll")],
            [InlineKeyboardButton("🏠 HOME", callback_data="home")],
        ]),
    )

    if GROUP_ID:
        masked = number[:5] + "*" * max(0, len(number) - 5)
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=f"💎 NEW NUMBER\n📱 {service}\n☎️ {masked}",
            )
        except Exception:
            log.exception("Group notification failed")


async def poll_otp(query, context):
    number = context.user_data.get("active_number")
    if not number:
        await query.edit_message_text(
            "⚠️ আগে একটি নম্বর অর্ডার করো।",
            reply_markup=back_keyboard(),
        )
        return

    data = await api_request(
        "GET", POLL_PATH, params={"number": number}
    )

    if not isinstance(data, dict):
        raise ValueError("Unexpected OTP response")

    otp = data.get("otp") or data.get("code")
    sms = data.get("sms")

    if otp or sms:
        message = (
            "✅ OTP RECEIVED!\n\n"
            f"📱 Number: {number}\n"
            f"🔐 OTP: {otp or sms}"
        )
    else:
        message = (
            "⏳ OTP এখনো আসেনি।\n\n"
            f"📱 Number: {number}\n"
            "কিছুক্ষণ পর আবার Poll করো।"
        )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 POLL AGAIN", callback_data="poll")],
            [InlineKeyboardButton("🏠 HOME", callback_data="home")],
        ]),
    )


async def show_history(query):
    data = await api_request("GET", HISTORY_PATH)
    items = get_list(data, "numbers", "data", "results")

    if not items:
        await query.edit_message_text(
            "📭 কোনো History পাওয়া যায়নি।",
            reply_markup=back_keyboard(),
        )
        return

    lines = ["👑 MY HISTORY\n"]
    for item in items[:15]:
        if isinstance(item, dict):
            lines.append(
                f"📱 {item.get('number', 'Unknown')}\n"
                f"💎 {item.get('service', 'Unknown')}\n"
                f"📌 {item.get('status', 'Unknown')}\n"
            )

    await query.edit_message_text(
        "\n".join(lines)[:4000],
        reply_markup=back_keyboard(),
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data or ""

    try:
        if action == "home":
            await query.edit_message_text(
                "💎 PREMIUM NUMBER BOT\n\nChoose an option:",
                reply_markup=home_keyboard(),
            )

        elif action == "services":
            await show_services(query)

        elif action == "countries":
            await show_countries(
                query, context.user_data.get("selected_service")
            )

        elif action == "history":
            await show_history(query)

        elif action == "poll":
            await poll_otp(query, context)

        elif action.startswith("svc:"):
            service = action.split(":", 1)[1]
            context.user_data["selected_service"] = service
            await show_countries(query, service)

        elif action.startswith("cty:"):
            _, service, country = action.split(":", 2)
            await order_number(query, context, service, country)

    except httpx.HTTPStatusError as exc:
        log.error("Provider HTTP status: %s", exc.response.status_code)
        await query.edit_message_text(
            f"⚠️ API HTTP {exc.response.status_code}\n"
            "Endpoint বা API access যাচাই করো।",
            reply_markup=back_keyboard(),
        )

    except Exception:
        log.exception("Button handler error")
        await query.edit_message_text(
            "⚠️ সমস্যা হয়েছে। Termux-এর log দেখো।",
            reply_markup=back_keyboard(),
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))

    log.info("Premium Number Bot is starting")
    app.run_polling()


if __name__ == "__main__":
    main()
