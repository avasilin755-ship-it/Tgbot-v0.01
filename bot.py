
import telebot
from telebot import types  # клавиатуры
import time

# 👉 ВСТАВЬ СЮДА СВОЙ ТОКЕН
TOKEN = "8401776638:AAHOKWF0qm0oxI96Udg4fjkO5VKyoPkKLDc"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Очередь ожидающих пользователей
waiting_users = []  # список user_id

# Активные пары: user_id -> partner_id
pairs = {}

# Пол пользователя: user_id -> "M" или "F"
user_gender = {}

# Возраст пользователя: user_id -> int
user_age = {}

# Желаемый пол партнёра на текущий поиск: user_id -> None / "M" / "F"
desired_partner_gender = {}

# Пользователи, от которых ждём ввод возраста
waiting_for_age = set()

# Время начала текущего чата: user_id -> timestamp
chat_start_time = {}

# Простейший список слов для фильтрации порнографического контента
BAD_WORDS = [
    "porn", "sex", "nude", "xxx",
    "порно", "секс", "голый", "голая", "голые",
    "эротика", "эротич", "вагин", "член", "минет",
    "оральн", "анал", "анальный", "оральный",
]


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------

def get_partner(user_id):
    return pairs.get(user_id)


def remove_from_waiting(user_id):
    try:
        waiting_users.remove(user_id)
    except ValueError:
        pass


def main_keyboard():
    """Основная клавиатура под полем ввода."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_any = types.KeyboardButton("🔍 Найти собеседника")
    btn_m = types.KeyboardButton("👨 Искать парня")
    btn_f = types.KeyboardButton("👩 Искать девушку")
    btn_stop = types.KeyboardButton("⛔ Стоп")
    btn_help = types.KeyboardButton("ℹ️ Помощь")
    btn_profile = types.KeyboardButton("👤 Профиль")
    kb.row(btn_any)
    kb.row(btn_m, btn_f)
    kb.row(btn_stop, btn_help)
    kb.row(btn_profile)
    return kb


def gender_keyboard():
    """Клавиатура выбора пола."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn_m = types.KeyboardButton("👨 Я парень")
    btn_f = types.KeyboardButton("👩 Я девушка")
    kb.row(btn_m, btn_f)
    return kb


