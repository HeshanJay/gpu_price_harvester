# # main.py
# import functions_framework
# import requests
# from bs4 import BeautifulSoup
# import gspread
# from google.auth import default as adc_default
# from google.oauth2.service_account import Credentials # For local GSpread fallback
# from datetime import datetime, timezone
# import os
# import re
# import logging # For handlers that use logging

# # Import your provider handlers
# from providers import runpod_handler
# from providers import vast_ai_handler
# from providers import coreweave_handler
# from providers import genesiscloud_handler
# from providers import lambda_labs_handler
# from providers import neevcloud_handler
# from providers import sakura_internet_handler
# from providers import soroban_highreso_handler
# from providers import seeweb_handler
# from providers import gcp_handler
# from providers import aws_handler

# # --- Initialize Configuration ---
# print("Initializing configuration from environment variables...")

# # Google Sheets Configuration
# SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER")
# MASTER_WORKSHEET_NAME = os.environ.get("MASTER_WORKSHEET_NAME", "All_GPU_Prices")
# SERVICE_ACCOUNT_FILE = "service_account_creds.json" # For local fallback only
# SCOPES_SHEETS = [
#     "https://www.googleapis.com/auth/spreadsheets",
#     "https://www.googleapis.com/auth/drive.file",
# ]
# gspread_client_instance = None

# # Database Configuration - expecting actual values in these env vars
# DB_USER = os.environ.get("DB_USER")
# DB_PASS = os.environ.get("DB_PASS") # Expecting actual password here
# DB_NAME = os.environ.get("DB_NAME")
# INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
# USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get("USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"

# # Provider API Keys - expecting actual values in these env vars
# VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")
# AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
# AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
# AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION")

# # Set AWS credentials in environment if provided, for Boto3 or other SDKs to pick up
# if AWS_ACCESS_KEY_ID:
#     os.environ['AWS_ACCESS_KEY_ID'] = AWS_ACCESS_KEY_ID # Ensure it's set for the AWS SDK
# if AWS_SECRET_ACCESS_KEY:
#     os.environ['AWS_SECRET_ACCESS_KEY'] = AWS_SECRET_ACCESS_KEY # Ensure it's set for the AWS SDK
# if AWS_DEFAULT_REGION:
#     os.environ['AWS_DEFAULT_REGION'] = AWS_DEFAULT_REGION

# if not VAST_AI_API_KEY:
#     print("WARNING: VAST_AI_API_KEY environment variable not set.")
# if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
#     print("WARNING: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY environment variable not set.")
# if not DB_PASS:
#     print("WARNING: DB_PASS environment variable not set.")


# # --- Database Libraries ---
# import pymysql
# from google.cloud.sql.connector import Connector, IPTypes
# import sqlalchemy

# db_pool = None

# EXPECTED_COLUMNS = [
#     "Provider Name", "Service Provided", "Region", "Currency",
#     "GPU ID", "GPU (H100 or H200 or L40S)",
#     "Memory (GB)", "Display Name(GPU Type)", "GPU Variant Name",
#     "Storage Option", "Amount of Storage", "Network Performance (Gbps)",
#     "Number of Chips", "Period", "Total Price ($)",
#     "Effective Hourly Rate ($/hr)",
#     "Commitment Discount - 1 Month Price ($/hr per GPU)",
#     "Commitment Discount - 3 Month Price ($/hr per GPU)",
#     "Commitment Discount - 6 Month Price ($/hr per GPU)",
#     "Commitment Discount - 12 Month Price ($/hr per GPU)",
#     "Notes / Features", "Last Updated"
# ]

# PYTHON_TO_DB_COLUMN_MAP = {
#     "Provider Name": "provider_name",
#     "Service Provided": "service_provided",
#     "Region": "region",
#     "Currency": "currency_code",
#     "GPU ID": "gpu_id",
#     "GPU (H100 or H200 or L40S)": "gpu_family",
#     "Memory (GB)": "memory_gb",
#     "Display Name(GPU Type)": "display_name_gpu_type",
#     "GPU Variant Name": "gpu_variant_name",
#     "Storage Option": "storage_option",
#     "Amount of Storage": "amount_of_storage",
#     "Network Performance (Gbps)": "network_performance_gbps",
#     "Number of Chips": "number_of_chips",
#     "Period": "period",
#     "Total Price ($)": "total_price_value",
#     "Effective Hourly Rate ($/hr)": "effective_hourly_rate_value",
#     "Commitment Discount - 1 Month Price ($/hr per GPU)": "commitment_1_month_price_value",
#     "Commitment Discount - 3 Month Price ($/hr per GPU)": "commitment_3_month_price_value",
#     "Commitment Discount - 6 Month Price ($/hr per GPU)": "commitment_6_month_price_value",
#     "Commitment Discount - 12 Month Price ($/hr per GPU)": "commitment_12_month_price_value",
#     "Notes / Features": "notes_features",
#     "Last Updated": "last_updated"
# }


# def get_gspread_client_lazy():
#     global gspread_client_instance
#     if gspread_client_instance is None:
#         print("Initializing gspread client...")
#         try:
#             credentials, project = adc_default(scopes=SCOPES_SHEETS)
#             gspread_client_instance = gspread.authorize(credentials)
#             print("Successfully initialized gspread client with Application Default Credentials.")
#         except Exception as e_adc:
#             print(f"Failed to use ADC for gspread: {e_adc}. Falling back to service account file (for local dev).")
#             gac_file_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", SERVICE_ACCOUNT_FILE)
#             if not os.path.exists(gac_file_path):
#                 print(f"ERROR: Service account file '{gac_file_path}' not found. Cannot initialize gspread via file.")
#                 return None
#             try:
#                 creds_from_file = Credentials.from_service_account_file(gac_file_path, scopes=SCOPES_SHEETS)
#                 gspread_client_instance = gspread.authorize(creds_from_file)
#                 print(f"Successfully initialized gspread client with service account file: {gac_file_path}")
#             except Exception as e_file_auth:
#                 print(f"ERROR initializing gspread client with local file '{gac_file_path}': {e_file_auth}");
#                 return None
#     return gspread_client_instance

# def get_db_connection_pool_lazy():
#     global db_pool
#     if db_pool:
#         return db_pool

#     # DB_PASS is now expected to be directly in os.environ
#     required_vars = {"INSTANCE_CONNECTION_NAME": INSTANCE_CONNECTION_NAME, "DB_USER": DB_USER, "DB_PASS": DB_PASS, "DB_NAME": DB_NAME}
#     missing_vars = [key for key, value in required_vars.items() if not value]
#     if missing_vars:
#         print(f"CRITICAL ERROR: Missing database environment variables: {', '.join(missing_vars)}")
#         if "DB_PASS" in missing_vars:
#             print("DB_PASS is missing. Ensure it's set as an environment variable containing the actual password.")
#         raise ValueError(f"Missing DB environment variables: {', '.join(missing_vars)}")

#     print("Initializing database connection pool...")
#     try:
#         ip_type_to_use = IPTypes.PUBLIC if USE_PUBLIC_IP_FOR_CONNECTOR else IPTypes.PRIVATE
#         print(f"Connector IP Type: {ip_type_to_use}")
#         connector = Connector(ip_type=ip_type_to_use)

#         def getconn() -> pymysql.connections.Connection:
#             conn: pymysql.connections.Connection = connector.connect(
#                 INSTANCE_CONNECTION_NAME,
#                 "pymysql",
#                 user=DB_USER,
#                 password=DB_PASS, # Uses DB_PASS directly from environment
#                 db=DB_NAME
#             )
#             return conn

#         db_pool = sqlalchemy.create_engine(
#             "mysql+pymysql://",
#             creator=getconn,
#             pool_size=5,
#             max_overflow=2,
#             pool_timeout=30,
#             pool_recycle=1800,
#         )
#         print("Successfully initialized database connection pool.")
#         with db_pool.connect() as test_conn:
#             test_conn.execute(sqlalchemy.text("SELECT 1"))
#         print("Database connection pool test successful.")
#         return db_pool
#     except Exception as e:
#         print(f"ERROR initializing database connection pool: {e}")
#         import traceback
#         traceback.print_exc()
#         raise

# # ... (create_gpu_prices_table_if_not_exists, write_all_data_to_google_sheet, write_all_data_to_mysql_db remain the same) ...
# def create_gpu_prices_table_if_not_exists(pool):
#     table_name = "gpu_prices"
#     create_table_sql = f"""
#     CREATE TABLE IF NOT EXISTS {table_name} (
#         id INT AUTO_INCREMENT PRIMARY KEY,
#         provider_name VARCHAR(255),
#         service_provided VARCHAR(255),
#         region VARCHAR(255),
#         currency_code VARCHAR(10),
#         gpu_id VARCHAR(255),
#         gpu_family VARCHAR(50) COMMENT 'H100 or H200 or L40S',
#         memory_gb INT NULL,
#         display_name_gpu_type VARCHAR(255),
#         gpu_variant_name VARCHAR(255),
#         storage_option TEXT,
#         amount_of_storage TEXT,
#         network_performance_gbps VARCHAR(255),
#         number_of_chips INT NULL,
#         period VARCHAR(50),
#         total_price_value VARCHAR(255) NULL,
#         effective_hourly_rate_value DECIMAL(10, 4) NULL,
#         commitment_1_month_price_value DECIMAL(10, 4) NULL,
#         commitment_3_month_price_value DECIMAL(10, 4) NULL,
#         commitment_6_month_price_value DECIMAL(10, 4) NULL,
#         commitment_12_month_price_value DECIMAL(10, 4) NULL,
#         notes_features TEXT,
#         last_updated TIMESTAMP,
#         UNIQUE KEY unique_gpu_offering_historical (
#             provider_name(50),
#             gpu_variant_name(100),
#             number_of_chips,
#             period(20),
#             region(50),
#             currency_code(10),
#             display_name_gpu_type(100),
#             last_updated
#         )
#     );
#     """
#     try:
#         with pool.connect() as db_conn:
#             db_conn.execute(sqlalchemy.text(create_table_sql))
#             db_conn.commit()
#         print(f"Table '{table_name}' checked/created successfully with currency_code and updated unique key.")
#     except Exception as e:
#         print(f"ERROR checking/creating table '{table_name}': {e}")
#         import traceback
#         traceback.print_exc()

