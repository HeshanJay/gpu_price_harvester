# providers/vast_ai_handler.py
import requests
import json
import re
from datetime import datetime, timezone
import os
from bs4 import BeautifulSoup

# --- Configuration specific to Vast.ai Handler ---
VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY", "YOUR_PLACEHOLDER_VAST_AI_KEY_HERE")
VAST_BUNDLES_URL = "https://console.vast.ai/api/v0/bundles/"

HOURS_IN_MONTH = 730

STATIC_SERVICE_PROVIDED_VASTAI = "Decentralized GPU Cloud (Vast.ai)"
STATIC_REGION_INFO_VASTAI = "Global Datacenters (User-selected)"
STATIC_STORAGE_OPTION_VASTAI = "Instance Disk (varies) + Optional Persistent Storage"
STATIC_AMOUNT_OF_STORAGE_VASTAI = "Varies by instance; Persistent typically up to 1TB+"
STATIC_NETWORK_PERFORMANCE_VASTAI = "Varies by instance (e.g., 1-100 Gbps typical)"

def get_canonical_variant_and_base_chip_vast(gpu_model_from_api, num_gpus_in_bundle=1):
    text_to_search = str(gpu_model_from_api).lower()
    prefix = "" # For 1-GPU offerings, prefix is not needed for variant name

    if "h100 sxm" in text_to_search: return "H100 SXM", "H100"
    if "h100 nvl" in text_to_search: return "H100 NVL", "H100"
    if "h100 pcie" in text_to_search or \
       (gpu_model_from_api.upper() == "H100" and "sxm" not in text_to_search and "nvl" not in text_to_search) or \
       ("rtx h100" in text_to_search and "sxm" not in text_to_search and "nvl" not in text_to_search):
        return "H100 PCIe", "H100"
    if "h200 sxm" in text_to_search: return "H200 SXM", "H200"
    if "gh200 sxm" in text_to_search : return "H200 SXM", "H200"
    if "h200 nvl" in text_to_search: return "H200 NVL", "H200"
    if "gh200 nvl" in text_to_search: return "H200 NVL", "H200"
    if ("gh200" in text_to_search or gpu_model_from_api.upper() == "H200") and \
       "sxm" not in text_to_search and "nvl" not in text_to_search :
        return "H200/GH200 (Other)", "H200"
    if "l40s" == text_to_search or "l40 s" == text_to_search or "nvidia l40s" in text_to_search:
        return "L40S", "L40S"
    # Fallback if specific variants are not matched but base chip is present
    if "h100" in text_to_search: return gpu_model_from_api, "H100" # Use original name as variant
    if "h200" in text_to_search: return gpu_model_from_api, "H200"
    return None, None

def extract_static_text_from_page(soup, text_keywords_for_id, default_value_to_return, exact_phrase_to_prefer=None):
    try:
        keywords_lower = text_keywords_for_id.lower(); candidate_tags = soup.find_all(['p', 'div', 'span', 'li', 'h1', 'h2', 'h3', 'h4', 'strong', 'b', 'td', 'th', 'dd', 'dt', 'a'])
        matched_elements_texts = []
        for tag in candidate_tags:
            tag_text = tag.get_text(separator=' ', strip=True); tag_text_lower = tag_text.lower()
            if keywords_lower in tag_text_lower:
                if exact_phrase_to_prefer and exact_phrase_to_prefer.lower() in tag_text_lower: return exact_phrase_to_prefer
                if default_value_to_return and default_value_to_return.strip().lower() in tag_text_lower and len(tag_text) < 350 : return tag_text
                if len(tag_text) < 350: matched_elements_texts.append(tag_text)
        if matched_elements_texts:
            if default_value_to_return:
                for mt in matched_elements_texts:
                    if default_value_to_return.strip().lower() in mt.lower(): return mt
            best_match = min(matched_elements_texts, key=len); return best_match
        return default_value_to_return
    except Exception: return default_value_to_return

