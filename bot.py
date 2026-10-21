"""Premium Number Bot for NumberPanel.

Confirmed from NumberPanel docs:
  GET  /api/services
  GET  /api/countries?service=whatsapp
  POST /api/request_number   JSON: {"service":"whatsapp","country":"random" or country name}
  GET  /api/latest_otp?number=...
  GET  /api/my_numbers
  GET  /api/my_otps

No force-join feature is included. Keep credentials in .env, never in this file.
"""

import os
import json
import logging
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("numberpanel_bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API_KEY = os.getenv("NUMBERPANEL_API_KEY", "").strip()
GROUP_ID = os.getenv("GROUP_ID", "").strip()
BASE_URL = os.getenv("NUMBERPANEL_BASE_URL", "https://numberpanel.tech").rstrip("/")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/challeh61")
HELP_URL = os.getenv("HELP_URL", "https://t.me/bluebear10")

SERVICES_PATH = "/api/services"
COUNTRIES_PATH = "/api/countries"
ORDER_PATH = "/api/request_number"
POLL_PATH = "/api/latest_otp"
HISTORY_PATH = "/api/my_numbers"
OTP_HISTORY_PATH = "/api/my_otps"


def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 GET NUMBER", callback_data="services")],
        [
            InlineKeyboardButton("🌍 COUNTRY", callback_data="countries"),
            InlineKeyboardButton("👑 MY HISTORY", callback_data="history"),
        ],
        [InlineKeyboardButton("🔄 POLL OTP", callback_data="poll")],
        [
            InlineKeyboardButton("📢 CHANNEL", url=CHANNEL_URL),
            InlineKeyboardButton("💬 HELP", url=HELP_URL),
        ],
    ])


def nav_keyboard(back="home"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ BACK", callback_data=back)],
        [InlineKeyboardButton("🏠 HOME", callback_data="home")],
    ])


def country_fallback_keyboard(service):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 RANDOM COUNTRY", callback_data=f"random:{service[:40]}")],
        [InlineKeyboardButton("🔄 RETRY COUNTRIES", callback_data=f"svc:{service[:40]}")],
        [InlineKeyboardButton("🏠 HOME", callback_data="home")],
    ])


async def api_request(context, method, path, **kwargs):
    client = context.application.bot_data["http_client"]
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    response = await client.request(
        method, f"{BASE_URL}{path}", headers=headers, **kwargs
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"API returned non-JSON content: {response.text[:300]}"
        ) from exc


