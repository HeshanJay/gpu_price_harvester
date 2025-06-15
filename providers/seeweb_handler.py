# # providers/seeweb_handler.py
# import requests
# from bs4 import BeautifulSoup
# import re
# import logging

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# SEEWEB_CLOUD_SERVER_GPU_URL = "https://www.seeweb.it/en/products/cloud-server-gpu"
# SEEWEB_SERVERLESS_GPU_URL = "https://www.seeweb.it/en/products/serverless-gpu"
# HOURS_IN_MONTH = 730

# STATIC_PROVIDER_NAME = "Seeweb"
# STATIC_SERVICE_PROVIDED = "Seeweb Cloud GPU" # General term
# STATIC_REGION_INFO = "Europe (Italy, Switzerland)" 
# STATIC_STORAGE_OPTION_SEEWEB = "Local NVMe SSD" 
# STATIC_NETWORK_PERFORMANCE_SEEWEB = "High-Speed Network (10 Gbps typical)"

# def parse_price_seeweb(price_str):
#     if not price_str: return None
#     price_str_cleaned = price_str.lower().replace(',', '')
#     if "contact" in price_str_cleaned or "coming soon" in price_str_cleaned: return None
    
#     match = re.search(r"(\d+\.?\d*)\s*€", price_str_cleaned) 
#     if not match:
#         match = re.search(r"(\d+\.?\d*)", price_str_cleaned) # Fallback if Euro symbol is missing but number is there

#     if match:
#         try:
#             return float(match.group(1))
#         except ValueError: 
#             logger.warning(f"Seeweb: Could not parse price from: '{price_str}'")
#             return None
#     logger.warning(f"Seeweb: No numeric price found in: '{price_str}'")
#     return None

# def parse_memory_seeweb(memory_str): # Parses GPU VRAM
#     if not memory_str: return 0
#     memory_str = memory_str.strip()
#     match = re.search(r"(\d+)\s*GB", memory_str, re.IGNORECASE) 
#     if match:
#         return int(match.group(1))
#     logger.warning(f"Seeweb: Could not parse VRAM from: '{memory_str}'")
#     return 0

# def parse_system_specs_seeweb(card_content_div):
#     specs = {"cpu_cores": "N/A", "ram_gb": "N/A", "disk_space": "N/A"}
#     if not card_content_div: return specs
    
#     # CPU and System RAM are often in a <p> like <p><span class="cpuCore">32</span> CORE | <span class="ram">256</span> GB RAM</p>
#     cpu_ram_p_tag = card_content_div.find(lambda tag: tag.name == 'p' and tag.find('span', class_='cpuCore') and tag.find('span', class_='ram'))
#     if cpu_ram_p_tag:
#         cpu_match = cpu_ram_p_tag.find('span', class_='cpuCore')
#         ram_match = cpu_ram_p_tag.find('span', class_='ram')
#         if cpu_match: specs['cpu_cores'] = cpu_match.get_text(strip=True)
#         if ram_match: specs['ram_gb'] = ram_match.get_text(strip=True) # This is System RAM value

#     # Disk space is often in a <p> like <p><span class="disk"><span>750 GB</span></span> Disk space</p>
#     disk_p_tag = card_content_div.find(lambda tag: tag.name == 'p' and tag.find('span', class_='disk'))
#     if disk_p_tag:
#         disk_span = disk_p_tag.find('span', class_='disk')
#         if disk_span:
#             inner_span = disk_span.find('span')
#             if inner_span: # Handles nested span like <span><span>2</span> TB</span>
#                 value_part = inner_span.get_text(strip=True)
#                 unit_part = "".join(sibling.get_text(strip=True) for sibling in inner_span.next_siblings if isinstance(sibling, str)).strip()
#                 specs['disk_space'] = f"{value_part} {unit_part}".strip()
#             else: # Handles simple span like <span>500 GB</span>
#                 specs['disk_space'] = disk_span.get_text(strip=True)
            
#     return specs

# def get_vram_for_gpu_seeweb(gpu_name_on_card, listed_vram_on_card):
#     name_lower = gpu_name_on_card.lower()
#     # Use listed VRAM if it's reasonable for a single GPU of that type
#     if "h200" in name_lower: return 141
#     if "h100" in name_lower:
#         # Seeweb's H100 card on cloud-server-gpu page lists 320GB which is likely for 4x80GB node.
#         # Price is per GPU, so VRAM per GPU is 80GB.
#         # The H100 on serverless page lists 80GB directly.
#         return 80 
#     if "l40s" in name_lower: return 48
    
#     # Fallback to listed VRAM if it's a target GPU and the above didn't catch it
#     if listed_vram_on_card > 0 and any(target_gpu in name_lower for target_gpu in ["h100", "h200", "l40s"]):
#         return listed_vram_on_card
        
#     return 0 # Default if not specifically known or unparseable for target

# def get_canonical_variant_and_base_chip_seeweb(gpu_name_from_card, gpu_type_text_raw=""):
#     text_to_search = gpu_name_from_card.lower().replace("nvidia", "").strip()
#     family = None
#     variant_name = gpu_name_from_card 

#     type_suffix = ""
#     if gpu_type_text_raw:
#         if "sxm" in gpu_type_text_raw.lower(): type_suffix = " SXM"
#         elif "pci" in gpu_type_text_raw.lower(): type_suffix = " PCIe" # Catches PCIe

