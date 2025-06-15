# providers/lambda_labs_handler.py
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone # Not strictly needed here, but often useful

# Configuration
LAMBDALABS_PRICING_URL = "https://lambda.ai/service/gpu-cloud"
HOURS_IN_MONTH = 730 # Consistent with other handlers

# Static information for Lambda Labs
STATIC_PROVIDER_NAME = "Lambda Labs"
STATIC_SERVICE_PROVIDED = "Lambda Cloud GPU Instances"
# Based on Lambda Labs FAQ: "Lambda Cloud runs in multiple US regions, with our primary data centers located in Texas, California, and Utah."
STATIC_REGION_INFO = "US (TX, CA, UT)"
STATIC_STORAGE_OPTION_LAMBDA = "Local NVMe SSD" # Specific storage amount will be per instance
STATIC_NETWORK_PERFORMANCE_LAMBDA = "High-Speed Fabric (InfiniBand/Ethernet)" # General term

def parse_price_lambda(price_str):
    """
    Parses price string like "$2.99 / GPU / hr" into a float.
    Returns None if parsing fails or price is "CONTACT SALES".
    """
    if not price_str or "contact sales" in price_str.lower():
        return None
    match = re.search(r"[\$€£]?\s*(\d+\.?\d*)", price_str.replace(',', ''))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def parse_memory_lambda(memory_str):
    """
    Parses memory string like "80 GB" or "432 GiB" into an integer (GB).
    Converts GiB to GB (1 GiB = 1.07374 GB, approx for simplicity or exact).
    For simplicity here, we'll treat GiB as GB if no specific conversion factor is critical.
    Let's assume numbers are effectively GB or can be treated as such for this column.
    """
    if not memory_str:
        return 0
    match = re.search(r"(\d+)\s*(G[iB]B|T[iB]B)", memory_str, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        unit = match.group(2).upper()
        if "TIB" in unit or "TB" in unit: # Convert TB to GB
             return val * 1024 # Or 1000 if preferred, 1024 is common for TiB->GiB->MiB
        return val # Assuming GiB is close enough to GB for this column's purpose
    return 0

def parse_gpu_instance_name(gpu_name_str):
    """
    Parses GPU instance name like "On-demand 8x NVIDIA H100 SXM"
    Returns: (number_of_chips, base_gpu_model_name, full_display_name)
    Example: (8, "NVIDIA H100 SXM", "On-demand 8x NVIDIA H100 SXM")
    """
    gpu_name_str = gpu_name_str.strip()
    num_chips = 1 # Default
    base_gpu_model = gpu_name_str
    
    # Try to find "Nx" pattern
    match_chips = re.match(r"(?:On-demand\s+|Reserved\s+)?(\d+)x\s*(.*)", gpu_name_str, re.IGNORECASE)
    if match_chips:
        num_chips = int(match_chips.group(1))
        base_gpu_model = match_chips.group(2).strip()
    else: # Handle cases like "1x NVIDIA GH200" or just "NVIDIA GH200" if 1x is implied
        if "NVIDIA GH200" in gpu_name_str.upper() and not match_chips: # GH200 is usually single
            num_chips = 1
            # Attempt to extract just "NVIDIA GH200"
            model_match = re.search(r"(NVIDIA\s*GH200(?: Grace Hopper Superchip)?)", gpu_name_str, re.IGNORECASE)
            if model_match:
                base_gpu_model = model_match.group(1).strip()
        # Could add more specific 1x patterns if needed
        
    return num_chips, base_gpu_model, gpu_name_str # Return original full string as display_name

def get_canonical_variant_and_base_chip_lambda(base_gpu_model_name):
    """
    Determines the canonical GPU variant name and the base chip family (H100, H200, L40S).
    Input: "NVIDIA H100 SXM", "NVIDIA GH200", "NVIDIA L40S"
    Output: (gpu_variant_name, gpu_family) or (None, None)
    """
    text_to_search = base_gpu_model_name.lower()
    family = None
    variant = base_gpu_model_name # Default variant to the input if no specific match

    if "h100" in text_to_search:
        family = "H100"
        if "sxm" in text_to_search:
            variant = "H100 SXM"
        elif "pcie" in text_to_search:
            variant = "H100 PCIe"
        else: # Generic H100
            variant = "H100 (Other)"
    elif "gh200" in text_to_search or ("h200" in text_to_search and "grace hopper" in text_to_search): # GH200 is part of H200 family for this purpose
        family = "H200" # As requested by user
        variant = "GH200 Grace Hopper Superchip" # Or a more specific H200 variant if listed
    elif "h200" in text_to_search: # For standalone H200 that isn't GH200
        family = "H200"
        if "sxm" in text_to_search: # Assuming H200 might have SXM
            variant = "H200 SXM"
        else:
            variant = "H200 (Other)"
    elif "l40s" in text_to_search:
        family = "L40S"
        variant = "L40S"
    
    if family in ["H100", "H200", "L40S"]:
        return variant, family
    else:
        return None, None # Not a target GPU

def fetch_lambda_labs_data(soup):
    final_data_for_sheet = []
    provider_name_for_sheet = STATIC_PROVIDER_NAME

    # The page has tabbed content for 8x, 4x, 2x, 1x configurations
    # Each tab panel has class 'comp-tabbed-content__tab-panel'
    tab_panels = soup.find_all('div', class_='comp-tabbed-content__tab-panel')

    if not tab_panels:
        print("Lambda Labs Handler: Could not find tab panels for GPU configurations.")
        return []

    print(f"Lambda Labs Handler: Found {len(tab_panels)} configuration tabs (e.g., 8x, 4x, 2x, 1x).")

    for panel in tab_panels:
        table = panel.find('table')
        if not table:
            continue

        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
        
        header_skipped = False
        for row in rows:
            if not header_skipped: # Skip the first row (header) in each table
                header_skipped = True
                continue

            cells = row.find_all('td')
            if len(cells) < 6: # Expecting at least 6 columns
                continue

            gpu_name_full_str = cells[0].get_text(strip=True)
            vram_per_gpu_str = cells[1].get_text(strip=True)
            vcpus_str = cells[2].get_text(strip=True) # For notes
            ram_str = cells[3].get_text(strip=True)   # For notes (total instance RAM)
            storage_str = cells[4].get_text(strip=True) # Total instance storage
            price_per_gpu_hr_str = cells[5].get_text(strip=True)

            price_per_gpu_hr = parse_price_lambda(price_per_gpu_hr_str)
            if price_per_gpu_hr is None: # Skip if "CONTACT SALES" or unparseable
                # print(f"Lambda Labs Handler: Skipping row due to unparseable price or 'Contact Sales': {gpu_name_full_str}")
                continue

            num_chips_in_offering, base_gpu_model, display_name_from_lambda = parse_gpu_instance_name(gpu_name_full_str)
            
            gpu_variant_name, gpu_family = get_canonical_variant_and_base_chip_lambda(base_gpu_model)

            if not gpu_family: # Skip if not H100, H200, L40S
                # print(f"Lambda Labs Handler: Skipping non-target GPU: {base_gpu_model}")
                continue

            memory_gb_per_gpu = parse_memory_lambda(vram_per_gpu_str)
            
            # Construct a unique-ish GPU ID
            gpu_id_lambda = f"lambda_{num_chips_in_offering}x_{gpu_variant_name.replace(' ','_').replace('/','_')}_{display_name_from_lambda.split(' ')[0].lower()}"
            gpu_id_lambda = re.sub(r'[^a-zA-Z0-9_-]', '', gpu_id_lambda) # Clean up special chars

            notes = f"On-demand offering. vCPUs: {vcpus_str}, Instance RAM: {ram_str}. "
            if "reserved" in display_name_from_lambda.lower():
                notes = f"Reserved offering (check terms). vCPUs: {vcpus_str}, Instance RAM: {ram_str}. "
            
            base_info_for_row = {
                "Provider Name": provider_name_for_sheet,
                "Currency": "USD",
                "Service Provided": STATIC_SERVICE_PROVIDED,
                "Region": STATIC_REGION_INFO,
                "GPU ID": gpu_id_lambda,
                "GPU (H100 or H200 or L40S)": gpu_family,
                "Memory (GB)": memory_gb_per_gpu,
                "Display Name(GPU Type)": display_name_from_lambda,
                "GPU Variant Name": gpu_variant_name,
                "Storage Option": STATIC_STORAGE_OPTION_LAMBDA,
                "Amount of Storage": storage_str, 
                "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_LAMBDA, # General, specific might be in notes
                "Number of Chips": num_chips_in_offering, # This is fixed for this offering
                # Commitment discount columns are typically N/A for on-demand, unless specific reserved prices are parsed
                "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A", # Or parse if 1-year/3-year reserved prices are listed
                "Notes / Features": notes.strip(),
            }

            # This offering from Lambda Labs has a specific number of chips.
            # We report this offering with its given chip count.
            
            # --- Per Hour ---
            total_hourly_price_for_instance = num_chips_in_offering * price_per_gpu_hr
            row_hourly_data = {
                **base_info_for_row,
                "Period": "Per Hour",
                "Total Price ($)": round(total_hourly_price_for_instance, 2) if total_hourly_price_for_instance is not None else "N/A",
                "Effective Hourly Rate ($/hr)": round(price_per_gpu_hr, 2) if price_per_gpu_hr is not None else "N/A"
            }
            final_data_for_sheet.append(row_hourly_data)

            # --- Per 6 Months ---
            if price_per_gpu_hr is not None:
                total_6_months_price_numeric = (price_per_gpu_hr * HOURS_IN_MONTH * 6) * num_chips_in_offering
                # Total price string: N-chip hourly total (Total for period)
                total_price_6_months_str = f"{total_hourly_price_for_instance:.2f} ({total_6_months_price_numeric:.2f})"
            else:
                total_price_6_months_str = "N/A"

            row_6_months_data = {
                **base_info_for_row,
                "Period": "Per 6 Months",
                "Total Price ($)": total_price_6_months_str,
                "Effective Hourly Rate ($/hr)": round(price_per_gpu_hr, 2) if price_per_gpu_hr is not None else "N/A"
            }
            final_data_for_sheet.append(row_6_months_data)

            # --- Per Year ---
            if price_per_gpu_hr is not None:
                total_yearly_price_numeric = (price_per_gpu_hr * HOURS_IN_MONTH * 12) * num_chips_in_offering
                total_price_yearly_str = f"{total_hourly_price_for_instance:.2f} ({total_yearly_price_numeric:.2f})"
            else:
                total_price_yearly_str = "N/A"
                
            row_yearly_data = {
                **base_info_for_row,
                "Period": "Per Year",
                "Total Price ($)": total_price_yearly_str,
                "Effective Hourly Rate ($/hr)": round(price_per_gpu_hr, 2) if price_per_gpu_hr is not None else "N/A"
            }
            final_data_for_sheet.append(row_yearly_data)

    if final_data_for_sheet:
        num_unique_offerings = len(set(row["GPU ID"] for row in final_data_for_sheet if row["Period"] == "Per Hour"))
        print(f"Lambda Labs Handler: Processed {num_unique_offerings} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        print(f"Lambda Labs Handler: No target GPU offerings (H100, H200, L40S) found or parseable from the page.")
        
    return final_data_for_sheet

# --- Main function for local testing ---
if __name__ == '__main__':
    print(f"Testing Lambda Labs Handler. Fetching {LAMBDALABS_PRICING_URL}...")
    try:
        response = requests.get(LAMBDALABS_PRICING_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}, timeout=30)
        response.raise_for_status()
        # # Optional: Save HTML for offline testing
        # with open("lambda_labs_pricing.html", "w", encoding="utf-8") as f:
        #     f.write(response.text)
        # print("Saved HTML to lambda_labs_pricing.html")

        soup = BeautifulSoup(response.text, "html.parser")
        
        # # --- Test with saved HTML ---
        # print("Testing with local HTML file: lambda_labs_pricing.html")
        # with open("lambda_labs_pricing.html", "r", encoding="utf-8") as f:
        #     saved_html = f.read()
        # soup = BeautifulSoup(saved_html, "html.parser")
        # # --- End Test with saved HTML ---

        processed_data = fetch_lambda_labs_data(soup)
        
        if processed_data:
            print(f"\nSuccessfully processed {len(processed_data)} rows from Lambda Labs.")
            print(f"Sample of processed Lambda Labs data (first {min(6, len(processed_data))} rows):")
            for i, row_data in enumerate(processed_data):
                if i >= 6: # Print first 2 offerings (3 rows each)
                    break
                print(f"Row {i+1}:")
                for key, value in row_data.items():
                    print(f"  {key}: {value}")
                if (i + 1) % 3 == 0:
                    print("-" * 20) 
        else:
            print("No data processed by fetch_lambda_labs_data.")
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Lambda Labs page: {e}")
    except Exception as e:
        print(f"An error occurred during Lambda Labs handler test: {e}")
        import traceback
        traceback.print_exc()