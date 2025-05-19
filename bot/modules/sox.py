import os
import subprocess
from pyrogram.types import Message
from pyrogram import Client
import time


async def spectrum_handler(_, message):
    replied = message.reply_to_message

    if not (replied.audio or replied.document):
        await message.reply_text("Reply to an audio or document message with /sox.")
        return

    progress_message = await message.reply("Downloading... 0%")

    last_update = 0

    async def progress(current, total):
        nonlocal last_update
        now = time.time()
        if now - last_update > 1:  # update every 1 second
            percentage = current * 100 / total
            await progress_message.edit(f"Downloading... {percentage:.1f}%")
            last_update = now

    file_path = await replied.download(progress=progress)
    output_image = "spectrum.png"

    try:
        await progress_message.edit("Generating spectrum...")
        subprocess.run(
            ["sox", file_path, "-n", "spectrogram", "-o", output_image],
            check=True,
        )
        await message.reply_photo(output_image)
        await progress_message.delete()
    except subprocess.CalledProcessError:
        await progress_message.edit(
            "Failed to generate spectrum. Unsupported format or corrupted file."
        )
    finally:
        os.remove(file_path)
        if os.path.exists(output_image):
            os.remove(output_image)