#     if "h200" in text_to_search:
#         family = "H200"
#         variant_name = f"H200{type_suffix}".strip()
#     elif "h100" in text_to_search:
#         family = "H100"
#         variant_name = f"H100{type_suffix}".strip()
#     elif "l40s" in text_to_search:
#         family = "L40S"
#         variant_name = f"L40S{type_suffix}".strip() if type_suffix else "L40S" # L40S is PCIe
    
#     if family in ["H100", "H200", "L40S"]:
#         return variant_name, family
#     return None, None

# def generate_periodic_rows_seeweb(base_info_template, num_chips_for_offering, on_demand_hr_rate_eur, commit_rates_eur):
#     rows = []
#     if on_demand_hr_rate_eur is None:
#         logger.warning(f"Seeweb: Cannot generate rows for {base_info_template.get('Display Name(GPU Type)')} as on_demand_hr_rate is None.")
#         return rows
        
#     base_info = base_info_template.copy()
#     base_info["Number of Chips"] = num_chips_for_offering
    
#     # Update display name to reflect chip count if not already part of base_info
#     if f"{num_chips_for_offering}x" not in base_info["Display Name(GPU Type)"].lower():
#          base_info["Display Name(GPU Type)"] = f"{num_chips_for_offering}x {base_info['GPU Variant Name']} ({base_info['GPU (H100 or H200 or L40S)']})" \
#                                                + f" - {base_info['Notes / Features'].split('.')[0]}"


#     base_info["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A" 
#     base_info["Commitment Discount - 3 Month Price ($/hr per GPU)"] = round(commit_rates_eur.get("3m"), 2) if commit_rates_eur.get("3m") is not None else "N/A"
#     base_info["Commitment Discount - 6 Month Price ($/hr per GPU)"] = round(commit_rates_eur.get("6m"), 2) if commit_rates_eur.get("6m") is not None else "N/A"
#     base_info["Commitment Discount - 12 Month Price ($/hr per GPU)"] = round(commit_rates_eur.get("12m"), 2) if commit_rates_eur.get("12m") is not None else "N/A"
    
#     total_hourly_for_instance = num_chips_for_offering * on_demand_hr_rate_eur
#     hourly_row = {**base_info, 
#                   "Period": "Per Hour",
#                   "Total Price ($)": round(total_hourly_for_instance, 2), 
#                   "Effective Hourly Rate ($/hr)": round(on_demand_hr_rate_eur, 2)}
#     rows.append(hourly_row)

#     eff_rate_6mo = commit_rates_eur.get("6m") if commit_rates_eur.get("6m") is not None else on_demand_hr_rate_eur
#     total_6mo_instance_hourly = num_chips_for_offering * eff_rate_6mo
#     total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
#     price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
#     six_month_row = {**base_info,
#                      "Period": "Per 6 Months",
#                      "Total Price ($)": price_str_6mo,
#                      "Effective Hourly Rate ($/hr)": round(eff_rate_6mo, 2)}
#     rows.append(six_month_row)

#     eff_rate_12mo = commit_rates_eur.get("12m") if commit_rates_eur.get("12m") is not None else on_demand_hr_rate_eur
#     total_12mo_instance_hourly = num_chips_for_offering * eff_rate_12mo
#     total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
#     price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
#     yearly_row_data = {**base_info,
#                   "Period": "Per Year",
#                   "Total Price ($)": price_str_12mo,
#                   "Effective Hourly Rate ($/hr)": round(eff_rate_12mo, 2)}
#     rows.append(yearly_row_data)
#     return rows

# def parse_seeweb_page(soup, page_url_identifier):
#     """Parses a Seeweb pricing page (either Cloud Server GPU or Serverless GPU)"""
#     offerings_on_page = []
#     if not soup or not soup.body:
#         logger.error(f"Seeweb Handler: Invalid or empty HTML soup for page: {page_url_identifier}.")
#         return offerings_on_page

#     product_cards = soup.select('div.cont-table.config div.cardType') # Common selector for cards
#     logger.info(f"Seeweb Handler ({page_url_identifier}): Found {len(product_cards)} product cards.")

#     for card in product_cards:
#         card_header = card.find('div', class_='card-header')
#         card_body = card.find('div', class_='card-body')
#         if not card_header or not card_body: continue

#         gpu_name_tag = card_header.find('span', class_='cardname')
#         if not gpu_name_tag: continue
        
#         gpu_name_on_card = gpu_name_tag.get_text(strip=True)

#         # Extract GPU type text (e.g., "GPU SXM", "GPU PCI")
#         first_spec_line_div = card_body.find('div') 
#         gpu_type_text_raw = ""
#         if first_spec_line_div and first_spec_line_div.find('div'): # GPU type text is after the select dropdown
#             full_text = first_spec_line_div.find('div').get_text(separator=" ",strip=True)
#             gpu_type_match = re.search(r"(GPU\s*(?:SXM|PCI))", full_text, re.IGNORECASE)
#             if gpu_type_match: gpu_type_text_raw = gpu_type_match.group(1)
#             else: gpu_type_text_raw = "GPU" if "GPU" in full_text else ""


#         gpu_variant, gpu_family = get_canonical_variant_and_base_chip_seeweb(gpu_name_on_card, gpu_type_text_raw)
#         if not gpu_family: continue
        
