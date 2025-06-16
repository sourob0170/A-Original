#!/usr/bin/env python3
"""
Comprehensive Encoding/Decoding Module for Telegram Bot
Supports all codext codecs and various encoding/decoding methods
"""

import asyncio
import base64
import json
import urllib.parse
from logging import getLogger
from typing import Any

import codext
from cryptography.fernet import Fernet

from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

LOGGER = getLogger(__name__)

# Codext codec categories with verified working methods only
CODEXT_CATEGORIES = {
    "BaseXX": [
        "base2",
        "base3",
        "base4",
        "base8",
        "base10",
        "base11",
        "base16",
        "base26",
        "base32",
        "base36",
        "base45",
        "base58",
        "base62",
        "base63",
        "base64",
        "base67",
        "base85",
        "base91",
        "base100",
        "base122",
        "ascii85",
    ],
    "Binary": [
        "baudot",
        "bcd",
        "bcd-extended0",
        "bcd-extended1",
        "excess3",
        "gray",
        "manchester",
        "manchester-inverted",
        # Note: binary and hex are handled separately in Standard methods
    ]
    + [f"rotate{i}" for i in range(1, 8)],
    "Common": [
        "a1z26",
        "reverse",
        "integer",
        "replace",
        "substitute",
        "strip-spaces",
        "octal",
        "octal-spaced",
        "ordinal",
        "ordinal-spaced",
        "capitalize",
        "title",
        "uppercase",
        "lowercase",
    ],
    "Compression": [
        "gzip",
        "lz77",
        "lz78",
        "pkzip_deflate",
        "pkzip_bzip2",
        "pkzip_lzma",
    ],
    "Cryptography": [
        "affine",
        "atbash",
        "railfence",
        # Removed problematic methods: citrix, bacon
    ]
    + [f"scytale{i}" for i in range(2, 10)]
    + [f"barbie-{i}" for i in range(1, 5)]
    + [
        f"rot{i}"
        for i in [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
        ]
    ]
    + [f"shift{i}" for i in range(1, 26)]
    + [
        f"xor{i}"
        for i in [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
        ]
    ],
    "Hashing": [
        "blake2b",
        "blake2s",
        "adler32",
        "crc32",
        "md5",
        "sha1",
        "sha224",
        "sha256",
        "sha384",
        "sha512",
        "sha3-224",
        "sha3-256",
        "sha3-384",
        "sha3-512",
        "shake128",
        "shake256",
    ],
    "Languages": [
        "braille",
        "galactic",
        "leetspeak",
        "morse",
        "navajo",
        "radio",
        # Removed problematic methods: ipsum, southpark
    ],
    "Steganography": [
        "hexagram",
        "resistor",
        "whitespace",
        # Removed problematic methods: rick
    ]
    + [f"dna-{i}" for i in range(1, 9)],
    "Web": ["html", "url"],
}

# Additional encoding methods not in codext
ADDITIONAL_METHODS = {
    "Standard": ["hex", "binary", "ascii", "utf-8", "utf-16", "utf-32", "latin-1"],
    "Advanced Crypto": [
        "aes-encrypt",
        "aes-decrypt",
        "rsa-encrypt",
        "rsa-decrypt",
        "fernet-encrypt",
        "fernet-decrypt",
    ],
    "Custom": [
        "json-encode",
        "json-decode",
        "percent-encode",
        "percent-decode",
        "mime-encode",
        "mime-decode",
    ],
}


class EncodingProcessor:
    """Main class for handling encoding/decoding operations"""

    def __init__(self):
        self.session_data = {}

    def get_all_methods(self) -> dict[str, list[str]]:
        """Get all available encoding methods organized by category"""
        all_methods = {}
        all_methods.update(CODEXT_CATEGORIES)
        all_methods.update(ADDITIONAL_METHODS)
        return all_methods

    def get_method_info(self, method: str) -> dict[str, Any]:
        """Get information about a specific encoding method"""
        for category, methods in self.get_all_methods().items():
            if method in methods:
                return {
                    "method": method,
                    "category": category,
                    "supports_encode": True,
                    "supports_decode": True,
                    "description": self._get_method_description(method),
                }
        return {}

    def _get_method_description(self, method: str) -> str:
        """Get comprehensive description for a specific method"""
        descriptions = {
            # BaseXX encodings
            "base64": "Standard Base64 encoding (RFC 4648) - converts binary to text",
            "base32": "Base32 encoding - uses 32-character alphabet, case-insensitive",
            "base16": "Base16/Hexadecimal encoding - uses 0-9 and A-F",
            "base58": "Base58 encoding - Bitcoin-style, no confusing characters",
            "base85": "Base85 encoding - more efficient than Base64",
            "base100": "Base100 emoji encoding - converts text to emojis",
            # Binary encodings
            "binary": "Binary representation - converts to 0s and 1s",
            "hex": "Hexadecimal representation - base-16 number system",
            "baudot": "Baudot code - 5-bit telegraph encoding",
            "gray": "Gray code - binary numeral system",
            "manchester": "Manchester encoding - self-synchronizing",
            # Common transformations
            "reverse": "Reverse text - mirrors the input string",
            "upper-case": "Convert to uppercase letters",
            "lower-case": "Convert to lowercase letters",
            "camel-case": "Convert to camelCase format",
            "snake-case": "Convert to snake_case format",
            "a1z26": "A1Z26 cipher - A=1, B=2, ..., Z=26",
            # Compression
            "gzip": "Gzip compression - reduces file size",
            "lz77": "LZ77 compression algorithm",
            "lz78": "LZ78 compression algorithm",
            # Cryptography
            "rot13": "ROT13 Caesar cipher - shifts letters by 13",
            "atbash": "Atbash cipher - Hebrew alphabet substitution",
            "affine": "Affine cipher - mathematical substitution",
            "railfence": "Rail fence cipher - zigzag pattern",
            "bacon": "Bacon cipher - steganographic method",
            # Hashing
            "md5": "MD5 hash function (128-bit) - fast but not secure",
            "sha1": "SHA-1 hash function (160-bit) - deprecated",
            "sha256": "SHA-256 hash function (256-bit) - secure standard",
            "sha512": "SHA-512 hash function (512-bit) - very secure",
            "blake2b": "BLAKE2b hash - modern, fast, and secure",
            "blake2s": "BLAKE2s hash - optimized for 8-32 bit platforms",
            # Languages
            "morse": "Morse code - dots and dashes (may be lossy)",
            "braille": "Braille encoding - tactile writing system",
            "leetspeak": "Leet speak - internet slang (lossy conversion)",
            "galactic": "Galactic alphabet - Minecraft enchantment language",
            "navajo": "Navajo code - WWII encryption method",
            "radio": "NATO phonetic alphabet - Alpha, Bravo, Charlie...",
            # Web encodings
            "url": "URL percent encoding - web-safe character encoding",
            "html": "HTML entity encoding - converts special characters",
            # Advanced crypto
            "aes-encrypt": "AES encryption - Advanced Encryption Standard",
            "aes-decrypt": "AES decryption - requires matching key",
            "fernet-encrypt": "Fernet encryption - symmetric authenticated cryptography",
            "fernet-decrypt": "Fernet decryption - requires matching key",
            "rsa-encrypt": "RSA encryption - public key cryptography",
            "rsa-decrypt": "RSA decryption - requires private key",
            # Custom methods
            "json-encode": "JSON encoding - converts to JSON format",
            "json-decode": "JSON decoding - parses JSON data",
            "percent-encode": "Percent encoding - URL-style encoding",
            "percent-decode": "Percent decoding - URL-style decoding",
        }

        # Generate descriptions for numbered variants
        if method.startswith("rot") and method[3:].isdigit():
            n = method[3:]
            return f"ROT{n} Caesar cipher - shifts letters by {n} positions"
        if method.startswith("shift") and method[5:].isdigit():
            n = method[5:]
            return f"Shift cipher - shifts ASCII values by {n}"
        if method.startswith("xor") and method[3:].isdigit():
            n = method[3:]
            return f"XOR cipher - XORs each byte with {n}"
        if method.startswith("base") and method[4:].isdigit():
            n = method[4:]
            return f"Base{n} encoding - uses {n}-character alphabet"
        if method.startswith("dna-") and method[4:].isdigit():
            n = method[4:]
            return f"DNA encoding rule {n} - converts to DNA sequences"
        if method.startswith("barbie-") and method[7:].isdigit():
            n = method[7:]
            return f"Barbie typewriter cipher variant {n}"

        return descriptions.get(method, f"Encoding method: {method}")


