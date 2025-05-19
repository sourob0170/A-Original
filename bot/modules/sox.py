import os
import subprocess


async def spectrum_handler(_, message):
    replied = message.reply_to_message

    if replied.audio or replied.document:
        file = replied.audio or replied.document
        file_path = await replied.download()
        output_image = "spectrum.png"

        try:
            subprocess.run(
                ["sox", file_path, "-n", "spectrogram", "-o", output_image],
                check=True,
            )
            await message.reply_photo(output_image)
        except subprocess.CalledProcessError:
            await message.reply_text(
                "Failed to generate spectrum. Unsupported format or corrupted file."
            )
        finally:
            os.remove(file_path)
            if os.path.exists(output_image):
                os.remove(output_image)
    else:
        await message.reply_text("Reply to an audio or document message with /sox.")
