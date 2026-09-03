"""
Telegram-бот корпоративной базы знаний ИТ-службы.

Что делает:
  /start      — приветствие и три кнопки
  /help       — что умеет бот
  /reglament  — присылает все файлы регламента (.md и .txt), найденные
                рядом со скриптом
  любой текст — ищет подходящий пункт по номеру и отвечает с указанием
                номера, заголовка и файла-источника; если ничего не
                найдено — честно об этом пишет, ничего не выдумывает

Поиск работает без БД и без ML: только стоп-слова + пересечение
значимых слов + difflib.SequenceMatcher.

----------------------------------------------------------------------
Как запустить (пошагово — рассчитано на то, что вы не программист):

  1. Установите Python 3.10 или новее (python.org).

  2. Положите рядом в одну папку:
       - bot.py            (этот файл)
       - requirements.txt
       - .gitignore
       - хотя бы один файл базы знаний с расширением .md или .txt
         (например, reglament.txt) — можно несколько файлов.

  3. Откройте терминал в этой папке и выполните:

         pip install -r requirements.txt

  4. Получите токен бота у @BotFather в Telegram (команда /newbot).

  5. Укажите токен через переменную окружения BOT_TOKEN. Проще всего —
     создать в этой же папке файл с именем ".env" (без расширения)
     с одной строкой внутри:

         BOT_TOKEN=вставьте_сюда_ваш_токен

     Бот сам прочитает этот файл при запуске. Токена в коде нет и
     быть не должно.

  6. Запустите бота:

         python bot.py

  7. Если в терминале появилось "Бот запущен и слушает сообщения" —
     всё работает. Найдите бота в Telegram и напишите /start.

----------------------------------------------------------------------
Формат файлов базы знаний (.md или .txt):

  Пункты нумеруются в начале строки. Поддерживаются форматы:
      1. Заголовок
      1.2 Заголовок
      2.3.1 Заголовок
      # 1.2 Заголовок       (markdown-заголовок с номером)

  Весь текст после заголовка до начала следующего пункта считается
  содержимым этого пункта. Пример:

      1. Общие положения
      Текст первого пункта...

      1.1 Сфера действия
      Текст подпункта...

      # 2 Следующий раздел
      ...

  Внутри текста можно использовать **жирный** и *курсив* — бот
  аккуратно превратит это в форматирование Telegram.
----------------------------------------------------------------------
"""

import asyncio
import difflib
import html
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Необязательная поддержка файла .env, чтобы не программисту было проще
# один раз указать токен и не разбираться с переменными окружения вручную.
# Если пакета python-dotenv нет — просто ничего не делаем, не падаем.
# --------------------------------------------------------------------------- #
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    FSInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

# --------------------------------------------------------------------------- #
# Логирование — все ошибки и основные события пишутся в консоль
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("kb_bot")

# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #

SCRIPT_DIR = Path(__file__).resolve().parent
BOT_TOKEN = os.getenv("BOT_TOKEN")
KB_EXTENSIONS = ("*.md", "*.txt")

MIN_COMBINED_SCORE = 1.15  # порог, ниже которого пункт считается ненайденным
DIVIDER_LINE = "━" * 20

STOP_WORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "её", "мне", "было", "вот", "от", "меня",
    "еще", "ещё", "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну",
    "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до",
    "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя",
    "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней",
    "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто",
    "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда", "кто",
    "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь",
    "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были",
    "куда", "зачем", "всех", "никогда", "можно", "при", "наконец", "два",
    "об", "другой", "хоть", "после", "над", "больше", "тот", "через", "эти",
    "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту",
    "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше",
    "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно",
    "всю", "между", "это", "эта", "который", "которая", "которое",
    "которые", "также", "либо", "например", "пожалуйста", "спасибо",
    "здравствуйте", "привет", "скажи", "скажите", "подскажи", "подскажите",
    "нужно", "нужен", "нужна", "нужны", "хочу", "хотел", "хотела", "делать",
    "сделать", "сделай", "какие", "какое", "каком", "каким", "почему",
    "любой", "любая", "любое", "являться", "являются", "является", "иметь",
    "имеет", "имеют", "мочь", "могут", "должен", "должна", "должны", "весь",
    "вся", "всё", "именно", "просто", "очень", "самый", "самая", "самое",
    "самые",
}

# --------------------------------------------------------------------------- #
# Модель пункта базы знаний
# --------------------------------------------------------------------------- #


@dataclass
class KnowledgeItem:
    number: str
    title: str
    text: str
    source_file: str


# Ловит: "1. Заголовок", "1.2 Заголовок", "2.3.1 Заголовок",
#        а также markdown-заголовки "# 1.2 Заголовок"
ITEM_PATTERN = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(\d+(?:\.\d+)*\.?)[ \t]+(.+?)[ \t]*$",
    re.MULTILINE,
)

