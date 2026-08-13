import asyncio
import logging
import sys
from datetime import datetime
import aiosqlite

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    BusinessConnection,
    BusinessMessagesDeleted,  # Исправленный импорт
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
BOT_TOKEN = "8138153160:AAF4Zl35mDsuuERANThzY9nMdo_cljhixts"
DB_PATH = "business_messages.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =====================================================================
# КЛАВИАТУРЫ ДЛЯ ЛС С БОТОМ
# =====================================================================
def get_main_keyboard():
    """Главное меню кнопок в личке с ботом."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📜 Команды")],
            [KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True,
    )


async def get_settings_inline_keyboard(user_id: int):
    """Инлайн клавиатура настроек пользователя."""
    settings = await get_user_settings(user_id)
    
    save_media_status = "✅ ВКЛ" if settings["save_media"] else "❌ ВЫКЛ"
    log_edits_status = "✅ ВКЛ" if settings["log_edits"] else "❌ ВЫКЛ"
    only_others_status = "👤 Только собеседник" if settings["only_others"] else "👥 Все сообщения"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Медиафайлы: {save_media_status}",
                    callback_data="toggle_setting:save_media",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Лог изменений: {log_edits_status}",
                    callback_data="toggle_setting:log_edits",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Фильтр отслеживания: {only_others_status}",
                    callback_data="toggle_setting:only_others",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить", callback_data="refresh_settings"
                )
            ],
        ]
    )
    return kb


# =====================================================================
# РАБОТА С БАЗОЙ ДАННЫХ
# =====================================================================
async def init_db():
    """Инициализация БД и таблиц."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                connection_id TEXT PRIMARY KEY,
                user_id INTEGER,
                is_enabled INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                chat_id INTEGER,
                message_id INTEGER,
                connection_id TEXT,
                sender_id INTEGER,
                sender_name TEXT,
                text TEXT,
                media_type TEXT,
                file_id TEXT,
                created_at TEXT,
                PRIMARY KEY (chat_id, message_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS muted_chats (
                connection_id TEXT,
                chat_id INTEGER,
                PRIMARY KEY (connection_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                save_media INTEGER DEFAULT 1,
                log_edits INTEGER DEFAULT 1,
                only_others INTEGER DEFAULT 1
            )
        """)
        await db.commit()


async def save_connection(connection_id: str, user_id: int, is_enabled: bool):
    """Сохранение/обновление состояния подключения."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO connections (connection_id, user_id, is_enabled) VALUES (?, ?, ?)",
            (connection_id, user_id, 1 if is_enabled else 0),
        )
        await db.commit()


async def get_owner_id(connection_id: str) -> int | None:
    """Получение ID владельца бизнеса по connection_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM connections WHERE connection_id = ?",
            (connection_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_user_settings(user_id: int) -> dict:
    """Получение индивидуальных настроек пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT save_media, log_edits, only_others FROM user_settings WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "save_media": bool(row[0]),
                    "log_edits": bool(row[1]),
                    "only_others": bool(row[2]),
                }
            await db.execute(
                "INSERT INTO user_settings (user_id, save_media, log_edits, only_others) VALUES (?, 1, 1, 1)",
                (user_id,),
            )
            await db.commit()
            return {"save_media": True, "log_edits": True, "only_others": True}


async def toggle_setting(user_id: int, setting_key: str):
    """Переключение конкретной настройки."""
    current = await get_user_settings(user_id)
    new_val = 0 if current[setting_key] else 1
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE user_settings SET {setting_key} = ? WHERE user_id = ?",
            (new_val, user_id),
        )
        await db.commit()


