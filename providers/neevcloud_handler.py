# # providers/neevcloud_handler.py
# import requests
# from bs4 import BeautifulSoup
# import re
# import logging

# # Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# NEEVCLOUD_PRICING_URL = "https://www.neevcloud.com/pricing.php"
# HOURS_IN_MONTH = 730

# STATIC_PROVIDER_NAME = "Neevcloud"
# STATIC_SERVICE_PROVIDED = "Neevcloud GPU Cloud Instances"
# STATIC_REGION_INFO = "Multiple (US, India)"
# STATIC_STORAGE_OPTION_NEEV = "Local NVMe SSD / Block Storage"
# STATIC_NETWORK_PERFORMANCE_NEEV = "High-Speed Fabric (e.g., InfiniBand/Ethernet)"

# def parse_price_neev(price_str):
#     if not price_str: return None
#     price_str = price_str.lower().replace(',', '')
#     if "contact" in price_str or "coming soon" in price_str: return None
#     match = re.search(r"[\$₹]?\s*(\d+\.?\d*)", price_str)
#     if match:
#         try:
#             return float(match.group(1))
#         except ValueError: return None
#     return None

# def parse_memory_neev_from_box_list(memory_text):
#     if not memory_text: return 0
#     memory_text = memory_text.strip()
#     match = re.search(r"(\d+)\s*(GiB|GB|TB)", memory_text, re.IGNORECASE)
#     if match:
#         val = int(match.group(1))
#         unit = match.group(2).lower()
#         if unit == "tb": return val * 1024 
#         return val
#     return 0

# def get_vram_for_gpu(base_gpu_model_name_cleaned):
#     name_lower = base_gpu_model_name_cleaned.lower()
#     if "h200" in name_lower: return 141
#     if "h100" in name_lower: return 80
#     if "l40s" in name_lower: return 48
#     if "a40" in name_lower: return 48 # As per NVIDIA specs
#     if "a30" in name_lower: return 24 # As per NVIDIA specs
#     if "l4" in name_lower and "l40s" not in name_lower: return 24 # As per NVIDIA specs
#     if "v100" in name_lower: return 16 # Common variant, can also be 32GB
#     if "rtx 8000" in name_lower: return 48 # Quadro RTX 8000
#     return 0

# def get_canonical_variant_and_base_chip_neev(gpu_name_from_site):
#     text_to_search = gpu_name_from_site.lower().replace("nvidia", "").replace("gpu", "").replace("price", "").replace("pricing", "").strip()
#     text_to_search = re.sub(r'\s+', ' ', text_to_search)
#     family = None
#     variant = gpu_name_from_site 

#     if "h200" in text_to_search:
#         family = "H200"
#         variant = "H200 HGX" if "hgx" in text_to_search else "H200"
#     elif "h100" in text_to_search:
#         family = "H100"
#         if "sxm" in text_to_search or "hgx" in text_to_search: variant = "H100 HGX"
#         elif "pcie" in text_to_search: variant = "H100 PCIe"
#         else: variant = "H100"
#     elif "l40s" in text_to_search:
#         family = "L40S"
#         variant = "L40S"
    
#     if family in ["H100", "H200", "L40S"]:
#         return variant, family
#     return None, None

# def extract_specs_from_pricing_box_list(ul_tag):
#     specs = {"system_ram_gb": 0, "vcpus": "N/A", "ssd": "N/A"}
#     if not ul_tag: return specs
#     for li in ul_tag.find_all('li'):
#         text_content = li.get_text(separator=" ", strip=True)
#         text_content_lower = text_content.lower()
        
#         main_text_part = ""
#         for content_part_node in li.contents:
#             if isinstance(content_part_node, str):
#                 main_text_part += content_part_node.strip()
#             elif content_part_node.name == 'span':
#                 break 
#         main_text_part = main_text_part.strip()

#         if "memory" in text_content_lower:
#             specs["system_ram_gb"] = parse_memory_neev_from_box_list(main_text_part)
#         elif "vcpu" in text_content_lower:
#             match = re.search(r"(\d+)", main_text_part)
#             if match: specs["vcpus"] = match.group(1)
#         elif "ssd" in text_content_lower:
#             specs["ssd"] = main_text_part # e.g., "750 GiB" or "250 GiB"
#     return specs

# def generate_periodic_rows(base_info, num_chips, on_demand_hr_rate, commit_12mo_hr_rate):
#     rows = []
#     if on_demand_hr_rate is None: 
#         logger.warning(f"Cannot generate rows for {base_info.get('Display Name(GPU Type)')} as on_demand_hr_rate is None.")
#         return rows
        
#     base_info_copy = base_info.copy()
#     base_info_copy["Commitment Discount - 12 Month Price ($/hr per GPU)"] = (
#         round(commit_12mo_hr_rate, 2) if commit_12mo_hr_rate is not None else "N/A"
#     )

#     total_hourly_for_instance = num_chips * on_demand_hr_rate
#     hourly_row = {**base_info_copy, 
#                   "Period": "Per Hour",
#                   "Total Price ($)": round(total_hourly_for_instance, 2),
#                   "Effective Hourly Rate ($/hr)": round(on_demand_hr_rate, 2)}
#     rows.append(hourly_row)