#         logger.info(f"  ({page_url_identifier}) Processing target GPU card: {gpu_name_on_card} -> Family: {gpu_family}, Variant: {gpu_variant}")

#         vram_tag = card_body.find('span', class_='gpuRam')
#         listed_vram_on_card = parse_memory_seeweb(vram_tag.get_text(strip=True)) if vram_tag else 0
#         vram_gb_per_gpu = get_vram_for_gpu_seeweb(gpu_variant, listed_vram_on_card)
#         if vram_gb_per_gpu == 0 : # If still zero, might be an issue or non-standard target GPU
#             logger.warning(f"    Could not determine VRAM for {gpu_variant}, skipping.")
#             continue


#         specs_content_div = card_body.find_all('div')[0] # First div holds specs usually
#         instance_specs = parse_system_specs_seeweb(specs_content_div)
        
#         notes = f"Instance specs: {instance_specs['cpu_cores']} CORE, {instance_specs['ram_gb']} GB System RAM, {instance_specs['disk_space']} Disk."
#         if page_url_identifier == "Serverless":
#             notes = f"Serverless GPU. Base instance specs for 1x GPU: {instance_specs['cpu_cores']} CORE, {instance_specs['ram_gb']} GB System RAM, {instance_specs['disk_space']} Disk."
#             runtime_class_tag = card_body.find('p', class_='runtimeclassName')
#             if runtime_class_tag: notes += f" {runtime_class_tag.get_text(strip=True)}."


#         on_demand_hourly_tag = card_body.find('p', class_='hourly')
#         on_demand_hr_rate = parse_price_seeweb(on_demand_hourly_tag.find('span').get_text(strip=True)) if on_demand_hourly_tag and on_demand_hourly_tag.find('span') else None

#         commit_rates_eur = {}
#         commit_3m_tag = card_body.find('p', class_='hourly_3mnths')
#         if commit_3m_tag and commit_3m_tag.find('span'): commit_rates_eur["3m"] = parse_price_seeweb(commit_3m_tag.find('span').get_text(strip=True))
        
#         commit_6m_tag = card_body.find('p', class_='hourly_6mnths')
#         if commit_6m_tag and commit_6m_tag.find('span'): commit_rates_eur["6m"] = parse_price_seeweb(commit_6m_tag.find('span').get_text(strip=True))

#         commit_12m_tag = card_body.find('p', class_='hourly_12mnths')
#         if commit_12m_tag and commit_12m_tag.find('span'): commit_rates_eur["12m"] = parse_price_seeweb(commit_12m_tag.find('span').get_text(strip=True))

#         if on_demand_hr_rate is None and not any(c is not None for c in commit_rates_eur.values()):
#             logger.warning(f"    No valid on-demand or commitment prices found for {gpu_name_on_card} on {page_url_identifier}. Skipping.")
#             continue
        
#         # If on-demand is missing but commitments exist, use the shortest commitment as a proxy for on-demand for calculations
#         if on_demand_hr_rate is None:
#             if commit_rates_eur.get("3m") is not None: on_demand_hr_rate = commit_rates_eur.get("3m")
#             elif commit_rates_eur.get("6m") is not None: on_demand_hr_rate = commit_rates_eur.get("6m")
#             elif commit_rates_eur.get("12m") is not None: on_demand_hr_rate = commit_rates_eur.get("12m")
#             else: continue # Still no base price

#         gpu_counts_select = card_body.find('select', class_=re.compile(r"gpu-params|serverless-gpu-params"))
#         possible_chip_counts = [1] 
#         if gpu_counts_select:
#             parsed_counts = [int(opt['value']) for opt in gpu_counts_select.find_all('option') if opt.get('value') and opt.get('value').isdigit()]
#             if parsed_counts: possible_chip_counts = parsed_counts
        
#         for num_chips in possible_chip_counts:
#             display_name_final = f"{num_chips}x {gpu_variant} ({gpu_family}) - {instance_specs['cpu_cores']} CORE, {instance_specs['ram_gb']}GB RAM"
            
#             gpu_id_seeweb = f"seeweb_{page_url_identifier.lower()}_{num_chips}x_{gpu_variant.replace(' ','_')}"
#             gpu_id_seeweb = re.sub(r'[^a-zA-Z0-9_-]', '', gpu_id_seeweb)

#             base_info = {
#                 "Provider Name": STATIC_PROVIDER_NAME,
#                 "Service Provided": f"{STATIC_SERVICE_PROVIDED} ({page_url_identifier})",
#                 "Region": STATIC_REGION_INFO, "Currency": "EUR", "GPU ID": gpu_id_seeweb,
#                 "GPU (H100 or H200 or L40S)": gpu_family, "Memory (GB)": vram_gb_per_gpu,
#                 "Display Name(GPU Type)": display_name_final, "GPU Variant Name": gpu_variant,
#                 "Storage Option": STATIC_STORAGE_OPTION_SEEWEB, "Amount of Storage": instance_specs['disk_space'],
#                 "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_SEEWEB,
#                 "Notes / Features": notes.strip(),
#             }
#             offerings_on_page.extend(generate_periodic_rows_seeweb(base_info, num_chips, on_demand_hr_rate, commit_rates_eur))
#     return offerings_on_page


