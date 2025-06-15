# providers/genesiscloud_handler.py
import requests
from bs4 import BeautifulSoup
import re
import os

GENESISCLOUD_PRICING_URL = "https://www.genesiscloud.com/pricing"
HOURS_IN_MONTH = 730

# Static text defaults for Genesis Cloud
STATIC_SERVICE_PROVIDED_GENESIS = "Genesis Cloud - Green GPU Cloud"
STATIC_REGION_INFO_GENESIS = "Multiple Global Locations (e.g., Norway, USA, Canada, EU)" # From their site
STATIC_STORAGE_OPTION_GENESIS = "NVMe SSD based (Details within instance config)"
STATIC_AMOUNT_OF_STORAGE_GENESIS = "Varies by instance configuration"
STATIC_NETWORK_PERFORMANCE_GENESIS = "High-speed networking (Details within instance config)"

def get_canonical_variant_and_base_chip_genesis(gpu_name_on_page):
    text_to_search = str(gpu_name_on_page).lower()
    # Genesis Cloud examples: "NVIDIA HGX H100 On-Demand", "NVIDIA HGX H200 On-Demand"
    if "h100" in text_to_search:
        family = "H100"
        # They usually list HGX H100, which implies SXM-like connectivity
        if "hgx h100" in text_to_search or "h100 sxm" in text_to_search : variant = "H100 HGX/SXM"
        elif "h100 pcie" in text_to_search : variant = "H100 PCIe"
        else: variant = gpu_name_on_page # Fallback
        return variant, family
    if "l40s" in text_to_search: # Assuming they might offer L40S
        return "L40S", "L40S"
    if "h200" in text_to_search or "gh200" in text_to_search:
        family = "H200"
        if "hgx h200" in text_to_search: variant = "H200 HGX/SXM"
        # Add other H200 variants if they list them specifically
        else: variant = gpu_name_on_page
        return variant, family
    return None, None

def extract_static_text_from_genesis_page(soup, text_keywords_for_id, default_value_to_return, exact_phrase_to_prefer=None):
    # This function can be similar to the one in other handlers
    # Keywords will need to be tuned for genesiscloud.com
    try:
        keywords_lower = text_keywords_for_id.lower()
        candidate_tags = soup.find_all(['p', 'div', 'span', 'li', 'h1', 'h2', 'h3', 'h4', 'strong', 'b', 'td', 'th'])
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


def parse_price_genesis(price_str):
    if not price_str: return None
    # Example: "$ 2.19h" or "$3.15/h"
    match = re.search(r'([\d\.]+)', str(price_str).replace('$', '').replace('h', '').replace('/h', '').strip())
    if match:
        try: return float(match.group(1))
        except ValueError: return None
    return None

def parse_gpu_details_from_description(description_text):
    # Example: "- 8x NVIDIA H100 GPU 80 GB" or "- 8x NVIDIA H200 GPU 141 GB"
    gpus = 1 # Default
    vram = 0 # Default

    gpu_match = re.search(r"(\d+)x\s+NVIDIA\s+([A-Z0-9]+)\s+GPU\s+(\d+)\s*GB", description_text, re.IGNORECASE)
    if gpu_match:
        try:
            gpus = int(gpu_match.group(1))
            # gpu_model_in_desc = gpu_match.group(2) # e.g., H100, H200
            vram = int(gpu_match.group(3))
        except ValueError:
            pass # Keep defaults if parsing fails
    elif "NVIDIA L40S" in description_text: # Handle L40S if mentioned differently
        vram_match = re.search(r"L40S\s+(\d+)\s*GB", description_text, re.IGNORECASE)
        if vram_match : vram = int(vram_match.group(1))
        else: vram = 48 # Default L40S VRAM
        gpus = 1 # Assume L40S is usually listed per GPU if not in Nx config
    
    # If the description only mentions a single GPU without "Nx"
    elif "NVIDIA H100 GPU" in description_text and "x " not in description_text.split("NVIDIA H100 GPU")[0][-3:]:
        gpus = 1
        vram_match = re.search(r"H100 GPU\s+(\d+)\s*GB", description_text, re.IGNORECASE)
        if vram_match: vram = int(vram_match.group(1))
        else: vram = 80
    elif "NVIDIA H200 GPU" in description_text and "x " not in description_text.split("NVIDIA H200 GPU")[0][-3:]:
        gpus = 1
        vram_match = re.search(r"H200 GPU\s+(\d+)\s*GB", description_text, re.IGNORECASE)
        if vram_match: vram = int(vram_match.group(1))
        else: vram = 141


    return gpus, vram