# def write_all_data_to_google_sheet(all_data_rows_dicts, target_worksheet_name, client):
#     if not client:
#         print("Google Sheets client not available. Skipping sheet update.")
#         return False
#     if not all_data_rows_dicts:
#         print(f"No data to update worksheet '{target_worksheet_name}'.")
#         return False

#     current_spreadsheet_id = SPREADSHEET_ID
#     if not current_spreadsheet_id or "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER" in current_spreadsheet_id:
#         print("CRITICAL ERROR: SPREADSHEET_ID not set or is placeholder for Google Sheet write.")
#         return False

#     print(f"Updating Sheet ID: '{current_spreadsheet_id}', Worksheet: '{target_worksheet_name}'")
#     try:
#         spreadsheet = client.open_by_key(current_spreadsheet_id)
#         try:
#             worksheet = spreadsheet.worksheet(target_worksheet_name)
#         except gspread.exceptions.WorksheetNotFound:
#             print(f"Worksheet '{target_worksheet_name}' not found. Creating...")
#             worksheet = spreadsheet.add_worksheet(title=target_worksheet_name, rows="3000", cols=len(EXPECTED_COLUMNS))
#             print(f"Worksheet created.")

#         current_time_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
#         rows_to_upload = [EXPECTED_COLUMNS]
#         for data_dict in all_data_rows_dicts:
#             row = [data_dict.get(col, "N/A") if col != "Last Updated" else current_time_utc_str for col in EXPECTED_COLUMNS]
#             rows_to_upload.append(row)

#         worksheet.clear()
#         worksheet.update(range_name="A1", values=rows_to_upload, value_input_option='USER_ENTERED')
#         print(f"Successfully updated Sheet '{spreadsheet.title} | {worksheet.title}' with {len(all_data_rows_dicts)} total rows.")
#         return True
#     except Exception as e:
#         print(f"ERROR in write_all_data_to_google_sheet: {e}")
#         import traceback
#         traceback.print_exc()
#         return False

# def write_all_data_to_mysql_db(all_data_rows_dicts, pool):
#     if not pool:
#         print("Database pool not available. Skipping MySQL write.")
#         return False
#     if not all_data_rows_dicts:
#         print("No data to write to MySQL.")
#         return False

#     table_name = "gpu_prices"
#     current_time_utc_for_db = datetime.now(timezone.utc)

#     rows_to_insert_for_db = []
#     for data_dict_py in all_data_rows_dicts:
#         db_row = {}
#         for python_key, db_col_name in PYTHON_TO_DB_COLUMN_MAP.items():
#             val = data_dict_py.get(python_key)

#             if db_col_name == "last_updated":
#                 db_row[db_col_name] = current_time_utc_for_db
#             elif val == "N/A" or val == "" or (isinstance(val, str) and val.strip().lower() == "contact sales"):
#                 if db_col_name in [
#                     "memory_gb", "number_of_chips",
#                     "effective_hourly_rate_value",
#                     "commitment_1_month_price_value",
#                     "commitment_3_month_price_value",
#                     "commitment_6_month_price_value",
#                     "commitment_12_month_price_value"
#                 ]:
#                     db_row[db_col_name] = None
#                 elif db_col_name == "currency_code" and (val == "N/A" or val == ""):
#                     db_row[db_col_name] = None
#                 else:
#                     db_row[db_col_name] = val if val != "" else None
#             elif db_col_name in ["memory_gb", "number_of_chips"] and val is not None:
#                 try:
#                     db_row[db_col_name] = int(val)
#                 except (ValueError, TypeError):
#                     print(f"Warning: Could not convert '{val}' to int for '{db_col_name}'. Setting to NULL.")
#                     db_row[db_col_name] = None
#             elif db_col_name in [
#                     "effective_hourly_rate_value",
#                     "commitment_1_month_price_value",
#                     "commitment_3_month_price_value",
#                     "commitment_6_month_price_value",
#                     "commitment_12_month_price_value"
#                 ] and val is not None:
#                 try:
#                     str_val = str(val).replace('$', '').replace('₹', '').replace('€', '').replace(',', '').strip()
#                     if not str_val or not re.match(r"^-?\d+\.?\d*$", str_val): # Check if it's a valid number string after stripping
#                         raise ValueError("String is not a valid number after stripping symbols.")
#                     db_row[db_col_name] = float(str_val)
#                 except (ValueError, TypeError):
#                     print(f"Warning: Could not convert '{val}' to float for '{db_col_name}'. Setting to NULL.")
#                     db_row[db_col_name] = None
#             else:
#                 db_row[db_col_name] = val
#         rows_to_insert_for_db.append(db_row)

#     if not rows_to_insert_for_db:
#         print("No rows processed into DB format for MySQL insertion.")
#         return False

#     try:
#         with pool.connect() as db_conn:
#             if rows_to_insert_for_db:
#                 db_column_names = list(PYTHON_TO_DB_COLUMN_MAP.values())
#                 sql_insert_query_str = f"INSERT INTO {table_name} ({', '.join(db_column_names)}) VALUES ({', '.join([':' + name for name in db_column_names])})"
#                 insert_stmt = sqlalchemy.text(sql_insert_query_str)
#                 db_conn.execute(insert_stmt, rows_to_insert_for_db)
#                 db_conn.commit()
#             print(f"Successfully APPENDED {len(rows_to_insert_for_db)} rows into MySQL table '{table_name}'. Table now contains historical data.")
#             return True
#     except Exception as e:
#         print(f"ERROR in write_all_data_to_mysql_db during insert: {e}")
#         import traceback
#         traceback.print_exc()
#         if rows_to_insert_for_db:
#             print(f"Sample data for failed insert (first row): {rows_to_insert_for_db[0]}")
#         return False

# @functions_framework.http
# def process_all_gpu_prices_http(request):
#     print(f"Cloud Function 'process_all_gpu_prices_http' triggered at {datetime.now(timezone.utc)}")

#     # Configuration (including secrets like DB_PASS, API keys) is expected to be loaded
#     # directly from environment variables when the Cloud Function instance starts.

#     gs_client = None
#     try:
#         gs_client = get_gspread_client_lazy()
#     except Exception as auth_e:
#         print(f"Google Sheets Auth Error: {auth_e}. Proceeding.")

#     db_pool_instance = None
#     try:
#         # This will now use DB_PASS directly from os.environ if set.
#         db_pool_instance = get_db_connection_pool_lazy()
#         if db_pool_instance:
#             create_gpu_prices_table_if_not_exists(db_pool_instance)
#     except Exception as db_setup_e:
#         print(f"Database Connection/Setup Error: {db_setup_e}. Function might not write to DB.")

#     resolved_spreadsheet_id = SPREADSHEET_ID
#     if gs_client and (("YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER" in resolved_spreadsheet_id and resolved_spreadsheet_id == os.environ.get("SPREADSHEET_ID", "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER")) or not resolved_spreadsheet_id) :
#         print("CRITICAL WARNING: SPREADSHEET_ID placeholder or empty. Google Sheet update will fail.")

#     master_data_list = []

#     # --- Process RunPod ---
#     try:
#         print("\n--- Processing RunPod ---")
#         runpod_page_content = requests.get(runpod_handler.RUNPOD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         runpod_page_content.raise_for_status()
#         runpod_soup = BeautifulSoup(runpod_page_content.text, "html.parser")
#         runpod_data = runpod_handler.fetch_runpod_data(runpod_soup)
#         if runpod_data: master_data_list.extend(runpod_data)
#         print(f"RunPod: Added {len(runpod_data) if runpod_data else 0} rows.")
#     except Exception as e: print(f"ERROR processing RunPod: {e}"); import traceback; traceback.print_exc()

#     # --- Process Vast.ai ---
#     # VAST_AI_API_KEY is expected to be in os.environ directly by vast_ai_handler or was set globally
#     try:
#         print("\n--- Processing Vast.ai ---")
#         if not VAST_AI_API_KEY: # VAST_AI_API_KEY is now a global variable from os.environ
#             print("WARNING: VAST_AI_API_KEY not found in environment for Vast.ai handler. Skipping.")
#         else:
#             # If vast_ai_handler directly uses os.environ.get("VAST_AI_API_KEY"), it will work.
#             # If it expected it to be passed, you'd pass VAST_AI_API_KEY here.
#             vast_data = vast_ai_handler.fetch_vast_ai_data()
#             if vast_data: master_data_list.extend(vast_data)
#             print(f"Vast.ai: Added {len(vast_data) if vast_data else 0} rows.")
#     except Exception as e: print(f"ERROR processing Vast.ai: {e}"); import traceback; traceback.print_exc()