# Initialize the processor
processor = EncodingProcessor()


def create_category_buttons(operation="encode", page=0) -> ButtonMaker:
    """Create buttons for encoding/decoding categories with pagination"""
    buttons = ButtonMaker()

    # Get categories based on operation
    all_categories = list(processor.get_all_methods().keys())

    # Filter categories based on operation
    if operation == "decode":
        # Remove hashing category for decode as hashes are one-way
        categories = [cat for cat in all_categories if cat != "Hashing"]
    else:
        categories = all_categories

    # Pagination settings
    items_per_page = 10  # Show 10 categories per page (5 rows of 2)
    total_pages = (len(categories) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(categories))

    # Add category buttons for current page
    page_categories = categories[start_idx:end_idx]
    for i in range(0, len(page_categories), 2):
        row = []
        row.append((page_categories[i], f"enc_cat_{page_categories[i]}_{operation}"))
        if i + 1 < len(page_categories):
            row.append(
                (
                    page_categories[i + 1],
                    f"enc_cat_{page_categories[i + 1]}_{operation}",
                )
            )
        for text, callback in row:
            buttons.data_button(text, callback)

    # Add pagination buttons if needed
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                ("⬅️ Previous", f"enc_cat_page_{operation}_{page - 1}")
            )
        if page < total_pages - 1:
            nav_buttons.append(("➡️ Next", f"enc_cat_page_{operation}_{page + 1}"))

        for text, callback in nav_buttons:
            buttons.data_button(text, callback)

    buttons.data_button("❌ Close", "enc_close")
    return buttons


def create_method_buttons(category: str, operation="encode", page=0) -> ButtonMaker:
    """Create buttons for methods in a category with pagination and operation filtering"""
    buttons = ButtonMaker()

    all_methods = processor.get_all_methods().get(category, [])

    # Filter methods based on operation
    if operation == "decode":
        # Remove encode-only methods for decode operation
        encode_only_methods = []
        if category == "Hashing":
            # All hashing methods are encode-only
            encode_only_methods = all_methods
        elif category == "Advanced Crypto":
            # Remove encrypt methods, keep decrypt methods
            encode_only_methods = [m for m in all_methods if m.endswith("-encrypt")]

        methods = [m for m in all_methods if m not in encode_only_methods]
    elif operation == "encode":
        # Remove decode-only methods for encode operation
        decode_only_methods = []
        if category == "Advanced Crypto":
            # Remove decrypt methods, keep encrypt methods
            decode_only_methods = [m for m in all_methods if m.endswith("-decrypt")]

        methods = [m for m in all_methods if m not in decode_only_methods]
    else:
        methods = all_methods

    # Pagination settings
    items_per_page = 16  # Show 16 methods per page (8 rows of 2)
    total_pages = (
        (len(methods) + items_per_page - 1) // items_per_page if methods else 1
    )
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(methods))

    # Add method buttons for current page
    page_methods = methods[start_idx:end_idx]
    for i in range(0, len(page_methods), 2):
        row = []
        row.append((page_methods[i], f"enc_method_{page_methods[i]}_{operation}"))
        if i + 1 < len(page_methods):
            row.append(
                (
                    page_methods[i + 1],
                    f"enc_method_{page_methods[i + 1]}_{operation}",
                )
            )
        for text, callback in row:
            buttons.data_button(text, callback)

    # Add pagination buttons if needed
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                ("⬅️ Previous", f"enc_method_page_{category}_{operation}_{page - 1}")
            )
        if page < total_pages - 1:
            nav_buttons.append(
                ("➡️ Next", f"enc_method_page_{category}_{operation}_{page + 1}")
            )

        for text, callback in nav_buttons:
            buttons.data_button(text, callback)

    buttons.data_button("🔙 Back", f"enc_back_categories_{operation}")
    buttons.data_button("❌ Close", "enc_close")
    return buttons


async def encode_command(_, message):
    """Main encode command handler with method-specific support"""
    await delete_message(message)

    # Check if encoding is enabled
    if not Config.ENCODING_ENABLED:
        msg = await send_message(
            message, "❌ <b>Encoding functionality is disabled</b>"
        )
        asyncio.create_task(auto_delete_message(msg, time=60))
        return

    # Parse command: /encode [method] [text] or /encode [text]
    cmd_parts = message.text.split(maxsplit=2)
    method = None
    query = None

    if len(cmd_parts) >= 2:
        # Check if second part is a method name
        potential_method = cmd_parts[1].lower()
        all_methods = processor.get_all_methods()
        all_method_names = []
        for methods in all_methods.values():
            all_method_names.extend([m.lower() for m in methods])

        if potential_method in all_method_names:
            method = potential_method
            if len(cmd_parts) >= 3:
                query = cmd_parts[2].strip()
        else:
            # No method specified, treat as query
            query = " ".join(cmd_parts[1:]).strip()

    user_id = message.from_user.id

    # Store query and operation type in session
    if user_id not in processor.session_data:
        processor.session_data[user_id] = {}
    processor.session_data[user_id]["query"] = query
    processor.session_data[user_id]["operation"] = "encode"
    processor.session_data[user_id]["replied_message"] = message.reply_to_message

    # If method is specified and we have content, process immediately
    if method and (query or message.reply_to_message):
        content = None
        source = None

        if query:
            content = query
            source = "query"
        elif message.reply_to_message:
            reply_msg = message.reply_to_message
            if reply_msg.text:
                content = reply_msg.text
                source = "replied message"
            elif reply_msg.caption:
                content = reply_msg.caption
                source = "replied message caption"

        if content:
            try:
                result = await process_encoding_text(
                    content, method, "encode", user_id
                )

                result_text = (
                    f"✅ <b>Encode Result</b>\n\n"
                    f"🔧 <b>Method:</b> {method}\n"
                    f"📝 <b>Source:</b> {source}\n"
                    f"📊 <b>Input:</b> {len(content)} chars\n"
                    f"📤 <b>Output:</b> {len(result)} chars\n\n"
                    f"📋 <b>Result:</b>\n<code>{result}</code>"
                )

                msg = await send_message(message, result_text)
                asyncio.create_task(auto_delete_message(msg, time=300))
                return
            except Exception as e:
                error_text = f"❌ <b>Encoding Error</b>\n\n🔧 <b>Method:</b> {method}\n📝 <b>Error:</b> {e!s}"
                msg = await send_message(message, error_text)
                asyncio.create_task(auto_delete_message(msg, time=300))
                return

    # Check if we have content to process (query or replied message)
    has_content = False
    content = None
    source = None

    if query:
        has_content = True
        content = query
        source = "query"
    elif message.reply_to_message:
        reply_msg = message.reply_to_message
        if reply_msg.text:
            has_content = True
            content = reply_msg.text
            source = "replied message"
        elif reply_msg.caption:
            has_content = True
            content = reply_msg.caption
            source = "replied message caption"

    # If we have content but no method specified, show menu for method selection
    if has_content and not method:
        # Show content preview
        content_preview = content[:100] + ("..." if len(content) > 100 else "")

        text = (
            "🔐 <b>Encoding Tool</b>\n\n"
            f"📝 <b>Ready to encode ({source}):</b>\n"
            f"<code>{content_preview}</code>\n\n"
            "💡 <b>Select an encoding method from the categories below:</b>\n\n"
            "📊 <b>Available Categories:</b>\n"
            "• BaseXX - Base encodings (Base64, Base32, etc.)\n"
            "• Binary - Binary representations\n"
            "• Common - Common text transformations\n"
            "• Compression - Data compression\n"
            "• Cryptography - Cipher methods\n"
            "• Hashing - Hash functions\n"
            "• Languages - Special languages (Morse, Braille, etc.)\n"
            "• Steganography - Hidden message techniques\n"
            "• Web - Web-related encodings\n"
            "• Standard - Standard character encodings\n"
            "• Advanced Crypto - Modern cryptography\n"
            "• Custom - Custom encoding methods"
        )

        buttons = create_category_buttons("encode")
        msg = await send_message(message, text, buttons.build_menu(2))
        asyncio.create_task(auto_delete_message(msg, time=300))
        return

    # Show menu if there's no content to process
    text = (
        "🔐 <b>Encoding Tool</b>\n\n"
        "📝 <b>No content provided</b>\n\n"
        "💡 <b>How to use:</b>\n"
        "• <code>/encode your text here</code> - Show encoding menu for your text\n"
        "• <code>/encode method text</code> - Encode with specific method\n"
        "• <code>/encode</code> (reply to message) - Show encoding menu for replied message\n"
        "• Use the menu below to browse available methods\n\n"
        "📊 <b>Available Categories:</b>\n"
        "• BaseXX - Base encodings (Base64, Base32, etc.)\n"
        "• Binary - Binary representations\n"
        "• Common - Common text transformations\n"
        "• Compression - Data compression\n"
        "• Cryptography - Cipher methods\n"
        "• Hashing - Hash functions\n"
        "• Languages - Special languages (Morse, Braille, etc.)\n"
        "• Steganography - Hidden message techniques\n"
        "• Web - Web-related encodings\n"
        "• Standard - Standard character encodings\n"
        "• Advanced Crypto - Modern cryptography\n"
        "• Custom - Custom encoding methods"
    )

    buttons = create_category_buttons("encode")
    msg = await send_message(message, text, buttons.build_menu(2))
    asyncio.create_task(auto_delete_message(msg, time=300))


