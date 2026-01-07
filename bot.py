import os
import telebot
from telebot import types  # клавиатуры
import time

# 👉 Токен берём из переменной окружения
TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ---------- НАСТРОЙКИ ----------
REF_VIP_THRESHOLD = 3     # сколько приглашений нужно, чтобы показывать "VIP-очередь"
ONLINE_WINDOW = 600       # окно для "онлайн" в секундах (10 минут)

# ---------- ХРАНИЛКИ СОСТОЯНИЯ ----------

waiting_users = []              # список user_id
pairs = {}                      # user_id -> partner_id
user_gender = {}                # user_id -> "M"/"F"
user_age = {}                   # user_id -> int
desired_partner_gender = {}     # user_id -> None / "M" / "F"
waiting_for_age = set()         # user_id, от которых ждём возраст
chat_start_time = {}            # user_id -> timestamp начала чата

last_partner = {}               # user_id -> последний собеседник (для оценки)
user_likes_received = {}        # user_id -> int
user_dislikes_received = {}     # user_id -> int

last_seen = {}                  # user_id -> last activity timestamp

ref_inviter = {}                # user_id -> inviter_id
ref_count = {}                  # inviter_id -> int (сколько он привёл)

# Простейший список слов для фильтрации порнографического контента
BAD_WORDS = [
    "porn", "sex", "nude", "xxx",
    "порно", "секс", "голый", "голая", "голые",
    "эротика", "эротич", "вагин", "член", "минет",
    "оральн", "анал", "анальный", "оральный",
]

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------


def touch_user(user_id: int) -> None:
    """Обновляем время последней активности пользователя."""
    last_seen[user_id] = time.time()


def get_partner(user_id: int):
    return pairs.get(user_id)


def remove_from_waiting(user_id: int) -> None:
    """Безопасно убираем пользователя из очереди."""
    try:
        waiting_users.remove(user_id)
    except ValueError:
        pass