#     eff_rate_6mo = on_demand_hr_rate 
#     total_6mo_instance_hourly = num_chips * eff_rate_6mo
#     total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
#     price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
#     six_month_row = {**base_info_copy,
#                      "Period": "Per 6 Months",
#                      "Total Price ($)": price_str_6mo,
#                      "Effective Hourly Rate ($/hr)": round(eff_rate_6mo, 2)}
#     rows.append(six_month_row)

#     eff_rate_12mo = commit_12mo_hr_rate if commit_12mo_hr_rate is not None else on_demand_hr_rate
#     total_12mo_instance_hourly = num_chips * eff_rate_12mo
#     total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
#     price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
#     yearly_row_data = {**base_info_copy,
#                   "Period": "Per Year",
#                   "Total Price ($)": price_str_12mo,
#                   "Effective Hourly Rate ($/hr)": round(eff_rate_12mo, 2)}
#     rows.append(yearly_row_data)
#     return rows


# def fetch_neevcloud_data(soup):
#     final_data_for_sheet = []
    
#     gpu_cloud_section = soup.find('section', id='gpu-cloud')
#     if not gpu_cloud_section:
#         logger.error("Neevcloud Handler: Could not find the main 'gpu-cloud' pricing section (id='gpu-cloud').")
#         gpu_cloud_section = soup.find('body') 
#         if not gpu_cloud_section:
#             logger.error("Neevcloud Handler: Could not even find body tag. Aborting.")
#             return []
            
#     section_headers = gpu_cloud_section.find_all('h6', class_='pricing_table_gpu_name')
#     logger.info(f"Neevcloud Handler: Found {len(section_headers)} GPU pricing section headers.")

#     for header_tag in section_headers:
#         section_name_full = header_tag.get_text(strip=True)
#         base_gpu_model_for_section = section_name_full.replace("Pricing", "").replace("Price", "").strip()
#         gpu_variant_name_section, gpu_family_section = get_canonical_variant_and_base_chip_neev(base_gpu_model_for_section)

#         if not gpu_family_section:
#             continue
        
#         logger.info(f"Neevcloud Handler: Processing section: '{section_name_full}' -> Target Family: {gpu_family_section}, Variant: {gpu_variant_name_section}")

#         on_demand_price_gpu = None
#         commitment_prices = {"12": None, "24": None, "36": None}
#         assumed_chips_for_section = 8 if "hgx" in base_gpu_model_for_section.lower() else 1
#         vram_gb = get_vram_for_gpu(base_gpu_model_for_section)
        
#         hr_sibling = header_tag.find_next_sibling('hr', class_='pricing_table_gpu_bottom_border')
#         if not hr_sibling:
#             logger.warning(f"  Neevcloud Handler: Could not find <hr> after header for {section_name_full}.")
#             continue
        
#         # Try to find explicit On-Demand Price for HGX H100/H200 sections
#         if "hgx" in base_gpu_model_for_section.lower():
#             next_div_row_for_ondemand = hr_sibling.find_next_sibling('div', class_='row') # The on-demand P is usually in the *first* div.row
#             if next_div_row_for_ondemand:
#                 on_demand_p_tag = next_div_row_for_ondemand.find(lambda tag: tag.name == 'p' and "on demand" in tag.get_text(strip=True).lower() and "/gpu/hr" in tag.get_text(strip=True).lower())
#                 if on_demand_p_tag:
#                     text_content = on_demand_p_tag.get_text(strip=True)
#                     match = re.search(r"On Demand:\s*([\$\€£₹]?\s*\d+\.?\d*(?:\s*/GPU/hr)?)", text_content, re.IGNORECASE)
#                     if match:
#                         on_demand_price_gpu = parse_price_neev(match.group(1))
#                         logger.info(f"  Found explicit On-Demand for {base_gpu_model_for_section}: ${on_demand_price_gpu if on_demand_price_gpu else 'N/A'}")

#             # Process commitment boxes for this HGX section
#             # Commitment boxes are in subsequent div.row.mb-5 structures
#             current_element_for_commitment_rows = hr_sibling
#             while current_element_for_commitment_rows:
#                 current_element_for_commitment_rows = current_element_for_commitment_rows.find_next_sibling()
#                 if not current_element_for_commitment_rows: break
#                 if current_element_for_commitment_rows.name == 'h6' and 'pricing_table_gpu_name' in current_element_for_commitment_rows.get('class', []):
#                     break # Reached next GPU section header

#                 if current_element_for_commitment_rows.name == 'div' and 'row' in current_element_for_commitment_rows.get('class', []):
#                     commitment_boxes = current_element_for_commitment_rows.find_all('div', class_='pricing_box_width')
#                     for box in commitment_boxes:
#                         term_tag = box.find('p', class_='pricing_choose_box_price_hr')
#                         price_tag = box.find('h5', class_='pricing_choose_box_heading')
                        
#                         # Try to get on_demand_price_gpu from crossed_out price if not found yet
#                         if not on_demand_price_gpu:
#                              cross_price_tag = box.find('h6', class_='pricing_choose_box_price_cross')
#                              if cross_price_tag:
#                                  temp_on_demand = parse_price_neev(cross_price_tag.get_text(strip=True))
#                                  if temp_on_demand:
#                                      on_demand_price_gpu = temp_on_demand
#                                      logger.info(f"  Using crossed-out price as On-Demand for {base_gpu_model_for_section}: ${on_demand_price_gpu}")
                        
