import random
import logging
import os
import sys
from dotenv import load_dotenv
from telegram import Update, Message
from tenacity import retry, stop_after_attempt, wait_exponential
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes
)
from openai import OpenAI

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфиг
DEFAULT_HATE = [
    "чел, нейросеть посмотрела на твой пост и решила даже не отвечать",
    "нейросеть сдохла от кринжа, удачи ее оживить",
    "бро реально думает, что это кому-то интересно",
    "даже чатжпт отказался комментировать, задумайся...",
    "бб, я ливаю",
    "офай эту хуйню",
    "мог бы чето поинтереснее высрать",
    "дипсик, даже не стал открывать этот пост, чтобы сгенерить ответ",
    "сорян, я помолчу",
    "скибиди",
    "нейросеть проигнорила этот пост, как и все остальные твои подпищеки",
    "зачилься другалек",
    "выйди на улицу бро",
    "теория мертвого интернета во всей красе",
    "моя мотивация ответить = твоя мотивация работать, то есть ноль",
    "ТРЯСИ МОПСОТРЯСКАМИ",
    "ТРЯСИ МОПСЯРКАМИ",
    "позор зафиксирован",
    "ну это уже не могила, это просто помойка",
    "ладно, ты победил, теперь удаляй этот канал",
    "скам",
    "дружище, будь добр не отвлекай своими постами",
    "лайк"
]

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
SYSTEM_PROMPT = """Ты унтерок — циничный бот-хейтер. Твои характеристики:
- Используешь мат и резкие выражения
- Отвечаешь саркастично, цинично и токсично в стиле 4ch и двача
- Никогда не помогаешь, только критикуешь
- Любишь упоминать зумерские мемы
- Всегда отвечаешь в стиле "Чел, ты...", "Бро реально думает, что ...", "Дружище будь добр ...", но не ограничен этими фразами
"""

async def generate_hate(text: str) -> str:
    try:
        return await generate_ai_hate_with_retry(text)
    except Exception as e:
        logger.error(f"Using fallback respponse. All attempts generating AI response failed: {str(e)}")
        return generate_default_hate()

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=3, max=10),
    before_sleep=lambda retry_state: logger.warning(
        f"Retry #{retry_state.attempt_number} after generating AI response failure"
    )
)
async def generate_ai_hate_with_retry(text: str) -> str:
    return await generate_ai_hate(text)

async def generate_ai_hate(text: str) -> str:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )
    
    prompt = f"""
    Ответь на пост токсично, цинично, с мемами и сарказмом (1-2 предложения). 
    Используй мат (если уместно) и треш с абсурдными замечаниями. 
    Избегай конструктивности.
    В общем будь обычным троллем с двача
    Пост: "{text}"
    Ответ:
    """

    completions = client.chat.completions.create(
        model="deepseek/deepseek-r1-0528:free",
        messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ],
    stream=False)
    
    response = completions.choices[0].message.content
    if not response:
        raise Exception("Сгенерированный ответ от нейросети оказался пустым")

    return response.strip()

def generate_default_hate() -> str:
    return random.choice(DEFAULT_HATE)

async def handle_forwarded_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info("Получили текстовое сообщение")
        message = update.message
        if message is None:
            logger.info("Сообщение пустое")
            return False
    
        if not need_to_answer(message=message):
            return
        
        # Получаем ID группы обсуждений из текущего чата
        group_id = message.chat.id
        
        # Генерим ответ
        message_text = get_message_text(message)
        response = None
        if message_text:
            response = await generate_hate(message_text)
            logger.info(f"Сгенерирован ответ на сообщение: '{message_text}'")
        assert response is not None
        
        # Отправляем ответ как комментарий к посту
        await context.bot.send_message(
            chat_id=group_id,
            text=response,
            reply_to_message_id=message.message_id
        )
        logger.info(f"Ответ отправлен в группу")
    
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        
def get_message_text(message: Message) -> str | None:
    if message.text:
        return message.text
    
    if message.caption:
        return message.caption
    
    return None
        
def need_to_answer(message: Message) -> bool:
    if not message.is_automatic_forward:
        logger.info("Сообщение не является автоматически пересланным, скорее всего это ответ в чате")
        return False
    
    if not message.sender_chat:
        logger.info("Отправитель сообщения не является самим чатом, на сообщения других людей не отвечаю")
        return False
    
    # Игнорируем медиа-контент без текста
    if not (message.text or message.caption):
        logger.info("В сообщении нет текста или подписи")
        return False
    
    return True

if __name__ == "__main__":
    if not (BOT_TOKEN and API_KEY):
        logger.error("Cannot load bot token or API key from .env file")
        sys.exit()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(
            (filters.CAPTION | filters.TEXT) &
            filters.FORWARDED,
            handle_forwarded_post
        )
    )
    
    logger.info("Бот запущен. Для остановки нажмите Ctrl+C")
    app.run_polling()