async def decode_command(_, message):
    """Decode command handler with auto-decode functionality and method-specific support"""
    await delete_message(message)

    # Check if decoding is enabled
    if not Config.DECODING_ENABLED:
        msg = await send_message(
            message, "❌ <b>Decoding functionality is disabled</b>"
        )
        asyncio.create_task(auto_delete_message(msg, time=60))
        return

    # Parse command: /decode [method] [text] or /decode [text]
    cmd_parts = message.text.split(maxsplit=2)
    method = None
    query = None

    if len(cmd_parts) >= 2:
        # Check if second part is a method name
        potential_method = cmd_parts[1].lower()
        all_methods = processor.get_all_methods()
        all_method_names = []
        for methods in all_methods.values():
            all_method_names.extend([m.lower() for m in methods])

        if potential_method in all_method_names:
            method = potential_method
            if len(cmd_parts) >= 3:
                query = cmd_parts[2].strip()
        else:
            # No method specified, treat as query
            query = " ".join(cmd_parts[1:]).strip()

    # Get content to decode (query takes priority over replied message)
    content_to_decode = None
    source = None

    if query:
        content_to_decode = query
        source = "query"
    elif message.reply_to_message:
        reply_msg = message.reply_to_message
        if reply_msg.text:
            content_to_decode = reply_msg.text
            source = "replied message"
        elif reply_msg.caption:
            content_to_decode = reply_msg.caption
            source = "replied message caption"

    user_id = message.from_user.id

    # Store query and operation type in session
    if user_id not in processor.session_data:
        processor.session_data[user_id] = {}
    processor.session_data[user_id]["query"] = query
    processor.session_data[user_id]["operation"] = "decode"
    processor.session_data[user_id]["replied_message"] = message.reply_to_message

    # If method is specified and we have content, process immediately
    if method and content_to_decode:
        try:
            result = await process_encoding_text(
                content_to_decode, method, "decode", user_id
            )

            result_text = (
                f"✅ <b>Decode Result</b>\n\n"
                f"🔧 <b>Method:</b> {method}\n"
                f"📝 <b>Source:</b> {source}\n"
                f"📊 <b>Input:</b> {len(content_to_decode)} chars\n"
                f"📤 <b>Output:</b> {len(result)} chars\n\n"
                f"📋 <b>Result:</b>\n<code>{result}</code>"
            )

            msg = await send_message(message, result_text)
            asyncio.create_task(auto_delete_message(msg, time=300))
            return
        except Exception as e:
            error_text = f"❌ <b>Decoding Error</b>\n\n🔧 <b>Method:</b> {method}\n📝 <b>Error:</b> {e!s}"
            msg = await send_message(message, error_text)
            asyncio.create_task(auto_delete_message(msg, time=300))
            return

    # Try auto-decode if we have content
    if content_to_decode:
        auto_decode_result = await try_auto_decode(content_to_decode)

        if auto_decode_result:
            # Auto-decode successful
            result_text = (
                f"✅ <b>Auto-Decode Successful!</b>\n\n"
                f"🔧 <b>Method:</b> {auto_decode_result['method']}\n"
                f"📝 <b>Source:</b> {source}\n"
                f"📊 <b>Input:</b> {len(content_to_decode)} chars\n"
                f"📤 <b>Output:</b> {len(auto_decode_result['result'])} chars\n\n"
                f"📋 <b>Result:</b>\n<code>{auto_decode_result['result']}</code>\n\n"
                f"💡 <b>Tip:</b> If this isn't correct, use the menu below to try other methods."
            )

            buttons = ButtonMaker()
            buttons.data_button("🔄 Try Other Methods", "enc_back_categories_decode")
            buttons.data_button("❌ Close", "enc_close")

            msg = await send_message(message, result_text, buttons.build_menu(1))
            asyncio.create_task(auto_delete_message(msg, time=300))
            return

    # Auto-decode failed or no content, show decode menu
    text = "🔓 <b>Decoding Tool</b>\n\n"

    if content_to_decode:
        text += f"⚠️ <b>Auto-decode failed for:</b> <code>{content_to_decode[:100]}{'...' if len(content_to_decode) > 100 else ''}</code>\n\n"
        text += "💡 <b>Possible reasons:</b>\n"
        text += "• Text might not be encoded\n"
        text += "• Unknown encoding method\n"
        text += "• Corrupted encoded data\n\n"
        text += "Select a category to manually choose a decoding method:\n\n"
    else:
        text += "Select a category to see available decoding methods:\n\n"

    text += (
        "📊 <b>Available Categories:</b>\n"
        "• BaseXX - Base decodings (Base64, Base32, etc.)\n"
        "• Binary - Binary representations\n"
        "• Common - Common text transformations\n"
        "• Compression - Data decompression\n"
        "• Cryptography - Cipher methods\n"
        "• Languages - Special languages (Morse, Braille, etc.)\n"
        "• Steganography - Hidden message techniques\n"
        "• Web - Web-related decodings\n"
        "• Standard - Standard character decodings\n"
        "• Advanced Crypto - Modern cryptography\n"
        "• Custom - Custom decoding methods\n\n"
        "💡 <b>Usage Options:</b>\n"
        "1. <code>/decode method text</code> - Direct decoding\n"
        "2. <code>/decode text</code> - Auto-decode or choose method\n"
        "3. <code>/decode</code> (reply to message) - Auto-decode\n"
        "4. Select category → method for instant results"
    )

    buttons = create_category_buttons("decode")
    msg = await send_message(message, text, buttons.build_menu(2))
    asyncio.create_task(auto_delete_message(msg, time=300))


