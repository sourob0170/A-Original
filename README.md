# Streamrip Download Bot

A streamlined Telegram bot focused on downloading music from various streaming platforms using Streamrip.

## Description

This bot allows users to download music directly through Telegram. It utilizes the power of [Streamrip](https://github.com/nathom/streamrip) to fetch audio from services like Qobuz, Tidal, Deezer, and SoundCloud. Most other functionalities of the original bot have been removed to provide a lightweight and focused experience.

## Primary Command

The main command to interact with the bot is:

*   `/download <URL_or_ID_or_search_term> [options]`
*   Alias: `/dl <URL_or_ID_or_search_term> [options]`

**Basic Usage:**

*   To download a track or album:
    `/download https://tidal.com/browse/track/123456789`
*   You can also reply to a message containing a URL with `/download`.
*   Use options to specify quality, codec, etc. For example:
    `/download <URL> -q 1 -c flac` (Downloads at 320kbps FLAC)

Refer to the bot's `/help` command (specifically the Streamrip sections) for more details on supported URLs, ID formats, and available command options.

## Configuration

1.  **Bot Configuration**:
    *   Copy `config_sample.py` to `config.env` or set environment variables.
    *   Fill in your `BOT_TOKEN`, `OWNER_ID`, and other essential settings.
    *   Ensure `STREAMRIP_ENABLED` is set to `True`.

2.  **Streamrip Configuration**:
    *   Edit `streamrip_config.toml` to configure your accounts for streaming services (Qobuz, Tidal, etc.) to access higher quality downloads.

## Disclaimer

This bot is for personal use. Please respect copyright laws and the terms of service for any streaming platforms you use with this bot.
