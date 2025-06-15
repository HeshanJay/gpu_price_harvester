from bs4 import BeautifulSoup
import re
import logging
import os
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HOURS_IN_MONTH = 730

STATIC_PROVIDER_NAME = "Google Cloud Platform"
STATIC_SERVICE_PROVIDED = "GCP A3 GPU Instances"
STATIC_STORAGE_OPTION_GCP = "Local SSD"
STATIC_NETWORK_PERFORMANCE_GCP = "Up to 200 Gbps (A3)"

TARGET_GPU_SPECS_MAP = {
    "a3-highgpu": {"family": "H100", "vram": 80, "variant_base_name": "H100 SXM 80GB"},
    "a3-ultragpu": {"family": "H200", "vram": 141, "variant_base_name": "H200 SXM 141GB"},
}

def parse_price(price_str):
    if price_str is None or not isinstance(price_str, str) or "N/A" in price_str or "contact sales" in price_str.lower():
        return None
    match = re.search(r"[\$€₹]?\s*([\d,]+\.?\d*)", price_str)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None

def parse_price_from_nanos(price_dict):
    if not price_dict or 'nanos' not in price_dict or 'currencyCode' not in price_dict:
        return None, None
    nanos = price_dict.get('nanos', 0)
    units = price_dict.get('units', 0)
    price = float(units) + float(nanos) / 1_000_000_000.0
    return price, price_dict['currencyCode']

def generate_periodic_rows(base_info, num_chips, on_demand_hr, cud_1yr_hr, cud_3yr_hr, currency):
    rows = []
    if on_demand_hr is None or num_chips is None or num_chips == 0:
        return rows

    notes = base_info.get("Notes / Features", "")
    if cud_3yr_hr is not None:
        notes += f" 3-year CUD: approx ${cud_3yr_hr:.4f}/hr/GPU."

    hourly_row = {
        **base_info,
        "Period": "Per Hour",
        "Total Price ($)": round(on_demand_hr * num_chips, 4),
        "Effective Hourly Rate ($/hr)": round(on_demand_hr, 4),
        "Commitment Discount - 12 Month Price ($/hr per GPU)": round(cud_1yr_hr, 4) if cud_1yr_hr is not None else "N/A",
        "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
        "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
        "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
        "Notes / Features": notes.strip()
    }
    rows.append(hourly_row)

    total_6mo_price = (on_demand_hr * num_chips) * HOURS_IN_MONTH * 6
    price_str_6mo = f"{on_demand_hr * num_chips:.2f} ({total_6mo_price:.2f} total)"
    six_month_row = {**hourly_row, "Period": "Per 6 Months", "Total Price ($)": price_str_6mo}
    rows.append(six_month_row)

    if cud_1yr_hr is not None:
        total_yearly_price = (cud_1yr_hr * num_chips) * HOURS_IN_MONTH * 12
        price_str_12mo = f"{cud_1yr_hr * num_chips:.2f} ({total_yearly_price:.2f} total)"
        yearly_row = {**hourly_row, "Period": "Per Year", "Total Price ($)": price_str_12mo, "Effective Hourly Rate ($/hr)": round(cud_1yr_hr, 4)}
        rows.append(yearly_row)

    return rows

def _parse_json_data(html_content):
    logger.info("GCP Handler: Attempting to find and parse embedded JSON data...")
    soup = BeautifulSoup(html_content, 'html.parser')
    all_scripts = soup.find_all('script')
    
    for script in all_scripts:
        if script.string and 'ATOZ_PRICING_RESPONSE' in script.string:
            logger.info("GCP Handler: Found a candidate script tag with pricing data.")
            match = re.search(r'=\s*({.*})\s*;', script.string, re.S)
            if match:
                try:
                    pricing_data = json.loads(match.group(1))
                    skus_list = pricing_data.get('ATOZ_PRICING_RESPONSE', {}).get('skus', [])
                    if skus_list:
                        logger.info(f"GCP Handler: Successfully parsed {len(skus_list)} SKUs from JSON.")
                        return _process_skus_from_json(skus_list)
                except json.JSONDecodeError as e:
                    logger.error(f"GCP Handler: Failed to decode JSON from script tag: {e}")
                    continue # Try next script tag
    
    logger.warning("GCP Handler: Could not find or parse any embedded JSON data.")
    return None