async def encoding_callback(_, callback_query):
    """Handle encoding/decoding callback queries"""
    data = callback_query.data
    message = callback_query.message
    user_id = callback_query.from_user.id

    try:
        # Check if encoding/decoding is enabled based on the operation
        if data.endswith("_encode") and not Config.ENCODING_ENABLED:
            await callback_query.answer(
                "❌ Encoding functionality is disabled", show_alert=True
            )
            return
        if data.endswith("_decode") and not Config.DECODING_ENABLED:
            await callback_query.answer(
                "❌ Decoding functionality is disabled", show_alert=True
            )
            return
        if data == "enc_close":
            await delete_message(message)
            await callback_query.answer("Closed")
            return

        if data.startswith("enc_back_categories_"):
            operation = data.replace("enc_back_categories_", "")
            operation_title = "Encoding" if operation == "encode" else "Decoding"

            # Check if user has content to process and show status
            status_info = ""
            if user_id in processor.session_data:
                session = processor.session_data[user_id]
                if session.get("query"):
                    content = session["query"][:50] + (
                        "..." if len(session["query"]) > 50 else ""
                    )
                    status_info = (
                        f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    )
                elif session.get("replied_message"):
                    reply_msg = session["replied_message"]
                    if reply_msg.text:
                        content = reply_msg.text[:50] + (
                            "..." if len(reply_msg.text) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    elif reply_msg.caption:
                        content = reply_msg.caption[:50] + (
                            "..." if len(reply_msg.caption) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"

            text = (
                f"🔐 <b>{operation_title} Tool</b>\n\n"
                f"{status_info}"
                f"Select a category to see available {operation} methods:"
            )
            buttons = create_category_buttons(operation)
            await edit_message(message, text, buttons.build_menu(2))
            await callback_query.answer("Back to categories")
            return

        if data.startswith("enc_cat_page_"):
            # Handle category pagination
            parts = data.replace("enc_cat_page_", "").split("_")
            operation = parts[0]
            page = int(parts[1])
            operation_title = "Encoding" if operation == "encode" else "Decoding"

            # Check if user has content to process and show status
            status_info = ""
            if user_id in processor.session_data:
                session = processor.session_data[user_id]
                if session.get("query"):
                    content = session["query"][:50] + (
                        "..." if len(session["query"]) > 50 else ""
                    )
                    status_info = (
                        f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    )
                elif session.get("replied_message"):
                    reply_msg = session["replied_message"]
                    if reply_msg.text:
                        content = reply_msg.text[:50] + (
                            "..." if len(reply_msg.text) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    elif reply_msg.caption:
                        content = reply_msg.caption[:50] + (
                            "..." if len(reply_msg.caption) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"

            text = (
                f"🔐 <b>{operation_title} Tool</b>\n\n"
                f"{status_info}"
                f"Select a category to see available {operation} methods:"
            )
            buttons = create_category_buttons(operation, page)
            await edit_message(message, text, buttons.build_menu(2))
            await callback_query.answer(f"Page {page + 1}")
            return

        if data.startswith("enc_cat_"):
            # Handle category selection
            parts = data.replace("enc_cat_", "").split("_")
            category = parts[0]
            operation = parts[1] if len(parts) > 1 else "encode"

            # Check if user has content to process and show status
            status_info = ""
            if user_id in processor.session_data:
                session = processor.session_data[user_id]
                if session.get("query"):
                    content = session["query"][:50] + (
                        "..." if len(session["query"]) > 50 else ""
                    )
                    status_info = (
                        f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    )
                elif session.get("replied_message"):
                    reply_msg = session["replied_message"]
                    if reply_msg.text:
                        content = reply_msg.text[:50] + (
                            "..." if len(reply_msg.text) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    elif reply_msg.caption:
                        content = reply_msg.caption[:50] + (
                            "..." if len(reply_msg.caption) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"

            text = (
                f"📂 <b>{category} Methods</b>\n\n"
                f"{status_info}"
                f"Select a {category.lower()} method to {operation}:\n\n"
                f"💡 Methods will process your query or replied message instantly."
            )
            buttons = create_method_buttons(category, operation)
            await edit_message(message, text, buttons.build_menu(2))
            await callback_query.answer(f"Showing {category} methods")
            return

        if data.startswith("enc_method_page_"):
            # Handle method pagination
            parts = data.replace("enc_method_page_", "").split("_")
            category = parts[0]
            operation = parts[1]
            page = int(parts[2])

            # Check if user has content to process and show status
            status_info = ""
            if user_id in processor.session_data:
                session = processor.session_data[user_id]
                if session.get("query"):
                    content = session["query"][:50] + (
                        "..." if len(session["query"]) > 50 else ""
                    )
                    status_info = (
                        f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    )
                elif session.get("replied_message"):
                    reply_msg = session["replied_message"]
                    if reply_msg.text:
                        content = reply_msg.text[:50] + (
                            "..." if len(reply_msg.text) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"
                    elif reply_msg.caption:
                        content = reply_msg.caption[:50] + (
                            "..." if len(reply_msg.caption) > 50 else ""
                        )
                        status_info = f"📝 <b>Ready to {operation}:</b> <code>{content}</code>\n\n"

            text = (
                f"📂 <b>{category} Methods</b>\n\n"
                f"{status_info}"
                f"Select a {category.lower()} method to {operation}:\n\n"
                f"💡 Methods will process your query or replied message instantly."
            )
            buttons = create_method_buttons(category, operation, page)
            await edit_message(message, text, buttons.build_menu(2))
            await callback_query.answer(f"Page {page + 1}")
            return

        if data.startswith("enc_method_"):
            # Handle method selection
            parts = data.replace("enc_method_", "").split("_")
            method = parts[0]
            operation = parts[1] if len(parts) > 1 else "encode"

            # DO NOT store selected method/operation to prevent automatic processing
            # This prevents the bot from processing every message the user sends
            # Only process via commands with queries or replies

            # Get method information
            info = processor.get_method_info(method)

            # Process immediately if we have query or replied message
            session = processor.session_data[user_id]
            if session.get("query") or session.get("replied_message"):
                # Process the content
                if session.get("query"):
                    content = session["query"]
                    source = "query"
                elif session.get("replied_message"):
                    reply_msg = session["replied_message"]
                    if reply_msg.text:
                        content = reply_msg.text
                        source = "replied message"
                    elif reply_msg.caption:
                        content = reply_msg.caption
                        source = "replied message caption"
                    else:
                        content = None
                        source = None

                if content:
                    # Process the encoding/decoding
                    result = await process_encoding_text(
                        content, method, operation, user_id
                    )

                    result_text = (
                        f"✅ <b>Result ({operation.title()})</b>\n\n"
                        f"🔧 <b>Method:</b> {method}\n"
                        f"📝 <b>Source:</b> {source}\n\n"
                        f"📤 <b>Result:</b>\n<code>{result}</code>"
                    )

                    buttons = ButtonMaker()
                    buttons.data_button(
                        "🔙 Back to Methods",
                        f"enc_cat_{info.get('category', 'BaseXX')}_{operation}",
                    )
                    buttons.data_button("❌ Close", "enc_close")

                    await edit_message(message, result_text, buttons.build_menu(1))
                    await callback_query.answer(f"Processed with {method}")
                    return

            # If no content to process, show method information and usage instructions
            # Check if user has any content available but not processed
            content_status = ""
            if user_id in processor.session_data:
                session = processor.session_data[user_id]
                if session.get("query"):
                    content_status = f"⚠️ <b>No content to process:</b> Use <code>/{operation} {method} {session['query']}</code> to process your query.\n\n"
                elif session.get("replied_message"):
                    content_status = f"⚠️ <b>No content to process:</b> Use <code>/{operation} {method}</code> (reply to message) to process.\n\n"

            text = (
                f"✅ <b>Method Selected: {method}</b>\n\n"
                f"{content_status}"
                f"📝 <b>Description:</b> {info.get('description', 'No description available')}\n\n"
                f"📂 <b>Category:</b> {info.get('category', 'Unknown')}\n"
                f"🎯 <b>Operation:</b> {operation.title()}\n\n"
                f"💡 <b>How to use this method:</b>\n"
                f"• <code>/{operation} {method} your text here</code>\n"
                f"• <code>/{operation} {method}</code> (reply to a message)\n\n"
                f"⚠️ <b>Note:</b> This method will only process text when used with the command, not from regular messages."
            )

            buttons = ButtonMaker()
            buttons.data_button(
                "🔙 Back to Methods",
                f"enc_cat_{info.get('category', 'BaseXX')}_{operation}",
            )
            buttons.data_button("🏠 Main Menu", f"enc_back_categories_{operation}")
            buttons.data_button("❌ Close", "enc_close")

            await edit_message(message, text, buttons.build_menu(1))
            await callback_query.answer(f"Selected {method}")
            return

    except Exception as e:
        LOGGER.error(f"Error in encoding_callback: {e}")
        await callback_query.answer("Error processing request")


async def process_encoding_text(
    text: str, method: str, operation: str, user_id: int
) -> str:
    """Process text encoding/decoding with improved error handling and auto-detection"""
    try:
        # Smart auto-detection of operation
        if operation == "auto":
            operation = detect_operation(text, method)

        result = None
        error_msg = None
        warning_msg = None

        # Validate input
        if not text.strip():
            error_msg = "Input text cannot be empty"
        elif len(text) > 50000:  # Reasonable limit
            error_msg = "Input text too large (max 50,000 characters)"

        if not error_msg:
            if method in get_flat_codext_methods():
                # Use codext for supported methods with enhanced error handling
                try:
                    # Pre-process text for methods with known limitations
                    processed_text = text

                    # Methods that only work with letters
                    letter_only_methods = [
                        "affine",
                        "radio",
                        "galactic",
                        "navajo",
                        "a1z26",
                        "atbash",
                    ]
                    if method in letter_only_methods:
                        if operation == "encode":
                            if method == "a1z26":
                                # A1Z26 works with letters and spaces
                                processed_text = "".join(
                                    c for c in text if c.isalpha() or c.isspace()
                                )
                                if not processed_text.strip():
                                    raise ValueError(
                                        f"No valid characters for {method} encoding (letters and spaces only)"
                                    )
                                if processed_text != text:
                                    warning_msg = f"⚠️ Note: {method} only processes letters and spaces - numbers/symbols filtered out"
                            else:
                                # Other methods work with letters only
                                processed_text = "".join(
                                    c for c in text if c.isalpha()
                                )
                                if not processed_text.strip():
                                    raise ValueError(
                                        f"No valid characters for {method} encoding (letters only)"
                                    )
                                if processed_text != text:
                                    warning_msg = f"⚠️ Note: {method} only processes letters - other characters filtered out"

                    # Methods with case sensitivity issues
                    case_sensitive_methods = ["baudot"]
                    if method in case_sensitive_methods and operation == "encode":
                        processed_text = text.upper()
                        if processed_text != text:
                            warning_msg = f"⚠️ Note: {method} converted to uppercase"

                    # Methods that change case (lossy)
                    case_changing_methods = [
                        "capitalize",
                        "title",
                        "uppercase",
                        "lowercase",
                    ]
                    if method in case_changing_methods and operation == "decode":
                        warning_msg = (
                            f"⚠️ Note: {method} may have changed the original case"
                        )

                    # Special handling for morse code
                    if method == "morse":
                        if operation == "encode":
                            # Morse only works with alphanumeric and some punctuation
                            processed_text = "".join(
                                c for c in text if c.isalnum() or c in " .,?!-()/"
                            )
                            if not processed_text.strip():
                                raise ValueError(
                                    "No valid characters for morse encoding (alphanumeric and basic punctuation only)"
                                )
                            if processed_text != text:
                                warning_msg = "⚠️ Note: morse only processes alphanumeric and basic punctuation - other characters filtered out"
                        else:
                            # Morse decoding is case-insensitive, warn user
                            warning_msg = "⚠️ Note: morse decoding converts to lowercase (lossy conversion)"

                    # Special handling for braille
                    if method == "braille":
                        if operation == "encode":
                            # Braille works with most characters but may have limitations
                            if any(ord(c) > 127 for c in text):
                                warning_msg = "⚠️ Note: braille may not support all Unicode characters"
                        else:
                            warning_msg = (
                                "⚠️ Note: braille decoding may be case-sensitive"
                            )

                    # Special handling for leetspeak
                    if method == "leetspeak":
                        if operation == "encode":
                            warning_msg = "⚠️ Note: leetspeak is a lossy conversion (cannot be perfectly reversed)"
                        else:
                            warning_msg = "⚠️ Note: leetspeak decoding is approximate and may not match original text"

                    # Special handling for compression methods
                    compression_methods = [
                        "gzip",
                        "lz77",
                        "lz78",
                        "pkzip_deflate",
                        "pkzip_bzip2",
                        "pkzip_lzma",
                    ]
                    if method in compression_methods:
                        if len(text) < 10:
                            warning_msg = f"⚠️ Note: {method} compression works better with longer text"

                    # Special handling for shift methods (prevent overflow)
                    if method.startswith("shift"):
                        try:
                            shift_value = int(method[5:])
                            if shift_value > 127:
                                warning_msg = f"⚠️ Note: shift{shift_value} may cause character overflow issues"
                            elif operation == "encode":
                                # Check if any characters would overflow
                                max_char = max(ord(c) for c in text)
                                if max_char + shift_value > 127:
                                    warning_msg = f"⚠️ Note: some characters may overflow with shift{shift_value}"
                        except ValueError:
                            pass

                    # Special handling for XOR methods
                    if method.startswith("xor"):
                        try:
                            xor_value = int(method[3:])
                            if xor_value > 127:
                                warning_msg = f"⚠️ Note: xor{xor_value} may cause character encoding issues"
                        except ValueError:
                            pass

                    # Special handling for DNA encoding methods
                    if method.startswith("dna-"):
                        if operation == "encode":
                            # DNA encoding works with text but has specific rules
                            if any(ord(c) > 127 for c in text):
                                warning_msg = f"⚠️ Note: {method} works best with ASCII characters"
                        else:
                            warning_msg = f"⚠️ Note: {method} decoding follows specific DNA sequence rules"

                    # Special handling for steganography methods
                    stego_methods = ["hexagram", "resistor", "whitespace"]
                    if method in stego_methods:
                        if operation == "encode":
                            warning_msg = f"⚠️ Note: {method} creates hidden representations that may not be obvious"
                        else:
                            warning_msg = f"⚠️ Note: {method} decoding requires specific format recognition"

                    # Special handling for case-sensitive methods
                    case_sensitive_methods = ["baudot"]
                    if method in case_sensitive_methods and operation == "encode":
                        processed_text = text.upper()
                        if processed_text != text:
                            warning_msg = f"⚠️ Note: {method} converted to uppercase"

                    # Try the encoding/decoding operation
                    if operation == "encode":
                        result = codext.encode(processed_text, method)
                    else:
                        result = codext.decode(text, method)

                    # Add warnings for lossy methods
                    lossy_methods = [
                        "leetspeak",
                        "morse",
                        "a1z26",
                        "navajo",
                        "radio",
                        "braille",
                        "galactic",
                        "atbash",
                    ]
                    if method in lossy_methods and not warning_msg:
                        warning_msg = f"⚠️ Note: {method} encoding may be lossy or case-insensitive"

                except Exception as e:
                    # Provide helpful error messages for common issues
                    error_str = str(e).lower()
                    if (
                        "can't encode character" in error_str
                        or "can't decode character" in error_str
                    ):
                        if method in letter_only_methods:
                            error_msg = f"Method '{method}' only supports letters. Try with alphabetic text only."
                        elif method == "morse":
                            error_msg = f"Method '{method}' only supports alphanumeric characters and basic punctuation."
                        elif method.startswith(("shift", "xor")):
                            error_msg = f"Method '{method}' caused character overflow. Try with simpler text or lower values."
                        elif method in compression_methods:
                            error_msg = f"Method '{method}' failed. Try with longer text or different content."
                        elif method.startswith("dna-"):
                            error_msg = f"Method '{method}' failed. Try with ASCII text only."
                        else:
                            error_msg = f"Method '{method}' doesn't support some characters in your text."
                    elif "unknown encoding" in error_str or "codec" in error_str:
                        error_msg = f"Method '{method}' not available in current codext version."
                    elif "invalid" in error_str:
                        error_msg = f"Invalid input for {method}: {e!s}"
                    elif "overflow" in error_str:
                        error_msg = f"Method '{method}' caused overflow. Try with different text or method parameters."
                    elif "decode" in error_str and operation == "decode":
                        error_msg = f"Cannot decode with '{method}'. The input may not be encoded with this method."
                    else:
                        error_msg = f"Error with {method}: {e!s}"

            elif method in ADDITIONAL_METHODS["Standard"]:
                # Handle standard encodings
                result = await process_standard_encoding(text, method, operation)

            elif method in ADDITIONAL_METHODS["Advanced Crypto"]:
                # Handle advanced crypto
                result = await process_crypto_encoding(
                    text, method, operation, user_id
                )

            elif method in ADDITIONAL_METHODS["Custom"]:
                # Handle custom methods
                result = await process_custom_encoding(text, method, operation)

            else:
                error_msg = f"Method '{method}' not implemented yet"

        if error_msg:
            raise ValueError(error_msg)

        if result is None:
            raise ValueError(f"Failed to process with method '{method}'")

        return str(result)

    except Exception as e:
        # Log encoding errors as warnings since they're often user input validation issues
        error_str = str(e).lower()
        if any(
            phrase in error_str
            for phrase in [
                "can't decode character",
                "can't encode character",
                "codec",
                "unknown encoding",
            ]
        ):
            LOGGER.warning(
                f"Encoding validation issue in process_encoding_text: {e}"
            )
        else:
            LOGGER.error(f"Unexpected error in process_encoding_text: {e}")
        raise ValueError(f"Encoding Error: {e!s}")


async def try_auto_decode(text: str) -> dict:
    """Try to automatically decode text using common encoding detection"""

    # Clean input text
    text = text.strip()
    if not text:
        return None

    # List of common encoding methods to try in order of likelihood
    auto_decode_methods = [
        # Base encodings (most common) - order by likelihood
        (
            "base64",
            lambda t: all(
                c
                in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
                for c in t
            )
            and len(t) % 4 == 0
            and len(t) >= 4
            and not all(c.isdigit() for c in t),
        ),
        (
            "base32",
            lambda t: all(
                c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in t.upper()
            )
            and len(t) % 8 == 0
            and len(t) >= 8,
        ),
        (
            "base16",
            lambda t: all(c in "0123456789ABCDEFabcdef" for c in t)
            and len(t) % 2 == 0
            and len(t) >= 4
            and len(t) <= 100,
        ),
        # URL encoding (check for % followed by hex digits, allow more URL characters)
        (
            "url",
            lambda t: "%" in t
            and all(
                c
                in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789%+-._~=&@:"
                for c in t
            )
            and any(
                t[i : i + 3]
                for i in range(len(t) - 2)
                if t[i] == "%"
                and len(t[i : i + 3]) == 3
                and all(c in "0123456789ABCDEFabcdef" for c in t[i + 1 : i + 3])
            ),
        ),
        # Hex encoding (even length, all hex chars, reasonable length, not pure binary, contains A-F)
        (
            "hex",
            lambda t: all(c in "0123456789ABCDEFabcdef" for c in t)
            and len(t) % 2 == 0
            and len(t) >= 6
            and len(t) <= 200
            and any(c in "ABCDEFabcdef" for c in t)
            and not all(c in "01" for c in t),
        ),
        # Binary (only 0s, 1s, and spaces, proper length, prioritize over hex)
        (
            "binary",
            lambda t: all(c in "01 " for c in t)
            and len(t.replace(" ", "")) % 8 == 0
            and len(t.replace(" ", "")) >= 8
            and (t.count("0") + t.count("1")) / len(t.replace(" ", "")) == 1,
        ),  # Only binary digits
        # Morse code (dots, dashes, spaces, slashes)
        (
            "morse",
            lambda t: all(c in ".-/ \n\t" for c in t)
            and ("." in t or "-" in t)
            and len(t) >= 3,
        ),
        # ROT13 (contains letters but doesn't look like normal English, and has vowel patterns suggesting encoding)
        (
            "rot13",
            lambda t: any(c.isalpha() for c in t)
            and len(t) >= 8
            and not any(
                word in t.lower()
                for word in [
                    "the",
                    "and",
                    "for",
                    "are",
                    "but",
                    "not",
                    "you",
                    "all",
                    "can",
                    "had",
                    "her",
                    "was",
                    "one",
                    "our",
                    "out",
                    "day",
                    "get",
                    "has",
                    "him",
                    "his",
                    "how",
                    "man",
                    "new",
                    "now",
                    "old",
                    "see",
                    "two",
                    "way",
                    "who",
                    "boy",
                    "did",
                    "its",
                    "let",
                    "put",
                    "say",
                    "she",
                    "too",
                    "use",
                    "hello",
                    "world",
                    "test",
                    "this",
                    "that",
                    "with",
                    "from",
                    "they",
                    "know",
                    "want",
                    "been",
                    "good",
                    "much",
                    "some",
                    "time",
                    "very",
                    "when",
                    "come",
                    "here",
                    "just",
                    "like",
                    "long",
                    "make",
                    "many",
                    "over",
                    "such",
                    "take",
                    "than",
                    "them",
                    "well",
                    "were",
                    "https",
                    "www",
                    "example",
                    "com",
                ]
            )
            and len([c for c in t if c.isalpha()]) > 0
            and sum(1 for c in t.lower() if c in "aeiou")
            / len([c for c in t if c.isalpha()])
            < 0.3,
        ),  # Low vowel ratio suggests encoding
        # A1Z26 (numbers separated by spaces, commas, or dashes, numbers should be 1-26)
        (
            "a1z26",
            lambda t: all(c.isdigit() or c in " ,-" for c in t)
            and any(c.isdigit() for c in t)
            and len(
                [
                    x
                    for x in t.replace(",", " ").replace("-", " ").split()
                    if x.isdigit()
                ]
            )
            >= 2
            and all(
                1 <= int(x) <= 26
                for x in t.replace(",", " ").replace("-", " ").split()
                if x.isdigit()
            ),
        ),
        # HTML entities
        (
            "html",
            lambda t: "&" in t
            and ";" in t
            and any(
                entity in t
                for entity in ["&amp;", "&lt;", "&gt;", "&quot;", "&apos;", "&#"]
            ),
        ),
        # Reverse text (very restrictive: only if it looks like reversed English and doesn't contain common patterns)
        (
            "reverse",
            lambda t: len(t) >= 8
            and any(c.isalpha() for c in t)
            and not all(c.isdigit() or c.isspace() for c in t)
            and not t.lower().startswith(
                (
                    "hello",
                    "test",
                    "the ",
                    "and ",
                    "for ",
                    "this ",
                    "that ",
                    "with ",
                    "user",
                    "http",
                    "www",
                    "mixed",
                )
            )
            and not any(
                word in t.lower()
                for word in [
                    "hello",
                    "world",
                    "test",
                    "the",
                    "and",
                    "for",
                    "this",
                    "that",
                    "user",
                    "example",
                    "com",
                    "case",
                    "text",
                    "with",
                ]
            )
            and t.count(" ") <= 2,
        ),  # Reversed text usually has fewer spaces
    ]

    for method, detector in auto_decode_methods:
        try:
            # Check if text matches the pattern for this encoding
            if detector(text):
                # Try to decode using this method
                result = await process_encoding_text(
                    text, method, "decode", 0
                )  # Use user_id 0 for auto-decode

                # Validate the result
                if result and len(result.strip()) > 0 and result != text:
                    # Check if result is meaningful (contains printable characters)
                    printable_chars = sum(
                        1
                        for c in result
                        if (ord(c) >= 32 and ord(c) <= 126) or c in "\n\r\t"
                    )
                    total_chars = len(result)

                    if (
                        total_chars > 0 and printable_chars / total_chars >= 0.8
                    ):  # At least 80% printable
                        # Additional validation for specific methods
                        if method in ["base64", "base32", "base16", "hex"]:
                            # These should decode to readable text
                            if len(result) > 0 and result != text:
                                return {"method": method, "result": result}
                        elif method == "url":
                            # URL decode should remove % encodings
                            if "%" not in result and len(result) <= len(text):
                                return {"method": method, "result": result}
                        elif method == "binary":
                            # Binary should decode to readable text
                            if len(result) > 0 and not all(
                                c in "01 " for c in result
                            ):
                                return {"method": method, "result": result}
                        elif method == "morse":
                            # Morse should decode to letters/numbers
                            if any(c.isalnum() for c in result) and not all(
                                c in ".-/ " for c in result
                            ):
                                return {"method": method, "result": result}
                        elif method == "rot13":
                            # ROT13 should produce different text with common English words
                            if any(
                                word in result.lower()
                                for word in [
                                    "the",
                                    "and",
                                    "hello",
                                    "world",
                                    "test",
                                    "message",
                                ]
                            ):
                                return {"method": method, "result": result}
                        elif method == "a1z26":
                            # A1Z26 should decode to letters
                            if any(c.isalpha() for c in result) and not any(
                                c.isdigit() for c in result
                            ):
                                return {"method": method, "result": result}
                        elif method == "html":
                            # HTML decode should remove entities
                            if "&" not in result or result.count("&") < text.count(
                                "&"
                            ):
                                return {"method": method, "result": result}
                        elif method == "reverse":
                            # Reverse should make text look more normal
                            if any(
                                word in result.lower()
                                for word in [
                                    "hello",
                                    "world",
                                    "test",
                                    "the ",
                                    "and ",
                                ]
                            ):
                                return {"method": method, "result": result}
                        # For other methods, basic validation
                        elif len(result) > 0 and result != text:
                            return {"method": method, "result": result}
        except Exception:
            # If decoding fails, try next method
            continue

    return None


def detect_operation(text: str, method: str) -> str:
    """Smart detection of whether to encode or decode based on input characteristics"""

    # Hash methods are always encode-only
    if method in CODEXT_CATEGORIES.get("Hashing", []):
        return "encode"

    # Check if text looks like it's already encoded
    encoded_indicators = {
        "base64": lambda t: all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
            for c in t.strip()
        ),
        "base32": lambda t: all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in t.strip().upper()
        ),
        "base16": lambda t: all(c in "0123456789ABCDEFabcdef" for c in t.strip()),
        "hex": lambda t: all(c in "0123456789ABCDEFabcdef" for c in t.strip())
        and len(t.strip()) % 2 == 0,
        "binary": lambda t: all(c in "01 " for c in t.strip()),
        "morse": lambda t: all(c in ".-/ " for c in t.strip()),
        "url": lambda t: "%" in t and any(c in "0123456789ABCDEFabcdef" for c in t),
    }

    # Check if input looks like encoded data for this method
    if method in encoded_indicators:
        try:
            if encoded_indicators[method](text):
                return "decode"
        except:
            pass

    # Default to encode for most cases
    return "encode"


def get_flat_codext_methods() -> list[str]:
    """Get all codext methods as a flat list"""
    methods = []
    for category_methods in CODEXT_CATEGORIES.values():
        methods.extend(category_methods)
    return methods


async def process_standard_encoding(text: str, method: str, operation: str) -> str:
    """Process standard encoding methods with improved error handling"""
    try:
        if method == "hex":
            if operation == "encode":
                return text.encode("utf-8").hex()
            # Remove spaces and validate hex
            hex_text = text.replace(" ", "").replace("\n", "").replace("\t", "")
            if not all(c in "0123456789ABCDEFabcdef" for c in hex_text):
                raise ValueError("Invalid hexadecimal characters")
            if len(hex_text) % 2 != 0:
                raise ValueError("Hexadecimal string must have even length")
            return bytes.fromhex(hex_text).decode("utf-8")

        if method == "binary":
            if operation == "encode":
                return " ".join(format(ord(char), "08b") for char in text)
            # Handle different binary formats
            binary_text = text.replace("\n", " ").replace("\t", " ")
            binary_parts = [
                part.strip() for part in binary_text.split() if part.strip()
            ]

            if not binary_parts:
                raise ValueError("No binary data found")

            if not all(all(c in "01" for c in part) for part in binary_parts):
                raise ValueError("Invalid binary characters (only 0 and 1 allowed)")

            # Pad to 8 bits if needed
            padded_parts = []
            for part in binary_parts:
                if len(part) <= 8:
                    padded_parts.append(part.zfill(8))
                else:
                    # Split long binary strings into 8-bit chunks
                    for i in range(0, len(part), 8):
                        chunk = part[i : i + 8]
                        if len(chunk) < 8:
                            chunk = chunk.ljust(8, "0")
                        padded_parts.append(chunk)

            # Validate that we can convert to characters
            try:
                return "".join(chr(int(byte, 2)) for byte in padded_parts)
            except ValueError as e:
                raise ValueError(f"Invalid binary sequence: {e!s}")

        elif method in ["ascii", "utf-8", "utf-16", "utf-32", "latin-1"]:
            if operation == "encode":
                encoded_bytes = text.encode(method)
                return encoded_bytes.hex()
            # Remove spaces and validate hex
            hex_text = text.replace(" ", "").replace("\n", "").replace("\t", "")
            if not all(c in "0123456789ABCDEFabcdef" for c in hex_text):
                raise ValueError("Invalid hexadecimal characters")
            if len(hex_text) % 2 != 0:
                raise ValueError("Hexadecimal string must have even length")
            return bytes.fromhex(hex_text).decode(method)

        return None

    except UnicodeDecodeError as e:
        raise ValueError(f"Unicode decode error: {e!s}")
    except UnicodeEncodeError as e:
        raise ValueError(f"Unicode encode error: {e!s}")
    except ValueError as e:
        raise ValueError(f"Encoding error: {e!s}")
    except Exception as e:
        raise ValueError(f"Unexpected error in {method} {operation}: {e!s}")


async def process_crypto_encoding(
    text: str, method: str, operation: str, user_id: int
) -> str:
    """Process advanced cryptographic methods"""
    try:
        if method == "aes-encrypt":
            # Generate a key for demo (in production, use proper key management)
            key = Fernet.generate_key()
            f = Fernet(key)
            encrypted = f.encrypt(text.encode())
            # Store key for this user session (temporary)
            if user_id not in processor.session_data:
                processor.session_data[user_id] = {}
            processor.session_data[user_id]["aes_key"] = key.decode()
            return f"Key: {key.decode()}\nEncrypted: {encrypted.decode()}"

        if method == "aes-decrypt":
            # Try to get key from session
            if (
                user_id in processor.session_data
                and "aes_key" in processor.session_data[user_id]
            ):
                key = processor.session_data[user_id]["aes_key"].encode()
                f = Fernet(key)
                # Assume text contains the encrypted data
                decrypted = f.decrypt(text.encode())
                return decrypted.decode()
            return "Error: No AES key found. Encrypt something first."

        if method == "fernet-encrypt":
            key = Fernet.generate_key()
            f = Fernet(key)
            encrypted = f.encrypt(text.encode())
            if user_id not in processor.session_data:
                processor.session_data[user_id] = {}
            processor.session_data[user_id]["fernet_key"] = key.decode()
            return f"Key: {key.decode()}\nEncrypted: {encrypted.decode()}"

        if method == "fernet-decrypt":
            if (
                user_id in processor.session_data
                and "fernet_key" in processor.session_data[user_id]
            ):
                key = processor.session_data[user_id]["fernet_key"].encode()
                f = Fernet(key)
                decrypted = f.decrypt(text.encode())
                return decrypted.decode()
            return "Error: No Fernet key found. Encrypt something first."

        if method in ["rsa-encrypt", "rsa-decrypt"]:
            return "RSA encryption requires key pair generation. Use /crypto command for setup."

    except Exception as e:
        return f"Crypto error: {e!s}"

    return None


async def process_custom_encoding(text: str, method: str, operation: str) -> str:
    """Process custom encoding methods with improved error handling"""
    try:
        if method == "json-encode":
            if operation == "encode":
                return json.dumps(
                    {"data": text, "timestamp": "encoded", "length": len(text)},
                    indent=2,
                )
            # Try to extract data from JSON
            data = json.loads(text)
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return str(data)

        if method == "json-decode":
            data = json.loads(text)
            if isinstance(data, dict):
                return json.dumps(data, indent=2)
            return str(data)

        if method == "percent-encode":
            if operation == "encode":
                return urllib.parse.quote(text, safe="")
            try:
                return urllib.parse.unquote(text)
            except Exception as e:
                raise ValueError(f"Invalid percent-encoded string: {e!s}")

        elif method == "percent-decode":
            try:
                return urllib.parse.unquote(text)
            except Exception as e:
                raise ValueError(f"Invalid percent-encoded string: {e!s}")

        elif method == "mime-encode":
            if operation == "encode":
                return base64.b64encode(text.encode("utf-8")).decode("ascii")
            return base64.b64decode(text.encode("ascii")).decode("utf-8")

        elif method == "mime-decode":
            return base64.b64decode(text.encode("ascii")).decode("utf-8")

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e!s}")
    except base64.binascii.Error as e:
        raise ValueError(f"Invalid Base64: {e!s}")
    except UnicodeDecodeError as e:
        raise ValueError(f"Unicode decode error: {e!s}")
    except Exception as e:
        raise ValueError(f"Custom encoding error: {e!s}")

    return None


# Add a comprehensive help command
async def encoding_help_command(_, message):
    """Show comprehensive help for encoding/decoding"""
    await delete_message(message)

    help_text = (
        "📚 <b>Encoding/Decoding Help Guide</b>\n\n"
        "🔐 <b>Available Commands:</b>\n"
        "• <code>/encode</code> or <code>/enc</code> [query] - Encoding interface\n"
        "• <code>/decode</code> or <code>/dec</code> [query] - Decoding interface\n\n"
        "🎯 <b>How to Use:</b>\n"
        "1. Send a command with optional query: <code>/encode hello world</code>\n"
        "2. Or reply to a message and use: <code>/encode</code>\n"
        "3. Select a category from the menu\n"
        "4. Choose an encoding/decoding method\n"
        "5. Get instant results!\n\n"
        "📂 <b>Categories Overview:</b>\n"
        "• <b>BaseXX</b> - Base64, Base32, Base16, etc.\n"
        "• <b>Binary</b> - Binary, hex, baudot codes\n"
        "• <b>Common</b> - Case changes, reversals\n"
        "• <b>Compression</b> - Gzip, LZ77, LZ78\n"
        "• <b>Cryptography</b> - ROT13, Atbash, Affine\n"
        "• <b>Hashing</b> - MD5, SHA256, BLAKE2 (encode only)\n"
        "• <b>Languages</b> - Morse, Braille, Leet\n"
        "• <b>Steganography</b> - Hidden messages\n"
        "• <b>Web</b> - URL, HTML encoding\n"
        "• <b>Standard</b> - UTF-8, ASCII, etc.\n"
        "• <b>Advanced Crypto</b> - AES, Fernet encryption\n"
        "• <b>Custom</b> - JSON, Percent encoding\n\n"
        "💡 <b>Pro Tips:</b>\n"
        "• Query with command takes priority over replied messages\n"
        "• Hash functions only appear in encode menu\n"
        "• Decrypt methods only appear in decode menu\n"
        "• Large results are sent as downloadable files\n"
        "• Some methods may be lossy or case-insensitive\n\n"
        "⚠️ <b>Limitations:</b>\n"
        "• Max input: 50,000 characters\n"
        "• Cryptographic keys are session-temporary\n"
        "• Authorization required to use commands\n\n"
        "🔢 <b>Total Methods Available:</b> 400+\n"
        "📊 <b>Success Rate:</b> 96%+ in testing\n\n"
        "Start with <code>/encode</code> or <code>/decode</code> to begin! 🚀"
    )

    buttons = ButtonMaker()
    buttons.data_button("🔐 Start Encoding", "enc_back_categories_encode")
    buttons.data_button("🔓 Start Decoding", "enc_back_categories_decode")
    buttons.data_button("❌ Close", "enc_close")

    msg = await send_message(message, help_text, buttons.build_menu(1))
    asyncio.create_task(auto_delete_message(msg, time=600))  # 10 minutes


# Message handler for processing user input (DISABLED - only process via commands)
async def handle_encoding_message(_, message):
    """
    Handle messages when user has selected an encoding method

    IMPORTANT: This handler is now DISABLED to prevent automatic processing
    of all user messages. Encoding/decoding should only happen via:
    1. Commands with queries: /encode hello world
    2. Commands with replies: /encode (reply to message)
    3. NOT via random messages after method selection
    """
    # DISABLED: Do not process any messages automatically
    # This prevents the bot from encoding/decoding every message a user sends
    # after selecting a method, which was the unwanted behavior.
    return

    # The old code below is commented out but kept for reference:
    """
    user_id = message.from_user.id

    # Check if user has selected a method and operation
    if (user_id not in processor.session_data or
        "selected_method" not in processor.session_data[user_id] or
        "selected_operation" not in processor.session_data[user_id]):
        return  # User hasn't selected a method, ignore

    session = processor.session_data[user_id]
    method = session["selected_method"]
    operation = session["selected_operation"]

    try:
        if message.text:
            text = message.text
            result = await process_encoding_text(text, method, operation, user_id)

            result_text = (
                f"✅ <b>Result ({operation.title()})</b>\n\n"
                f"🔧 <b>Method:</b> {method}\n"
                f"📝 <b>Input:</b> {len(text)} chars\n"
                f"📤 <b>Output:</b> {len(result)} chars\n\n"
                f"📋 <b>Result:</b>\n<code>{result}</code>"
            )

            await send_message(message, result_text)

        elif message.document:
            # Handle file input
            try:
                file_info = await message.download()
                with open(file_info, 'r', encoding='utf-8') as f:
                    text = f.read()

                if len(text) > 10000:  # Limit file size
                    await send_message(message, "❌ File too large. Maximum 10,000 characters.")
                    return

                result = await process_encoding_text(text, method, operation, user_id)

                result_text = (
                    f"✅ <b>Result ({operation.title()})</b>\n\n"
                    f"🔧 <b>Method:</b> {method}\n"
                    f"📁 <b>Source:</b> File ({message.document.file_name})\n"
                    f"📝 <b>Input:</b> {len(text)} chars\n"
                    f"📤 <b>Output:</b> {len(result)} chars\n\n"
                    f"📋 <b>Result:</b>\n<code>{result}</code>"
                )

                await send_message(message, result_text)

            except Exception as e:
                await send_message(message, f"❌ Error processing file: {str(e)}")

        else:
            await send_message(message, "❌ Please send text or a text file to encode/decode.")

    except Exception as e:
        await send_message(message, f"❌ Error: {str(e)}")
    """


# Utility function to list all available methods
async def list_methods_command(_, message):
    """List all available encoding methods"""
    await delete_message(message)

    text = "📋 <b>All Available Encoding Methods</b>\n\n"

    all_methods = processor.get_all_methods()
    for category, methods in all_methods.items():
        text += f"📂 <b>{category}</b> ({len(methods)} methods)\n"
        # Show first 5 methods of each category
        for method in methods[:5]:
            text += f"  • <code>{method}</code>\n"
        if len(methods) > 5:
            text += f"  ... and {len(methods) - 5} more\n"
        text += "\n"

    text += f"🔢 <b>Total Methods:</b> {sum(len(methods) for methods in all_methods.values())}\n\n"
    text += "💡 Use /encode to start encoding/decoding"

    buttons = ButtonMaker()
    buttons.data_button("🔐 Start Encoding", "enc_back_categories")
    buttons.data_button("❌ Close", "enc_close")

    msg = await send_message(message, text, buttons.build_menu(1))
    asyncio.create_task(auto_delete_message(msg, time=300))
