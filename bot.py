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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# --- CREDENTIALS CONFIGURATION ---
BOT_TOKEN = "8837482302:AAG7__knyervYM8750TkcFHGmWRmN0EOENs"
ADMIN_ID = 7946253154
UOTP_API_KEY = "45l5Co5a0s27NrIxnYQUa1SnmVPUJM3XS9fyXiSv"
UPI_IDS = ["abhishekzz@fam", "abhishek0912@fam"]

FOOTER_TEXT = "\n\n━━━━━━━━━━━━━━━━━━━━\n⚡ <b>Fast OTP Store | Owner: @abhisxhxz</b>"

# Popular services & updated selling prices (+₹10 added)
DEFAULT_SERVICES = {
    "whatsapp": {"name": "WhatsApp", "price": 30},
    "telegram": {"name": "Telegram", "price": 35},
    "google": {"name": "Google / Gmail", "price": 28},
    "instagram": {"name": "Instagram / Meta", "price": 25},
    "snapchat": {"name": "Snapchat", "price": 25},
    "discord": {"name": "Discord", "price": 22},
    "twitter": {"name": "Twitter / X", "price": 25},
    "other": {"name": "Any Other Service", "price": 18},
}

DEFAULT_SEARCH_PRICE = 18

API_HEADERS = {
    "Authorization": f"Bearer {UOTP_API_KEY}",
    "Content-Type": "application/json"
}
BASE_API_URL = "https://api.uotp.store/v1"

# --- DATABASE SETUP ---
DB_FILE = "otp_bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            utr TEXT UNIQUE,
            status TEXT DEFAULT 'PENDING'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT,
            number_id TEXT,
            phone_number TEXT,
            cost REAL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_balance(user_id, username=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 0.0)", (user_id, username))
        conn.commit()
        bal = 0.0
    else:
        bal = row[0]
    conn.close()
    return bal

def update_user_balance(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

USER_STATES = {}

# --- KEYBOARDS ---
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Buy Number", callback_data="menu_buy")],
        [
            InlineKeyboardButton("💳 Add Balance", callback_data="menu_deposit"),
            InlineKeyboardButton("👤 My Wallet", callback_data="menu_wallet"),
        ],
        [
            InlineKeyboardButton("📞 Support", url="https://t.me/abhisxhxz"),
        ]
    ])

