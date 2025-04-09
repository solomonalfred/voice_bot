import logging
import os
import asyncio
import ffmpeg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import torch
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
from TTS.config.shared_configs import BaseDatasetConfig
torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, XttsArgs, BaseDatasetConfig])
from TTS.api import TTS
tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7980337356:AAGLO79pibSWfAOQbHJEdtRsby7RsBIZ-3Y"

SAVE_DIR = "voice_messages"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Озвучить текст", callback_data="record_text")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Нажмите кнопку ниже для озвучивания текста:",
        reply_markup=reply_markup,
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "record_text":
        await query.edit_message_text(text="Пожалуйста, введите текст, который вы хотите озвучить:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["text"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Загрузить MP3", callback_data="upload_mp3")],
        [InlineKeyboardButton("Записать голосовое сообщение", callback_data="record_voice")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Выберите способ предоставления записи для озвучивания текста:",
        reply_markup=reply_markup,
    )

def convert_to_wav(ogg_path: str, wav_path: str) -> (bool, str):
    try:
        stream = ffmpeg.input(ogg_path)
        stream = ffmpeg.output(stream, wav_path, format="wav")
        stream = ffmpeg.overwrite_output(stream)
        ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
        return True, ""
    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else str(e)
        return False, error_message
    except Exception as e:
        return False, str(e)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    if voice:
        file_id = voice.file_id
        new_file = await context.bot.get_file(file_id)
        ogg_file_path = os.path.join(SAVE_DIR, f"{file_id}.ogg")
        wav_file_path = os.path.join(SAVE_DIR, f"{file_id}.wav")
        await new_file.download_to_drive(ogg_file_path)
        success, error_message = await asyncio.to_thread(convert_to_wav, ogg_file_path, wav_file_path)
        if not success:
            logger.error("Ошибка конвертации: %s", error_message)
            await update.message.reply_text("Ошибка при конвертации голосового сообщения в формат WAV.")
        else:
            await update.message.reply_text("Голосовое сообщение успешно сохранено в формате WAV!")
        text = context.user_data.get("text")
        if text:
            await generate_tts_from_voice(text, wav_file_path, update)
        os.remove(ogg_file_path)
    else:
        await update.message.reply_text("Пожалуйста, отправьте голосовое сообщение.")


async def generate_tts_from_voice(text, wav_path, update: Update):
    tts.tts_to_file(
        text=text,
        file_path="out.wav",
        speaker_wav=wav_path,
        language="ru"
    )
    with open("out.wav", "rb") as f:
        await update.message.reply_audio(audio=InputFile(f, filename="output.wav"))


async def mp3_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    audio = update.message.audio
    if audio:
        file_id = audio.file_id
        new_file = await context.bot.get_file(file_id)
        mp3_file_path = os.path.join(SAVE_DIR, f"{file_id}.mp3")
        await new_file.download_to_drive(mp3_file_path)
        if audio.duration < 5:
            await update.message.reply_text("Запись должна быть длиной не менее 5 секунд.")
        else:
            await update.message.reply_text("Запись получена. Генерируем озвучку текста...")
            text = context.user_data.get("text")
            if text:
                await generate_tts_from_mp3(text, mp3_file_path, update)
            os.remove(mp3_file_path)
    else:
        await update.message.reply_text("Пожалуйста, отправьте MP3 файл.")


async def generate_tts_from_mp3(text, mp3_path, update: Update):
    tts.tts_to_file(
        text=text,
        file_path="out.wav",
        speaker_wav=mp3_path,
        language="ru"
    )
    with open("out.wav", "rb") as f:
        await update.message.reply_audio(audio=InputFile(f, filename="output.wav"))


def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^record_text$"))
    application.add_handler(MessageHandler(filters.TEXT, text_handler))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^record_voice$"))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^upload_mp3$"))
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    application.add_handler(MessageHandler(filters.AUDIO, mp3_handler))
    application.run_polling()


if __name__ == '__main__':
    main()