#     # ... (Processing for CoreWeave, Genesis, Lambda, Neev, Sakura, Soroban, Seeweb remain the same,
#     #      assuming their handlers don't have specific secret fetching logic that needs changing)
#     # --- Process CoreWeave ---
#     try:
#         print("\n--- Processing CoreWeave ---")
#         coreweave_page_content = requests.get(coreweave_handler.COREWEAVE_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         coreweave_page_content.raise_for_status()
#         coreweave_soup = BeautifulSoup(coreweave_page_content.text, "html.parser")
#         coreweave_data = coreweave_handler.fetch_coreweave_data(coreweave_soup)
#         if coreweave_data: master_data_list.extend(coreweave_data)
#         print(f"CoreWeave: Added {len(coreweave_data) if coreweave_data else 0} rows.")
#     except Exception as e: print(f"ERROR processing CoreWeave: {e}"); import traceback; traceback.print_exc()

#     # --- Process Genesis Cloud ---
#     try:
#         print("\n--- Processing Genesis Cloud ---")
#         genesis_page_content = requests.get(genesiscloud_handler.GENESISCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         genesis_page_content.raise_for_status()
#         genesis_soup = BeautifulSoup(genesis_page_content.text, "html.parser")
#         genesis_data = genesiscloud_handler.fetch_genesiscloud_data(genesis_soup)
#         if genesis_data: master_data_list.extend(genesis_data)
#         print(f"Genesis Cloud: Added {len(genesis_data) if genesis_data else 0} rows.")
#     except Exception as e: print(f"ERROR processing Genesis Cloud: {e}"); import traceback; traceback.print_exc()

#     # --- Process Lambda Labs ---
#     try:
#         print("\n--- Processing Lambda Labs ---")
#         lambda_page_content = requests.get(lambda_labs_handler.LAMBDALABS_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         lambda_page_content.raise_for_status()
#         lambda_soup = BeautifulSoup(lambda_page_content.text, "html.parser")
#         lambda_data = lambda_labs_handler.fetch_lambda_labs_data(lambda_soup)
#         if lambda_data: master_data_list.extend(lambda_data)
#         print(f"Lambda Labs: Added {len(lambda_data) if lambda_data else 0} rows.")
#     except Exception as e: print(f"ERROR processing Lambda Labs: {e}"); import traceback; traceback.print_exc()

#     # --- Process Neevcloud ---
#     try:
#         print("\n--- Processing Neevcloud ---")
#         neevcloud_page_content_text = None
#         try:
#             response_neevcloud = requests.get(neevcloud_handler.NEEVCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#             response_neevcloud.raise_for_status()
#             neevcloud_page_content_text = response_neevcloud.text
#         except Exception as e_fetch_neev_http:
#             print(f"ERROR fetching Neevcloud page (HTTP Context): {e_fetch_neev_http}")

#         neevcloud_soup = BeautifulSoup(neevcloud_page_content_text, "html.parser") if neevcloud_page_content_text else BeautifulSoup("", "html.parser")
#         neevcloud_data = neevcloud_handler.fetch_neevcloud_data(neevcloud_soup)
#         if neevcloud_data: master_data_list.extend(neevcloud_data)
#         print(f"Neevcloud: Added {len(neevcloud_data) if neevcloud_data else 0} rows.")
#     except Exception as e_neev: print(f"ERROR processing Neevcloud: {e_neev}"); import traceback; traceback.print_exc()


#     # --- Process Sakura Internet (VRT and PHY) ---
#     try:
#         print("\n--- Processing Sakura Internet ---")
#         html_vrt_content_http = None
#         html_phy_content_http = None
#         sakura_data_http = []

#         try:
#             response_vrt_http = requests.get(sakura_internet_handler.SAKURA_VRT_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#             response_vrt_http.raise_for_status()
#             html_vrt_content_http = response_vrt_http.text
#         except Exception as e_vrt_http: print(f"ERROR fetching Sakura VRT page (HTTP Context): {e_vrt_http}")
#         try:
#             response_phy_http = requests.get(sakura_internet_handler.SAKURA_PHY_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#             response_phy_http.raise_for_status()
#             html_phy_content_http = response_phy_http.text
#         except Exception as e_phy_http: print(f"ERROR fetching Sakura PHY page (HTTP Context): {e_phy_http}")

#         soup_vrt_http = BeautifulSoup(html_vrt_content_http, "html.parser") if html_vrt_content_http else BeautifulSoup("", "html.parser")
#         soup_phy_http = BeautifulSoup(html_phy_content_http, "html.parser") if html_phy_content_http else BeautifulSoup("", "html.parser")
#         sakura_data_http = sakura_internet_handler.fetch_sakura_internet_data(soup_vrt_http, soup_phy_http)
#         if sakura_data_http: master_data_list.extend(sakura_data_http)
#         print(f"Sakura Internet: Added {len(sakura_data_http) if sakura_data_http else 0} rows.")
#     except Exception as e_sakura: print(f"ERROR processing Sakura Internet: {e_sakura}"); import traceback; traceback.print_exc()

#     # --- Process Soroban (Highreso) ---
#     try:
#         print("\n--- Processing Soroban (Highreso) ---")
#         soroban_page_content = requests.get(soroban_highreso_handler.SOROBAN_AISPACON_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         soroban_page_content.raise_for_status()
#         soroban_soup = BeautifulSoup(soroban_page_content.text, "html.parser")
#         soroban_data = soroban_highreso_handler.fetch_soroban_highreso_data(soroban_soup)
#         if soroban_data: master_data_list.extend(soroban_data)
#         print(f"Soroban (Highreso): Added {len(soroban_data) if soroban_data else 0} rows.")
#     except Exception as e_soroban: print(f"ERROR processing Soroban (Highreso): {e_soroban}"); import traceback; traceback.print_exc()

#     # --- Process Seeweb ---
#     try:
#         print("\n--- Processing Seeweb ---")
#         html_cloud_server_gpu_http = None
#         html_serverless_gpu_http = None
#         seeweb_data_http = []
#         try:
#             response_csg_http = requests.get(seeweb_handler.SEEWEB_CLOUD_SERVER_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#             response_csg_http.raise_for_status()
#             html_cloud_server_gpu_http = response_csg_http.text
#         except Exception as e_csg_http: print(f"ERROR fetching Seeweb Cloud Server GPU page (HTTP Context): {e_csg_http}")
#         try:
#             response_slg_http = requests.get(seeweb_handler.SEEWEB_SERVERLESS_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#             response_slg_http.raise_for_status()
#             html_serverless_gpu_http = response_slg_http.text
#         except Exception as e_slg_http: print(f"ERROR fetching Seeweb Serverless GPU page (HTTP Context): {e_slg_http}")

#         soup_cloud_server_gpu_http = BeautifulSoup(html_cloud_server_gpu_http, "html.parser") if html_cloud_server_gpu_http else BeautifulSoup("", "html.parser")
#         soup_serverless_gpu_http = BeautifulSoup(html_serverless_gpu_http, "html.parser") if html_serverless_gpu_http else BeautifulSoup("", "html.parser")
#         seeweb_data_http = seeweb_handler.fetch_seeweb_data(soup_cloud_server_gpu_http, soup_serverless_gpu_http)
#         if seeweb_data_http: master_data_list.extend(seeweb_data_http)
#         print(f"Seeweb: Added {len(seeweb_data_http) if seeweb_data_http else 0} rows.")
#     except Exception as e_seeweb_main: print(f"ERROR processing Seeweb (HTTP Context): {e_seeweb_main}"); import traceback; traceback.print_exc()


#     # --- Process Google Cloud Platform (GCP) ---
#     try:
#         print("\n--- Processing Google Cloud Platform (GCP) ---")
#         gcp_data = gcp_handler.fetch_gcp_gpu_data() # Assumes gcp_handler uses ADC via function's service account
#         if gcp_data:
#             master_data_list.extend(gcp_data)
#         print(f"Google Cloud Platform: Added {len(gcp_data) if gcp_data else 0} rows.")
#     except Exception as e_gcp:
#         print(f"ERROR processing Google Cloud Platform: {e_gcp}")
#         import traceback
#         traceback.print_exc()

#     # --- Process Amazon Web Services (AWS) ---
#     # AWS keys are expected to be in os.environ directly by Boto3 if set globally
#     try:
#         print("\n--- Processing Amazon Web Services (AWS) ---")
#         if not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY): # Check global vars
#             print("WARNING: AWS credentials not found in environment for AWS handler. Skipping.")
#         else:
#             aws_data = aws_handler.fetch_aws_gpu_data() # Assumes handler (boto3) reads from os.environ
#             if aws_data:
#                 master_data_list.extend(aws_data)
#             print(f"Amazon Web Services (AWS): Added {len(aws_data) if aws_data else 0} rows.")
#     except Exception as e_aws:
#         print(f"ERROR processing Amazon Web Services (AWS): {e_aws}")
#         import traceback
#         traceback.print_exc()


