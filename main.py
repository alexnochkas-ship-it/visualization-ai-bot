import os
import telebot
from telebot import types
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6203930902"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)
orders = {}

QUESTIONS = [
    ("name", "Как вас зовут?"),
    ("task", "Что нужно визуализировать? Опишите задачу."),
    ("style", "Какие есть пожелания по стилю, цветам, референсам?"),
    ("deadline", "К какому сроку нужно выполнить заказ?"),
    ("contact", "Оставьте контакт для связи: телефон или @username."),
]

def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Заказать визуализацию"))
    return kb

def cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Отмена"))
    return kb

def files_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Готово"))
    kb.add(types.KeyboardButton("Пропустить"))
    kb.add(types.KeyboardButton("Отмена"))
    return kb

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Здравствуйте! Я бот для приёма заказов на визуализацию.\n\n"
        "Нажмите кнопку ниже, чтобы оформить заявку.",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == "Отмена")
def cancel(message):
    orders.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Заявка отменена.", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "Заказать визуализацию")
def new_order(message):
    orders[message.chat.id] = {
        "step": 0,
        "answers": {},
        "files": [],
        "username": message.from_user.username or "",
        "tg_id": message.from_user.id,
        "collecting_files": False,
    }
    bot.send_message(message.chat.id, QUESTIONS[0][1], reply_markup=cancel_keyboard())

@bot.message_handler(content_types=["photo", "document"])
def handle_file(message):
    chat_id = message.chat.id
    if chat_id not in orders:
        bot.send_message(chat_id, "Сначала нажмите «Заказать визуализацию».", reply_markup=main_keyboard())
        return

    order = orders[chat_id]
    if not order.get("collecting_files"):
        bot.send_message(chat_id, "Файлы можно отправить после ответов на вопросы.")
        return

    if message.content_type == "photo":
        file_id = message.photo[-1].file_id
        order["files"].append(("photo", file_id))
        bot.send_message(chat_id, "Фото принято. Можете отправить ещё или нажать «Готово».", reply_markup=files_keyboard())
    elif message.content_type == "document":
        file_id = message.document.file_id
        order["files"].append(("document", file_id))
        bot.send_message(chat_id, "Файл принят. Можете отправить ещё или нажать «Готово».", reply_markup=files_keyboard())

@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id

    if chat_id not in orders:
        bot.send_message(chat_id, "Нажмите «Заказать визуализацию».", reply_markup=main_keyboard())
        return

    order = orders[chat_id]

    if order.get("collecting_files"):
        if message.text in ["Готово", "Пропустить"]:
            finish_order(message)
        else:
            bot.send_message(chat_id, "Отправьте фото/файлы или нажмите «Готово».", reply_markup=files_keyboard())
        return

    step = order["step"]
    key, _ = QUESTIONS[step]
    order["answers"][key] = message.text.strip()
    order["step"] += 1

    if order["step"] < len(QUESTIONS):
        bot.send_message(chat_id, QUESTIONS[order["step"]][1], reply_markup=cancel_keyboard())
    else:
        order["collecting_files"] = True
        bot.send_message(
            chat_id,
            "Теперь отправьте фото/файлы для заказа.\n\nЕсли файлов нет — нажмите «Пропустить». Когда закончите — нажмите «Готово».",
            reply_markup=files_keyboard()
        )

def finish_order(message):
    chat_id = message.chat.id
    order = orders.get(chat_id)
    if not order:
        return

    a = order["answers"]
    username = f"@{order['username']}" if order["username"] else "не указан"

    text = (
        "🆕 <b>Новая заявка на визуализацию</b>\n\n"
        f"👤 <b>Имя:</b> {a.get('name', '-')}\n"
        f"📝 <b>Задача:</b> {a.get('task', '-')}\n"
        f"🎨 <b>Пожелания:</b> {a.get('style', '-')}\n"
        f"⏰ <b>Срок:</b> {a.get('deadline', '-')}\n"
        f"📞 <b>Контакт:</b> {a.get('contact', '-')}\n\n"
        f"Telegram: {username}\n"
        f"ID клиента: <code>{order['tg_id']}</code>"
    )

    bot.send_message(ADMIN_ID, text)

    for kind, file_id in order["files"]:
        if kind == "photo":
            bot.send_photo(ADMIN_ID, file_id)
        elif kind == "document":
            bot.send_document(ADMIN_ID, file_id)

    bot.send_message(
        chat_id,
        "Спасибо! Заявка принята. Мы свяжемся с вами для уточнения деталей.",
        reply_markup=main_keyboard()
    )
    orders.pop(chat_id, None)

@app.route("/", methods=["GET"])
def index():
    return "Bot is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

if WEBHOOK_URL:
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + "/webhook")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
