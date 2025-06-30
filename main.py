# import functions_framework
# import requests
# from bs4 import BeautifulSoup
# import gspread
# from google.auth import default as adc_default
# from google.oauth2.service_account import Credentials # For local GSpread fallback
# from datetime import datetime, timezone
# import os
# import re
# import logging

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
# from providers import scaleway_handler
# from providers import hyperstack_handler
# from providers import koyeb_handler

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

# # Database Configuration
# DB_USER = os.environ.get("DB_USER")
# DB_PASS = os.environ.get("DB_PASS")
# DB_NAME = os.environ.get("DB_NAME")
# INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
# USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get("USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"

# # Provider API Keys
# VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")

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
#             print(f"Failed to use ADC for gspread: {e_adc}. Falling back to service account file.")
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

#     required_vars = {"INSTANCE_CONNECTION_NAME": INSTANCE_CONNECTION_NAME, "DB_USER": DB_USER, "DB_PASS": DB_PASS, "DB_NAME": DB_NAME}
#     missing_vars = [key for key, value in required_vars.items() if not value]
#     if missing_vars:
#         print(f"CRITICAL ERROR: Missing database environment variables: {', '.join(missing_vars)}")
#         raise ValueError(f"Missing DB environment variables: {', '.join(missing_vars)}")

#     print("Initializing database connection pool...")
#     try:
#         ip_type_to_use = IPTypes.PUBLIC if USE_PUBLIC_IP_FOR_CONNECTOR else IPTypes.PRIVATE
#         connector = Connector(ip_type=ip_type_to_use)

#         def getconn() -> pymysql.connections.Connection:
#             conn: pymysql.connections.Connection = connector.connect(
#                 INSTANCE_CONNECTION_NAME,
#                 "pymysql",
#                 user=DB_USER,
#                 password=DB_PASS,
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
#         print(f"Table '{table_name}' checked/created successfully.")
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
#                 "effective_hourly_rate_value",
#                 "commitment_1_month_price_value",
#                 "commitment_3_month_price_value",
#                 "commitment_6_month_price_value",
#                 "commitment_12_month_price_value"
#             ] and val is not None:
#                 try:
#                     str_val = str(val).replace('$', '').replace('₹', '').replace('€', '').replace(',', '').strip()
#                     if not str_val or not re.match(r"^-?\d+\.?\d*$", str_val):
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
#             print(f"Successfully APPENDED {len(rows_to_insert_for_db)} rows into MySQL table '{table_name}'.")
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

#     gs_client = None
#     try:
#         gs_client = get_gspread_client_lazy()
#     except Exception as auth_e:
#         print(f"Google Sheets Auth Error: {auth_e}. Proceeding.")

#     db_pool_instance = None
#     try:
#         db_pool_instance = get_db_connection_pool_lazy()
#         if db_pool_instance:
#             create_gpu_prices_table_if_not_exists(db_pool_instance)
#     except Exception as db_setup_e:
#         print(f"Database Connection/Setup Error: {db_setup_e}. Function might not write to DB.")

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
#     try:
#         print("\n--- Processing Vast.ai ---")
#         vast_data = vast_ai_handler.fetch_vast_ai_data()
#         if vast_data: master_data_list.extend(vast_data)
#         print(f"Vast.ai: Added {len(vast_data) if vast_data else 0} rows.")
#     except Exception as e: print(f"ERROR processing Vast.ai: {e}"); import traceback; traceback.print_exc()

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
#         response_neevcloud = requests.get(neevcloud_handler.NEEVCLOUD_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_neevcloud.raise_for_status()
#         neevcloud_soup = BeautifulSoup(response_neevcloud.text, "html.parser")
#         neevcloud_data = neevcloud_handler.fetch_neevcloud_data(neevcloud_soup)
#         if neevcloud_data: master_data_list.extend(neevcloud_data)
#         print(f"Neevcloud: Added {len(neevcloud_data) if neevcloud_data else 0} rows.")
#     except Exception as e_neev: print(f"ERROR processing Neevcloud: {e_neev}"); import traceback; traceback.print_exc()

#     # --- Process Sakura Internet ---
#     try:
#         print("\n--- Processing Sakura Internet ---")
#         response_vrt_http = requests.get(sakura_internet_handler.SAKURA_VRT_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_vrt_http.raise_for_status()
#         soup_vrt_http = BeautifulSoup(response_vrt_http.text, "html.parser")