#                         if term_tag and price_tag:
#                             term_text = term_tag.get_text(strip=True).lower()
#                             commit_price = parse_price_neev(price_tag.get_text(strip=True))
#                             if commit_price:
#                                 if "12 months" in term_text: commitment_prices["12"] = commit_price
#                                 elif "24 months" in term_text: commitment_prices["24"] = commit_price # Store for notes
#                                 elif "36 months" in term_text: commitment_prices["36"] = commit_price # Store for notes
            
#             if on_demand_price_gpu:
#                 display_name_hgx = f"{assumed_chips_for_section}x {base_gpu_model_for_section} (On-Demand)"
#                 notes_hgx = f"HGX Configuration (assumed {assumed_chips_for_section}x)."
#                 if commitment_prices["24"]: notes_hgx += f" 24mo commit: ${commitment_prices['24']:.2f}/GPU/hr."
#                 if commitment_prices["36"]: notes_hgx += f" 36mo commit: ${commitment_prices['36']:.2f}/GPU/hr."
#                 gpu_id_neev = f"neev_{assumed_chips_for_section}x_{gpu_variant_name_section.replace(' ','_')}_ondemand_hgx"
                
#                 base_info_hgx = {
#                     "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
#                     "Region": STATIC_REGION_INFO, "GPU ID": gpu_id_neev,
#                     "GPU (H100 or H200 or L40S)": gpu_family_section, "Memory (GB)": vram_gb,
#                     "Display Name(GPU Type)": display_name_hgx, "GPU Variant Name": gpu_variant_name_section,
#                     "Storage Option": STATIC_STORAGE_OPTION_NEEV, "Amount of Storage": "N/A (HGX Node)",
#                     "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_NEEV,
#                     "Number of Chips": assumed_chips_for_section,
#                     "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
#                     "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
#                     "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
#                     "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A", # Will be updated by generate_periodic_rows
#                     "Notes / Features": notes_hgx.strip(),
#                 }
#                 final_data_for_sheet.extend(generate_periodic_rows(base_info_hgx, assumed_chips_for_section, on_demand_price_gpu, commitment_prices["12"]))
#             else:
#                 logger.warning(f"  No on-demand price determined for HGX section: {section_name_full}")

#         else: # This section is for other GPUs like L40S (if named "Nvidia L40S GPU Pricing")
#             row_of_boxes_other = hr_sibling.find_next_sibling('div', class_=re.compile(r'row\s+mb-5'))
#             if not row_of_boxes_other: continue

#             pricing_boxes_other = row_of_boxes_other.find_all('div', class_='pricing_box_width')
#             for box in pricing_boxes_other:
#                 price_tag = box.find('h5', class_='pricing_choose_box_heading')
#                 if not price_tag: continue
                
#                 instance_price_hr = parse_price_neev(price_tag.get_text(strip=True))
#                 if instance_price_hr is None: continue

#                 specs_ul = box.find('ul', class_='pricing_choose_box_list')
#                 specs = extract_specs_from_pricing_box_list(specs_ul)

#                 num_chips_this_box = 1 
                
#                 display_name_this_instance = f"{num_chips_this_box}x {base_gpu_model_for_section} ({specs['vcpus']}vCPU, {specs['system_ram_gb']}GB SysRAM)"
#                 notes_this_instance = f"vCPUs: {specs['vcpus']}, System RAM: {specs['system_ram_gb']}GB, Instance Storage: {specs['ssd']}."
#                 gpu_id_neev = f"neev_{num_chips_this_box}x_{gpu_variant_name_section.replace(' ','_')}_{specs['vcpus']}vcpu_box"

#                 base_info = {
#                     "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
#                     "Region": STATIC_REGION_INFO, "GPU ID": gpu_id_neev,
#                     "GPU (H100 or H200 or L40S)": gpu_family_section, "Memory (GB)": vram_gb, # VRAM
#                     "Display Name(GPU Type)": display_name_this_instance, "GPU Variant Name": gpu_variant_name_section,
#                     "Storage Option": STATIC_STORAGE_OPTION_NEEV, "Amount of Storage": specs['ssd'],
#                     "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_NEEV,
#                     "Number of Chips": num_chips_this_box,
#                     "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
#                     "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
#                     "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
#                     "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
#                     "Notes / Features": notes_this_instance.strip(),
#                 }
#                 final_data_for_sheet.extend(generate_periodic_rows(base_info, num_chips_this_box, instance_price_hr, None))
    
#     # De-duplicate final list
#     unique_rows_dict = {}
#     if final_data_for_sheet:
#         logger.info(f"Neevcloud Handler: Starting de-duplication. Original row count: {len(final_data_for_sheet)}")
#         for row in final_data_for_sheet:
#             key_for_dedup = (
#                 row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
#                 row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
#                 # Including effective rate helps if same config offered at different on-demand prices (unlikely but possible)
#                 row.get("Effective Hourly Rate ($/hr)") 
#             )
#             if key_for_dedup not in unique_rows_dict:
#                 unique_rows_dict[key_for_dedup] = row
        
#         final_data_for_sheet = list(unique_rows_dict.values())
#         logger.info(f"Neevcloud Handler: After de-duplication. New row count: {len(final_data_for_sheet)}")

#     if final_data_for_sheet:
#         distinct_offerings_count = len(set((row["Display Name(GPU Type)"], row["Number of Chips"]) for row in final_data_for_sheet if row["Period"] == "Per Hour"))
#         logger.info(f"Neevcloud Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
#     else:
#         logger.warning(f"Neevcloud Handler: No target GPU offerings (H100, H200, L40S) found or parseable from the page.")
        