def _process_skus_from_json(skus_list):
    final_data = []
    offerings = {}

    for sku in skus_list:
        machine_type = sku.get('machineType')
        if not machine_type or not (machine_type.startswith('a3-highgpu') or machine_type.startswith('a3-ultragpu')):
            continue

        base_type = 'a3-highgpu' if 'highgpu' in machine_type else 'a3-ultragpu'
        gpu_spec = TARGET_GPU_SPECS_MAP.get(base_type)
        if not gpu_spec: continue

        try:
            num_chips = int(sku['gpus'][0]['count'])
            region = sku['region']
            offering_key = (machine_type, region)

            if offering_key not in offerings:
                offerings[offering_key] = {
                    'base_info': {
                        "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED, "Region": region,
                        "GPU (H100 or H200 or L40S)": gpu_spec["family"], "Memory (GB)": gpu_spec["vram"],
                        "Display Name(GPU Type)": f"{num_chips}x {gpu_spec['variant_base_name']}",
                        "GPU Variant Name": gpu_spec['variant_base_name'],
                        "Storage Option": f"{sku.get('localSsdGb', 'N/A')} GB Local SSD" if sku.get('localSsdGb') else STATIC_STORAGE_OPTION_GCP,
                        "Amount of Storage": f"{sku.get('localSsdGb', 'N/A')} GB" if sku.get('localSsdGb') else 'N/A',
                        "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_GCP, "Number of Chips": num_chips,
                        "Notes / Features": f"Machine Type: {machine_type}. vCPUs: {sku.get('vcpus', 'N/A')}. System Memory: {sku.get('memoryGib', 'N/A')} GiB.",
                        "GPU ID": f"gcp_json_{machine_type.replace('-', '_')}_{region.replace('-', '_')}".lower(),
                    }, 'prices': {}
                }

            price_type = sku['pricingRate']['type']
            price, currency = parse_price_from_nanos(sku['pricingRate']['price'])
            if price is not None:
                offerings[offering_key]['prices'][price_type] = price
                offerings[offering_key]['base_info']['Currency'] = currency
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning(f"Skipping SKU due to JSON parsing error: {e}. SKU data: {sku.get('machineType')}, {sku.get('region')}")

    for key, offering in offerings.items():
        prices = offering['prices']
        on_demand_rate, cud_1yr_rate, cud_3yr_rate = prices.get('ON_DEMAND'), prices.get('ONE_YEAR_CUD'), prices.get('THREE_YEAR_CUD')
        if on_demand_rate is None: continue
        
        num_chips = offering['base_info']['Number of Chips']
        on_demand_per_gpu = on_demand_rate / num_chips
        cud_1yr_per_gpu = cud_1yr_rate / num_chips if cud_1yr_rate else None
        cud_3yr_per_gpu = cud_3yr_rate / num_chips if cud_3yr_rate else None
        
        final_data.extend(generate_periodic_rows(offering['base_info'], num_chips, on_demand_per_gpu, cud_1yr_per_gpu, cud_3yr_per_gpu, offering['base_info'].get('Currency')))
        
    return final_data