def buy_services_keyboard():
    keyboard = []
    buttons = []
    for s_id, s_info in DEFAULT_SERVICES.items():
        btn = InlineKeyboardButton(f"{s_info['name']} (₹{s_info['price']})", callback_data=f"buy_{s_id}")
        buttons.append(btn)
        if len(buttons) == 2:
            keyboard.append(buttons)
            buttons = []
    if buttons:
        keyboard.append(buttons)
    keyboard.append([InlineKeyboardButton("🔍 Search Any App / Service", callback_data="service_search")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu_home")])
    return InlineKeyboardMarkup(keyboard)

# --- TELEGRAM BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bal = get_user_balance(user.id, user.username or user.first_name)
    USER_STATES.pop(user.id, None)

    msg = (
        f"👋 <b>Welcome {user.first_name}!</b>\n\n"
        "⚡ <b>Fast OTP Store</b> me aapka swagat hai.\n"
        "Yahan se aap WhatsApp, Telegram, Google, etc. ke liye fresh virtual numbers le sakte hain.\n\n"
        f"💰 <b>Aapka Balance:</b> <code>₹{bal:.2f}</code>\n\n"
        "Niche diye gaye options me se select karein:"
        f"{FOOTER_TEXT}"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(msg, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(msg, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "menu_home":
        await start(update, context)

    elif data == "menu_wallet":
        bal = get_user_balance(user_id)
        text = (
            f"👤 <b>Account Overview:</b>\n\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"💵 <b>Current Balance:</b> <code>₹{bal:.2f}</code>\n\n"
            "Funds add karne ke liye niche <b>Add Balance</b> par click karein."
            f"{FOOTER_TEXT}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Add Balance", callback_data="menu_deposit")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_home")]
        ])
        await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data == "menu_deposit":
        text = (
            "💳 <b>Add Funds / Wallet Recharge</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Niche diye gaye kisi bhi UPI ID par payment karein:\n\n"
            f"🔹 <code>{UPI_IDS[0]}</code> <i>(Tap to copy)</i>\n"
            f"🔹 <code>{UPI_IDS[1]}</code> <i>(Tap to copy)</i>\n\n"
            "2️⃣ Payment complete karne ke baad bank se aane wala <b>12-digit UTR / Reference No.</b> chat me send karein.\n\n"
            "<i>Minimum deposit: ₹20</i>\n"
            "⚠️ <i>Galat ya purana UTR submit na karein, verification automated check hota hai.</i>"
            f"{FOOTER_TEXT}"
        )
        USER_STATES[user_id] = {"state": "AWAIT_UTR"}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="menu_home")]])
        await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data == "menu_buy":
        bal = get_user_balance(user_id)
        text = (
            f"📱 <b>Select a Service for OTP:</b>\n"
            f"💰 <b>Your Balance:</b> <code>₹{bal:.2f}</code>\n\n"
            "Select from popular services below, ya <b>Search</b> option use karein:"
            f"{FOOTER_TEXT}"
        )
        await query.message.edit_text(text, reply_markup=buy_services_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "service_search":
        USER_STATES[user_id] = {"state": "SEARCH_SERVICE"}
        text = (
            "🔍 <b>Search Any Service / App</b>\n\n"
            "Jis website ya app ka OTP chahiye uska naam chat me likh kar send karein (e.g. <i>Dream11, Tinder, Flipkart</i>):\n"
            f"📌 <i>Sabhi searched services ka price <b>₹{DEFAULT_SEARCH_PRICE}</b> fix hai.</i>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_buy")]])
        await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data.startswith("buy_"):
        service_id = data.replace("buy_", "")
        service_info = DEFAULT_SERVICES.get(service_id, {"name": service_id.capitalize(), "price": DEFAULT_SEARCH_PRICE})
        price = service_info["price"]

        bal = get_user_balance(user_id)
        if bal < price:
            await query.answer("❌ Insufficient balance! Please recharge your wallet first.", show_alert=True)
            return

        await query.message.edit_text("⏳ <i>Purchasing fresh virtual number from API...</i>", parse_mode=ParseMode.HTML)

        url = BASE_API_URL + "/number/buy"
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                res = await client.post(url, headers=API_HEADERS, json={"service": service_id, "country": "india"})
                res_data = res.json()
            except Exception:
                res_data = {}

        if res_data.get("status") in ("success", True) or "number" in res_data:
            num_data = res_data.get("data", res_data)
            number_id = str(num_data.get("number_id", num_data.get("id", "")))
            phone_num = str(num_data.get("number", num_data.get("phone", "")))

            update_user_balance(user_id, -price)

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "INSERT INTO orders (user_id, service, number_id, phone_number, cost, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
                (user_id, service_id, number_id, phone_num, price)
            )
            order_id = c.lastrowid
            conn.commit()
            conn.close()

            text = (
                f"🎉 <b>Number Allocated Successfully!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>Service:</b> {service_info['name']}\n"
                f"📱 <b>Phone Number:</b> <code>{phone_num}</code>\n"
                f"💵 <b>Price:</b> ₹{price}\n\n"
                f"👉 <i>Number copy karke app me daalein aur OTP request karein. OTP aate hi yahan show ho jayega.</i>\n\n"
                f"⏳ <b>Validity:</b> 15-20 Minutes\n"
                f"⚠️ <i>Agar OTP nahi aata toh Cancel dabane par instant full refund mil jayega.</i>"
                f"{FOOTER_TEXT}"
            )

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check OTP", callback_data=f"chk_{order_id}")],
                [InlineKeyboardButton("❌ Cancel & Refund", callback_data=f"cnc_{order_id}")]
            ])
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            err = res_data.get("message", "Temporary stock unavailable. Please try again.")
            text = (
                f"❌ <b>Purchase Failed:</b> {err}\n\n"
                "Aapka koi balance deduct nahi hua hai."
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Services", callback_data="menu_buy")]])
            await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif data.startswith("chk_"):
        order_id = int(data.replace("chk_", ""))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT number_id, phone_number, status FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
        order = c.fetchone()
        conn.close()

        if not order:
            await query.answer("Order not found.", show_alert=True)
            return

        num_id, phone, status = order
        if status == "COMPLETED":
            await query.answer("Ye OTP pehle hi deliver ho chuka hai.", show_alert=True)
            return

        check_url = BASE_API_URL + "/number/" + str(num_id) + "/sms"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                res = await client.get(check_url, headers=API_HEADERS)
                res_data = res.json()
            except Exception:
                res_data = {}

        otp_val = res_data.get("otp") or res_data.get("code") or (res_data.get("data", {}).get("otp") if isinstance(res_data.get("data"), dict) else None)
        sms_text = res_data.get("message") or (res_data.get("data", {}).get("message") if isinstance(res_data.get("data"), dict) else "")

        if otp_val:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE orders SET status = 'COMPLETED' WHERE id = ?", (order_id,))
            conn.commit()
            conn.close()

            success_text = (
                f"🔔 <b>OTP RECEIVED SUCCESSFULLY!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📱 <b>Number:</b> <code>{phone}</code>\n"
                f"🔑 <b>Your OTP:</b> <code>{otp_val}</code>\n\n"
                f"💬 <b>SMS Text:</b>\n<code>{sms_text}</code>"
                f"{FOOTER_TEXT}"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Buy Another", callback_data="menu_buy")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_home")]
            ])
            await query.message.edit_text(success_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await query.answer("📭 Abhi tak OTP nahi aaya. Kripya thoda wait karke refresh karein.", show_alert=True)

    elif data.startswith("cnc_"):
        order_id = int(data.replace("cnc_", ""))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT number_id, cost, status FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
        order = c.fetchone()
        conn.close()

        if not order or order[2] != "ACTIVE":
            await query.answer("Order cannot be canceled.", show_alert=True)
            return

        num_id, cost, _ = order

        cancel_url = BASE_API_URL + "/number/" + str(num_id) + "/cancel"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                await client.post(cancel_url, headers=API_HEADERS)
            except Exception:
                pass

        update_user_balance(user_id, cost)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE orders SET status = 'CANCELED' WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()

        await query.message.edit_text(
            f"✅ <b>Order Canceled!</b>\n₹{cost:.2f} aapke wallet me turant refund kar diye gaye hain.",
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )

    # --- ADMIN APPROVAL HANDLERS ---
    elif data.startswith("adm_app_"):
        if user_id != ADMIN_ID:
            return
        dep_id = int(data.replace("adm_app_", ""))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id, amount, utr, status FROM deposits WHERE id = ?", (dep_id,))
        row = c.fetchone()
        if not row or row[3] != "PENDING":
            await query.answer("Already processed!", show_alert=True)
            conn.close()
            return

        target_uid, amount, utr, _ = row
        c.execute("UPDATE deposits SET status = 'APPROVED' WHERE id = ?", (dep_id,))
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_uid))
        conn.commit()
        conn.close()

        await query.message.edit_text(f"✅ <b>APPROVED!</b> ₹{amount} added to User ID <code>{target_uid}</code> (UTR: {utr}).", parse_mode=ParseMode.HTML)
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"🎉 <b>Deposit Approved!</b>\n₹{amount:.2f} aapke wallet me add ho gaye hain.\nAb aap number buy kar sakte hain!",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    elif data.startswith("adm_rej_"):
        if user_id != ADMIN_ID:
            return
        dep_id = int(data.replace("adm_rej_", ""))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (dep_id,))
        conn.commit()
        conn.close()

        await query.message.edit_text(f"❌ <b>REJECTED!</b> Deposit #{dep_id} was declined.", parse_mode=ParseMode.HTML)