#         response_phy_http = requests.get(sakura_internet_handler.SAKURA_PHY_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_phy_http.raise_for_status()
#         soup_phy_http = BeautifulSoup(response_phy_http.text, "html.parser")

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
#         response_csg_http = requests.get(seeweb_handler.SEEWEB_CLOUD_SERVER_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_csg_http.raise_for_status()
#         soup_csg_http = BeautifulSoup(response_csg_http.text, "html.parser")

#         response_slg_http = requests.get(seeweb_handler.SEEWEB_SERVERLESS_GPU_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_slg_http.raise_for_status()
#         soup_slg_http = BeautifulSoup(response_slg_http.text, "html.parser")

#         seeweb_data_http = seeweb_handler.fetch_seeweb_data(soup_csg_http, soup_slg_http)
#         if seeweb_data_http: master_data_list.extend(seeweb_data_http)
#         print(f"Seeweb: Added {len(seeweb_data_http) if seeweb_data_http else 0} rows.")
#     except Exception as e_seeweb_main: print(f"ERROR processing Seeweb (HTTP Context): {e_seeweb_main}"); import traceback; traceback.print_exc()

#     # --- Process Scaleway ---
#     try:
#         print("\n--- Processing Scaleway ---")
#         response_h100_http = requests.get(scaleway_handler.SCALEWAY_H100_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_h100_http.raise_for_status()
#         soup_h100_http = BeautifulSoup(response_h100_http.text, "html.parser")

#         response_l40s_http = requests.get(scaleway_handler.SCALEWAY_L40S_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_l40s_http.raise_for_status()
#         soup_l40s_http = BeautifulSoup(response_l40s_http.text, "html.parser")

#         scaleway_data = scaleway_handler.fetch_scaleway_data(soup_h100_http, soup_l40s_http)
#         if scaleway_data: master_data_list.extend(scaleway_data)
#         print(f"Scaleway: Added {len(scaleway_data) if scaleway_data else 0} rows.")
#     except Exception as e_scaleway:
#         print(f"ERROR processing Scaleway: {e_scaleway}")
#         import traceback
#         traceback.print_exc()

#     # --- Process Hyperstack ---
#     try:
#         print("\n--- Processing Hyperstack ---")
#         response_http = requests.get(hyperstack_handler.HYPERSTACK_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_http.raise_for_status()
#         soup_http = BeautifulSoup(response_http.text, "html.parser")
#         hyperstack_data = hyperstack_handler.fetch_hyperstack_data(soup_http)
#         if hyperstack_data: master_data_list.extend(hyperstack_data)
#         print(f"Hyperstack: Added {len(hyperstack_data) if hyperstack_data else 0} rows.")
#     except Exception as e_hyperstack:
#         print(f"ERROR processing Hyperstack: {e_hyperstack}")
#         import traceback
#         traceback.print_exc()

#     # --- Process Koyeb ---
#     try:
#         print("\n--- Processing Koyeb ---")
#         response_http = requests.get(koyeb_handler.KOYEB_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_http.raise_for_status()
#         soup_http = BeautifulSoup(response_http.text, "html.parser")
#         koyeb_data = koyeb_handler.fetch_koyeb_data(soup_http)
#         if koyeb_data: master_data_list.extend(koyeb_data)
#         print(f"Koyeb: Added {len(koyeb_data) if koyeb_data else 0} rows.")
#     except Exception as e_koyeb:
#         print(f"ERROR processing Koyeb: {e_koyeb}")
#         import traceback
#         traceback.print_exc()

#     sheet_update_success = False
#     db_write_success = False

#     if master_data_list:
#         if gs_client:
#             sheet_update_success = write_all_data_to_google_sheet(master_data_list, MASTER_WORKSHEET_NAME, gs_client)

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

#         SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", SPREADSHEET_ID)
#         MASTER_WORKSHEET_NAME = os.environ.get("MASTER_WORKSHEET_NAME", MASTER_WORKSHEET_NAME)
#         DB_USER = os.environ.get("DB_USER")
#         DB_PASS = os.environ.get("DB_PASS")
#         DB_NAME = os.environ.get("DB_NAME")
#         INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
#         USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get("USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"
#         VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")

#     gs_client_local = None
#     try:
#         gs_client_local = get_gspread_client_lazy()
#     except Exception as e_gs:
#         print(f"Failed to init gspread for local test: {e_gs}")

#     db_pool_local = None
#     if not (INSTANCE_CONNECTION_NAME and DB_USER and DB_PASS and DB_NAME):
#         print("\nWARNING: One or more required database environment variables are not set. Skipping DB part.")
#     else:
#         try:
#             print("\n--- Attempting to connect to Database for Local Test ---")
#             db_pool_local = get_db_connection_pool_lazy()
#             if db_pool_local:
#                 create_gpu_prices_table_if_not_exists(db_pool_local)
#         except Exception as e_db_local:
#             print(f"Failed to init DB pool or create table for local test: {e_db_local}")
#             db_pool_local = None