def _parse_tables_fallback(html_content):
    logger.warning("GCP Handler: Falling back to scraping visible HTML tables. Data may be limited to a single region.")
    final_data = []
    soup = BeautifulSoup(html_content, "html.parser")
    
    all_tables = soup.find_all('table', class_='nooFgd')
    region = "Unknown"
    region_element = soup.find('span', class_='rHGeGc-uusGie-fmcmS', jsname='Fb0Bif')
    if region_element:
        region = region_element.text.strip()
    
    for table in all_tables:
        rows = table.find_all('tr', class_='YXefId')
        if not rows or len(rows) < 2: continue
        
        first_data_cell = rows[1].find('td', class_='dXsTZe')
        if not first_data_cell: continue
        
        first_machine_type = first_data_cell.get_text(strip=True).lower()
        base_type = None
        if 'a3-highgpu' in first_machine_type: base_type = "a3-highgpu"
        elif 'a3-ultragpu' in first_machine_type: base_type = "a3-ultragpu"
        else: continue
        
        gpu_spec = TARGET_GPU_SPECS_MAP.get(base_type)
        if not gpu_spec: continue

        for row in rows[1:]:
            cols = row.find_all('td', class_='dXsTZe')
            if len(cols) < 8: continue
            
            try:
                machine_type, gpu_count, vcpu, sys_mem, ssd, on_demand_str, cud_1yr_str, cud_3yr_str = [c.get_text(strip=True) for c in cols[:8]]
                num_chips = int(gpu_count)
                
                on_demand_instance_hr = parse_price(on_demand_str)
                cud_1yr_instance_hr = parse_price(cud_1yr_str)
                cud_3yr_instance_hr = parse_price(cud_3yr_str)
                
                if on_demand_instance_hr is None: continue
                
                on_demand_per_gpu = on_demand_instance_hr / num_chips
                cud_1yr_per_gpu = cud_1yr_instance_hr / num_chips if cud_1yr_instance_hr else None
                cud_3yr_per_gpu = cud_3yr_instance_hr / num_chips if cud_3yr_instance_hr else None
                
                base_info = {
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED, "Region": region, "Currency": "USD",
                    "GPU (H100 or H200 or L40S)": gpu_spec["family"], "Memory (GB)": gpu_spec["vram"],
                    "Display Name(GPU Type)": f"{num_chips}x {gpu_spec['variant_base_name']}",
                    "GPU Variant Name": gpu_spec['variant_base_name'],
                    "Storage Option": STATIC_STORAGE_OPTION_GCP, "Amount of Storage": f"{ssd} GiB",
                    "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_GCP, "Number of Chips": num_chips,
                    "Notes / Features": f"Machine Type: {machine_type}. vCPUs: {vcpu}. System Memory: {sys_mem}.",
                    "GPU ID": f"gcp_{machine_type.replace('-', '_')}_{region.split('(')[0].strip().replace(' ', '_')}".lower()
                }
                final_data.extend(generate_periodic_rows(base_info, num_chips, on_demand_per_gpu, cud_1yr_per_gpu, cud_3yr_per_gpu, "USD"))
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Could not parse table row: {row.get_text()}. Error: {e}")

    return final_data


def fetch_gcp_gpu_data_from_html(html_content):
    if not html_content:
        logger.error("GCP Handler: Received empty HTML content.")
        return []
    
    # Try the robust JSON parsing method first
    json_data = _parse_json_data(html_content)
    
    # If JSON parsing succeeds and returns data, use it
    if json_data:
        return json_data
        
    # Otherwise, fall back to scraping the visible HTML tables
    return _parse_tables_fallback(html_content)


if __name__ == '__main__':
    logger.info("Testing GCP GPU Pricing Handler from local HTML file...")
    html_file_path = "Pricing _ Compute Engine_ Virtual Machines (VMs) _ Google Cloud _ Google Cloud.html"
    
    try:
        if not os.path.exists(html_file_path):
            logger.error(f"CRITICAL: HTML file '{html_file_path}' not found.")
        else:
            with open(html_file_path, 'r', encoding='utf-8') as f:
                test_html_content = f.read()
            logger.info(f"Successfully loaded HTML from {html_file_path} for testing.")
            processed_data = fetch_gcp_gpu_data_from_html(test_html_content)

            if processed_data:
                logger.info(f"\nSuccessfully processed {len(processed_data)} rows from GCP HTML.")
            else:
                logger.warning("No data processed by fetch_gcp_gpu_data_from_html.")
    except Exception as e:
        logger.error(f"Error during local test: {e}")
        import traceback
        traceback.print_exc()