# def fetch_seeweb_data(soup_cloud_server_gpu, soup_serverless_gpu):
#     all_offerings = []

#     if soup_cloud_server_gpu:
#         logger.info("Seeweb Handler: Parsing Cloud Server GPU page...")
#         all_offerings.extend(parse_seeweb_page(soup_cloud_server_gpu, "CloudServerGPU"))
#     else:
#         logger.warning("Seeweb Handler: No soup provided for Cloud Server GPU page.")

#     if soup_serverless_gpu:
#         logger.info("Seeweb Handler: Parsing Serverless GPU page...")
#         all_offerings.extend(parse_seeweb_page(soup_serverless_gpu, "ServerlessGPU"))
#     else:
#         logger.warning("Seeweb Handler: No soup provided for Serverless GPU page.")

#     # De-duplicate final list
#     unique_rows_dict = {}
#     if all_offerings:
#         logger.info(f"Seeweb Handler: Starting de-duplication. Original row count: {len(all_offerings)}")
#         for row in all_offerings:
#             key_for_dedup = (
#                 row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
#                 row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
#                 row.get("Currency"), row.get("Effective Hourly Rate ($/hr)") 
#             )
#             # For Seeweb, if the same offering (GPU, Chips, Period, Rate) appears on both pages, keep one.
#             # If rates differ, this will keep them as distinct entries.
#             if key_for_dedup not in unique_rows_dict:
#                 unique_rows_dict[key_for_dedup] = row
        
#         final_data_for_sheet = list(unique_rows_dict.values())
#         logger.info(f"Seeweb Handler: After de-duplication. New row count: {len(final_data_for_sheet)}")
#     else:
#         final_data_for_sheet = []


#     if final_data_for_sheet:
#         distinct_offerings_count = len(set((row["Display Name(GPU Type)"], row["Number of Chips"]) for row in final_data_for_sheet if row["Period"] == "Per Hour"))
#         logger.info(f"Seeweb Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
#     else:
#         logger.warning(f"Seeweb Handler: No target GPU offerings (H100, H200, L40S) found or parseable from Seeweb pages.")
        
#     return final_data_for_sheet


# if __name__ == '__main__':
#     logger.info(f"Testing Seeweb Handler...")
    
#     html_cloud_gpu = None
#     html_serverless_gpu = None

#     # Fetch Cloud Server GPU Page
#     try:
#         logger.info(f"Fetching Cloud Server GPU page: {SEEWEB_CLOUD_SERVER_GPU_URL}")
#         response = requests.get(SEEWEB_CLOUD_SERVER_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
#         response.raise_for_status()
#         html_cloud_gpu = response.text
#         with open("seeweb_cloud_server_gpu_latest.html", "w", encoding="utf-8") as f:
#             f.write(html_cloud_gpu)
#         logger.info("Saved Cloud Server GPU HTML to seeweb_cloud_server_gpu_latest.html for inspection.")
#     except Exception as e:
#         logger.error(f"Error fetching Seeweb Cloud Server GPU page: {e}. Trying local file.")
#         try:
#             with open("seeweb_cloud_server_gpu_latest.html", "r", encoding="utf-8") as f: html_cloud_gpu = f.read()
#             logger.info("Loaded Cloud Server GPU HTML from local file.")
#         except FileNotFoundError: logger.error("Local Cloud Server GPU HTML file not found.")

#     # Fetch Serverless GPU Page
#     try:
#         logger.info(f"Fetching Serverless GPU page: {SEEWEB_SERVERLESS_GPU_URL}")
#         response = requests.get(SEEWEB_SERVERLESS_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
#         response.raise_for_status()
#         html_serverless_gpu = response.text
#         with open("seeweb_serverless_gpu_latest.html", "w", encoding="utf-8") as f:
#             f.write(html_serverless_gpu)
#         logger.info("Saved Serverless GPU HTML to seeweb_serverless_gpu_latest.html for inspection.")
#     except Exception as e:
#         logger.error(f"Error fetching Seeweb Serverless GPU page: {e}. Trying local file.")
#         try:
#             with open("seeweb_serverless_gpu_latest.html", "r", encoding="utf-8") as f: html_serverless_gpu = f.read()
#             logger.info("Loaded Serverless GPU HTML from local file.")
#         except FileNotFoundError: logger.error("Local Serverless GPU HTML file not found.")

#     soup_cloud_gpu_obj = BeautifulSoup(html_cloud_gpu, "html.parser") if html_cloud_gpu else BeautifulSoup("", "html.parser")
#     soup_serverless_gpu_obj = BeautifulSoup(html_serverless_gpu, "html.parser") if html_serverless_gpu else BeautifulSoup("", "html.parser")
        
#     processed_data = fetch_seeweb_data(soup_cloud_gpu_obj, soup_serverless_gpu_obj)
    
#     if processed_data:
#         logger.info(f"\nSuccessfully processed {len(processed_data)} rows from Seeweb.")
#         # Print summary
#         printed_offerings_summary = {}
#         for i, row_data in enumerate(processed_data):
#             offering_key_print = (row_data["Display Name(GPU Type)"], row_data["Number of Chips"])
#             if offering_key_print not in printed_offerings_summary:
#                 printed_offerings_summary[offering_key_print] = []
            