#     master_data_list_local = []

#     # --- Local Test Blocks for each provider ---

#     # (RunPod, Vast.ai, CoreWeave, Genesis, Lambda, Neev, Sakura, Soroban, Seeweb, Scaleway, Hyperstack...)
#     # This section contains all the individual provider test blocks as shown in previous responses.
#     # To keep this response readable, I'm showing the pattern for the last one.

#     # ... (all previous 11 provider test blocks) ...

#     # --- Process Koyeb (Local Test) ---
#     try:
#         print("\n--- Processing Koyeb (Local Test) ---")
#         response_local = requests.get(koyeb_handler.KOYEB_PRICING_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
#         response_local.raise_for_status()
#         soup_local = BeautifulSoup(response_local.text, "html.parser")
#         koyeb_data_local = koyeb_handler.fetch_koyeb_data(soup_local)
#         if koyeb_data_local: master_data_list_local.extend(koyeb_data_local)
#         print(f"Koyeb (Local Test) processed {len(koyeb_data_local) if koyeb_data_local else 0} rows.")
#     except Exception as e_koyeb_local:
#         print(f"Error in local Koyeb test: {e_koyeb_local}")
#         import traceback
#         traceback.print_exc()

#     # --- Final Data Writing for Local Test ---
#     if master_data_list_local:
#         print(f"\n--- Total rows from all providers for local test: {len(master_data_list_local)} ---")

#         if gs_client_local:
#             target_ws_local = MASTER_WORKSHEET_NAME
#             print(f"\n--- Writing to Google Sheet (Local Test): {target_ws_local}_TestLocal ---")
#             write_all_data_to_google_sheet(master_data_list_local, target_ws_local + "_TestLocal", gs_client_local)
#         else:
#             print("\nLocal test: Skipping GSheet write (client not available or SPREADSHEET_ID issue).")

#         if db_pool_local:
#             print("\n--- Writing to MySQL DB (Local Test) ---")
#             write_all_data_to_mysql_db(master_data_list_local, db_pool_local)
#         else:
#             print("\nLocal test: Skipping MySQL write (DB pool not available).")
#     else:
#         print("\nLocal test: No data processed from any provider.")

#     print("--- Local Test Finished ---")


# main.py

import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes
import pymysql
import functions_framework
import requests
from bs4 import BeautifulSoup
import gspread
from google.auth import default as adc_default
from google.oauth2.service_account import Credentials  # For local GSpread fallback
from datetime import datetime, timezone
import os
import re
import logging

# --- Step 1: Import all provider handlers ---
from providers import runpod_handler
from providers import vast_ai_handler
from providers import coreweave_handler
from providers import genesiscloud_handler
from providers import lambda_labs_handler
from providers import neevcloud_handler
from providers import sakura_internet_handler
from providers import soroban_highreso_handler
from providers import seeweb_handler
from providers import scaleway_handler
from providers import hyperstack_handler
from providers import koyeb_handler

# Import the Selenium script runner for Vast.ai
from get_full_list import fetch_and_save_final_html


# --- Initialize Configuration ---
print("Initializing configuration from environment variables...")

# Google Sheets Configuration
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID", "YOUR_ACTUAL_SPREADSHEET_ID_PLACEHOLDER")
MASTER_WORKSHEET_NAME = os.environ.get(
    "MASTER_WORKSHEET_NAME", "All_GPU_Prices")
