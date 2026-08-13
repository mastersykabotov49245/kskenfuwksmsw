import asyncio
import logging
import sys
from datetime import datetime
import aiosqlite

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import Message, BusinessConnection, DeletedBusinessMessages

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
BOT_TOKEN = "8138153160:AAF4Zl35mDsuuERANThzY9nMdo_cljhixts"
DB_PATH = "business_messages.db"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =====================================================================
# РАБОТА С БАЗОЙ ДАННЫХ
# =====================================================================
async def init_db():
    """Инициализация таблиц базы данных."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица связей business_connection_id -> user_id (владелец бизнеса)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                connection_id TEXT PRIMARY KEY,
                user_id INTEGER
            )
        """)
        # Таблица для сохранения всех сообщений из бизнес-чатов
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
        # Таблица для списка заблокированных (замученных) чатов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS muted_chats (
                connection_id TEXT,
                chat_id INTEGER,
                PRIMARY KEY (connection_id, chat_id)
            )
        """)
        await db.commit()


async def save_connection(connection_id: str, user_id: int):
    """Сохранение или обновление бизнес-подключения."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO connections (connection_id, user_id) VALUES (?, ?)",
            (connection_id, user_id),
        )
        await db.commit()


async def get_owner_id(connection_id: str) -> int | None:
    """Получение ID владельца аккаунта по connection_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM connections WHERE connection_id = ?",
            (connection_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


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
    """Кэширование сообщения в базу данных."""
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
    """Получение сохранённого сообщения по chat_id и message_id."""
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


# --- Управление мутом в БД ---

async def set_chat_mute(connection_id: str, chat_id: int, mute: bool):
    """Добавление или удаление чата из списка замученных."""
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
    """Проверка, находится ли чат в муте."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM muted_chats WHERE connection_id = ? AND chat_id = ?",
            (connection_id, chat_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


# =====================================================================
# ХЕНДЛЕРЫ СОБЫТИЙ TELEGRAM
# =====================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start в личных сообщениях с ботом."""
    await message.answer(
        "👋 **Привет! Я бот для Telegram Business.**\n\n"
        "**Мои возможности:**\n"
        "1. Сохранение удалённых и отредактированных сообщений собеседника.\n"
        "2. Команды в бизнес-чатах:\n"
        "   • `.mute` — замутить собеседника (все его сообщения будут удаляться).\n"
        "   • `.unmute` — размутить собеседника.\n"
        "   • `.spam <кол-во> <текст>` — заспамить чат сообщениями от имени бизнес-бота (например: `.spam 10 Привет`)."
    )


@dp.business_connection()
async def on_business_connection(connection: BusinessConnection):
    """Отслеживание подключения/отключения бота к бизнес-аккаунту."""
    if connection.is_enabled:
        await save_connection(connection.id, connection.user.id)
        logging.info(f"Бизнес-подключение установлено для пользователя {connection.user.id}")
        try:
            await bot.send_message(
                chat_id=connection.user.id,
                text="✅ **Бот успешно подключён к вашему бизнес-аккаунту!**"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение владельцу: {e}")


@dp.business_message()
async def on_business_message(message: Message):
    """Перехват и обработка сообщений из бизнес-чатов."""
    connection_id = message.business_connection_id
    if not connection_id:
        return

    owner_id = await get_owner_id(connection_id)
    sender = message.from_user
    sender_id = sender.id if sender else 0
    sender_name = sender.full_name if sender else "Неизвестный"

    text_content = message.text or message.caption or ""

    # =================================================================
    # 1. ОБРАБОТКА КОМАНД ВЛАДЕЛЬЦА АККАУНТА (.mute / .unmute / .spam)
    # =================================================================
    if owner_id and sender_id == owner_id:
        clean_text = text_content.strip()

        # Команда включения мута
        if clean_text == ".mute":
            await set_chat_mute(connection_id, message.chat.id, True)
            try:
                await bot.edit_message_text(
                    text="Замолчи!",
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_id=message.message_id
                )
            except Exception as e:
                logging.error(f"Не удалось отредактировать сообщение на .mute: {e}")
            return

        # Команда выключения мута
        elif clean_text == ".unmute":
            await set_chat_mute(connection_id, message.chat.id, False)
            try:
                await bot.edit_message_text(
                    text="Говори!",
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_id=message.message_id
                )
            except Exception as e:
                logging.error(f"Не удалось отредактировать сообщение на .unmute: {e}")
            return

        # Команда спама: .spam <Количество> <Текст>
        elif clean_text.startswith(".spam"):
            parts = clean_text.split(" ", 2)
            if len(parts) >= 3 and parts[1].isdigit():
                count = int(parts[1])
                spam_text = parts[2]

                # Ограничим максимальное количество, чтобы не забанили бота
                count = min(count, 100)

                # Удаляем исходное сообщение с командой
                try:
                    await bot.delete_business_messages(
                        business_connection_id=connection_id,
                        chat_id=message.chat.id,
                        message_ids=[message.message_id]
                    )
                except Exception as e:
                    logging.error(f"Не удалось удалить команду спама: {e}")

                # Запускаем цикл отправки сообщений от имени бизнес-аккаунта
                for _ in range(count):
                    try:
                        await bot.send_message(
                            chat_id=message.chat.id,
                            text=spam_text,
                            business_connection_id=connection_id
                        )
                        # Минимальная пауза, чтобы Telegram не ограничил запросы
                        await asyncio.sleep(0.15)
                    except Exception as e:
                        logging.error(f"Ошибка при отправке спам-сообщения: {e}")
                        break
                return

    # =================================================================
    # 2. ПРОВЕРКА МУТА СОБЕСЕДНИКА
    # =================================================================
    if owner_id and sender_id != owner_id:
        muted = await is_chat_muted(connection_id, message.chat.id)
        if muted:
            # Сначала пытаемся удалить сообщение собеседника
            try:
                await bot.delete_business_messages(
                    business_connection_id=connection_id,
                    chat_id=message.chat.id,
                    message_ids=[message.message_id]
                )
            except Exception as e:
                logging.error(f"Не удалось удалить сообщение из замученного чата: {e}")

            # Отправляем владельцу копию удалённого сообщения в ЛС
            chat_title = message.chat.full_name or message.chat.title or f"Чат {message.chat.id}"
            info_msg = (
                f"🚫 **Заблокированное сообщение от:** {sender_name}\n"
                f"💬 **Чат:** {chat_title}\n"
                f"📝 **Текст/Контент:** {text_content if text_content else '[Медиафайл]'}"
            )
            try:
                await bot.send_message(chat_id=owner_id, text=info_msg)
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление о замученном сообщении: {e}")
            return

    # =================================================================
    # 3. СОХРАНЕНИЕ ОБЫЧНОГО СООБЩЕНИЯ В БАЗУ ДАННЫХ
    # =================================================================
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


@dp.deleted_business_messages()
async def on_deleted_business_messages(event: DeletedBusinessMessages):
    """Событие: удаление сообщений в бизнес-чате."""
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

        # Не уведомляем об удалении сообщений самого владельца
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
            if media_type == "text":
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"{header_info}💬 **Текст:**\n{text_content}"
                )
            elif media_type == "photo":
                await bot.send_photo(
                    chat_id=owner_id,
                    photo=file_id,
                    caption=f"{header_info}📷 **[Фотография]**\n{text_content}"
                )
            elif media_type == "voice":
                await bot.send_voice(
                    chat_id=owner_id,
                    voice=file_id,
                    caption=f"{header_info}🎙 **[Голосовое сообщение]**"
                )
            elif media_type == "video":
                await bot.send_video(
                    chat_id=owner_id,
                    video=file_id,
                    caption=f"{header_info}🎥 **[Видео]**\n{text_content}"
                )
            elif media_type == "document":
                await bot.send_document(
                    chat_id=owner_id,
                    document=file_id,
                    caption=f"{header_info}📁 **[Документ]**\n{text_content}"
                )
            elif media_type == "sticker":
                await bot.send_message(chat_id=owner_id, text=f"{header_info}Забавный стикер был удалён:")
                await bot.send_sticker(chat_id=owner_id, sticker=file_id)
            elif media_type == "video_note":
                await bot.send_message(chat_id=owner_id, text=f"{header_info}📹 **[Видеосообщение / Кружок]**")
                await bot.send_video_note(chat_id=owner_id, video_note=file_id)
            else:
                await bot.send_message(
                    chat_id=owner_id,
                    text=f"{header_info}❓ **[Неизвестный тип медиа]**\n{text_content}"
                )
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления об удалённом сообщении: {e}")


@dp.edited_business_message()
async def on_edited_business_message(message: Message):
    """Отслеживание редактирования сообщений."""
    connection_id = message.business_connection_id
    if not connection_id:
        return

    owner_id = await get_owner_id(connection_id)
    if not owner_id or message.from_user.id == owner_id:
        return

    old_msg = await get_saved_message(message.chat.id, message.message_id)
    if not old_msg:
        return

    old_text = old_msg["text"]
    new_text = message.text or message.caption

    if old_text and new_text and old_text != new_text:
        chat_title = message.chat.full_name or message.chat.title or f"Чат {message.chat.id}"
        sender_name = message.from_user.full_name

        notification = (
            f"✏️ **Отредактировано сообщение в чате:** {chat_title}\n"
            f"👤 **От:** {sender_name}\n\n"
            f"❌ **Было:**\n{old_text}\n\n"
            f"✅ **Стало:**\n{new_text}"
        )

        try:
            await bot.send_message(chat_id=owner_id, text=notification)
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления о редактировании: {e}")

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
