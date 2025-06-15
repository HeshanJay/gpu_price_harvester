# providers/runpod_handler.py
import requests
import json
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone

# --- Configuration and other functions (RUNPOD_PRICING_URL, HOURS_IN_MONTH, STATIC_..., 
# --- get_canonical_variant_and_base_chip, extract_static_text_from_html) 
# --- remain the same as the previous version. I'll include them in the full script at the end.

RUNPOD_PRICING_URL = "https://www.runpod.io/pricing"
HOURS_IN_MONTH = 730

STATIC_SERVICE_PROVIDED_RUNPOD = "AI-specialized cloud (RunPod)"
STATIC_REGION_INFO_RUNPOD = "30+ Global (e.g. US-CA-1, EU-IS-1, AP-SG-1) "
STATIC_STORAGE_OPTION_RUNPOD = "Local NVMe SSD + Network Volume $0.05/GB/month"
STATIC_AMOUNT_OF_STORAGE_RUNPOD = "Maximum 100TB/volume (>1PB upon request)"
STATIC_NETWORK_PERFORMANCE_RUNPOD = "Varies (e.g., up to 3.2 Tbps Inter-Pod)"

def get_canonical_variant_and_base_chip(gpu_id, display_name):
    text_to_search = (str(gpu_id) + " " + str(display_name)).lower()
    variant_map = {
        "H100 SXM": (["h100 sxm", "h100sxm"], "H100"), "H100 NVL": (["h100 nvl"], "H100"),
        "H100 PCIe": (["h100 pcie"], "H100"),
        "H200 SXM": (["h200 sxm", "h200sxm"], "H200"), "GH200 SXM": (["gh200 sxm"], "H200"),
        "H200 NVL": (["h200 nvl"], "H200"), "GH200 NVL": (["gh200 nvl"], "H200"),
        "L40S": (["l40s", "l40 s"], "L40S"),
    }
    for canonical, (terms, family) in variant_map.items():
        if all(term in text_to_search for term in terms): return canonical, family
    if "l40s" in text_to_search or "l40 s" in text_to_search : return display_name, "L40S" # Use display_name for general L40S
    if "h100" in text_to_search: return display_name, "H100"
    if "gh200" in text_to_search: return display_name, "H200"
    if "h200" in text_to_search: return display_name, "H200"
    return None, None

def extract_static_text_from_html(soup, text_keywords_for_id, default_value_to_return, exact_phrase_to_prefer=None):
    try:
        keywords_lower = text_keywords_for_id.lower()
        candidate_tags = soup.find_all(['p', 'div', 'span', 'li', 'h1', 'h2', 'h3', 'h4', 'strong', 'b', 'td', 'th', 'dd', 'dt'])
        matched_elements_texts = []
        for tag in candidate_tags:
            tag_text = tag.get_text(separator=' ', strip=True); tag_text_lower = tag_text.lower()
            if keywords_lower in tag_text_lower:
                if exact_phrase_to_prefer and exact_phrase_to_prefer.lower() in tag_text_lower:
                    return exact_phrase_to_prefer
                if default_value_to_return and default_value_to_return.strip().lower() in tag_text_lower and len(tag_text) < 350 :
                     return tag_text
                if len(tag_text) < 350: matched_elements_texts.append(tag_text)
        if matched_elements_texts:
            if default_value_to_return:
                for mt in matched_elements_texts:
                    if default_value_to_return.strip().lower() in mt.lower(): return mt
            best_match = min(matched_elements_texts, key=len)
            # print(f"RunPod Handler: Found static text for '{text_keywords_for_id}': '{best_match}'")
            return best_match
        # print(f"RunPod Handler: Static text part containing '{text_keywords_for_id}' not clearly matched, using default: '{default_value_to_return}'")
        return default_value_to_return
    except Exception as e:
        # print(f"RunPod Handler: Error extracting static text for '{text_keywords_for_id}': {e}")
        return default_value_to_return