def fetch_vast_ai_data():
    final_data_for_sheet = []
    provider_name_for_sheet = "Vast.ai"

    if VAST_AI_API_KEY == "YOUR_PLACEHOLDER_VAST_AI_KEY_HERE" or not VAST_AI_API_KEY:
        print("ERROR (Vast.ai): API Key not configured. Please update VAST_AI_API_KEY in handler or set as ENV VAR.")
        return []

    live_service_provided = STATIC_SERVICE_PROVIDED_VASTAI; live_region_info = STATIC_REGION_INFO_VASTAI
    live_storage_option = STATIC_STORAGE_OPTION_VASTAI; live_amount_of_storage = STATIC_AMOUNT_OF_STORAGE_VASTAI
    live_network_performance = STATIC_NETWORK_PERFORMANCE_VASTAI
    try:
        hp_resp = requests.get("https://vast.ai/", headers={"User-Agent": "Mozilla/5.0..."}, timeout=20)
        if hp_resp.status_code == 200:
            hp_soup = BeautifulSoup(hp_resp.text, "html.parser")
            live_service_provided = extract_static_text_from_page(hp_soup, "decentralized gpu", STATIC_SERVICE_PROVIDED_VASTAI, exact_phrase_to_prefer=STATIC_SERVICE_PROVIDED_VASTAI)
            live_region_info = extract_static_text_from_page(hp_soup, "datacenters worldwide", STATIC_REGION_INFO_VASTAI, exact_phrase_to_prefer=STATIC_REGION_INFO_VASTAI)
            live_storage_option = extract_static_text_from_page(hp_soup, "instance storage", STATIC_STORAGE_OPTION_VASTAI)
            live_amount_of_storage = extract_static_text_from_page(hp_soup, "terabytes of storage", STATIC_AMOUNT_OF_STORAGE_VASTAI)
            live_network_performance = extract_static_text_from_page(hp_soup, "internet speeds", STATIC_NETWORK_PERFORMANCE_VASTAI)
    except Exception as e_scrape: print(f"Vast.ai Handler: Could not scrape static info from homepage: {e_scrape}")

    api_url_with_key = f"{VAST_BUNDLES_URL}?api_key={VAST_AI_API_KEY}"
    print(f"Vast.ai Handler: Fetching bundles from {api_url_with_key.split('?')[0]}")
    all_api_offers_from_bundles = [] 

    try:
        response = requests.get(api_url_with_key, timeout=60)
        print(f"Vast.ai API (/bundles/) response status: {response.status_code}")
        if response.status_code != 200 or not response.text:
            print(f"Vast.ai API non-200 or empty response text from /bundles/: {response.text[:1000] if response.text else 'Empty Response Body'}")
        response.raise_for_status()
        api_data = response.json()
        
        # Based on your log: {'offers': [{'id': 19727625, ...
        if isinstance(api_data, dict) and "offers" in api_data:
            all_api_offers_from_bundles = api_data["offers"]
            print("Vast.ai Handler: Used 'offers' key from API response dictionary.")
        elif isinstance(api_data, list): 
            all_api_offers_from_bundles = api_data # Should not happen for /bundles/ if your log is correct
            print("Vast.ai Handler: Received a direct list from API (processing as bundles).")
        else:
            print(f"Vast.ai Handler: Unexpected API response from /bundles/. Expected dict with 'offers'. Got: {type(api_data)}")
            print(f"Vast.ai API Response Content (first 1000 chars): {str(api_data)[:1000]}")
            return []
            
    except requests.exceptions.RequestException as e_req:
        print(f"ERROR (Vast.ai) API request to /bundles/ failed: {e_req}"); return []
    except json.JSONDecodeError as e_json:
        print(f"ERROR (Vast.ai) parsing API JSON from /bundles/: {e_json}")
        if 'response' in locals() and response is not None: print(f"Vast.ai API raw response text (if JSON error): {response.text[:500]}")
        return []
    except Exception as e_api:
        print(f"ERROR (Vast.ai) during API processing for /bundles/: {e_api}"); import traceback; traceback.print_exc(); return []

    print(f"Found {len(all_api_offers_from_bundles)} total offers from Vast.ai API. Filtering for 1-GPU H100/H200/L40S variants...")
    
    base_1x_variant_offerings_vast = {}

    for offer in all_api_offers_from_bundles:
        # Field names from your log: 'gpu_name', 'num_gpus', 'dph_total', 'gpu_ram', 'disk_space', 'geolocation', 'id', 'reliability2', 'verified', 'cpu_ram', 'dlperf'
        gpu_name_api = offer.get("gpu_name", "N/A") 
        num_gpus_in_offer = int(offer.get("num_gpus", 0))
        
        if num_gpus_in_offer != 1: continue

        canonical_variant, base_chip_family = get_canonical_variant_and_base_chip_vast(gpu_name_api, 1)
        if not base_chip_family: continue
        
        instance_hourly_price_raw = offer.get("dph_total") 
        try:
            current_1x_hourly_price = float(instance_hourly_price_raw) if instance_hourly_price_raw is not None else None
        except (ValueError, TypeError): continue
        if current_1x_hourly_price is None: continue

        gpu_ram_mb = offer.get("gpu_ram", 0) 
        memory_gb = int(gpu_ram_mb / 1024) if gpu_ram_mb and gpu_ram_mb > 200 else int(gpu_ram_mb or 0)
        
        offer_id = offer.get("id", offer.get("bundle_id", gpu_name_api.replace(" ","_")))


        current_offering_for_1x_variant = {
            "gpu_id_provider": f"vast_{offer_id}",
            "display_name_provider": gpu_name_api,
            "base_chip_category_for_sheet": base_chip_family,
            "memory_gb_per_gpu": memory_gb,
            "secure_price_per_gpu_hourly": current_1x_hourly_price,
            "one_month_price_per_gpu_hourly": None, "three_month_price_per_gpu_hourly": None,
            "six_month_price_per_gpu_hourly": None, "twelve_month_price_per_gpu_hourly": None,
            "storage_gb": int(float(offer.get("disk_space", 0) or 0)),
            "actual_region_vast": offer.get("geolocation", "N/A"),
            "notes_features": f"VastID:{offer_id}, Reliability:{offer.get('reliability2', 'N/A')}, Verified:{offer.get('verified', 'N/A')}, HostRAM:{offer.get('cpu_ram',0)/1024 if offer.get('cpu_ram') else 'N/A'}GB, DLPerf:{offer.get('dlperf', 'N/A')}"
        }
        if canonical_variant not in base_1x_variant_offerings_vast or \
           current_1x_hourly_price < base_1x_variant_offerings_vast[canonical_variant].get("secure_price_per_gpu_hourly", float('inf')):
            base_1x_variant_offerings_vast[canonical_variant] = current_offering_for_1x_variant
    
    # Generate sheet rows
    for variant_name_key_cv, base_1x_details_cv in base_1x_variant_offerings_vast.items():
        notes_for_this_variant = [base_1x_details_cv.get("notes_features", "N/A")] # Initialize here

        base_info_for_unpivot = {
            "Provider Name": provider_name_for_sheet, "Service Provided": live_service_provided,
            "Currency": "USD",
            "Region": base_1x_details_cv.get("actual_region_vast", live_region_info),
            "GPU ID": base_1x_details_cv["gpu_id_provider"], 
            "GPU (H100 or H200 or L40S)": base_1x_details_cv["base_chip_category_for_sheet"],
            "Memory (GB)": base_1x_details_cv["memory_gb_per_gpu"], 
            "Display Name(GPU Type)": base_1x_details_cv["display_name_provider"],
            "GPU Variant Name": variant_name_key_cv, 
            "Storage Option": f"Instance Disk: {base_1x_details_cv.get('storage_gb', 'N/A')}GB" if base_1x_details_cv.get('storage_gb') else live_storage_option,
            "Amount of Storage": f"{base_1x_details_cv.get('storage_gb', 'N/A')}GB available" if base_1x_details_cv.get('storage_gb') else live_amount_of_storage,
            "Network Performance (Gbps)": live_network_performance,
            "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
            "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
            "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
            "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
            # "Notes / Features" will be assembled per N-chip calculation below
        }
        base_1x_hourly_for_calc = base_1x_details_cv["secure_price_per_gpu_hourly"]
        eff_hr_for_all_periods = base_1x_hourly_for_calc 

        for num_chips_to_calc in [1, 2, 4, 8]:
            total_hourly_val = eff_hr_for_all_periods * num_chips_to_calc
            
            current_row_notes_list = notes_for_this_variant.copy() # Use notes for this variant
            if num_chips_to_calc > 1:
                current_row_notes_list.append(f"{num_chips_to_calc}x price calculated from 1x Vast.ai offering.")

            unpivoted_row_base_with_notes = { 
                **base_info_for_unpivot, 
                "Number of Chips": num_chips_to_calc,
                "Notes / Features": ", ".join(filter(None, current_row_notes_list)) # Corrected
            }
            
            row_hourly_data = unpivoted_row_base_with_notes.copy()
            row_hourly_data["Period"] = "Per Hour"
            row_hourly_data["Total Price ($)"] = round(total_hourly_val, 2) if total_hourly_val is not None else "N/A"
            row_hourly_data["Effective Hourly Rate ($/hr)"] = round(eff_hr_for_all_periods, 2) if eff_hr_for_all_periods is not None else "N/A"
            final_data_for_sheet.append(row_hourly_data)

            total_6_months_val_numeric = (eff_hr_for_all_periods * HOURS_IN_MONTH * 6) * num_chips_to_calc
            total_n_chip_hourly_for_6mo = eff_hr_for_all_periods * num_chips_to_calc
            total_6_months_price_str = f"{round(total_n_chip_hourly_for_6mo, 2)} ({round(total_6_months_val_numeric, 2)})"
            row_6_months_data = unpivoted_row_base_with_notes.copy()
            row_6_months_data["Period"] = "Per 6 Months"; row_6_months_data["Total Price ($)"] = total_6_months_price_str
            row_6_months_data["Effective Hourly Rate ($/hr)"] = round(eff_hr_for_all_periods, 2) if eff_hr_for_all_periods is not None else "N/A"
            final_data_for_sheet.append(row_6_months_data)

            total_yearly_val_numeric = (eff_hr_for_all_periods * HOURS_IN_MONTH * 12) * num_chips_to_calc
            total_n_chip_hourly_for_yearly = eff_hr_for_all_periods * num_chips_to_calc
            total_yearly_price_str = f"{round(total_n_chip_hourly_for_yearly, 2)} ({round(total_yearly_val_numeric, 2)})"
            row_yearly_data = unpivoted_row_base_with_notes.copy()
            row_yearly_data["Period"] = "Per Year"; row_yearly_data["Total Price ($)"] = total_yearly_price_str
            row_yearly_data["Effective Hourly Rate ($/hr)"] = round(eff_hr_for_all_periods, 2) if eff_hr_for_all_periods is not None else "N/A"
            final_data_for_sheet.append(row_yearly_data)
            
    if final_data_for_sheet:
        num_base_variants = len(base_1x_variant_offerings_vast)
        print(f"Vast.ai: Processed {num_base_variants} base 1-GPU variants, generating {len(final_data_for_sheet)} sheet rows.")
    else:
        print(f"Vast.ai: No 1-GPU H100/H200/L40S offerings found via API based on current filters.")
    return final_data_for_sheet

# --- (Optional) Test call if you run this file directly ---
if __name__ == '__main__':
    print("Testing Vast.ai Handler (using /bundles/ GET, expecting dict with 'offers')...")
    if VAST_AI_API_KEY == "YOUR_PLACEHOLDER_VAST_AI_KEY_HERE" or not VAST_AI_API_KEY :
        print("CRITICAL: Please set VAST_AI_API_KEY env var or update placeholder in script for local test.")
    else:
        try:
            processed_data = fetch_vast_ai_data()
            if processed_data:
                print(f"\nSample of processed Vast.ai data (first {min(6, len(processed_data))} of {len(processed_data)} rows):")
                for i, row_data in enumerate(processed_data):
                    if i >= 6: break; print(f"Row {i+1}: {row_data}")
            else: print("No data processed by fetch_vast_ai_data.")
        except Exception as e: print(f"Error during direct test of vast_ai_handler: {e}"); import traceback; traceback.print_exc()