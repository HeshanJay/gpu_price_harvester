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
            logger.warning(f"Koyeb: Could not parse price from '{price_str}'")
            return None
    return None

def get_canonical_variant_and_base_chip_koyeb(gpu_name_str):
    """Determines the canonical GPU variant and base chip family."""
    text_to_search = str(gpu_name_str).lower()
    family = None
    variant = gpu_name_str.replace('NVIDIA ', '')

    if "h100" in text_to_search:
        family = "H100"
        variant = "H100" # Koyeb page doesn't specify PCIe/SXM, so using generic H100
    elif "l40s" in text_to_search:
        family = "L40S"
        variant = "L40S"
    elif "h200" in text_to_search: # For future use, not currently on page
        family = "H200"
        variant = "H200"
        
    if family:
        return variant, family
    return None, None

def generate_periodic_rows_koyeb(base_info, num_chips, per_gpu_hourly_rate):
    """Generates the standard hourly, 6-month, and yearly rows for a Koyeb offering."""
    rows = []
    if per_gpu_hourly_rate is None or not num_chips:
        return rows

    base_info["Number of Chips"] = num_chips
    
    # Koyeb lists on-demand prices. We'll use this for all projections.
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
    """Fetches data from the Koyeb pricing page."""
    final_data = []
    
    # Find the container for the GPU instance list
    gpu_section = soup.find('div', id='compute')
    if not gpu_section:
        logger.error("Koyeb: Could not find the main compute section with id='compute'.")
        return []

    # Prioritize the desktop grid view as it is more structured
    desktop_grid = gpu_section.find('div', class_=re.compile("hidden grid-cols-5"))
    
    if desktop_grid:
        logger.info("Koyeb: Parsing with desktop grid layout.")
        cells = desktop_grid.find_all('div', recursive=False)
        # The structure is a flat list of divs, 5 per row.
        for i in range(5, len(cells), 5): # Start from the first data row
            instance_div, vcpu_div, ram_div, disk_div, price_div = cells[i:i+5]
            
            instance_name_tag = instance_div.find('div', class_='row')
            instance_name = instance_name_tag.get_text(strip=True) if instance_name_tag else "N/A"
            vram_tag = instance_div.find('div', class_='text-dark/50')
            vram_str = vram_tag.get_text(strip=True) if vram_tag else ""
            
            price_str = price_div.get_text(strip=True)
            
            variant, family = get_canonical_variant_and_base_chip_koyeb(instance_name)
            if not family:
                continue

            instance_price_eur = parse_price_koyeb(price_str)
            if instance_price_eur is None:
                continue

            num_chips_match = re.match(r'(\d+)x', instance_name, re.IGNORECASE)
            num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
            
            per_gpu_hourly_rate = instance_price_eur / num_chips if num_chips > 0 else 0

            vram_gb_match = re.search(r'(\d+)', vram_str)
            vram_gb = int(vram_gb_match.group(1)) if vram_gb_match else 0
            # For multi-GPU instances, VRAM is often total, so we divide.
            if num_chips > 1:
                vram_gb = vram_gb / num_chips

            gpu_id = f"koyeb_{instance_name.lower().replace(' ','-')}"
            notes = f"vCPU: {vcpu_div.get_text(strip=True)}, RAM: {ram_div.get_text(strip=True)}, Disk: {disk_div.get_text(strip=True)}"

            base_info = {
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
                "Region": STATIC_REGION_INFO, "Currency": "USD", "GPU ID": gpu_id,
                "GPU (H100 or H200 or L40S)": family, "Memory (GB)": int(vram_gb),
                "Display Name(GPU Type)": instance_name, "GPU Variant Name": variant,
                "Storage Option": STATIC_STORAGE_OPTION, "Amount of Storage": disk_div.get_text(strip=True),
                "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE,
                "Notes / Features": notes,
            }
            final_data.extend(generate_periodic_rows_koyeb(base_info, num_chips, per_gpu_hourly_rate))

    else:
        # Fallback to mobile view if desktop grid is not found
        logger.warning("Koyeb: Desktop grid not found, falling back to mobile view parsing.")
        mobile_container = gpu_section.find('div', class_=re.compile("2xl:hidden"))
        if not mobile_container:
             logger.error("Koyeb: Could not find mobile container either.")
             return []

        cards = mobile_container.find_all('div', class_='col gap-2')
        for card in cards:
            name_price_row = card.find('div', class_='row')
            if not name_price_row: continue
            
            instance_name_tag = name_price_row.find('div', class_='row')
            instance_name = instance_name_tag.get_text(strip=True) if instance_name_tag else "N/A"
            price_str = name_price_row.get_text(strip=True).replace(instance_name, '')
            
            variant, family = get_canonical_variant_and_base_chip_koyeb(instance_name)
            if not family: continue

            instance_price_eur = parse_price_koyeb(price_str)
            if instance_price_eur is None: continue

            num_chips_match = re.match(r'(\d+)x', instance_name, re.IGNORECASE)
            num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
            
            per_gpu_hourly_rate = instance_price_eur / num_chips if num_chips > 0 else 0

            # VRAM is not easily accessible in this mobile view, so we set a default based on name
            vram_gb = 80 if 'H100' in variant else (48 if 'L40S' in variant else 0)

            spec_divs = card.find_all('div', class_='typo-body-lg')
            vcpu, ram, disk = "N/A", "N/A", "N/A"
            if len(spec_divs) == 3:
                vcpu, ram, disk = [div.get_text(strip=True) for div in spec_divs]

            notes = f"vCPU: {vcpu}, RAM: {ram}, Disk: {disk}"
            gpu_id = f"koyeb_m_{instance_name.lower().replace(' ','-')}"
            
            base_info = {
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
                "Region": STATIC_REGION_INFO, "Currency": "USD", "GPU ID": gpu_id,
                "GPU (H100 or H200 or L40S)": family, "Memory (GB)": vram_gb,
                "Display Name(GPU Type)": instance_name, "GPU Variant Name": variant,
                "Storage Option": STATIC_STORAGE_OPTION, "Amount of Storage": disk,
                "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE,
                "Notes / Features": notes,
            }
            final_data.extend(generate_periodic_rows_koyeb(base_info, num_chips, per_gpu_hourly_rate))

    return final_data