def profile_keyboard():
    """Клавиатура управления профилем."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_change_gender = types.KeyboardButton("🔄 Изменить пол")
    btn_change_age = types.KeyboardButton("🎂 Изменить возраст")
    btn_back = types.KeyboardButton("⬅️ В меню")
    kb.row(btn_change_gender, btn_change_age)
    kb.row(btn_back)
    return kb


def ask_age(user_id, chat_id):
    """Запрос возраста у пользователя."""
    waiting_for_age.add(user_id)
    bot.send_message(
        chat_id,
        "Введите, пожалуйста, ваш возраст цифрой (например, 18):"
    )


def ensure_profile_complete(user_id, chat_id):
    """Проверяем, указан ли пол и возраст. Если нет — просим указать."""
    if user_id not in user_gender:
        bot.send_message(
            chat_id,
            "Перед началом выберите, кто вы:",
            reply_markup=gender_keyboard()
        )
        return False

    if user_id not in user_age:
        ask_age(user_id, chat_id)
        return False

    return True


def is_compatible(user_a, user_b):
    """Проверка по полу и желаемому полу."""
    ga = user_gender.get(user_a)
    gb = user_gender.get(user_b)
    da = desired_partner_gender.get(user_a)
    db = desired_partner_gender.get(user_b)

    # если вдруг у кого-то не указан пол — допускаем
    if ga is None or gb is None:
        return True

    if da is not None and gb != da:
        return False
    if db is not None and ga != db:
        return False
    return True


def start_search(user_id, chat_id, mode=None):
    """
    mode:
      None  -> любой пол
      "M"   -> искать только парней
      "F"   -> искать только девушек
    """
    if not ensure_profile_complete(user_id, chat_id):
        return

    if get_partner(user_id):
        bot.send_message(chat_id, "Вы уже в чате. Используйте ⛔ Стоп, чтобы закончить разговор.")
        return

    if user_id in waiting_users:
        bot.send_message(chat_id, "Вы уже в очереди, ждём собеседника…")
        return

    desired_partner_gender[user_id] = mode  # None, "M" или "F"

    partner_id = None
    for other_id in waiting_users:
        if is_compatible(user_id, other_id):
            partner_id = other_id
            break

    if partner_id is not None:
        remove_from_waiting(partner_id)

        pairs[user_id] = partner_id
        pairs[partner_id] = user_id

        # фиксируем время начала чата для антиспама по медиа
        now = time.time()
        chat_start_time[user_id] = now
        chat_start_time[partner_id] = now

        desired_partner_gender.pop(user_id, None)
        desired_partner_gender.pop(partner_id, None)

        bot.send_message(chat_id, "✅ Собеседник найден! Можете писать, отправлять фото и позже медиа.")
        bot.send_message(partner_id, "✅ Собеседник найден! Можете писать, отправлять фото и позже медиа.")
    else:
        waiting_users.append(user_id)
        bot.send_message(chat_id, "Вы в очереди. Как только появится подходящий собеседник — я соединю вас.")


def gender_to_text(g):
    if g == "M":
        return "парень"
    if g == "F":
        return "девушка"
    return "не указан"


def can_send_media(user_id):
    """Первые 30 секунд после начала диалога запрещаем медиа/стикеры/гиф/видео."""
    start = chat_start_time.get(user_id)
    if not start:
        return True  # если нет данных — не ограничиваем
    if time.time() - start < 30:
        return False
    return True


def contains_bad_words(text: str) -> bool:
    """Проверяем, есть ли в тексте запрещённые слова."""
    t = text.lower()
    for word in BAD_WORDS:
        if word in t:
            return True
    return False


# ---------- КОМАНДЫ ----------

@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id

    if user_id not in user_gender or user_id not in user_age:
        # новый или неполный профиль
        if user_id not in user_gender:
            bot.send_message(
                message.chat.id,
                "Привет! 👋\n\nЭто анонимный чат 1-на-1.\n\nСначала выберите, кто вы:",
                reply_markup=gender_keyboard()
            )
        else:
            # пол уже есть, но нет возраста
            bot.send_message(
                message.chat.id,
                "Привет ещё раз! Осталось указать возраст.",
            )
            ask_age(user_id, message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "С возвращением! 👋\n\n"
            "Используйте кнопки снизу для поиска собеседника.\n"
            "Команда /profile покажет ваш профиль.",
            reply_markup=main_keyboard()
        )


@bot.message_handler(commands=["stop"])
def handle_stop(message):
    user_id = message.from_user.id
    partner_id = get_partner(user_id)

    if partner_id:
        pairs.pop(user_id, None)
        pairs.pop(partner_id, None)
        # можно очистить время чата, но не обязательно
        chat_start_time.pop(user_id, None)
        chat_start_time.pop(partner_id, None)
        bot.send_message(user_id, "❌ Вы завершили разговор.", reply_markup=main_keyboard())
        bot.send_message(partner_id, "❌ Собеседник завершил разговор.", reply_markup=main_keyboard())
        return

    if user_id in waiting_users:
        remove_from_waiting(user_id)
        desired_partner_gender.pop(user_id, None)
        bot.send_message(user_id, "Вы вышли из очереди.", reply_markup=main_keyboard())
        return

    bot.send_message(user_id, "Вы сейчас ни с кем не общаетесь.", reply_markup=main_keyboard())


@bot.message_handler(commands=["help"])
def handle_help(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>Справка</b>\n\n"
        "🔍 Найти собеседника — без фильтра по полу\n"
        "👨 Искать парня — искать только парней\n"
        "👩 Искать девушку — искать только девушек\n"
        "⛔ Стоп — завершить разговор или выйти из очереди\n"
        "👤 Профиль /profile — посмотреть и изменить пол/возраст\n\n"
        "Первые 30 секунд диалога нельзя отправлять стикеры, GIF и видео.\n"
        "Запрещён порнографический контент.",
        reply_markup=main_keyboard()
    )


@bot.message_handler(commands=["profile"])
def handle_profile(message):
    user_id = message.from_user.id
    g = gender_to_text(user_gender.get(user_id))
    a = user_age.get(user_id)

    text = "👤 <b>Ваш профиль</b>\n\n"
    text += f"Пол: <b>{g}</b>\n"
    if a is not None:
        text += f"Возраст: <b>{a}</b>\n"
    else:
        text += "Возраст: <b>не указан</b>\n"

    text += "\nВы можете изменить пол или возраст кнопками ниже."

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=profile_keyboard()
    )


# ---------- ВЫБОР ПОЛА (кнопки) ----------

@bot.message_handler(func=lambda m: m.text in ["👨 Я парень", "👩 Я девушка"])
def handle_gender_select(message):
    user_id = message.from_user.id

    if message.text == "👨 Я парень":
        user_gender[user_id] = "M"
    else:
        user_gender[user_id] = "F"

    # После выбора пола — если возраста нет, просим возраст
    if user_id not in user_age:
        bot.send_message(
            message.chat.id,
            "Отлично, я запомнил 👍\nТеперь укажите ваш возраст.",
        )
        ask_age(user_id, message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "Пол обновлён 👍",
            reply_markup=main_keyboard()
        )


# ---------- ОБРАБОТКА ТЕКСТА ----------

@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text

    # --- сначала проверяем, не ждём ли мы возраст ---
    if user_id in waiting_for_age:
        if text.isdigit():
            age = int(text)
            # Примитивная проверка адекватного диапазона
            if 10 <= age <= 100:
                user_age[user_id] = age
                waiting_for_age.remove(user_id)
                bot.send_message(
                    message.chat.id,
                    f"Возраст записан: {age} 🎂",
                    reply_markup=main_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Введите, пожалуйста, реальный возраст от 10 до 100:"
                )
        else:
            bot.send_message(
                message.chat.id,
                "Возраст нужно ввести цифрами, например: 18"
            )
        return

    # --- кнопки поиска/меню/профиля ---
    if text == "🔍 Найти собеседника":
        start_search(user_id, message.chat.id, mode=None)
        return
    if text == "👨 Искать парня":
        start_search(user_id, message.chat.id, mode="M")
        return
    if text == "👩 Искать девушку":
        start_search(user_id, message.chat.id, mode="F")
        return
    if text == "⛔ Стоп":
        handle_stop(message)
        return
    if text == "ℹ️ Помощь":
        handle_help(message)
        return
    if text == "👤 Профиль":
        handle_profile(message)
        return
    if text == "🔄 Изменить пол":
        bot.send_message(
            message.chat.id,
            "Выберите новый пол:",
            reply_markup=gender_keyboard()
        )
        return
    if text == "🎂 Изменить возраст":
        ask_age(user_id, message.chat.id)
        return
    if text == "⬅️ В меню":
        bot.send_message(
            message.chat.id,
            "Возврат в меню.",
            reply_markup=main_keyboard()
        )
        return

    # --- обычные сообщения ---

    # профиль не заполнен
    if not ensure_profile_complete(user_id, message.chat.id):
        return

    partner_id = get_partner(user_id)

    if user_id in waiting_users and not partner_id:
        bot.send_message(user_id, "Вы в очереди, дождитесь собеседника или нажмите ⛔ Стоп.")
        return

    if not partner_id:
        bot.send_message(user_id, "Вы не в чате. Используйте кнопки для поиска.", reply_markup=main_keyboard())
        return

    # фильтр порнографического контента
    if contains_bad_words(text):
        bot.send_message(user_id, "🚫 Сообщение отклонено: запрещённый контент.")
        return

    try:
        bot.send_message(partner_id, text)
    except Exception as e:
        print("Ошибка при отправке текста:", e)
        bot.send_message(user_id, "Не удалось доставить сообщение собеседнику.")


# ---------- ОБРАБОТКА ФОТО ----------

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id
    partner_id = get_partner(user_id)

    if not ensure_profile_complete(user_id, message.chat.id):
        return

    if not partner_id:
        bot.send_message(user_id, "Сначала найдите собеседника.", reply_markup=main_keyboard())
        return

    # фото разрешаем сразу, ограничение только для стикеров/гиф/видео по твоему запросу

    file_id = message.photo[-1].file_id
    try:
        bot.send_photo(partner_id, file_id, caption=message.caption or "")
    except Exception as e:
        print("Ошибка при отправке фото:", e)
        bot.send_message(user_id, "Не удалось доставить фото собеседнику.")


# ---------- ОБРАБОТКА СТИКЕРОВ ----------

@bot.message_handler(content_types=["sticker"])
def handle_sticker(message):
    user_id = message.from_user.id
    partner_id = get_partner(user_id)

    if not ensure_profile_complete(user_id, message.chat.id):
        return

    if not partner_id:
        bot.send_message(user_id, "Сначала найдите собеседника.", reply_markup=main_keyboard())
        return

    if not can_send_media(user_id):
        bot.send_message(user_id, "⏳ В первые 30 секунд нельзя отправлять стикеры. Немного подождите.")
        return

    try:
        bot.send_sticker(partner_id, message.sticker.file_id)
    except Exception as e:
        print("Ошибка при отправке стикера:", e)
        bot.send_message(user_id, "Не удалось доставить стикер собеседнику.")


# ---------- ОБРАБОТКА ВИДЕО / GIF (ANIMATION) ----------

@bot.message_handler(content_types=["video", "animation"])
def handle_video_or_gif(message):
    user_id = message.from_user.id
    partner_id = get_partner(user_id)

    if not ensure_profile_complete(user_id, message.chat.id):
        return

    if not partner_id:
        bot.send_message(user_id, "Сначала найдите собеседника.", reply_markup=main_keyboard())
        return

    if not can_send_media(user_id):
        bot.send_message(user_id, "⏳ В первые 30 секунд нельзя отправлять GIF и видео. Немного подождите.")
        return

    file_id = message.video.file_id if message.content_type == "video" else message.animation.file_id

    try:
        if message.content_type == "video":
            bot.send_video(partner_id, file_id, caption=message.caption or "")
        else:
            bot.send_animation(partner_id, file_id, caption=message.caption or "")
    except Exception as e:
        print("Ошибка при отправке видео/GIF:", e)
        bot.send_message(user_id, "Не удалось доставить медиа собеседнику.")


if __name__ == "__main__":
    print("Бот запущен (анонимный чат + пол + возраст + профиль + защита от спама)...")
    bot.infinity_polling()
