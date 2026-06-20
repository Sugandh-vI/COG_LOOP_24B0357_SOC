"""
browser_test.py — Week 2, Task 2
Uses Playwright to scrape the current headlines from Hacker News and
displays a numbered list of titles and their URLs.

Optionally prompts the user to open one of the headlines in their browser.
"""

import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def scrape_hacker_news(max_headlines: int = 20) -> list[dict]:
    """
    Scrape top headlines from Hacker News.

    Args:
        max_headlines: Maximum number of headlines to return.

    Returns:
        A list of dicts with 'title' and 'url' keys.
    """
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://news.ycombinator.com", timeout=15000)

            # Each story row has class "athing"; the title link is inside .titleline > a
            story_rows = page.locator("tr.athing").all()

            for row in story_rows[:max_headlines]:
                try:
                    title_el = row.locator(".titleline > a").first
                    title = title_el.inner_text(timeout=3000).strip()
                    href = title_el.get_attribute("href") or ""

                    # Some links are relative (e.g., items/ on HN); make them absolute
                    if href.startswith("item?"):
                        href = f"https://news.ycombinator.com/{href}"

                    if title:
                        results.append({"title": title, "url": href})
                except PlaywrightTimeoutError:
                    continue  # Skip rows that time out

            browser.close()
    except PlaywrightTimeoutError:
        print("Error: Timed out while loading Hacker News. Check your internet connection.")
    except Exception as exc:
        print(f"Error during scraping: {exc}")

    return results


def main():
    print("Fetching top headlines from Hacker News...\n")
    headlines = scrape_hacker_news(max_headlines=20)

    if not headlines:
        print("No headlines found. The page structure may have changed.")
        sys.exit(1)

    # Print numbered list
    for i, item in enumerate(headlines, start=1):
        print(f"{i}. {item['title']}")
        print(f"   {item['url']}\n")

    # Optional: let the user open a headline in their default browser
    try:
        choice = input("Enter a number to open that link (or press Enter to quit): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(headlines):
                import webbrowser
                webbrowser.open(headlines[idx]["url"])
                print(f"Opening: {headlines[idx]['url']}")
            else:
                print("Invalid number.")
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
