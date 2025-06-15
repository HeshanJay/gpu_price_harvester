# providers/sakura_internet_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SAKURA_VRT_PRICING_URL = "https://cloud.sakura.ad.jp/products/server/gpu/"
SAKURA_PHY_PRICING_URL = "https://www.sakura.ad.jp/koukaryoku-phy/"
HOURS_IN_MONTH = 730

STATIC_PROVIDER_NAME = "Sakura Internet"
STATIC_SERVICE_PROVIDED = "Sakura Cloud GPU Services"
# VRT H100 is in Ishikari Zone 2. PHY is also in Ishikari Data Center.
STATIC_REGION_INFO = "Japan (Ishikari)"
STATIC_STORAGE_OPTION_SAKURA = "Local SSD / NVMe (Instance specific)"
STATIC_NETWORK_PERFORMANCE_SAKURA = "High-Speed Fabric"

def parse_price_sakura(price_str):
    """Parse price string in JPY (e.g., "990円", "3,046,120円") to float."""
    if not price_str:
        return None
    # Remove commas and "円" (yen symbol), and any surrounding whitespace
    price_str_cleaned = price_str.replace(',', '').replace('円', '').strip()
    # Handle cases like "500円（税込990円）" - try to get the primary number
    match = re.match(r"(\d+)", price_str_cleaned) # Get the first number
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            logger.warning(f"Sakura: Could not parse price from: {price_str}")
            return None
    return None

def get_canonical_variant_and_base_chip_sakura(gpu_name_str):
    text_to_search = gpu_name_str.lower()
    family = None
    variant = gpu_name_str # Default

    if "h100" in text_to_search:
        family = "H100"
        if "sxm" in text_to_search:
            variant = "H100 SXM"
        elif "pcie" in text_to_search: # Not currently seen for Sakura H100 but good to have
            variant = "H100 PCIe"
        else: # For "NVIDIA H100 beta version"
            variant = "H100" 
    # Add H200/L40S if they appear on Sakura's pages later
    # elif "h200" in text_to_search:
    #     family = "H200"
    #     variant = "H200"
    # elif "l40s" in text_to_search:
    #     family = "L40S"
    #     variant = "L40S"

    if family == "H100": # Currently only processing H100 for Sakura based on findings
        return variant, family
    return None, None

def generate_periodic_rows_sakura(base_info, num_chips, on_demand_hr_rate_jpy, effective_monthly_rate_jpy=None):
    rows = []
    if on_demand_hr_rate_jpy is None:
        logger.warning(f"Sakura: Cannot generate rows for {base_info.get('Display Name(GPU Type)')} as on_demand_hr_rate is None.")
        return rows
        
    base_info_copy = base_info.copy()
    # For Sakura, specific commitment discount columns might not directly map from monthly rates.
    # We'll use the on-demand or effective monthly rate for calculations.
    # The "Commitment Discount - 1 Month Price" could be the effective hourly from monthly.
    
    one_month_commit_hourly_rate = None
    if effective_monthly_rate_jpy and num_chips > 0:
        one_month_commit_hourly_rate = (effective_monthly_rate_jpy / num_chips) / HOURS_IN_MONTH
        base_info_copy["Commitment Discount - 1 Month Price ($/hr per GPU)"] = round(one_month_commit_hourly_rate, 2)


    total_hourly_for_instance = num_chips * on_demand_hr_rate_jpy
    hourly_row = {**base_info_copy, 
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_for_instance, 2), # This will be JPY value
                  "Effective Hourly Rate ($/hr)": round(on_demand_hr_rate_jpy, 2)} # This is JPY value
    rows.append(hourly_row)

    # For 6 month and 1 year, use the on-demand rate if no specific commitment rate is parsed for these periods
    eff_rate_for_calc = on_demand_hr_rate_jpy 
    if one_month_commit_hourly_rate and one_month_commit_hourly_rate < eff_rate_for_calc : # if monthly derived rate is better
        # This is debatable for 6mo/12mo projection, but using it if it's the only "commitment" data point
        # eff_rate_for_calc = one_month_commit_hourly_rate 
        pass # Sticking to on-demand for longer term unless specific rates are given for those terms


    total_6mo_instance_hourly = num_chips * eff_rate_for_calc
    total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
    six_month_row = {**base_info_copy,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(eff_rate_for_calc, 2)}
    rows.append(six_month_row)

    total_12mo_instance_hourly = num_chips * eff_rate_for_calc
    total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
    yearly_row_data = {**base_info_copy,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(eff_rate_for_calc, 2)}
    rows.append(yearly_row_data)
    return rows

