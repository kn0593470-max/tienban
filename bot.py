import os
import json
import logging
import random
import string
import time
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)

# --- PHẦN WEB SERVER CHO RENDER ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Telegram Bot is running smoothly!", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)


# --- CẤU HÌNH BOT ---
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "8940617884:AAHw7goFVSMIw9lQps6NiyNLxQ-o9LGUyFs")
ADMIN_IDS  = {8653130427, 8825095433}

STATE_FILE = "state.json"
BANS_FILE  = "bans.json"

DEFAULT_STATE = {
    "rate": 7,
    "options": [200_000, 300_000, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000],
    "qr_file_id": None,
    "bank_name": "VIB",
    "bank_stk": "099121046",
    "bank_owner": "NGUYEN HOANG TUNG"
}

def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(default, dict):
                    for k, v in default.items():
                        if k not in data:
                            data[k] = v
                return data
            except:
                pass
    return default.copy() if isinstance(default, dict) else default.copy()

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

state = load_json(STATE_FILE, DEFAULT_STATE)
bans = load_json(BANS_FILE, {})

def save_state(): save_json(STATE_FILE, state)
def save_bans(): save_json(BANS_FILE, bans)

def is_banned(user_id: int) -> bool:
    uid = str(user_id)
    if uid in bans:
        unban_time = bans[uid]
        if unban_time == 0 or time.time() < unban_time:
            return True
        else:
            del bans[uid]
            save_bans()
    return False

(
    WAIT_PROOF, WAIT_CUST_INFO, 
    WAIT_NEW_RATE, WAIT_NEW_OPTIONS, WAIT_BANK_INFO,
    WAIT_QR_IMAGE, WAIT_BAN_DAYS, WAIT_WARN_TEXT
) = range(8)

def fmt(n: int) -> str: return f"{n:,}".replace(",", ".")
def gen_order_id() -> str: return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_bank_info_text() -> str:
    return (
        f"🏦 *THÔNG TIN CHUYỂN KHOẢN*\n"
        f"• Ngân hàng: `{state.get('bank_name', 'VIB')}`\n"
        f"• Số tài khoản: `{state.get('bank_stk', '099121046')}`\n"
        f"• Chủ tài khoản: `{state.get('bank_owner', 'NGUYEN HOANG TUNG')}`"
    )

def main_menu() -> InlineKeyboardMarkup:
    r = state["rate"]
    rows = [
        [InlineKeyboardButton(f"💵 {fmt(amt)} VND ➔ Nhận {fmt(amt * r)} VND", callback_data=f"buy_{amt}")]
        for amt in state["options"]
    ]
    rows.append([InlineKeyboardButton("📞 Liên hệ Admin", url=f"tg://user?id={list(ADMIN_IDS)[0]}")])
    return InlineKeyboardMarkup(rows)

def admin_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Đổi Tỉ Lệ", callback_data="adm_rate"),
         InlineKeyboardButton("📋 Sửa Mức Giá", callback_data="adm_options")],
        [InlineKeyboardButton("🏦 Đổi Ngân Hàng", callback_data="adm_bank"),
         InlineKeyboardButton("🖼 Cập Nhật QR", callback_data="adm_qr_info")],
        [InlineKeyboardButton("❌ Đóng Menu", callback_data="adm_close")]
    ])

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("⛔ Tài khoản của bạn đã bị khóa khỏi hệ thống.")
        return ConversationHandler.END

    r = state["rate"]
    header = f"💱 *HỆ THỐNG QUY ĐỔI TỰ ĐỘNG*\n📊 Tỉ lệ hiện tại: `1:{r}`\n\n👇 Vui lòng chọn gói giao dịch bên dưới:"
    await update.message.reply_text(header, parse_mode="Markdown", reply_markup=main_menu())
    return ConversationHandler.END