#     return final_data_for_sheet

# if __name__ == '__main__':
#     logger.info(f"Testing Neevcloud Handler. Fetching {NEEVCLOUD_PRICING_URL}...")
#     try:
#         # To fetch live and save:
#         # response = requests.get(NEEVCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
#         # response.raise_for_status()
#         # with open("neevcloud_pricing_latest.html", "w", encoding="utf-8") as f:
#         #     f.write(response.text)
#         # logger.info("Saved HTML to neevcloud_pricing_latest.html for inspection.")
#         # soup = BeautifulSoup(response.text, "html.parser")

#         # To load from file (after running once to save the HTML):
#         logger.info("Attempting to load from neevcloud_pricing_latest.html...")
#         with open("neevcloud_pricing_latest.html", "r", encoding="utf-8") as f:
#             html_content = f.read()
#         if not html_content:
#              logger.error("ERROR: neevcloud_pricing_latest.html is empty!")
#              soup = BeautifulSoup("", "html.parser") 
#         else:
#              logger.info(f"Successfully loaded HTML from file (first 500 chars): {html_content[:500]}")
#              soup = BeautifulSoup(html_content, "html.parser")
        
#         processed_data = fetch_neevcloud_data(soup)
        
#         if processed_data:
#             logger.info(f"\nSuccessfully processed {len(processed_data)} rows from Neevcloud.")
#             printed_offerings_summary = {}
#             for i, row_data in enumerate(processed_data):
#                 offering_key_print = (row_data["Display Name(GPU Type)"], row_data["Number of Chips"])
#                 if offering_key_print not in printed_offerings_summary:
#                     printed_offerings_summary[offering_key_print] = []
                
#                 period_info = f"{row_data['Period']}: Rate ${row_data['Effective Hourly Rate ($/hr)']}/GPU/hr, Total Inst Price ${row_data['Total Price ($)']}"
#                 if row_data['Period'] == 'Per Year' and row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != "N/A":
#                     period_info += f" (12mo Commit Rate: ${row_data['Commitment Discount - 12 Month Price ($/hr per GPU)']})"
#                 printed_offerings_summary[offering_key_print].append(period_info)

#             logger.info("\n--- Summary of Processed Offerings (Neevcloud) ---")
#             for (disp_name, chips), periods_info in printed_offerings_summary.items():
#                  logger.info(f"\nOffering: {disp_name} (Chips: {chips})")
#                  for p_info in periods_info:
#                      logger.info(f"  - {p_info}")
#         else:
#             logger.warning("No data processed by fetch_neevcloud_data.")
            
#     except FileNotFoundError:
#         logger.error("ERROR: neevcloud_pricing_latest.html not found for testing. Run with live fetch first to save it.")
#     except Exception as e:
#         logger.error(f"An error occurred during Neevcloud handler test: {e}")
#         import traceback
#         traceback.print_exc()



# providers/neevcloud_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

NEEVCLOUD_PRICING_URL = "https://www.neevcloud.com/pricing.php"
HOURS_IN_MONTH = 730

STATIC_PROVIDER_NAME = "Neevcloud"
STATIC_SERVICE_PROVIDED = "Neevcloud GPU Cloud Instances"
STATIC_REGION_INFO = "Multiple (US, India)"
STATIC_STORAGE_OPTION_NEEV = "Local NVMe SSD / Block Storage"
STATIC_NETWORK_PERFORMANCE_NEEV = "High-Speed Fabric (e.g., InfiniBand/Ethernet)"

def parse_price_neev(price_str):
    if not price_str: return None, "USD" 
    price_str_original_case = price_str
    price_str_lower = price_str.lower().replace(',', '')
    if "contact" in price_str_lower or "coming soon" in price_str_lower: return None, "USD"

    currency_code = "USD" 
    if "₹" in price_str_original_case:
        currency_code = "INR"
    elif "$" in price_str_original_case:
        currency_code = "USD"
    
    match = re.search(r"(\d+\.?\d*)", price_str_lower)
    if match:
        try:
            return float(match.group(1)), currency_code
        except ValueError:
            logger.warning(f"Neevcloud: Could not parse price from value '{match.group(1)}' in '{price_str_original_case}'")
            return None, currency_code
    logger.warning(f"Neevcloud: No numeric price found in '{price_str_original_case}'")
    return None, currency_code