async def save_message(
    chat_id: int,
    message_id: int,
    connection_id: str,
    sender_id: int,
    sender_name: str,
    text: str | None,
    media_type: str,
    file_id: str | None,
):
    """Сохранение сообщения в БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO messages 
            (chat_id, message_id, connection_id, sender_id, sender_name, text, media_type, file_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                message_id,
                connection_id,
                sender_id,
                sender_name,
                text,
                media_type,
                file_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        await db.commit()


async def get_saved_message(chat_id: int, message_id: int) -> dict | None:
    """Извлечение сообщения из БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT connection_id, sender_id, sender_name, text, media_type, file_id, created_at 
            FROM messages WHERE chat_id = ? AND message_id = ?
            """,
            (chat_id, message_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "connection_id": row[0],
                    "sender_id": row[1],
                    "sender_name": row[2],
                    "text": row[3],
                    "media_type": row[4],
                    "file_id": row[5],
                    "created_at": row[6],
                }
            return None


async def set_chat_mute(connection_id: str, chat_id: int, mute: bool):
    """Управление мутом в базе данных."""
    async with aiosqlite.connect(DB_PATH) as db:
        if mute:
            await db.execute(
                "INSERT OR IGNORE INTO muted_chats (connection_id, chat_id) VALUES (?, ?)",
                (connection_id, chat_id),
            )
        else:
            await db.execute(
                "DELETE FROM muted_chats WHERE connection_id = ? AND chat_id = ?",
                (connection_id, chat_id),
            )
        await db.commit()


async def is_chat_muted(connection_id: str, chat_id: int) -> bool:
    """Проверка замучен ли чат."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM muted_chats WHERE connection_id = ? AND chat_id = ?",
            (connection_id, chat_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def get_stats(user_id: int) -> dict:
    """Получение статистики бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE connection_id IN (SELECT connection_id FROM connections WHERE user_id = ?)",
            (user_id,),
        ) as cursor:
            msg_count = (await cursor.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM muted_chats WHERE connection_id IN (SELECT connection_id FROM connections WHERE user_id = ?)",
            (user_id,),
        ) as cursor:
            muted_count = (await cursor.fetchone())[0]

    return {"msg_count": msg_count, "muted_count": muted_count}


# =====================================================================
# ХЕНДЛЕРЫ ЛИЧНЫХ СООБЩЕНИЙ С БОТОМ
# =====================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start в ЛС с ботом."""
    text = (
        "👋 **Добро пожаловать в Telegram Business Менеджер!**\n\n"
        "Я помогу вам сохранить все удалённые и изменённые сообщения собеседников, "
        "а также предоставлю команды для быстрого управления чатами.\n\n"
        "Используйте меню ниже для настройки и чтения списка команд 👇"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


@dp.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message):
    """Открытие настроек через кнопку."""
    kb = await get_settings_inline_keyboard(message.from_user.id)
    await message.answer(
        "⚙️ **Панель настроек вашего Telegram Business:**\n"
        "Нажимайте на кнопки ниже для переключения функций.",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@dp.message(F.text == "📜 Команды")
async def btn_commands(message: Message):
    """Просмотр списка доступных команд."""
    text = (
        "📜 **Список команд для отправки в бизнес-чатах:**\n\n"
        "🔇 **Управление доступом:**\n"
        "• `.mute` — Заблокировать собеседника в чате. Текст меняется на «Замолчи!», новые сообщения собеседника сразу удаляются.\n"
        "• `.unmute` — Снять блокировку. Текст меняется на «Говори!».\n\n"
        "⚡️ **Быстрые действия:**\n"
        "• `.spam <кол-во> <текст>` — Отправить указанное кол-во сообщений от вашего имени (Пример: `.spam 5 Привет`).\n"
        "• `.del` — Напишите в ответ (reply) на сообщение, чтобы быстро его удалить.\n"
        "• `.pin` — Закрепить сообщение (отправьте в ответ на нужное сообщение).\n"
        "• `.unpin` — Открепить последнее закрепленное сообщение.\n"
        "• `.info` — Показать краткую информацию о собеседнике и чате."
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "📊 Статистика")
async def btn_stats(message: Message):
    """Вывод статистики."""
    stats = await get_stats(message.from_user.id)
    text = (
        "📊 **Ваша статистика Telegram Business:**\n\n"
        f"💾 **Всего сохранено сообщений:** `{stats['msg_count']}`\n"
        f"🚫 **Замученных чатов:** `{stats['muted_count']}`"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("toggle_setting:"))
async def process_setting_toggle(callback: CallbackQuery):
    """Обработка переключений настроек."""
    setting_key = callback.data.split(":")[1]
    await toggle_setting(callback.from_user.id, setting_key)
    kb = await get_settings_inline_keyboard(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Настройки обновлены!")


@dp.callback_query(F.data == "refresh_settings")
async def process_settings_refresh(callback: CallbackQuery):
    """Обновление инлайн-меню настроек."""
    kb = await get_settings_inline_keyboard(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Обновлено!")


# =====================================================================
# ХЕНДЛЕРЫ TELEGRAM BUSINESS (ПОДКЛЮЧЕНИЕ / ОТКЛЮЧЕНИЕ)
# =====================================================================

@dp.business_connection()
async def on_business_connection(connection: BusinessConnection):
    """Уведомления при подключении / отключении бота."""
    user_id = connection.user.id
    connection_id = connection.id
    is_enabled = connection.is_enabled

    await save_connection(connection_id, user_id, is_enabled)

    if is_enabled:
        logging.info(f"Бизнес-подключение ВКЛЮЧЕНО для {user_id}")
        text = (
            "✅ **Telegram Business успешно подключён!**\n\n"
            f"🆔 Connection ID: `{connection_id}`\n"
            "🟢 Бот активен и готов сохранять удалённые сообщения и выполнять команды."
        )
    else:
        logging.info(f"Бизнес-подключение ОТКЛЮЧЕНО для {user_id}")
        text = (
            "⚠️ **Telegram Business отключён!**\n\n"
            f"🆔 Connection ID: `{connection_id}`\n"
            "🔴 Бот больше не имеет доступа к вашим чатам."
        )

    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при отправке статуса подключения: {e}")


# =====================================================================
# ХЕНДЛЕР БИЗНЕС-СООБЩЕНИЙ
# =====================================================================

@dp.business_message()
async def on_business_message(message: Message):
    """Обработка всех сообщений из бизнес-чатов."""
    connection_id = message.business_connection_id
    if not connection_id:
        return

    owner_id = await get_owner_id(connection_id)
    sender = message.from_user
    sender_id = sender.id if sender else 0
    sender_name = sender.full_name if sender else "Неизвестный"
    text_content = message.text or message.caption or ""

    # 1. КОМАНДЫ ВЛАДЕЛЬЦА
    if owner_id and sender_id == owner_id:
        clean_text = text_content.strip()

        if clean_text == ".mute":
            await set_chat_mute(connection_id, message.chat.id, True)
            try:
                await bot.edit_message_text(
                    text="Замолчи!",
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except Exception as e:
                logging.error(f"Ошибка .mute: {e}")
            return

        elif clean_text == ".unmute":
            await set_chat_mute(connection_id, message.chat.id, False)
            try:
                await bot.edit_message_text(
                    text="Говори!",
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except Exception as e:
                logging.error(f"Ошибка .unmute: {e}")
            return

        elif clean_text.startswith(".spam"):
            parts = clean_text.split(" ", 2)
            if len(parts) >= 3 and parts[1].isdigit():
                count = min(int(parts[1]), 50)
                spam_text = parts[2]

                try:
                    await bot.delete_business_messages(
                        business_connection_id=connection_id,
                        chat_id=message.chat.id,
                        message_ids=[message.message_id],
                    )
                except Exception:
                    pass

                for _ in range(count):
                    try:
                        await bot.send_message(
                            chat_id=message.chat.id,
                            text=spam_text,
                            business_connection_id=connection_id,
                        )
                        await asyncio.sleep(0.15)
                    except Exception as e:
                        logging.error(f"Ошибка .spam: {e}")
                        break
                return

        elif clean_text == ".del" and message.reply_to_message:
            try:
                await bot.delete_business_messages(
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_ids=[message.reply_to_message.message_id, message.message_id],
                )
            except Exception as e:
                logging.error(f"Ошибка .del: {e}")
            return

        elif clean_text == ".pin" and message.reply_to_message:
            try:
                await bot.pin_chat_message(
                    chat_id=message.chat.id,
                    message_id=message.reply_to_message.message_id,
                )
                await bot.delete_business_messages(
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_ids=[message.message_id],
                )
            except Exception as e:
                logging.error(f"Ошибка .pin: {e}")
            return

        elif clean_text == ".unpin":
            try:
                await bot.unpin_chat_message(chat_id=message.chat.id)
                await bot.delete_business_messages(
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_ids=[message.message_id],
                )
            except Exception as e:
                logging.error(f"Ошибка .unpin: {e}")
            return

        elif clean_text == ".info":
            info = (
                f"ℹ️ **Информация о чате:**\n"
                f"👤 Имя: {message.chat.full_name or 'Нет'}\n"
                f"🆔 Chat ID: `{message.chat.id}`\n"
                f"📱 Username: @{message.chat.username or 'отсутствует'}"
            )
            try:
                await bot.edit_message_text(
                    text=info,
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error(f"Ошибка .info: {e}")
            return

    # 2. ПРОВЕРКА МУТА СОБЕСЕДНИКА
    if owner_id and sender_id != owner_id:
        muted = await is_chat_muted(connection_id, message.chat.id)
        if muted:
            try:
                await bot.delete_business_messages(
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_ids=[message.message_id],
                )
            except Exception as e:
                logging.error(f"Ошибка удаления замученного сообщения: {e}")

            chat_title = message.chat.full_name or f"Чат {message.chat.id}"
            info_msg = (
                f"🚫 **Заблокированное сообщение от:** {sender_name}\n"
                f"💬 **Чат:** {chat_title}\n"
                f"📝 **Текст:** {text_content if text_content else '[Медиафайл]'}"
            )
            try:
                await bot.send_message(chat_id=owner_id, text=info_msg)
            except Exception as e:
                logging.error(f"Ошибка отправки сообщения о муте: {e}")
            return

    # 3. СОХРАНЕНИЕ В БД
    if owner_id:
        settings = await get_user_settings(owner_id)

        if settings["only_others"] and sender_id == owner_id:
            return

        media_type = "text"
        file_id = None

        if message.photo:
            media_type = "photo"
            file_id = message.photo[-1].file_id
        elif message.voice:
            media_type = "voice"
            file_id = message.voice.file_id
        elif message.video:
            media_type = "video"
            file_id = message.video.file_id
        elif message.document:
            media_type = "document"
            file_id = message.document.file_id
        elif message.audio:
            media_type = "audio"
            file_id = message.audio.file_id
        elif message.sticker:
            media_type = "sticker"
            file_id = message.sticker.file_id
        elif message.video_note:
            media_type = "video_note"
            file_id = message.video_note.file_id

        if not settings["save_media"] and media_type != "text":
            file_id = None

        await save_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
            connection_id=connection_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text_content,
            media_type=media_type,
            file_id=file_id,
        )


# =====================================================================
# ХЕНДЛЕР УДАЛЁННЫХ СООБЩЕНИЙ
# =====================================================================

@dp.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted):
    """Событие: удаление сообщения в бизнес-чате."""
    connection_id = event.business_connection_id
    owner_id = await get_owner_id(connection_id)

    if not owner_id:
        return

    chat_title = event.chat.full_name or event.chat.title or f"Чат {event.chat.id}"

    for msg_id in event.message_ids:
        saved_msg = await get_saved_message(event.chat.id, msg_id)
        if not saved_msg:
            continue

        sender_name = saved_msg["sender_name"]
        sender_id = saved_msg["sender_id"]

        if sender_id == owner_id:
            continue

        header_info = (
            f"🗑 **Удалено сообщение в чате:** {chat_title}\n"
            f"👤 **Отправитель:** {sender_name} (ID: `{sender_id}`)\n"
            f"🕒 **Отправлено:** {saved_msg['created_at']}\n"
            f"----------------------------------------\n"
        )

        media_type = saved_msg["media_type"]
        file_id = saved_msg["file_id"]
        text_content = saved_msg["text"] or ""

        try:
            if media_type == "text" or not file_id:
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"{header_info}💬 **Текст:**\n{text_content}",
                    parse_mode="Markdown",
                )
            elif media_type == "photo":
                await bot.send_photo(
                    chat_id=owner_id,
                    photo=file_id,
                    caption=f"{header_info}📷 **[Фотография]**\n{text_content}",
                    parse_mode="Markdown",
                )
            elif media_type == "voice":
                await bot.send_voice(
                    chat_id=owner_id,
                    voice=file_id,
                    caption=f"{header_info}🎙 **[Голосовое сообщение]**",
                    parse_mode="Markdown",
                )
            elif media_type == "video":
                await bot.send_video(
                    chat_id=owner_id,
                    video=file_id,
                    caption=f"{header_info}🎥 **[Видео]**\n{text_content}",
                    parse_mode="Markdown",
                )
            elif media_type == "document":
                await bot.send_document(
                    chat_id=owner_id,
                    document=file_id,
                    caption=f"{header_info}📁 **[Документ]**\n{text_content}",
                    parse_mode="Markdown",
                )
            elif media_type == "sticker":
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"{header_info}Забавный стикер был удалён:",
                    parse_mode="Markdown",
                )
                await bot.send_sticker(chat_id=owner_id, sticker=file_id)
            elif media_type == "video_note":
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"{header_info}📹 **[Видеосообщение / Кружок]**",
                    parse_mode="Markdown",
                )
                await bot.send_video_note(chat_id=owner_id, video_note=file_id)
        except Exception as e:
            logging.error(f"Ошибка отправки удалённого сообщения: {e}")


# =====================================================================
# ХЕНДЛЕР ОТРЕДАКТИРОВАННЫХ СООБЩЕНИЙ
# =====================================================================

@dp.edited_business_message()
async def on_edited_business_message(message: Message):
    """Событие: редактирование сообщения."""
    connection_id = message.business_connection_id
    if not connection_id:
        return

    owner_id = await get_owner_id(connection_id)
    if not owner_id or message.from_user.id == owner_id:
        return

    settings = await get_user_settings(owner_id)
    if not settings["log_edits"]:
        return

    old_msg = await get_saved_message(message.chat.id, message.message_id)
    if not old_msg:
        return

    old_text = old_msg["text"]
    new_text = message.text or message.caption

    if old_text and new_text and old_text != new_text:
        chat_title = message.chat.full_name or f"Чат {message.chat.id}"
        sender_name = message.from_user.full_name

        notification = (
            f"✏️ **Отредактировано сообщение в чате:** {chat_title}\n"
            f"👤 **От:** {sender_name}\n\n"
            f"❌ **Было:**\n{old_text}\n\n"
            f"✅ **Стало:**\n{new_text}"
        )

        try:
            await bot.send_message(
                chat_id=owner_id, text=notification, parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Ошибка отправки отредактированного сообщения: {e}")

    await save_message(
        chat_id=message.chat.id,
        message_id=message.message_id,
        connection_id=connection_id,
        sender_id=message.from_user.id,
        sender_name=message.from_user.full_name,
        text=new_text,
        media_type=old_msg["media_type"],
        file_id=old_msg["file_id"],
    )


# =====================================================================
# ЗАПУСК БОТА
# =====================================================================
async def main():
    await init_db()
    logging.info("База данных инициализирована. Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
