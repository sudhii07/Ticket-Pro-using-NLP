import streamlit as st
import boto3
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import uuid
from decimal import Decimal
from botocore.exceptions import ClientError
import json
from typing import List, Dict, Any
from boto3.dynamodb.conditions import Attr # Ensure this import is at the top of your script

# --- Page Config ---
st.set_page_config(page_title="Admin Dashboard", layout="wide")

# --- Custom CSS ---
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(to right, #f0f4f8, #e0f7fa);
        font-family: 'Segoe UI', sans-serif;
    }
    h1 {
        color: #004d40;
        text-align: center;
        font-weight: 700;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0px 2px 8px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-card h3 {
        font-size: 18px;
        color: #555;
    }
    .metric-card p {
        font-size: 24px;
        font-weight: bold;
        margin: 0;
    }
    .css-1y4p8pa {
        background-color: white;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)


# --- Login & Session State Management ---
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'admin_view' not in st.session_state:
    st.session_state.admin_view = 'dashboard'

if not st.session_state.admin_logged_in:
    # Use a column layout to center the login form
    col_empty, col_login, col_empty2 = st.columns([1, 1, 1])
    
    with col_login:
        st.markdown("<h1>🔒 Admin Portal Login</h1>", unsafe_allow_html=True)
        
        with st.form("admin_login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password", placeholder="********")

            submitted = st.form_submit_button("Login to Dashboard", help="Click to login")

            if submitted:
                # Dummy credentials for demonstration
                if username == "admin" and password == "admin123":
                    st.session_state.admin_logged_in = True
                    st.success("Admin login successful! Redirecting...")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    st.stop()
    
# --- Initialize AWS clients ---
try:
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    s3_client = boto3.client('s3')
    products_table = dynamodb.Table('products')
    orders_table = dynamodb.Table('orders')
    support_table = dynamodb.Table('SupportTickets')
    # NEW: Table for Product Categories
    category_table = dynamodb.Table('product_category') 
except Exception as e:
    st.error(f"Error initializing AWS clients: {e}. Please ensure credentials and tables are set up.")
    st.stop()

S3_BUCKET_NAME = "project-student-gap-123"

# Initialize session state for tracking the product being edited
if 'editing_product_id' not in st.session_state:
    st.session_state.editing_product_id = None


# --- Navigation Bar for Admin Panel ---
def admin_navigation():
    # Use a stronger title with an icon
    st.sidebar.markdown("## ⚙️ Control Center", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    
    # Use st.button for navigation, ensuring custom styles can be applied
    if st.sidebar.button("📊 Dashboard", help="View support tickets"):
        st.session_state.admin_view = 'dashboard'
    if st.sidebar.button("📦 Product Management", help="Manage store catalog"):
        st.session_state.admin_view = 'products'
    if st.sidebar.button("🛒 View Orders", help="Review customer transactions"):
        st.session_state.admin_view = 'orders'
    
    st.sidebar.markdown("---")
    
    # Logout button with specific color
    if st.sidebar.button("⬅️ Logout", help="End session", type="primary"):
        st.session_state.admin_logged_in = False
        st.session_state.admin_view = 'dashboard'
        st.success("Logged out successfully!")
        st.rerun()

def convert_decimals(item: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively convert Decimal objects to floats for display in Streamlit."""
    for key, value in item.items():
        if isinstance(value, Decimal):
            item[key] = float(value)
        elif isinstance(value, dict):
            item[key] = convert_decimals(value)
        elif isinstance(value, list):
            item[key] = [convert_decimals(v) if isinstance(v, dict) else float(v) if isinstance(v, Decimal) else v for v in value]
    return item

def fetch_all_items(table_name: str) -> List[Dict[str, Any]]:
    """A helper function to fetch all items from a DynamoDB table and convert Decimals."""
    table = dynamodb.Table(table_name)
    items = []
    try:
        response = table.scan()
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
            
        # Robustly process items, converting decimals only on dictionaries
        cleaned_items = []
        for item in items:
            if isinstance(item, dict):
                cleaned_items.append(convert_decimals(item))
            # Ignore items that are not dictionaries to prevent AttributeError
            
    except Exception as e:
        st.error(f"Error fetching data from {table_name}: {e}")
        return []
    return cleaned_items

# -------------------------------------------------------------------------
# --- Category Management Helper Functions (Using product_category table) ---
# -------------------------------------------------------------------------

def fetch_all_categories() -> List[Dict[str, Any]]:
    """
    MODIFIED: Fetches all unique categories (ID and Name) 
    by scanning the products_table.
    """
    unique_categories = {} # Use a dictionary to store unique pairs (category_id is the key)
    items = []
    try:
        # 1. Scan the PRODUCTS table, projecting only category attributes
        response = products_table.scan(
            ProjectionExpression='category_id, category_name' 
        )
        items.extend(response.get('Items', []))
        
        while 'LastEvaluatedKey' in response:
            response = products_table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey'],
                ProjectionExpression='category_id, category_name'
            )
            items.extend(response.get('Items', []))
            
        # 2. Extract unique categories
        for item in items:
            if isinstance(item, dict) and item.get('category_id') and item.get('category_name'):
                cat_id = item['category_id']
                cat_name = item['category_name']
                # Store the item using its ID as the key to guarantee uniqueness
                unique_categories[cat_id] = {'category_id': cat_id, 'category_name': cat_name}
                
    except Exception as e:
        st.error(f"Error fetching categories from products table: {e}")
        return []
        
    # Return a list of the unique category dictionaries
    return list(unique_categories.values())


def get_product_categories_map() -> Dict[str, str]:
    """Retrieves a map of category_name to category_id."""
    items = fetch_all_categories()
    category_map = {item.get('category_name'): item.get('category_id') for item in items if isinstance(item, dict) and item.get('category_name') and item.get('category_id')}
    return category_map

def add_product_for_new_category(category_id: str, category_name: str):
    """
    Adds a placeholder product entry to the products_table. 
    'product_id' is generated as the PK.
    """
    try:
        # 1. Generate a unique ID for the new product (this is the PK for products_table)
        product_id = str(uuid.uuid4())
        
        # 2. Insert the item into the products_table
        products_table.put_item(
            Item={
                'product_id': product_id,       # Generated Primary Key (PK) for products_table
                'category_id': category_id,      # The category ID (a regular attribute)
                'category_name': category_name # The category name (a regular attribute)
               # Placeholder image
            }
        )
        # st.success(f"Placeholder product for category '{category_name}' added to products table.")
    except Exception as e:
        st.error(f"Error adding placeholder product to products_table: {e}")
def add_new_category(category_name: str):
    """
    Adds a new category to the product_category table (PK: category_id)
    AND adds a placeholder product to the products_table (PK: product_id).
    """
    try:
        category_id = str(uuid.uuid4())
        
        # 1. Add to the product_category table
        category_table.put_item(
            Item={
                'category_id': category_id,
                'category_name': category_name
            }
        )
        
        # 2. Add a placeholder entry to the products_table using the new ID
        add_product_for_new_category(category_id, category_name) 

        st.success(f"Category '{category_name}' added successfully! 🎉")
    except Exception as e:
        st.error(f"Error adding category: {e}")

# NO CHANGE NEEDED HERE (It must delete from the dedicated 'product_category' table)
def unlink_products_from_category(category_id: str, category_name: str) -> int:
    """
    Scans the products table for items matching the category_id and UNLINKS them
    by setting category_id/category_name to None/Uncategorized.
    Returns the count of products unlinked.
    """
    products_to_update = []
    
    # 1. Scan for products in the given category (Projection is optional but good practice)
    try:
        response = products_table.scan(
            FilterExpression=Attr('category_id').eq(category_id),
            ProjectionExpression='product_id' # Only need ID to update
        )
        products_to_update.extend(response.get('Items', []))

        while 'LastEvaluatedKey' in response:
            response = products_table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey'],
                FilterExpression=Attr('category_id').eq(category_id),
                ProjectionExpression='product_id'
            )
            products_to_update.extend(response.get('Items', []))
    except Exception as e:
        st.error(f"Error scanning products for unlinking: {e}")
        return 0

    # 2. Update found products (remove the category link)
    unlinked_count = 0
    with st.spinner(f"Unlinking {len(products_to_update)} products from category '{category_name}'..."):
        for product in products_to_update:
            try:
                products_table.update_item(
                    Key={'product_id': product['product_id']},
                    # Use REMOVE to clear the attributes or SET to 'Uncategorized'
                    UpdateExpression="REMOVE category_id, category_name" 
                )
                unlinked_count += 1
            except Exception as e:
                st.warning(f"Failed to unlink product {product.get('product_id', 'N/A')}. Error: {e}")
                
    return unlinked_count

def delete_category_from_db(category_name: str, category_map: Dict[str, str]):
    """
    Unlinks products from the category in products_table and then deletes 
    the category from the product_category table.
    """
    try:
        category_id_to_delete = category_map.get(category_name)
        
        if not category_id_to_delete:
            st.error(f"Category ID for '{category_name}' not found.")
            return

        # --- STEP 1: Unlink Products in products_table ---
        unlinked_count = unlink_products_from_category(category_id_to_delete, category_name)
        
        # --- STEP 2: Delete Category from Master Table ---
        # This deletes the category from the source of truth (PK: category_id)
        category_table.delete_item(Key={'category_id': category_id_to_delete})
        
        st.success(f"Category '{category_name}' deleted successfully! {unlinked_count} associated products were unlinked. 🗑️")
        
    except Exception as e:
        st.error(f"Error deleting category: {e}")

# -------------------------------------------------------------------------
# --- Product Management Helper Functions (General) ---
# -------------------------------------------------------------------------

def delete_product_from_db(product_id_to_delete: str):
    """Deletes a product from DynamoDB and triggers a rerun."""
    try:
        products_table.delete_item(Key={'product_id': product_id_to_delete})
        st.success(f"Product deleted successfully! 🗑️")
        st.rerun()
    except Exception as e:
        st.error(f"Error deleting product: {e}")

def update_product_in_db(product_id: str, new_name: str, new_category_name: str, new_price: float, category_map: Dict[str, str]):
    """Updates product details in DynamoDB and exits edit mode."""
    
    new_category_id = category_map.get(new_category_name)
    if not new_category_id:
        st.error(f"Error: Category ID not found for '{new_category_name}'. Update failed.")
        return

    with st.spinner(f"Updating product {product_id[:8]}..."):
        try:
            products_table.update_item(
                Key={'product_id': product_id},
                UpdateExpression="SET product_name = :n, category_id = :c_id, category_name = :c_name, price = :p",
                ExpressionAttributeValues={
                    ':n': new_name,
                    ':c_id': new_category_id,
                    ':c_name': new_category_name, # Storing both ID and Name for easier lookup/display
                    ':p': Decimal(str(new_price))
                }
            )
            # Crucial: Exit edit mode after successful update
            st.session_state.editing_product_id = None 
            st.success(f"Product **{new_name}** updated successfully! ✨")
            st.rerun()
        except ClientError as e:
            st.error(f"Error updating product: {e.response['Error']['Message']}")

# -------------------------------------------------------------------------
# --- Admin Dashboard Functions ---
# -------------------------------------------------------------------------

def admin_dashboard_view():
    st.markdown("<h1>🎛️ Support Ticket Admin Panel</h1>", unsafe_allow_html=True)
    
    # --- Data Fetching and Preparation ---
    items = fetch_all_items('SupportTickets')
    df = pd.DataFrame(items)

    if df.empty:
        st.warning("📭 No tickets found in DynamoDB!")
        return
    
    # Ensure necessary columns exist for filtering/display
    if 'status' not in df.columns:
        df['status'] = 'Not Taken'
    if 'order_id' not in df.columns: 
        df['order_id'] = None
    if 'category' not in df.columns:
        df['category'] = 'N/A' 
    df['category'] = df['category'].fillna('N/A')
    
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    else:
        df['timestamp'] = pd.NaT
        
    def emoji_priority(priority):
        if priority == "High":
            return "🔴 High"
        elif priority == "Medium":
            return "🟠 Medium"
        else:
            return "🟢 Low"

    if 'priority' in df.columns:
        df["priority_display"] = df["priority"].apply(emoji_priority)
    else:
        df["priority_display"] = "🟢 Unknown"

    if 'description' in df.columns:
        df["short_description"] = df["description"].apply(lambda x: x[:100] + "..." if isinstance(x, str) and len(x) > 100 else x)
    else:
        df["short_description"] = ""
        
    # --- Metric Cards ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<div class='metric-card'><h3>📬 Total Tickets</h3><p>{len(df)}</p></div>", unsafe_allow_html=True)
    with col2:
        high_count = df[df.get('priority', '') == 'High'].shape[0] if 'priority' in df.columns else 0
        st.markdown(f"<div class='metric-card'><h3>🔴 High Priority</h3><p>{high_count}</p></div>", unsafe_allow_html=True)
    with col3:
        medium_count = df[df.get('priority', '') == 'Medium'].shape[0] if 'priority' in df.columns else 0
        st.markdown(f"<div class='metric-card'><h3>🟠 Medium Priority</h3><p>{medium_count}</p></div>", unsafe_allow_html=True)

    st.markdown("---")

    # --- INITIAL UNIVERSAL FILTERING ---
    selected_priority = st.selectbox("📌 Filter by Priority (Universal)", ["All", "High", "Medium", "Low"])
    search_term = st.text_input("🔍 Search Order ID / Ticket ID (Universal)")
    
    # Apply universal filters
    base_filtered_df = df.copy()
    
    if selected_priority != "All" and 'priority' in base_filtered_df.columns:
        base_filtered_df = base_filtered_df[base_filtered_df["priority"] == selected_priority]

    if search_term and ('order_id' in base_filtered_df.columns or 'ticket_id' in base_filtered_df.columns):
        base_filtered_df = base_filtered_df[
            base_filtered_df.get("order_id", "").astype(str).str.contains(search_term, case=False, na=False) |
            base_filtered_df.get("ticket_id", "").astype(str).str.contains(search_term, case=False, na=False)
        ]
        
    # --- SPLIT INTO TWO BASE DATAFRAMES (BEFORE CATEGORY FILTERING) ---
    no_order_values = [None, '', 'n/a', 'na'] 
    order_id_standardized = base_filtered_df['order_id'].astype(str).str.strip().str.lower()
    
    tickets_with_order_id_base = base_filtered_df[
        ~order_id_standardized.isin(no_order_values)
    ].copy()

    tickets_without_order_id_base = base_filtered_df[
        order_id_standardized.isin(no_order_values)
    ].copy()
    
    # --- DUAL CATEGORY FILTER UI - GENERATE UNIQUE OPTIONS FOR EACH TABLE ---
    
    # 1. Categories for Order-Linked Tickets
    categories_order = ["All"] + sorted(tickets_with_order_id_base['category'].unique().tolist())
    
    # 2. Categories for General Tickets
    categories_no_order = ["All"] + sorted(tickets_without_order_id_base['category'].unique().tolist())
    
    st.subheader("Category Filtering")
    col_filter1, col_filter2 = st.columns(2)
    
    with col_filter1:
        selected_category_order = st.selectbox(
            "📂 Filter Category for **Order-Linked Tickets**", 
            categories_order, 
            key='cat_filter_order'
        )
    
    with col_filter2:
        selected_category_no_order = st.selectbox(
            "📂 Filter Category for **General Tickets**", 
            categories_no_order, 
            key='cat_filter_no_order'
        )

    # --- APPLY DUAL CATEGORY FILTERS ---
    
    # 1. Filter for Order-Linked Tickets
    if selected_category_order != "All":
        tickets_with_order_id = tickets_with_order_id_base[
            tickets_with_order_id_base["category"] == selected_category_order
        ]
    else:
        tickets_with_order_id = tickets_with_order_id_base
        
    # 2. Filter for General Tickets
    if selected_category_no_order != "All":
        tickets_without_order_id = tickets_without_order_id_base[
            tickets_without_order_id_base["category"] == selected_category_no_order
        ]
    else:
        tickets_without_order_id = tickets_without_order_id_base
        
    display_columns = ['ticket_id', 'order_id', 'timestamp', 'name', 'email', 'category', 'short_description', 'priority_display', 'sentiment', 'status']
    
    # --- Function to build and display AgGrid ---
    def display_ticket_grid(df_to_display, title, grid_key):
        df_display = df_to_display[[col for col in display_columns if col in df_to_display.columns]].copy()
        
        # --- HEIGHT CALCULATION FIX ---
        num_rows = len(df_to_display)
        ROW_HEIGHT_PX = 50
        HEADER_HEIGHT_PX = 50 
        MIN_HEIGHT_PX = 200
        MAX_HEIGHT_PX = 500

        required_height = (num_rows * ROW_HEIGHT_PX) + HEADER_HEIGHT_PX
        final_height = max(MIN_HEIGHT_PX, min(MAX_HEIGHT_PX, required_height))
        # ---------------------------

        gb = GridOptionsBuilder.from_dataframe(df_display)
        gb.configure_column("short_description", header_name="Description", wrapText=True, autoHeight=True, width=350)
        gb.configure_column("priority_display", header_name="Priority", width=120)
        gb.configure_column(
            "status",
            header_name="Status",
            editable=True,
            cellEditor='agSelectCellEditor',
            cellEditorParams={'values': ['Not Taken', 'Pending', 'Completed']},
            width=150
        )
        gb.configure_default_column(wrapText=True, autoHeight=True)
        grid_options = gb.build()

        st.subheader(title)
        return AgGrid(
            df_display,
            gridOptions=grid_options,
            height=final_height, 
            fit_columns_on_grid_load=True,
            allow_unsafe_jscode=True,
            data_return_mode=DataReturnMode.AS_INPUT,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            editable=True,
            key=grid_key
        )


    # --- DISPLAY GRIDS and UPDATE LOGIC ---
    grid_response_order = display_ticket_grid(
        tickets_with_order_id, 
        f"💳 Tickets Linked to an Order ({len(tickets_with_order_id)})", 
        'ticket_grid_order'
    )
    
    st.markdown("---")

    grid_response_no_order = display_ticket_grid(
        tickets_without_order_id, 
        f"⚙️ General Tickets ({len(tickets_without_order_id)})", 
        'ticket_grid_no_order'
    )
    
    updated_df_order = grid_response_order['data']
    merged_df_order = pd.merge(tickets_with_order_id, updated_df_order, on='ticket_id', suffixes=('_old', '_new'))
    changed_rows_order = merged_df_order[merged_df_order['status_old'] != merged_df_order['status_new']]

    updated_df_no_order = grid_response_no_order['data']
    merged_df_no_order = pd.merge(tickets_without_order_id, updated_df_no_order, on='ticket_id', suffixes=('_old', '_new'))
    changed_rows_no_order = merged_df_no_order[merged_df_no_order['status_old'] != merged_df_no_order['status_new']]
    
    all_changed_rows = pd.concat([changed_rows_order, changed_rows_no_order])

    if not all_changed_rows.empty:
        for index, row in all_changed_rows.iterrows():
            ticket_id = row['ticket_id']
            new_status = row['status_new']
            
            try:
                with st.spinner(f"Updating ticket {ticket_id} status..."):
                    support_table.update_item(
                        Key={'ticket_id': ticket_id},
                        UpdateExpression="SET #s = :val",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":val": new_status}
                    )
                    st.success(f"Ticket {ticket_id} status updated to **{new_status}**! ✨")
                    st.rerun() 
            except Exception as e:
                st.error(f"Error updating ticket {ticket_id}: {e}")
                break

    st.markdown("---")
    export_columns = ['ticket_id', 'timestamp', 'name', 'email', 'category', 'description', 'priority', 'sentiment', 'status', 'order_id']
    df_export = df[[col for col in export_columns if col in df.columns]]
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Download Full Tickets CSV",
        data=csv,
        file_name='support_tickets.csv',
        mime='text/csv',
    )

# -------------------------------------------------------------------------
# --- Product Management View ---
# -------------------------------------------------------------------------
def products_view():
    st.markdown("<h1>📦 Product Management</h1>", unsafe_allow_html=True)
    
    # --- DYNAMICALLY FETCH CATEGORIES (From the source of truth, products_table via fetch_all_categories) ---
    category_map = get_product_categories_map()
    PRODUCT_CATEGORIES_NAMES = sorted(category_map.keys())

    if not PRODUCT_CATEGORIES_NAMES:
        st.info("No categories found. Please add one below to start managing products.")
    
    # --- Section 1: Manage Categories ---
    st.markdown("### ⚙️ Manage Categories")
    
    col_cat1, col_cat2 = st.columns([3, 1])
    
    with col_cat1:
        st.markdown(f"**Current Categories:** {', '.join(PRODUCT_CATEGORIES_NAMES)}")
        new_category_name = st.text_input("New Category Name", key="new_cat_name", placeholder="e.g., Seasonal Sales")

    with col_cat2:
        st.markdown("<br>", unsafe_allow_html=True) # Align button
        if st.button("➕ Add Category", use_container_width=True, type="secondary"):
            if new_category_name and new_category_name not in PRODUCT_CATEGORIES_NAMES:
                # Calls the updated function which adds to both tables
                add_new_category(new_category_name)
                st.rerun()
            elif new_category_name:
                st.warning(f"Category '{new_category_name}' already exists.")
            else:
                st.warning("Please enter a category name.")
            
    # Delete Category UI
    if PRODUCT_CATEGORIES_NAMES:
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            # Dropdown populated with fetched categories
            category_to_delete = st.selectbox(
                "Select Category to Delete", 
                options=[""] + PRODUCT_CATEGORIES_NAMES, 
                key="cat_to_delete"
            )
        
        with col_del2:
            st.markdown("<br>", unsafe_allow_html=True) # Align button
            if category_to_delete and st.button("🗑️ Delete Selected", use_container_width=True, type="primary"):
                if category_to_delete in PRODUCT_CATEGORIES_NAMES:
                    delete_category_from_db(category_to_delete, category_map)
                    st.rerun()
                
    st.markdown("---")


    # --- Section 2: Add a New Product (USES DYNAMIC CATEGORIES) ---
    st.markdown("### ➕ Add a New Product")
    with st.form("add_product_form", clear_on_submit=True):
        product_name = st.text_input("Product Name")
        
        # USE DYNAMIC CATEGORIES HERE
        if PRODUCT_CATEGORIES_NAMES:
            category_name_selected = st.selectbox("Category", options=PRODUCT_CATEGORIES_NAMES, key="add_category")
        else:
            category_name_selected = st.text_input("Category (Add one above first)", disabled=True, key="add_category_disabled")
            
        # Standard input for new products starts at min_value
        price = st.number_input("Price", min_value=0.01, format="%.2f") 
        uploaded_file = st.file_uploader("Upload Product Image", type=['jpg', 'png', 'jpeg'])
        
        submitted = st.form_submit_button("Add Product", disabled=not bool(PRODUCT_CATEGORIES_NAMES))
        if submitted:
            if not product_name or not uploaded_file or not PRODUCT_CATEGORIES_NAMES:
                st.error("Please fill in all fields and ensure at least one category exists.")
            else:
                try:
                    product_id = str(uuid.uuid4())
                    image_path = f"products/{product_id}_{uploaded_file.name}"
                    s3_client.upload_fileobj(uploaded_file, S3_BUCKET_NAME, image_path)
                    image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{image_path}"
                    
                    # Get the category ID corresponding to the selected name
                    selected_category_id = category_map.get(category_name_selected)
                    if not selected_category_id:
                        st.error(f"Error: Could not find ID for category '{category_name_selected}'. Product upload failed.")
                        st.stop() # Stop execution if category ID is missing

                    products_table.put_item(
                        Item={
                            'product_id': product_id,
                            'product_name': product_name,
                            'category_id': selected_category_id, # Use ID for relational integrity
                            'category_name': category_name_selected, # Store name for easier display/query
                            'price': Decimal(str(price)),
                            'image_url': image_url
                        } 
                    )
                    st.success(f"Product '{product_name}' added to category '{category_name_selected}' successfully!")
                    st.rerun()
                except ClientError as e:
                    st.error(f"Error uploading product: {e.response['Error']['Message']}")

    st.markdown("---")

    # --- Section 3: Manage Existing Products using CARDS ---
    st.markdown("### 📝 Manage Existing Products")
    
    # Fetch all items from products table
    items = fetch_all_items('products')
    
    # 💡 FILTER MODIFICATION: Remove products with missing/empty names OR placeholder names
    def is_valid_product(item):
        """Checks if the item is a dictionary and has a valid, non-placeholder product_name."""
        if not isinstance(item, dict):
            return False
        name = item.get('product_name')
        
        # 1. Check for missing/empty/whitespace name
        if not name or not isinstance(name, str) or name.strip() == "":
            return False
            
        # 2. Exclude the placeholder product used for new categories
        if "Placeholder Product for" in name:
             return False
             
        return True

    # Apply the filter
    items = [item for item in items if is_valid_product(item)]

    if not items:
        st.info("No products available to manage.")
    else:
        items.sort(key=lambda x: x.get('product_name', '').lower())

        cols = st.columns(3) 
        
        # Check if any product is currently in edit mode to disable other edit buttons
        is_any_product_editing = st.session_state.editing_product_id is not None
        
        for i, product in enumerate(items):
            product_id = product['product_id']
            product_name = product.get('product_name', 'No Name')
            
            # 💡 PRICE FIX: Ensure the price defaults to 0.01 (min_value) to prevent Streamlit crash
            price = product.get('price', 0.01)
            
            # Use category_name for display
            category_name_display = product.get('category_name', PRODUCT_CATEGORIES_NAMES[0] if PRODUCT_CATEGORIES_NAMES else 'Uncategorized')
            image_url = product.get('image_url', '')

            # DETERMINE EDIT STATE FOR THIS SPECIFIC CARD
            is_editing_this_card = (st.session_state.editing_product_id == product_id)
            
            with cols[i % 3]:
                with st.container(border=True):
                    
                    st.markdown(f"**{product_name}**", unsafe_allow_html=True)
                    
                    if image_url:
                        st.image(image_url, caption=f"ID: {product_id[:8]}...", width=100)
                    
                    # 1. Editable/Disabled Input Fields
                    st.text_input("Name", value=product_name, key='name_'+product_id, disabled=not is_editing_this_card, label_visibility="collapsed")
                    
                    # USE DYNAMIC CATEGORIES for the edit selectbox
                    default_index = PRODUCT_CATEGORIES_NAMES.index(category_name_display) if category_name_display in PRODUCT_CATEGORIES_NAMES else 0
                    
                    # Ensure options are only available if categories exist
                    if PRODUCT_CATEGORIES_NAMES:
                        st.selectbox("Category", options=PRODUCT_CATEGORIES_NAMES, index=default_index, key='cat_'+product_id, disabled=not is_editing_this_card, label_visibility="collapsed")
                    else:
                        st.text_input("Category", value=category_name_display, key='cat_'+product_id, disabled=True, label_visibility="collapsed")

                    # This is the line that required the price check above
                    st.number_input("Price", value=price, format="%.2f", key='price_'+product_id, min_value=0.01, disabled=not is_editing_this_card, label_visibility="collapsed")

                    st.markdown("---", help="Actions")

                    col_b1, col_b2 = st.columns(2)
                    
                    if not is_editing_this_card:
                        # --- VIEW MODE BUTTONS ---
                        if col_b1.button("✏️ Edit", key='edit_'+product_id, use_container_width=True, disabled=is_any_product_editing):
                            st.session_state.editing_product_id = product_id
                            st.rerun()

                        with col_b2:
                            with st.popover("🗑️ Delete", use_container_width=True, disabled=is_any_product_editing):
                                st.warning(f"Are you sure you want to permanently delete **{product_name}**?")
                                st.caption("This action cannot be undone.")
                                if st.button("CONFIRM DELETE", key='confirm_delete_'+product_id, type="primary", use_container_width=True):
                                    delete_product_from_db(product_id)
                            
                    else:
                        # --- EDIT MODE BUTTONS ---
                        # Get the values from the state-controlled input fields
                        if col_b1.button("💾 Update", key='update_'+product_id, type="primary", use_container_width=True):
                            # Note: Reading current state values from the keys defined above
                            updated_name = st.session_state['name_'+product_id]
                            updated_category = st.session_state['cat_'+product_id]
                            updated_price = st.session_state['price_'+product_id]
                            
                            update_product_in_db(product_id, updated_name, updated_category, updated_price, category_map)

                        if col_b2.button("🚫 Cancel", key='cancel_'+product_id, use_container_width=True):
                            st.session_state.editing_product_id = None
                            st.rerun()

    st.markdown("---")

    # --- Download CSV ---
    df_products = pd.DataFrame(items)
    if not df_products.empty:
        # Decimal conversion is handled by fetch_all_items, so no extra conversion needed here
        csv = df_products.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Products CSV",
            data=csv,
            file_name='products.csv',
            mime='text/csv',
        )

# -------------------------------------------------------------------------
# --- Order View ---
# -------------------------------------------------------------------------

def orders_view():
    st.markdown("<h1>🛒 User Orders</h1>", unsafe_allow_html=True)
    # Price and other Decimal types are converted to float by fetch_all_items
    items = fetch_all_items('orders') 
    df = pd.DataFrame(items)

    if df.empty:
        st.warning("📭 No orders found in DynamoDB!")
        return

    df['timestamp'] = pd.to_datetime(df.get('timestamp', ''), errors='coerce')
    df = df.sort_values('timestamp', ascending=False)
    
    st.subheader("All User Orders")
    st.dataframe(df, use_container_width=True)
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Download Orders CSV",
        data=csv,
        file_name='user_orders.csv',
        mime='text/csv',
    )
    
# -------------------------------------------------------------------------
# --- Main Admin App Logic ---
# -------------------------------------------------------------------------
admin_navigation()

if st.session_state.admin_view == 'dashboard':
    admin_dashboard_view()
elif st.session_state.admin_view == 'products':
    products_view()
elif st.session_state.admin_view == 'orders':
    orders_view()