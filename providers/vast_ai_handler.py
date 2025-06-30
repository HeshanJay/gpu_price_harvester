# # providers/vast_ai_handler.py

# import requests
# import json
# from datetime import datetime, timezone
# import os
# import re
# from bs4 import BeautifulSoup

# # --- Configuration specific to Vast.ai Handler ---
# # This is the page that needs to be loaded by a browser automation tool like Selenium.
# VAST_AI_PRICING_URL = "https://console.vast.ai/create/"

# HOURS_IN_MONTH = 730

# # Static information for consistent data entry
# STATIC_SERVICE_PROVIDED_VASTAI = "Decentralized GPU Cloud (Vast.ai)"
# STATIC_REGION_INFO_VASTAI = "Global Datacenters (User-selected)"
# STATIC_STORAGE_OPTION_VASTAI = "Instance Disk (varies) + Optional Persistent Storage"
# STATIC_AMOUNT_OF_STORAGE_VASTAI = "Varies by instance; Persistent typically up to 1TB+"
# STATIC_NETWORK_PERFORMANCE_VASTAI = "Varies by instance (e.g., 1-100 Gbps typical)"


# def get_canonical_variant_and_base_chip_vast(gpu_model_from_page):
#     """
#     Parses the GPU model text from the webpage to find its canonical name and base chip family.
#     """
#     text_to_search = str(gpu_model_from_page).lower().strip()

#     if "h100 sxm" in text_to_search:
#         return "H100 SXM", "H100"
#     if "h100 nvl" in text_to_search:
#         return "H100 NVL", "H100"
#     if "h100 pcie" in text_to_search:
#         return "H100 PCIe", "H100"
#     if "h200 sxm" in text_to_search or "gh200" in text_to_search:
#         return "H200 SXM", "H200"
#     if "h200 nvl" in text_to_search:
#         return "H200 NVL", "H200"
#     if "h200" == text_to_search:
#         return "H200 (Unknown Variant)", "H200"
#     if "l40s" == text_to_search or "l40 s" == text_to_search or "nvidia l40s" in text_to_search:
#         return "L40S", "L40S"

#     # Broader fallbacks for other H100/H200 types that may appear
#     if "h100" in text_to_search:
#         return gpu_model_from_page.split(' ', 1)[-1], "H100"
#     if "h200" in text_to_search:
#         return gpu_model_from_page.split(' ', 1)[-1], "H200"

#     return None, None


# def fetch_vast_ai_data(soup: BeautifulSoup):
#     """
#     Fetches GPU pricing data by scraping the BeautifulSoup object of the Vast.ai pricing page.
#     This version captures ALL valid instances found, not just the cheapest one.

#     Args:
#         soup: A BeautifulSoup object containing the *fully rendered* HTML of the Vast.ai page.
#     """
#     all_offerings = []  # This list will store EVERY valid GPU offering found.
#     provider_name_for_sheet = "Vast.ai"
#     gpu_targets = {"H100", "H200", "L40S"}

#     # NOTE: You must verify this selector is correct by inspecting the page.
#     # It might be 'div.instance-card' or something similar.
#     instance_rows = soup.select('div.machine-row')

#     if not instance_rows:
#         print("Vast.ai Scraper: No instance rows found. The main selector (e.g., 'div.machine-row') may need to be updated.")
#         return []

#     print(
#         f"Vast.ai Scraper: Found {len(instance_rows)} instance rows to process.")

#     for row in instance_rows:
#         try:
#             gpu_name_page = "N/A"
#             location = STATIC_REGION_INFO_VASTAI
#             memory_gb_per_gpu = 0

#             data_divs = row.select('div.popover-container')

#             for div in data_divs:
#                 text = div.text.strip()
#                 if re.search(r'^\d+x\s+(H100|H200|L40S)', text):
#                     gpu_name_page = text
#                 # NOTE: This selector for location is a guess. It may need to be made more specific
#                 # by inspecting the HTML for a unique attribute on the location element.
#                 elif re.search(r',\s[A-Z]{2}$', text):
#                     location = text
#                 elif re.search(r'^\d+(\.\d+)?\s+GB$', text):
#                     memory_gb_per_gpu = int(
#                         float(re.sub(r'[^0-9.]', '', text)))

#             canonical_variant, base_chip_family = get_canonical_variant_and_base_chip_vast(
#                 gpu_name_page)

#             if not base_chip_family or base_chip_family not in gpu_targets:
#                 continue

#             price_element = row.select_one('div.button-hover div.MuiBox-root')
#             if not price_element:
#                 continue

#             price_text = price_element.text.strip()
#             hourly_price = float(re.sub(r'[^\d.]', '', price_text))

#             if not hourly_price:
#                 continue

