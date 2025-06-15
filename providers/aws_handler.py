# providers/aws_handler.py
import boto3
import json
import re
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HOURS_IN_MONTH = 730

STATIC_PROVIDER_NAME = "Amazon Web Services"
STATIC_SERVICE_PROVIDED = "AWS EC2 GPU Instances"
STATIC_STORAGE_OPTION_AWS = "EBS / Instance Store (Configurable)"
STATIC_NETWORK_PERFORMANCE_AWS = "Enhanced Networking (Varies by instance type)"

# --- Configuration: User MUST review and update these ---
TARGET_AWS_REGIONS = [
    "US East (N. Virginia)",    # us-east-1
    "US West (Oregon)",         # us-west-2
    "EU (Ireland)",             # eu-west-1
    "EU (Frankfurt)",           # eu-central-1
    "Asia Pacific (Tokyo)",     # ap-northeast-1
    "Asia Pacific (Sydney)",    # ap-southeast-2
    # Add more regions as needed
]

# This mapping is CRUCIAL and requires research from AWS EC2 Instance Types documentation.
# Key: Exact EC2 Instance Type string from AWS Price List API
# Values: 
#   'family': Your target family (H100, L40S, H200)
#   'vram_per_gpu': VRAM in GB for a single GPU of this type
#   'gpus_in_type': How many GPUs are in this specific full instance type
#   'variant_base': A base name for the GPU variant (e.g., "H100 SXM", "L40S PCIe")
AWS_INSTANCE_TYPE_TO_GPU_SPECS = {
    # NVIDIA H100 (P5 Instances)
    "p5.48xlarge":  {"family": "H100", "vram_per_gpu": 80, "gpus_in_type": 8, "variant_base": "H100 SXM 80GB"},
    # Add other P5 sizes: e.g. "p5.24xlarge" if it has 4 H100s, "p5.12xlarge" if 2 H100s (verify from AWS docs)

    # NVIDIA L40S (G6 and G6e Instances)
    "g6.xlarge":    {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6.2xlarge":   {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6.4xlarge":   {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6.8xlarge":   {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6.12xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 4, "variant_base": "L40S PCIe 48GB"},
    "g6.16xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 4, "variant_base": "L40S PCIe 48GB"},
    "g6.24xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 4, "variant_base": "L40S PCIe 48GB"},
    "g6.48xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 8, "variant_base": "L40S PCIe 48GB"},
    
    "g6e.xlarge":   {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6e.2xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6e.4xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    "g6e.8xlarge":  {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"},
    # G6e instances above g6e.8xlarge might have more than 1 L40S, verify with AWS documentation.
    # For example, g6e.16xlarge might have 2 or 4. g6e.metal has 8.
    "g6e.16xlarge": {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 1, "variant_base": "L40S PCIe 48GB"}, # Example, please verify
    "g6e.metal":    {"family": "L40S", "vram_per_gpu": 48, "gpus_in_type": 8, "variant_base": "L40S PCIe 48GB"},

    # NVIDIA H200 - Add instance types here once they are available and you know their Price List API instanceType string
    # Example:
    # "p6whatever.size": {"family": "H200", "vram_per_gpu": 141, "gpus_in_type": 8, "variant_base": "H200 SXM 141GB"},
}
# --- End of User Configuration ---

def get_aws_pricing_client(api_region='us-east-1'):
    try:
        client = boto3.client('pricing', region_name=api_region)
        logger.info(f"AWS Handler: Successfully initialized Boto3 Pricing client for API region {api_region}.")
        return client
    except Exception as e:
        logger.error(f"AWS Handler: Failed to initialize Boto3 Pricing client: {e}")
        return None

def parse_instance_system_specs_from_attributes(attributes):
    vcpu = attributes.get('vcpu', "N/A")
    memory_str = attributes.get('memory', "N/A") 
    
    if isinstance(memory_str, str) and " GiB" in memory_str:
        memory_val = memory_str.replace(" GiB", "").strip()
    elif isinstance(memory_str, str): # If just number
        memory_val = memory_str.strip()
    else:
        memory_val = "N/A"
        
    return vcpu, memory_val

def generate_periodic_rows_aws(base_info, num_chips, on_demand_hr_rate_usd):
    rows = []
    if on_demand_hr_rate_usd is None or num_chips is None or num_chips == 0:
        logger.warning(f"AWS: Cannot generate rows for {base_info.get('Display Name(GPU Type)')} due to missing rate or zero/None chip count ({num_chips}).")
        return rows
        
    base_info_copy = base_info.copy()
    base_info_copy["Commitment Discount - 1 Month Price ($/hr per GPU)"] = "N/A"
    base_info_copy["Commitment Discount - 3 Month Price ($/hr per GPU)"] = "N/A"
    base_info_copy["Commitment Discount - 6 Month Price ($/hr per GPU)"] = "N/A"
    base_info_copy["Commitment Discount - 12 Month Price ($/hr per GPU)"] = "N/A" 

    total_hourly_for_instance = num_chips * on_demand_hr_rate_usd
    hourly_row = {**base_info_copy, 
                  "Period": "Per Hour",
                  "Total Price ($)": round(total_hourly_for_instance, 2), 
                  "Effective Hourly Rate ($/hr)": round(on_demand_hr_rate_usd, 2)}
    rows.append(hourly_row)

    eff_rate_calc = on_demand_hr_rate_usd 
    
    total_6mo_instance_hourly = num_chips * eff_rate_calc
    total_6mo_period_price = total_6mo_instance_hourly * HOURS_IN_MONTH * 6
    price_str_6mo = f"{total_6mo_instance_hourly:.2f} ({total_6mo_period_price:.2f})"
    six_month_row = {**base_info_copy,
                     "Period": "Per 6 Months",
                     "Total Price ($)": price_str_6mo,
                     "Effective Hourly Rate ($/hr)": round(eff_rate_calc, 2)}
    rows.append(six_month_row)

    total_12mo_instance_hourly = num_chips * eff_rate_calc
    total_12mo_period_price = total_12mo_instance_hourly * HOURS_IN_MONTH * 12
    price_str_12mo = f"{total_12mo_instance_hourly:.2f} ({total_12mo_period_price:.2f})"
    
    yearly_row_data = {**base_info_copy,
                  "Period": "Per Year",
                  "Total Price ($)": price_str_12mo,
                  "Effective Hourly Rate ($/hr)": round(eff_rate_calc, 2)}
    rows.append(yearly_row_data)
    return rows

def fetch_aws_gpu_data():
    final_data_for_sheet = []
    pricing_client = get_aws_pricing_client(api_region='us-east-1') 
    if not pricing_client:
        return final_data_for_sheet

    for region_name_full in TARGET_AWS_REGIONS:
        # Iterate through the instance types defined in your mapping
        for instance_type_str, spec_details in AWS_INSTANCE_TYPE_TO_GPU_SPECS.items():
            target_gpu_family_from_map = spec_details["family"]
            
            # Ensure we only process H100, H200, L40S as per project scope
            if target_gpu_family_from_map not in ["H100", "L40S", "H200"]:
                continue

            logger.info(f"AWS Handler: Querying prices for Instance Type: {instance_type_str} in Region: {region_name_full}")
            try:
                paginator = pricing_client.get_paginator('get_products')
                response_iterator = paginator.paginate(
                    ServiceCode='AmazonEC2',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type_str},
                        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region_name_full},
                        {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
                        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'}, 
                        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'}, 
                        {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'}, 
                    ]
                )

                for page in response_iterator:
                    for price_item_str in page.get('PriceList', []):
                        price_item = json.loads(price_item_str)
                        product_attrs = price_item.get('product', {}).get('attributes', {})
                        
                        # Confirm instance type from SKU matches what we filtered for
                        sku_instance_type = product_attrs.get('instanceType')
                        if not sku_instance_type or sku_instance_type.lower() != instance_type_str.lower():
                            continue

                        # Use predefined specs from our map for this instance type
                        num_chips = spec_details["gpus_in_type"]
                        vram_gb = spec_details["vram_per_gpu"]
                        gpu_variant = spec_details["variant_base"] # e.g. "H100 SXM 80GB"
                        
                        vcpu, system_ram = parse_instance_system_specs_from_attributes(product_attrs)

                        terms = price_item.get('terms', {}).get('OnDemand')
                        if not terms: continue

                        for term_code, term_details in terms.items():
                            for pd_code, price_dimension in term_details.get('priceDimensions', {}).items():
                                if price_dimension.get('unit') == 'Hrs': # Hourly pricing for the instance
                                    price_per_unit_str = price_dimension.get('pricePerUnit', {}).get('USD')
                                    if price_per_unit_str:
                                        try:
                                            instance_hourly_rate_usd = float(price_per_unit_str)
                                            if instance_hourly_rate_usd == 0.0: continue

                                            effective_hourly_rate_per_gpu = instance_hourly_rate_usd / num_chips if num_chips > 0 else instance_hourly_rate_usd
                                            
                                            display_name = f"{num_chips}x {gpu_variant} ({instance_type_str})"
                                            gpu_id_aws = f"aws_{instance_type_str.replace('.','-')}_{product_attrs.get('regionCode','na')}" # Use regionCode for ID

                                            notes = f"Instance: {instance_type_str}. vCPU: {vcpu}, System RAM: {system_ram} GiB. "
                                            notes += f"Term: OnDemand. SKU: {price_item.get('product',{}).get('sku','N/A')}."

                                            base_info = {
                                                "Provider Name": STATIC_PROVIDER_NAME,
                                                "Service Provided": STATIC_SERVICE_PROVIDED,
                                                "Region": region_name_full, 
                                                "Currency": "USD",
                                                "GPU ID": gpu_id_aws,
                                                "GPU (H100 or H200 or L40S)": target_gpu_family_from_map,
                                                "Memory (GB)": vram_gb,
                                                "Display Name(GPU Type)": display_name,
                                                "GPU Variant Name": gpu_variant,
                                                "Storage Option": product_attrs.get('storage', STATIC_STORAGE_OPTION_AWS),
                                                "Amount of Storage": product_attrs.get('storage', "Instance Dependent"),
                                                "Network Performance (Gbps)": product_attrs.get('networkPerformance', STATIC_NETWORK_PERFORMANCE_AWS),
                                                "Number of Chips": num_chips,
                                                "Notes / Features": notes.strip(),
                                            }
                                            final_data_for_sheet.extend(generate_periodic_rows_aws(base_info, num_chips, effective_hourly_rate_per_gpu))
                                        except ValueError:
                                            logger.warning(f"AWS Handler: Could not convert price '{price_per_unit_str}' to float for {instance_type_str} in {region_name_full}")
                                        except Exception as e_inner:
                                            logger.error(f"AWS Handler: Error processing price dimension for {instance_type_str}: {e_inner}")
                logger.info(f"AWS Handler: Finished API query for {instance_type_str} in {region_name_full}.")
            except Exception as e_paginate:
                logger.error(f"AWS Handler: Error paginating/processing for {instance_type_str} in {region_name_full}: {e_paginate}")
    
    logger.info(f"AWS Handler: Finished querying all target instance types. Total initial rows: {len(final_data_for_sheet)}")

    unique_rows_dict = {}
    if final_data_for_sheet:
        logger.info(f"AWS Handler: Starting de-duplication. Original row count: {len(final_data_for_sheet)}")
        for row in final_data_for_sheet:
            key_for_dedup = (
                row.get("Provider Name"), row.get("GPU Variant Name"), row.get("Number of Chips"),
                row.get("Period"), row.get("Region"), row.get("Display Name(GPU Type)"),
                row.get("Currency"), row.get("Effective Hourly Rate ($/hr)") 
            )
            if key_for_dedup not in unique_rows_dict:
                unique_rows_dict[key_for_dedup] = row
        final_data_for_sheet = list(unique_rows_dict.values())
        logger.info(f"AWS Handler: After de-duplication. New row count: {len(final_data_for_sheet)}")

    if final_data_for_sheet:
        distinct_offerings_count = len(set((row["Display Name(GPU Type)"], row["Number of Chips"], row["Region"]) for row in final_data_for_sheet if row["Period"] == "Per Hour"))
        logger.info(f"AWS Handler: Processed {distinct_offerings_count} distinct GPU offerings, generating {len(final_data_for_sheet)} total rows.")
    else:
        logger.warning(f"AWS Handler: No target GPU offerings (H100, H200, L40S) found or parseable from AWS Price List API.")
        
    return final_data_for_sheet

if __name__ == '__main__':
    logger.info("Testing AWS GPU Pricing Handler...")
    
    if not (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")) and \
       not (os.path.exists(os.path.expanduser("~/.aws/credentials")) and os.path.exists(os.path.expanduser("~/.aws/config"))):
        logger.error("CRITICAL: AWS credentials not found in environment variables or AWS CLI config files.")
        logger.error("Please configure them using `aws configure` or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")
    else:
        logger.info("AWS credentials seem to be configured (found in env or will be picked up by Boto3 default chain).")
        processed_data = fetch_aws_gpu_data()
        
        if processed_data:
            logger.info(f"\nSuccessfully processed {len(processed_data)} rows from AWS.")
            printed_offerings_summary = {}
            for i, row_data in enumerate(processed_data):
                # Defensive get for potentially missing keys in summary print
                display_name = row_data.get("Display Name(GPU Type)", "Unknown Display Name")
                num_chips_val = row_data.get("Number of Chips", "N/A")
                region_val = row_data.get("Region", "N/A")
                
                offering_key_print = (display_name, num_chips_val, region_val)
                if offering_key_print not in printed_offerings_summary:
                    printed_offerings_summary[offering_key_print] = []
                
                period_info = f"{row_data.get('Period','N/A')}: Currency {row_data.get('Currency','N/A')}, Rate {row_data.get('Effective Hourly Rate ($/hr)','N/A')}/GPU/hr"
                printed_offerings_summary[offering_key_print].append(period_info)

            logger.info("\n--- Summary of Processed Offerings (AWS) ---")
            for (disp_name, chips, region), periods_info in printed_offerings_summary.items():
                logger.info(f"\nOffering: {disp_name} (Chips: {chips}) in {region}")
                for p_info in periods_info:
                    if "Per Hour" in p_info: 
                        logger.info(f"  - {p_info}")
        else:
            logger.warning("No data processed by fetch_aws_gpu_data.")