#             period_info = f"{row_data['Period']}: Currency {row_data['Currency']}, Rate {row_data['Effective Hourly Rate ($/hr)']}/GPU/hr, Total Inst Price {row_data['Total Price ($)']}"
#             # Only show 12-month commit rate in summary if it's different from on-demand
#             if row_data['Period'] == 'Per Year' and row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != "N/A" and \
#                (row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != row_data['Effective Hourly Rate ($/hr)'] or \
#                 (row_data.get('commit_12mo_price') is not None and row_data['Effective Hourly Rate ($/hr)'] != row_data.get('commit_12mo_price'))): # Check if it was a commit rate
#                  period_info += f" (12mo Commit Rate: {row_data['Commitment Discount - 12 Month Price ($/hr per GPU)']})"
#             printed_offerings_summary[offering_key_print].append(period_info)

#         logger.info("\n--- Summary of Processed Offerings (Seeweb) ---")
#         for (disp_name, chips), periods_info in printed_offerings_summary.items():
#                 logger.info(f"\nOffering: {disp_name} (Chips: {chips})")
#                 for p_info in periods_info:
#                     logger.info(f"  - {p_info}")
#     else:
#         logger.warning("No data processed by fetch_seeweb_data.")



# providers/seeweb_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SEEWEB_CLOUD_SERVER_GPU_URL = "https://www.seeweb.it/en/products/cloud-server-gpu"
SEEWEB_SERVERLESS_GPU_URL = "https://www.seeweb.it/en/products/serverless-gpu"
HOURS_IN_MONTH = 730

STATIC_PROVIDER_NAME = "Seeweb"
STATIC_SERVICE_PROVIDED = "Seeweb Cloud GPU" 
STATIC_REGION_INFO = "Europe (Italy, Switzerland)" 
STATIC_STORAGE_OPTION_SEEWEB = "Local NVMe SSD" 
STATIC_NETWORK_PERFORMANCE_SEEWEB = "High-Speed Network (10 Gbps typical)"

def parse_price_seeweb(price_str):
    if not price_str: return None
    price_str_cleaned = price_str.lower().replace(',', '')
    if "contact" in price_str_cleaned or "coming soon" in price_str_cleaned: return None
    
    match = re.search(r"(\d+\.?\d*)\s*€?", price_str_cleaned) 
    if not match:
        match = re.search(r"(\d+\.?\d*)", price_str_cleaned)

    if match:
        try:
            return float(match.group(1))
        except ValueError: 
            logger.warning(f"Seeweb: Could not parse price from value: '{match.group(1)}' in full string: '{price_str}'")
            return None
    logger.warning(f"Seeweb: No numeric price found in: '{price_str}'")
    return None

def parse_vram_from_span_text(vram_text_from_span):
    """Directly parses the numeric VRAM value from the gpuRam span's text."""
    if not vram_text_from_span: return 0
    try:
        return int(vram_text_from_span.strip())
    except ValueError:
        logger.warning(f"Seeweb: Could not parse VRAM number from span text: '{vram_text_from_span}'")
        return 0

def get_vram_for_gpu_seeweb(gpu_name_on_card, parsed_vram_from_span):
    name_lower = gpu_name_on_card.lower()
    
    if "h200" in name_lower: return 141
    if "h100" in name_lower: return 80 
    if "l40s" in name_lower: return 48
    
    # Fallback if it's a target GPU but not caught above (shouldn't happen for H100/H200/L40S)
    if parsed_vram_from_span > 0 and any(target_gpu in name_lower for target_gpu in ["h100", "h200", "l40s"]):
        logger.info(f"Seeweb: Using parsed VRAM {parsed_vram_from_span}GB for {gpu_name_on_card} as specific override wasn't hit.")
        return parsed_vram_from_span
        
    logger.warning(f"Seeweb: VRAM for '{gpu_name_on_card}' (parsed span VRAM: {parsed_vram_from_span}GB) could not be definitively determined for target GPUs, defaulting to 0 or relying on above knowns.")
    return 0 

def get_canonical_variant_and_base_chip_seeweb(gpu_name_from_card, gpu_type_text_raw=""):
    text_to_search = gpu_name_from_card.lower().replace("nvidia", "").strip()
    family = None
    variant_name = gpu_name_from_card 

    type_suffix = ""
    if gpu_type_text_raw: 
        if "sxm" in gpu_type_text_raw.lower(): type_suffix = " SXM"
        elif "pci" in gpu_type_text_raw.lower(): type_suffix = " PCIe"

    if "h200" in text_to_search:
        family = "H200"
        variant_name = f"H200{type_suffix}".strip() if type_suffix else "H200 SXM" 
    elif "h100" in text_to_search:
        family = "H100"
        variant_name = f"H100{type_suffix}".strip() if type_suffix else "H100 SXM" 
    elif "l40s" in text_to_search:
        family = "L40S"
        variant_name = f"L40S{type_suffix}".strip() if type_suffix else "L40S PCIe"
    
    if family in ["H100", "H200", "L40S"]:
        return variant_name, family
    return None, None

