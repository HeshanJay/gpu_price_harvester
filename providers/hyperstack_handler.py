# providers/hyperstack_handler.py
import requests
from bs4 import BeautifulSoup
import re
import logging

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HYPERSTACK_PRICING_URL = "https://www.hyperstack.cloud/gpu-pricing"
HOURS_IN_MONTH = 730

# --- Static Information ---
STATIC_PROVIDER_NAME = "Hyperstack"
STATIC_SERVICE_PROVIDED = "Hyperstack GPU Cloud"
STATIC_REGION_INFO = "Europe, North America"
STATIC_STORAGE_OPTION = "Instance Dependent"
STATIC_NETWORK_PERFORMANCE = "High-Speed Fabric"

# --- Parsing Helper Functions ---

def parse_price_hyperstack(price_str):
    """Parses price string like '$ 2.40 per Hour' or '$1.90/hour' into a float."""
    if not price_str:
        return None
    
    price_str_cleaned = price_str.lower().replace('$', '').strip()
    match = re.search(r"(\d+\.?\d*)", price_str_cleaned)
    
    if match:
        try:
            return float(match.group(1))
        except (ValueError, TypeError):
            logger.warning(f"Hyperstack: Could not parse price from value: '{match.group(1)}' in string: '{price_str}'")
            return None
    return None

def get_canonical_variant_and_base_chip_hyperstack(gpu_name_str):
    """Determines the canonical GPU variant and base chip family from strings like 'NVIDIA H100 SXM 80GB'."""
    text_to_search = str(gpu_name_str).lower()
    family = None
    variant = gpu_name_str # Default

    # Note: Page does not list H200, but we include logic for it.
    # It lists L40, which we will map to the L40S family as requested.
    if "h200" in text_to_search:
        family = "H200"
        if "sxm" in text_to_search:
            variant = "H200 SXM"
        else:
            variant = "H200 PCIe"
    elif "h100" in text_to_search:
        family = "H100"
        if "sxm" in text_to_search:
            variant = "H100 SXM"
        elif "pcie" in text_to_search:
            variant = "H100 PCIe"
        else:
            variant = "H100"
    elif "l40" in text_to_search and "l40s" not in text_to_search: # Match L40 but not L40S explicitly
        family = "L40S"
        variant = "L40S"
        
    if family in ["H100", "H200", "L40S"]:
        return variant, family
    return None, None