#             instance_id_element = row.select_one('div[data-aid="instance_id"]')
#             instance_id = instance_id_element.text.strip() if instance_id_element else "N/A"

#             # Create a dictionary for the current offering
#             offering_details = {
#                 "Provider Name": provider_name_for_sheet,
#                 "Service Provided": STATIC_SERVICE_PROVIDED_VASTAI,
#                 "Currency": "USD",
#                 "Region": location,
#                 "GPU ID": f"vast-scraped_{instance_id.replace('#', '')}",
#                 "GPU (H100 or H200 or L40S)": base_chip_family,
#                 "Memory (GB)": memory_gb_per_gpu,
#                 "Display Name(GPU Type)": gpu_name_page,
#                 "GPU Variant Name": canonical_variant,
#                 "Storage Option": STATIC_STORAGE_OPTION_VASTAI,
#                 "Amount of Storage": STATIC_AMOUNT_OF_STORAGE_VASTAI,
#                 "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_VASTAI,
#                 "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
#                 "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
#                 "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
#                 "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
#                 "Number of Chips": int(re.sub(r'[^0-9]', '', gpu_name_page.split('x')[0])),
#                 "Notes / Features": f"Scraped from web. Instance ID: {instance_id}",
#                 "Period": "Per Hour",
#                 "Total Price ($)": round(hourly_price, 4),
#                 "Effective Hourly Rate ($/hr)": round(hourly_price, 4)
#             }
#             # This line adds EVERY valid offering to our list, not just the cheapest
#             all_offerings.append(offering_details)

#         except (AttributeError, ValueError, TypeError) as e:
#             # Silently skip rows that have parsing errors, as some may be incomplete.
#             continue

#     print(
#         f"Vast.ai Scraper: Successfully processed {len(all_offerings)} instances.")
#     return all_offerings


# if __name__ == '__main__':
#     # --- Local Test for Web Scraping ---
#     # This test requires a file named 'vast_rendered.html' which contains the
#     # FULLY RENDERED HTML of the pricing page.
#     print("Testing Vast.ai Handler (Web Scraping Mode)...")
#     try:
#         with open('vast_rendered.html', 'r', encoding='utf-8') as f:
#             print("Found 'vast_rendered.html'. Parsing file...")
#             soup = BeautifulSoup(f.read(), "html.parser")
#             processed_data = fetch_vast_ai_data(soup)

#             if processed_data:
#                 # --- MODIFIED SECTION ---
#                 # This loop will now print every GPU record found instead of just a sample.
#                 print(
#                     f"\n--- Full List of Processed Vast.ai Data ({len(processed_data)} rows) ---")
#                 # The slice "[:3]" has been removed
#                 for i, row_data in enumerate(processed_data):
#                     print(f"--- Row {i+1} ---")
#                     print(json.dumps(row_data, indent=2))
#                 print("\n--- End of List ---")
#             else:
#                 print(
#                     "No data processed by fetch_vast_ai_data. Check your HTML file and selectors.")

#     except FileNotFoundError:
#         print("\n---! TEST SKIPPED !---")
#         print("To run this local test, you must:")
#         print("1. Use a tool like Selenium to load the page and wait for content.")
#         print("2. Save the complete, rendered page source as an HTML file.")
#         print("3. Name the file 'vast_rendered.html' and place it in the same directory as this script.")


# providers/vast_ai_handler.py

import requests
import json
from datetime import datetime, timezone
import os
import re
from bs4 import BeautifulSoup

# --- Configuration specific to Vast.ai Handler ---
VAST_AI_PRICING_URL = "https://console.vast.ai/create/"

# Static information for consistent data entry
STATIC_SERVICE_PROVIDED_VASTAI = "Decentralized GPU Cloud (Vast.ai)"
STATIC_STORAGE_OPTION_VASTAI = "Instance Disk (varies) + Optional Persistent Storage"
STATIC_AMOUNT_OF_STORAGE_VASTAI = "Varies by instance; Persistent typically up to 1TB+"
STATIC_NETWORK_PERFORMANCE_VASTAI = "Varies by instance (e.g., 1-100 Gbps typical)"


def get_canonical_variant_and_base_chip_vast(gpu_model_from_page):
    """
    Parses the GPU model text from the webpage to find its canonical name and base chip family.
    """
    text_to_search = str(gpu_model_from_page).lower().strip()

    # Prioritize specific variants first
    if "h100 sxm" in text_to_search:
        return "H100 SXM", "H100"
    if "h100 nvl" in text_to_search:
        return "H100 NVL", "H100"
    if "h100 pcie" in text_to_search:
        return "H100 PCIe", "H100"
    if "gh200" in text_to_search:
        return "H200 SXM (GH200)", "H200"
    if "h200 sxm" in text_to_search:
        return "H200 SXM", "H200"
    if "h200 pcie" in text_to_search:
        return "H200 PCIe", "H200"
    if "l40s" in text_to_search or "l40 s" in text_to_search:
        return "L40S", "L40S"

    # Broader fallbacks for general types
    if "h100" in text_to_search:
        return "H100", "H100"
    if "h200" in text_to_search:
        return "H200", "H200"

    # Return None for the base chip if it's not a target
    return gpu_model_from_page, None