def extract_specs_from_pricing_box_list(card_content_div):
    specs = {"cpu_cores": "N/A", "ram_gb": "N/A", "disk_space": "N/A"}
    if not card_content_div: return specs
    
    # For CPU and System RAM
    p_tags = card_content_div.find_all('p')
    for p_tag in p_tags:
        text = p_tag.get_text(strip=True)
        cpu_core_match = p_tag.find('span', class_='cpuCore')
        ram_match = p_tag.find('span', class_='ram')
        disk_match = p_tag.find('span', class_='disk')

        if cpu_core_match:
            specs['cpu_cores'] = cpu_core_match.get_text(strip=True)
        if ram_match:
            specs['ram_gb'] = ram_match.get_text(strip=True) # This is System RAM value
        if disk_match:
            # Handles structures like <span class="disk"><span>750 GB</span></span> or <span class="disk">1 TB</span>
            inner_disk_span = disk_match.find('span')
            if inner_disk_span:
                specs['disk_space'] = inner_disk_span.get_text(strip=True)
                # Append unit if it's outside the inner span but inside the main disk_span
                next_text_node = inner_disk_span.next_sibling
                if next_text_node and isinstance(next_text_node, str) and next_text_node.strip():
                    specs['disk_space'] += " " + next_text_node.strip()
            else:
                specs['disk_space'] = disk_match.get_text(strip=True)
            specs['disk_space'] = specs['disk_space'].replace("Disk space","").strip()


    return specs


def generate_periodic_rows_seeweb(base_info_template, num_chips_for_offering, on_demand_hr_rate_eur, commit_rates_eur):
    rows = []
    if on_demand_hr_rate_eur is None:
        logger.warning(f"Seeweb: Cannot generate rows for {base_info_template.get('Display Name(GPU Type)')} as on_demand_hr_rate is None.")
        return rows
        
    base_info = base_info_template.copy()
    base_info["Number of Chips"] = num_chips_for_offering
    
    # Construct a more informative display name including key specs if available
    notes_summary_parts = []
    if base_info.get("cpu_cores_note") and base_info["cpu_cores_note"] != "N/A":
        notes_summary_parts.append(f"{base_info['cpu_cores_note']} CORE")
    if base_info.get("ram_gb_note") and base_info["ram_gb_note"] != "N/A":
         notes_summary_parts.append(f"{base_info['ram_gb_note']} GB SysRAM")
    
    notes_summary = ", ".join(notes_summary_parts)
    base_display_name = f"{num_chips_for_offering}x {base_info['GPU Variant Name']} ({base_info['GPU (H100 or H200 or L40S)']})"
    base_info["Display Name(GPU Type)"] = f"{base_display_name} [{notes_summary}]" if notes_summary else base_display_name


    base_info["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A" 
    base_info["Commitment Discount - 3 Month Price ($/hr per GPU)"] = round(commit_rates_eur.get("3m"), 2) if commit_rates_eur.get("3m") is not None else "N/A"
    base_info["Commitment Discount - 6 Month Price ($/hr per GPU)"] = round(commit_rates_eur.get("6m"), 2) if commit_rates_eur.get("6m") is not None else "N/A"
    base_info["Commitment Discount - 12 Month Price ($/hr per GPU)"] = round(commit_rates_eur.get("12m"), 2) if commit_rates_eur.get("12m") is not None else "N/A"
    
    total_hourly_for_instance = num_chips_for_offering * on_demand_hr_rate_eur
    hourly_row = {**base_info, 
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_for_instance, 2), 
                  "Effective Hourly Rate ($/hr)": round(on_demand_hr_rate_eur, 2)}
    rows.append(hourly_row)

    eff_rate_6mo = commit_rates_eur.get("6m") if commit_rates_eur.get("6m") is not None else on_demand_hr_rate_eur
    total_6mo_instance_hourly = num_chips_for_offering * eff_rate_6mo
    total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
    six_month_row = {**base_info,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(eff_rate_6mo, 2)}
    rows.append(six_month_row)

    eff_rate_12mo = commit_rates_eur.get("12m") if commit_rates_eur.get("12m") is not None else on_demand_hr_rate_eur
    total_12mo_instance_hourly = num_chips_for_offering * eff_rate_12mo
    total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
    yearly_row_data = {**base_info,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(eff_rate_12mo, 2)}
    rows.append(yearly_row_data)
    return rows