def as_list(data, *keys):
    """Accept common API response shapes, including nested data objects."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = as_list(value, *keys)
            if nested:
                return nested
    # Some APIs return the array under a generic 'items' field.
    for key in ("items", "available", "inventory", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def get_service_key(item):
    return str(item.get("key") or item.get("id") or item.get("code") or "").strip()


def get_country_value(item):
    # The provider docs say country name or "random" is accepted for ordering.
    return str(
        item.get("name") or item.get("country") or item.get("country_name")
        or item.get("title") or item.get("code") or item.get("key") or ""
    ).strip()


async def safe_edit(query, text, markup=None):
    try:
        await query.edit_message_text(
            text=text, reply_markup=markup, disable_web_page_preview=True
        )
    except BadRequest as exc:
        if "Message is not modified" not in str(exc):
            raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "╭━━ 💎 PREMIUM NUMBER BOT ━━╮\n"
        "┃ 👑 Welcome!\n"
        "┃ 📱 Select a service\n"
        "┃ 🌍 Choose a country\n"
        "┃ 🔐 Check OTP\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "👇 নিচের মেনু থেকে বেছে নাও:",
        reply_markup=home_keyboard(),
    )


async def show_services(query, context):
    await safe_edit(query, "⏳ Service list লোড হচ্ছে…")
    data = await api_request(context, "GET", SERVICES_PATH)
    services = as_list(data, "services", "data", "results")
    log.info("Services API response: %s", json.dumps(data, ensure_ascii=False)[:2500])

    buttons = []
    for item in services[:50]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        key = get_service_key(item)
        count = item.get("count", "")
        if name and key:
            buttons.append([InlineKeyboardButton(
                f"📱 {name[:25]}  ·  🔢 {count}",
                callback_data=f"svc:{key[:40]}",
            )])

    if not buttons:
        log.error("Could not parse service list from response: %s", data)
        await safe_edit(
            query, "⚠️ Service list পাওয়া যায়নি। API response Termux log-এ দেখো।",
            nav_keyboard(),
        )
        return

    buttons.append([InlineKeyboardButton("🏠 HOME", callback_data="home")])
    await safe_edit(query, "💎 SELECT SERVICE", InlineKeyboardMarkup(buttons))


async def show_countries(query, context, service=None):
    service = service or context.user_data.get("selected_service")
    if not service:
        await safe_edit(query, "আগে একটি service নির্বাচন করো।", nav_keyboard("services"))
        return

    await safe_edit(query, "⏳ Country list লোড হচ্ছে…")
    # Provider docs: GET /api/countries, optional query parameter service.
    data = await api_request(
        context, "GET", COUNTRIES_PATH, params={"service": service}
    )
    countries = as_list(data, "countries", "data", "results", "country_list")
    log.info(
        "Countries API response for service=%s: %s",
        service, json.dumps(data, ensure_ascii=False)[:4000]
    )

    buttons = []
    country_options = {}
    for item in countries[:50]:
        if not isinstance(item, dict):
            continue
        name = get_country_value(item)
        # Keep displayed label and submitted value the same. Store the full
        # country in user_data to keep Telegram callback_data under 64 bytes.
        if name:
            idx = len(country_options)
            country_options[str(idx)] = name
            buttons.append([InlineKeyboardButton(
                f"🌍 {name[:28]}",
                callback_data=f"cty:{idx}",
            )])
    context.user_data["country_options"] = country_options
    context.user_data["selected_service"] = service

    if not buttons:
        # Don't leave users stuck: provider docs allow country="random".
        await safe_edit(
            query,
            "⚠️ Country list API থেকে পড়া যায়নি।\n"
            "তুমি চাইলে Random Country দিয়ে অর্ডার চেষ্টা করতে পারো।\n\n"
            "API response দেখতে Termux-এ চালাও: tail -n 80 bot.log",
            country_fallback_keyboard(service),
        )
        return

    buttons.append([InlineKeyboardButton("🎲 RANDOM COUNTRY", callback_data=f"random:{service[:40]}")])
    buttons.append([InlineKeyboardButton("⬅️ SERVICES", callback_data="services")])
    await safe_edit(query, "🌍 SELECT COUNTRY", InlineKeyboardMarkup(buttons))


async def order_number(query, context, service, country):
    await safe_edit(query, "⏳ নম্বর অর্ডার করা হচ্ছে…")
    data = await api_request(
        context, "POST", ORDER_PATH,
        json={"service": service, "country": country},
    )
    log.info("Order API response: %s", json.dumps(data, ensure_ascii=False)[:2500])

    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected order response: {data!r}")

    number = data.get("number") or data.get("phone_number")
    if isinstance(number, dict):
        number = number.get("number") or number.get("phone") or number.get("phone_number")
    if not number:
        reason = data.get("message") or data.get("error") or data.get("detail") or "API returned no number"
        await safe_edit(query, f"⚠️ অর্ডার হয়নি: {str(reason)[:300]}", nav_keyboard("services"))
        return

    number = str(number)
    context.user_data["active_number"] = number
    context.user_data["active_service"] = service
    await safe_edit(
        query,
        "💎 NUMBER RECEIVED\n\n"
        f"📱 Service: {service}\n"
        f"🌍 Country: {country}\n"
        f"☎️ Number: {number}\n\nOTP এলে নিচের বাটনে চাপ দাও।",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 POLL OTP", callback_data="poll")],
            [InlineKeyboardButton("🏠 HOME", callback_data="home")],
        ]),
    )

    if GROUP_ID:
        masked = number[:5] + "*" * max(0, len(number) - 5)
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=f"💎 NEW ORDER\n📱 {service}\n🌍 {country}\n☎️ {masked}",
            )
        except Exception:
            log.exception("Group notification failed")


async def poll_otp(query, context):
    number = context.user_data.get("active_number")
    if not number:
        await safe_edit(query, "⚠️ আগে একটি নম্বর অর্ডার করো।", nav_keyboard("services"))
        return
    await safe_edit(query, "🔄 OTP চেক করা হচ্ছে…")
    data = await api_request(context, "GET", POLL_PATH, params={"number": number})
    log.info("OTP API response: %s", json.dumps(data, ensure_ascii=False)[:2000])

    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected OTP response: {data!r}")
    otp = data.get("otp") or data.get("code") or data.get("latest_otp")
    sms = data.get("sms") or data.get("message_text")
    if otp or sms:
        message = f"✅ OTP RECEIVED!\n\n📱 Number: {number}\n🔐 OTP/SMS: {otp or sms}"
    else:
        status = data.get("message") or data.get("status") or "OTP এখনো আসেনি।"
        message = f"⏳ {str(status)[:250]}\n\n📱 Number: {number}\nকিছুক্ষণ পর আবার চেষ্টা করো।"
    await safe_edit(
        query, message,
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 POLL AGAIN", callback_data="poll")],
            [InlineKeyboardButton("🏠 HOME", callback_data="home")],
        ]),
    )


async def show_history(query, context):
    await safe_edit(query, "⏳ History লোড হচ্ছে…")
    data = await api_request(context, "GET", HISTORY_PATH)
    items = as_list(data, "numbers", "history", "data", "results")
    log.info("History API response: %s", json.dumps(data, ensure_ascii=False)[:2500])
    if not items:
        await safe_edit(query, "📭 কোনো active number history পাওয়া যায়নি।", nav_keyboard())
        return

    lines = ["👑 MY HISTORY", ""]
    for item in items[:15]:
        if isinstance(item, dict):
            lines.append(
                f"📱 {item.get('number', 'Unknown')}\n"
                f"💎 {item.get('service', 'Unknown')}\n"
                f"📌 {item.get('status', 'Unknown')}\n"
            )
    await safe_edit(query, "\n".join(lines)[:3900], nav_keyboard())


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Answer first, so Telegram stops showing the spinning indicator.
    await query.answer()
    action = query.data or ""
    try:
        if action == "home":
            await safe_edit(query, "💎 PREMIUM NUMBER BOT\n\n👇 একটি অপশন বেছে নাও:", home_keyboard())
        elif action == "services":
            await show_services(query, context)
        elif action == "countries":
            await show_countries(query, context)
        elif action == "history":
            await show_history(query, context)
        elif action == "poll":
            await poll_otp(query, context)
        elif action.startswith("svc:"):
            service = action.split(":", 1)[1]
            context.user_data["selected_service"] = service
            await show_countries(query, context, service)
        elif action.startswith("random:"):
            service = action.split(":", 1)[1]
            context.user_data["selected_service"] = service
            await order_number(query, context, service, "random")
        elif action.startswith("cty:"):
            idx = action.split(":", 1)[1]
            country = context.user_data.get("country_options", {}).get(idx)
            service = context.user_data.get("selected_service")
            if not country or not service:
                await safe_edit(query, "⚠️ Country selection মেয়াদ শেষ। আবার service বেছে নাও।", nav_keyboard("services"))
            else:
                await order_number(query, context, service, country)
        else:
            await safe_edit(query, "⚠️ অজানা অপশন। /start চাপো।", home_keyboard())

    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:350]
        log.error("API HTTP %s at %s: %s", exc.response.status_code, exc.request.url, body)
        await safe_edit(
            query,
            f"⚠️ NumberPanel API HTTP {exc.response.status_code}\n"
            f"{body[:200]}\n\nAPI key/access যাচাই করো।",
            nav_keyboard(),
        )
    except (httpx.TimeoutException, httpx.ConnectError):
        log.exception("API connection error")
        await safe_edit(
            query, "⏱️ NumberPanel API-তে সংযোগ হচ্ছে না। ইন্টারনেট/সার্ভার যাচাই করে আবার চেষ্টা করো।",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 TRY AGAIN", callback_data=action)],
                [InlineKeyboardButton("🏠 HOME", callback_data="home")],
            ]),
        )
    except Exception as exc:
        log.exception("Button handler failed")
        await safe_edit(
            query, f"⚠️ সমস্যা: {str(exc)[:250]}",
            nav_keyboard(),
        )


async def post_init(application):
    application.bot_data["http_client"] = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0)
    )


async def post_shutdown(application):
    client = application.bot_data.get("http_client")
    if client:
        await client.aclose()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN নেই। .env ফাইলে নতুন bot token বসাও।")
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    log.info("Bot started. No forced-join channel is configured.")
    app.run_polling()


if __name__ == "__main__":
    main()