SERVICE_ACCOUNT_FILE = "service_account_creds.json"  # For local fallback only
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
USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get(
    "USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"

# Provider API Keys
VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")

# --- Database Libraries ---

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
            print(
                "Successfully initialized gspread client with Application Default Credentials.")
        except Exception as e_adc:
            print(
                f"Failed to use ADC for gspread: {e_adc}. Falling back to service account file.")
            gac_file_path = os.environ.get(
                "GOOGLE_APPLICATION_CREDENTIALS", SERVICE_ACCOUNT_FILE)
            if not os.path.exists(gac_file_path):
                print(
                    f"ERROR: Service account file '{gac_file_path}' not found. Cannot initialize gspread via file.")
                return None
            try:
                creds_from_file = Credentials.from_service_account_file(
                    gac_file_path, scopes=SCOPES_SHEETS)
                gspread_client_instance = gspread.authorize(creds_from_file)
                print(
                    f"Successfully initialized gspread client with service account file: {gac_file_path}")
            except Exception as e_file_auth:
                print(
                    f"ERROR initializing gspread client with local file '{gac_file_path}': {e_file_auth}")
                return None
    return gspread_client_instance


def get_db_connection_pool_lazy():
    global db_pool
    if db_pool:
        return db_pool

    required_vars = {"INSTANCE_CONNECTION_NAME": INSTANCE_CONNECTION_NAME,
                     "DB_USER": DB_USER, "DB_PASS": DB_PASS, "DB_NAME": DB_NAME}
    missing_vars = [key for key, value in required_vars.items() if not value]
    if missing_vars:
        print(
            f"CRITICAL ERROR: Missing database environment variables: {', '.join(missing_vars)}")
        raise ValueError(
            f"Missing DB environment variables: {', '.join(missing_vars)}")

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
    # This SQL statement includes the corrected UNIQUE KEY to prevent integrity errors.
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
            gpu_id(100),
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

    print(
        f"Updating Sheet ID: '{current_spreadsheet_id}', Worksheet: '{target_worksheet_name}'")
    try:
        spreadsheet = client.open_by_key(current_spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(target_worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            print(
                f"Worksheet '{target_worksheet_name}' not found. Creating...")
            worksheet = spreadsheet.add_worksheet(
                title=target_worksheet_name, rows="3000", cols=len(EXPECTED_COLUMNS))
            print(f"Worksheet created.")

        current_time_utc_str = datetime.now(
            timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rows_to_upload = [EXPECTED_COLUMNS]
        for data_dict in all_data_rows_dicts:
            row = [data_dict.get(
                col, "N/A") if col != "Last Updated" else current_time_utc_str for col in EXPECTED_COLUMNS]
            rows_to_upload.append(row)

        worksheet.clear()
        worksheet.update(range_name="A1", values=rows_to_upload,
                         value_input_option='USER_ENTERED')
        print(
            f"Successfully updated Sheet '{spreadsheet.title} | {worksheet.title}' with {len(all_data_rows_dicts)} total rows.")
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
                    print(
                        f"Warning: Could not convert '{val}' to int for '{db_col_name}'. Setting to NULL.")
                    db_row[db_col_name] = None
            elif db_col_name in [
                "effective_hourly_rate_value",
                "commitment_1_month_price_value",
                "commitment_3_month_price_value",
                "commitment_6_month_price_value",
                "commitment_12_month_price_value"
            ] and val is not None:
                try:
                    str_val = str(val).replace('$', '').replace(
                        '₹', '').replace('€', '').replace(',', '').strip()
                    if not str_val or not re.match(r"^-?\d+\.?\d*$", str_val):
                        raise ValueError(
                            "String is not a valid number after stripping symbols.")
                    db_row[db_col_name] = float(str_val)
                except (ValueError, TypeError):
                    print(
                        f"Warning: Could not convert '{val}' to float for '{db_col_name}'. Setting to NULL.")
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
            print(
                f"Successfully APPENDED {len(rows_to_insert_for_db)} rows into MySQL table '{table_name}'.")
            return True
    except Exception as e:
        print(f"ERROR in write_all_data_to_mysql_db during insert: {e}")
        import traceback
        traceback.print_exc()
        if rows_to_insert_for_db:
            print(
                f"Sample data for failed insert (first row): {rows_to_insert_for_db[0]}")
        return False


@functions_framework.http
def process_all_gpu_prices_http(request):
    print(
        f"Cloud Function 'process_all_gpu_prices_http' triggered at {datetime.now(timezone.utc)}")

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
        print(
            f"Database Connection/Setup Error: {db_setup_e}. Function might not write to DB.")

    master_data_list = []

    # --- Process RunPod ---
    try:
        print("\n--- Processing RunPod ---")
        runpod_page_content = requests.get(runpod_handler.RUNPOD_PRICING_URL, headers={
                                           "User-Agent": "Mozilla/5.0"}, timeout=60)
        runpod_page_content.raise_for_status()
        runpod_soup = BeautifulSoup(runpod_page_content.text, "html.parser")
        runpod_data = runpod_handler.fetch_runpod_data(runpod_soup)
        if runpod_data:
            master_data_list.extend(runpod_data)
        print(f"RunPod: Added {len(runpod_data) if runpod_data else 0} rows.")
    except Exception as e:
        print(f"ERROR processing RunPod: {e}")
        import traceback
        traceback.print_exc()

    # --- Process Vast.ai ---
    try:
        print("\n--- Processing Vast.ai ---")
        vast_html_output_file = "vast_rendered.html"
        print("Step 1: Running Selenium to generate fully rendered HTML for Vast.ai...")
        fetch_and_save_final_html(
            vast_ai_handler.VAST_AI_PRICING_URL, vast_html_output_file)

        print(f"Step 2: Parsing the generated file: '{vast_html_output_file}'")
        if os.path.exists(vast_html_output_file):
            with open(vast_html_output_file, 'r', encoding='utf-8') as f:
                vast_soup = BeautifulSoup(f.read(), "html.parser")

            vast_data = vast_ai_handler.fetch_vast_ai_data(vast_soup)
            if vast_data:
                master_data_list.extend(vast_data)
            print(f"Vast.ai: Added {len(vast_data) if vast_data else 0} rows.")
        else:
            print(
                f"ERROR: The file '{vast_html_output_file}' was not created by the Selenium script.")

    except Exception as e:
        print(f"ERROR processing Vast.ai: {e}")
        import traceback
        traceback.print_exc()

    # --- Process CoreWeave ---
    try:
        print("\n--- Processing CoreWeave ---")
        coreweave_page_content = requests.get(coreweave_handler.COREWEAVE_PRICING_URL, headers={
                                              "User-Agent": "Mozilla/5.0"}, timeout=60)
        coreweave_page_content.raise_for_status()
        coreweave_soup = BeautifulSoup(
            coreweave_page_content.text, "html.parser")
        coreweave_data = coreweave_handler.fetch_coreweave_data(coreweave_soup)
        if coreweave_data:
            master_data_list.extend(coreweave_data)
        print(
            f"CoreWeave: Added {len(coreweave_data) if coreweave_data else 0} rows.")
    except Exception as e:
        print(f"ERROR processing CoreWeave: {e}")
        import traceback
        traceback.print_exc()

    # --- Process Genesis Cloud ---
    try:
        print("\n--- Processing Genesis Cloud ---")
        genesis_page_content = requests.get(genesiscloud_handler.GENESISCLOUD_PRICING_URL, headers={
                                            "User-Agent": "Mozilla/5.0"}, timeout=60)
        genesis_page_content.raise_for_status()
        genesis_soup = BeautifulSoup(genesis_page_content.text, "html.parser")
        genesis_data = genesiscloud_handler.fetch_genesiscloud_data(
            genesis_soup)
        if genesis_data:
            master_data_list.extend(genesis_data)
        print(
            f"Genesis Cloud: Added {len(genesis_data) if genesis_data else 0} rows.")
    except Exception as e:
        print(f"ERROR processing Genesis Cloud: {e}")
        import traceback
        traceback.print_exc()

    # --- Process Lambda Labs ---
    try:
        print("\n--- Processing Lambda Labs ---")
        lambda_page_content = requests.get(lambda_labs_handler.LAMBDALABS_PRICING_URL, headers={
                                           "User-Agent": "Mozilla/5.0"}, timeout=60)
        lambda_page_content.raise_for_status()
        lambda_soup = BeautifulSoup(lambda_page_content.text, "html.parser")
        lambda_data = lambda_labs_handler.fetch_lambda_labs_data(lambda_soup)
        if lambda_data:
            master_data_list.extend(lambda_data)
        print(
            f"Lambda Labs: Added {len(lambda_data) if lambda_data else 0} rows.")
    except Exception as e:
        print(f"ERROR processing Lambda Labs: {e}")
        import traceback
        traceback.print_exc()

    # --- Process Neevcloud ---
    try:
        print("\n--- Processing Neevcloud ---")
        response_neevcloud = requests.get(neevcloud_handler.NEEVCLOUD_PRICING_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_neevcloud.raise_for_status()
        neevcloud_soup = BeautifulSoup(response_neevcloud.text, "html.parser")
        neevcloud_data = neevcloud_handler.fetch_neevcloud_data(neevcloud_soup)
        if neevcloud_data:
            master_data_list.extend(neevcloud_data)
        print(
            f"Neevcloud: Added {len(neevcloud_data) if neevcloud_data else 0} rows.")
    except Exception as e_neev:
        print(f"ERROR processing Neevcloud: {e_neev}")
        import traceback
        traceback.print_exc()

    # --- Process Sakura Internet ---
    try:
        print("\n--- Processing Sakura Internet ---")
        response_vrt_http = requests.get(sakura_internet_handler.SAKURA_VRT_PRICING_URL, headers={
                                         "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_vrt_http.raise_for_status()
        soup_vrt_http = BeautifulSoup(response_vrt_http.text, "html.parser")

        response_phy_http = requests.get(sakura_internet_handler.SAKURA_PHY_PRICING_URL, headers={
                                         "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_phy_http.raise_for_status()
        soup_phy_http = BeautifulSoup(response_phy_http.text, "html.parser")

        sakura_data_http = sakura_internet_handler.fetch_sakura_internet_data(
            soup_vrt_http, soup_phy_http)
        if sakura_data_http:
            master_data_list.extend(sakura_data_http)
        print(
            f"Sakura Internet: Added {len(sakura_data_http) if sakura_data_http else 0} rows.")
    except Exception as e_sakura:
        print(f"ERROR processing Sakura Internet: {e_sakura}")
        import traceback
        traceback.print_exc()

    # --- Process Soroban (Highreso) ---
    try:
        print("\n--- Processing Soroban (Highreso) ---")
        soroban_page_content = requests.get(soroban_highreso_handler.SOROBAN_AISPACON_URL, headers={
                                            "User-Agent": "Mozilla/5.0"}, timeout=60)
        soroban_page_content.raise_for_status()
        soroban_soup = BeautifulSoup(soroban_page_content.text, "html.parser")
        soroban_data = soroban_highreso_handler.fetch_soroban_highreso_data(
            soroban_soup)
        if soroban_data:
            master_data_list.extend(soroban_data)
        print(
            f"Soroban (Highreso): Added {len(soroban_data) if soroban_data else 0} rows.")
    except Exception as e_soroban:
        print(f"ERROR processing Soroban (Highreso): {e_soroban}")
        import traceback
        traceback.print_exc()

    # --- Process Seeweb ---
    try:
        print("\n--- Processing Seeweb ---")
        response_csg_http = requests.get(seeweb_handler.SEEWEB_CLOUD_SERVER_GPU_URL, headers={
                                         "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_csg_http.raise_for_status()
        soup_csg_http = BeautifulSoup(response_csg_http.text, "html.parser")

        response_slg_http = requests.get(seeweb_handler.SEEWEB_SERVERLESS_GPU_URL, headers={
                                         "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_slg_http.raise_for_status()
        soup_slg_http = BeautifulSoup(response_slg_http.text, "html.parser")

        seeweb_data_http = seeweb_handler.fetch_seeweb_data(
            soup_csg_http, soup_slg_http)
        if seeweb_data_http:
            master_data_list.extend(seeweb_data_http)
        print(
            f"Seeweb: Added {len(seeweb_data_http) if seeweb_data_http else 0} rows.")
    except Exception as e_seeweb_main:
        print(f"ERROR processing Seeweb (HTTP Context): {e_seeweb_main}")
        import traceback
        traceback.print_exc()

    # --- Process Scaleway ---
    try:
        print("\n--- Processing Scaleway ---")
        response_h100_http = requests.get(scaleway_handler.SCALEWAY_H100_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_h100_http.raise_for_status()
        soup_h100_http = BeautifulSoup(response_h100_http.text, "html.parser")

        response_l40s_http = requests.get(scaleway_handler.SCALEWAY_L40S_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_l40s_http.raise_for_status()
        soup_l40s_http = BeautifulSoup(response_l40s_http.text, "html.parser")

        scaleway_data = scaleway_handler.fetch_scaleway_data(
            soup_h100_http, soup_l40s_http)
        if scaleway_data:
            master_data_list.extend(scaleway_data)
        print(
            f"Scaleway: Added {len(scaleway_data) if scaleway_data else 0} rows.")
    except Exception as e_scaleway:
        print(f"ERROR processing Scaleway: {e_scaleway}")
        import traceback
        traceback.print_exc()

    # --- Process Hyperstack ---
    try:
        print("\n--- Processing Hyperstack ---")
        response_http = requests.get(hyperstack_handler.HYPERSTACK_PRICING_URL, headers={
                                     "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_http.raise_for_status()
        soup_http = BeautifulSoup(response_http.text, "html.parser")
        hyperstack_data = hyperstack_handler.fetch_hyperstack_data(soup_http)
        if hyperstack_data:
            master_data_list.extend(hyperstack_data)
        print(
            f"Hyperstack: Added {len(hyperstack_data) if hyperstack_data else 0} rows.")
    except Exception as e_hyperstack:
        print(f"ERROR processing Hyperstack: {e_hyperstack}")
        import traceback
        traceback.print_exc()

    # --- Process Koyeb ---
    try:
        print("\n--- Processing Koyeb ---")
        response_http = requests.get(koyeb_handler.KOYEB_PRICING_URL, headers={
                                     "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_http.raise_for_status()
        soup_http = BeautifulSoup(response_http.text, "html.parser")
        koyeb_data = koyeb_handler.fetch_koyeb_data(soup_http)
        if koyeb_data:
            master_data_list.extend(koyeb_data)
        print(f"Koyeb: Added {len(koyeb_data) if koyeb_data else 0} rows.")
    except Exception as e_koyeb:
        print(f"ERROR processing Koyeb: {e_koyeb}")
        import traceback
        traceback.print_exc()

    sheet_update_success = False
    db_write_success = False

    if master_data_list:
        if gs_client:
            sheet_update_success = write_all_data_to_google_sheet(
                master_data_list, MASTER_WORKSHEET_NAME, gs_client)

        if db_pool_instance:
            db_write_success = write_all_data_to_mysql_db(
                master_data_list, db_pool_instance)

        final_messages = []
        if gs_client:
            final_messages.append(
                f"GSheet update: {'succeeded' if sheet_update_success else 'failed'}")
        else:
            final_messages.append(
                "GSheet update: skipped (client not available)")

        if db_pool_instance:
            final_messages.append(
                f"DB write: {'succeeded' if db_write_success else 'failed'}")
        else:
            final_messages.append(
                "DB write: skipped (pool not available or setup failed)")

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

        SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", SPREADSHEET_ID)
        MASTER_WORKSHEET_NAME = os.environ.get(
            "MASTER_WORKSHEET_NAME", MASTER_WORKSHEET_NAME)
        DB_USER = os.environ.get("DB_USER")
        DB_PASS = os.environ.get("DB_PASS")
        DB_NAME = os.environ.get("DB_NAME")
        INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
        USE_PUBLIC_IP_FOR_CONNECTOR = os.environ.get(
            "USE_PUBLIC_IP_FOR_CONNECTOR", "false").lower() == "true"
        VAST_AI_API_KEY = os.environ.get("VAST_AI_API_KEY")

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
            print(
                f"Failed to init DB pool or create table for local test: {e_db_local}")
            db_pool_local = None

    master_data_list_local = []

    # --- Local Test Blocks for each provider ---

    # --- Process RunPod (Local Test) ---
    try:
        print("\n--- Processing RunPod (Local Test) ---")
        response_local = requests.get(runpod_handler.RUNPOD_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = runpod_handler.fetch_runpod_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"RunPod (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local RunPod test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Vast.ai (Local Test) ---
    try:
        print("\n--- Processing Vast.ai (Local Test) ---")
        vast_html_output_file_local = "vast_rendered.html"
        print("Step 1: Running Selenium to generate fully rendered HTML for Vast.ai...")
        fetch_and_save_final_html(
            vast_ai_handler.VAST_AI_PRICING_URL, vast_html_output_file_local)

        print(
            f"Step 2: Parsing the generated file: '{vast_html_output_file_local}'")
        if os.path.exists(vast_html_output_file_local):
            with open(vast_html_output_file_local, 'r', encoding='utf-8') as f:
                vast_soup_local = BeautifulSoup(f.read(), "html.parser")

            vast_data_local = vast_ai_handler.fetch_vast_ai_data(
                vast_soup_local)
            if vast_data_local:
                master_data_list_local.extend(vast_data_local)
            print(
                f"Vast.ai (Local Test) processed {len(vast_data_local) if vast_data_local else 0} rows.")
        else:
            print(
                f"ERROR: The file '{vast_html_output_file_local}' was not created by the Selenium script.")
    except Exception as e_vast_local:
        print(f"Error in local Vast.ai test: {e_vast_local}")
        import traceback
        traceback.print_exc()

    # --- Process CoreWeave (Local Test) ---
    try:
        print("\n--- Processing CoreWeave (Local Test) ---")
        response_local = requests.get(coreweave_handler.COREWEAVE_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = coreweave_handler.fetch_coreweave_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"CoreWeave (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local CoreWeave test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Genesis Cloud (Local Test) ---
    try:
        print("\n--- Processing Genesis Cloud (Local Test) ---")
        response_local = requests.get(genesiscloud_handler.GENESISCLOUD_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = genesiscloud_handler.fetch_genesiscloud_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Genesis Cloud (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Genesis Cloud test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Lambda Labs (Local Test) ---
    try:
        print("\n--- Processing Lambda Labs (Local Test) ---")
        response_local = requests.get(lambda_labs_handler.LAMBDALABS_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = lambda_labs_handler.fetch_lambda_labs_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Lambda Labs (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Lambda Labs test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Neevcloud (Local Test) ---
    try:
        print("\n--- Processing Neevcloud (Local Test) ---")
        response_local = requests.get(neevcloud_handler.NEEVCLOUD_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = neevcloud_handler.fetch_neevcloud_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Neevcloud (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Neevcloud test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Sakura Internet (Local Test) ---
    try:
        print("\n--- Processing Sakura Internet (Local Test) ---")
        response_vrt_local = requests.get(sakura_internet_handler.SAKURA_VRT_PRICING_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_vrt_local.raise_for_status()
        soup_vrt_local = BeautifulSoup(response_vrt_local.text, "html.parser")
        response_phy_local = requests.get(sakura_internet_handler.SAKURA_PHY_PRICING_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_phy_local.raise_for_status()
        soup_phy_local = BeautifulSoup(response_phy_local.text, "html.parser")
        data_local = sakura_internet_handler.fetch_sakura_internet_data(
            soup_vrt_local, soup_phy_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Sakura Internet (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Sakura Internet test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Soroban (Highreso) (Local Test) ---
    try:
        print("\n--- Processing Soroban (Highreso) (Local Test) ---")
        response_local = requests.get(soroban_highreso_handler.SOROBAN_AISPACON_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = soroban_highreso_handler.fetch_soroban_highreso_data(
            soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Soroban (Highreso) (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Soroban test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Seeweb (Local Test) ---
    try:
        print("\n--- Processing Seeweb (Local Test) ---")
        response_csg_local = requests.get(seeweb_handler.SEEWEB_CLOUD_SERVER_GPU_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_csg_local.raise_for_status()
        soup_csg_local = BeautifulSoup(response_csg_local.text, "html.parser")
        response_slg_local = requests.get(seeweb_handler.SEEWEB_SERVERLESS_GPU_URL, headers={
                                          "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_slg_local.raise_for_status()
        soup_slg_local = BeautifulSoup(response_slg_local.text, "html.parser")
        data_local = seeweb_handler.fetch_seeweb_data(
            soup_csg_local, soup_slg_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Seeweb (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Seeweb test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Scaleway (Local Test) ---
    try:
        print("\n--- Processing Scaleway (Local Test) ---")
        response_h100_local = requests.get(scaleway_handler.SCALEWAY_H100_URL, headers={
                                           "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_h100_local.raise_for_status()
        soup_h100_local = BeautifulSoup(
            response_h100_local.text, "html.parser")
        response_l40s_local = requests.get(scaleway_handler.SCALEWAY_L40S_URL, headers={
                                           "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_l40s_local.raise_for_status()
        soup_l40s_local = BeautifulSoup(
            response_l40s_local.text, "html.parser")
        data_local = scaleway_handler.fetch_scaleway_data(
            soup_h100_local, soup_l40s_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Scaleway (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Scaleway test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Hyperstack (Local Test) ---
    try:
        print("\n--- Processing Hyperstack (Local Test) ---")
        response_local = requests.get(hyperstack_handler.HYPERSTACK_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = hyperstack_handler.fetch_hyperstack_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Hyperstack (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Hyperstack test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Process Koyeb (Local Test) ---
    try:
        print("\n--- Processing Koyeb (Local Test) ---")
        response_local = requests.get(koyeb_handler.KOYEB_PRICING_URL, headers={
                                      "User-Agent": "Mozilla/5.0"}, timeout=60)
        response_local.raise_for_status()
        soup_local = BeautifulSoup(response_local.text, "html.parser")
        data_local = koyeb_handler.fetch_koyeb_data(soup_local)
        if data_local:
            master_data_list_local.extend(data_local)
        print(
            f"Koyeb (Local Test) processed {len(data_local) if data_local else 0} rows.")
    except Exception as e_local:
        print(f"Error in local Koyeb test: {e_local}")
        import traceback
        traceback.print_exc()

    # --- Final Data Writing for Local Test ---
    if master_data_list_local:
        print(
            f"\n--- Total rows from all providers for local test: {len(master_data_list_local)} ---")

        if gs_client_local:
            target_ws_local = MASTER_WORKSHEET_NAME
            print(
                f"\n--- Writing to Google Sheet (Local Test): {target_ws_local}_TestLocal ---")
            write_all_data_to_google_sheet(
                master_data_list_local, target_ws_local + "_TestLocal", gs_client_local)
        else:
            print(
                "\nLocal test: Skipping GSheet write (client not available or SPREADSHEET_ID issue).")

        if db_pool_local:
            print("\n--- Writing to MySQL DB (Local Test) ---")
            write_all_data_to_mysql_db(master_data_list_local, db_pool_local)
        else:
            print("\nLocal test: Skipping MySQL write (DB pool not available).")
    else:
        print("\nLocal test: No data processed from any provider.")

    print("--- Local Test Finished ---")
