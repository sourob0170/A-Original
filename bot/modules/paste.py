import os
from asyncio import create_task

import aiofiles
from pyrogram.types import Message

from bot import LOGGER
from bot.helper.ext_utils.pasting_services import katbin_paste
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


async def paste_text(client, message: Message):
    """
    Paste the text in katb.in website.

    Args:
        client: The Pyrogram client instance
        message: The message containing text to paste

    Returns:
        None
    """
    paste_usage = (
        "**📋 Paste Command Usage**\n\n"
        "Paste text to katb.in website. You can use this command in three ways:\n\n"
        "1️⃣ **Direct text:** <pre><code>/paste your text here</code></pre>\n"
        "2️⃣ **Reply to a message:** Reply to any text message with <pre><code>/paste</code></pre>\n"
        "3️⃣ **Reply to a file:** Reply to a text file with <pre><code>/paste</code></pre>\n\n"
        "**Supported file types:** <pre><code>.txt, .log, .json, .xml, .csv, .md, .py, .js, .html, .css, .conf, .ini, .sh, .bat</code></pre> and more"
    )

    # Send initial reply
    paste_reply = await send_message(message, "Pasting...")
    replied_message = message.reply_to_message

    try:
        # Get content from command arguments
        if len(message.command) > 1:
            content = message.text.split(None, 1)[1]

        # Get content from replied message text
        elif replied_message and replied_message.text:
            content = replied_message.text

        # Get content from replied document
        elif replied_message and replied_message.document:
            # Check if it's a text file by mime type or file extension
            is_text_file = False

            # Check mime type
            if replied_message.document.mime_type:
                is_text_file = any(
                    format in replied_message.document.mime_type.lower()
                    for format in ("text", "json", "xml", "csv", "html", "plain")
                )

            # Check file extension if mime type check failed
            if not is_text_file and replied_message.document.file_name:
                file_name = replied_message.document.file_name.lower()
                text_extensions = (
                    ".txt",
                    ".log",
                    ".json",
                    ".xml",
                    ".csv",
                    ".md",
                    ".py",
                    ".js",
                    ".html",
                    ".css",
                    ".conf",
                    ".ini",
                    ".sh",
                    ".bat",
                )
                is_text_file = any(
                    file_name.endswith(ext) for ext in text_extensions
                )

            if is_text_file:
                # Download the file
                file_path = os.path.join(os.getcwd(), "temp_file")
                await paste_reply.edit("Downloading file...")
                await message.reply_to_message.download(file_path)

                try:
                    # Read the file content
                    await paste_reply.edit("Reading file content...")
                    async with aiofiles.open(
                        file_path, encoding="utf-8", errors="replace"
                    ) as file:
                        content = await file.read()

                    # Limit content size if too large
                    if len(content) > 1000000:  # ~1MB limit
                        content = (
                            content[:1000000]
                            + "\n\n... (content truncated due to size)"
                        )
                        await paste_reply.edit(
                            "File is very large, content will be truncated..."
                        )
                except UnicodeDecodeError:
                    await paste_reply.edit(
                        "Error: Cannot read file - it appears to be a binary file, not text."
                    )
                    await auto_delete_message(paste_reply, time=60)
                    if os.path.exists(file_path):
                        os.remove(file_path)

                    # Auto-delete the command message and replied message
                    create_task(auto_delete_message(message, time=300))
                    if replied_message:
                        create_task(auto_delete_message(replied_message, time=300))
                    return
                except Exception as e:
                    await paste_reply.edit(f"Error reading file: {e!s}")
                    await auto_delete_message(paste_reply, time=60)
                    if os.path.exists(file_path):
                        os.remove(file_path)

                    # Auto-delete the command message and replied message
                    create_task(auto_delete_message(message, time=300))
                    if replied_message:
                        create_task(auto_delete_message(replied_message, time=300))
                    return
                finally:
                    # Remove the temporary file
                    if os.path.exists(file_path):
                        os.remove(file_path)

                await paste_reply.edit("Pasting content...")
            else:
                await paste_reply.edit(
                    "Error: The file doesn't appear to be a text file."
                )
                await auto_delete_message(paste_reply, time=60)

                # Auto-delete the command message and replied message
                create_task(auto_delete_message(message, time=300))
                if replied_message:
                    create_task(auto_delete_message(replied_message, time=300))
                return

        # No valid content found
        else:
            await paste_reply.edit(paste_usage)
            await auto_delete_message(paste_reply, time=60)

            # Auto-delete the command message
            create_task(auto_delete_message(message, time=300))
            if replied_message:
                create_task(auto_delete_message(replied_message, time=300))
            return

        # Check if content is too large for pasting
        if len(content) > 4000000:  # ~4MB limit (katbin might have lower limits)
            await paste_reply.edit("Error: Content is too large for pasting (>4MB).")
            await auto_delete_message(paste_reply, time=60)

            # Auto-delete the command message and replied message
            create_task(auto_delete_message(message, time=300))
            if replied_message:
                create_task(auto_delete_message(replied_message, time=300))
            return

        # Paste the content
        await paste_reply.edit("Uploading to katb.in...")
        output = await katbin_paste(content)

        # Create a nice response with content info
        content_lines = content.count("\n") + 1
        content_size = len(content)
        size_str = (
            f"{content_size / 1024:.1f} KB"
            if content_size >= 1024
            else f"{content_size} bytes"
        )

        response = "<b>Successfully pasted to katb.in</b>\n\n"
        response += f"• <b>URL:</b> <blockquote>{output}</blockquote>\n"
        response += f"• <b>Size:</b> <pre><code>{size_str}</code></pre>\n"
        response += f"• <b>Lines:</b> <pre><code>{content_lines}</code></pre>\n"
        response += "\n<i>This message and the command will be auto-deleted in 5 minutes.</i>"

        await paste_reply.edit(response, disable_web_page_preview=True)

        # Auto-delete the command message and replied message after 5 minutes
        create_task(
            auto_delete_message(message, time=300)
        )  # 5 minutes = 300 seconds
        if replied_message:
            create_task(auto_delete_message(replied_message, time=300))

    except Exception as e:
        LOGGER.error(f"Error in paste command: {e}")
        await paste_reply.edit(f"Error: {e!s}")
        await auto_delete_message(paste_reply, time=60)

        # Also auto-delete the command message and replied message in case of error
        create_task(auto_delete_message(message, time=300))
        if replied_message:
            create_task(auto_delete_message(replied_message, time=300))
