"""
youtube_autoplay.py — Week 2, Task 3
Takes a search query from the user, opens YouTube in a visible Chromium
browser, searches for the query, clicks the first video result, and plays it.

Handles common real-world issues:
  - Cookie / consent pop-ups
  - Ad skip button (waits up to 8 seconds after video load)
  - Robust waits to avoid flaky timing errors
"""

import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def dismiss_consent_popup(page) -> None:
    """
    Dismiss the YouTube cookie consent / sign-in pop-up if it appears.
    Silently does nothing if the pop-up is not present.
    """
    try:
        # European cookie consent form
        consent_btn = page.locator("button:has-text('Accept all')").first
        if consent_btn.is_visible(timeout=4000):
            consent_btn.click()
            page.wait_for_timeout(1000)
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass


def skip_ad_if_present(page) -> None:
    """
    Click the 'Skip Ad' button if it appears within 8 seconds of video start.
    Silently does nothing if no ad is present.
    """
    try:
        skip_btn = page.locator(".ytp-skip-ad-button, .ytp-ad-skip-button").first
        if skip_btn.is_visible(timeout=8000):
            skip_btn.click()
            print("Ad skipped.")
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass


def youtube_autoplay(query: str) -> None:
    """
    Search YouTube for the given query and auto-play the first result.

    Args:
        query: The search term to look up on YouTube.
    """
    with sync_playwright() as p:
        # headless=False so the user can watch the video play
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            # Spoof a common User-Agent to reduce bot-detection friction
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        print(f"Opening YouTube and searching for: {query!r}")
        try:
            page.goto("https://www.youtube.com", timeout=20000)
        except PlaywrightTimeoutError:
            print("Error: Timed out loading YouTube. Check your internet connection.")
            browser.close()
            return

        # Wait for initial page render before querying the DOM
        page.wait_for_load_state("domcontentloaded")

        # Handle consent / cookie pop-up before interacting with the page
        dismiss_consent_popup(page)

        # Type the query into the search box and submit.
        # Selector verified against live YouTube DOM:
        # input[name="search_query"] -> count=1
        # input#search              -> count=0  (outdated, no longer in DOM)
        try:
            search_box = page.locator('input[name="search_query"]').first
            search_box.wait_for(state="visible", timeout=12000)
            search_box.fill(query)
            search_box.press("Enter")
        except PlaywrightTimeoutError:
            print("Error: Could not find the YouTube search box.")
            browser.close()
            return

        # Wait for search results to load
        print("Waiting for search results...")
        try:
            page.wait_for_selector("ytd-video-renderer", timeout=15000)
        except PlaywrightTimeoutError:
            print("Error: Search results did not load in time.")
            browser.close()
            return

        # Click the first video result
        try:
            first_video = page.locator("ytd-video-renderer #video-title").first
            first_title = first_video.inner_text(timeout=5000).strip()
            print(f"Playing: {first_title}")
            first_video.click()
        except PlaywrightTimeoutError:
            print("Error: Could not click the first video result.")
            browser.close()
            return

        # Wait for the video player to appear
        try:
            page.wait_for_selector("video", timeout=15000)
        except PlaywrightTimeoutError:
            print("Error: Video player did not load.")
            browser.close()
            return

        # Handle any pre-roll ad
        time.sleep(2)  # Brief pause to let the ad start if present
        skip_ad_if_present(page)

        print("Video is playing. The browser will stay open for 30 seconds.")
        time.sleep(30)

        browser.close()
        print("Done.")


def main():
    try:
        query = input("Enter your YouTube search query: ").strip()
        if not query:
            print("No query entered. Exiting.")
            sys.exit(0)
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)

    youtube_autoplay(query)


if __name__ == "__main__":
    main()