def parse_seeweb_page(soup, page_url_identifier):
    offerings_on_page = []
    if not soup or not soup.body:
        logger.error(f"Seeweb Handler: Invalid or empty HTML soup for page: {page_url_identifier}.")
        return offerings_on_page

    product_cards = soup.select('div.cont-table.config div.cardType')
    logger.info(f"Seeweb Handler ({page_url_identifier}): Found {len(product_cards)} product cards.")

    for card in product_cards:
        card_header = card.find('div', class_='card-header')
        card_body = card.find('div', class_='card-body')
        if not card_header or not card_body: continue

        gpu_name_tag = card_header.find('span', class_='cardname')
        if not gpu_name_tag: continue
        gpu_name_on_card = gpu_name_tag.get_text(strip=True)

        first_spec_line_div = card_body.find('div') 
        gpu_type_text_raw = ""
        if first_spec_line_div and first_spec_line_div.find('div'): 
            full_text = first_spec_line_div.find('div').get_text(separator=" ",strip=True)
            gpu_type_match = re.search(r"(GPU\s*(?:SXM|PCI))", full_text, re.IGNORECASE)
            if gpu_type_match: gpu_type_text_raw = gpu_type_match.group(1)
            else: gpu_type_text_raw = "GPU" if "GPU" in full_text else ""

        gpu_variant, gpu_family = get_canonical_variant_and_base_chip_seeweb(gpu_name_on_card, gpu_type_text_raw)
        if not gpu_family: continue
        
        logger.info(f"  ({page_url_identifier}) Processing target GPU card: {gpu_name_on_card} -> Family: {gpu_family}, Variant: {gpu_variant}")

        vram_tag = card_body.find('span', class_='gpuRam')
        parsed_vram_from_span = parse_vram_from_span_text(vram_tag.get_text(strip=True)) if vram_tag else 0
        vram_gb_per_gpu = get_vram_for_gpu_seeweb(gpu_name_on_card, parsed_vram_from_span)
        
        if vram_gb_per_gpu == 0:
            logger.warning(f"    Could not determine VRAM for {gpu_variant} from {page_url_identifier}, card skipped.")
            continue

        specs_content_div = card_body.find_all('div')[0] 
        instance_specs = extract_specs_from_pricing_box_list(specs_content_div)
        
        notes = f"Base instance config: {instance_specs['cpu_cores']} CORE, {instance_specs['ram_gb']} GB System RAM, {instance_specs['disk_space']} Disk."
        if page_url_identifier == "ServerlessGPU":
            runtime_class_tag = card_body.find('p', class_='runtimeclassName')
            if runtime_class_tag: notes += f" {runtime_class_tag.get_text(strip=True)}."


        on_demand_hourly_tag = card_body.find('p', class_='hourly')
        on_demand_hr_rate = parse_price_seeweb(on_demand_hourly_tag.find('span').get_text(strip=True)) if on_demand_hourly_tag and on_demand_hourly_tag.find('span') else None

        commit_rates_eur = {}
        commit_3m_tag = card_body.find('p', class_='hourly_3mnths')
        if commit_3m_tag and commit_3m_tag.find('span'): commit_rates_eur["3m"] = parse_price_seeweb(commit_3m_tag.find('span').get_text(strip=True))
        
        commit_6m_tag = card_body.find('p', class_='hourly_6mnths')
        if commit_6m_tag and commit_6m_tag.find('span'): commit_rates_eur["6m"] = parse_price_seeweb(commit_6m_tag.find('span').get_text(strip=True))

        commit_12m_tag = card_body.find('p', class_='hourly_12mnths')
        if commit_12m_tag and commit_12m_tag.find('span'): commit_rates_eur["12m"] = parse_price_seeweb(commit_12m_tag.find('span').get_text(strip=True))

        # Use shortest commitment if on-demand is missing
        effective_on_demand_rate = on_demand_hr_rate
        if effective_on_demand_rate is None:
            if commit_rates_eur.get("3m") is not None: effective_on_demand_rate = commit_rates_eur.get("3m")
            elif commit_rates_eur.get("6m") is not None: effective_on_demand_rate = commit_rates_eur.get("6m")
            elif commit_rates_eur.get("12m") is not None: effective_on_demand_rate = commit_rates_eur.get("12m")
            else: 
                logger.warning(f"    No valid on-demand or commitment prices found for {gpu_name_on_card} on {page_url_identifier}. Skipping card.")
                continue
        
        gpu_counts_select = card_body.find('select', class_=re.compile(r"gpu-params|serverless-gpu-params"))
        possible_chip_counts = [1] 
        if gpu_counts_select:
            parsed_counts = [int(opt['value']) for opt in gpu_counts_select.find_all('option') if opt.get('value') and opt.get('value').isdigit()]
            if parsed_counts: possible_chip_counts = parsed_counts
        
        for num_chips in possible_chip_counts:
            gpu_id_seeweb = f"seeweb_{page_url_identifier.lower()}_{num_chips}x_{gpu_variant.replace(' ','_').replace('/','-')}"
            gpu_id_seeweb = re.sub(r'[^a-zA-Z0-9_-]', '', gpu_id_seeweb)

            base_info = {
                "Provider Name": STATIC_PROVIDER_NAME,
                "Service Provided": f"{STATIC_SERVICE_PROVIDED} ({page_url_identifier})",
                "Region": STATIC_REGION_INFO, "Currency": "EUR", "GPU ID": gpu_id_seeweb,
                "GPU (H100 or H200 or L40S)": gpu_family, "Memory (GB)": vram_gb_per_gpu,
                "Display Name(GPU Type)": f"{num_chips}x {gpu_variant}", # Will be refined in generate_periodic_rows
                "GPU Variant Name": gpu_variant,
                "Storage Option": STATIC_STORAGE_OPTION_SEEWEB, "Amount of Storage": instance_specs['disk_space'],
                "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_SEEWEB,
                "Notes / Features": notes.strip(), # Base notes
                # Pass instance specs for display name refinement
                "cpu_cores_note": instance_specs['cpu_cores'],
                "ram_gb_note": instance_specs['ram_gb'],
            }
            offerings_on_page.extend(generate_periodic_rows_seeweb(base_info, num_chips, effective_on_demand_rate, commit_rates_eur))
    return offerings_on_page


