
import asyncio
import base64
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Confirmed page-number anchors for 24 September 2026
ANCHOR_DATE = date(2026, 9, 24)
MANGALA_ANCHOR_PAGE = 640
SRINGAR_ANCHOR_PAGE = 629

# Confirmed altar-photo positions
POSITIONS = {
    "mangala": [2, 6, 18],
    "sringar": [2, 7, 27],
}


# ============================================================
# Calculate today's pages using India time
# ============================================================

today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
days_from_anchor = (today - ANCHOR_DATE).days

mangala_page = MANGALA_ANCHOR_PAGE + days_from_anchor
sringar_page = SRINGAR_ANCHOR_PAGE + days_from_anchor

MANGALA_URL = (
    f"https://www.iskconmumbai.com/mangala/"
    f"mangal-darshan-{mangala_page}"
)

SRINGAR_URL = (
    f"https://www.iskconmumbai.com/sringar/"
    f"sringar-darshan-{sringar_page}"
)


# ============================================================
# Save a data: URL
# ============================================================

def save_data_url(data_url, output_file):
    """
    Save an image encoded as a data: URL.
    """

    header, encoded = data_url.split(",", 1)

    if ";base64" in header:
        data = base64.b64decode(encoded)
    else:
        data = encoded.encode("utf-8")

    output_file.write_bytes(data)

    print(
        f"Saved {output_file.name} "
        f"({len(data):,} bytes)"
    )


# ============================================================
# Download selected images from a rendered page
# ============================================================

async def get_images(page, url, positions, prefix):
    print(f"\nOpening: {url}")

    await page.goto(
        url,
        wait_until="commit",
        timeout=120000,
    )

    # Allow the page's JavaScript gallery to render.
    await page.wait_for_timeout(10000)

    # Scroll through the page to trigger lazy-loaded images.
    await page.evaluate("""
        async () => {
            const distance = 500;
            const delay = 300;

            while (
                window.scrollY + window.innerHeight <
                document.body.scrollHeight
            ) {
                window.scrollBy(0, distance);
                await new Promise(resolve => setTimeout(resolve, delay));
            }

            window.scrollTo(0, 0);
        }
    """)

    await page.wait_for_timeout(5000)

    # Collect unique image URLs in the order they appear.
    image_urls = await page.evaluate("""
        () => {
            const imgs = Array.from(document.images);
            const urls = [];

            for (const img of imgs) {
                const src =
                    img.currentSrc ||
                    img.src ||
                    img.getAttribute("data-src") ||
                    img.getAttribute("data-lazy-src");

                if (src && !urls.includes(src)) {
                    urls.push(src);
                }
            }

            return urls;
        }
    """)

    print(f"Found {len(image_urls)} unique images.")

    for output_number, position in enumerate(positions, start=1):
        index = position - 1

        if index < 0 or index >= len(image_urls):
            raise RuntimeError(
                f"{prefix}: image position {position} not found. "
                f"Only {len(image_urls)} unique images were found."
            )

        image_url = image_urls[index]

        output_file = (
            BASE_DIR / f"{prefix}-{output_number}.jpg"
        )

        print(
            f"{prefix} position {position}: "
            f"{image_url[:120]}"
        )

        # ----------------------------------------------------
        # Case 1: data:image/... URL
        # ----------------------------------------------------

        if image_url.startswith("data:"):
            save_data_url(
                image_url,
                output_file,
            )
            continue

        # ----------------------------------------------------
        # Case 2: normal HTTP/HTTPS URL
        # ----------------------------------------------------

        parsed = urlparse(image_url)

        if parsed.scheme not in ("http", "https"):
            raise RuntimeError(
                f"Unsupported image URL scheme: "
                f"{parsed.scheme}"
            )

        response = await page.request.get(
            image_url,
            timeout=120000,
        )

        if not response.ok:
            raise RuntimeError(
                f"Failed to download image: "
                f"HTTP {response.status}"
            )

        data = await response.body()

        output_file.write_bytes(data)

        print(
            f"Saved {output_file.name} "
            f"({len(data):,} bytes)"
        )


# ============================================================
# Main
# ============================================================

async def main():
    print("========================================")
    print("ISKCON Juhu Daily Darshan Updater")
    print("========================================")
    print(f"India date: {today}")
    print(f"Days from anchor: {days_from_anchor}")
    print(f"Mangala page: {mangala_page}")
    print(f"Sringar page: {sringar_page}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200,
            }
        )

        try:
            await get_images(
                page,
                MANGALA_URL,
                POSITIONS["mangala"],
                "mangala",
            )

            await get_images(
                page,
                SRINGAR_URL,
                POSITIONS["sringar"],
                "sringar",
            )

        finally:
            await browser.close()

    print("\n========================================")
    print("Update completed successfully.")
    print("========================================")


if __name__ == "__main__":
    asyncio.run(main())