#     sheet_update_success = False
#     db_write_success = False

#     if master_data_list:
#         if gs_client:
#             target_worksheet_gs = MASTER_WORKSHEET_NAME
#             sheet_update_success = write_all_data_to_google_sheet(master_data_list, target_worksheet_gs, gs_client)

#         if db_pool_instance:
#             db_write_success = write_all_data_to_mysql_db(master_data_list, db_pool_instance)

#         final_messages = []
#         if gs_client: final_messages.append(f"GSheet update: {'succeeded' if sheet_update_success else 'failed'}")
#         else: final_messages.append("GSheet update: skipped (client not available)")

#         if db_pool_instance: final_messages.append(f"DB write: {'succeeded' if db_write_success else 'failed'}")
#         else: final_messages.append("DB write: skipped (pool not available or setup failed)")

#         msg = f"Processed {len(master_data_list)} total rows. {'. '.join(final_messages)}."
#         print(msg)
#         if (gs_client and sheet_update_success) or (db_pool_instance and db_write_success) or (not gs_client and not db_pool_instance and master_data_list):
#             return msg, 200
#         else:
#             return msg, 500
#     else:
#         msg = "No GPU data processed from any provider."
#         print(msg)
#         return msg, 200

# if __name__ == "__main__":
#     print("--- Running Local Test: All Providers to Google Sheet AND MySQL DB ---")

#     env_path = os.path.join(os.path.dirname(__file__), '.env')
#     if os.path.exists(env_path):
#         print(f"Loading environment variables from {env_path}")
#         with open(env_path, 'r') as f:
#             for line in f:
#                 line = line.strip()
#                 if not line or line.startswith('#'):
#                     continue
#                 if '=' in line:
#                     key, value_str = line.split('=', 1)
#                     key = key.strip()
#                     value = value_str.strip()
#                     if (value.startswith('"') and value.endswith('"')) or \
#                        (value.startswith("'") and value.endswith("'")):
#                         value = value[1:-1]
#                     os.environ[key] = value

#         # Re-initialize global config variables after .env load for local testing
#         # This will pick up the direct values from .env for DB_PASS, API keys etc.
#         SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", SPREADSHEET_ID)
#         MASTER_WORKSHEET_NAME = os.environ.get("MASTER_WORKSHEET_NAME", MASTER_WORKSHEET_NAME)
#         DB_USER = os.environ.get("DB_USER")
#         DB_PASS = os.environ.get("DB_PASS") # Expecting actual password from .env
#         DB_NAME = os.environ.get("DB_NAME")
#         INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
#         USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get("USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"

#         VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")
#         AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
#         if AWS_ACCESS_KEY_ID: os.environ['AWS_ACCESS_KEY_ID'] = AWS_ACCESS_KEY_ID # ensure for boto3
#         AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
#         if AWS_SECRET_ACCESS_KEY: os.environ['AWS_SECRET_ACCESS_KEY'] = AWS_SECRET_ACCESS_KEY # ensure for boto3
#         AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION")
#         if AWS_DEFAULT_REGION: os.environ['AWS_DEFAULT_REGION'] = AWS_DEFAULT_REGION


#     print("\n--- DEBUG: Environment Variables After .env Load (Local Test) ---")
#     print(f"DEBUG: SPREADSHEET_ID='{SPREADSHEET_ID}'")
#     print(f"DEBUG: VAST_AI_API_KEY='{VAST_AI_API_KEY}'")
#     print(f"DEBUG: AWS_ACCESS_KEY_ID is {'SET' if AWS_ACCESS_KEY_ID else 'NOT SET'}")
#     print(f"DEBUG: AWS_SECRET_ACCESS_KEY is {'SET' if AWS_SECRET_ACCESS_KEY else 'NOT SET'}")
#     print(f"DEBUG: AWS_DEFAULT_REGION='{AWS_DEFAULT_REGION}'")
#     print(f"DEBUG: INSTANCE_CONNECTION_NAME='{INSTANCE_CONNECTION_NAME}'")
#     print(f"DEBUG: DB_USER='{DB_USER}'")
#     print(f"DEBUG: DB_PASS is {'SET' if DB_PASS and DB_PASS.strip() else 'NOT SET or EMPTY'}")
#     print(f"DEBUG: DB_NAME='{DB_NAME}'")
#     print(f"DEBUG: GOOGLE_APPLICATION_CREDENTIALS='{os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}'")
#     print("---------------------------------------------------\n")

#     current_test_spreadsheet_id = SPREADSHEET_ID
#     if ("YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER" in current_test_spreadsheet_id and os.environ.get("SPREADSHEET_ID") is None and current_test_spreadsheet_id == "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER") or not current_test_spreadsheet_id:
#         print("\nCRITICAL: Update SPREADSHEET_ID (or set SPREADSHEET_ID env var) for local GSheet test.\n")
#     else:
#         print(f"Local GSheet Config: SPREADSHEET_ID='{current_test_spreadsheet_id}', Master Worksheet='{MASTER_WORKSHEET_NAME}'")

#     gs_client_local = None
#     try:
#         gs_client_local = get_gspread_client_lazy()
#     except Exception as e_gs:
#         print(f"Failed to init gspread for local test: {e_gs}")

#     db_pool_local = None
#     if not (INSTANCE_CONNECTION_NAME and DB_USER and DB_PASS and DB_NAME): # DB_PASS is now direct
#         print("\nWARNING: One or more required database environment variables (INSTANCE_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME) are not set or are empty for local test.")
#         print("Skipping database part of the local test.")
#     else:
#         try:
#             print("\n--- Attempting to connect to Database for Local Test ---")
#             db_pool_local = get_db_connection_pool_lazy()
#             if db_pool_local:
#                 create_gpu_prices_table_if_not_exists(db_pool_local)
#             else:
#                 print("DB Pool local is None after get_db_connection_pool_lazy, cannot proceed with table creation.")
#         except Exception as e_db_local:
#             print(f"Failed to init DB pool or create table for local test: {e_db_local}")
#             import traceback
#             traceback.print_exc()
#             print("Proceeding with local test without Database.")
#             db_pool_local = None

#     master_data_list_local = []

#     # ... (Local test processing for providers remains largely the same,
#     #      as they will use the VAST_AI_API_KEY, AWS_ACCESS_KEY_ID etc.
#     #      variables now populated directly from os.environ after .env loading) ...

#     # RunPod
#     try:
#         print("\n--- Processing RunPod (Local Test) ---")
#         runpod_page_content_local = requests.get(runpod_handler.RUNPOD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         runpod_page_content_local.raise_for_status()
#         runpod_soup_local = BeautifulSoup(runpod_page_content_local.text, "html.parser")
#         runpod_data_local = runpod_handler.fetch_runpod_data(runpod_soup_local)
#         if runpod_data_local: master_data_list_local.extend(runpod_data_local)
#         print(f"RunPod (Local Test) processed {len(runpod_data_local) if runpod_data_local else 0} rows.")
#     except Exception as e_runpod_local: print(f"Error in local RunPod test: {e_runpod_local}"); import traceback; traceback.print_exc()

#     # Vast.ai
#     try:
#         print("\n--- Processing Vast.ai (Local Test) ---")
#         if not VAST_AI_API_KEY: print("WARNING (Vast.ai Local Test): VAST_AI_API_KEY not set.")
#         vast_data_local = vast_ai_handler.fetch_vast_ai_data()
#         if vast_data_local: master_data_list_local.extend(vast_data_local)
#         print(f"Vast.ai (Local Test) processed {len(vast_data_local) if vast_data_local else 0} rows.")
#     except Exception as e_vast_local: print(f"Error in local Vast.ai test: {e_vast_local}"); import traceback; traceback.print_exc()

#     # CoreWeave, Genesis, Lambda, Neev, Sakura, Soroban, Seeweb local tests remain structurally the same

#     # GCP
#     try:
#         print("\n--- Processing Google Cloud Platform (GCP) (Local Test) ---")
#         gcp_data_local = gcp_handler.fetch_gcp_gpu_data()
#         if gcp_data_local: master_data_list_local.extend(gcp_data_local)
#         print(f"Google Cloud Platform (Local Test) processed {len(gcp_data_local) if gcp_data_local else 0} rows.")
#     except Exception as e_gcp_local: print(f"Error in local GCP test: {e_gcp_local}"); import traceback; traceback.print_exc()

#     # AWS
#     try:
#         print("\n--- Processing Amazon Web Services (AWS) (Local Test) ---")
#         if not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY): print("WARNING (AWS Local Test): AWS credentials not set.")
#         aws_data_local = aws_handler.fetch_aws_gpu_data()
#         if aws_data_local: master_data_list_local.extend(aws_data_local)
#         print(f"Amazon Web Services (AWS) (Local Test) processed {len(aws_data_local) if aws_data_local else 0} rows.")
#     except Exception as e_aws_local: print(f"Error in local AWS test: {e_aws_local}"); import traceback; traceback.print_exc()


#     if master_data_list_local:
#         print(f"\n--- Sample of COMBINED data for Sheet & DB ({len(master_data_list_local)} total rows) ---")
#         if master_data_list_local:
#             print(f"Sample Row 1 (from provider '{master_data_list_local[0].get('Provider Name')}'):")
#             for k,v in master_data_list_local[0].items(): print(f"  {k}: {v}")
#             print("-" * 20)