def main_keyboard() -> types.ReplyKeyboardMarkup:
    """Основная клавиатура."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("🔍 Найти собеседника"))
    kb.row(
        types.KeyboardButton("👨 Искать парня"),
        types.KeyboardButton("👩 Искать девушку"),
    )
    kb.row(
        types.KeyboardButton("⛔ Стоп"),
        types.KeyboardButton("ℹ️ Помощь"),
    )
    kb.row(
        types.KeyboardButton("👤 Профиль"),
        types.KeyboardButton("📊 Статистика"),
    )
    kb.row(types.KeyboardButton("🎁 Бонусы"))
    return kb


def gender_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(
        types.KeyboardButton("👨 Я парень"),
        types.KeyboardButton("👩 Я девушка"),
    )
    return kb


def profile_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(
        types.KeyboardButton("🔄 Изменить пол"),
        types.KeyboardButton("🎂 Изменить возраст"),
    )
    kb.row(types.KeyboardButton("⬅️ В меню"))
    return kb


def ask_age(user_id: int, chat_id: int) -> None:
    """Запрос возраста у пользователя."""
    waiting_for_age.add(user_id)
    bot.send_message(
        chat_id,
        "Введите, пожалуйста, ваш возраст цифрой (например, 18):"
    )


def ensure_profile_complete(user_id: int, chat_id: int) -> bool:
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


def is_compatible(user_a: int, user_b: int) -> bool:
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


def start_search(user_id: int, chat_id: int, mode=None) -> None:
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

    desired_partner_gender[user_id] = mode

    partner_id = None
    for other_id in waiting_users:
        if is_compatible(user_id, other_id):
            partner_id = other_id
            break

    if partner_id is not None:
        # нашёлся подходящий собеседник
        remove_from_waiting(partner_id)

        pairs[user_id] = partner_id
        pairs[partner_id] = user_id

        now = time.time()
        chat_start_time[user_id] = now
        chat_start_time[partner_id] = now

        desired_partner_gender.pop(user_id, None)
        desired_partner_gender.pop(partner_id, None)

        bot.send_message(chat_id, "✅ Собеседник найден! Можете писать, отправлять фото и позже медиа.")
        bot.send_message(partner_id, "✅ Собеседник найден! Можете писать, отправлять фото и позже медиа.")
    else:
        # никого подходящего нет — встаём в очередь
        waiting_users.append(user_id)
        invites = ref_count.get(user_id, 0)
        if invites >= REF_VIP_THRESHOLD:
            text = (
                "🚀 Вы в <b>VIP-очереди</b>! Как только появится подходящий собеседник — "
                "я постараюсь соединить вас как можно быстрее 😉"
            )
        else:
            text = "Вы в очереди. Как только появится подходящий собеседник — я соединю вас."
        bot.send_message(chat_id, text)


def gender_to_text(g: str) -> str:
    return {"M": "парень", "F": "девушка"}.get(g, "не указан")


def can_send_media(user_id: int) -> bool:
    """Первые 30 секунд после начала диалога запрещаем медиа/стикеры/гиф/видео."""
    start = chat_start_time.get(user_id)
    if not start:
        return True
    return time.time() - start >= 30


def contains_bad_words(text: str) -> bool:
    """Проверяем, есть ли в тексте запрещённые слова."""
    t = text.lower()
    return any(word in t for word in BAD_WORDS)


def get_rating(user_id: int):
    """Возвращает (лайки, дизлайки) пользователя."""
    return user_likes_received.get(user_id, 0), user_dislikes_received.get(user_id, 0)


def inc_like(user_id: int, delta: int = 1) -> None:
    """Увеличить лайки у пользователя."""
    if delta <= 0:
        return
    user_likes_received[user_id] = user_likes_received.get(user_id, 0) + delta


def get_bot_username() -> str:
    """Безопасно получаем username бота для реф-ссылок."""
    try:
        return bot.get_me().username or "your_bot"
    except Exception:
        return "your_bot"


def build_ref_link(user_id: int) -> str:
    return f"https://t.me/{get_bot_username()}?start={user_id}"


def send_stats(user_id: int, chat_id: int) -> None:
    """Отправка статистики: онлайн, очередь, активные чаты, рейтинг пользователя."""
    now = time.time()
    online = sum(1 for ts in last_seen.values() if now - ts < ONLINE_WINDOW)
    in_queue = len(waiting_users)
    active_chats = len(pairs) // 2
    total_users = len(user_gender)

    likes, dislikes = get_rating(user_id)

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Онлайн (за последние 10 минут): <b>{online}</b>\n"
        f"Сейчас в очереди: <b>{in_queue}</b>\n"
        f"Активных чатов: <b>{active_chats}</b>\n"
        f"Всего пользователей: <b>{total_users}</b>\n\n"
        f"Ваш рейтинг: 👍 <b>{likes}</b> / 👎 <b>{dislikes}</b>"
    )

    bot.send_message(chat_id, text, reply_markup=main_keyboard())


def send_rate_request(user_id: int) -> None:
    """Отправляем пользователю запрос оценить собеседника."""
    if user_id not in last_partner:
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("👍 Нравился", callback_data="rate_like"),
        types.InlineKeyboardButton("👎 Не очень", callback_data="rate_dislike"),
    )
    bot.send_message(user_id, "Оцените собеседника:", reply_markup=kb)


def send_bonus_info(user_id: int, chat_id: int) -> None:
    """Информация о реферальной ссылке и приглашениях."""
    invites = ref_count.get(user_id, 0)
    likes, dislikes = get_rating(user_id)
    ref_link = build_ref_link(user_id)

    vip = invites >= REF_VIP_THRESHOLD
    if vip:
        vip_status = "✅ У вас активирован <b>VIP-статус</b> в очереди."
    else:
        remaining = max(REF_VIP_THRESHOLD - invites, 1)
        vip_status = (
            f"Чтобы получить <b>VIP-очередь</b>, пригласите ещё <b>{remaining}</b> человек(а)."
        )

    text = (
        "🎁 <b>Бонусы и приглашения</b>\n\n"
        "Поделитесь этой ссылкой, чтобы друзья заходили в чат по вашей рефералке:\n"
        f"<code>{ref_link}</code>\n\n"
        f"Вы уже пригласили: <b>{invites}</b> человек(а).\n"
        "За каждого приглашённого вам добавляется +1 👍 к рейтингу.\n\n"
        f"{vip_status}\n\n"
        f"Ваш текущий рейтинг: 👍 <b>{likes}</b> / 👎 <b>{dislikes}</b>"
    )

    bot.send_message(chat_id, text, reply_markup=main_keyboard())


def send_leaderboard(chat_id: int, current_user_id: int) -> None:
    """Лидерборд по приглашениям."""
    if not ref_count:
        bot.send_message(
            chat_id,
            "🏆 Пока никто никого не пригласил.\n"
            "Станьте первым — используйте /bonus и делитесь ссылкой!",
            reply_markup=main_keyboard()
        )
        return

    sorted_refs = sorted(ref_count.items(), key=lambda kv: kv[1], reverse=True)
    top_n = sorted_refs[:10]

    lines = ["🏆 <b>Топ-10 по приглашениям</b>\n"]
    position_of_user = None

    for idx, (uid, cnt) in enumerate(sorted_refs, start=1):
        if uid == current_user_id:
            position_of_user = (idx, cnt)
            break

    for rank, (uid, cnt) in enumerate(top_n, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")
        marker = "  <b>(это вы)</b>" if uid == current_user_id else ""
        lines.append(f"{medal} ID <code>{uid}</code> — <b>{cnt}</b> приглашений{marker}")

    if position_of_user is None:
        me_line = "\nВы пока не в топе. Приглашайте друзей через /bonus!"
    else:
        pos, cnt = position_of_user
        me_line = (
            f"\n📌 Ваша позиция: <b>#{pos}</b> с <b>{cnt}</b> приглашениями.\n"
            "Продолжайте — легко ворваться в топ!"
        )

    text = "\n".join(lines) + me_line
    bot.send_message(chat_id, text, reply_markup=main_keyboard())


# ---------- КОМАНДЫ ----------


@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)

    # --- РЕФЕРАЛЬНАЯ ЛОГИКА ---
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        payload = parts[1]
        try:
            inviter_id = int(payload)
            if inviter_id != user_id and user_id not in ref_inviter:
                ref_inviter[user_id] = inviter_id
                ref_count[inviter_id] = ref_count.get(inviter_id, 0) + 1
                inc_like(inviter_id, 1)

                invites = ref_count[inviter_id]
                try:
                    bot.send_message(
                        inviter_id,
                        "🎉 <b>По вашей ссылке пришёл новый человек!</b>\n"
                        f"Всего приглашений: <b>{invites}</b>.\n"
                        "Спасибо, что помогаете чату расти ❤️"
                    )
                except Exception:
                    pass
        except ValueError:
            pass

    # --- ПРОФИЛЬ / ПРИВЕТСТВИЕ ---
    if user_id not in user_gender or user_id not in user_age:
        if user_id not in user_gender:
            bot.send_message(
                chat_id,
                "Привет! 👋\n\nЭто анонимный чат 1-на-1.\n\nСначала выберите, кто вы:",
                reply_markup=gender_keyboard()
            )
        else:
            bot.send_message(
                chat_id,
                "Привет ещё раз! Осталось указать возраст.",
            )
            ask_age(user_id, chat_id)
    else:
        bot.send_message(
            chat_id,
            "С возвращением! 👋\n\n"
            "Используйте кнопки снизу для поиска собеседника.\n"
            "Команда /profile покажет ваш профиль.\n"
            "Команда /bonus — ваша личная ссылка и бонусы.",
            reply_markup=main_keyboard()
        )


@bot.message_handler(commands=["stop"])
def handle_stop(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    partner_id = get_partner(user_id)

    if partner_id:
        # сохраняем последнего собеседника для оценки
        last_partner[user_id] = partner_id
        last_partner[partner_id] = user_id

        pairs.pop(user_id, None)
        pairs.pop(partner_id, None)
        chat_start_time.pop(user_id, None)
        chat_start_time.pop(partner_id, None)

        bot.send_message(user_id, "❌ Вы завершили разговор.", reply_markup=main_keyboard())
        bot.send_message(partner_id, "❌ Собеседник завершил разговор.", reply_markup=main_keyboard())

        # запрос оценки
        send_rate_request(user_id)
        send_rate_request(partner_id)
        return

    if user_id in waiting_users:
        remove_from_waiting(user_id)
        desired_partner_gender.pop(user_id, None)
        bot.send_message(user_id, "Вы вышли из очереди.", reply_markup=main_keyboard())
        return

    bot.send_message(user_id, "Вы сейчас ни с кем не общаетесь.", reply_markup=main_keyboard())


@bot.message_handler(commands=["help"])
def handle_help(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    bot.send_message(
        chat_id,
        "ℹ️ <b>Справка</b>\n\n"
        "🔍 Найти собеседника — без фильтра по полу\n"
        "👨 Искать парня — искать только парней\n"
        "👩 Искать девушку — искать только девушек\n"
        "⛔ Стоп — завершить разговор или выйти из очереди\n"
        "👤 Профиль /profile — посмотреть и изменить пол/возраст\n"
        "📊 Статистика — онлайн, очередь, активные чаты и ваш рейтинг\n"
        "🎁 /bonus — ваша личная приглашалка и бонусы\n"
        "🏆 /top — лидерборд по приглашениям\n\n"
        "После завершения чата можно оценить собеседника 👍👎\n\n"
        "Первые 30 секунд диалога нельзя отправлять стикеры, GIF и видео.\n"
        "Запрещён порнографический контент.",
        reply_markup=main_keyboard()
    )


@bot.message_handler(commands=["profile"])
def handle_profile(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    g = gender_to_text(user_gender.get(user_id))
    a = user_age.get(user_id)
    likes, dislikes = get_rating(user_id)
    invites = ref_count.get(user_id, 0)

    text = "👤 <b>Ваш профиль</b>\n\n"
    text += f"Пол: <b>{g}</b>\n"
    text += f"Возраст: <b>{a}</b>\n" if a is not None else "Возраст: <b>не указан</b>\n"
    text += f"Рейтинг: 👍 <b>{likes}</b> / 👎 <b>{dislikes}</b>\n"
    text += f"Приглашено друзей: <b>{invites}</b>\n"
    text += "\nВы можете изменить пол или возраст кнопками ниже.\n"
    text += "А в /bonus — ваша личная пригласительная ссылка."

    bot.send_message(chat_id, text, reply_markup=profile_keyboard())


@bot.message_handler(commands=["bonus"])
def handle_bonus(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    send_bonus_info(user_id, chat_id)


@bot.message_handler(commands=["top"])
def handle_top(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    send_leaderboard(chat_id, user_id)


# ---------- ВЫБОР ПОЛА (кнопки) ----------


@bot.message_handler(func=lambda m: m.text in ["👨 Я парень", "👩 Я девушка"])
def handle_gender_select(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)

    user_gender[user_id] = "M" if message.text == "👨 Я парень" else "F"

    if user_id not in user_age:
        bot.send_message(
            chat_id,
            "Отлично, я запомнил 👍\nТеперь укажите ваш возраст.",
        )
        ask_age(user_id, chat_id)
    else:
        bot.send_message(chat_id, "Пол обновлён 👍", reply_markup=main_keyboard())


# ---------- ОЦЕНКА СОБЕСЕДНИКА (INLINE) ----------


@bot.callback_query_handler(func=lambda c: c.data in ["rate_like", "rate_dislike"])
def handle_rating_callback(call):
    user_id = call.from_user.id
    touch_user(user_id)
    partner_id = last_partner.get(user_id)

    if not partner_id:
        bot.answer_callback_query(call.id, "Пока некого оценивать 🙂")
        return

    if call.data == "rate_like":
        inc_like(partner_id, 1)
        msg = "Спасибо! 👍 Я учту ваш лайк."
    else:
        user_dislikes_received[partner_id] = user_dislikes_received.get(partner_id, 0) + 1
        msg = "Спасибо за отзыв 👌"

    # запрет повторной оценки
    last_partner.pop(user_id, None)

    # убираем кнопки у сообщения
    try:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )
    except Exception:
        pass

    bot.answer_callback_query(call.id, "Оценка сохранена")
    bot.send_message(user_id, msg)


# ---------- ОБРАБОТКА ТЕКСТА ----------


@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    touch_user(user_id)

    # команды обрабатываются отдельно
    if text.startswith("/"):
        return

    # Ввод возраста
    if user_id in waiting_for_age:
        if text.isdigit():
            age = int(text)
            if 10 <= age <= 100:
                user_age[user_id] = age
                waiting_for_age.remove(user_id)
                bot.send_message(
                    chat_id,
                    f"Возраст записан: {age} 🎂",
                    reply_markup=main_keyboard()
                )
            else:
                bot.send_message(chat_id, "Введите, пожалуйста, реальный возраст от 10 до 100:")
        else:
            bot.send_message(chat_id, "Возраст нужно ввести цифрами, например: 18")
        return

    # Кнопки меню
    if text == "🔍 Найти собеседника":
        start_search(user_id, chat_id, mode=None)
        return
    if text == "👨 Искать парня":
        start_search(user_id, chat_id, mode="M")
        return
    if text == "👩 Искать девушку":
        start_search(user_id, chat_id, mode="F")
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
    if text == "📊 Статистика":
        send_stats(user_id, chat_id)
        return
    if text == "🎁 Бонусы":
        send_bonus_info(user_id, chat_id)
        return
    if text == "🔄 Изменить пол":
        bot.send_message(chat_id, "Выберите новый пол:", reply_markup=gender_keyboard())
        return
    if text == "🎂 Изменить возраст":
        ask_age(user_id, chat_id)
        return
    if text == "⬅️ В меню":
        bot.send_message(chat_id, "Возврат в меню.", reply_markup=main_keyboard())
        return

    # Обычные сообщения в чате
    if not ensure_profile_complete(user_id, chat_id):
        return

    partner_id = get_partner(user_id)

    if user_id in waiting_users and not partner_id:
        bot.send_message(user_id, "Вы в очереди, дождитесь собеседника или нажмите ⛔ Стоп.")
        return

    if not partner_id:
        bot.send_message(user_id, "Вы не в чате. Используйте кнопки для поиска.", reply_markup=main_keyboard())
        return

    if contains_bad_words(text):
        bot.send_message(user_id, "🚫 Сообщение отклонено: запрещённый контент.")
        return

    try:
        bot.send_message(partner_id, text)
    except Exception as e:
        print("Ошибка при отправке текста:", e)
        bot.send_message(user_id, "Не удалось доставить сообщение собеседнику.")


# ---------- МЕДИА ----------


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    partner_id = get_partner(user_id)

    if not ensure_profile_complete(user_id, chat_id):
        return

    if not partner_id:
        bot.send_message(user_id, "Сначала найдите собеседника.", reply_markup=main_keyboard())
        return

    file_id = message.photo[-1].file_id
    try:
        bot.send_photo(partner_id, file_id, caption=message.caption or "")
    except Exception as e:
        print("Ошибка при отправке фото:", e)
        bot.send_message(user_id, "Не удалось доставить фото собеседнику.")


@bot.message_handler(content_types=["sticker"])
def handle_sticker(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    partner_id = get_partner(user_id)

    if not ensure_profile_complete(user_id, chat_id):
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


@bot.message_handler(content_types=["video", "animation"])
def handle_video_or_gif(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    touch_user(user_id)
    partner_id = get_partner(user_id)

    if not ensure_profile_complete(user_id, chat_id):
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


# ---------- ЗАПУСК ----------

if __name__ == "__main__":
    print("Бот запущен (анонимный чат + профиль + рейтинг + статистика + рефералка + лидерборд)...")
    bot.infinity_polling()
