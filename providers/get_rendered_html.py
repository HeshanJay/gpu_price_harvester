# get_full_list.py

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

VAST_AI_PRICING_URL = "https://console.vast.ai/create/"


def fetch_and_save_final_html(url, output_filename="vast_rendered.html"):
    """
    Launches a browser, repeatedly clicks the "Show More" button up to 20 times,
    and then saves the final, complete HTML.
    """
    print("Initializing VISIBLE Chrome browser...")
    service = ChromeService(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()

    # Keep it visible to watch the process.
    # options.add_argument('--headless')

    options.add_argument("window-size=1280,1024")
    driver = webdriver.Chrome(service=service, options=options)

    print(f"Navigating to {url}...")
    driver.get(url)

    print("Waiting 10 seconds for the initial page to load...")
    time.sleep(10)

    # --- MODIFIED SECTION ---
    # Initialize a counter and set the maximum number of clicks.
    click_count = 0
    max_clicks = 20

    # Loop will now run up to 'max_clicks' times.
    while click_count < max_clicks:
        try:
            # Wait for the button to be clickable
            show_more_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[text()='Show More']"))
            )

            # Increment counter before the click
            click_count += 1

            print(
                f"Found 'Show More' button (Click #{click_count}/{max_clicks}). Clicking...")

            # Use JavaScript click for reliability
            driver.execute_script("arguments[0].click();", show_more_button)

            # Wait for new content to load
            print("Waiting 5 seconds for new rows to appear...")
            time.sleep(5)

        except NoSuchElementException:
            # This handles the case where the button disappears before we reach 20 clicks.
            print(
                "'Show More' button not found before reaching the limit. All instances are loaded.")
            break
        except Exception as e:
            # Catch any other unexpected errors during the click loop.
            print(
                f"An unexpected error occurred while trying to click 'Show More': {e}")
            break

    # Add a message if the loop finished because it hit the click limit.
    if click_count == max_clicks:
        print(f"Reached the maximum limit of {max_clicks} clicks.")

    print(
        f"\nClicking process finished after {click_count} clicks. Capturing final page source...")
    html_content = driver.page_source

    print(f"Saving the rendered HTML to {output_filename}...")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"HTML saved successfully. It should now contain all instances.")
    driver.quit()


if __name__ == "__main__":
    fetch_and_save_final_html(VAST_AI_PRICING_URL)