#         if gs_client_local:
#             target_ws_local = MASTER_WORKSHEET_NAME
#             print(f"\n--- Writing to Google Sheet (Local Test): {target_ws_local}_TestLocal ---")
#             write_all_data_to_google_sheet(master_data_list_local, target_ws_local + "_TestLocal", gs_client_local)
#         else:
#             print("\nLocal test: Could not initialize Google Sheets client or SPREADSHEET_ID issue, skipping GSheet write.")

#         if db_pool_local:
#             print("\n--- Writing to MySQL DB (Local Test) ---")
#             write_all_data_to_mysql_db(master_data_list_local, db_pool_local)
#         else:
#             print("\nLocal test: DB pool not available (or relevant DB config missing), skipping MySQL write.")

#     else:
#         print("\nLocal test: No data processed from any provider.")

#     print("--- Local Test Finished ---")



import functions_framework
import requests
from bs4 import BeautifulSoup
import gspread
from google.auth import default as adc_default
from google.oauth2.service_account import Credentials # For local GSpread fallback
from datetime import datetime, timezone
import os
import re
import logging # For handlers that use logging

# Import your provider handlers
from providers import runpod_handler
from providers import vast_ai_handler
from providers import coreweave_handler
from providers import genesiscloud_handler
from providers import lambda_labs_handler
from providers import neevcloud_handler
from providers import sakura_internet_handler
from providers import soroban_highreso_handler
from providers import seeweb_handler
from providers import gcp_handler # Now uses web scraping via fetch_gcp_gpu_data_from_html
from providers import aws_handler

# --- Initialize Configuration ---
print("Initializing configuration from environment variables...")

# Google Sheets Configuration
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER")
MASTER_WORKSHEET_NAME = os.environ.get("MASTER_WORKSHEET_NAME", "All_GPU_Prices")
SERVICE_ACCOUNT_FILE = "service_account_creds.json" # For local fallback only
SCOPES_SHEETS = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
gspread_client_instance = None