def fetch_seeweb_data(soup_cloud_server_gpu, soup_serverless_gpu):
    all_offerings = []

    if soup_cloud_server_gpu and soup_cloud_server_gpu.body:
        logger.info("Seeweb Handler: Parsing Cloud Server GPU page...")
        all_offerings.extend(parse_seeweb_page(soup_cloud_server_gpu, "CloudServerGPU"))
    else:
        logger.warning("Seeweb Handler: No valid soup provided for Cloud Server GPU page.")

    if soup_serverless_gpu and soup_serverless_gpu.body:
        logger.info("Seeweb Handler: Parsing Serverless GPU page...")
        all_offerings.extend(parse_seeweb_page(soup_serverless_gpu, "ServerlessGPU"))
    else:
        logger.warning("Seeweb Handler: No valid soup provided for Serverless GPU page.")

    unique_rows_dict = {}
    if all_offerings:
        logger.info(f"Seeweb Handler: Starting de-duplication. Original row count: {len(all_offerings)}")
        for row in all_offerings:
            key_for_dedup = (
                row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
                row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
                row.get("Currency"), row.get("Effective Hourly Rate ($/hr)") 
            )
            if key_for_dedup not in unique_rows_dict:
                unique_rows_dict[key_for_dedup] = row
        
        final_data_for_sheet = list(unique_rows_dict.values())
        logger.info(f"Seeweb Handler: After de-duplication. New row count: {len(final_data_for_sheet)}")
    else:
        final_data_for_sheet = []

    if final_data_for_sheet:
        distinct_offerings_count = len(set((row["Display Name(GPU Type)"], row["Number of Chips"]) for row in final_data_for_sheet if row["Period"] == "Per Hour"))
        logger.info(f"Seeweb Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        logger.warning(f"Seeweb Handler: No target GPU offerings (H100, H200, L40S) found or parseable from Seeweb pages.")
        
    return final_data_for_sheet


if __name__ == '__main__':
    logger.info(f"Testing Seeweb Handler...")
    
    html_cloud_gpu = None
    html_serverless_gpu = None
    
    # Attempt to load from local files first
    try:
        with open("seeweb_cloud_server_gpu_latest.html", "r", encoding="utf-8") as f:
            html_cloud_gpu = f.read()
        logger.info("Loaded Cloud Server GPU HTML from local file.")
    except FileNotFoundError:
        logger.info("Local Cloud Server GPU HTML file not found. Fetching live.")
        try:
            response = requests.get(SEEWEB_CLOUD_SERVER_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            html_cloud_gpu = response.text
            with open("seeweb_cloud_server_gpu_latest.html", "w", encoding="utf-8") as f:
                f.write(html_cloud_gpu)
            logger.info("Saved Cloud Server GPU HTML to seeweb_cloud_server_gpu_latest.html.")
        except Exception as e:
            logger.error(f"Error fetching Seeweb Cloud Server GPU page: {e}")

    try:
        with open("seeweb_serverless_gpu_latest.html", "r", encoding="utf-8") as f:
            html_serverless_gpu = f.read()
        logger.info("Loaded Serverless GPU HTML from local file.")
    except FileNotFoundError:
        logger.info("Local Serverless GPU HTML file not found. Fetching live.")
        try:
            response = requests.get(SEEWEB_SERVERLESS_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            html_serverless_gpu = response.text
            with open("seeweb_serverless_gpu_latest.html", "w", encoding="utf-8") as f:
                f.write(html_serverless_gpu)
            logger.info("Saved Serverless GPU HTML to seeweb_serverless_gpu_latest.html.")
        except Exception as e:
            logger.error(f"Error fetching Seeweb Serverless GPU page: {e}")

    soup_cloud_gpu_obj = BeautifulSoup(html_cloud_gpu, "html.parser") if html_cloud_gpu else BeautifulSoup("", "html.parser")
    soup_serverless_gpu_obj = BeautifulSoup(html_serverless_gpu, "html.parser") if html_serverless_gpu else BeautifulSoup("", "html.parser")
        
    processed_data = fetch_seeweb_data(soup_cloud_gpu_obj, soup_serverless_gpu_obj)
    
    if processed_data:
        logger.info(f"\nSuccessfully processed {len(processed_data)} rows from Seeweb.")
        printed_offerings_summary = {}
        for i, row_data in enumerate(processed_data):
            offering_key_print = (row_data["Display Name(GPU Type)"], row_data["Number of Chips"])
            if offering_key_print not in printed_offerings_summary:
                printed_offerings_summary[offering_key_print] = []
            
            period_info = f"{row_data['Period']}: Currency {row_data['Currency']}, Rate {row_data['Effective Hourly Rate ($/hr)']}/GPU/hr, Total Inst Price {row_data['Total Price ($)']}"
            if row_data['Period'] == 'Per Year' and row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != "N/A":
                 if row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != row_data['Effective Hourly Rate ($/hr)']:
                     period_info += f" (12mo Commit Rate: {row_data['Commitment Discount - 12 Month Price ($/hr per GPU)']})"
            printed_offerings_summary[offering_key_print].append(period_info)

        logger.info("\n--- Summary of Processed Offerings (Seeweb) ---")
        for (disp_name, chips), periods_info in printed_offerings_summary.items():
                logger.info(f"\nOffering: {disp_name} (Chips: {chips})")
                for p_info in periods_info:
                    logger.info(f"  - {p_info}")
    else:
        logger.warning("No data processed by fetch_seeweb_data.")