# --------------------------------------------------------------------------- #
# Загрузка и разбор файлов базы знаний
# --------------------------------------------------------------------------- #


def parse_kb_file(path: Path) -> List[KnowledgeItem]:
    """Разбивает один файл (.md или .txt) на пронумерованные пункты."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("Не удалось прочитать файл %s", path.name)
        return []

    matches = list(ITEM_PATTERN.finditer(content))
    items: List[KnowledgeItem] = []

    for idx, match in enumerate(matches):
        number = match.group(1).rstrip(".")
        title = match.group(2).strip()
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        text = content[start:end].strip()
        if text:
            items.append(
                KnowledgeItem(
                    number=number, title=title, text=text, source_file=path.name
                )
            )

    logger.info("Файл %s: найдено пунктов — %d", path.name, len(items))
    return items


def load_knowledge_base() -> Tuple[List[KnowledgeItem], List[Path]]:
    """Сканирует папку скрипта на .md и .txt файлы и строит базу пунктов."""
    kb_files: List[Path] = []
    for pattern in KB_EXTENSIONS:
        kb_files.extend(SCRIPT_DIR.glob(pattern))
    kb_files = sorted(set(kb_files))

    if not kb_files:
        logger.warning(
            "В папке %s не найдено ни одного .md или .txt файла", SCRIPT_DIR
        )

    all_items: List[KnowledgeItem] = []
    for file_path in kb_files:
        all_items.extend(parse_kb_file(file_path))

    logger.info(
        "База знаний загружена: %d файлов, %d пунктов", len(kb_files), len(all_items)
    )
    return all_items, kb_files


# --------------------------------------------------------------------------- #
# Поиск без БД и без ML
# --------------------------------------------------------------------------- #


def tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^а-яёa-z0-9\s]", " ", text)
    words = text.split()
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def find_item(query: str, items: List[KnowledgeItem]) -> Optional[KnowledgeItem]:
    """
    1. Запрос очищается от стоп-слов.
    2. Считается число общих значимых слов с каждым пунктом.
    3. Считается коэффициент схожести через difflib.SequenceMatcher.
    4. combined_score = число общих слов + коэффициент схожести.
    5. Пункт считается найденным, если есть >=1 общее слово и
       combined_score > MIN_COMBINED_SCORE. Возвращается пункт с
       максимальным score.
    """
    query_words = tokenize(query)
    if not query_words:
        return None

    query_set = set(query_words)
    query_joined = " ".join(query_words)

    best_item: Optional[KnowledgeItem] = None
    best_score = 0.0

    for item in items:
        item_words = tokenize(f"{item.title} {item.text}")
        if not item_words:
            continue

        common_words = query_set & set(item_words)
        if not common_words:
            continue

        item_joined = " ".join(item_words)
        similarity = difflib.SequenceMatcher(None, query_joined, item_joined).ratio()
        combined_score = len(common_words) + similarity

        if combined_score > MIN_COMBINED_SCORE and combined_score > best_score:
            best_score = combined_score
            best_item = item

    return best_item


# --------------------------------------------------------------------------- #
# Форматирование ответа: безопасное экранирование + markdown -> html
# --------------------------------------------------------------------------- #


def markdown_to_html(escaped_text: str) -> str:
    """Конвертирует **жирный** и *курсив* в HTML-теги.
    Ожидает текст, уже пропущенный через html.escape."""
    escaped_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped_text)
    escaped_text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped_text)
    return escaped_text


def format_item_response(item: KnowledgeItem) -> str:
    body_html = markdown_to_html(html.escape(item.text))
    filename_html = html.escape(item.source_file)
    number_html = html.escape(item.number)

    return (
        f"📄 Документ: <b>{filename_html}</b>\n"
        f"📎 Пункт <b>{number_html}</b>\n"
        f"{DIVIDER_LINE}\n"
        f"{body_html}"
    )


# --------------------------------------------------------------------------- #
# Клавиатура и тексты
# --------------------------------------------------------------------------- #

BTN_REGLAMENT = "📄 Прислать регламент"
BTN_HELP = "❓ Что умеет бот"
BTN_SEARCH = "🔍 Найти пункт"

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_REGLAMENT)],
        [KeyboardButton(text=BTN_HELP)],
        [KeyboardButton(text=BTN_SEARCH)],
    ],
    resize_keyboard=True,
)

GREETING_TEXT = (
    "👋 Здравствуйте! Я бот корпоративной базы знаний ИТ-службы.\n\n"
    "Напишите мне вопрос обычными словами — я найду подходящий пункт "
    "регламента и укажу его номер и документ-источник.\n\n"
    "Используйте кнопки ниже или команду /help."
)

HELP_TEXT = (
    "❓ <b>Что я умею</b>\n\n"
    f"{BTN_REGLAMENT} — пришлю все файлы регламентов.\n"
    f"{BTN_SEARCH} — подскажу, как искать нужный пункт.\n\n"
    "Просто напишите вопрос или ключевые слова (например: "
    "«как сбросить пароль» или «настройка VPN»), и я найду наиболее "
    "подходящий пункт регламента.\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — эта справка\n"
    "/reglament — получить все файлы регламентов"
)

SEARCH_PROMPT_TEXT = (
    "🔍 Напишите вопрос или ключевые слова обычным сообщением — "
    "и я поищу подходящий пункт регламента."
)

NOT_FOUND_TEXT = (
    "🤷 Не нашёл подходящего пункта в базе знаний по вашему запросу.\n"
    "Попробуйте сформулировать вопрос другими словами или воспользуйтесь "
    f"кнопкой «{BTN_REGLAMENT}»."
)

EMPTY_KB_TEXT = (
    "⚠️ База знаний пуста: рядом со скриптом не найдено ни одного "
    ".md или .txt файла. Обратитесь к администратору бота."
)

NO_FILES_TEXT = "⚠️ Файлы регламентов не найдены рядом со скриптом."

# --------------------------------------------------------------------------- #
# Данные базы знаний (загружаются один раз при старте)
# --------------------------------------------------------------------------- #

KNOWLEDGE_ITEMS: List[KnowledgeItem] = []
KB_FILES: List[Path] = []

# --------------------------------------------------------------------------- #
# Хендлеры
# --------------------------------------------------------------------------- #

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(GREETING_TEXT, reply_markup=main_keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_keyboard)


async def send_reglaments(message: Message) -> None:
    if not KB_FILES:
        await message.answer(NO_FILES_TEXT, reply_markup=main_keyboard)
        return

    await message.answer(
        f"📄 Отправляю {len(KB_FILES)} файл(ов) регламента...",
        reply_markup=main_keyboard,
    )
    for file_path in KB_FILES:
        try:
            await message.answer_document(FSInputFile(file_path))
        except Exception:
            logger.exception("Не удалось отправить файл %s", file_path.name)
            await message.answer(
                f"⚠️ Не удалось отправить файл {html.escape(file_path.name)}"
            )


@router.message(Command("reglament"))
async def cmd_reglament(message: Message) -> None:
    await send_reglaments(message)


@router.message(F.text == BTN_REGLAMENT)
async def btn_reglament(message: Message) -> None:
    await send_reglaments(message)


@router.message(F.text == BTN_HELP)
async def btn_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_keyboard)


@router.message(F.text == BTN_SEARCH)
async def btn_search(message: Message) -> None:
    await message.answer(SEARCH_PROMPT_TEXT, reply_markup=main_keyboard)


@router.message(F.text)
async def handle_text(message: Message) -> None:
    query = (message.text or "").strip()

    if not KNOWLEDGE_ITEMS:
        await message.answer(EMPTY_KB_TEXT, reply_markup=main_keyboard)
        return

    try:
        found = find_item(query, KNOWLEDGE_ITEMS)
    except Exception:
        logger.exception("Ошибка при поиске по запросу: %r", query)
        await message.answer(
            "⚠️ Произошла ошибка при поиске. Попробуйте ещё раз.",
            reply_markup=main_keyboard,
        )
        return

    if found is None:
        await message.answer(NOT_FOUND_TEXT, reply_markup=main_keyboard)
    else:
        await message.answer(format_item_response(found), reply_markup=main_keyboard)


@router.message()
async def handle_other(message: Message) -> None:
    await message.answer(
        "Я понимаю только текстовые сообщения. Напишите ваш вопрос текстом.",
        reply_markup=main_keyboard,
    )


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #


async def main() -> None:
    global KNOWLEDGE_ITEMS, KB_FILES

    if not BOT_TOKEN:
        logger.error(
            "Не задана переменная окружения BOT_TOKEN. "
            "Создайте файл .env рядом со скриптом со строкой "
            "BOT_TOKEN=ваш_токен, либо задайте переменную окружения вручную."
        )
        sys.exit(1)

    logger.info("Сканирование .md и .txt файлов в папке: %s", SCRIPT_DIR)
    KNOWLEDGE_ITEMS, KB_FILES = load_knowledge_base()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    logger.info("Бот запущен и слушает сообщения (Ctrl+C для остановки)")
    try:
        await dispatcher.start_polling(bot)
    except Exception:
        logger.exception("Бот аварийно завершил работу")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
