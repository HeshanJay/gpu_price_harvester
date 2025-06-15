# providers/scaleway_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- URLs for Scaleway Products ---
SCALEWAY_H100_URL = "https://www.scaleway.com/en/h100-pcie-try-it-now/"
SCALEWAY_L40S_URL = "https://www.scaleway.com/en/l40s-gpu-instance/"
HOURS_IN_MONTH = 730

# --- Static Information ---
STATIC_PROVIDER_NAME = "Scaleway"
STATIC_SERVICE_PROVIDED = "Scaleway GPU Instances"
STATIC_REGION_INFO = "Europe (Paris, Amsterdam, Warsaw)" 
STATIC_STORAGE_OPTION = "Local NVMe SSD / Block Storage"
STATIC_NETWORK_PERFORMANCE = "High-Speed Internal Network"

# --- Parsing Helper Functions ---

def parse_price_scaleway(price_str):
    """Parses price string like '€28.32' or '€2.10/hour' into a float."""
    if not price_str or "contact" in price_str.lower() or "coming soon" in price_str.lower():
        return None
    
    price_str_cleaned = price_str.replace(',', '').replace('€', '').replace('$', '').replace('/hour', '').strip()
    match = re.search(r"(\d+\.?\d*)", price_str_cleaned)
    
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            logger.warning(f"Scaleway: Could not parse price from value: '{match.group(1)}' in string: '{price_str}'")
            return None
    logger.warning(f"Scaleway: No numeric price found in string: '{price_str}'")
    return None

def get_canonical_variant_and_base_chip_scaleway(gpu_name_str):
    """Determines the canonical GPU variant and base chip family."""
    text_to_search = str(gpu_name_str).lower()
    family = None
    variant = gpu_name_str

    if "h100" in text_to_search:
        family = "H100"
        if "sxm" in text_to_search:
            variant = "H100 SXM"
        else:
            variant = "H100 PCIe"
    elif "l40s" in text_to_search:
        family = "L40S"
        variant = "L40S"
        
    if family in ["H100", "L40S"]:
        return variant, family
    return None, None

# --- Standardized Row Generation ---

def generate_periodic_rows_scaleway(base_info_template, num_chips, per_gpu_hourly_rate_eur):
    """Generates the standard hourly, 6-month, and yearly rows for an offering."""
    rows = []
    if per_gpu_hourly_rate_eur is None or not num_chips:
        logger.warning(f"Scaleway: Cannot generate rows for {base_info_template.get('Display Name(GPU Type)')}, missing rate or chip count.")
        return rows
        
    base_info = base_info_template.copy()
    base_info["Number of Chips"] = num_chips
    
    base_info["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 3 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 6 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 12 Month Price ($/hr per GPU)"] = "N/A"

    total_hourly_instance_price = num_chips * per_gpu_hourly_rate_eur
    hourly_row = {**base_info,
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_instance_price, 2),
                  "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_rate_eur, 2)}
    rows.append(hourly_row)

    total_6mo_price = total_hourly_instance_price * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_hourly_instance_price:.2f} ({total_6mo_price:.2f})"
    six_month_row = {**base_info,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_rate_eur, 2)}
    rows.append(six_month_row)
    
    total_yearly_price = total_hourly_instance_price * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_hourly_instance_price:.2f} ({total_yearly_price:.2f})"
    yearly_row = {**base_info,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_rate_eur, 2)}
    rows.append(yearly_row)
    
    return rows

# --- Page-Specific Parsers ---

def parse_h100_page(soup):
    """Parses the table-based H100 pricing page."""
    offerings = []
    section_heading = soup.find('h2', string=re.compile("Choose your instance's format"))
    if not section_heading:
        logger.warning("Scaleway H100 Page: Could not find the 'Choose your instance's format' section.")
        return offerings

    table = section_heading.find_next('table')
    if not table:
        logger.warning("Scaleway H100 Page: Found the heading but could not find the subsequent pricing table.")
        return offerings

    rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
    logger.info(f"Scaleway H100 Page: Found {len(rows)} rows in the pricing table.")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5: continue

        instance_name, gpu_count_str, tflops_str, vram_str, price_str = [c.get_text(strip=True) for c in cols[:5]]
        
        variant, family = get_canonical_variant_and_base_chip_scaleway(instance_name)
        if not family: continue

        total_instance_price_eur = parse_price_scaleway(price_str)
        if total_instance_price_eur is None: continue

        num_chips_match = re.search(r'(\d+)', gpu_count_str)
        num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
        
        vram_match = re.search(r'(\d+)', vram_str)
        vram_gb = int(vram_match.group(1)) if vram_match else 80

        per_gpu_hourly_rate = total_instance_price_eur / num_chips if num_chips > 0 else 0
        display_name = f"{num_chips}x {variant} ({instance_name})"
        gpu_id = f"scaleway_h100_{instance_name.lower().replace(' ','-')}"
        notes = f"TFLOPs FP16: {tflops_str}"

        base_info = {
            "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": STATIC_REGION_INFO, "Currency": "EUR", "GPU ID": gpu_id,
            "GPU (H100 or H200 or L40S)": family, "Memory (GB)": vram_gb,
            "Display Name(GPU Type)": display_name, "GPU Variant Name": variant,
            "Storage Option": STATIC_STORAGE_OPTION, "Amount of Storage": "Refer to technical specs",
            "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE,
            "Notes / Features": notes,
        }
        offerings.extend(generate_periodic_rows_scaleway(base_info, num_chips, per_gpu_hourly_rate))
        
    return offerings

