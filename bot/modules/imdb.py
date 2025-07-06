from asyncio import create_task
from re import IGNORECASE, findall, search

from imdb import Cinemagoer
from pycountry import countries as conn
from pyrogram.errors import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from pyrogram.types import Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

imdb = Cinemagoer()

IMDB_GENRE_EMOJI = {
    "Action": "🚀",
    "Adult": "🔞",
    "Adventure": "🌋",
    "Animation": "🎠",
    "Biography": "📜",
    "Comedy": "🪗",
    "Crime": "🔪",
    "Documentary": "🎞",
    "Drama": "🎭",
    "Family": "👨‍👩‍👧‍👦",
    "Fantasy": "🫧",
    "Film Noir": "🎯",
    "Game Show": "🎮",
    "History": "🏛",
    "Horror": "🧟",
    "Musical": "🎻",
    "Music": "🎸",
    "Mystery": "🧳",
    "News": "📰",
    "Reality-TV": "🖥",
    "Romance": "🥰",
    "Sci-Fi": "🌠",
    "Short": "📝",
    "Sport": "⛳",
    "Talk-Show": "👨‍🍳",
    "Thriller": "🗡",
    "War": "⚔",
    "Western": "🪩",
}
LIST_ITEMS = 4


def list_to_str(k):
    """Convert list to string with proper formatting"""
    if not k:
        return "N/A"
    if len(k) == 1:
        return str(k[0])
    # Limit items if needed
    if LIST_ITEMS:
        k = k[:LIST_ITEMS]
    return ", ".join(f"{elem}" for elem in k)


def list_to_hash(k, country=False, emoji=False):
    """Convert list to hashtag string with proper formatting"""
    if not k:
        return "N/A"

    # Handle single item case
    if len(k) == 1:
        if emoji and k[0] in IMDB_GENRE_EMOJI:
            return f"{IMDB_GENRE_EMOJI[k[0]]} #{k[0].replace(' ', '_')}"
        if country:
            try:
                return f"#{conn.get(name=k[0]).alpha_2}"
            except (AttributeError, KeyError):
                return f"#{k[0].replace(' ', '_')}"
        return f"#{k[0].replace(' ', '_')}"

    # Limit items if needed
    if LIST_ITEMS:
        k = k[:LIST_ITEMS]

    # Format multiple items
    if emoji:
        return " ".join(
            f"{IMDB_GENRE_EMOJI.get(elem, '')} #{elem.replace(' ', '_')}"
            for elem in k
        )
    if country:
        return " ".join(
            f"#{conn.get(name=elem).alpha_2}"
            if elem in [c.name for c in conn]
            else f"#{elem.replace(' ', '_')}"
            for elem in k
        )
    return " ".join(f"#{elem.replace(' ', '_')}" for elem in k)


async def imdb_search(_, message: Message):
    """Handle IMDB search command"""
    # Check if IMDB module is enabled
    if not Config.IMDB_ENABLED:
        error_msg = await send_message(
            message,
            "❌ <b>IMDB module is currently disabled.</b>\n\nPlease contact the bot owner to enable it.",
        )
        # Schedule for auto-deletion after 5 minutes
        create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
        return

    # Default template with Telegram quote format
    default_template = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
<b>⭐ Rating:</b> <i>{rating}</i>
<b>🎭 Genre:</b> {genres}
<b>📅 Released:</b> <a href=\"{url_releaseinfo}\">{release_date}</a>
<b>🎙️ Languages:</b> {languages}
<b>🌍 Country:</b> {countries}
<b>🎬 Type:</b> {kind}

<b>📖 Story Line:</b>
<blockquote>{plot}</blockquote>

<b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>
<b>👥 Cast:</b> <a href=\"{url_cast}\">{cast}</a>

<b>👨‍💼 Director:</b> {director}
<b>✍️ Writer:</b> {writer}
<b>🎵 Music:</b> {composer}
<b>🎥 Cinematography:</b> {cinematographer}

<b>⏱️ Runtime:</b> {runtime} minutes
<b>🏆 Awards:</b> {certificates}