def parse_memory_neev_from_box_list(memory_text):
    if not memory_text: return 0
    memory_text = memory_text.strip()
    match = re.search(r"(\d+)\s*(GiB|GB|TB)", memory_text, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "tb": return val * 1024 
        return val
    return 0

def get_vram_for_gpu_neev(base_gpu_model_name_cleaned):
    name_lower = base_gpu_model_name_cleaned.lower()
    if "h200" in name_lower: return 141
    if "h100" in name_lower: return 80
    if "l40s" in name_lower: return 48
    if "a40" in name_lower: return 48
    if "a30" in name_lower: return 24
    if "l4" in name_lower and "l40s" not in name_lower: return 24
    if "v100" in name_lower: return 16 
    if "rtx 8000" in name_lower: return 48
    return 0 

def get_canonical_variant_and_base_chip_neev(gpu_name_from_site):
    text_to_search = gpu_name_from_site.lower().replace("nvidia", "").replace("gpu", "").replace("price", "").replace("pricing", "").strip()
    text_to_search = re.sub(r'\s+', ' ', text_to_search).replace("graphics card","").strip()
    family = None
    variant = gpu_name_from_site 

    if "h200" in text_to_search:
        family = "H200"
        variant = "H200 HGX" if "hgx" in text_to_search or "supercluster" in text_to_search else "H200"
    elif "h100" in text_to_search:
        family = "H100"
        if "sxm" in text_to_search or "hgx" in text_to_search or "supercluster" in text_to_search: 
            variant = "H100 HGX"
        elif "pcie" in text_to_search: variant = "H100 PCIe"
        else: variant = "H100"
    elif "l40s" in text_to_search:
        family = "L40S"
        variant = "L40S" 
    
    if family in ["H100", "H200", "L40S"]:
        return variant, family
    return None, None

def extract_specs_from_pricing_box_list_neev(ul_tag):
    specs = {"system_ram_gb": 0, "vcpus": "N/A", "ssd": "N/A", "gpu_range": "N/A", "deposit": "N/A", "cluster_range": "N/A", "infiniband": "N/A", "prepaid": "N/A"}
    if not ul_tag: return specs
    for li in ul_tag.find_all('li'):
        text_content = li.get_text(separator=" ", strip=True)
        text_content_lower = text_content.lower()
        
        span_node = li.find('span')
        span_text = span_node.get_text(strip=True) if span_node else ""
        main_text_part = text_content.replace(span_text, "").strip().rstrip(':').strip()

        if "memory" in text_content_lower:
            specs["system_ram_gb"] = parse_memory_neev_from_box_list(main_text_part)
        elif "vcpu" in text_content_lower:
            match = re.search(r"(\d+)", main_text_part)
            if match: specs["vcpus"] = match.group(1)
        elif "ssd" in text_content_lower:
            specs["ssd"] = main_text_part
        elif "gpu range" in text_content_lower:
            specs["gpu_range"] = span_text if span_text else main_text_part
        elif "deposit" in text_content_lower:
            specs["deposit"] = span_text if span_text else main_text_part
        elif "cluster range" in text_content_lower:
            specs["cluster_range"] = span_text if span_text else main_text_part
        elif "infiniband" in text_content_lower:
            specs["infiniband"] = span_text if span_text else main_text_part
        elif "prepaid" in text_content_lower:
            specs["prepaid"] = span_text if span_text else main_text_part
    return specs

def generate_periodic_rows_neev(base_info_template, num_chips_for_offering, on_demand_hr_rate, currency, commit_12mo_hr_rate=None):
    rows = []
    if on_demand_hr_rate is None or num_chips_for_offering is None: 
        logger.warning(f"Neevcloud: Cannot generate rows for {base_info_template.get('Display Name(GPU Type)')} as on_demand_hr_rate or num_chips_for_offering is None.")
        return rows
        
    base_info = base_info_template.copy() # Ensure base_info_template already has "Number of Chips"
    base_info["Currency"] = currency # Explicitly set currency for these rows
    
    # Ensure Number of Chips is in the base_info before creating rows from it
    if "Number of Chips" not in base_info: # Should already be there
         base_info["Number of Chips"] = num_chips_for_offering


    base_info["Commitment Discount - 12 Month Price ($/hr per GPU)"] = (
        round(commit_12mo_hr_rate, 2) if commit_12mo_hr_rate is not None else "N/A"
    )
    base_info["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 3 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 6 Month Price ($/hr per GPU)"] = "N/A"

    total_hourly_for_instance = num_chips_for_offering * on_demand_hr_rate
    hourly_row = {**base_info, 
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_for_instance, 2), 
                  "Effective Hourly Rate ($/hr)": round(on_demand_hr_rate, 2)}
    rows.append(hourly_row)

    eff_rate_6mo = on_demand_hr_rate 
    total_6mo_instance_hourly = num_chips_for_offering * eff_rate_6mo
    total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
    six_month_row = {**base_info,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(eff_rate_6mo, 2)}
    rows.append(six_month_row)

    eff_rate_12mo = commit_12mo_hr_rate if commit_12mo_hr_rate is not None else on_demand_hr_rate
    total_12mo_instance_hourly = num_chips_for_offering * eff_rate_12mo
    total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
    yearly_row_data = {**base_info,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(eff_rate_12mo, 2)}
    rows.append(yearly_row_data)
    return rows