def fetch_runpod_data(soup):
    final_sheet_rows_unpivoted = []
    provider_name_for_sheet = "RunPod"

    live_service_provided = extract_static_text_from_html(soup, "AI-specialized cloud", STATIC_SERVICE_PROVIDED_RUNPOD, exact_phrase_to_prefer=STATIC_SERVICE_PROVIDED_RUNPOD)
    live_region_info = extract_static_text_from_html(soup, "Secure Cloud Locations", STATIC_REGION_INFO_RUNPOD, exact_phrase_to_prefer=STATIC_REGION_INFO_RUNPOD)
    live_storage_option = extract_static_text_from_html(soup, "Network Volume pricing is", STATIC_STORAGE_OPTION_RUNPOD, exact_phrase_to_prefer=STATIC_STORAGE_OPTION_RUNPOD)
    live_amount_of_storage = extract_static_text_from_html(soup, "Volumes can be sized up to", STATIC_AMOUNT_OF_STORAGE_RUNPOD, exact_phrase_to_prefer=STATIC_AMOUNT_OF_STORAGE_RUNPOD)
    live_network_performance = extract_static_text_from_html(soup, "network speed", STATIC_NETWORK_PERFORMANCE_RUNPOD)

    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script_tag: print("ERROR (RunPod): Could not find __NEXT_DATA__ script tag."); return []
    try: page_data_json = json.loads(script_tag.string)
    except json.JSONDecodeError as e: print(f"ERROR (RunPod) parsing JSON: {e}"); return []

    page_props_content = page_data_json.get("props", {}).get("pageProps", {})
    gpu_data_source = page_props_content.get("data", {}).get("gpu", {})
    if not gpu_data_source or not isinstance(gpu_data_source, dict):
        print("ERROR (RunPod): GPU data dictionary not found."); return []

    print(f"Found {len(gpu_data_source)} RunPod offerings. Processing for unpivoted Google Sheet output...")

    for gpu_id_from_runpod, details in gpu_data_source.items():
        if gpu_id_from_runpod == "unknown" or not isinstance(details, dict): continue

        display_name_from_runpod = details.get("displayName", "N/A")
        canonical_variant_name, base_chip_category = get_canonical_variant_and_base_chip(gpu_id_from_runpod, display_name_from_runpod)

        if not base_chip_category: continue

        gpus_in_this_offering = 1
        match_count_in_id = re.match(r"(\d+)x", gpu_id_from_runpod, re.IGNORECASE)
        if match_count_in_id: gpus_in_this_offering = int(match_count_in_id.group(1))

        if gpus_in_this_offering != 1: continue

        base_1x_hourly_price = None
        secure_price_raw = details.get("securePrice")
        try: base_1x_hourly_price = float(secure_price_raw) if secure_price_raw is not None else None
        except (ValueError, TypeError): base_1x_hourly_price = None

        if base_1x_hourly_price is None: continue

        def get_price_float(price_key):
            price_raw = details.get(price_key)
            return float(price_raw) if price_raw not in [None, "N/A", ""] and isinstance(price_raw, (int, float)) else None

        one_month_discount_hourly = get_price_float("oneMonthPrice")
        three_month_discount_hourly = get_price_float("threeMonthPrice")
        six_month_discount_hourly = get_price_float("sixMonthPrice")
        twelve_month_discount_hourly = get_price_float("yearlyPrice") or get_price_float("twelveMonthPrice")

        base_info_for_row = {
            "Provider Name": provider_name_for_sheet,
            "Currency": "USD",
            "Service Provided": live_service_provided, "Region": live_region_info,
            "GPU ID": gpu_id_from_runpod, "GPU (H100 or H200 or L40S)": base_chip_category,
            "Memory (GB)": int(details.get("memoryInGb", 0) or 0),
            "Display Name(GPU Type)": display_name_from_runpod,
            "Storage Option": live_storage_option,
            "Amount of Storage": live_amount_of_storage,
            "Network Performance (Gbps)": live_network_performance,
            "Commitment Discount - 1 Month Price ($/hr per GPU)": one_month_discount_hourly if one_month_discount_hourly is not None else "N/A",
            "Commitment Discount - 3 Month Price ($/hr per GPU)": three_month_discount_hourly if three_month_discount_hourly is not None else "N/A",
            "Commitment Discount - 6 Month Price ($/hr per GPU)": six_month_discount_hourly if six_month_discount_hourly is not None else "N/A",
            "Commitment Discount - 12 Month Price ($/hr per GPU)": twelve_month_discount_hourly if twelve_month_discount_hourly is not None else "N/A",
            "Notes / Features": f"Variant: {canonical_variant_name}. Stock: {details.get('lowestPrice', {}).get('stockStatus', 'N/A')}, Max Pod GPUs: {details.get('maxGpuCount', 'N/A')}"
        }

        for num_chips_to_calc in [1, 2, 4, 8]:
            # --- Per Hour ---
            total_hourly_price_numeric = base_1x_hourly_price * num_chips_to_calc
            eff_hr_display_per_hour = base_1x_hourly_price
            row_hourly_data = {
                **base_info_for_row,
                "Number of Chips": num_chips_to_calc,
                "Period": "Per Hour",
                "Total Price ($)": round(total_hourly_price_numeric, 2) if total_hourly_price_numeric is not None else "N/A",
                "Effective Hourly Rate ($/hr)": round(eff_hr_display_per_hour, 2) if eff_hr_display_per_hour is not None else "N/A"
            }
            final_sheet_rows_unpivoted.append(row_hourly_data)

            # --- Per 6 Months ---
            eff_hr_for_6_months_period = six_month_discount_hourly # Use the specific 6-month rate
            
            total_6_months_price_numeric = "N/A"
            total_price_6_months_str = "N/A"
            eff_hr_display_6_months = "N/A"

            if eff_hr_for_6_months_period is not None: 
                total_6_months_price_numeric = (eff_hr_for_6_months_period * HOURS_IN_MONTH * 6) * num_chips_to_calc
                eff_hr_display_6_months = round(eff_hr_for_6_months_period, 2)
                total_n_chip_hourly_for_6mo_period = eff_hr_for_6_months_period * num_chips_to_calc
                # CHANGED FORMATTING: Removed leading $ for numbers, kept structure
                total_price_6_months_str = f"{round(total_n_chip_hourly_for_6mo_period, 2)} ({round(total_6_months_price_numeric, 2)})"
            
            row_6_months_data = {
                **base_info_for_row,
                "Number of Chips": num_chips_to_calc,
                "Period": "Per 6 Months",
                "Total Price ($)": total_price_6_months_str, # This now contains the string "N_CHIP_HOURLY_TOTAL (TOTAL_FOR_PERIOD)"
                "Effective Hourly Rate ($/hr)": eff_hr_display_6_months 
            }
            final_sheet_rows_unpivoted.append(row_6_months_data)

            # --- Per Year (12 Months) ---
            eff_hr_for_yearly_period = twelve_month_discount_hourly # Use the specific 12-month rate
            
            total_yearly_price_numeric = "N/A"
            total_price_yearly_str = "N/A"
            eff_hr_display_yearly = "N/A"

            if eff_hr_for_yearly_period is not None: 
                total_yearly_price_numeric = (eff_hr_for_yearly_period * HOURS_IN_MONTH * 12) * num_chips_to_calc
                eff_hr_display_yearly = round(eff_hr_for_yearly_period, 2)
                total_n_chip_hourly_for_yearly_period = eff_hr_for_yearly_period * num_chips_to_calc
                # CHANGED FORMATTING: Removed leading $ for numbers, kept structure
                total_price_yearly_str = f"{round(total_n_chip_hourly_for_yearly_period, 2)} ({round(total_yearly_price_numeric, 2)})"
                
            row_yearly_data = {
                **base_info_for_row,
                "Number of Chips": num_chips_to_calc,
                "Period": "Per Year",
                "Total Price ($)": total_price_yearly_str, # This now contains the string "N_CHIP_HOURLY_TOTAL (TOTAL_FOR_PERIOD)"
                "Effective Hourly Rate ($/hr)": eff_hr_display_yearly
            }
            final_sheet_rows_unpivoted.append(row_yearly_data)
            
    if final_sheet_rows_unpivoted:
        num_base_offerings = len(set(row["GPU ID"] for row in final_sheet_rows_unpivoted if row["Number of Chips"] == 1 and row["Period"] == "Per Hour"))
        print(f"RunPod: Processed and unpivoted data for {num_base_offerings} base 1-GPU offerings, generating {len(final_sheet_rows_unpivoted)} total rows for Sheet.")
    else:
        print(f"RunPod: No 1-GPU offerings found for target variants to generate unpivoted rows for Sheet.")
    return final_sheet_rows_unpivoted

# --- (Optional) Add a simple test call if you run this file directly ---
if __name__ == '__main__':
    print(f"Testing RunPod Handler. Fetching {RUNPOD_PRICING_URL}...")
    try:
        response = requests.get(RUNPOD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0..."}, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        processed_data = fetch_runpod_data(soup)
        if processed_data:
            print(f"\nSample of processed RunPod data (first {min(12, len(processed_data))} rows):")
            for i, row_data in enumerate(processed_data):
                if i >= 12: break
                print(f"Row {i+1}: {row_data}")
        else:
            print("No data processed by fetch_runpod_data.")
    except Exception as e:
        print(f"Error during direct test of runpod_handler: {e}")
        import traceback
        traceback.print_exc()