import os
import asyncio
import logging
import sqlite3
import threading
import httpx
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)

# --- CREDENTIALS ---
BOT_TOKEN = "8837482302:AAG7__knyervYM8750TkcFHGmWRmN0EOENs"
ADMIN_ID = 7946253154
UOTP_API_KEY = "45l5Co5a0s27NrIxnYQUa1SnmVPUJM3XS9fyXiSv"
UPI_IDS = ["abhishekzz@fam", "abhishek0912@fam"]

FOOTER = "\n\n━━━━━━━━━━━━━━━━━━━━\n⚡ <b>Fast OTP Store | Owner: @abhisxhxz</b>"

SERVICES = {
    "whatsapp": ("WhatsApp", 30),
    "telegram": ("Telegram", 35),
    "google": ("Google / Gmail", 28),
    "instagram": ("Instagram", 25),
    "snapchat": ("Snapchat", 25),
    "discord": ("Discord", 22),
    "twitter": ("Twitter / X", 25),
    "other": ("Other Service", 18),
}
SEARCH_PRICE = 18

HEADERS = {"Authorization": f"Bearer {UOTP_API_KEY}", "Content-Type": "application/json"}
API_URL = "https://api.uotp.store/v1"

# --- DATABASE ---
def db():
    return sqlite3.connect("otp_bot.db")

with db() as c:
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0)")
    c.execute("CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, utr TEXT UNIQUE, status TEXT DEFAULT 'PENDING')")
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, number_id TEXT, phone_number TEXT, cost REAL, status TEXT DEFAULT 'ACTIVE')")

def get_bal(uid):
    with db() as c:
        row = c.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
        if not row:
            c.execute("INSERT INTO users VALUES (?, 0.0)", (uid,))
            return 0.0
        return row[0]

def add_bal(uid, amt):
    with db() as c:
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))

STATES = {}

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Buy Number", callback_data="buy_menu")],
        [InlineKeyboardButton("💳 Add Balance", callback_data="dep_menu"), InlineKeyboardButton("👤 My Wallet", callback_data="bal_menu")],
        [InlineKeyboardButton("📞 Support", url="https://t.me/abhisxhxz")]
    ])