def process_neevcloud_section(section_element, section_id_for_log):
    section_data = []
    if not section_element:
        logger.warning(f"Neevcloud Handler: Section element for '{section_id_for_log}' not found.")
        return section_data

    section_headers = section_element.find_all('h6', class_='pricing_table_gpu_name')
    logger.info(f"Neevcloud Handler ({section_id_for_log}): Found {len(section_headers)} GPU pricing section headers.")

    for header_tag in section_headers:
        section_name_full = header_tag.get_text(strip=True)
        base_gpu_model_for_section = section_name_full.replace("Pricing", "").replace("Price", "").strip()
        gpu_variant_name_section, gpu_family_section = get_canonical_variant_and_base_chip_neev(base_gpu_model_for_section)

        if not gpu_family_section:
            continue
        
        logger.info(f"Neevcloud Handler ({section_id_for_log}): Processing section: '{section_name_full}' -> Target Family: {gpu_family_section}, Variant: {gpu_variant_name_section}")

        vram_gb = get_vram_for_gpu_neev(base_gpu_model_for_section)
        
        hr_sibling = header_tag.find_next_sibling('hr', class_='pricing_table_gpu_bottom_border')
        if not hr_sibling:
            logger.warning(f"  Neevcloud Handler ({section_id_for_log}): Could not find <hr> after header for {section_name_full}.")
            continue
        
        row_of_boxes = hr_sibling.find_next_sibling('div', class_=re.compile(r'row\s+mb-5'))
        if not row_of_boxes:
            logger.warning(f"  Neevcloud Handler ({section_id_for_log}): Could not find row of pricing boxes for {section_name_full}")
            continue
            
        pricing_boxes = row_of_boxes.find_all('div', class_=re.compile(r'pricing_box_width'))
        if not pricing_boxes:
             logger.info(f"  Neevcloud Handler ({section_id_for_log}): No pricing_box_width found for {section_name_full}.")

        default_currency = "USD" 

        if "hgx" in base_gpu_model_for_section.lower() or "supercluster" in section_name_full.lower():
            assumed_chips = 8 
            on_demand_price_hgx = None
            currency_hgx = default_currency
            commitment_rates_hgx = {"12": None, "24": None, "36": None, "48": None}
            other_notes = []

            for box in pricing_boxes:
                cross_price_tag = box.find('h6', class_='pricing_choose_box_price_cross')
                main_price_tag = box.find('h5', class_='pricing_choose_box_heading')
                term_tag = box.find('p', class_='pricing_choose_box_price_hr')
                box_specs_ul = box.find('ul', class_='pricing_choose_box_list')
                box_specs = extract_specs_from_pricing_box_list_neev(box_specs_ul)

                current_box_price, current_box_currency = parse_price_neev(main_price_tag.get_text(strip=True)) if main_price_tag else (None, default_currency)

                if cross_price_tag:
                    temp_on_demand, temp_currency = parse_price_neev(cross_price_tag.get_text(strip=True))
                    if temp_on_demand is not None and on_demand_price_hgx is None:
                        on_demand_price_hgx = temp_on_demand
                        currency_hgx = temp_currency # Prioritize currency from price string
                        logger.info(f"  Neevcloud ({section_id_for_log}): Using crossed-out price as On-Demand for {base_gpu_model_for_section}: {currency_hgx}{on_demand_price_hgx}")
                
                if main_price_tag and term_tag and current_box_price is not None:
                    term_text = term_tag.get_text(strip=True).lower()
                    if "12 months" in term_text: commitment_rates_hgx["12"] = current_box_price
                    elif "24 months" in term_text: commitment_rates_hgx["24"] = current_box_price
                    elif "36 months" in term_text: commitment_rates_hgx["36"] = current_box_price
                    elif "48 months" in term_text: commitment_rates_hgx["48"] = current_box_price
                    else:
                         other_notes.append(f"Rate {current_box_currency}{current_box_price:.2f}/GPU/hr for {term_text}")
                    if currency_hgx == "USD" and current_box_currency != "USD": # Update if term price has clearer currency
                        currency_hgx = current_box_currency

                if not cross_price_tag and main_price_tag and "pricing_choose_mar" in main_price_tag.get('class', []) and "h100" in base_gpu_model_for_section.lower() and section_id_for_log == "AI SuperCloud":
                    price_val, curr = parse_price_neev(main_price_tag.get_text(strip=True))
                    if price_val is not None:
                        if on_demand_price_hgx is None: on_demand_price_hgx = price_val # Only if not set by cross_price
                        currency_hgx = curr
                        if term_tag and "12 months" in term_tag.get_text(strip=True).lower():
                            commitment_rates_hgx["12"] = price_val
                        logger.info(f"  Neevcloud ({section_id_for_log}): Using H100 specific box price: {currency_hgx}{price_val}")
                
                # Capture specs from this box for notes
                for spec_key, spec_val in box_specs.items():
                    if spec_val != "N/A" and spec_val != 0:
                         other_notes.append(f"{spec_key.replace('_',' ').title()}: {spec_val}")

            if on_demand_price_hgx is None:
                prices_in_order = [commitment_rates_hgx["12"], commitment_rates_hgx["24"], commitment_rates_hgx["36"], commitment_rates_hgx["48"]]
                for price_val in prices_in_order:
                    if price_val is not None:
                        on_demand_price_hgx = price_val
                        logger.info(f"  Neevcloud ({section_id_for_log}): No explicit on-demand, using best commitment {currency_hgx}{on_demand_price_hgx} as proxy for {base_gpu_model_for_section}")
                        break
                if on_demand_price_hgx is None and pricing_boxes and pricing_boxes[0].find('h5', class_='pricing_choose_box_heading'): # Last resort
                    single_price, single_curr = parse_price_neev(pricing_boxes[0].find('h5', class_='pricing_choose_box_heading').get_text(strip=True))
                    if single_price:
                        on_demand_price_hgx = single_price
                        currency_hgx = single_curr
                        logger.info(f"  Neevcloud ({section_id_for_log}): Using single box price as On-Demand for {base_gpu_model_for_section}: {currency_hgx}{on_demand_price_hgx}")


            if on_demand_price_hgx is not None:
                display_name = f"{assumed_chips}x {base_gpu_model_for_section}"
                notes_str = f"Config: {gpu_variant_name_section} (assumed {assumed_chips}x GPUs/node). " + ". ".join(list(set(other_notes))) 
                gpu_id_neev = f"neev_{assumed_chips}x_{gpu_variant_name_section.replace(' ','_').lower()}_{section_id_for_log.replace(' ','_').lower()}"
                
                base_info = {
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": f"{STATIC_SERVICE_PROVIDED} ({section_id_for_log})",
                    "Region": STATIC_REGION_INFO, 
                    "GPU ID": gpu_id_neev,
                    "GPU (H100 or H200 or L40S)": gpu_family_section, "Memory (GB)": vram_gb,
                    "Display Name(GPU Type)": display_name, "GPU Variant Name": gpu_variant_name_section,
                    "Storage Option": STATIC_STORAGE_OPTION_NEEV, "Amount of Storage": "HGX Node Default", # Specs not in these boxes
                    "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_NEEV,
                    "Number of Chips": assumed_chips, # <<< EXPLICITLY ADDED
                    "Notes / Features": notes_str.strip(),
                }
                section_data.extend(generate_periodic_rows_neev(base_info, assumed_chips, on_demand_price_hgx, currency_hgx, commitment_rates_hgx["12"]))
            else:
                logger.warning(f"  Neevcloud ({section_id_for_log}): No valid on-demand or commitment price found for HGX section: {section_name_full}")

        else: # For non-HGX target GPUs
            for box in pricing_boxes:
                main_price_tag = box.find('h5', class_='pricing_choose_box_heading')
                if not main_price_tag: continue

                instance_price_hr, currency = parse_price_neev(main_price_tag.get_text(strip=True))
                if instance_price_hr is None: continue

                specs_ul = box.find('ul', class_='pricing_choose_box_list')
                specs = extract_specs_from_pricing_box_list_neev(specs_ul)
                
                num_chips_this_box = 1 
                display_name = f"{num_chips_this_box}x {base_gpu_model_for_section} ({specs.get('vcpus','N/A')}vCPU, {specs.get('system_ram_gb','N/A')}GB SysRAM)"
                notes = f"vCPUs: {specs.get('vcpus','N/A')}, System RAM: {specs.get('system_ram_gb','N/A')}GB, Storage: {specs.get('ssd','N/A')}."
                gpu_id_neev = f"neev_{num_chips_this_box}x_{gpu_variant_name_section.replace(' ','_').lower()}_{specs.get('vcpus','na')}vcpu_box"

                base_info = {
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": f"{STATIC_SERVICE_PROVIDED} ({section_id_for_log})",
                    "Region": STATIC_REGION_INFO, 
                    "GPU ID": gpu_id_neev,
                    "GPU (H100 or H200 or L40S)": gpu_family_section, "Memory (GB)": vram_gb,
                    "Display Name(GPU Type)": display_name, "GPU Variant Name": gpu_variant_name_section,
                    "Storage Option": STATIC_STORAGE_OPTION_NEEV, "Amount of Storage": specs.get('ssd','N/A'),
                    "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_NEEV,
                    "Number of Chips": num_chips_this_box, # <<< EXPLICITLY ADDED
                    "Notes / Features": notes.strip(),
                }
                section_data.extend(generate_periodic_rows_neev(base_info, num_chips_this_box, instance_price_hr, currency))
    return section_data