# Luồng Mua Hàng (Gửi bill trước -> Nhập thông tin nhận tiền sau)
async def on_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if is_banned(user.id):
        await query.answer("⛔ Bạn đã bị cấm sử dụng bot.", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    amt   = int(query.data.split("_")[1])
    dirty = amt * state["rate"]
    order_id = gen_order_id()
    
    ctx.user_data.update(amount=amt, dirty=dirty, order_id=order_id)

    caption = (
        f"📦 *MÃ ĐƠN HÀNG:* `#ORD-{order_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Gói nạp: `{fmt(amt)} VND`\n"
        f"💰 Thực nhận: `{fmt(dirty)} VND`\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{get_bank_info_text()}\n\n"
        f"📌 *Lưu ý:* Quét mã QR hoặc chuyển khoản chính xác số tiền trên.\n\n"
        f"📸 *Bước 1:* Sau khi chuyển khoản xong, vui lòng gửi **ảnh chụp biên lai / màn hình chuyển khoản** trước:"
    )

    if state.get("qr_file_id"):
        await query.message.reply_photo(photo=state["qr_file_id"], caption=caption, parse_mode="Markdown")
    else:
        await query.message.reply_text(caption, parse_mode="Markdown")

    return WAIT_PROOF

async def on_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    ctx.user_data["photo_file_id"] = photo.file_id

    await update.message.reply_text(
        f"✅ Đã nhận được ảnh biên lai của bạn!\n\n"
        f"👉 *Bước 2:* Bây giờ vui lòng nhập **thông tin nhận tiền** theo mẫu:\n"
        f"`Tên Chủ Tài Khoản - Số Tài Khoản - Tên Ngân Hàng`\n"
        f"(Ví dụ: `NGUYEN VAN A - 0123456789 - VCB`)",
        parse_mode="Markdown",
    )
    return WAIT_CUST_INFO

async def on_cust_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user         = update.effective_user
    customer_info = update.message.text.strip()
    amt          = ctx.user_data.get("amount", 0)
    dirty        = ctx.user_data.get("dirty", 0)
    order_id     = ctx.user_data.get("order_id", "000000")
    photo_file_id = ctx.user_data.get("photo_file_id")

    admin_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt", callback_data=f"app_{user.id}_{order_id}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{user.id}_{order_id}")
        ],
        [
            InlineKeyboardButton("🔨 Cấm user", callback_data=f"ban_{user.id}"),
            InlineKeyboardButton("⚠️ Cảnh báo", callback_data=f"warn_{user.id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        await ctx.bot.send_photo(
            chat_id=admin_id,
            photo=photo_file_id,
            caption=(
                f"📸 *BIÊN LAI ĐƠN HÀNG* (`#ORD-{order_id}`)\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Telegram: {user.full_name} (@{user.username or 'N/A'}) | `{user.id}`\n"
                f"💵 Chuyển: `{fmt(amt)} VND` ➔ Nhận: `{fmt(dirty)} VND`\n"
                f"🏦 **TT Nhận tiền của KH:**\n`{customer_info}`\n"
                f"━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="Markdown",
            reply_markup=admin_markup
        )

    await update.message.reply_text(
        f"✅ *Hoàn tất gửi thông tin cho đơn `#ORD-{order_id}`!*\n"
        f"Admin đang kiểm tra biên lai và thông tin chuyển khoản, sẽ xử lý sớm nhất cho bạn. 🙏",
        parse_mode="Markdown",
    )
    return ConversationHandler.END

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Đã hủy giao dịch hiện tại.")
    return ConversationHandler.END

# Quản trị viên (Admin)
def admin_only(fn):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            if update.callback_query:
                await update.callback_query.answer("⛔ Bạn không có quyền quản trị.", show_alert=True)
            else:
                await update.message.reply_text("⛔ Bạn không có quyền thực hiện lệnh này.")
            return
        return await fn(update, ctx)
    return wrapper

@admin_only
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ *BẢNG ĐIỀU KHIỂN ADMIN*", parse_mode="Markdown", reply_markup=admin_menu_markup())

@admin_only
async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "adm_rate":
        await query.message.reply_text("Nhập tỉ lệ mới (Ví dụ: `7.5` hoặc `8`):", parse_mode="Markdown")
        return WAIT_NEW_RATE
    elif data == "adm_options":
        await query.message.reply_text("Nhập danh sách mức giá cách nhau bằng dấu phẩy (Ví dụ: `100000, 200000, 500000`):")
        return WAIT_NEW_OPTIONS
    elif data == "adm_bank":
        await query.message.reply_text("Nhập thông tin ngân hàng mới theo cú pháp:\n`TênNH | SốTK | ChủTK`", parse_mode="Markdown")
        return WAIT_BANK_INFO
    elif data == "adm_qr_info":
        await query.message.reply_text("Gửi ảnh mã QR mới:")
        return WAIT_QR_IMAGE
    elif data == "adm_close":
        await query.message.delete()
        return ConversationHandler.END

    parts = data.split("_")
    action = parts[0]

    if action == "app":
        target_user_id = parts[1]
        order_id = parts[2]
        try:
            await ctx.bot.send_message(
                chat_id=int(target_user_id),
                text=f"🎉 *Đơn hàng `#ORD-{order_id}` của bạn đã được Admin duyệt thành công!*\nTiền đang được chuyển khoản cho bạn.",
                parse_mode="Markdown"
            )
        except Exception: pass
        await query.edit_message_caption(caption=query.message.caption + "\n\n🟢 **[ĐÃ DUYỆT]**", parse_mode="Markdown")

    elif action == "rej":
        target_user_id = parts[1]
        order_id = parts[2]
        try:
            await ctx.bot.send_message(
                chat_id=int(target_user_id),
                text=f"❌ *Đơn hàng `#ORD-{order_id}` của bạn đã bị từ chối.* Vui lòng liên hệ Admin để biết thêm chi tiết.",
                parse_mode="Markdown"
            )
        except Exception: pass
        await query.edit_message_caption(caption=query.message.caption + "\n\n🔴 **[ĐÃ TỪ CHỐI]**", parse_mode="Markdown")

    elif action == "ban":
        target_user_id = int(parts[1])
        ctx.user_data["ban_target"] = target_user_id
        await query.message.reply_text("Nhập số ngày cấm (Nhập `0` để cấm vĩnh viễn):")
        return WAIT_BAN_DAYS

    elif action == "warn":
        target_user_id = int(parts[1])
        ctx.user_data["warn_target"] = target_user_id
        await query.message.reply_text("Nhập nội dung cảnh báo gửi cho user:")
        return WAIT_WARN_TEXT

@admin_only
async def set_rate_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        new_rate = float(update.message.text.strip())
        state["rate"] = new_rate
        save_state()
        await update.message.reply_text(f"✅ Đã cập nhật tỉ lệ thành công: `1:{new_rate}`", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Tỉ lệ không hợp lệ. Vui lòng nhập số.")
    return ConversationHandler.END

@admin_only
async def set_options_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        opts = [int(x.strip()) for x in update.message.text.split(",")]
        state["options"] = opts
        save_state()
        await update.message.reply_text(f"✅ Đã cập nhật mức giá thành công!")
    except ValueError:
        await update.message.reply_text("❌ Định dạng không hợp lệ.")
    return ConversationHandler.END

@admin_only
async def set_bank_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        parts = [p.strip() for p in update.message.text.split("|")]
        if len(parts) == 3:
            state["bank_name"] = parts[0]
            state["bank_stk"] = parts[1]
            state["bank_owner"] = parts[2]
            save_state()
            await update.message.reply_text("✅ Đã cập nhật thông tin ngân hàng thành công!")
        else:
            await update.message.reply_text("❌ Sai cú pháp. Nhập: `TênNH | SốTK | ChủTK`", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ Có lỗi xảy ra.")
    return ConversationHandler.END

@admin_only
async def set_qr_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo = update.message.photo[-1]
        state["qr_file_id"] = photo.file_id
        save_state()
        await update.message.reply_text("✅ Đã cập nhật mã QR thành công!")
    else:
        await update.message.reply_text("❌ Vui lòng gửi một bức ảnh hợp lệ.")
    return ConversationHandler.END

@admin_only
async def set_ban_days_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text.strip())
        target_user_id = ctx.user_data.get("ban_target")
        unban_time = 0 if days == 0 else time.time() + days * 86400
        bans[str(target_user_id)] = unban_time
        save_bans()
        await update.message.reply_text(f"🔨 Đã cấm user `{target_user_id}` thành công!", parse_mode="Markdown")
        try:
            await ctx.bot.send_message(chat_id=target_user_id, text="⛔ Tài khoản của bạn đã bị cấm khỏi hệ thống.")
        except: pass
    except ValueError:
        await update.message.reply_text("❌ Số ngày không hợp lệ.")
    return ConversationHandler.END

@admin_only
async def set_warn_text_step(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    warn_text = update.message.text.strip()
    target_user_id = ctx.user_data.get("warn_target")
    try:
        await ctx.bot.send_message(chat_id=target_user_id, text=f"⚠️ *CẢNH BÁO TỪ ADMIN:*\n{warn_text}", parse_mode="Markdown")
        await update.message.reply_text("⚠️ Đã gửi cảnh báo cho user thành công!")
    except Exception:
        await update.message.reply_text("❌ Không thể gửi tin nhắn cho user này.")
    return ConversationHandler.END


def main():
    # Khởi động Flask Server ngầm trên 1 thread riêng biệt cho Render
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Khởi động Telegram Bot
    app = Application.builder().token(BOT_TOKEN).build()

    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(on_buy, pattern="^buy_")],
        states={
            WAIT_PROOF: [MessageHandler(filters.PHOTO, on_proof)],
            WAIT_CUST_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_cust_info)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^(adm_|app_|rej_|ban_|warn_)")],
        states={
            WAIT_NEW_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_rate_step)],
            WAIT_NEW_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_options_step)],
            WAIT_BANK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_bank_step)],
            WAIT_QR_IMAGE: [MessageHandler(filters.PHOTO, set_qr_step)],
            WAIT_BAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_ban_days_step)],
            WAIT_WARN_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_warn_text_step)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(buy_conv)
    app.add_handler(admin_conv)

    print("Bot đang chạy thành công!")
    app.run_polling()

if __name__ == "__main__":
    main()