def fetch_sakura_internet_data(soup_vrt, soup_phy): # Takes two soup objects
    final_data_for_sheet = []

    # 1. Parse VRT Page (https://cloud.sakura.ad.jp/products/server/gpu/)
    logger.info("Sakura Handler: Parsing VRT page...")
    if soup_vrt:
        try:
            price_list_table = soup_vrt.find('table', class_='price-list_02')
            if price_list_table:
                rows = price_list_table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) == 4: # Plan Name, Monthly, Daily, Hourly
                        plan_name_tag = cols[0]
                        plan_name = plan_name_tag.get_text(strip=True)
                        
                        hourly_price_str = cols[3].get_text(strip=True)
                        monthly_price_str = cols[1].get_text(strip=True) # For notes or context

                        if "h100" in plan_name.lower():
                            gpu_variant, gpu_family = get_canonical_variant_and_base_chip_sakura(plan_name)
                            if gpu_family:
                                hourly_price_jpy = parse_price_sakura(hourly_price_str)
                                if hourly_price_jpy:
                                    num_chips = 1 # Assume 1x for VRT H100 plan
                                    vram_gb = 80  # Assume 80GB for H100
                                    display_name = plan_name
                                    gpu_id = f"sakura_vrt_1x_{gpu_variant.replace(' ','_')}"
                                    notes = f"VRT Plan. Monthly: {monthly_price_str}. Daily: {cols[2].get_text(strip=True)}. Ishikari Zone 2. Temporary high-speed storage available."

                                    base_info = {
                                        "Provider Name": STATIC_PROVIDER_NAME,
                                        "Service Provided": f"{STATIC_SERVICE_PROVIDED} (VRT Plan)",
                                        "Region": STATIC_REGION_INFO,
                                        "Currency": "JPY",
                                        "GPU ID": gpu_id,
                                        "GPU (H100 or H200 or L40S)": gpu_family,
                                        "Memory (GB)": vram_gb,
                                        "Display Name(GPU Type)": display_name,
                                        "GPU Variant Name": gpu_variant,
                                        "Storage Option": STATIC_STORAGE_OPTION_SAKURA,
                                        "Amount of Storage": "Host dependent, temp storage available",
                                        "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_SAKURA,
                                        "Number of Chips": num_chips,
                                        "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
                                        "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                                        "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                                        "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
                                        "Notes / Features": notes,
                                    }
                                    final_data_for_sheet.extend(generate_periodic_rows_sakura(base_info, num_chips, hourly_price_jpy))
            else:
                logger.warning("Sakura Handler: VRT price list table not found.")
        except Exception as e:
            logger.error(f"Sakura Handler: Error parsing VRT page: {e}")
            # import traceback; traceback.print_exc()


    # 2. Parse PHY Page (https://www.sakura.ad.jp/koukaryoku-phy/)
    logger.info("Sakura Handler: Parsing PHY page...")
    if soup_phy:
        try:
            # Find H100 PHY specification
            gpu_spec_header = soup_phy.find('h3', string=re.compile("仕様")) # "Specifications"
            if gpu_spec_header:
                spec_table = gpu_spec_header.find_next_sibling('table', class_='table')
                if spec_table:
                    phy_specs = {}
                    for row in spec_table.find_all('tr'):
                        th = row.find('th')
                        td = row.find('td')
                        if th and td:
                            key = th.get_text(strip=True).lower()
                            value = td.get_text(separator=" ", strip=True)
                            phy_specs[key] = value
                    
                    gpu_text_phy = phy_specs.get('gpu')
                    if gpu_text_phy and "h100 sxm 80gb x 8" in gpu_text_phy.lower():
                        gpu_variant, gpu_family = "H100 SXM", "H100"
                        num_chips = 8
                        vram_gb = 80
                        display_name = "8x NVIDIA H100 SXM (PHY Bare Metal)"
                        
                        # Find PHY Price
                        price_header = soup_phy.find('h3', string=re.compile("料金")) # "Price"
                        monthly_price_jpy = None
                        if price_header:
                            price_box = price_header.find_next_sibling('div', class_='price__box')
                            if price_box:
                                dd_tag = price_box.find('dd')
                                if dd_tag:
                                    monthly_price_jpy = parse_price_sakura(dd_tag.get_text(strip=True))
                        
                        if monthly_price_jpy:
                            effective_hourly_per_gpu_jpy = (monthly_price_jpy / num_chips) / HOURS_IN_MONTH
                            gpu_id = f"sakura_phy_{num_chips}x_{gpu_variant.replace(' ','_')}"
                            notes = f"PHY Bare Metal Server. CPU: {phy_specs.get('cpu','N/A')}. Server RAM: {phy_specs.get('メモリ','N/A')}. Server Storage: {phy_specs.get('ストレージ','N/A')}."
                            notes += " Primarily monthly billing. For annual, contact sales."

                            base_info = {
                                "Provider Name": STATIC_PROVIDER_NAME,
                                "Service Provided": f"{STATIC_SERVICE_PROVIDED} (PHY Bare Metal)",
                                "Region": STATIC_REGION_INFO,
                                "Currency": "JPY",
                                "GPU ID": gpu_id,
                                "GPU (H100 or H200 or L40S)": gpu_family,
                                "Memory (GB)": vram_gb,
                                "Display Name(GPU Type)": display_name,
                                "GPU Variant Name": gpu_variant,
                                "Storage Option": STATIC_STORAGE_OPTION_SAKURA,
                                "Amount of Storage": phy_specs.get('ストレージ','N/A'),
                                "Network Performance (Gbps)": phy_specs.get('ローカル回線インターコネクト（広帯域ロスレスネットワーク）※1 ※2', STATIC_NETWORK_PERFORMANCE_SAKURA),
                                "Number of Chips": num_chips,
                                "Commitment Discount - 1 Month Price ($/hr per GPU)": round(effective_hourly_per_gpu_jpy, 2), # Treating this as a 1-mo commit rate
                                "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                                "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                                "Commitment Discount - 12 Month Price ($/hr per GPU)": "Contact Sales",
                                "Notes / Features": notes,
                            }
                            # Use the effective hourly from monthly as the base rate for this offering
                            final_data_for_sheet.extend(generate_periodic_rows_sakura(base_info, num_chips, effective_hourly_per_gpu_jpy, effective_hourly_per_gpu_jpy if "12 month" in notes.lower() else None)) # Pass effective as 12mo if it's the only commit data
                        else:
                            logger.warning("Sakura Handler: Could not find monthly price for PHY H100.")
                    else:
                        logger.info("Sakura Handler: PHY specification is not for H100 8xSXM or not found.")
                else:
                    logger.warning("Sakura Handler: PHY specification table not found.")
            else:
                logger.warning("Sakura Handler: PHY specification header not found.")
        except Exception as e:
            logger.error(f"Sakura Handler: Error parsing PHY page: {e}")
            # import traceback; traceback.print_exc()

    # De-duplicate final list
    unique_rows_dict = {}
    if final_data_for_sheet:
        for row in final_data_for_sheet:
            key = (
                row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
                row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
                row.get("Currency"), row.get("Effective Hourly Rate ($/hr)")
            )
            if key not in unique_rows_dict:
                unique_rows_dict[key] = row
    final_data_for_sheet = list(unique_rows_dict.values())

    if final_data_for_sheet:
        distinct_offerings_count = len(set((row["Display Name(GPU Type)"], row["Number of Chips"]) for row in final_data_for_sheet if row["Period"] == "Per Hour"))
        logger.info(f"Sakura Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows for Sheet.")
    else:
        logger.warning(f"Sakura Handler: No target GPU offerings (H100) found or parseable from Sakura Internet.")
        
    return final_data_for_sheet