def parse_l40s_page(soup):
    """Parses the table-based L40S pricing page."""
    offerings = []
    section_heading = soup.find('h2', string=re.compile("Scale your infrastructure effortlessly"))
    if not section_heading:
        logger.warning("Scaleway L40S Page: Could not find the 'Scale your infrastructure' section.")
        return offerings
        
    table = section_heading.find_next('table')
    if not table:
        logger.warning("Scaleway L40S Page: Found the heading but could not find the subsequent pricing table.")
        return offerings

    rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
    logger.info(f"Scaleway L40S Page: Found {len(rows)} rows in the pricing table.")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5: continue

        instance_name, gpu_spec_str, tflops_str, vram_str, price_str = [c.get_text(strip=True) for c in cols[:5]]

        variant, family = get_canonical_variant_and_base_chip_scaleway(gpu_spec_str)
        if not family: continue

        instance_price_eur = parse_price_scaleway(price_str)
        if instance_price_eur is None: continue
            
        num_chips = 1
        match = re.search(r'(\d+)\s*x', gpu_spec_str, re.IGNORECASE)
        if match: num_chips = int(match.group(1))

        per_gpu_hourly_rate = instance_price_eur / num_chips if num_chips > 0 else 0
        vram_gb = 48
        
        display_name = f"{num_chips}x {variant} ({instance_name})"
        gpu_id = f"scaleway_l40s_{instance_name.lower().replace(' ','-')}"
        notes = f"TFLOPs FP16: {tflops_str}"

        base_info = {
            "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": STATIC_REGION_INFO, "Currency": "EUR", "GPU ID": gpu_id,
            "GPU (H100 or H200 or L40S)": family, "Memory (GB)": vram_gb,
            "Display Name(GPU Type)": display_name, "GPU Variant Name": variant,
            "Storage Option": STATIC_STORAGE_OPTION, "Amount of Storage": "Instance-specific",
            "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE,
            "Notes / Features": notes,
        }
        offerings.extend(generate_periodic_rows_scaleway(base_info, num_chips, per_gpu_hourly_rate))

    return offerings

# --- Main Handler Function ---
def fetch_scaleway_data(soup_h100, soup_l40s):
    """Main function to fetch data from both Scaleway pages and combine them."""
    all_offerings = []
    
    if soup_h100 and soup_h100.body:
        all_offerings.extend(parse_h100_page(soup_h100))
    else:
        logger.warning("Scaleway Handler: No valid soup provided for H100 page.")
        
    if soup_l40s and soup_l40s.body:
        all_offerings.extend(parse_l40s_page(soup_l40s))
    else:
        logger.warning("Scaleway Handler: No valid soup provided for L40S page.")

    return all_offerings

# --- Standalone Test Execution ---
if __name__ == '__main__':
    logger.info("Testing Scaleway Handler with local HTML files...")
    
    html_h100, html_l40s = None, None

    try:
        with open("H100 GPU instance _ Scaleway.html", "r", encoding="utf-8") as f:
            html_h100 = f.read()
        logger.info("Successfully loaded H100 HTML from local file.")
    except FileNotFoundError:
        logger.error("Local file 'H100 GPU instance _ Scaleway.html' not found.")

    try:
        with open("L40S GPU Instance _ Scaleway.html", "r", encoding="utf-8") as f:
            html_l40s = f.read()
        logger.info("Successfully loaded L40S HTML from local file.")
    except FileNotFoundError:
        logger.error("Local file 'L40S GPU Instance _ Scaleway.html' not found.")
        
    soup_h100_obj = BeautifulSoup(html_h100, "html.parser") if html_h100 else BeautifulSoup("", "html.parser")
    soup_l40s_obj = BeautifulSoup(html_l40s, "html.parser") if html_l40s else BeautifulSoup("", "html.parser")
    
    processed_data = fetch_scaleway_data(soup_h100_obj, soup_l40s_obj)
    
    if processed_data:
        logger.info(f"\nSuccessfully processed {len(processed_data)} total rows from Scaleway.")
        # ... (rest of the printing logic for summary)
    else:
        logger.warning("No data processed by fetch_scaleway_data.")