def fetch_vast_ai_data(soup: BeautifulSoup):
    """
    Fetches GPU pricing data by scraping the BeautifulSoup object of the Vast.ai pricing page.
    This version uses robust selectors based on the latest site structure.
    """
    all_offerings = []
    provider_name_for_sheet = "Vast.ai"
    gpu_targets = {"H100", "H200", "L40S"}

    instance_rows = soup.select('div.machine-row')

    if not instance_rows:
        print("Vast.ai Scraper: No instance rows found. The main selector ('div.machine-row') may need updating.")
        return []

    print(
        f"Vast.ai Scraper: Found {len(instance_rows)} instance rows to process.")

    for row in instance_rows:
        try:
            # Re-initialize for each row
            gpu_name_page = "N/A"
            location = "Global Datacenters (User-selected)"
            memory_gb_per_gpu = 0

            # Find all potential data points within the row's central layout area
            data_divs = row.select('.fixed-layout > .popover-container')

            # First pass: identify the GPU name from its unique styling/position
            for div in data_divs:
                style = div.get('style', '')
                if 'font-size: 24px' in style:
                    gpu_name_page = div.text.strip()
                    break

            # If no GPU name was found, skip this row
            if gpu_name_page == "N/A":
                continue

            # Now, check if this GPU is one of our targets
            canonical_variant, base_chip_family = get_canonical_variant_and_base_chip_vast(
                gpu_name_page)
            if not base_chip_family or base_chip_family not in gpu_targets:
                continue

            # Second pass: extract other details like location and RAM
            for div in data_divs:
                text = div.text.strip()
                # Regex for location (e.g., "City, CC")
                if re.search(r',\s[A-Z]{2}$', text):
                    location = text
                # Regex for GPU RAM (e.g., "80 GB", "140 GB")
                elif re.search(r'^\d+\sGB$', text) and 'GB/s' not in text:
                    memory_gb_per_gpu = int(
                        float(re.sub(r'[^0-9.]', '', text)))

            # Extract the unique instance ID
            instance_id_element = row.select_one('div[data-aid="instance_id"]')
            instance_id = "N/A"
            if instance_id_element:
                instance_id = instance_id_element.text.strip().replace('Type #', '')

            if instance_id == "N/A":
                continue

            # Extract the price
            price_element = row.select_one('div.button-hover div.MuiBox-root')
            if not price_element:
                continue

            price_text = price_element.text.strip()
            hourly_price_match = re.search(r'[\$]?(\d+\.\d+)', price_text)
            if not hourly_price_match:
                continue
            hourly_price = float(hourly_price_match.group(1))

            num_chips_match = re.search(r'^(\d+)x', gpu_name_page)
            number_of_chips = int(num_chips_match.group(1)
                                  ) if num_chips_match else 1

            offering_details = {
                "Provider Name": provider_name_for_sheet,
                "Service Provided": STATIC_SERVICE_PROVIDED_VASTAI,
                "Currency": "USD",
                "Region": location,
                "GPU ID": f"vast-scraped_{instance_id}",
                "GPU (H100 or H200 or L40S)": base_chip_family,
                "Memory (GB)": memory_gb_per_gpu,
                "Display Name(GPU Type)": gpu_name_page,
                "GPU Variant Name": canonical_variant,
                "Storage Option": STATIC_STORAGE_OPTION_VASTAI,
                "Amount of Storage": STATIC_AMOUNT_OF_STORAGE_VASTAI,
                "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_VASTAI,
                "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
                "Number of Chips": number_of_chips,
                "Notes / Features": f"Scraped from web. Instance ID: {instance_id}",
                "Period": "Per Hour",
                "Total Price ($)": round(hourly_price, 4),
                "Effective Hourly Rate ($/hr)": round(hourly_price / number_of_chips, 4) if number_of_chips > 0 else 0
            }
            all_offerings.append(offering_details)

        except (AttributeError, ValueError, TypeError, IndexError) as e:
            # print(f"Vast.ai Scraper: Skipping a row due to parsing error: {e}")
            continue

    print(
        f"Vast.ai Scraper: Successfully processed {len(all_offerings)} instances.")
    return all_offerings


if __name__ == '__main__':
    # Local test block remains the same
    pass