def fetch_neevcloud_data(soup):
    final_data_for_sheet = []
    
    if not soup or not soup.body:
        logger.error("Neevcloud Handler: HTML content seems invalid (no body tag or empty soup). Aborting.")
        return final_data_for_sheet

    ai_supercloud_section = soup.find('section', id='gpu-cloud')
    if ai_supercloud_section:
        final_data_for_sheet.extend(process_neevcloud_section(ai_supercloud_section, "AI SuperCloud"))
    else:
        logger.warning("Neevcloud Handler: Could not find the AI SuperCloud section (id='gpu-cloud').")

    ai_supercluster_section = soup.find('section', id='gpu') 
    if ai_supercluster_section:
        final_data_for_sheet.extend(process_neevcloud_section(ai_supercluster_section, "AI SuperCluster"))
    else:
        logger.warning("Neevcloud Handler: Could not find the AI SuperCluster section (id='gpu').")
    
    unique_rows_dict = {}
    if final_data_for_sheet:
        logger.info(f"Neevcloud Handler: Starting de-duplication. Original row count: {len(final_data_for_sheet)}")
        
        # ---- START DEBUG BLOCK to check for missing keys before de-duplication ----
        for i, row_debug in enumerate(final_data_for_sheet):
            if "Number of Chips" not in row_debug:
                logger.error(f"  PRE-DEDUP Row {i} is MISSING 'Number of Chips'. Row content: {row_debug}")
            if "Display Name(GPU Type)" not in row_debug:
                 logger.error(f"  PRE-DEDUP Row {i} is MISSING 'Display Name(GPU Type)'. Row content: {row_debug}")
        # ---- END DEBUG BLOCK ----

        for row in final_data_for_sheet:
            key_for_dedup = (
                row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
                row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
                row.get("Currency"), row.get("Effective Hourly Rate ($/hr)") 
            )
            if key_for_dedup not in unique_rows_dict:
                unique_rows_dict[key_for_dedup] = row
        final_data_for_sheet = list(unique_rows_dict.values())
        logger.info(f"Neevcloud Handler: After de-duplication. New row count: {len(final_data_for_sheet)}")


    if final_data_for_sheet:
        # ---- START DEBUG BLOCK to check for missing keys before count ----
        logger.info("Neevcloud Handler: Inspecting rows before creating distinct_offerings_count (after de-dup)...")
        for i, row_debug in enumerate(final_data_for_sheet):
            if row_debug.get("Period") == "Per Hour":
                if "Number of Chips" not in row_debug:
                    logger.error(f"  POST-DEDUP Row {i} (Per Hour) is MISSING 'Number of Chips'. Row content: {row_debug}")
                if "Display Name(GPU Type)" not in row_debug:
                    logger.error(f"  POST-DEDUP Row {i} (Per Hour) is MISSING 'Display Name(GPU Type)'. Row content: {row_debug}")
        # ---- END DEBUG BLOCK ----
        
        # Make the count more robust
        distinct_offerings_count = 0
        try:
            distinct_offerings_set = set()
            for row in final_data_for_sheet:
                if row.get("Period") == "Per Hour":
                    # Ensure keys exist before trying to access them for the set
                    display_name = row.get("Display Name(GPU Type)")
                    num_chips_val = row.get("Number of Chips")
                    if display_name is not None and num_chips_val is not None:
                        distinct_offerings_set.add((display_name, num_chips_val))
                    else:
                        logger.warning(f"Skipping row for distinct_offerings_count due to missing keys: {row}")
            distinct_offerings_count = len(distinct_offerings_set)
        except KeyError as e:
            logger.error(f"A KeyError occurred during distinct_offerings_count calculation: {e}. This should not happen with .get().")
        
        logger.info(f"Neevcloud Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        logger.warning(f"Neevcloud Handler: No target GPU offerings (H100, H200, L40S) found or parseable from Neevcloud.")
        
    return final_data_for_sheet


if __name__ == '__main__':
    logger.info(f"Testing Neevcloud Handler. Fetching {NEEVCLOUD_PRICING_URL}...")
    html_content = None
    try:
        response = requests.get(NEEVCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        logger.info(f"Neevcloud: HTTP Status Code: {response.status_code}")
        response.raise_for_status()
        html_content = response.text
        
        if html_content:
            logger.info(f"Neevcloud: Fetched content (first 500 chars): {html_content[:500]}")
            with open("neevcloud_pricing_latest.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("Saved HTML to neevcloud_pricing_latest.html for inspection.")
        else:
            logger.warning("Neevcloud: Fetched content is empty.")
            
    except requests.exceptions.RequestException as e_req:
        logger.error(f"Error fetching Neevcloud page (RequestException): {e_req}")
    except Exception as e_generic_fetch:
        logger.error(f"Generic error fetching Neevcloud page: {e_generic_fetch}")
        import traceback
        traceback.print_exc()

    if not html_content:
        logger.info("Neevcloud: Live fetch failed or produced no content. Attempting to load from local file neevcloud_pricing_latest.html (if it exists).")
        try:
            with open("neevcloud_pricing_latest.html", "r", encoding="utf-8") as f:
                html_content = f.read()
            logger.info("Loaded HTML from local file: neevcloud_pricing_latest.html")
        except FileNotFoundError:
            logger.error("Local HTML file neevcloud_pricing_latest.html not found.")
        except Exception as e_file_read:
            logger.error(f"Error reading local HTML file: {e_file_read}")

    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        if not soup.body:
            logger.error("Neevcloud Handler (Standalone Test): Parsed HTML content does not have a body tag. Cannot parse further.")
            logger.info("Please inspect 'neevcloud_pricing_latest.html' to see what was actually fetched.")
        else:
            processed_data = fetch_neevcloud_data(soup)
            
            if processed_data:
                logger.info(f"\nSuccessfully processed {len(processed_data)} rows from Neevcloud.")
                printed_offerings_summary = {}
                for i, row_data in enumerate(processed_data):
                    # Defensive access for printing summary
                    display_name = row_data.get("Display Name(GPU Type)", "Unknown Display Name")
                    num_chips_val = row_data.get("Number of Chips", "Unknown Chips")
                    offering_key_print = (display_name, num_chips_val)
                    
                    if offering_key_print not in printed_offerings_summary:
                        printed_offerings_summary[offering_key_print] = []
                    
                    period_info = f"{row_data.get('Period','N/A')}: Currency {row_data.get('Currency','N/A')}, Rate {row_data.get('Effective Hourly Rate ($/hr)','N/A')}/GPU/hr, Total Inst Price {row_data.get('Total Price ($)','N/A')}"
                    commit_12_price = row_data.get('Commitment Discount - 12 Month Price ($/hr per GPU)', "N/A")
                    effective_rate = row_data.get('Effective Hourly Rate ($/hr)', "N/A")

                    if row_data.get('Period') == 'Per Year' and commit_12_price != "N/A":
                         if commit_12_price != effective_rate : # Only show if different from effective rate
                             period_info += f" (12mo Commit Rate: {commit_12_price})"
                    printed_offerings_summary[offering_key_print].append(period_info)

                logger.info("\n--- Summary of Processed Offerings (Neevcloud) ---")
                for (disp_name, chips), periods_info in printed_offerings_summary.items():
                     logger.info(f"\nOffering: {disp_name} (Chips: {chips})")
                     for p_info in periods_info:
                         logger.info(f"  - {p_info}")
            else:
                logger.warning("No data processed by fetch_neevcloud_data.")
    else:
        logger.warning("No HTML content for Neevcloud page (either from fetch or local file), cannot parse.")