def generate_periodic_rows_hyperstack(base_info, on_demand_rate, reservation_rate):
    """
    Generates rows for different chip counts and periods, using reservation rate for yearly calculations.
    """
    all_rows_for_offering = []
    
    for num_chips in [1, 2, 4, 8]:
        base_info_chips = base_info.copy()
        base_info_chips["Number of Chips"] = num_chips
        
        # On-demand rates for Hour and 6-Month periods
        eff_rate_ondemand = on_demand_rate
        total_hourly_ondemand = num_chips * eff_rate_ondemand

        # Commitment rate for Yearly period
        eff_rate_commit = reservation_rate if reservation_rate is not None else on_demand_rate
        total_hourly_commit = num_chips * eff_rate_commit

        base_info_chips["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A"
        base_info_chips["Commitment Discount - 3 Month Price ($/hr per GPU)"] = "N/A"
        base_info_chips["Commitment Discount - 6 Month Price ($/hr per GPU)"] = "N/A"
        # The lowest "Reservation" price is considered the 12-month equivalent for comparison
        base_info_chips["Commitment Discount - 12 Month Price ($/hr per GPU)"] = round(eff_rate_commit, 2) if reservation_rate else "N/A"

        # Per Hour (On-demand)
        hourly_row = {**base_info_chips, 
                      "Period": "Per Hour",
                      "Total Price ($)": round(total_hourly_ondemand, 2), 
                      "Effective Hourly Rate ($/hr)": round(eff_rate_ondemand, 2)}
        all_rows_for_offering.append(hourly_row)

        # Per 6 Months (On-demand)
        total_6mo_price = total_hourly_ondemand * HOURS_IN_MONTH * 6
        price_str_6mo = f"{total_hourly_ondemand:.2f} ({total_6mo_price:.2f})"
        six_month_row = {**base_info_chips,
                         "Period": "Per 6 Months",
                         "Total Price ($)": price_str_6mo,
                         "Effective Hourly Rate ($/hr)": round(eff_rate_ondemand, 2)}
        all_rows_for_offering.append(six_month_row)

        # Per Year (Commitment/Reservation Rate)
        total_yearly_price = total_hourly_commit * HOURS_IN_MONTH * 12
        price_str_12mo = f"{total_hourly_commit:.2f} ({total_yearly_price:.2f})"
        yearly_row = {**base_info_chips,
                      "Period": "Per Year",
                      "Total Price ($)": price_str_12mo,
                      "Effective Hourly Rate ($/hr)": round(eff_rate_commit, 2)}
        all_rows_for_offering.append(yearly_row)
        
    return all_rows_for_offering

# --- Main Handler Function ---

def fetch_hyperstack_data(soup):
    """Main function to fetch data from the Hyperstack pricing table."""
    final_data = []
    
    pricing_table = soup.find('table', id='tblSortTest_jquery')
    if not pricing_table:
        logger.error("Hyperstack: Could not find the pricing table with id 'tblSortTest_jquery'.")
        return []

    tbody = pricing_table.find('tbody')
    if not tbody:
        logger.warning("Hyperstack: Pricing table found, but no tbody content.")
        return []
        
    rows = tbody.find_all('tr')
    logger.info(f"Hyperstack: Found {len(rows)} rows in the pricing table.")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue

        gpu_model, vram_gb, max_cpus, max_ram, on_demand_price_str, reservation_price_cell = [c.get_text(strip=True) for c in cols]
        
        variant, family = get_canonical_variant_and_base_chip_hyperstack(gpu_model)
        if not family:
            continue # Skip non-target GPUs like A100

        on_demand_rate = parse_price_hyperstack(on_demand_price_str)
        
        reservation_rate_raw_str = reservation_price_cell
        reservation_link_tag = cols[5].find('a')
        if reservation_link_tag:
            reservation_rate_raw_str = reservation_link_tag.get_text(strip=True)
            
        reservation_rate = parse_price_hyperstack(reservation_rate_raw_str)

        if on_demand_rate is None:
            logger.warning(f"Hyperstack: Skipping '{gpu_model}' due to unparseable on-demand price.")
            continue
            
        notes = f"Max pCPUs per GPU: {max_cpus}, Max System RAM per GPU: {max_ram} GB."
        gpu_id = f"hyperstack_{variant.replace(' ','-').replace('/','-').lower()}"

        base_info = {
            "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": STATIC_REGION_INFO, "Currency": "USD", "GPU ID": gpu_id,
            "GPU (H100 or H200 or L40S)": family, "Memory (GB)": int(vram_gb),
            "Display Name(GPU Type)": gpu_model, "GPU Variant Name": variant,
            "Storage Option": STATIC_STORAGE_OPTION, "Amount of Storage": "Instance Dependent",
            "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE,
            "Notes / Features": notes,
        }
        
        # Since prices are per GPU, we generate rows for 1, 2, 4, 8 chip calculations
        final_data.extend(generate_periodic_rows_hyperstack(base_info, on_demand_rate, reservation_rate))
            
    return final_data

# --- Standalone Test Execution ---
if __name__ == '__main__':
    logger.info(f"Testing Hyperstack Handler by fetching {HYPERSTACK_PRICING_URL}...")
    try:
        response = requests.get(HYPERSTACK_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        processed_data = fetch_hyperstack_data(soup)
        
        if processed_data:
            logger.info(f"\nSuccessfully processed {len(processed_data)} total rows from Hyperstack.")
            
            # Print summary of the first offering (all periods and chip counts)
            first_offering_name = processed_data[0].get("Display Name(GPU Type)")
            logger.info(f"\n--- Sample Offering: {first_offering_name} ---")
            for row in processed_data:
                if row.get("Display Name(GPU Type)") == first_offering_name:
                    logger.info(f"  Chips: {row.get('Number of Chips')}, Period: {row.get('Period')}, "
                                f"Rate: ${row.get('Effective Hourly Rate ($/hr)')}/hr, "
                                f"Total Price: {row.get('Total Price ($)')}")
        else:
            logger.warning("No data was processed by the Hyperstack handler.")
            
    except Exception as e:
        logger.error(f"An error occurred during the Hyperstack handler test: {e}")
        import traceback
        traceback.print_exc()