if __name__ == '__main__':
    logger.info(f"Testing Sakura Internet Handler...")
    
    html_vrt_content = None
    html_phy_content = None

    try:
        logger.info(f"Fetching VRT page: {SAKURA_VRT_PRICING_URL}")
        response_vrt = requests.get(SAKURA_VRT_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response_vrt.raise_for_status()
        html_vrt_content = response_vrt.text
        with open("sakura_vrt_pricing_latest.html", "w", encoding="utf-8") as f:
            f.write(html_vrt_content)
        logger.info("Saved VRT HTML to sakura_vrt_pricing_latest.html for inspection.")
    except Exception as e:
        logger.error(f"Error fetching Sakura VRT page: {e}. Trying to load from local file if exists.")
        try:
            with open("sakura_vrt_pricing_latest.html", "r", encoding="utf-8") as f:
                html_vrt_content = f.read()
            logger.info("Loaded VRT HTML from local file.")
        except FileNotFoundError:
            logger.error("Local VRT HTML file not found.")

    try:
        logger.info(f"Fetching PHY page: {SAKURA_PHY_PRICING_URL}")
        response_phy = requests.get(SAKURA_PHY_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response_phy.raise_for_status()
        html_phy_content = response_phy.text
        with open("sakura_phy_pricing_latest.html", "w", encoding="utf-8") as f:
            f.write(html_phy_content)
        logger.info("Saved PHY HTML to sakura_phy_pricing_latest.html for inspection.")
    except Exception as e:
        logger.error(f"Error fetching Sakura PHY page: {e}. Trying to load from local file if exists.")
        try:
            with open("sakura_phy_pricing_latest.html", "r", encoding="utf-8") as f:
                html_phy_content = f.read()
            logger.info("Loaded PHY HTML from local file.")
        except FileNotFoundError:
            logger.error("Local PHY HTML file not found.")

    soup_vrt_obj = BeautifulSoup(html_vrt_content, "html.parser") if html_vrt_content else BeautifulSoup("", "html.parser")
    soup_phy_obj = BeautifulSoup(html_phy_content, "html.parser") if html_phy_content else BeautifulSoup("", "html.parser")
        
    processed_data = fetch_sakura_internet_data(soup_vrt_obj, soup_phy_obj)
    
    if processed_data:
        logger.info(f"\nSuccessfully processed {len(processed_data)} rows from Sakura Internet.")
        # Print summary
        printed_offerings_summary = {}
        for i, row_data in enumerate(processed_data):
            offering_key_print = (row_data["Display Name(GPU Type)"], row_data["Number of Chips"])
            if offering_key_print not in printed_offerings_summary:
                printed_offerings_summary[offering_key_print] = []
            
            period_info = f"{row_data['Period']}: Currency {row_data['Currency']}, Rate {row_data['Effective Hourly Rate ($/hr)']}/GPU/hr, Total Inst Price {row_data['Total Price ($)']}"
            if row_data['Period'] == 'Per Year' and row_data['Commitment Discount - 12 Month Price ($/hr per GPU)'] != "N/A":
                period_info += f" (12mo Commit Rate: {row_data['Commitment Discount - 12 Month Price ($/hr per GPU)']})"
            printed_offerings_summary[offering_key_print].append(period_info)

        logger.info("\n--- Summary of Processed Offerings (Sakura Internet) ---")
        for (disp_name, chips), periods_info in printed_offerings_summary.items():
                logger.info(f"\nOffering: {disp_name} (Chips: {chips})")
                for p_info in periods_info:
                    logger.info(f"  - {p_info}")
    else:
        logger.warning("No data processed by fetch_sakura_internet_data.")