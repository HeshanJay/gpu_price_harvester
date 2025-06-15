# providers/coreweave_handler.py
import requests
from bs4 import BeautifulSoup
import re

COREWEAVE_PRICING_URL = "https://www.coreweave.com/pricing"
HOURS_IN_MONTH = 730

STATIC_SERVICE_PROVIDED_COREWEAVE = "CoreWeave Specialized Cloud"
STATIC_REGION_INFO_COREWEAVE = "Multiple US Data Centers (e.g., LAS1, ORD1, EWR2)"
STATIC_STORAGE_OPTION_COREWEAVE = "NFS, Block, Object Storage (Details on site)"
STATIC_AMOUNT_OF_STORAGE_COREWEAVE = "Varies by configuration"
STATIC_NETWORK_PERFORMANCE_COREWEAVE = "High-Performance Fabric"

def get_canonical_variant_and_base_chip_coreweave(gpu_name_on_page):
    text_to_search = str(gpu_name_on_page).lower()
    if "h100" in text_to_search:
        family = "H100"
        if "sxm" in text_to_search or "hgx h100" in text_to_search: variant = "H100 SXM/HGX" # Grouping HGX as SXM-like
        elif "nvl" in text_to_search: variant = "H100 NVL"
        elif "pcie" in text_to_search: variant = "H100 PCIe"
        else: variant = gpu_name_on_page
        return variant, family
    if "l40s" in text_to_search or "l40 s" in text_to_search:
        return "L40S", "L40S"
    if "h200" in text_to_search or "gh200" in text_to_search:
        family = "H200"
        if "sxm" in text_to_search or "hgx h200" in text_to_search: variant = "H200 SXM/HGX"
        elif "nvl" in text_to_search: variant = "H200 NVL"
        else: variant = gpu_name_on_page # e.g., "NVIDIA GH200" if it's a single unit like Grace Hopper
        return variant, family
    return None, None

def extract_static_text_from_coreweave_page(soup, text_keywords_for_id, default_value_to_return, exact_phrase_to_prefer=None):
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
            best_match = min(matched_elements_texts, key=len);
            # print(f"CoreWeave Handler: Static text for '{text_keywords_for_id}': '{best_match}'")
            return best_match
        # print(f"CoreWeave Handler: Static text for '{text_keywords_for_id}' not found, using default: '{default_value_to_return}'")
        return default_value_to_return
    except Exception as e:
        # print(f"CoreWeave Handler: Error extracting static text for '{text_keywords_for_id}': {e}")
        return default_value_to_return


def parse_price_coreweave(price_str):
    if not price_str: return None
    match = re.search(r'([\d\.]+)', str(price_str).replace('$', '').replace('/hr', '').strip())
    if match:
        try: return float(match.group(1))
        except ValueError: return None
    return None

def parse_memory_coreweave(memory_str): # Assumes VRAM per GPU
    if not memory_str: return 0
    match = re.search(r'(\d+)', str(memory_str).strip()) # Just find the number
    if match:
        try: return int(match.group(1))
        except ValueError: return 0
    return 0

def parse_gpu_count_coreweave(count_str):
    if not count_str: return 1 # Default to 1 if not specified
    match = re.search(r'(\d+)', str(count_str).strip())
    if match:
        try: return int(match.group(1))
        except ValueError: return 1
    return 1