async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user = update.effective_user

    state_data = USER_STATES.get(user_id)
    if not state_data:
        return

    if state_data.get("state") == "AWAIT_UTR":
        utr = "".join(filter(str.isalnum, text))
        if len(utr) < 8:
            await update.message.reply_text("❌ Kripya valid 12-digit UPI UTR / Transaction number enter karein.")
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id FROM deposits WHERE utr = ?", (utr,))
        if c.fetchone():
            conn.close()
            await update.message.reply_text("⚠️ Ye UTR pehle hi submit kiya ja chuka hai.")
            return

        amount = 30.0
        c.execute("INSERT INTO deposits (user_id, amount, utr, status) VALUES (?, ?, ?, 'PENDING')", (user_id, amount, utr))
        dep_id = c.lastrowid
        conn.commit()
        conn.close()

        USER_STATES.pop(user_id, None)
        await update.message.reply_text(
            "⏳ <b>Aapka UTR submit ho gaya hai!</b>\nAdmin verification ke baad 1-2 minute me balance add ho jayega.",
            parse_mode=ParseMode.HTML
        )

        admin_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"✅ Approve ₹{amount}", callback_data=f"adm_app_{dep_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{dep_id}")
            ]
        ])
        admin_alert = (
            f"🚨 <b>NEW DEPOSIT REQUEST!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {user.first_name} (<code>{user_id}</code>)\n"
            f"🔢 <b>UTR:</b> <code>{utr}</code>\n"
            f"💵 <b>Claimed Amount:</b> ₹{amount}\n\n"
            "Apne bank / UPI app me verify karke button dabayein:"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, reply_markup=admin_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            logging.error(f"Failed to alert admin: {e}")

    elif state_data.get("state") == "SEARCH_SERVICE":
        query = text.lower()
        USER_STATES.pop(user_id, None)

        matched = []
        for s_id, s_info in DEFAULT_SERVICES.items():
            if query in s_info["name"].lower() or query in s_id:
                matched.append((s_id, s_info))

        if not matched:
            matched.append((query, {"name": text.capitalize(), "price": DEFAULT_SEARCH_PRICE}))

        keyboard = []
        for s_id, s_info in matched:
            keyboard.append([InlineKeyboardButton(f"Buy {s_info['name']} (₹{s_info['price']})", callback_data=f"buy_{s_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Services", callback_data="menu_buy")])

        await update.message.reply_text(
            f"🎯 <b>Search Results for '{text}':</b>\nSelect karke number buy karein:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

# --- BACKGROUND OTP CHECKER ---
async def background_otp_checker(app):
    while True:
        await asyncio.sleep(8)
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, user_id, number_id, phone_number, service FROM orders WHERE status = 'ACTIVE'")
            active_orders = c.fetchall()
            conn.close()

            for order in active_orders:
                o_id, u_id, num_id, phone, srv = order
                check_url = BASE_API_URL + "/number/" + str(num_id) + "/sms"
                async with httpx.AsyncClient(
