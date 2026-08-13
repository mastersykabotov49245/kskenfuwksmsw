import logging
import json
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ContextTypes, filters, ConversationHandler
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = "8893361270:AAF8kJgzBX_2P5BKwHtWl18slL-FNObQgUw"

# Файлы для сохранения данных
DATA_FILE = "bot_data.json"
LOGS_FILE = "bot_logs.json"

class AdvancedBotManager:
    def __init__(self):
        self.load_data()
    
    def load_data(self):
        """Загрузить данные бота"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                self.data = self._create_default_data()
        else:
            self.data = self._create_default_data()
    
    def _create_default_data(self):
        """Создать данные по умолчанию"""
        return {
            "active_chats": {},
            "muted_users": {},
            "deleted_messages": {},
            "settings": {},
            "spam_count": {}
        }
    
    def save_data(self):
        """Сохранить данные бота"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")
    
    def log_action(self, action: str, user_id: int, chat_id: int, details: str = ""):
        """Логировать действия"""
        try:
            if not os.path.exists(LOGS_FILE):
                logs = []
            else:
                with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            
            log_entry = {
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "action": action,
                "user_id": user_id,
                "chat_id": chat_id,
                "details": details
            }
            logs.append(log_entry)
            
            with open(LOGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при логировании: {e}")
    
    def activate_chat(self, chat_id: int):
        """Активировать управление чатом"""
        chat_str = str(chat_id)
        self.data["active_chats"][chat_str] = {
            "status": True,
            "activated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "notifications": True,
            "autosave": True
        }
        if chat_str not in self.data["settings"]:
            self.data["settings"][chat_str] = {
                "notifications": True,
                "autosave": True,
                "log_enabled": True
            }
        self.save_data()
    
    def deactivate_chat(self, chat_id: int):
        """Деактивировать управление чатом"""
        chat_str = str(chat_id)
        if chat_str in self.data["active_chats"]:
            del self.data["active_chats"][chat_str]
        self.save_data()
    
    def is_chat_active(self, chat_id: int) -> bool:
        """Проверить активен ли чат"""
        return str(chat_id) in self.data["active_chats"]
    
    def mute_user(self, chat_id: int, user_id: int):
        """Замутить пользователя"""
        chat_str = str(chat_id)
        if chat_str not in self.data["muted_users"]:
            self.data["muted_users"][chat_str] = []
        if user_id not in self.data["muted_users"][chat_str]:
            self.data["muted_users"][chat_str].append(user_id)
        self.save_data()
    
    def unmute_user(self, chat_id: int, user_id: int):
        """Размутить пользователя"""
        chat_str = str(chat_id)
        if chat_str in self.data["muted_users"]:
            if user_id in self.data["muted_users"][chat_str]:
                self.data["muted_users"][chat_str].remove(user_id)
        self.save_data()
    
    def is_user_muted(self, chat_id: int, user_id: int) -> bool:
        """Проверить замутен ли пользователь"""
        chat_str = str(chat_id)
        if chat_str not in self.data["muted_users"]:
            return False
        return user_id in self.data["muted_users"][chat_str]
    
    def save_deleted_message(self, chat_id: int, message_id: int, user_id: int, 
                           user_name: str, text: str):
        """Сохранить удаленное сообщение"""
        chat_str = str(chat_id)
        if chat_str not in self.data["deleted_messages"]:
            self.data["deleted_messages"][chat_str] = []
        
        message_info = {
            "message_id": message_id,
            "user_id": user_id,
            "user_name": user_name,
            "text": text[:100],  # Сохраняем первые 100 символов
            "deleted_date": datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            "full_text": text
        }
        self.data["deleted_messages"][chat_str].append(message_info)
        self.save_data()
    
    def get_deleted_messages(self, chat_id: int, limit: int = 10):
        """Получить удаленные сообщения"""
        chat_str = str(chat_id)
        if chat_str not in self.data["deleted_messages"]:
            return []
        return self.data["deleted_messages"][chat_str][-limit:]
    
    def get_muted_users(self, chat_id: int):
        """Получить список замученных пользователей"""
        chat_str = str(chat_id)
        if chat_str not in self.data["muted_users"]:
            return []
        return self.data["muted_users"][chat_str]
    
    def toggle_notifications(self, chat_id: int):
        """Включить/выключить уведомления"""
        chat_str = str(chat_id)
        if chat_str not in self.data["settings"]:
            self.data["settings"][chat_str] = {}
        
        current = self.data["settings"][chat_str].get("notifications", True)
        self.data["settings"][chat_str]["notifications"] = not current
        self.save_data()
        return not current
    
    def get_stats(self):
        """Получить общую статистику"""
        return {
            "active_chats": len(self.data["active_chats"]),
            "total_deleted_messages": sum(len(msgs) for msgs in self.data["deleted_messages"].values()),
            "total_muted_users": sum(len(users) for users in self.data["muted_users"].values())
        }

bot_manager = AdvancedBotManager()

# ==================== ОБРАБОТЧИКИ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - главное меню"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    keyboard = [
        [
            InlineKeyboardButton("🔐 Активировать", callback_data="activate"),
            InlineKeyboardButton("🔓 Отключить", callback_data="deactivate")
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
            InlineKeyboardButton("📋 Команды", callback_data="commands")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("🗑️ Удаленные", callback_data="deleted")
        ],
        [
            InlineKeyboardButton("👥 Замученные юзеры", callback_data="muted_list"),
            InlineKeyboardButton("📝 Логи", callback_data="logs")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ АКТИВЕН" if bot_manager.is_chat_active(chat_id) else "❌ НЕАКТИВЕН"
    
    await update.message.reply_html(
        f"<b>👋 Привет, {user.first_name}!</b>\n\n"
        f"<b>🤖 Статус бота:</b> {status}\n\n"
        f"<b>Основные возможности:</b>\n"
        f"💾 Сохранение удаленных сообщений\n"
        f"🔇 Режим мута для пользователей\n"
        f"📢 Спам-команда для отправки сообщений\n"
        f"⚙️ Полные настройки и управление\n"
        f"📊 Подробная статистика и логи\n\n"
        f"<i>Выбери действие ниже:</i>",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await query.answer()
    
    if query.data == "activate":
        bot_manager.activate_chat(chat_id)
        bot_manager.log_action("ACTIVATE", user_id, chat_id, "Бот активирован")
        
        await query.edit_message_html(
            text="<b>✅ БОТА АКТИВИРОВАН!</b>\n\n"
                 "🟢 <b>Статус:</b> Управление чатом включено\n\n"
                 "<b>Теперь я буду:</b>\n"
                 "💾 Сохранять удаленные сообщения\n"
                 "🔇 Работать с режимом мута\n"
                 "⚡ Обрабатывать все команды\n\n"
                 "📲 <b>УВЕДОМЛЕНИЕ:</b> Бот успешно подключен к чату!\n"
                 f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
    
    elif query.data == "deactivate":
        bot_manager.deactivate_chat(chat_id)
        bot_manager.log_action("DEACTIVATE", user_id, chat_id, "Бот деактивирован")
        
        await query.edit_message_html(
            text="<b>❌ БОТ ОТКЛЮЧЕН</b>\n\n"
                 "🔴 <b>Статус:</b> Управление чатом отключено\n\n"
                 "📲 <b>УВЕДОМЛЕНИЕ:</b> Бот отключен от чата!\n"
                 f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                 "Для повторной активации нажми кнопку выше"
        )
    
    elif query.data == "commands":
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        commands_text = (
            "<b>📋 ПОЛНЫЙ СПИСОК КОМАНД:</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<b>🔇 МУТ КОМАНДЫ:</b>\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<code>.mute</code> - Замучить себя (тебя удалять не будут)\n"
            "<code>.unmute</code> - Размучить себя\n\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<b>📢 СПАМ КОМАНДА:</b>\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<code>.spam [кол-во] [текст]</code>\n"
            "Пример: <code>.spam 5 привет</code>\n"
            "Результат: отправит 'привет' 5 раз\n"
            "⚠️ Максимум: 100 сообщений\n\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<b>📊 ИНФОРМАЦИОННЫЕ:</b>\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<code>.deleted</code> - Показать удаленные сообщения\n"
            "<code>.stats</code> - Статистика бота\n"
            "<code>.muted_list</code> - Список замученных\n"
            "<code>.clear</code> - Очистить удаленные\n\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<b>⚙️ УПРАВЛЕНИЕ:</b>\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<code>/start</code> - Главное меню\n"
            "<code>/menu</code> - Главное меню\n"
            "<code>/help</code> - Помощь"
        )
        
        await query.edit_message_html(text=commands_text, reply_markup=reply_markup)
    
    elif query.data == "settings":
        chat_str = str(chat_id)
        settings = bot_manager.data["settings"].get(chat_str, {})
        notifications = "ВКЛ ✅" if settings.get("notifications", True) else "ВЫКЛ ❌"
        autosave = "ВКЛ ✅" if settings.get("autosave", True) else "ВЫКЛ ❌"
        
        keyboard = [
            [InlineKeyboardButton(f"🔔 Уведомления: {notifications}", callback_data="toggle_notifications")],
            [InlineKeyboardButton(f"💾 Автосохранение: {autosave}", callback_data="toggle_autosave")],
            [InlineKeyboardButton("🗑️ Очистить удаленные", callback_data="clear_deleted")],
            [InlineKeyboardButton("📝 Логи действий", callback_data="view_logs")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_html(
            text="<b>⚙️ ПАНЕЛЬ НАСТРОЕК</b>\n\n"
                 f"🔔 <b>Уведомления:</b> {notifications}\n"
                 f"💾 <b>Автосохранение:</b> {autosave}\n"
                 f"📝 <b>Логирование:</b> ВКЛ ✅\n\n"
                 "Выбери, что изменить:",
            reply_markup=reply_markup
        )
    
    elif query.data == "toggle_notifications":
        status = bot_manager.toggle_notifications(chat_id)
        await query.answer(f"Уведомления {'включены' if status else 'отключены'}")
        # Переоткрыть меню настроек
        await button_callback(update, context) if query.data != "toggle_notifications" else None
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_html(
            text=f"<b>✅ Уведомления {'включены' if status else 'отключены'}!</b>",
            reply_markup=reply_markup
        )
    
    elif query.data == "stats":
        stats = bot_manager.get_stats()
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_html(
            text=f"<b>📊 СТАТИСТИКА БОТА</b>\n\n"
                 f"🟢 <b>Активных чатов:</b> {stats['active_chats']}\n"
                 f"💾 <b>Сохранено сообщений:</b> {stats['total_deleted_messages']}\n"
                 f"🔇 <b>Замученных пользователей:</b> {stats['total_muted_users']}\n"
                 f"📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y')}\n"
                 f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n",
            reply_markup=reply_markup
        )
    
    elif query.data == "deleted":
        messages = bot_manager.get_deleted_messages(chat_id, limit=5)
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if not messages:
            text = "<b>🗑️ Удаленные сообщения:</b>\n\nПока нет удаленных сообщений"
        else:
            text = "<b>🗑️ ПОСЛЕДНИЕ УДАЛЕННЫЕ СООБЩЕНИЯ (макс. 5):</b>\n\n"
            for i, msg in enumerate(messages[-5:], 1):
                text += (f"<b>{i}.</b> 👤 <b>{msg['user_name']}:</b>\n"
                        f"   <i>{msg['text']}</i>\n"
                        f"   🕐 {msg['deleted_date']}\n\n")
        
        await query.edit_message_html(text=text, reply_markup=reply_markup)
    
    elif query.data == "muted_list":
        muted = bot_manager.get_muted_users(chat_id)
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if not muted:
            text = "<b>👥 Замученные пользователи:</b>\n\nНет замученных пользователей"
        else:
            text = f"<b>👥 ЗАМУЧЕННЫЕ ПОЛЬЗОВАТЕЛИ ({len(muted)}):</b>\n\n"
            for i, uid in enumerate(muted, 1):
                text += f"<b>{i}.</b> ID: <code>{uid}</code>\n"
        
        await query.edit_message_html(text=text, reply_markup=reply_markup)
    
    elif query.data == "logs":
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                    logs = [l for l in logs if l['chat_id'] == chat_id][-5:]
                
                keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if not logs:
                    text = "<b>📝 Логи действий:</b>\n\nНет логов"
                else:
                    text = "<b>📝 ПОСЛЕДНИЕ ЛОГИ ДЕЙСТВИЙ:</b>\n\n"
                    for log in logs:
                        text += f"<b>{log['action']}</b> - {log['timestamp']}\n"
                
                await query.edit_message_html(text=text, reply_markup=reply_markup)
            except Exception as e:
                await query.answer(f"Ошибка: {e}")
        else:
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_html(
                text="<b>📝 Логи действий:</b>\n\nНет логов",
                reply_markup=reply_markup
            )
    
    elif query.data == "clear_deleted":
        chat_str = str(chat_id)
        bot_manager.data["deleted_messages"][chat_str] = []
        bot_manager.save_data()
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_html(
            text="<b>✅ Удаленные сообщения очищены!</b>",
            reply_markup=reply_markup
        )
    
    elif query.data == "back":
        keyboard = [
            [
                InlineKeyboardButton("🔐 Активировать", callback_data="activate"),
                InlineKeyboardButton("🔓 Отключить", callback_data="deactivate")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
                InlineKeyboardButton("📋 Команды", callback_data="commands")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="stats"),
                InlineKeyboardButton("🗑️ Удаленные", callback_data="deleted")
            ],
            [
                InlineKeyboardButton("👥 Замученные юзеры", callback_data="muted_list"),
                InlineKeyboardButton("📝 Логи", callback_data="logs")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status = "✅ АКТИВЕН" if bot_manager.is_chat_active(chat_id) else "❌ НЕАКТИВЕН"
        
        await query.edit_message_html(
            text=f"<b>👋 Главное меню</b>\n\n"
                 f"<b>Статус бота:</b> {status}\n\n"
                 f"Выбери действие:",
            reply_markup=reply_markup
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений"""
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Unknown"
    
    if not bot_manager.is_chat_active(chat_id):
        return
    
    text = message.text or ""
    
    try:
        # Команда .mute
        if text.strip() == ".mute":
            bot_manager.mute_user(chat_id, user_id)
            bot_manager.log_action("MUTE", user_id, chat_id, f"User {user_name} muted")
            
            try:
                await message.edit_text("<b>Замолчи!</b>", parse_mode=ParseMode.HTML)
            except:
                pass
            
            await message.reply_html(
                f"🔇 <b>{user_name}</b> получил мут.\n"
                f"Его сообщения будут автоматически удаляться."
            )
        
        # Команда .unmute
        elif text.strip() == ".unmute":
            bot_manager.unmute_user(chat_id, user_id)
            bot_manager.log_action("UNMUTE", user_id, chat_id, f"User {user_name} unmuted")
            
            await message.reply_html(
                f"🔊 <b>{user_name}</b> размучен.\n"
                f"Его сообщения будут видны."
            )
        
        # Команда .spam
        elif text.startswith(".spam"):
            try:
                parts = text.split(" ", 2)
                if len(parts) < 3:
                    await message.reply_html(
                        "❌ <b>Неправильный формат!</b>\n\n"
                        "<b>Использование:</b> <code>.spam [кол-во] [текст]</code>\n"
                        "<b>Пример:</b> <code>.spam 5 привет</code>"
                    )
                    return
                
                count = int(parts[1])
                spam_text = parts[2]
                
                if count > 100:
                    await message.reply_html("⚠️ <b>Максимум 100 сообщений!</b>")
                    return
                
                if count < 1:
                    await message.reply_html("⚠️ <b>Количество должно быть больше 0!</b>")
                    return
                
                bot_manager.log_action("SPAM", user_id, chat_id, f"Spam {count} messages")
                
                await message.reply_html(f"<b>📢 Начинаю спам...</b> ({count} сообщений)")
                
                for i in range(count):
                    await message.reply_html(
                        f"<b>[{i+1}/{count}]</b> {spam_text}"
                    )
                    await asyncio.sleep(0.1)  # Небольшая задержка
            
            except ValueError:
                await message.reply_html("❌ <b>Ошибка!</b> Число должно быть цифрой!")
            except Exception as e:
                logger.error(f"Ошибка при спаме: {e}")
        
        # Команда .deleted
        elif text.strip() == ".deleted":
            messages = bot_manager.get_deleted_messages(chat_id)
            if not messages:
                await message.reply_html("🗑️ <b>Нет удаленных сообщений</b>")
                return
            
            text_output = "<b>🗑️ УДАЛЕННЫЕ СООБЩЕНИЯ (последние 10):</b>\n\n"
            for i, msg in enumerate(messages[-10:], 1):
                text_output += (f"<b>{i}.</b> 👤 <b>{msg['user_name']}:</b>\n"
                               f"   <i>{msg['text']}</i>\n"
                               f"   🕐 {msg['deleted_date']}\n\n")
            
            await message.reply_html(text_output)
        
        # Команда .stats
        elif text.strip() == ".stats":
            stats = bot_manager.get_stats()
            await message.reply_html(
                f"<b>📊 СТАТИСТИКА БОТА:</b>\n\n"
                f"🟢 <b>Активных чатов:</b> {stats['active_chats']}\n"
                f"💾 <b>Сохранено сообщений:</b> {stats['total_deleted_messages']}\n"
                f"🔇 <b>Замученных пользователей:</b> {stats['total_muted_users']}\n"
                f"📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
        
        # Команда .muted_list
        elif text.strip() == ".muted_list":
            muted = bot_manager.get_muted_users(chat_id)
            if not muted:
                await message.reply_html("<b>👥 Замученные пользователи:</b> нет")
                return
            
            text_output = f"<b>👥 ЗАМУЧЕННЫЕ ПОЛЬЗОВАТЕЛИ ({len(muted)}):</b>\n\n"
            for i, uid in enumerate(muted, 1):
                text_output += f"<b>{i}.</b> ID: <code>{uid}</code>\n"
            
            await message.reply_html(text_output)
        
        # Команда .clear
        elif text.strip() == ".clear":
            chat_str = str(chat_id)
            bot_manager.data["deleted_messages"][chat_str] = []
            bot_manager.save_data()
            bot_manager.log_action("CLEAR", user_id, chat_id, "Deleted messages cleared")
            await message.reply_html("✅ <b>Удаленные сообщения очищены!</b>")
        
        # Проверка мута пользователя
        elif bot_manager.is_user_muted(chat_id, user_id):
            try:
                # Сохраняем сообщение перед удалением
                bot_manager.save_deleted_message(
                    chat_id,
                    message.message_id,
                    user_id,
                    user_name,
                    text
                )
                # Удаляем сообщение
                await message.delete()
            except TelegramError as e:
                logger.error(f"Ошибка при удалении сообщения: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")

async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик редактирования сообщений"""
    message = update.edited_message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not bot_manager.is_chat_active(chat_id):
        return
    
    if bot_manager.is_user_muted(chat_id, user_id):
        try:
            await message.delete()
        except TelegramError as e:
            logger.error(f"Ошибка при удалении отредактированного сообщения: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_html(
        "<b>❓ СПРАВКА ПО БОТУ</b>\n\n"
        "Напиши <code>/start</code> для открытия главного меню\n\n"
        "<b>Основные команды:</b>\n"
        "• <code>/start</code> - Главное меню\n"
        "• <code>/menu</code> - Главное меню\n"
        "• <code>/help</code> - Эта справка\n\n"
        "<b>Команды в чате:</b>\n"
        "• <code>.mute</code> - Замучить себя\n"
        "• <code>.unmute</code> - Размучить себя\n"
        "• <code>.spam [кол-во] [текст]</code> - Спам\n"
        "• <code>.deleted</code> - Удаленные сообщения\n"
        "• <code>.stats</code> - Статистика\n"
        "• <code>.muted_list</code> - Список замученных\n"
        "• <code>.clear</code> - Очистить удаленные\n"
    )

async def main():
    """Главная функция запуска бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.UPDATE_EDITED_MESSAGE, handle_edited_message))
    
    logger.info("🤖 БОТА ЗАПУЩЕН УСПЕШНО!")
    logger.info("📱 Напиши /start для начала работы")
    logger.info(f"🕐 Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
