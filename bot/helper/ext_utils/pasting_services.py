from bs4 import BeautifulSoup
from httpx import AsyncClient
from telegraph import Telegraph

from bot import LOGGER


async def katbin_paste(text: str) -> str:
    """
    Paste the text in katb.in website.
    Args:
        text: The text content to paste
    Returns:
        str: URL of the pasted content or error message
    """
    katbin_url = "https://katb.in"
    client = AsyncClient()
    try:
        # Get the CSRF token from the page
        response = await client.get(katbin_url)
        soup = BeautifulSoup(response.content, "html.parser")
        csrf_token = soup.find("input", {"name": "_csrf_token"}).get("value")

        # Post the content with the CSRF token
        paste_post = await client.post(
            katbin_url,
            data={"_csrf_token": csrf_token, "paste[content]": text},
            follow_redirects=False,
        )

        # Get the URL from the redirect location
        return f"{katbin_url}{paste_post.headers['location']}"
    except Exception as e:
        LOGGER.error(f"Error in katbin_paste: {e}")
        return "Something went wrong while pasting text in katb.in."
    finally:
        await client.aclose()


async def telegraph_paste(content: str, title="AimLeechBot") -> str:
    """
    Paste the text in telegra.ph (graph.org) website.
    Args:
        content: The text content to paste
        title: Title for the Telegraph page
    Returns:
        str: URL of the pasted content or fallback to katbin
    """
    try:
        # The standard Telegraph package is synchronous
        telegraph = Telegraph(domain="graph.org")
        telegraph.create_account(short_name=title)
        html_content = (
            "<pre><code>" + content.replace("\n", "<br>") + "</code></pre>"
        )

        response = telegraph.create_page(title=title, html_content=html_content)
        return response["url"]
    except Exception as e:
        LOGGER.error(f"Error in telegraph_paste: {e}")
        # Fallback to katbin if telegraph fails
        return await katbin_paste(content)
