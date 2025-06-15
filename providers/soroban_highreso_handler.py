# providers/soroban_highreso_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOROBAN_AISPACON_URL = "https://soroban.highreso.jp/aispacon"
# SOROBAN_COMPUTE_URL = "https://soroban.highreso.jp/compute/" # For L40S, other H100s - to be added if needed

HOURS_IN_MONTH = 730 

STATIC_PROVIDER_NAME = "Highreso Soroban" # Using "Highreso Soroban" to distinguish
STATIC_SERVICE_PROVIDED = "Soroban AI Supercomputer Cloud / GPU Instances"
STATIC_REGION_INFO = "Japan" # The comparison table mentions Japan for Soroban
STATIC_STORAGE_OPTION_SOROBAN = "Local NVMe SSD" # General term
STATIC_NETWORK_PERFORMANCE_SOROBAN = "High-Speed Interconnect (NVLink/NVSwitch, InfiniBand)"

def parse_price_jp(price_str):
    """Parse price string in JPY (e.g., "¥2,783,000", "990円") to float."""
    if not price_str:
        return None
    price_str_cleaned = price_str.replace(',', '').replace('¥', '').replace('￥', '').replace('円', '').strip()
    match = re.search(r"(\d+\.?\d*)", price_str_cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            logger.warning(f"Soroban: Could not parse price from: {price_str}")
            return None
    return None

def get_vram_for_gpu_soroban(base_gpu_model_name_cleaned):
    name_lower = base_gpu_model_name_cleaned.lower()
    if "h200" in name_lower: return 141 # Per GPU in an 8x H200 node (1128GB total / 8)
    if "h100" in name_lower: return 80
    if "l40s" in name_lower: return 48
    return 0 

def get_canonical_variant_and_base_chip_soroban(gpu_name_from_site):
    text_to_search = gpu_name_from_site.lower().replace("nvidia", "").strip()
    text_to_search = re.sub(r'\s*\(sxm\)\s*x\d+枚?', '', text_to_search) # Remove "(SXM) xN枚"
    text_to_search = text_to_search.replace("tensor core gpu","").replace("gpu","").strip()
    family = None
    variant = gpu_name_from_site

    if "h200" in text_to_search:
        family = "H200"
        variant = "H200 SXM" # AISPACON lists SXM
    elif "h100" in text_to_search:
        family = "H100"
        variant = "H100 SXM" if "sxm" in text_to_search else "H100"
    elif "l40s" in text_to_search:
        family = "L40S"
        variant = "L40S"
    
    if family in ["H100", "H200", "L40S"]:
        return variant, family
    return None, None

def generate_periodic_rows_soroban(base_info, num_chips, effective_ondemand_hourly_jpy, monthly_commit_price_jpy=None):
    rows = []
    if effective_ondemand_hourly_jpy is None:
        logger.warning(f"Soroban: Cannot generate rows for {base_info.get('Display Name(GPU Type)')} as on_demand_hr_rate is None.")
        return rows
        
    base_info_copy = base_info.copy()
    
    # Calculate 1-month commitment price if monthly_commit_price_jpy is available
    commit_1mo_hourly_val = None
    if monthly_commit_price_jpy and num_chips > 0:
        commit_1mo_hourly_val = (monthly_commit_price_jpy / num_chips) / HOURS_IN_MONTH
        base_info_copy["Commitment Discount - 1 Month Price ($/hr per GPU)"] = round(commit_1mo_hourly_val, 2)
    else:
        base_info_copy["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A"
    
    # For Soroban, explicit 3, 6, 12 month discounts are not directly on this page for H200 hourly
    # They have longer term discounts which are "contact sales" or part of campaigns.
    # The monthly price on AISPACON is for "single node H200". We treat derived hourly as 1-month commit.
    base_info_copy["Commitment Discount - 3 Month Price ($/hr per GPU)"] = "N/A"
    base_info_copy["Commitment Discount - 6 Month Price ($/hr per GPU)"] = "N/A"
    base_info_copy["Commitment Discount - 12 Month Price ($/hr per GPU)"] = "N/A" # Unless specific 1-year monthly is parsed

    total_hourly_for_instance = num_chips * effective_ondemand_hourly_jpy
    hourly_row = {**base_info_copy, 
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_for_instance, 2), # JPY value
                  "Effective Hourly Rate ($/hr)": round(effective_ondemand_hourly_jpy, 2)} # JPY value
    rows.append(hourly_row)

    # Use the effective on-demand rate for 6-month projection if no other is available
    eff_rate_6mo = effective_ondemand_hourly_jpy 
    total_6mo_instance_hourly = num_chips * eff_rate_6mo
    total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
    six_month_row = {**base_info_copy,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(eff_rate_6mo, 2)}
    rows.append(six_month_row)

    # Use the effective on-demand rate for 1-year projection if no specific 12-mo commit is available
    eff_rate_12mo = effective_ondemand_hourly_jpy
    total_12mo_instance_hourly = num_chips * eff_rate_12mo
    total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
    yearly_row_data = {**base_info_copy,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(eff_rate_12mo, 2)}
    rows.append(yearly_row_data)
    return rows

def fetch_soroban_highreso_data(aispacon_soup): # Initially focuses on AISPACON page
    final_data_for_sheet = []

    if not aispacon_soup or not aispacon_soup.body: # Check if soup is valid
        logger.error("Soroban Handler: Invalid or empty HTML soup for AISPACON page.")
        return []

    # --- Parse H200 data from AISPACON page ---
    # Look for "HGX H200とH100インスタンスの料金・性能比較" table or similar
    # and "AIスパコンクラウドの料金プラン" table
    
    logger.info("Soroban Handler: Parsing AISPACON page for H200...")
    h200_offering = None

    # Try to find the "AIスパコンクラウドの料金プラン" table for H200 Single Node
    plans_heading = aispacon_soup.find(lambda tag: tag.name in ['h2','h3'] and "aiスパコンクラウドの料金プラン" in tag.get_text(strip=True).lower())
    if plans_heading:
        plan_table = plans_heading.find_next('table')
        if plan_table:
            rows = plan_table.find_all('tr')
            # Header: 構成, シングルノード構成, クラスタ構成
            # Data Row 1 (特徴): HGX H200 x1ノード, HGX H200 x複数ノード
            # Data Row 2 (月額費用): ¥2,783,000, お問い合わせ
            # Data Row 3 (GPU／ノード): NVIDIA H200(SXM) x8枚, NVIDIA H200(SXM) x8枚
            
            gpu_per_node_str = ""
            monthly_price_str = ""
            vcpu_str = ""
            system_ram_str = ""
            storage_str = ""

            for row in rows:
                cols = row.find_all(['th', 'td'])
                if len(cols) >= 2: # Need at least header and first data column
                    header_text = cols[0].get_text(strip=True).lower()
                    single_node_val = cols[1].get_text(strip=True)

                    if "月額費用" in header_text: #月額費用（税込み）
                        monthly_price_str = single_node_val
                    elif "gpu／ノード" in header_text: # GPU／ノード
                        gpu_per_node_str = single_node_val
                    elif "vcpu／ノード" in header_text:
                        vcpu_str = single_node_val
                    elif "システムメモリ／ノード" in header_text:
                        system_ram_str = single_node_val
                    elif "ストレージ／ノード" in header_text:
                        storage_str = single_node_val
            
            if "h200" in gpu_per_node_str.lower() and "x8枚" in gpu_per_node_str.lower():
                monthly_price_jpy = parse_price_jp(monthly_price_str)
                if monthly_price_jpy:
                    num_chips = 8
                    gpu_variant, gpu_family = "H200 SXM", "H200" # From "NVIDIA H200(SXM) x8枚"
                    vram_gb = get_vram_for_gpu_soroban("H200 SXM") # 1128GB total / 8 = 141GB per GPU
                    
                    # Effective hourly rate per GPU from monthly price
                    effective_hourly_jpy = (monthly_price_jpy / num_chips) / HOURS_IN_MONTH
                    
                    display_name = f"{num_chips}x {gpu_variant} (AISPACON Single Node)"
                    gpu_id = f"soroban_aispacon_{num_chips}x_{gpu_variant.replace(' ','_')}"
                    notes = f"AISPACON Single Node. Specs: {gpu_per_node_str}. "
                    if vcpu_str: notes += f"vCPU/Node: {vcpu_str}. "
                    if system_ram_str: notes += f"SysRAM/Node: {system_ram_str}. "
                    if storage_str: notes += f"Storage/Node: {storage_str}. "
                    notes += f"Monthly Price (Total Node): ¥{monthly_price_jpy:,.0f}."

                    base_info = {
                        "Provider Name": STATIC_PROVIDER_NAME,
                        "Service Provided": STATIC_SERVICE_PROVIDED,
                        "Region": STATIC_REGION_INFO,
                        "Currency": "JPY",
                        "GPU ID": gpu_id,
                        "GPU (H100 or H200 or L40S)": gpu_family,
                        "Memory (GB)": vram_gb,
                        "Display Name(GPU Type)": display_name,
                        "GPU Variant Name": gpu_variant,
                        "Storage Option": STATIC_STORAGE_OPTION_SOROBAN,
                        "Amount of Storage": storage_str if storage_str else "Refer to Node Spec",
                        "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_SOROBAN,
                        "Number of Chips": num_chips,
                        "Notes / Features": notes.strip(),
                    }
                    # Use the derived effective hourly rate as the on-demand for this offering,
                    # and also as the 1-month commitment effective rate.
                    final_data_for_sheet.extend(generate_periodic_rows_soroban(base_info, num_chips, effective_hourly_jpy, monthly_price_jpy))
                    logger.info(f"  Processed AISPACON H200 offering: {display_name}")


    # Placeholder: Add logic here to parse https://soroban.highreso.jp/compute/ for L40S and other H100s
    # This would involve another requests.get() call or taking another soup object.
    # For now, we only focus on H200 from the aispacon page as L40S/H100 were not clearly found there.
    # If L40S/H100 are on /aispacon page, the logic would be similar to the above,
    # looking for their specific plan tables or sections.
    # The AISPACON page's main table for H100/L40S/L4 needs to be found:
    
    aispacon_pricing_table_header = aispacon_soup.find(lambda tag: tag.name in ['h2','h3'] and "プランと料金" in tag.get_text(strip=True)) # "Plans and Pricing"
    if aispacon_pricing_table_header:
        table = aispacon_pricing_table_header.find_next('table')
        if table:
            logger.info("  Found AISPACON general pricing table. Parsing for H100, L40S...")
            rows = table.find_all('tr')
            header_cells_text = []
            if rows:
                header_cols = rows[0].find_all(['th', 'td'])
                header_cells_text = [col.get_text(strip=True).lower() for col in header_cols]

            col_indices = {}
            try:
                col_indices["gpu_name"] = header_cells_text.index("gpu")
                col_indices["vcpu_per_gpu"] = header_cells_text.index("vcpu")
                col_indices["memory_per_gpu"] = header_cells_text.index("メモリ") # Memory (System RAM per GPU)
                col_indices["ssd_per_gpu"] = header_cells_text.index("ローカルssd") # Local SSD
                col_indices["hourly_price_per_gpu"] = header_cells_text.index("時間料金") # Hourly Price
                col_indices["monthly_price_per_gpu"] = header_cells_text.index("月額固定料金") # Monthly Price
            except ValueError:
                logger.warning("  Could not find all expected columns in AISPACON pricing table. Skipping this table.")
            
            if col_indices:
                for row in rows[1:]: # Skip header
                    cols = row.find_all('td')
                    if len(cols) < max(col_indices.values()) +1 : continue

                    gpu_name_aispacon = cols[col_indices["gpu_name"]].get_text(strip=True) # e.g., "NVIDIA H100 Tensor Core GPU"
                    
                    # Determine number of chips (e.g., h100-80gb-sxm5-x8 -> 8 chips)
                    num_chips_match = re.search(r"x(\d+)", gpu_name_aispacon.lower())
                    num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
                    
                    # Clean the name for canonical matching
                    base_gpu_name = gpu_name_aispacon.split('(')[0].strip() # "NVIDIA H100 Tensor Core GPU"

                    gpu_variant, gpu_family = get_canonical_variant_and_base_chip_soroban(base_gpu_name)
                    if not gpu_family: continue # Only H100, H200, L40S

                    hourly_price_jpy = parse_price_jp(cols[col_indices["hourly_price_per_gpu"]].get_text(strip=True))
                    monthly_price_jpy_per_gpu = parse_price_jp(cols[col_indices["monthly_price_per_gpu"]].get_text(strip=True))

                    if hourly_price_jpy is None and monthly_price_jpy_per_gpu is None:
                        logger.warning(f"  No price found for {gpu_name_aispacon} in AISPACON table.")
                        continue
                    
                    # If hourly is missing but monthly is there, derive hourly for on-demand rate
                    effective_hourly_rate_jpy = hourly_price_jpy
                    if effective_hourly_rate_jpy is None and monthly_price_jpy_per_gpu:
                        effective_hourly_rate_jpy = monthly_price_jpy_per_gpu / HOURS_IN_MONTH
                    
                    if effective_hourly_rate_jpy is None: continue # Still no valid rate

                    vram_gb = get_vram_for_gpu(base_gpu_name)
                    vcpu_per_gpu = cols[col_indices["vcpu_per_gpu"]].get_text(strip=True)
                    sys_ram_per_gpu_str = cols[col_indices["memory_per_gpu"]].get_text(strip=True) # e.g. "128 GiB"
                    ssd_per_gpu_str = cols[col_indices["ssd_per_gpu"]].get_text(strip=True) # e.g. "480 GB"

                    display_name = f"{num_chips}x {gpu_variant} (AISPACON)"
                    gpu_id = f"soroban_aispacon_{num_chips}x_{gpu_variant.replace(' ','_')}"
                    notes = f"AISPACON offering. Per GPU: {vcpu_per_gpu} vCPU, {sys_ram_per_gpu_str} System RAM, {ssd_per_gpu_str} Local SSD."
                    
                    base_info = {
                        "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
                        "Region": STATIC_REGION_INFO, "Currency": "JPY", "GPU ID": gpu_id,
                        "GPU (H100 or H200 or L40S)": gpu_family, "Memory (GB)": vram_gb,
                        "Display Name(GPU Type)": display_name, "GPU Variant Name": gpu_variant,
                        "Storage Option": STATIC_STORAGE_OPTION_SOROBAN, "Amount of Storage": f"{num_chips}x {ssd_per_gpu_str}",
                        "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_SOROBAN,
                        "Number of Chips": num_chips,
                        "Notes / Features": notes.strip(),
                         # Default commitment to N/A, will be updated by generate_periodic_rows if 12mo is present
                        "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
                        "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                        "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                        "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
                    }
                    # The monthly price here is per GPU, so for 12 month commitment, effective hourly is monthly/HOURS_IN_MONTH
                    commit_12mo_rate = monthly_price_jpy_per_gpu / HOURS_IN_MONTH if monthly_price_jpy_per_gpu else None
                    final_data_for_sheet.extend(generate_periodic_rows_soroban(base_info, num_chips, effective_hourly_rate_jpy, commit_12mo_rate))
                    logger.info(f"  Processed AISPACON table offering: {display_name}")

    # De-duplicate final list
    unique_rows_dict = {}
    if final_data_for_sheet:
        logger.info(f"Soroban Handler: Starting de-duplication. Original row count: {len(final_data_for_sheet)}")
        for row in final_data_for_sheet:
            key_for_dedup = (
                row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
                row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
                row.get("Currency"), row.get("Effective Hourly Rate ($/hr)")
            )
            if key_for_dedup not in unique_rows_dict:
                unique_rows_dict[key_for_dedup] = row
        final_data_for_sheet = list(unique_rows_dict.values())
        logger.info(f"Soroban Handler: After de-duplication. New row count: {len(final_data_for_sheet)}")


    if final_data_for_sheet:
        distinct_offerings_count = len(set((row["Display Name(GPU Type)"], row["Number of Chips"]) for row in final_data_for_sheet if row["Period"] == "Per Hour"))
        logger.info(f"Soroban Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        logger.warning(f"Soroban Handler: No target GPU offerings (H100, H200, L40S) found or parseable from Sakura/Soroban.")
        
    return final_data_for_sheet


if __name__ == '__main__':
    logger.info(f"Testing Soroban/Highreso Handler (AISPACON page: {SOROBAN_AISPACON_URL})...")
    
    html_aispacon_content = None
    try:
        # Fetch live page
        response_aispacon = requests.get(SOROBAN_AISPACON_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response_aispacon.raise_for_status()
        html_aispacon_content = response_aispacon.text
        with open("soroban_aispacon_latest.html", "w", encoding="utf-8") as f:
            f.write(html_aispacon_content)
        logger.info("Saved AISPACON HTML to soroban_aispacon_latest.html for inspection.")
        
    except Exception as e:
        logger.error(f"Error fetching Soroban AISPACON page: {e}. Trying to load from local file if exists.")
        try:
            with open("soroban_aispacon_latest.html", "r", encoding="utf-8") as f:
                html_aispacon_content = f.read()
            logger.info("Loaded AISPACON HTML from local file.")
        except FileNotFoundError:
            logger.error("Local AISPACON HTML file not found. Please run once with live fetch enabled.")

    if html_aispacon_content:
        soup_aispacon = BeautifulSoup(html_aispacon_content, "html.parser")
        processed_data = fetch_soroban_highreso_data(soup_aispacon)
        
        if processed_data:
            logger.info(f"\nSuccessfully processed {len(processed_data)} rows from Soroban/Highreso.")
            printed_offerings_summary = {}
            for i, row_data in enumerate(processed_data):
                offering_key_print = (row_data["Display Name(GPU Type)"], row_data["Number of Chips"])
                if offering_key_print not in printed_offerings_summary:
                    printed_offerings_summary[offering_key_print] = []
                
                period_info = f"{row_data['Period']}: Currency {row_data['Currency']}, Rate {row_data['Effective Hourly Rate ($/hr)']}/GPU/hr, Total Inst Price {row_data['Total Price ($)']}"
                if row_data['Period'] == 'Per Year' and row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != "N/A":
                    period_info += f" (12mo Commit Rate: {row_data['Commitment Discount - 12 Month Price ($/hr per GPU)']})"
                printed_offerings_summary[offering_key_print].append(period_info)

            logger.info("\n--- Summary of Processed Offerings (Soroban/Highreso) ---")
            for (disp_name, chips), periods_info in printed_offerings_summary.items():
                 logger.info(f"\nOffering: {disp_name} (Chips: {chips})")
                 for p_info in periods_info:
                     logger.info(f"  - {p_info}")
        else:
            logger.warning("No data processed by fetch_soroban_highreso_data.")
    else:
        logger.warning("No HTML content for AISPACON page, cannot parse.")