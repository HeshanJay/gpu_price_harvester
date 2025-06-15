# providers/koyeb_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KOYEB_PRICING_URL = "https://www.koyeb.com/pricing"
HOURS_IN_MONTH = 730

STATIC_PROVIDER_NAME = "Koyeb"
STATIC_SERVICE_PROVIDED = "Koyeb Serverless Compute"
STATIC_REGION_INFO = "US, Europe, Asia"
STATIC_STORAGE_OPTION = "Local NVMe SSD"
STATIC_NETWORK_PERFORMANCE = "High-Speed Internal Network"

def parse_price_koyeb(price_str):
    """Parses price string like '$3.30 /hr' into a float."""
    if not price_str:
        return None
    
    price_str_cleaned = price_str.lower().replace('$', '').replace('/hr', '').strip()
    match = re.search(r"(\d+\.?\d*)", price_str_cleaned)
    
    if match:
        try:
            return float(match.group(1))
        except (ValueError, TypeError):
            logger.warning(f"Koyeb: Could not parse price from value: '{match.group(1)}' in string: '{price_str}'")
            return None
    return None

def get_canonical_variant_and_base_chip_koyeb(gpu_name_str):
    """Determines the canonical GPU variant and base chip family."""
    text_to_search = str(gpu_name_str).lower()
    family = None
    variant = gpu_name_str.replace('NVIDIA ', '')

    if "h100" in text_to_search:
        family = "H100"
        variant = "H100" # Page does not specify PCIe/SXM, so using a generic name
    elif "l40s" in text_to_search:
        family = "L40S"
        variant = "L40S"
    elif "h200" in text_to_search:
        family = "H200"
        variant = "H200"
        
    if family:
        return variant, family
    return None, None

def generate_periodic_rows_koyeb(base_info, num_chips, per_gpu_hourly_rate):
    """Generates the standard hourly, 6-month, and yearly rows for an offering."""
    rows = []
    if per_gpu_hourly_rate is None or not num_chips:
        return rows

    base_info["Number of Chips"] = num_chips
    base_info["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 3 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 6 Month Price ($/hr per GPU)"] = "N/A"
    base_info["Commitment Discount - 12 Month Price ($/hr per GPU)"] = "N/A"

    total_hourly_instance_price = num_chips * per_gpu_hourly_rate
    
    # Per Hour
    hourly_row = {**base_info,
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_instance_price, 2),
                  "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_rate, 2)}
    rows.append(hourly_row)

    # Per 6 Months
    total_6mo_price = total_hourly_instance_price * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_hourly_instance_price:.2f} ({total_6mo_price:.2f})"
    six_month_row = {**base_info,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_rate, 2)}
    rows.append(six_month_row)
    
    # Per Year
    total_yearly_price = total_hourly_instance_price * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_hourly_instance_price:.2f} ({total_yearly_price:.2f})"
    yearly_row = {**base_info,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_rate, 2)}
    rows.append(yearly_row)
    
    return rows

def fetch_koyeb_data(soup):
    """Fetches data from the Koyeb pricing page using a more robust selector strategy."""
    final_data = []
    
    section_heading = soup.find('h2', string=re.compile("Serverless Compute"))
    if not section_heading:
        logger.error("Koyeb: Could not find the 'Serverless Compute' section heading.")
        return []

    parent_container = section_heading.find_parent('section')
    if not parent_container:
        logger.error("Koyeb: Could not find parent section of the 'Serverless Compute' heading.")
        return []
    
    desktop_grid = parent_container.find('div', class_=re.compile("hidden.*grid-cols-5"))
    if not desktop_grid:
        logger.warning("Koyeb: Desktop grid not found. The site structure might have changed.")
        return []

    cells = desktop_grid.find_all('div', recursive=False)
    if len(cells) <= 5:
        logger.warning("Koyeb: No data rows found in the pricing grid.")
        return []

    # The first 5 cells are headers, so we start processing from the 6th cell (index 5)
    for i in range(5, len(cells), 5):
        instance_div, vcpu_div, ram_div, disk_div, price_div = cells[i:i+5]
        
        instance_name_tag = instance_div.find('div', class_='row')
        instance_name = instance_name_tag.get_text(strip=True) if instance_name_tag else "N/A"
        
        vram_tag = instance_div.find('div', class_='text-dark/50')
        vram_str = vram_tag.get_text(strip=True) if vram_tag else ""
        
        price_str = price_div.get_text(strip=True)
        
        variant, family = get_canonical_variant_and_base_chip_koyeb(instance_name)
        if not family:
            continue

        total_instance_price = parse_price_koyeb(price_str)
        if total_instance_price is None:
            continue

        num_chips_match = re.match(r'(\d+)x', instance_name, re.IGNORECASE)
        num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
        
        per_gpu_hourly_rate = total_instance_price / num_chips if num_chips > 0 else 0

        vram_gb = 0
        vram_match = re.search(r'(\d+)', vram_str)
        if vram_match:
            vram_gb = int(vram_match.group(1))
        
        # Normalize VRAM for multi-GPU instances
        if num_chips > 1 and vram_gb > 0:
            vram_gb = vram_gb / num_chips

        gpu_id = f"koyeb_{instance_name.lower().replace(' ','-')}"
        notes = f"vCPU: {vcpu_div.get_text(strip=True)}, RAM: {ram_div.get_text(strip=True)}, Disk: {disk_div.get_text(strip=True)}"

        base_info = {
            "Provider Name": STATIC_PROVIDER_NAME,
            "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": STATIC_REGION_INFO,
            "Currency": "USD",
            "GPU ID": gpu_id,
            "GPU (H100 or H200 or L40S)": family,
            "Memory (GB)": int(vram_gb),
            "Display Name(GPU Type)": instance_name,
            "GPU Variant Name": variant,
            "Storage Option": STATIC_STORAGE_OPTION,
            "Amount of Storage": disk_div.get_text(strip=True),
            "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE,
            "Notes / Features": notes,
        }
        final_data.extend(generate_periodic_rows_koyeb(base_info, num_chips, per_gpu_hourly_rate))

    return final_data