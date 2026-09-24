
import base64
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

MANGALA_PAGE = 640
SRINGAR_PAGE = 629

URLS = {
    "mangala": (
        "https://www.iskconmumbai.com/mangala/"
        "mangal-darshan-{}"
    ),
    "sringar": (
        "https://www.iskconmumbai.com/sringar/"
        "sringar-darshan-{}"
    ),
}

# Confirmed image positions.
POSITIONS = {
    "mangala": [2, 6, 18],
    "sringar": [2, 7, 27],
}

OUTPUTS = {
    "mangala": [
        "mangala-1.jpg",
        "mangala-2.jpg",
        "mangala-3.jpg",
    ],
    "sringar": [
        "sringar-1.jpg",
        "sringar-2.jpg",
        "sringar-3.jpg",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# DOWNLOAD IMAGE
# ---------------------------------------------------------------------------

def download_image(src):

    if src.startswith("data:image"):

        encoded = src.split(",", 1)[1]
        return base64.b64decode(encoded)

    if src.startswith("http://") or src.startswith("https://"):

        response = requests.get(
            src,
            headers=HEADERS,
            timeout=60,
        )

        response.raise_for_status()

        return response.content

    raise ValueError(
        "Unknown image source: " + src[:100]
    )


# ---------------------------------------------------------------------------
# FIND IMAGES USING CHROMIUM
# ---------------------------------------------------------------------------

def get_browser_images(url):

    print("  Opening Chromium...")

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            user_agent=HEADERS["User-Agent"]
        )

        try:

            page.goto(
                url,
                wait_until="commit",
                timeout=30000,
            )

        except Exception as e:

            print(
                "  Navigation warning:",
                e
            )

        print("  Waiting for gallery...")
        page.wait_for_timeout(10000)

        # Trigger lazy loading.
        page.evaluate("""
            window.scrollTo({
                top: document.body.scrollHeight,
                behavior: "smooth"
            });
        """)

        page.wait_for_timeout(5000)

        images = page.eval_on_selector_all(
            "img",
            """
            els => els.map(e => ({
                src: e.currentSrc || e.src || "",
                dataSrc: e.getAttribute("data-src") || "",
                dataLazy: e.getAttribute("data-lazy-src") || "",
                dataOriginal: e.getAttribute("data-original") || ""
            }))
            """
        )

        browser.close()

    # Remove duplicates.
    unique = []
    seen = set()

    for item in images:

        candidates = [
            item["src"],
            item["dataSrc"],
            item["dataLazy"],
            item["dataOriginal"],
        ]

        for src in candidates:

            if not src:
                continue

            if src in seen:
                continue

            seen.add(src)
            unique.append(src)

            break

    print(
        f"  Found {len(unique)} unique images."
    )

    return unique


# ---------------------------------------------------------------------------
# UPDATE ONE DARSHAN
# ---------------------------------------------------------------------------

def update_darshan(name, page_number):

    print()
    print("----------------------------------------")
    print(
        f"{name.upper()} — page {page_number}"
    )
    print("----------------------------------------")

    url = URLS[name].format(page_number)

    positions = POSITIONS[name]
    output_files = OUTPUTS[name]

    images = get_browser_images(url)

    required = max(positions)

    if len(images) < required:

        raise RuntimeError(
            f"{name}: found {len(images)} images, "
            f"but need at least {required}."
        )

    downloaded = []

    try:

        for position, output_file in zip(
            positions,
            output_files,
        ):

            print(
                f"  Selecting image #{position}"
            )

            src = images[position - 1]

            data = download_image(src)

            if len(data) < 10000:

                raise RuntimeError(
                    f"{output_file} is suspiciously "
                    f"small ({len(data)} bytes)."
                )

            temp_file = output_file + ".tmp"

            with open(temp_file, "wb") as f:
                f.write(data)

            downloaded.append(
                (temp_file, output_file)
            )

            print(
                f"  Downloaded "
                f"{len(data) // 1024} KB -> "
                f"{output_file}"
            )

        # Only replace the real files after all three
        # images have downloaded successfully.
        for temp_file, output_file in downloaded:

            os.replace(
                temp_file,
                output_file
            )

        print(
            f"  {name.capitalize()} update successful."
        )

    except Exception:

        # Clean up temporary files if anything fails.
        for temp_file, _ in downloaded:

            try:
                os.remove(temp_file)
            except OSError:
                pass

        raise


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():

    print()
    print("========================================")
    print("ISKCON DARSHAN PHOTO UPDATER")
    print("========================================")

    print()
    print(
        "Mangala page:",
        MANGALA_PAGE
    )

    print(
        "Sringar page:",
        SRINGAR_PAGE
    )

    try:

        update_darshan(
            "mangala",
            MANGALA_PAGE
        )

        update_darshan(
            "sringar",
            SRINGAR_PAGE
        )

    except Exception as e:

        print()
        print("========================================")
        print("UPDATE FAILED")
        print("========================================")
        print(e)

        sys.exit(1)

    print()
    print("========================================")
    print("ALL SIX PHOTOS UPDATED SUCCESSFULLY")
    print("========================================")
    print()
    print("Mangala:")
    print("  mangala-1.jpg")
    print("  mangala-2.jpg")
    print("  mangala-3.jpg")
    print()
    print("Sringar:")
    print("  sringar-1.jpg")
    print("  sringar-2.jpg")
    print("  sringar-3.jpg")
    print()


if __name__ == "__main__":
    main()










































# """
# this is for only mangal darshan
# Downloads one Mangala Darshan photo from the current ISKCON Juhu page
# and saves it as mangala.jpg.

# 24 Sep 2026 = page 640.
# """

# import base64
# import os
# import sys
# from datetime import date, datetime, timedelta, timezone

# import requests
# from bs4 import BeautifulSoup


# # ---------------------------------------------------------------------------
# # SETTINGS
# # ---------------------------------------------------------------------------

# ANCHOR_DATE = date(2026, 9, 24)
# ANCHOR_NUM = 640

# URL = "https://www.iskconmumbai.com/mangala/mangal-darshan-{}"

# OUTPUT_FILES = [
#     "mangala-1.jpg",
#     "mangala-2.jpg",
#     "mangala-3.jpg",
# ]

# # These are the browser image positions that we identified today.
# # IMPORTANT: these are based on the current page structure.
# IMAGE_POSITIONS = [2, 6, 18]

# HEADERS = {
#     "User-Agent": (
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#         "AppleWebKit/537.36 (KHTML, like Gecko) "
#         "Chrome/124.0 Safari/537.36"
#     )
# }


# # ---------------------------------------------------------------------------
# # DATE
# # ---------------------------------------------------------------------------

# def today_ist():
#     ist = timezone(timedelta(hours=5, minutes=30))
#     return datetime.now(ist).date()


# # ---------------------------------------------------------------------------
# # IMAGE DOWNLOAD
# # ---------------------------------------------------------------------------

# def download_image(src):
#     if src.startswith("data:image"):
#         encoded = src.split(",", 1)[1]
#         return base64.b64decode(encoded)

#     if src.startswith("http://") or src.startswith("https://"):
#         response = requests.get(
#             src,
#             headers=HEADERS,
#             timeout=60,
#         )
#         response.raise_for_status()
#         return response.content

#     raise ValueError(
#         "Unknown image source: " + src[:100]
#     )


# # ---------------------------------------------------------------------------
# # GET IMAGES FROM BROWSER
# # ---------------------------------------------------------------------------

# def get_browser_images(url):

#     from playwright.sync_api import sync_playwright

#     print("Opening page in Chromium...")

#     with sync_playwright() as p:

#         browser = p.chromium.launch(
#             headless=True
#         )

#         page = browser.new_page(
#             user_agent=HEADERS["User-Agent"]
#         )

#         try:
#             page.goto(
#                 url,
#                 wait_until="commit",
#                 timeout=30000,
#             )
#         except Exception as e:
#             print("Navigation warning:", e)

#         print("Waiting for gallery...")
#         page.wait_for_timeout(10000)

#         # Trigger lazy loading.
#         page.evaluate("""
#             window.scrollTo({
#                 top: document.body.scrollHeight,
#                 behavior: "smooth"
#             });
#         """)

#         page.wait_for_timeout(5000)

#         images = page.eval_on_selector_all(
#             "img",
#             """
#             els => els.map(e => ({
#                 src: e.currentSrc || e.src || "",
#                 dataSrc: e.getAttribute("data-src") || "",
#                 dataLazy: e.getAttribute("data-lazy-src") || "",
#                 dataOriginal: e.getAttribute("data-original") || ""
#             }))
#             """
#         )

#         browser.close()

#     # Build unique image list.
#     result = []
#     seen = set()

#     for item in images:

#         candidates = [
#             item["src"],
#             item["dataSrc"],
#             item["dataLazy"],
#             item["dataOriginal"],
#         ]

#         for src in candidates:

#             if not src:
#                 continue

#             if src in seen:
#                 continue

#             seen.add(src)
#             result.append(src)
#             break

#     print(f"Browser found {len(result)} unique images.")

#     return result


# # ---------------------------------------------------------------------------
# # MAIN
# # ---------------------------------------------------------------------------

# def main():

#     today = today_ist()

#     page_number = ANCHOR_NUM + (
#         today - ANCHOR_DATE
#     ).days

#     print()
#     print("========================================")
#     print("ISKCON Mangala Darshan updater")
#     print("========================================")
#     print(f"Today (IST): {today}")
#     print(f"Expected page: {page_number}")
#     print()

#     # Try today's page and then yesterday's page.
#     for number in [
#         page_number,
#         page_number - 1,
#     ]:

#         url = URL.format(number)

#         print(f"Trying page {number}:")
#         print(url)

#         try:
#             images = get_browser_images(url)
#         except Exception as e:
#             print("Browser error:", e)
#             continue

#         if len(images) < max(IMAGE_POSITIONS):
#             print(
#                 f"Only {len(images)} images found; "
#                 f"need at least {max(IMAGE_POSITIONS)}."
#             )
#             continue

#         downloaded = []

#         try:

#             for output_file, position in zip(
#                 OUTPUT_FILES,
#                 IMAGE_POSITIONS
#             ):

#                 src = images[position - 1]

#                 print()
#                 print(
#                     f"Selecting browser image #{position}"
#                 )

#                 data = download_image(src)

#                 if len(data) < 10000:
#                     raise ValueError(
#                         f"Image is suspiciously small: "
#                         f"{len(data)} bytes"
#                     )

#                 temp_file = output_file + ".tmp"

#                 with open(temp_file, "wb") as f:
#                     f.write(data)

#                 downloaded.append(
#                     (temp_file, output_file)
#                 )

#                 print(
#                     f"Downloaded {len(data) // 1024} KB "
#                     f"-> {output_file}"
#                 )

#             # Only replace the existing images after ALL
#             # three downloads succeeded.
#             for temp_file, output_file in downloaded:

#                 os.replace(
#                     temp_file,
#                     output_file
#                 )

#             print()
#             print("========================================")
#             print("SUCCESS")
#             print("========================================")
#             print("Updated:")
#             print("  mangala-1.jpg")
#             print("  mangala-2.jpg")
#             print("  mangala-3.jpg")
#             print()

#             return

#         except Exception as e:

#             print()
#             print("Download failed:", e)

#             # Remove temporary files.
#             for temp_file, _ in downloaded:

#                 try:
#                     os.remove(temp_file)
#                 except OSError:
#                     pass

#     sys.exit(
#         "Could not download all three Mangala Darshan photos."
#     )


# if __name__ == "__main__":
#     main()