<i>Powered by IMDb</i>"""

    user_id = message.from_user.id
    buttons = ButtonMaker()
    title = ""
    is_reply = False

    # Check if replying to a message
    if message.reply_to_message and message.reply_to_message.text:
        # Extract text from replied message
        title = message.reply_to_message.text.strip()
        k = await send_message(
            message,
            "<i>Searching IMDB for replied content...</i>",
        )
        is_reply = True
    elif " " in message.text:
        # User provided a search term in command
        title = message.text.split(" ", 1)[1]
        k = await send_message(message, "<i>Searching IMDB ...</i>")
    else:
        # No search term provided - schedule for auto-deletion after 5 minutes
        error_msg = await send_message(
            message,
            "<i>Send Movie / TV Series Name along with /imdb Command or reply to a message containing IMDB URL or movie/series name</i>",
        )
        # Schedule for auto-deletion after 5 minutes
        # pylint: disable=unused-variable
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )
        return

    # Check if it's an IMDB URL
    if result := search(r"imdb\.com/title/tt(\d+)", title, IGNORECASE):
        movieid = result.group(1)
        if movie := imdb.get_movie(movieid):
            # Process direct IMDB link
            # Delete messages and show result directly
            if is_reply:
                # If replying to a message with valid IMDB link
                await delete_message(message)
                await delete_message(message.reply_to_message)
                await delete_message(k)
                chat_id = message.chat.id
            else:
                # If command message has a valid IMDB link/key
                await delete_message(message)
                await delete_message(k)
                chat_id = message.chat.id

            # Process and show the movie directly
            imdb_data = get_poster(query=movieid, id=True)
            buttons = ButtonMaker()

            # Add trailer button if available
            if imdb_data["trailer"]:
                if isinstance(imdb_data["trailer"], list):
                    buttons.url_button(
                        "▶️ IMDb Trailer ",
                        imdb_data["trailer"][-1],
                    )
                    imdb_data["trailer"] = list_to_str(imdb_data["trailer"])
                else:
                    buttons.url_button("▶️ IMDb Trailer ", imdb_data["trailer"])

            buttons.data_button("🚫 Close 🚫", f"imdb {user_id} close")
            buttons = buttons.build_menu(1)

            # Get template from config or use default
            template = (
                Config.IMDB_TEMPLATE
                if hasattr(Config, "IMDB_TEMPLATE") and Config.IMDB_TEMPLATE
                else default_template
            )

            # Format caption with template
            if imdb_data and template:
                try:
                    cap = template.format(**imdb_data)
                except Exception as e:
                    LOGGER.error(f"Error formatting IMDB template: {e}")
                    cap = default_template.format(**imdb_data)
            else:
                cap = "No Results"

            # Send result with poster
            if imdb_data.get("poster"):
                try:
                    await TgClient.bot.send_photo(
                        chat_id=chat_id,
                        caption=cap,
                        photo=imdb_data["poster"],
                        reply_markup=buttons,
                    )
                except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                    # Try with alternative poster URL
                    poster = imdb_data.get("poster").replace(
                        ".jpg",
                        "._V1_UX360.jpg",
                    )
                    await send_message(
                        message,
                        cap,
                        buttons,
                        photo=poster,
                    )
            else:
                # Send without poster
                await send_message(
                    message,
                    cap,
                    buttons,
                    "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
                )
            return

        # No results found - schedule for auto-deletion after 5 minutes
        error_msg = await edit_message(k, "<i>No Results Found</i>")
        # Schedule for auto-deletion after 5 minutes
        # pylint: disable=unused-variable
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )
        return

    # Search for movies by title
    movies = get_poster(title, bulk=True)
    if not movies:
        # No results found - schedule for auto-deletion after 5 minutes
        error_msg = await edit_message(
            k,
            "<i>No Results Found</i>, Try Again or Use <b>Title ID</b>",
        )
        # Schedule for auto-deletion after 5 minutes
        # pylint: disable=unused-variable
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )

        # If replying to a message with invalid content, delete both messages
        if is_reply:
            await delete_message(message)
            await delete_message(message.reply_to_message)
        return

    # Add movies to buttons
    for movie in movies:
        # Get year safely, ensuring it's not None
        year = movie.get("year") if movie.get("year") else ""
        title = movie.get("title")
        # Format the button text with year only if it exists
        button_text = f"🎬 {title} ({year})" if year else f"🎬 {title}"
        buttons.data_button(
            button_text,
            f"imdb {user_id} movie {movie.movieID}",
        )

    buttons.data_button("🚫 Close 🚫", f"imdb {user_id} close")

    # Show search results and schedule for auto-deletion after 5 minutes
    results_msg = await edit_message(
        k,
        "<b><i>Search Results found on IMDb.com</i></b>",
        buttons.build_menu(1),
    )

    # If replying to a message with valid content but multiple results, delete both messages
    if is_reply:
        await delete_message(message)
        await delete_message(message.reply_to_message)

    # Schedule for auto-deletion after 5 minutes
    # pylint: disable=unused-variable
    create_task(  # noqa: RUF006
        auto_delete_message(results_msg, time=300),
    )


def get_poster(query, bulk=False, id=False, file=None):
    """Get movie/TV series information from IMDB"""
    if not id:
        query = (query.strip()).lower()
        title = query
        year = findall(r"[1-2]\d{3}$", query, IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = findall(r"[1-2]\d{3}", file, IGNORECASE)
            if year:
                year = list_to_str(year[:1])
        else:
            year = None

        movieid = imdb.search_movie(title.lower(), results=10)
        if not movieid:
            return None

        if year:
            filtered = (
                list(filter(lambda k: str(k.get("year")) == str(year), movieid))
                or movieid
            )
        else:
            filtered = movieid

        movieid = (
            list(filter(lambda k: k.get("kind") in ["movie", "tv series"], filtered))
            or filtered
        )

        if bulk:
            return movieid

        movieid = movieid[0].movieID
    else:
        movieid = query

    movie = imdb.get_movie(movieid)

    # Get release date
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"

    # Get plot
    plot = movie.get("plot")
    plot = plot[0] if plot and len(plot) > 0 else movie.get("plot outline")
    if plot and len(plot) > 300:
        plot = f"{plot[:300]}..."

    # Build URLs
    imdb_id = movie.get("imdbID")
    url = f"https://www.imdb.com/title/tt{imdb_id}"
    url_cast = f"{url}/fullcredits#cast"
    url_releaseinfo = f"{url}/releaseinfo"

    # Return movie data
    return {
        "title": movie.get("title"),
        "trailer": movie.get("videos"),
        "votes": movie.get("votes"),
        "aka": list_to_str(movie.get("akas")),
        "seasons": movie.get("number of seasons"),
        "box_office": movie.get("box office"),
        "localized_title": movie.get("localized title"),
        "kind": movie.get("kind"),
        "imdb_id": f"tt{imdb_id}",
        "cast": list_to_str(movie.get("cast")),
        "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_hash(movie.get("countries"), True),
        "certificates": list_to_str(movie.get("certificates")),
        "languages": list_to_hash(movie.get("languages")),
        "director": list_to_str(movie.get("director")),
        "writer": list_to_str(movie.get("writer")),
        "producer": list_to_str(movie.get("producer")),
        "composer": list_to_str(movie.get("composer")),
        "cinematographer": list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")),
        "distributors": list_to_str(movie.get("distributors")),
        "release_date": date,
        "year": movie.get("year"),
        "genres": list_to_hash(movie.get("genres"), emoji=True),
        "poster": movie.get("full-size cover url"),
        "plot": plot,
        "rating": str(movie.get("rating")) + " / 10",
        "url": url,
        "url_cast": url_cast,
        "url_releaseinfo": url_releaseinfo,
    }


async def imdb_callback(_, query):
    """Handle IMDB callback queries"""
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()

    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
        return

    if data[2] == "close":
        await query.answer()
        await delete_message(message)
        return

    if data[2] == "movie":
        await query.answer()
        imdb_data = get_poster(query=data[3], id=True)
        buttons = ButtonMaker()

        # Add trailer button if available
        if imdb_data["trailer"]:
            if isinstance(imdb_data["trailer"], list):
                buttons.url_button("▶️ IMDb Trailer ", imdb_data["trailer"][-1])
                imdb_data["trailer"] = list_to_str(imdb_data["trailer"])
            else:
                buttons.url_button("▶️ IMDb Trailer ", imdb_data["trailer"])

        buttons.data_button("🚫 Close 🚫", f"imdb {user_id} close")
        buttons = buttons.build_menu(1)

        # Default template with Telegram quote format
        default_template = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
<b>⭐ Rating:</b> <i>{rating}</i>
<b>🎭 Genre:</b> {genres}
<b>📅 Released:</b> <a href=\"{url_releaseinfo}\">{release_date}</a>
<b>🎙️ Languages:</b> {languages}
<b>🌍 Country:</b> {countries}
<b>🎬 Type:</b> {kind}

<b>📖 Story Line:</b>
<blockquote>{plot}</blockquote>

<b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>
<b>👥 Cast:</b> <a href=\"{url_cast}\">{cast}</a>

<b>👨‍💼 Director:</b> {director}
<b>✍️ Writer:</b> {writer}
<b>🎵 Music:</b> {composer}
<b>🎥 Cinematography:</b> {cinematographer}

<b>⏱️ Runtime:</b> {runtime} minutes
<b>🏆 Awards:</b> {certificates}

<i>Powered by IMDb</i>"""

        # Get template from config or use default
        template = (
            Config.IMDB_TEMPLATE
            if hasattr(Config, "IMDB_TEMPLATE") and Config.IMDB_TEMPLATE
            else default_template
        )

        # Format caption with template
        if imdb_data and template:
            try:
                cap = template.format(**imdb_data)
            except Exception as e:
                LOGGER.error(f"Error formatting IMDB template: {e}")
                cap = default_template.format(**imdb_data)
        else:
            cap = "No Results"

        # No need for additional formatting as it's already in the template

        # Delete the selection menu immediately
        await delete_message(message)

        # If there's a reply_to_message (original command), delete it too
        if message.reply_to_message:
            await delete_message(message.reply_to_message)

        # Send result with poster as a new message
        if imdb_data.get("poster"):
            try:
                # Send photo with caption
                await TgClient.bot.send_photo(
                    chat_id=query.message.chat.id,
                    caption=cap,
                    photo=imdb_data["poster"],
                    reply_markup=buttons,
                )
            except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                # Try with alternative poster URL
                poster = imdb_data.get("poster").replace(".jpg", "._V1_UX360.jpg")
                await send_message(
                    message,
                    cap,
                    buttons,
                    photo=poster,
                )
        else:
            # Send without poster
            await send_message(
                message,
                cap,
                buttons,
                "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
            )