# Database Configuration
DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
DB_NAME = os.environ.get("DB_NAME")
INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get("USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"

# Provider API Keys - This section was missing in the template you provided, re-adding it for completeness
VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION")

if AWS_ACCESS_KEY_ID:
    os.environ['AWS_ACCESS_KEY_ID'] = AWS_ACCESS_KEY_ID
if AWS_SECRET_ACCESS_KEY:
    os.environ['AWS_SECRET_ACCESS_KEY'] = AWS_SECRET_ACCESS_KEY
if AWS_DEFAULT_REGION:
    os.environ['AWS_DEFAULT_REGION'] = AWS_DEFAULT_REGION


# --- Database Libraries ---
import pymysql
from google.cloud.sql.connector import Connector, IPTypes
import sqlalchemy

db_pool = None

EXPECTED_COLUMNS = [
    "Provider Name", "Service Provided", "Region", "Currency",
    "GPU ID", "GPU (H100 or H200 or L40S)",
    "Memory (GB)", "Display Name(GPU Type)", "GPU Variant Name",
    "Storage Option", "Amount of Storage", "Network Performance (Gbps)",
    "Number of Chips", "Period", "Total Price ($)",
    "Effective Hourly Rate ($/hr)",
    "Commitment Discount - 1 Month Price ($/hr per GPU)",
    "Commitment Discount - 3 Month Price ($/hr per GPU)",
    "Commitment Discount - 6 Month Price ($/hr per GPU)",
    "Commitment Discount - 12 Month Price ($/hr per GPU)",
    "Notes / Features", "Last Updated"
]

PYTHON_TO_DB_COLUMN_MAP = {
    "Provider Name": "provider_name",
    "Service Provided": "service_provided",
    "Region": "region",
    "Currency": "currency_code",
    "GPU ID": "gpu_id",
    "GPU (H100 or H200 or L40S)": "gpu_family",
    "Memory (GB)": "memory_gb",
    "Display Name(GPU Type)": "display_name_gpu_type",
    "GPU Variant Name": "gpu_variant_name",
    "Storage Option": "storage_option",
    "Amount of Storage": "amount_of_storage",
    "Network Performance (Gbps)": "network_performance_gbps",
    "Number of Chips": "number_of_chips",
    "Period": "period",
    "Total Price ($)": "total_price_value",
    "Effective Hourly Rate ($/hr)": "effective_hourly_rate_value",
    "Commitment Discount - 1 Month Price ($/hr per GPU)": "commitment_1_month_price_value",
    "Commitment Discount - 3 Month Price ($/hr per GPU)": "commitment_3_month_price_value",
    "Commitment Discount - 6 Month Price ($/hr per GPU)": "commitment_6_month_price_value",
    "Commitment Discount - 12 Month Price ($/hr per GPU)": "commitment_12_month_price_value",
    "Notes / Features": "notes_features",
    "Last Updated": "last_updated"
}


def get_gspread_client_lazy():
    global gspread_client_instance
    if gspread_client_instance is None:
        print("Initializing gspread client...")
        try:
            credentials, project = adc_default(scopes=SCOPES_SHEETS)
            gspread_client_instance = gspread.authorize(credentials)
            print("Successfully initialized gspread client with Application Default Credentials.")
        except Exception as e_adc:
            print(f"Failed to use ADC for gspread: {e_adc}. Falling back to service account file.")
            gac_file_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", SERVICE_ACCOUNT_FILE)
            if not os.path.exists(gac_file_path):
                print(f"ERROR: Service account file '{gac_file_path}' not found. Cannot initialize gspread via file.")
                return None
            try:
                creds_from_file = Credentials.from_service_account_file(gac_file_path, scopes=SCOPES_SHEETS)
                gspread_client_instance = gspread.authorize(creds_from_file)
                print(f"Successfully initialized gspread client with service account file: {gac_file_path}")
            except Exception as e_file_auth:
                print(f"ERROR initializing gspread client with local file '{gac_file_path}': {e_file_auth}");
                return None
    return gspread_client_instance

def get_db_connection_pool_lazy():
    global db_pool
    if db_pool:
        return db_pool

    required_vars = {"INSTANCE_CONNECTION_NAME": INSTANCE_CONNECTION_NAME, "DB_USER": DB_USER, "DB_PASS": DB_PASS, "DB_NAME": DB_NAME}
    missing_vars = [key for key, value in required_vars.items() if not value]
    if missing_vars:
        print(f"CRITICAL ERROR: Missing database environment variables: {', '.join(missing_vars)}")
        raise ValueError(f"Missing DB environment variables: {', '.join(missing_vars)}")

    print("Initializing database connection pool...")
    try:
        ip_type_to_use = IPTypes.PUBLIC if USE_PUBLIC_IP_FOR_CONNECTOR else IPTypes.PRIVATE
        connector = Connector(ip_type=ip_type_to_use)
        
        def getconn() -> pymysql.connections.Connection:
            conn: pymysql.connections.Connection = connector.connect(
                INSTANCE_CONNECTION_NAME,
                "pymysql",
                user=DB_USER,
                password=DB_PASS,
                db=DB_NAME
            )
            return conn

        db_pool = sqlalchemy.create_engine(
            "mysql+pymysql://",
            creator=getconn,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,
        )
        print("Successfully initialized database connection pool.")
        with db_pool.connect() as test_conn:
            test_conn.execute(sqlalchemy.text("SELECT 1"))
        print("Database connection pool test successful.")
        return db_pool
    except Exception as e:
        print(f"ERROR initializing database connection pool: {e}")
        import traceback
        traceback.print_exc()
        raise

def create_gpu_prices_table_if_not_exists(pool):
    table_name = "gpu_prices"
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        provider_name VARCHAR(255),
        service_provided VARCHAR(255),
        region VARCHAR(255),
        currency_code VARCHAR(10),
        gpu_id VARCHAR(255),
        gpu_family VARCHAR(50) COMMENT 'H100 or H200 or L40S',
        memory_gb INT NULL,
        display_name_gpu_type VARCHAR(255),
        gpu_variant_name VARCHAR(255),
        storage_option TEXT,
        amount_of_storage TEXT,
        network_performance_gbps VARCHAR(255),
        number_of_chips INT NULL,
        period VARCHAR(50),
        total_price_value VARCHAR(255) NULL,
        effective_hourly_rate_value DECIMAL(10, 4) NULL,
        commitment_1_month_price_value DECIMAL(10, 4) NULL,
        commitment_3_month_price_value DECIMAL(10, 4) NULL,
        commitment_6_month_price_value DECIMAL(10, 4) NULL,
        commitment_12_month_price_value DECIMAL(10, 4) NULL,
        notes_features TEXT,
        last_updated TIMESTAMP,
        UNIQUE KEY unique_gpu_offering_historical (
            provider_name(50),
            gpu_variant_name(100),
            number_of_chips,
            period(20),
            region(50),
            currency_code(10),
            display_name_gpu_type(100),
            last_updated
        )
    );
    """
    try:
        with pool.connect() as db_conn:
            db_conn.execute(sqlalchemy.text(create_table_sql))
            db_conn.commit()
        print(f"Table '{table_name}' checked/created successfully.")
    except Exception as e:
        print(f"ERROR checking/creating table '{table_name}': {e}")
        import traceback
        traceback.print_exc()

def write_all_data_to_google_sheet(all_data_rows_dicts, target_worksheet_name, client):
    if not client:
        print("Google Sheets client not available. Skipping sheet update.")
        return False
    if not all_data_rows_dicts:
        print(f"No data to update worksheet '{target_worksheet_name}'.")
        return False
    
    current_spreadsheet_id = SPREADSHEET_ID
    if not current_spreadsheet_id or "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER" in current_spreadsheet_id:
        print("CRITICAL ERROR: SPREADSHEET_ID not set or is placeholder for Google Sheet write.")
        return False
        
    print(f"Updating Sheet ID: '{current_spreadsheet_id}', Worksheet: '{target_worksheet_name}'")
    try:
        spreadsheet = client.open_by_key(current_spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(target_worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{target_worksheet_name}' not found. Creating...")
            worksheet = spreadsheet.add_worksheet(title=target_worksheet_name, rows="3000", cols=len(EXPECTED_COLUMNS))
            print(f"Worksheet created.")
        
        current_time_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rows_to_upload = [EXPECTED_COLUMNS]
        for data_dict in all_data_rows_dicts:
            row = [data_dict.get(col, "N/A") if col != "Last Updated" else current_time_utc_str for col in EXPECTED_COLUMNS]
            rows_to_upload.append(row)
        
        worksheet.clear()
        worksheet.update(range_name="A1", values=rows_to_upload, value_input_option='USER_ENTERED')
        print(f"Successfully updated Sheet '{spreadsheet.title} | {worksheet.title}' with {len(all_data_rows_dicts)} total rows.")
        return True
    except Exception as e:
        print(f"ERROR in write_all_data_to_google_sheet: {e}")
        import traceback
        traceback.print_exc()
        return False

def write_all_data_to_mysql_db(all_data_rows_dicts, pool):
    if not pool:
        print("Database pool not available. Skipping MySQL write.")
        return False
    if not all_data_rows_dicts:
        print("No data to write to MySQL.")
        return False

    table_name = "gpu_prices"
    current_time_utc_for_db = datetime.now(timezone.utc)

    rows_to_insert_for_db = []
    for data_dict_py in all_data_rows_dicts:
        db_row = {}
        for python_key, db_col_name in PYTHON_TO_DB_COLUMN_MAP.items():
            val = data_dict_py.get(python_key)

            if db_col_name == "last_updated":
                db_row[db_col_name] = current_time_utc_for_db
            elif val == "N/A" or val == "" or (isinstance(val, str) and val.strip().lower() == "contact sales"):
                if db_col_name in [
                    "memory_gb", "number_of_chips",
                    "effective_hourly_rate_value",
                    "commitment_1_month_price_value",
                    "commitment_3_month_price_value",
                    "commitment_6_month_price_value",
                    "commitment_12_month_price_value"
                ]:
                    db_row[db_col_name] = None
                elif db_col_name == "currency_code" and (val == "N/A" or val == ""):
                    db_row[db_col_name] = None
                else:
                    db_row[db_col_name] = val if val != "" else None
            elif db_col_name in ["memory_gb", "number_of_chips"] and val is not None:
                try:
                    db_row[db_col_name] = int(val)
                except (ValueError, TypeError):
                    print(f"Warning: Could not convert '{val}' to int for '{db_col_name}'. Setting to NULL.")
                    db_row[db_col_name] = None
            elif db_col_name in [
                "effective_hourly_rate_value",
                "commitment_1_month_price_value",
                "commitment_3_month_price_value",
                "commitment_6_month_price_value",
                "commitment_12_month_price_value"
            ] and val is not None:
                try:
                    str_val = str(val).replace('$', '').replace('₹', '').replace('€', '').replace(',', '').strip()
                    if not str_val or not re.match(r"^-?\d+\.?\d*$", str_val):
                        raise ValueError("String is not a valid number after stripping symbols.")
                    db_row[db_col_name] = float(str_val)
                except (ValueError, TypeError):
                    print(f"Warning: Could not convert '{val}' to float for '{db_col_name}'. Setting to NULL.")
                    db_row[db_col_name] = None
            else:
                db_row[db_col_name] = val
        rows_to_insert_for_db.append(db_row)

    if not rows_to_insert_for_db:
        print("No rows processed into DB format for MySQL insertion.")
        return False

    try:
        with pool.connect() as db_conn:
            if rows_to_insert_for_db:
                db_column_names = list(PYTHON_TO_DB_COLUMN_MAP.values())
                sql_insert_query_str = f"INSERT INTO {table_name} ({', '.join(db_column_names)}) VALUES ({', '.join([':' + name for name in db_column_names])})"
                insert_stmt = sqlalchemy.text(sql_insert_query_str)
                db_conn.execute(insert_stmt, rows_to_insert_for_db)
                db_conn.commit()
            print(f"Successfully APPENDED {len(rows_to_insert_for_db)} rows into MySQL table '{table_name}'.")
            return True
    except Exception as e:
        print(f"ERROR in write_all_data_to_mysql_db during insert: {e}")
        import traceback
        traceback.print_exc()
        if rows_to_insert_for_db:
            print(f"Sample data for failed insert (first row): {rows_to_insert_for_db[0]}")
        return False

@functions_framework.http
def process_all_gpu_prices_http(request):
    print(f"Cloud Function 'process_all_gpu_prices_http' triggered at {datetime.now(timezone.utc)}")
    
    gs_client = None
    try:
        gs_client = get_gspread_client_lazy()
    except Exception as auth_e:
        print(f"Google Sheets Auth Error: {auth_e}. Proceeding.")

    db_pool_instance = None
    try:
        db_pool_instance = get_db_connection_pool_lazy()
        if db_pool_instance:
            create_gpu_prices_table_if_not_exists(db_pool_instance)
    except Exception as db_setup_e:
        print(f"Database Connection/Setup Error: {db_setup_e}. Function might not write to DB.")

    master_data_list = []

    # --- Process RunPod ---
    try:
        print("\n--- Processing RunPod ---")
        runpod_page_content = requests.get(runpod_handler.RUNPOD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        runpod_page_content.raise_for_status()
        runpod_soup = BeautifulSoup(runpod_page_content.text, "html.parser")
        runpod_data = runpod_handler.fetch_runpod_data(runpod_soup)
        if runpod_data: master_data_list.extend(runpod_data)
        print(f"RunPod: Added {len(runpod_data) if runpod_data else 0} rows.")
    except Exception as e: print(f"ERROR processing RunPod: {e}"); import traceback; traceback.print_exc()

    # --- Process Vast.ai ---
    try:
        print("\n--- Processing Vast.ai ---")
        # Assuming vast_ai_handler uses os.environ.get("VAST_AI_API_KEY") internally
        vast_data = vast_ai_handler.fetch_vast_ai_data()
        if vast_data: master_data_list.extend(vast_data)
        print(f"Vast.ai: Added {len(vast_data) if vast_data else 0} rows.")
    except Exception as e: print(f"ERROR processing Vast.ai: {e}"); import traceback; traceback.print_exc()

    # --- Process CoreWeave ---
    try:
        print("\n--- Processing CoreWeave ---")
        coreweave_page_content = requests.get(coreweave_handler.COREWEAVE_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        coreweave_page_content.raise_for_status()
        coreweave_soup = BeautifulSoup(coreweave_page_content.text, "html.parser")
        coreweave_data = coreweave_handler.fetch_coreweave_data(coreweave_soup)
        if coreweave_data: master_data_list.extend(coreweave_data)
        print(f"CoreWeave: Added {len(coreweave_data) if coreweave_data else 0} rows.")
    except Exception as e: print(f"ERROR processing CoreWeave: {e}"); import traceback; traceback.print_exc()
    
    # --- Process Genesis Cloud ---
    try:
        print("\n--- Processing Genesis Cloud ---")
        genesis_page_content = requests.get(genesiscloud_handler.GENESISCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        genesis_page_content.raise_for_status()
        genesis_soup = BeautifulSoup(genesis_page_content.text, "html.parser")
        genesis_data = genesiscloud_handler.fetch_genesiscloud_data(genesis_soup)
        if genesis_data: master_data_list.extend(genesis_data)
        print(f"Genesis Cloud: Added {len(genesis_data) if genesis_data else 0} rows.")
    except Exception as e: print(f"ERROR processing Genesis Cloud: {e}"); import traceback; traceback.print_exc()

    # --- Process Lambda Labs ---
    try:
        print("\n--- Processing Lambda Labs ---")
        lambda_page_content = requests.get(lambda_labs_handler.LAMBDALABS_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        lambda_page_content.raise_for_status()
        lambda_soup = BeautifulSoup(lambda_page_content.text, "html.parser")
        lambda_data = lambda_labs_handler.fetch_lambda_labs_data(lambda_soup)
        if lambda_data: master_data_list.extend(lambda_data)
        print(f"Lambda Labs: Added {len(lambda_data) if lambda_data else 0} rows.")
    except Exception as e: print(f"ERROR processing Lambda Labs: {e}"); import traceback; traceback.print_exc()

    # --- Process Neevcloud ---
    try:
        print("\n--- Processing Neevcloud ---")
        response_neevcloud = requests.get(neevcloud_handler.NEEVCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_neevcloud.raise_for_status()
        neevcloud_page_content_text = response_neevcloud.text
        neevcloud_soup = BeautifulSoup(neevcloud_page_content_text, "html.parser")
        neevcloud_data = neevcloud_handler.fetch_neevcloud_data(neevcloud_soup)
        if neevcloud_data: master_data_list.extend(neevcloud_data)
        print(f"Neevcloud: Added {len(neevcloud_data) if neevcloud_data else 0} rows.")
    except Exception as e_neev: print(f"ERROR processing Neevcloud: {e_neev}"); import traceback; traceback.print_exc()

    # --- Process Sakura Internet (VRT and PHY) ---
    try:
        print("\n--- Processing Sakura Internet ---")
        response_vrt_http = requests.get(sakura_internet_handler.SAKURA_VRT_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_vrt_http.raise_for_status()
        html_vrt_content_http = response_vrt_http.text

        response_phy_http = requests.get(sakura_internet_handler.SAKURA_PHY_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_phy_http.raise_for_status()
        html_phy_content_http = response_phy_http.text
        
        soup_vrt_http = BeautifulSoup(html_vrt_content_http, "html.parser")
        soup_phy_http = BeautifulSoup(html_phy_content_http, "html.parser")
        sakura_data_http = sakura_internet_handler.fetch_sakura_internet_data(soup_vrt_http, soup_phy_http)
        if sakura_data_http: master_data_list.extend(sakura_data_http)
        print(f"Sakura Internet: Added {len(sakura_data_http) if sakura_data_http else 0} rows.")
    except Exception as e_sakura: print(f"ERROR processing Sakura Internet: {e_sakura}"); import traceback; traceback.print_exc()

    # --- Process Soroban (Highreso) ---
    try:
        print("\n--- Processing Soroban (Highreso) ---")
        soroban_page_content = requests.get(soroban_highreso_handler.SOROBAN_AISPACON_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        soroban_page_content.raise_for_status()
        soroban_soup = BeautifulSoup(soroban_page_content.text, "html.parser")
        soroban_data = soroban_highreso_handler.fetch_soroban_highreso_data(soroban_soup)
        if soroban_data: master_data_list.extend(soroban_data)
        print(f"Soroban (Highreso): Added {len(soroban_data) if soroban_data else 0} rows.")
    except Exception as e_soroban: print(f"ERROR processing Soroban (Highreso): {e_soroban}"); import traceback; traceback.print_exc()
    
    # --- Process Seeweb ---
    try:
        print("\n--- Processing Seeweb ---")
        response_csg_http = requests.get(seeweb_handler.SEEWEB_CLOUD_SERVER_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_csg_http.raise_for_status()
        html_cloud_server_gpu_http = response_csg_http.text

        response_slg_http = requests.get(seeweb_handler.SEEWEB_SERVERLESS_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_slg_http.raise_for_status()
        html_serverless_gpu_http = response_slg_http.text

        soup_cloud_server_gpu_http = BeautifulSoup(html_cloud_server_gpu_http, "html.parser")
        soup_serverless_gpu_http = BeautifulSoup(html_serverless_gpu_http, "html.parser")
        seeweb_data_http = seeweb_handler.fetch_seeweb_data(soup_cloud_server_gpu_http, soup_serverless_gpu_http)
        if seeweb_data_http: master_data_list.extend(seeweb_data_http)
        print(f"Seeweb: Added {len(seeweb_data_http) if seeweb_data_http else 0} rows.")
    except Exception as e_seeweb_main: print(f"ERROR processing Seeweb (HTTP Context): {e_seeweb_main}"); import traceback; traceback.print_exc()

    # --- Process Google Cloud Platform (GCP) ---
    try:
        print("\n--- Processing Google Cloud Platform (GCP) ---")
        gcp_pricing_url = "https://cloud.google.com/compute/all-pricing?hl=en"
        print(f"Attempting to fetch GCP HTML from: {gcp_pricing_url}")
        gcp_page_response = requests.get(gcp_pricing_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
        gcp_page_response.raise_for_status()
        gcp_html_content = gcp_page_response.text
        print(f"Fetched GCP HTML content. Parsing...")
        gcp_data = gcp_handler.fetch_gcp_gpu_data_from_html(gcp_html_content)
        if gcp_data:
            master_data_list.extend(gcp_data)
        print(f"Google Cloud Platform: Added {len(gcp_data) if gcp_data else 0} rows.")
    except Exception as e_gcp:
        print(f"ERROR processing Google Cloud Platform: {e_gcp}")
        import traceback
        traceback.print_exc()

    # --- Process Amazon Web Services (AWS) ---
    try:
        print("\n--- Processing Amazon Web Services (AWS) ---")
        aws_data = aws_handler.fetch_aws_gpu_data()
        if aws_data:
            master_data_list.extend(aws_data)
        print(f"Amazon Web Services (AWS): Added {len(aws_data) if aws_data else 0} rows.")
    except Exception as e_aws:
        print(f"ERROR processing Amazon Web Services (AWS): {e_aws}")
        import traceback
        traceback.print_exc()

    sheet_update_success = False
    db_write_success = False

    if master_data_list:
        if gs_client:
            sheet_update_success = write_all_data_to_google_sheet(master_data_list, MASTER_WORKSHEET_NAME, gs_client)
        
        if db_pool_instance:
            db_write_success = write_all_data_to_mysql_db(master_data_list, db_pool_instance)
        
        final_messages = []
        if gs_client: final_messages.append(f"GSheet update: {'succeeded' if sheet_update_success else 'failed'}")
        else: final_messages.append("GSheet update: skipped (client not available)")
        
        if db_pool_instance: final_messages.append(f"DB write: {'succeeded' if db_write_success else 'failed'}")
        else: final_messages.append("DB write: skipped (pool not available or setup failed)")

        msg = f"Processed {len(master_data_list)} total rows. {'. '.join(final_messages)}."
        print(msg)
        if (gs_client and sheet_update_success) or (db_pool_instance and db_write_success) or (not gs_client and not db_pool_instance and master_data_list):
            return msg, 200
        else:
            return msg, 500
    else:
        msg = "No GPU data processed from any provider."
        print(msg)
        return msg, 200

if __name__ == "__main__":
    print("--- Running Local Test: All Providers to Google Sheet AND MySQL DB ---")
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        print(f"Loading environment variables from {env_path}")
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value_str = line.split('=', 1)
                    key = key.strip()
                    value = value_str.strip()
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    os.environ[key] = value
        
        # Re-initialize global variables from .env
        SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", SPREADSHEET_ID)
        MASTER_WORKSHEET_NAME = os.environ.get("MASTER_WORKSHEET_NAME", MASTER_WORKSHEET_NAME)
        DB_USER = os.environ.get("DB_USER")
        DB_PASS = os.environ.get("DB_PASS")
        DB_NAME = os.environ.get("DB_NAME")
        INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
        USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get("USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"
        VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")
        AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
        AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
        AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION")
        if AWS_ACCESS_KEY_ID: os.environ['AWS_ACCESS_KEY_ID'] = AWS_ACCESS_KEY_ID
        if AWS_SECRET_ACCESS_KEY: os.environ['AWS_SECRET_ACCESS_KEY'] = AWS_SECRET_ACCESS_KEY
        if AWS_DEFAULT_REGION: os.environ['AWS_DEFAULT_REGION'] = AWS_DEFAULT_REGION


    gs_client_local = None
    try:
        gs_client_local = get_gspread_client_lazy()
    except Exception as e_gs:
        print(f"Failed to init gspread for local test: {e_gs}")

    db_pool_local = None
    if not (INSTANCE_CONNECTION_NAME and DB_USER and DB_PASS and DB_NAME):
        print("\nWARNING: One or more required database environment variables are not set. Skipping DB part.")
    else:
        try:
            print("\n--- Attempting to connect to Database for Local Test ---")
            db_pool_local = get_db_connection_pool_lazy()
            if db_pool_local:
                create_gpu_prices_table_if_not_exists(db_pool_local)
        except Exception as e_db_local:
            print(f"Failed to init DB pool or create table for local test: {e_db_local}")
            db_pool_local = None

    master_data_list_local = []

    # --- Process RunPod (Local Test) ---
    try:
        print("\n--- Processing RunPod (Local Test) ---")
        runpod_page_content_local = requests.get(runpod_handler.RUNPOD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        runpod_page_content_local.raise_for_status()
        runpod_soup_local = BeautifulSoup(runpod_page_content_local.text, "html.parser")
        runpod_data_local = runpod_handler.fetch_runpod_data(runpod_soup_local)
        if runpod_data_local: master_data_list_local.extend(runpod_data_local)
        print(f"RunPod (Local Test) processed {len(runpod_data_local) if runpod_data_local else 0} rows.")
    except Exception as e_runpod_local: print(f"Error in local RunPod test: {e_runpod_local}"); import traceback; traceback.print_exc()
    
    # --- Process Vast.ai (Local Test) ---
    try:
        print("\n--- Processing Vast.ai (Local Test) ---")
        if not VAST_AI_API_KEY:
            print("WARNING (Vast.ai Local Test): VAST_AI_API_KEY not set.")
        else:
            vast_data_local = vast_ai_handler.fetch_vast_ai_data()
            if vast_data_local: master_data_list_local.extend(vast_data_local)
            print(f"Vast.ai (Local Test) processed {len(vast_data_local) if vast_data_local else 0} rows.")
    except Exception as e_vast_local: print(f"Error in local Vast.ai test: {e_vast_local}"); import traceback; traceback.print_exc()

    # --- Process CoreWeave (Local Test) ---
    try:
        print("\n--- Processing CoreWeave (Local Test) ---")
        coreweave_page_content_local = requests.get(coreweave_handler.COREWEAVE_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        coreweave_page_content_local.raise_for_status()
        coreweave_soup_local = BeautifulSoup(coreweave_page_content_local.text, "html.parser")
        coreweave_data_local = coreweave_handler.fetch_coreweave_data(coreweave_soup_local)
        if coreweave_data_local: master_data_list_local.extend(coreweave_data_local)
        print(f"CoreWeave (Local Test) processed {len(coreweave_data_local) if coreweave_data_local else 0} rows.")
    except Exception as e_coreweave_local: print(f"Error in local CoreWeave test: {e_coreweave_local}"); import traceback; traceback.print_exc()
    
    # --- Process Genesis Cloud (Local Test) ---
    try:
        print("\n--- Processing Genesis Cloud (Local Test) ---")
        genesis_page_content_local = requests.get(genesiscloud_handler.GENESISCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        genesis_page_content_local.raise_for_status()
        genesis_soup_local = BeautifulSoup(genesis_page_content_local.text, "html.parser")
        genesis_data_local = genesiscloud_handler.fetch_genesiscloud_data(genesis_soup_local)
        if genesis_data_local: master_data_list_local.extend(genesis_data_local)
        print(f"Genesis Cloud (Local Test) processed {len(genesis_data_local) if genesis_data_local else 0} rows.")
    except Exception as e_genesis_local: print(f"Error in local Genesis Cloud test: {e_genesis_local}"); import traceback; traceback.print_exc()

    # --- Process Lambda Labs (Local Test) ---
    try:
        print("\n--- Processing Lambda Labs (Local Test) ---")
        lambda_page_content_local = requests.get(lambda_labs_handler.LAMBDALABS_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        lambda_page_content_local.raise_for_status()
        lambda_soup_local = BeautifulSoup(lambda_page_content_local.text, "html.parser")
        lambda_data_local = lambda_labs_handler.fetch_lambda_labs_data(lambda_soup_local)
        if lambda_data_local: master_data_list_local.extend(lambda_data_local)
        print(f"Lambda Labs (Local Test) processed {len(lambda_data_local) if lambda_data_local else 0} rows.")
    except Exception as e_lambda_local: print(f"Error in local Lambda Labs test: {e_lambda_local}"); import traceback; traceback.print_exc()

    # --- Process Neevcloud (Local Test) ---
    try:
        print("\n--- Processing Neevcloud (Local Test) ---")
        response_neevcloud_local = requests.get(neevcloud_handler.NEEVCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_neevcloud_local.raise_for_status()
        neevcloud_soup_local = BeautifulSoup(response_neevcloud_local.text, "html.parser")
        neevcloud_data_local = neevcloud_handler.fetch_neevcloud_data(neevcloud_soup_local)
        if neevcloud_data_local: master_data_list_local.extend(neevcloud_data_local)
        print(f"Neevcloud (Local Test) processed {len(neevcloud_data_local) if neevcloud_data_local else 0} rows.")
    except Exception as e_neevcloud_local: print(f"Error in local Neevcloud test: {e_neevcloud_local}"); import traceback; traceback.print_exc()

    # --- Process Sakura Internet (Local Test) ---
    try:
        print("\n--- Processing Sakura Internet (Local Test) ---")
        response_vrt_local = requests.get(sakura_internet_handler.SAKURA_VRT_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_vrt_local.raise_for_status()
        soup_vrt_local = BeautifulSoup(response_vrt_local.text, "html.parser")
        
        response_phy_local = requests.get(sakura_internet_handler.SAKURA_PHY_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_phy_local.raise_for_status()
        soup_phy_local = BeautifulSoup(response_phy_local.text, "html.parser")
        
        sakura_data_local = sakura_internet_handler.fetch_sakura_internet_data(soup_vrt_local, soup_phy_local)
        if sakura_data_local: master_data_list_local.extend(sakura_data_local)
        print(f"Sakura Internet (Local Test) processed {len(sakura_data_local) if sakura_data_local else 0} rows.")
    except Exception as e_sakura_local: print(f"Error in local Sakura Internet test: {e_sakura_local}"); import traceback; traceback.print_exc()

    # --- Process Soroban (Highreso) (Local Test) ---
    try:
        print("\n--- Processing Soroban (Highreso) (Local Test) ---")
        soroban_page_content_local = requests.get(soroban_highreso_handler.SOROBAN_AISPACON_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        soroban_page_content_local.raise_for_status()
        soroban_soup_local = BeautifulSoup(soroban_page_content_local.text, "html.parser")
        soroban_data_local = soroban_highreso_handler.fetch_soroban_highreso_data(soroban_soup_local)
        if soroban_data_local: master_data_list_local.extend(soroban_data_local)
        print(f"Soroban (Highreso) (Local Test) processed {len(soroban_data_local) if soroban_data_local else 0} rows.")
    except Exception as e_soroban_local: print(f"Error in local Soroban (Highreso) test: {e_soroban_local}"); import traceback; traceback.print_exc()
    
    # --- Process Seeweb (Local Test) ---
    try:
        print("\n--- Processing Seeweb (Local Test) ---")
        response_csg_local = requests.get(seeweb_handler.SEEWEB_CLOUD_SERVER_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_csg_local.raise_for_status()
        soup_csg_local = BeautifulSoup(response_csg_local.text, "html.parser")

        response_slg_local = requests.get(seeweb_handler.SEEWEB_SERVERLESS_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        response_slg_local.raise_for_status()
        soup_slg_local = BeautifulSoup(response_slg_local.text, "html.parser")
        
        seeweb_data_local = seeweb_handler.fetch_seeweb_data(soup_csg_local, soup_slg_local)
        if seeweb_data_local: master_data_list_local.extend(seeweb_data_local)
        print(f"Seeweb (Local Test) processed {len(seeweb_data_local) if seeweb_data_local else 0} rows.")
    except Exception as e_seeweb_main_local: print(f"Error in local Seeweb test: {e_seeweb_main_local}"); import traceback; traceback.print_exc()

    # --- Process Google Cloud Platform (GCP) (Local Test from HTML file) ---
    try:
        print("\n--- Processing Google Cloud Platform (GCP) (Local Test from HTML file) ---")
        gcp_html_file_path = "Pricing _ Compute Engine_ Virtual Machines (VMs) _ Google Cloud _ Google Cloud.html"
        if os.path.exists(gcp_html_file_path):
            with open(gcp_html_file_path, 'r', encoding='utf-8') as f_gcp_local:
                gcp_html_content_local = f_gcp_local.read()
            print(f"Loaded local GCP HTML content from: {gcp_html_file_path}")
            gcp_data_local = gcp_handler.fetch_gcp_gpu_data_from_html(gcp_html_content_local)
            if gcp_data_local:
                master_data_list_local.extend(gcp_data_local)
            print(f"Google Cloud Platform (Local Test from HTML) processed {len(gcp_data_local) if gcp_data_local else 0} rows.")
        else:
            print(f"WARNING: Local GCP HTML file not found at '{gcp_html_file_path}'. Skipping GCP processing in local test.")
    except Exception as e_gcp_local:
        print(f"Error in local GCP test (from HTML): {e_gcp_local}")
        import traceback
        traceback.print_exc()

    # --- Process Amazon Web Services (AWS) (Local Test) ---
    try:
        print("\n--- Processing Amazon Web Services (AWS) (Local Test) ---")
        if not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_DEFAULT_REGION):
            print("WARNING (AWS Local Test): AWS credentials not fully set. Skipping.")
        else:
            aws_data_local = aws_handler.fetch_aws_gpu_data()
            if aws_data_local: master_data_list_local.extend(aws_data_local)
            print(f"Amazon Web Services (AWS) (Local Test) processed {len(aws_data_local) if aws_data_local else 0} rows.")
    except Exception as e_aws_local: print(f"Error in local AWS test: {e_aws_local}"); import traceback; traceback.print_exc()

    # --- Final Data Writing for Local Test ---
    if master_data_list_local:
        print(f"\n--- Total rows from all providers for local test: {len(master_data_list_local)} ---")

        if gs_client_local:
            target_ws_local = MASTER_WORKSHEET_NAME
            print(f"\n--- Writing to Google Sheet (Local Test): {target_ws_local}_TestLocal ---")
            write_all_data_to_google_sheet(master_data_list_local, target_ws_local + "_TestLocal", gs_client_local)
        else:
            print("\nLocal test: Skipping GSheet write (client not available or SPREADSHEET_ID issue).")

        if db_pool_local:
            print("\n--- Writing to MySQL DB (Local Test) ---")
            write_all_data_to_mysql_db(master_data_list_local, db_pool_local)
        else:
            print("\nLocal test: Skipping MySQL write (DB pool not available).")
    else:
        print("\nLocal test: No data processed from any provider.")

    print("--- Local Test Finished ---")