def fetch_coreweave_data(soup):
    final_data_for_sheet = []
    provider_name_for_sheet = "CoreWeave"

    live_service_provided = extract_static_text_from_coreweave_page(soup, "specialized cloud for compute", STATIC_SERVICE_PROVIDED_COREWEAVE, exact_phrase_to_prefer=STATIC_SERVICE_PROVIDED_COREWEAVE)
    live_region_info = extract_static_text_from_coreweave_page(soup, "data center locations", STATIC_REGION_INFO_COREWEAVE)
    live_storage_option = extract_static_text_from_coreweave_page(soup, "storage solutions like NFS", STATIC_STORAGE_OPTION_COREWEAVE)
    live_amount_of_storage = extract_static_text_from_coreweave_page(soup, "storage capacity", STATIC_AMOUNT_OF_STORAGE_COREWEAVE)
    live_network_performance = extract_static_text_from_coreweave_page(soup, "network backbone", STATIC_NETWORK_PERFORMANCE_COREWEAVE)

    print(f"CoreWeave Handler: Processing pricing page content...")

    # Find all rows that represent GPU offerings
    # The class "table-row" and "w-dyn-item" seems common to all product rows in the provided HTML.
    # We need a more specific selector for GPU rows, e.g., by checking if they are inside a "gpu-pricing" table.
    # Let's assume relevant rows are inside a div with class 'table-v2-body' and are 'table-row w-dyn-item'
    
    # From your HTML: class="table-v2-body w-dyn-list" contains the items
    # Each item: class="table-row w-dyn-item [some-category-pricing]"
    # We are interested in 'gpu-pricing-and-kubernetes-gpu-pricing' and 'kubernetes-gpu-pricing' that might contain GPUs.
    
    gpu_rows = []
    pricing_tables_body = soup.find_all('div', class_='table-v2-body')
    for body in pricing_tables_body:
        # Look for rows that are likely GPU compute instances rather than storage or networking
        # This relies on CoreWeave's naming conventions within the "GPU Model" column
        possible_gpu_rows = body.find_all('div', role='listitem', class_='table-row')
        for row in possible_gpu_rows:
            name_cell = row.find('div', class_='table-v2-cell--name')
            if name_cell and name_cell.find('h3'):
                gpu_name_test = name_cell.find('h3').get_text(strip=True).lower()
                if "nvidia" in gpu_name_test or any(gpu in gpu_name_test for gpu in ["h100", "l40s", "h200", "gh200", "a100", "rtx"]): # Broad check for NVIDIA GPUs
                    gpu_rows.append(row)
    
    print(f"CoreWeave Handler: Found {len(gpu_rows)} potential GPU pricing rows to analyze.")
    processed_gpu_variants = set() # To avoid duplicate base variants if listed multiple ways

    for row in gpu_rows:
        cells = row.find('div', class_='table-grid').find_all('div', class_='table-v2-cell', recursive=False)
        
        if len(cells) < 7: # Expect at least 7 cells for GPU Model to Price
            # print(f"CoreWeave Handler: Skipping row, not enough cells: {[c.get_text(strip=True) for c in cells]}")
            continue

        try:
            gpu_name_on_page = cells[0].find('h3', class_='table-model-name').get_text(strip=True) if cells[0].find('h3') else "N/A"
            gpu_count_scraped = parse_gpu_count_coreweave(cells[1].get_text(strip=True))
            memory_gb_scraped_per_gpu = parse_memory_coreweave(cells[2].get_text(strip=True)) # This is VRAM per GPU
            # vcpus_scraped = cells[3].get_text(strip=True) # For notes
            # system_ram_scraped = cells[4].get_text(strip=True) # For notes
            # local_storage_scraped = cells[5].get_text(strip=True) # For notes
            instance_price_str = cells[6].get_text(strip=True)
            instance_hourly_price_num = parse_price_coreweave(instance_price_str)

            if instance_hourly_price_num is None:
                # print(f"CoreWeave Handler: Could not parse price for {gpu_name_on_page} ('{instance_price_str}')")
                continue

            # Calculate per-GPU price if the listed price is for multiple GPUs
            base_1x_hourly_price_num = instance_hourly_price_num
            if gpu_count_scraped > 1:
                base_1x_hourly_price_num = instance_hourly_price_num / gpu_count_scraped
            
            canonical_variant, base_chip_family = get_canonical_variant_and_base_chip_coreweave(gpu_name_on_page)
            
            if not base_chip_family or base_chip_family not in ["H100", "H200", "L40S"]:
                # print(f"CoreWeave Handler: Skipped non-target GPU family: {gpu_name_on_page} -> {base_chip_family}")
                continue
            
            # Ensure we only process each unique canonical_variant once as a base
            if canonical_variant in processed_gpu_variants:
                # Optional: Add logic to update if this one is cheaper for the same variant
                continue
            processed_gpu_variants.add(canonical_variant)


            # CoreWeave typically doesn't list these on the main pricing page
            one_month_commit_hr = None; three_month_commit_hr = None; 
            six_month_commit_hr = None; twelve_month_commit_hr = None

            # GPU ID: Use a combination as specific SKU isn't always obvious from public page
            gpu_id_coreweave = f"coreweave_{canonical_variant.replace(' ','_').replace('/','_')}" if canonical_variant else f"coreweave_{gpu_name_on_page.replace(' ','_').replace('/','_')}"

            base_info_for_row = {
                "Provider Name": provider_name_for_sheet,
                "Currency": "USD",
                "Service Provided": live_service_provided, "Region": live_region_info, # CoreWeave regions might need better scraping
                "GPU ID": gpu_id_coreweave, 
                "GPU (H100 or H200 or L40S)": base_chip_family,
                "Memory (GB)": memory_gb_scraped_per_gpu, # This is VRAM per GPU
                "Display Name(GPU Type)": gpu_name_on_page,
                "GPU Variant Name": canonical_variant,
                "Storage Option": live_storage_option,
                "Amount of Storage": live_amount_of_storage,
                "Network Performance (Gbps)": live_network_performance,
                "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
                "Notes / Features": f"CoreWeave Offering: {gpu_name_on_page} ({gpu_count_scraped}x GPU config on site, price normalized to 1x GPU)" if gpu_count_scraped > 1 else f"CoreWeave Offering: {gpu_name_on_page}"
            }

            eff_hr_all_periods_cw = base_1x_hourly_price_num # No public tiered discounts from CoreWeave for this calc

            for num_chips_to_calc in [1, 2, 4, 8]:
                total_hourly_val = eff_hr_all_periods_cw * num_chips_to_calc
                current_row_data = {**base_info_for_row, "Number of Chips": num_chips_to_calc}
                
                row_hourly = current_row_data.copy()
                row_hourly["Period"] = "Per Hour"
                row_hourly["Total Price ($)"] = round(total_hourly_val, 2) if total_hourly_val is not None else "N/A"
                row_hourly["Effective Hourly Rate ($/hr)"] = round(eff_hr_all_periods_cw, 2) if eff_hr_all_periods_cw is not None else "N/A"
                final_data_for_sheet.append(row_hourly)

                total_6mo_val_numeric = (eff_hr_all_periods_cw * HOURS_IN_MONTH * 6) * num_chips_to_calc
                total_n_chip_hourly_for_6mo = eff_hr_all_periods_cw * num_chips_to_calc # N-chip hourly equivalent
                price_6_months_str = f"{round(total_n_chip_hourly_for_6mo, 2)} ({round(total_6mo_val_numeric, 2)})"
                row_6mo = current_row_data.copy()
                row_6mo["Period"] = "Per 6 Months"; row_6mo["Total Price ($)"] = price_6_months_str
                row_6mo["Effective Hourly Rate ($/hr)"] = round(eff_hr_all_periods_cw, 2) if eff_hr_all_periods_cw is not None else "N/A"
                final_data_for_sheet.append(row_6mo)

                total_yr_val_numeric = (eff_hr_all_periods_cw * HOURS_IN_MONTH * 12) * num_chips_to_calc
                total_n_chip_hourly_for_yearly = eff_hr_all_periods_cw * num_chips_to_calc # N-chip hourly equivalent
                price_yr_str = f"{round(total_n_chip_hourly_for_yearly, 2)} ({round(total_yr_val_numeric, 2)})"
                row_yr = current_row_data.copy()
                row_yr["Period"] = "Per Year"; row_yr["Total Price ($)"] = price_yr_str
                row_yr["Effective Hourly Rate ($/hr)"] = round(eff_hr_all_periods_cw, 2) if eff_hr_all_periods_cw is not None else "N/A"
                final_data_for_sheet.append(row_yr)
        
        except Exception as e_item_proc:
            print(f"CoreWeave Handler: Error processing one item on page: {e_item_proc}")
            # import traceback; traceback.print_exc() # Uncomment for detailed debug of item processing
            continue
    
    if final_data_for_sheet:
        num_base_variants = len(set(row["GPU Variant Name"] for row in final_data_for_sheet if row["Number of Chips"] == 1 and row["Period"] == "Per Hour"))
        print(f"CoreWeave: Processed and unpivoted data for {num_base_variants} base 1-GPU variants, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        print(f"CoreWeave: No 1-GPU offerings found for H100, H200, L40S from scraping.")
    return final_data_for_sheet

if __name__ == '__main__':
    print(f"Testing CoreWeave Handler. Fetching {COREWEAVE_PRICING_URL}...")
    page_content_to_parse = None
    # Option to load from local file for faster iteration during development
    # html_file_path_abs = os.path.join(os.path.dirname(__file__), '..', 'GPU Cloud Pricing _ CoreWeave.html') # If main.py is parent
    html_file_path_abs = 'GPU Cloud Pricing _ CoreWeave.html' # If HTML is in same 'providers' folder
    
    if os.path.exists(html_file_path_abs):
        with open(html_file_path_abs, "r", encoding="utf-8") as f:
            page_content_to_parse = f.read()
        print(f"CoreWeave Handler: Testing with local HTML file: {html_file_path_abs}")
    else:
        print(f"Local HTML file '{html_file_path_abs}' not found. Fetching live page for testing...")
        try:
            response_test = requests.get(COREWEAVE_PRICING_URL, headers={"User-Agent": "Mozilla/5.0..."}, timeout=60)
            response_test.raise_for_status()
            page_content_to_parse = response_test.text
        except Exception as e:
            print(f"Error fetching live CoreWeave page: {e}")

    if page_content_to_parse:
        soup_test = BeautifulSoup(page_content_to_parse, "html.parser")
        processed_data = fetch_coreweave_data(soup_test)
        if processed_data:
            print(f"\nSample of processed CoreWeave data (first {min(12, len(processed_data))} of {len(processed_data)} rows):")
            for i, row_data in enumerate(processed_data):
                if i >= 12: break
                print(f"Row {i+1}:")
                for key, value in row_data.items():
                    print(f"  {key}: {value}")
                print("-" * 20)
        else:
            print("No data processed by fetch_coreweave_data.")
    else:
        print("Could not load page content for CoreWeave testing.")