def kb_services():
    btn = [[InlineKeyboardButton(f"{v[0]} (₹{v[1]})", callback_data=f"ord_{k}")] for k, v in SERVICES.items()]
    btn.append([InlineKeyboardButton("🔍 Search Any App", callback_data="search")])
    btn.append([InlineKeyboardButton("🔙 Back", callback_data="home")])
    return InlineKeyboardMarkup(btn)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    STATES.pop(uid, None)
    bal = get_bal(uid)
    text = f"👋 <b>Welcome {update.effective_user.first_name}!</b>\n\n💰 <b>Balance:</b> <code>₹{bal:.2f}</code>{FOOTER}"
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=kb_main(), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=kb_main(), parse_mode=ParseMode.HTML)

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d = q.data

    if d == "home":
        await start(update, context)

    elif d == "bal_menu":
        bal = get_bal(uid)
        await q.message.edit_text(
            f"👤 <b>Account Overview:</b>\n🆔 <b>ID:</b> <code>{uid}</code>\n💵 <b>Balance:</b> <code>₹{bal:.2f}</code>{FOOTER}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Add Balance", callback_data="dep_menu")], [InlineKeyboardButton("🔙 Back", callback_data="home")]]),
            parse_mode=ParseMode.HTML
        )

    elif d == "dep_menu":
        STATES[uid] = "UTR"
        await q.message.edit_text(
            f"💳 <b>Recharge Wallet:</b>\n1️⃣ Pay via UPI:\n🔹 <code>{UPI_IDS[0]}</code>\n🔹 <code>{UPI_IDS[1]}</code>\n\n2️⃣ Send 12-digit <b>UTR number</b> in chat.{FOOTER}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="home")]]),
            parse_mode=ParseMode.HTML
        )

    elif d == "buy_menu":
        await q.message.edit_text(f"📱 <b>Select a Service:</b>\n💰 <b>Balance:</b> ₹{get_bal(uid):.2f}{FOOTER}", reply_markup=kb_services(), parse_mode=ParseMode.HTML)

    elif d == "search":
        STATES[uid] = "SEARCH"
        await q.message.edit_text(f"🔍 <b>Send app/website name in chat:</b>\n(Flat price: ₹{SEARCH_PRICE})", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="buy_menu")]]), parse_mode=ParseMode.HTML)

    elif d.startswith("ord_"):
        srv = d.replace("ord_", "")
        name, price = SERVICES.get(srv, (srv.capitalize(), SEARCH_PRICE))
        if get_bal(uid) < price:
            await q.answer("❌ Insufficient balance! Please recharge.", show_alert=True)
            return

        await q.message.edit_text("⏳ <i>Purchasing number from API...</i>", parse_mode=ParseMode.HTML)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(f"{API_URL}/number/buy", headers=HEADERS, json={"service": srv, "country": "india"})
                data = res.json()
        except Exception:
            data = {}

        if data.get("status") in ("success", True) or "number" in data:
            item = data.get("data", data)
            nid = str(item.get("number_id", item.get("id", "")))
            phone = str(item.get("number", item.get("phone", "")))

            add_bal(uid, -price)
            with db() as c:
                cur = c.execute("INSERT INTO orders (user_id, service, number_id, phone_number, cost) VALUES (?, ?, ?, ?, ?)", (uid, srv, nid, phone, price))
                oid = cur.lastrowid

            msg = f"🎉 <b>Number Allocated!</b>\n📌 <b>Service:</b> {name}\n📱 <b>Number:</b> <code>{phone}</code>\n💵 <b>Price:</b> ₹{price}\n\n👉 <i>App me daalo aur OTP bhejo!</i>{FOOTER}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check OTP", callback_data=f"chk_{oid}")],
                [InlineKeyboardButton("❌ Cancel & Refund", callback_data=f"cnc_{oid}")]
            ])
            await q.message.edit_text(msg, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await q.message.edit_text("❌ <b>Stock unavailable right now. Try again later.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="buy_menu")]]), parse_mode=ParseMode.HTML)

    elif d.startswith("chk_"):
        oid = int(d.replace("chk_", ""))
        with db() as c:
            row = c.execute("SELECT number_id, phone_number, status FROM orders WHERE id = ? AND user_id = ?", (oid, uid)).fetchone()
        if not row or row[2] != "ACTIVE":
            await q.answer("Order not active.", show_alert=True)
            return

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(f"{API_URL}/number/{row[0]}/sms", headers=HEADERS)
                res_data = res.json()
        except Exception:
            res_data = {}

        otp = res_data.get("otp") or res_data.get("code") or (res_data.get("data", {}).get("otp") if isinstance(res_data.get("data"), dict) else None)
        if otp:
            with db() as c:
                c.execute("UPDATE orders SET status = 'COMPLETED' WHERE id = ?", (oid,))
            await q.message.edit_text(
                f"🔔 <b>OTP RECEIVED!</b>\n━━━━━━━━━━━━━━━━━━━━\n📱 <b>Number:</b> <code>{row[1]}</code>\n🔑 <b>OTP:</b> <code>{otp}</code>{FOOTER}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Buy Another", callback_data="buy_menu")]]),
                parse_mode=ParseMode.HTML
            )
        else:
            await q.answer("📭 Abhi tak OTP nahi aaya. Wait karke dobara refresh karein.", show_alert=True)

    elif d.startswith("cnc_"):
        oid = int(d.replace("cnc_", ""))
        with db() as c:
            row = c.execute("SELECT number_id, cost, status FROM orders WHERE id = ? AND user_id = ?", (oid, uid)).fetchone()
        if not row or row[2] != "ACTIVE":
            await q.answer("Cannot cancel.", show_alert=True)
            return

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(f"{API_URL}/number/{row[0]}/cancel", headers=HEADERS)
        except Exception:
            pass

        add_bal(uid, row[1])
        with db() as c:
            c.execute("UPDATE orders SET status = 'CANCELED' WHERE id = ?", (oid,))
        await q.message.edit_text(f"✅ <b>Order Canceled!</b>\n₹{row[1]:.2f} aapke wallet me refund kar diye gaye.", reply_markup=kb_main(), parse_mode=ParseMode.HTML)

    elif d.startswith("app_"):
        if uid != ADMIN_ID:
            return
        did = int(d.replace("app_", ""))
        with db() as c:
            row = c.execute("SELECT user_id, amount, status FROM deposits WHERE id = ?", (did,)).fetchone()
            if row and row[2] == "PENDING":
                c.execute("UPDATE deposits SET status = 'APPROVED' WHERE id = ?", (did,))
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (row[1], row[0]))
                await q.message.edit_text(f"✅ Approved ₹{row[1]} for {row[0]}")
                try:
                    await context.bot.send_message(row[0], f"🎉 ₹{row[1]:.2f} added to your balance!")
                except Exception:
                    pass

    elif d.startswith("rej_"):
        if uid != ADMIN_ID:
            return
        did = int(d.replace("rej_", ""))
        with db() as c:
            c.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (did,))
        await q.message.edit_text(f"❌ Rejected deposit #{did}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip()
    st = STATES.get(uid)
    if not st:
        return

    if st == "UTR":
        utr = "".join(filter(str.isalnum, txt))
        if len(utr) < 8:
            await update.message.reply_text("❌ Invalid UTR. Enter 12-digit number.")
            return

        with db() as c:
            if c.execute("SELECT id FROM deposits WHERE utr = ?", (utr,)).fetchone():
                await update.message.reply_text("⚠️ UTR already used!")
                return
            cur = c.execute("INSERT INTO deposits (user_id, amount, utr) VALUES (?, 30.0, ?)", (uid, utr))
            did = cur.lastrowid

        STATES.pop(uid, None)
        await update.message.reply_text("⏳ UTR submitted! Admin verify karke balance add karega.")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Approve ₹30", callback_data=f"app_{did}"), InlineKeyboardButton("Reject", callback_data=f"rej_{did}")]])
        await context.bot.send_message(ADMIN_ID, f"🚨 <b>Deposit:</b> {uid}\nUTR: <code>{utr}</code>", reply_markup=kb, parse_mode=ParseMode.HTML)

    elif st == "SEARCH":
        STATES.pop(uid, None)
        q = txt.lower()
        kb = [[InlineKeyboardButton(f"Buy {txt.capitalize()} (₹{SEARCH_PRICE})", callback_data=f"ord_{q}")]]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="buy_menu")])
        await update.message.reply_text(f"🎯 Search result for '{txt}':", reply_markup=InlineKeyboardMarkup(kb))

def run_web():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot Alive!"))
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    loop.run_until_complete(site.start())
    loop.run_forever()

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