def fetch_genesiscloud_data(soup):
    final_data_for_sheet = []
    provider_name_for_sheet = "Genesis Cloud"

    live_service_provided = extract_static_text_from_genesis_page(soup, "green gpu cloud", STATIC_SERVICE_PROVIDED_GENESIS, exact_phrase_to_prefer=STATIC_SERVICE_PROVIDED_GENESIS)
    live_region_info = extract_static_text_from_genesis_page(soup, "data center locations", STATIC_REGION_INFO_GENESIS) # Will be overridden by specific item if found
    live_storage_option = extract_static_text_from_genesis_page(soup, "storage solutions", STATIC_STORAGE_OPTION_GENESIS)
    live_amount_of_storage = extract_static_text_from_genesis_page(soup, "NVMe SSD", STATIC_AMOUNT_OF_STORAGE_GENESIS) # More specific keyword
    live_network_performance = extract_static_text_from_genesis_page(soup, "InfiniBand Networking", STATIC_NETWORK_PERFORMANCE_GENESIS)

    print(f"Genesis Cloud Handler: Processing pricing page content...")

    # Find all pricing items based on the provided HTML structure
    # Each item is within <div class="pricing-two-price-item">
    pricing_items = soup.find_all('div', class_='pricing-two-price-item')
    print(f"Genesis Cloud Handler: Found {len(pricing_items)} potential pricing items.")

    processed_1x_equivalent_variants = {}

    for item in pricing_items:
        try:
            title_element = item.find('div', class_='heading-three-ninne pricing-two-price-title')
            gpu_name_on_page = title_element.find('a').get_text(strip=True) if title_element and title_element.find('a') else "N/A"
            
            price_text_element = item.find('div', class_='pricing-two-price-text')
            per_gpu_hourly_price_num = parse_price_genesis(price_text_element.get_text(strip=True)) if price_text_element else None

            if per_gpu_hourly_price_num is None:
                # print(f"Genesis Cloud: Price not found/parsed for: {gpu_name_on_page}")
                continue

            description_p = item.find('p', class_='pricing-two-price-content')
            description_text = description_p.get_text(separator='\n', strip=True) if description_p else ""
            
            # Extract GPU count and VRAM per GPU from description
            # The price given ($2.19h, $3.15/h) IS PER GPU, even for 8x nodes.
            # So, num_gpus_in_config is for information, base price is already per GPU.
            num_gpus_in_config, memory_gb_per_gpu = parse_gpu_details_from_description(description_text)

            if memory_gb_per_gpu == 0: # If VRAM couldn't be parsed, try to infer
                if "h100" in gpu_name_on_page.lower(): memory_gb_per_gpu = 80
                elif "h200" in gpu_name_on_page.lower(): memory_gb_per_gpu = 141
                elif "l40s" in gpu_name_on_page.lower(): memory_gb_per_gpu = 48


            canonical_variant, base_chip_family = get_canonical_variant_and_base_chip_genesis(gpu_name_on_page)
            if not base_chip_family or base_chip_family not in ["H100", "H200", "L40S"]:
                # print(f"Genesis Cloud: Skipped non-target GPU: {gpu_name_on_page} -> {base_chip_family}")
                continue
            
            # Store the best (cheapest) price for this canonical variant
            # (Genesis page lists per-GPU prices directly, so less need to compare if multiple configs of same GPU type)
            if canonical_variant not in processed_1x_equivalent_variants or \
               per_gpu_hourly_price_num < processed_1x_equivalent_variants[canonical_variant].get("base_1x_hourly_price_num", float('inf')):
                
                region_text_from_item = live_region_info # Default
                if description_p:
                    strong_tag = description_p.find('strong', string=re.compile("Data center locations", re.IGNORECASE))
                    if strong_tag and strong_tag.next_sibling:
                        region_text_from_item = str(strong_tag.next_sibling).split('<br>')[0].strip()
                        if not region_text_from_item or region_text_from_item.startswith('-'): # If it captured part of the list
                             region_text_from_item = description_p.get_text().split("Data center locations:")[1].split("\n")[0].strip() if "Data center locations:" in description_p.get_text() else live_region_info


                processed_1x_equivalent_variants[canonical_variant] = {
                    "gpu_name_on_page": gpu_name_on_page,
                    "base_1x_hourly_price_num": per_gpu_hourly_price_num, # This is already per GPU
                    "memory_gb_val": memory_gb_per_gpu,
                    "base_chip_family": base_chip_family,
                    "gpu_id_coreweave": f"genesis_{canonical_variant.replace(' ','_').replace('/','_').replace('(','').replace(')','')}", # Using coreweave naming for consistency
                    "region_info_item": region_text_from_item,
                    "notes_features": f"Genesis Offering: {gpu_name_on_page}. Node config example: {num_gpus_in_config}x GPUs. Full Description: {description_text[:100]}..."
                }
        except Exception as e_item_proc:
            print(f"Genesis Cloud Handler: Error processing an item: {e_item_proc}")
            # import traceback; traceback.print_exc() # Uncomment for full trace
            continue
            
    if not processed_1x_equivalent_variants:
        print("Genesis Cloud Handler: No valid H100/H200/L40S offerings were processed from the page.")
        return []

    for variant_name_key, details in processed_1x_equivalent_variants.items():
        base_1x_hourly_for_calc = details["base_1x_hourly_price_num"]
        eff_hr_for_all_periods = base_1x_hourly_for_calc # Genesis lists on-demand per GPU hourly

        base_info_for_unpivot = {
            "Provider Name": provider_name_for_sheet,
            "Currency": "USD",
            "Service Provided": live_service_provided, 
            "Region": details.get("region_info_item", live_region_info), # Use specific if scraped
            "GPU ID": details["gpu_id_coreweave"], 
            "GPU (H100 or H200 or L40S)": details["base_chip_family"],
            "Memory (GB)": details["memory_gb_val"],
            "Display Name(GPU Type)": details["gpu_name_on_page"], 
            "GPU Variant Name": variant_name_key, 
            "Storage Option": live_storage_option, "Amount of Storage": live_amount_of_storage,
            "Network Performance (Gbps)": live_network_performance,
            "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A", # Genesis usually by contract
            "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
            "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
            "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
            "Notes / Features": details["notes_features"]
        }

        for num_chips_to_calc in [1, 2, 4, 8]:
            total_hourly_val = eff_hr_for_all_periods * num_chips_to_calc
            current_row_data = {**base_info_for_unpivot, "Number of Chips": num_chips_to_calc}
            
            row_hourly = current_row_data.copy()
            row_hourly["Period"] = "Per Hour"
            row_hourly["Total Price ($)"] = round(total_hourly_val, 2) if total_hourly_val is not None else "N/A"
            row_hourly["Effective Hourly Rate ($/hr)"] = round(eff_hr_for_all_periods, 2) if eff_hr_for_all_periods is not None else "N/A"
            final_data_for_sheet.append(row_hourly)

            total_6mo_val_numeric = (eff_hr_for_all_periods * HOURS_IN_MONTH * 6) * num_chips_to_calc
            total_n_chip_hourly_for_6mo = eff_hr_for_all_periods * num_chips_to_calc
            price_6_months_str = f"{round(total_n_chip_hourly_for_6mo, 2)} ({round(total_6mo_val_numeric, 2)})"
            row_6mo = current_row_data.copy()
            row_6mo["Period"] = "Per 6 Months"; row_6mo["Total Price ($)"] = price_6_months_str
            row_6mo["Effective Hourly Rate ($/hr)"] = round(eff_hr_for_all_periods, 2) if eff_hr_for_all_periods is not None else "N/A"
            final_data_for_sheet.append(row_6mo)

            total_yr_val_numeric = (eff_hr_for_all_periods * HOURS_IN_MONTH * 12) * num_chips_to_calc
            total_n_chip_hourly_for_yearly = eff_hr_for_all_periods * num_chips_to_calc
            price_yr_str = f"{round(total_n_chip_hourly_for_yearly, 2)} ({round(total_yr_val_numeric, 2)})"
            row_yr = current_row_data.copy()
            row_yr["Period"] = "Per Year"; row_yr["Total Price ($)"] = price_yr_str
            row_yr["Effective Hourly Rate ($/hr)"] = round(eff_hr_for_all_periods, 2) if eff_hr_for_all_periods is not None else "N/A"
            final_data_for_sheet.append(row_yr)
            
    if final_data_for_sheet:
        num_base_variants = len(processed_1x_equivalent_variants)
        print(f"Genesis Cloud: Processed and unpivoted data for {num_base_variants} base 1-GPU equivalent variants, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        print(f"Genesis Cloud: No 1-GPU equivalent offerings found for H100, H200, L40S from scraping.")
    return final_data_for_sheet

if __name__ == '__main__':
    print(f"Testing Genesis Cloud Handler. Fetching {GENESISCLOUD_PRICING_URL}...")
    page_content_to_parse = None
    script_dir = os.path.dirname(__file__)
    html_file_path_abs = os.path.join(script_dir, '..', 'GPU Cloud Pricing_ NVIDIA H100, H200, B200, GB200 GPU Rates - Genesis Cloud.html') 
    
    if os.path.exists(html_file_path_abs):
        with open(html_file_path_abs, "r", encoding="utf-8") as f:
            page_content_to_parse = f.read()
        print(f"Genesis Cloud Handler: Testing with local HTML file: {html_file_path_abs}")
    else:
        print(f"Local HTML file '{html_file_path_abs}' not found. Fetching live page for testing...")
        try:
            response_test = requests.get(GENESISCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0..."}, timeout=60)
            response_test.raise_for_status()
            page_content_to_parse = response_test.text
        except Exception as e:
            print(f"Error fetching live Genesis Cloud page: {e}")

    if page_content_to_parse:
        soup_test = BeautifulSoup(page_content_to_parse, "html.parser")
        processed_data = fetch_genesiscloud_data(soup_test)
        if processed_data:
            print(f"\nSample of processed Genesis Cloud data (first {min(12, len(processed_data))} of {len(processed_data)} rows):")
            for i, row_data in enumerate(processed_data):
                if i >= 12: break
                print(f"Row {i+1}:")
                for key, value in row_data.items():
                    print(f"  {key}: {value}")
                print("-" * 20)
        else:
            print("No data processed by fetch_genesiscloud_data.")
    else:
        print("Could not load page content for Genesis Cloud testing.")