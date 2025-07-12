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

    # Try to get additional information using the most effective info sets
    # Based on comprehensive analysis: these info sets provide the most valuable data
    info_sets_to_try = [
        "technical",
        "keywords",
        "release info",
        "quotes",
        "trivia",
        "taglines",
        "connections",
    ]

    for info_set in info_sets_to_try:
        try:
            imdb.update(movie, info=[info_set])
        except Exception as e:
            LOGGER.warning(f"Could not update with {info_set} info: {e}")

    # Get release date
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"

    # Get plot - handle both single plot and list of plots
    plot = movie.get("plot")
    if plot:
        if isinstance(plot, list) and len(plot) > 0:
            plot = plot[0]
        elif isinstance(plot, str):
            pass  # plot is already a string
        else:
            plot = movie.get("synopsis")
            if plot and isinstance(plot, list) and len(plot) > 0:
                plot = plot[0]

    if not plot:
        plot = "Plot under wraps."
    elif len(str(plot)) > 300:
        plot = f"{str(plot)[:300]}..."

    # Build URLs - use movieID since imdbID might not be available
    movie_id = movieid if isinstance(movieid, str) else str(movieid)
    url = f"https://www.imdb.com/title/tt{movie_id}"
    url_cast = f"{url}/fullcredits#cast"
    url_releaseinfo = f"{url}/releaseinfo"

    # Extract runtime from tech info
    runtime = "N/A"
    tech_info = movie.get("tech", {})
    if tech_info and isinstance(tech_info, dict) and "runtime" in tech_info:
        runtime_raw = tech_info["runtime"]
        # Extract just the minutes part: "3h 1m::(181 min)" -> "181"
        if "::" in runtime_raw and "min)" in runtime_raw:
            runtime = runtime_raw.split("::(")[1].replace(" min)", "")
        else:
            runtime = runtime_raw

    # Get countries from country codes
    countries = movie.get("country codes", [])
    if countries and isinstance(countries, list):
        # Convert country codes to country names if possible
        try:
            country_names = []
            for code in countries:
                try:
                    country = conn.get(alpha_2=code.upper())
                    if country:
                        country_names.append(country.name)
                    else:
                        country_names.append(code.upper())
                except (AttributeError, KeyError):
                    country_names.append(code.upper())
            countries = country_names
        except ImportError:
            # If pycountry is not available, just use the codes
            countries = [code.upper() for code in countries]
    else:
        countries = []

    # Get genres from keywords if genres not available
    genres = movie.get("genres")
    if not genres:
        # Try to extract genre-like keywords
        keywords = movie.get("keywords", [])
        if keywords and isinstance(keywords, list):
            # Common genre keywords that might be in the keywords list
            genre_keywords = [
                "action",
                "comedy",
                "drama",
                "horror",
                "thriller",
                "romance",
                "sci-fi",
                "fantasy",
                "adventure",
                "crime",
                "mystery",
                "animation",
                "documentary",
                "biography",
                "history",
                "war",
                "western",
                "musical",
            ]
            found_genres = []
            for keyword in keywords[:10]:  # Check first 10 keywords
                if isinstance(keyword, str):
                    keyword_lower = keyword.lower().replace("-", " ")
                    for genre in genre_keywords:
                        if genre in keyword_lower:
                            found_genres.append(genre.title())
            if found_genres:
                genres = list(set(found_genres))  # Remove duplicates

    # Return comprehensive movie data with all latest supported keys
    return {
        # Basic Information
        "title": movie.get("title", "N/A"),
        "year": movie.get("year", "N/A"),
        "kind": movie.get("kind", "N/A"),
        "rating": f"{movie.get('rating', 'N/A')} / 10"
        if movie.get("rating")
        else "N/A / 10",
        "votes": movie.get("votes"),
        "plot": plot,
        "synopsis": list_to_str(movie.get("synopsis"))
        if movie.get("synopsis")
        else "N/A",
        # Media & Visual
        "poster": movie.get("full-size cover url"),
        "poster_small": movie.get("cover url"),
        "trailer": movie.get("videos"),
        # Technical Information
        "runtime": runtime,
        "tech_info": movie.get("tech"),
        # Content Classification
        "genres": list_to_hash(genres, emoji=True) if genres else "N/A",
        "keywords": list_to_str(movie.get("keywords")[:10])
        if movie.get("keywords")
        else "N/A",  # Limit to first 10
        "certificates": list_to_str(movie.get("certificates"))
        if movie.get("certificates")
        else "N/A",
        # Geographic & Release
        "countries": list_to_hash(countries, True) if countries else "N/A",
        "country_codes": movie.get("country codes"),
        "languages": list_to_hash(movie.get("languages"))
        if movie.get("languages")
        else "N/A",
        "release_dates": list_to_str(movie.get("release dates")[:5])
        if movie.get("release dates")
        else "N/A",  # Limit to first 5
        "release_date": date,
        "original_air_date": movie.get("original air date"),
        "aka": list_to_str(movie.get("akas")),
        # Cast & Crew
        "cast": list_to_str(movie.get("cast")) if movie.get("cast") else "N/A",
        "director": list_to_str(movie.get("director"))
        if movie.get("director")
        else "N/A",
        "writer": list_to_str(movie.get("writer")) if movie.get("writer") else "N/A",
        "producer": list_to_str(movie.get("producer"))
        if movie.get("producer")
        else "N/A",
        "composer": list_to_str(movie.get("composer"))
        if movie.get("composer")
        else "N/A",
        "cinematographer": list_to_str(movie.get("cinematographer"))
        if movie.get("cinematographer")
        else "N/A",
        "music_team": list_to_str(movie.get("music department"))
        if movie.get("music department")
        else "N/A",
        # Business Information
        "box_office": movie.get("box office"),
        "distributors": list_to_str(movie.get("distributors"))
        if movie.get("distributors")
        else "N/A",
        # Additional Content (NEW)
        "trivia": list_to_str(movie.get("trivia")[:3])
        if movie.get("trivia")
        else "N/A",  # Limit to first 3
        "quotes": list_to_str(movie.get("quotes")[:3])
        if movie.get("quotes")
        else "N/A",  # Limit to first 3
        "taglines": list_to_str(movie.get("taglines")[:3])
        if movie.get("taglines")
        else "N/A",  # Limit to first 3
        "goofs": list_to_str(movie.get("goofs")[:3])
        if movie.get("goofs")
        else "N/A",  # Limit to first 3
        "connections": movie.get("connections"),
        # TV Series Specific
        "seasons": movie.get("number of seasons"),
        # URLs & IDs
        "imdb_id": f"tt{movie_id}",
        "url": url,
        "url_cast": url_cast,
        "url_releaseinfo": url_releaseinfo,
        # Legacy fields for compatibility
        "localized_title": movie.get("localized title"),
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
