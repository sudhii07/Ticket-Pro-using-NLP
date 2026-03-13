import streamlit as st
import boto3
from botocore.exceptions import ClientError
import uuid
import re
from PIL import Image
import json
import io
from decimal import Decimal
from boto3.dynamodb.conditions import Attr 
import bcrypt # SECURE HASHING LIBRARY
import time 
import sys # Import system module for conditional execution
from typing import List, Dict, Any # Added missing import for helper functions
import random
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Attr


# --- HASHING HELPER FUNCTIONS (RECONFIRMED) ---
def hash_password(password):
    """Generates a secure, salt-based bcrypt hash string ($2b$...)."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(provided_password, stored_hash):
    """Verifies a plain password against the stored bcrypt hash."""
    if not stored_hash:
        return False
    # Ensure the hash is bytes for bcrypt.checkpw
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode('utf-8')
    try:
        # Checkpw handles verification, returns True or False
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash)
    except Exception:
        # Catches errors if the hash format is invalid
        return False

# --- END HASHING HELPERS ---

S3_BUCKET_NAME = "sudhan-ticketpro"
lambda_client = None # Declare globally

# Initialize AWS clients
try:
    s3_client = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    # NOTE: Table names assumed from previous context
    products_table = dynamodb.Table('products')
    users_table = dynamodb.Table('users-ecom')
    orders_table = dynamodb.Table('orders')
    support_table = dynamodb.Table('SupportTickets')
    
    # --- IMPORTANT CHANGE: Initialize Lambda Client here for global use ---
    # NOTE: You should ensure 'ap-south-1' is the correct region for your Lambda.
    lambda_client = boto3.client('lambda', region_name='ap-south-1') 
    
    # NEW: Table for Product Categories
    category_table = dynamodb.Table('product_category') 
    
except ClientError as e:
    # Use st.error instead of st.stop for better canvas compatibility
    st.error(f"AWS Client Error: {e.response['Error']['Message']}. Please check your AWS configuration.")
except Exception as e:
    st.error(f"An unexpected error occurred during AWS initialization: {e}.")


# -------------------------------------------------------------------------
# --- Category Management Helper Functions (Copied from Admin Dashboard) ---
# -------------------------------------------------------------------------

def fetch_all_categories() -> List[Dict[str, Any]]:
    """
    MODIFIED: Fetches all unique categories (ID and Name) 
    by scanning the products_table.
    """
    unique_categories = {} # Use a dictionary to store unique pairs (category_id is the key)
    items = []
    
    # NOTE: products_table is assumed to be initialized globally
    # If the user has not yet added categories, this table might be missing category_id/category_name attributes.
    
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
            
        # 2. Extract unique categories, ensuring robustness against malformed/missing data
        for item in items:
            if isinstance(item, dict) and item.get('category_id') and item.get('category_name'):
                cat_id = item['category_id']
                cat_name = item['category_name']
                # Store the item using its ID as the key to guarantee uniqueness
                unique_categories[cat_id] = {'category_id': cat_id, 'category_name': cat_name}
                
    except Exception as e:
        # Print error but return empty list to prevent crash
        print(f"Error fetching categories from products table for user: {e}") 
        return []
        
    # Return a list of the unique category dictionaries
    return list(unique_categories.values())


def get_product_categories() -> List[str]:
    """
    Retrieves a list of unique category names by calling the modified fetch_all_categories.
    """
    items = fetch_all_categories()
    # Extract only the names for the Streamlit select boxes/options
    category_names = sorted([item.get('category_name') for item in items if item.get('category_name')])
    return category_names
# -------------------------------------------------------------------------


def load_products():
    response = products_table.scan()
    return response['Items']

def get_user(username):
    try:
        response = users_table.get_item(Key={'username': username})
        return response.get('Item')
    except ClientError:
        return None

# --- Session State Management ---
if 'logged_in_as' not in st.session_state:
    st.session_state.logged_in_as = 'public'
if 'view' not in st.session_state:
    st.session_state.view = 'public'

def is_strong_password(password):
    if len(password) < 8: return False
    if not re.search(r'[A-Z]', password): return False
    if not re.search(r'[a-z]', password): return False
    if not re.search(r'[0-9]', password): return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password): return False
    return True
    
# --- Navigation (Simplified) ---
def main_menu():
    if st.session_state.logged_in_as == 'admin':
        with st.sidebar:
            st.title("Admin Navigation")
            if st.button("Admin Dashboard"):
                st.session_state.view = 'admin_dashboard'
            if st.button("Logout"):
                st.session_state.logged_in_as = 'public'
                st.session_state.view = 'public'
                st.rerun()
    elif st.session_state.logged_in_as != 'public': # Logged in user
        with st.sidebar:
            st.title("User Navigation")
            if st.button("🛍️ Product Catalog"):
                st.session_state.view = 'user_dashboard'
            if st.button("📦 My Orders"):
                st.session_state.view = 'view_orders'
            # --- NEW BUTTON HERE ---
            if st.button("🎫 Raise Ticket"):
                st.session_state.view = 'raise_general_ticket'
            # --- END NEW BUTTON ---
            if st.button("🎫 My Tickets"):
                st.session_state.view = 'track_tickets'
            if st.button("🚪 Logout"):
                st.session_state.logged_in_as = 'public'
                st.session_state.view = 'public'
                st.rerun()
    # else: no sidebar for public users

# --- Custom CSS for UI Enhancement (Login/Register and Public View) ---
def load_custom_css():
    st.markdown("""
        <style>
        /* --- GLOBAL BACKGROUND AND FONT --- */
        .stApp {
            /* Professional, subtle blue gradient background */
            background: linear-gradient(135deg, #f7f9fc 0%, #e0e7f7 100%); 
            background-attachment: fixed;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        /* Streamlit specific targets for full width consistency */
        .st-emotion-cache-1pxx5r6 { 
            padding-bottom: 0 !important;
        }

        /* --- MAIN TITLE (Replaces old .hero-title and stApp h1) --- */
        .stApp h1 {
            font-size: 3.8rem;
            font-weight: 900;
            color: #1a4f78; /* Deep Blue */
            text-align: center;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 6px rgba(0,0,0,0.1);
            animation: fadeIn 1s ease-out;
        }
        
        /* --- SUBTITLE (Replaces old stApp h3) --- */
        .stApp h3 {
            font-weight: 400;
            color: #3f6e91;
            text-align: center;
            margin-bottom: 50px;
            animation: fadeIn 1.5s ease-out;
        }

        /* --- AUTH CARD STYLING (Kept for Login/Register pages) --- */
        .auth-card {
            background: #ffffff;
            padding: 2.5rem 3rem;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            width: 100%;
            max-width: 450px;
            margin: auto;
            margin-top: 50px;
            text-align: center;
            border-top: 5px solid #007bff; /* Primary color accent */
        }
        .auth-card h2 {
            text-align: center;
            color: #1e3c72;
            margin-bottom: 1.5rem;
            font-size: 2rem;
            font-weight: 700;
        }
        .auth-card .stButton>button {
            width: 100%;
            background: linear-gradient(90deg, #1e3c72, #2a5298); 
            color: white;
            border-radius: 10px;
            padding: 0.8rem 1.5rem;
            font-size: 1.1rem;
            font-weight: 600;
            border: none;
            transition: all 0.3s ease;
        }
        .auth-card .stButton>button:hover {
            background: linear-gradient(90deg, #2a5298, #1e3c72);
            box-shadow: 0 4px 10px rgba(42, 82, 152, 0.4);
        }
        
        /* --- PRIMARY CTA BUTTONS (Used on Public View) --- */
        .cta-button button {
            background: linear-gradient(90deg, #007bff, #0056b3) !important; /* Brighter Blue Gradient */
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 1rem 2rem !important;
            font-size: 1.2rem !important;
            font-weight: 700 !important;
            transition: all 0.4s ease;
            box-shadow: 0 4px 15px rgba(0, 123, 255, 0.4);
            margin: 20px 0;
        }
        .cta-button button:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(0, 123, 255, 0.6) !important;
            background: linear-gradient(90deg, #0056b3, #007bff) !important;
        }
        
        /* --- FEATURE CARDS (NEW: For showcasing features on Public View) --- */
        .feature-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            margin-bottom: 20px;
            height: 100%; /* Important: Tells the card to occupy full height of its container */
            border: 1px solid #e0e0e0;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .feature-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.15);
        }
        .feature-card h4 {
            color: #007bff;
            font-weight: 700;
            margin-top: 0;
            margin-bottom: 15px;
        }
        .feature-icon {
            font-size: 2.5rem;
            color: #28a745; /* Success/Green color for tech/AI focus */
            margin-bottom: 15px;
        }
        
        /* --- COLUMN ALIGNMENT FIX (THE SOLUTION) --- */
        /* Targets the Streamlit element that wraps the columns (stHorizontalBlock) */
        /* Forces columns to stretch to the height of the tallest item */
        [data-testid="stHorizontalBlock"] {
            align-items: stretch; 
        }

        /* --- ANIMATIONS --- */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        </style>
    """, unsafe_allow_html=True)
    
# --- Login Page (Enhanced UI) ---
def login_page():
    load_custom_css()
    
    # Use columns to center the card on the page and give it room
    col_l, col_center, col_r = st.columns([1.5, 2, 1.5])
    
    with col_center:
        # **CORRECTION**: Wrap all elements in the custom UI card
        
        
        st.markdown("<h2>🚪 Log In</h2>", unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("👤 Username", key="login_username")
            password = st.text_input("🔒 Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login")
            
        # Add the Register button/link after the form
        st.markdown("<hr style='border: 0.5px solid #eee; margin: 1.5rem 0;'>", unsafe_allow_html=True)
        
        # Use a plain Streamlit button here. The custom CSS will style it if needed, 
        # but let's make sure it doesn't use the primary button style of the Login button 
        # to differentiate it. We'll use a unique key.
        if st.button("📝 Create New Account (Register)", key="login_to_register", use_container_width=True):
            st.session_state.view = 'register'
            st.rerun()
        if st.button("🔑 Forgot Password?", key="login_forgot_password", use_container_width=True):
            st.session_state.view = 'forgot_password'
            st.rerun()


        st.markdown("</div>", unsafe_allow_html=True) # Close the custom UI card div

    # The logic handling form submission should ideally be outside the 'with col_center' 
    # block if you want it to execute only once upon form submission, but based on your 
    # original pattern, we keep the logic here:

    if submitted:
        if username == "admin" and password == "admin123":
            st.session_state.logged_in_as = 'admin'
            st.session_state.view = 'admin_dashboard'
            st.success("Admin login successful!")
            st.rerun()
            return

        user = get_user(username)
        if user:
            stored_hash = user.get('password')
            if stored_hash and verify_password(password, stored_hash):
                st.session_state.logged_in_as = username
                st.session_state.view = 'user_dashboard'
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
        else:
            st.error("Invalid username or password.")
            
# --- Register Page (Enhanced UI) ---
def register_page():
    load_custom_css()
    
    # Use columns to center the card on the page and give it room
    col_l, col_form, col_r = st.columns([1, 3, 1])
    
    with col_form:
        
        st.markdown("<h2>📝 Register New User</h2>", unsafe_allow_html=True)

        with st.form("register_form"):
            st.markdown("### Account Details")
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("👤 Enter a Username", key="reg_username")
            with col2:
                new_email = st.text_input("📧 Enter your Email (@gmail.com)", key="reg_email")
                
            new_phone = st.text_input("📞 Enter your Phone Number (10 digits)", key="reg_phone")
            st.markdown("---")
            st.markdown("### Security")
            
            new_password = st.text_input("🔒 Choose a Password (Strong required)", type="password", key="reg_password")
            confirm_password = st.text_input("✅ Confirm Password", type="password", key="reg_confirm_password")
            
            st.markdown(
                """
                <p style='font-size: 0.8rem; color: #666; margin-top: -10px;'>
                Password must be at least 8 chars, and include uppercase, lowercase, number, and a special character.
                </p>
                """, unsafe_allow_html=True
            )
            
            submit_button = st.form_submit_button("🚀 Complete Registration", use_container_width=True)

        if submit_button:
            # --- Comprehensive Validation ---
            if not all([new_username, new_password, confirm_password, new_email, new_phone]):
                st.error("Please fill in **all** fields.")
                return

            if new_password != confirm_password:
                st.error("Passwords do not match.")
                return

            if not re.fullmatch(r"[^@]+@gmail\.com", new_email):
                st.error("Invalid email format. Must be a valid @gmail.com address.")
                return

            if not re.fullmatch(r"^\d{10}$", new_phone):
                st.error("Phone number must be exactly 10 digits.")
                return
                
            if not is_strong_password(new_password):
                st.error("Password is not strong enough. It must be at least 8 characters, and include uppercase, lowercase, number, and a special character.")
                return
            
            if get_user(new_username):
                st.error("This username already exists.")
                return
            
            try:
                # HASH THE PASSWORD using the secure, salt-based function (bcrypt)
                hashed_password = hash_password(new_password)
                
                users_table.put_item(
                    Item={
                        'username': new_username,
                        'password': hashed_password, 
                        'email': new_email,
                        'phone': new_phone
                    },
                    # Add ConditionExpression for safety to ensure username does not exist (Race condition prevention)
                    ConditionExpression=Attr('username').not_exists()
                )
                st.success("Registration successful! You can now log in.")
                st.session_state.view = 'login'
                st.rerun()
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    st.error("This username already exists.")
                else:
                    st.error(f"Could not register user: {e.response['Error']['Message']}")
            except Exception as e:
                st.error(f"An unexpected error occurred during registration: {e}")

        st.markdown("<div class='nav-btn-container'>", unsafe_allow_html=True)
        col_nav_1, col_nav_2 = st.columns(2)
        with col_nav_1:
            if st.button("⬅️ Go to Login", use_container_width=True):
                st.session_state.view = 'login'
                st.rerun()
        with col_nav_2:
            if st.button("🏠 HOME", key="register_to_public", use_container_width=True):
                st.session_state.view = 'public'
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ================ FORGOT PASSWORD (OTP SYSTEM with Gmail / Yahoo / Outlook) ================
import random
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Attr

otp_store = {}

def send_otp_email(email, otp):
    """Send OTP email using AWS SES (no domain required)."""
    try:
        ses_client = boto3.client('ses', region_name='ap-south-1')

        # 🔥 IMPORTANT — Enter your verified Gmail / Yahoo / Outlook email
        sender_email = "sudhanangadi20@gmail.com"

        subject = "Password Reset OTP - Project Ticket Pro"
        body = f"""
        Hello,

        Your OTP to reset password is: {otp}

        This OTP is valid for 5 minutes.
        If you did not request a password reset, please ignore this email.

        Regards,
        Ticket Pro Support Team
        """

        ses_client.send_email(
            Source=sender_email,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
        return True
    except Exception as e:
        st.error(f"❌ Error sending OTP email: {e}")
        return False


# ================ FORGOT PASSWORD (Robust — uses st.session_state for OTP) ================
import random
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Attr

def send_otp_email(email, otp):
    """Send OTP email using AWS SES (no domain required)."""
    try:
        ses_client = boto3.client('ses', region_name='ap-south-1')

        # <-- REPLACE THIS with a Gmail/Yahoo/Outlook address you verified in SES
        sender_email = "sudhanrangadi@gmail.com"

        subject = "Password Reset OTP - Project Ticket Pro"
        body = f"""Hello,

Your OTP to reset password is: {otp}

This OTP is valid for 5 minutes.
If you did not request a password reset, ignore this email.

Regards,
Ticket Pro Support
"""
        ses_client.send_email(
            Source=sender_email,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
        return True
    except Exception as e:
        st.error(f"❌ Error sending OTP email: {e}")
        return False


def init_fp_state():
    """Ensure all keys exist in session_state with safe defaults."""
    if 'fp_stage' not in st.session_state:
        st.session_state.fp_stage = "enter_email"
    if 'fp_email' not in st.session_state:
        st.session_state.fp_email = ""
    if 'fp_otp' not in st.session_state:
        st.session_state.fp_otp = ""
    if 'fp_otp_expires' not in st.session_state:
        st.session_state.fp_otp_expires = None
    if 'fp_otp_verified' not in st.session_state:
        st.session_state.fp_otp_verified = False
    if 'fp_entered_otp_input' not in st.session_state:
        st.session_state.fp_entered_otp_input = ""
    if 'fp_new_pass_input' not in st.session_state:
        st.session_state.fp_new_pass_input = ""
    if 'fp_confirm_pass_input' not in st.session_state:
        st.session_state.fp_confirm_pass_input = ""


def forgot_password_page():
    init_fp_state()
    st.markdown("<h2>🔑 Forgot Password</h2>", unsafe_allow_html=True)

    stage = st.session_state.fp_stage

    # ------------------ STEP 1: Enter email & request OTP ------------------
    if stage == "enter_email":
        email = st.text_input("📧 Enter your registered email", value=st.session_state.fp_email, key="fp_email_input")
        if st.button("Send OTP", key="fp_send_otp"):
            # Validate email format quickly
            if not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email or ""):
                st.error("Please enter a valid email.")
                return

            # Check if this email exists in your users table
            try:
                response = users_table.scan(FilterExpression=Attr('email').eq(email))
            except Exception as e:
                st.error(f"Error checking user email: {e}")
                return

            items = response.get('Items', [])
            if not items:
                st.error("No account found with this email.")
                return

            # Generate OTP and store it in session_state (safer across reruns)
            otp = str(random.randint(100000, 999999))
            st.session_state.fp_email = email
            st.session_state.fp_otp = otp
            st.session_state.fp_otp_expires = datetime.now() + timedelta(minutes=5)
            st.session_state.fp_otp_verified = False
            st.session_state.fp_entered_otp_input = ""

            sent = send_otp_email(email, otp)
            if sent:
                st.success("✅ OTP sent to your email. It will expire in 5 minutes.")
                st.session_state.fp_stage = "verify_otp"
                st.rerun()
            else:
                # send_otp_email already shows error
                return

    # ------------------ STEP 2: Verify OTP ------------------
    elif stage == "verify_otp":
        st.markdown(f"An OTP was sent to **{st.session_state.fp_email}**")
        # Use a key so the input content persists across reruns
        entered_otp = st.text_input("🔢 Enter OTP", value=st.session_state.fp_entered_otp_input, key="fp_entered_otp_input")

        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("Verify OTP", key="fp_verify_otp_btn"):
                # guard: ensure OTP exists
                if not st.session_state.fp_otp:
                    st.error("No OTP found. Please request a new OTP.")
                    st.session_state.fp_stage = "enter_email"
                    st.experimental_rerun()

                # guard: expired
                if st.session_state.fp_otp_expires and datetime.now() > st.session_state.fp_otp_expires:
                    st.error("⏳ OTP expired. Please request a new OTP.")
                    # clear OTP state
                    st.session_state.fp_otp = ""
                    st.session_state.fp_otp_expires = None
                    st.session_state.fp_stage = "enter_email"
                    st.experimental_rerun()

                if entered_otp == st.session_state.fp_otp:
                    st.success("✔ OTP verified successfully!")
                    st.session_state.fp_otp_verified = True
                    st.session_state.fp_stage = "reset_password"
                    st.rerun()
                else:
                    st.error("❌ Incorrect OTP. Try again.")
        with col2:
            if st.button("Resend OTP", key="fp_resend_otp_btn"):
                # Rate-limiting could be added here; for now, just resend and reset timer
                otp = str(random.randint(100000, 999999))
                st.session_state.fp_otp = otp
                st.session_state.fp_otp_expires = datetime.now() + timedelta(minutes=5)
                sent = send_otp_email(st.session_state.fp_email, otp)
                if sent:
                    st.success("✅ New OTP sent. Check your email.")
                else:
                    st.error("❌ Failed to resend OTP.")

        if st.button("⬅ Back to Login", key="fp_back_to_login_1"):
            # Clear sensitive state
            st.session_state.fp_stage = "enter_email"
            st.session_state.fp_email = ""
            st.session_state.fp_otp = ""
            st.session_state.fp_otp_expires = None
            st.session_state.fp_otp_verified = False
            st.rerun()

    # ------------------ STEP 3: Reset password (only if OTP verified) ------------------
    elif stage == "reset_password":
        # Ensure the user actually verified OTP
        if not st.session_state.fp_otp_verified:
            st.error("Unauthorized access — please verify OTP first.")
            # reset to email stage
            st.session_state.fp_stage = "enter_email"
            st.rerun()

        st.markdown(f"Reset password for **{st.session_state.fp_email}**")
        new_pass = st.text_input("🔒 New password", type="password", value=st.session_state.fp_new_pass_input, key="fp_new_pass_input")
        confirm_pass = st.text_input("🔒 Confirm new password", type="password", value=st.session_state.fp_confirm_pass_input, key="fp_confirm_pass_input")

        if st.button("Update Password", key="fp_update_password_btn"):
            # Basic validations
            if not new_pass or not confirm_pass:
                st.error("Please fill in both password fields.")
                return
            if new_pass != confirm_pass:
                st.error("Passwords do not match.")
                return
            if not is_strong_password(new_pass):
                st.error("Password must be at least 8 chars and include uppercase, lowercase, digit and special char.")
                return

            # Find user by email and update hashed password
            try:
                response = users_table.scan(FilterExpression=Attr('email').eq(st.session_state.fp_email))
                items = response.get("Items", [])
                if not items:
                    st.error("User not found — aborting.")
                    # clear state to be safe
                    st.session_state.fp_stage = "enter_email"
                    st.session_state.fp_email = ""
                    st.session_state.fp_otp = ""
                    st.session_state.fp_otp_expires = None
                    st.session_state.fp_otp_verified = False
                    st.rerun()
                    return

                user = items[0]
                username = user['username']
                hashed = hash_password(new_pass)

                users_table.update_item(
                    Key={'username': username},
                    UpdateExpression="SET password = :p",
                    ExpressionAttributeValues={':p': hashed}
                )

                # Clear OTP and related state after success
                st.session_state.fp_otp = ""
                st.session_state.fp_otp_expires = None
                st.session_state.fp_otp_verified = False
                st.success("🎉 Password reset successful! Please log in.")
                st.session_state.fp_stage = "enter_email"
                st.session_state.view = "login"
                st.rerun()

            except Exception as e:
                st.error(f"Error updating password: {e}")
                return

        if st.button("⬅ Back to Login", key="fp_back_to_login_2"):
            # Clear sensitive state
            st.session_state.fp_stage = "enter_email"
            st.session_state.fp_email = ""
            st.session_state.fp_otp = ""
            st.session_state.fp_otp_expires = None
            st.session_state.fp_otp_verified = False
            st.session_state.fp_new_pass_input = ""
            st.session_state.fp_confirm_pass_input = ""
            st.rerun()

# --- Admin, User, and Support Pages (Unchanged Logic) ---
def admin_dashboard():
    st.title("🛍️ Admin Dashboard")
    st.markdown("### Upload a New Product")
    
    with st.form("product_upload_form", clear_on_submit=True):
        product_name = st.text_input("Product Name")
        price = st.number_input("Price", min_value=0.01, format="%.2f")
        uploaded_file = st.file_uploader("Upload Product Image", type=['jpg', 'png', 'jpeg'])
        
        submitted = st.form_submit_button("Add Product")
        
        if submitted:
            if not product_name or not uploaded_file:
                st.error("Please fill in all fields.")
            else:
                try:
                    product_id = str(uuid.uuid4())
                    image_path = f"products/{product_id}_{uploaded_file.name}"
                    
                    s3_client.upload_fileobj(uploaded_file, S3_BUCKET_NAME, image_path)
                    image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{image_path}"
                    
                    products_table.put_item(
                        Item={
                            'product_id': product_id,
                            'product_name': product_name,
                            'price': Decimal(str(price)),
                            'image_url': image_url
                        }
                    )
                    st.success("Product added successfully!")
                    st.rerun()
                except ClientError as e:
                    st.error(f"Error uploading product: {e.response['Error']['Message']}")

# --- NEW: Dialog Function for the Order Form ---
@st.dialog("Order Details", width="large")
def order_dialog(product):
    st.write(f"Please fill out your details to order **{product['product_name']}**.")
    
    with st.form(f"order_form_{product['product_id']}", clear_on_submit=True):
        name = st.text_input("Name", value=st.session_state.logged_in_as)
        phone = st.text_input("Phone Number")
        address = st.text_area("Address")
        
        submitted = st.form_submit_button("Submit Order")
        
        if submitted:
            if not name or not phone or not address:
                st.error("Please fill in all fields.")
            else:
                try:
                    order_id = str(uuid.uuid4())
                    orders_table.put_item(
                        Item={
                            'order_id': order_id,
                            'username': st.session_state.logged_in_as,
                            'product_id': product['product_id'],
                            'product_name': product['product_name'],
                            'price': Decimal(str(product['price'])),
                            'customer_name': name,
                            'customer_phone': phone,
                            'customer_address': address
                        }
                    )
                    st.success("Order placed successfully! We will contact you shortly.")
                    st.rerun()
                except ClientError as e:
                    st.error(f"Error placing order: {e.response['Error']['Message']}")


# --- Corrected user_dashboard function to use dynamic categories ---
def user_dashboard():
    st.title("🛒 Product Catalog")
    st.write("Browse all our amazing products!")
    
    # --- DYNAMICALLY FETCH CATEGORIES (Now correctly from products_table) ---
    DYNAMIC_CATEGORIES = get_product_categories()
    # Add an 'All Categories' option for the user
    FILTER_CATEGORIES = ["All Categories"] + DYNAMIC_CATEGORIES

    if not DYNAMIC_CATEGORIES:
        st.warning("No product categories found in the database. Please contact support.")
        
    # 1. Category Filter Dropdown
    selected_category = "All Categories"
    if FILTER_CATEGORIES:
        selected_category = st.selectbox(
            "**Filter by Category**", 
            options=FILTER_CATEGORIES,
            key="product_category_filter"
        )
    
    # 2. DynamoDB Query Logic
    all_products = []
    
    # Get products based on filter selection
    if selected_category == "All Categories":
        all_products = load_products() # Perform unfiltered scan
    else:
        try:
            # Load products for the selected category using the correct attribute: 'category_name'
            response = products_table.scan(
                # 💡 THE FIX IS HERE: Use 'category_name' instead of 'category'
                FilterExpression=Attr('category_name').eq(selected_category)
            )
            all_products = response['Items']
        except ClientError as e:
            st.error(f"Error filtering products: {e.response['Error']['Message']}")
            return

    # 3. Filter malformed items
    valid_products = []
    for product in all_products:
        product_id = product.get('product_id')
        product_name = product.get('product_name')
        product_price = product.get('price')

        # Also skip products that were unlinked (category_name/id removed)
        # Note: 'category_name' will be present if selected_category was used in the filter
        
        if product_id and product_name and product_price:
            valid_products.append(product)
        else:
            pass 

    # 4. Display Products
    if not valid_products:
        st.info(f"No valid products available in the '{selected_category}' category yet.")
    else:
        st.success(f"Showing {len(valid_products)} product(s) in {selected_category}.")
        
        num_products = len(valid_products) 
        num_cols = 3
        
        for i in range(0, num_products, num_cols):
            row_products = valid_products[i:i+num_cols]
            cols = st.columns(num_cols)
            
            for j, product in enumerate(row_products):
                with cols[j]:
                    with st.container(border=True):
                        # 💡 AND HERE: Use the correct attribute 'category_name' for display tag
                        category_tag = product.get('category_name', 'Uncategorized')
                        image_url = product.get('image_url')

                        st.markdown(f"<span style='font-size: 0.8em; color: #888;'>{category_tag}</span>", unsafe_allow_html=True)
                        
                        st.markdown(f"**{product['product_name']}**")
                        
                        if image_url:
                            st.image(image_url, use_container_width=True)
                        else:
                            st.warning("No Image Available") 
                            
                        # Ensure price is handled as Decimal for display formatting
                        price_val = product['price']
                        if isinstance(price_val, float):
                             price_val = Decimal(str(price_val))
                             
                        st.markdown(f"**Price:** ₹{price_val:.2f}")
                        
                        button_key = f"buy_button_{product['product_id']}" 
                        
                        if st.button("Buy Now", key=button_key, use_container_width=True):
                            order_dialog(product)
def view_orders():
    st.title("My Orders")
    username = st.session_state.logged_in_as 
    
    try:
        response = orders_table.scan(
            FilterExpression=Attr('username').eq(username)
        )

        orders = response.get('Items', [])
        
        if not orders:
            st.info("You haven't placed any orders yet.")
        else:
            st.write("Here are your past orders:")
            for order in orders:
                with st.container(border=True):
                    st.markdown(f"**Order ID:** `{order['order_id']}`")
                    st.markdown(f"**Product:** {order['product_name']}")
                    st.markdown(f"**Price:** ₹{order['price']:.2f}")
                    st.markdown(f"**Ordered by:** {order['customer_name']}")
                    st.markdown(f"**Shipping Address:** {order['customer_address']}")
                    st.markdown(f"**Phone:** {order['customer_phone']}")
                    
                    feedback_key = f"feedback_button_{order['order_id']}"
                    if st.button("Give Feedback", key=feedback_key):
                        st.session_state[f'show_feedback_form_{order["order_id"]}'] = True
                        st.rerun()

                    if st.session_state.get(f'show_feedback_form_{order["order_id"]}'):
                        with st.expander("Submit Your Feedback", expanded=True):
                            with st.form(f"feedback_form_{order['order_id']}", clear_on_submit=True):
                                user_info = get_user(username)
                                email = user_info.get('email', '') if user_info else ''

                                name = st.text_input("👤 Name", value=username, disabled=True)
                                email_input = st.text_input("📧 Email", value=email, disabled=True)
                                category = st.selectbox("📂 Category", ["Payment", "Order", "Technical"], key=f"category_{order['order_id']}")
                                desc = st.text_area("💬 Describe your issue")

                                submit_feedback_button = st.form_submit_button("📨 Submit Ticket")
                                
                                if submit_feedback_button:
                                    if not desc:
                                        st.error("Please describe your issue.")
                                    else:
                                        # Ensure lambda_client is available
                                        if not lambda_client:
                                            st.error("Lambda client is not initialized. Cannot submit ticket.")
                                            return
                                            
                                        payload = {
                                            "name": name,
                                            "email": email,
                                            "category": category,
                                            "description": desc,
                                            "order_id": order['order_id']
                                        }

                                        with st.spinner("⏳ Submitting your ticket..."):
                                            try:
                                                response = lambda_client.invoke(
                                                    FunctionName='ticket_pro',
                                                    InvocationType='RequestResponse',
                                                    Payload=json.dumps(payload),
                                                )
                                                result_raw = response['Payload'].read()
                                                result = json.loads(result_raw)
                                                
                                                # Lambda response structure check
                                                if result.get('status') == "success" or result.get('statusCode') == 200:
                                                    st.success(f"✅ Ticket submitted successfully!")
                                                    st.session_state[f'show_feedback_form_{order["order_id"]}'] = False
                                                    st.rerun()
                                                else:
                                                    st.error("❌ Ticket submission failed.")
                                                    st.json(result)
                                            except Exception as e:
                                                st.error(f"🚨 Error: {str(e)}")
                    st.divider()

    except ClientError as e:
        st.error(f"Error fetching orders: {e.response['Error']['Message']}")

# --- NEW FUNCTION FOR GENERAL TICKET SUBMISSION ---
def raise_general_ticket():
    st.title("🎫 Raise a New Support Ticket")
    st.markdown("Use this form for general inquiries, technical issues, or questions not related to a specific order.")
    
    username = st.session_state.logged_in_as
    user_info = get_user(username)
    
    if not user_info or 'email' not in user_info:
        st.error("Could not find email information for the logged-in user.")
        return
        
    user_email = user_info['email']

    with st.form("general_ticket_form", clear_on_submit=True):
        st.markdown("### Your Details")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            name = st.text_input("👤 Name", value=username, disabled=True)
        with col_g2:
            email_input = st.text_input("📧 Email", value=user_email, disabled=True)
            
        # st.markdown("### Issue Details")
        # Added a general category
        category = st.text_input("📂 Category (e.g., Technical, Billing, General)", value="General")
        description = st.text_area("💬 Describe your issue in detail", height=150)
        
        submit_general_ticket = st.form_submit_button("📨 Submit General Ticket", use_container_width=True)
        
        if submit_general_ticket:
            if not description:
                st.error("Please provide a detailed description of your issue.")
                return

            if not lambda_client:
                st.error("Lambda client is not initialized. Cannot submit ticket.")
                return

            # The order_id will be 'N/A' for general tickets
            payload = {
                "name": name,
                "email": user_email,
                "category": category,
                "description": description,
                "order_id": "N/A" 
            }

            with st.spinner("⏳ Submitting your general ticket..."):
                try:
                    response = lambda_client.invoke(
                        FunctionName='ticket_pro',
                        InvocationType='RequestResponse',
                        Payload=json.dumps(payload),
                    )
                    result_raw = response['Payload'].read()
                    result = json.loads(result_raw)
                    
                    if result.get('status') == "success" or result.get('statusCode') == 200:
                        st.success(f"✅ General ticket submitted successfully! Check 'My Tickets' to track its status.")
                        # Optional: redirect or clear form by rerunning
                        st.session_state.view = 'track_tickets'
                        st.rerun()
                    else:
                        st.error("❌ General ticket submission failed.")
                        st.json(result)
                except Exception as e:
                    st.error(f"🚨 Error: {str(e)}")

# --- END NEW FUNCTION ---

def track_tickets():
    st.title("My Support Tickets")
    username = st.session_state.logged_in_as
    user_info = get_user(username)
    
    if not user_info or 'email' not in user_info:
        st.error("Could not find email information for the logged-in user.")
        return

    user_email = user_info['email']
    
    try:
        response = support_table.scan(
            FilterExpression=Attr('email').eq(user_email)
        )
        tickets = response.get('Items', [])
        
        if not tickets:
            st.info("You have not submitted any tickets yet.")
        else:
            st.write("Here are the tickets you have raised:")
            sorted_tickets = sorted(tickets, key=lambda x: x.get('timestamp', ''), reverse=True)
            for ticket in sorted_tickets:
                with st.container(border=True):
                    st.markdown(f"**Ticket ID:** `{ticket['ticket_id']}`")
                    st.markdown(f"**Order ID:** `{ticket.get('order_id', 'N/A')}`") # Use .get with default 'N/A'
                    st.markdown(f"**Category:** {ticket['category']}")
                    st.markdown(f"**Status:** `{ticket['status']}`")
                    st.markdown(f"**Priority:** `{ticket['priority']}`")
                    st.markdown(f"**Submitted on:** {ticket.get('timestamp', 'N/A')}")
                    st.divider()
                    st.expander("View Issue").markdown(f"**Description:** {ticket['description']}")
    
    except ClientError as e:
        st.error(f"Error fetching tickets: {e.response['Error']['Message']}")
        
# --- PUBLIC VIEW (Landing Page) ---
# --- PUBLIC VIEW (Enhanced Landing Page) ---
def public_view():
    # Ensure wide layout
    st.set_page_config(layout="wide")
    load_custom_css() # Ensure custom CSS is loaded

    # --- 1. HERO SECTION: Title and Core Value Proposition ---
    st.markdown("<div style='text-align: center; padding-top: 60px;'>", unsafe_allow_html=True)
    st.markdown("<h1>Project Ticket Pro</h1>", unsafe_allow_html=True)
    st.markdown("<h3>Intelligent Prioritization: Stop firefighting, start solving the critical issues first.</h3>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # --- 2. PROBLEM/SOLUTION SECTION (Centralized Container) ---
    col_l, col_center, col_r = st.columns([1, 4, 1])

    with col_center:
        st.markdown("<h2 style='text-align: center; color: #1a4f78; margin-top: 40px;'>The AI-Driven Customer Support Solution</h2>", unsafe_allow_html=True)
        st.divider()
        
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #ffffff, #f0f8ff); 
                padding: 40px; 
                border-radius: 20px; 
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                border: 1px solid #cceeff;
                margin-bottom: 30px;
                animation: fadeIn 2s ease-out;
            ">
                <h4 style="text-align: center; color: #cc3300; font-size: 1.5rem; font-weight: 600;">The Problem: Critical issues get lost.</h4>
                <p style="text-align: center; font-size: 1.1rem; color: #555;">
                Traditional support systems struggle with manual sorting. A highly urgent complaint from a frustrated user often gets buried beneath low-priority queries, leading to slow response times and reputation damage.
                </p>
                <hr style="margin: 20px 0;">
                <h4 style="text-align: center; color: #007bff; font-size: 1.5rem; font-weight: 600;">The Solution: Automated, Intelligent Prioritization.</h4>
                <p style="text-align: center; font-size: 1.1rem; color: #555;">
                Project Ticket Pro leverages AWS Comprehend to analyze ticket sentiment, instantly assigning a High, Medium, or Low priority tag. Our system ensures your team addresses the most critical issues—like "Payment Errors" with "NEGATIVE" sentiment—in seconds, not hours.
                </p>
            </div>
            """, unsafe_allow_html=True
        )

    # --- 3. KEY FEATURES SECTION (Grid Layout) ---
    st.markdown("<h2 style='text-align: center; color: #1a4f78; margin-top: 30px;'>Powered by Modern Serverless Architecture</h2>", unsafe_allow_html=True)
    st.markdown("<div style='padding: 20px 80px;'>", unsafe_allow_html=True)

    # Define feature content
    features = [
        {"icon": "🧠", "title": "Intelligent Prioritization", "desc": "Uses AWS Comprehend for Sentiment Analysis (Negative, Neutral, Positive) and custom business logic to assign High, Medium, or Low priority."},
        {"icon": "⚡", "title": "Automated SNS Alerts", "desc": "High-priority tickets instantly trigger an email notification to the Admin team via AWS SNS, ensuring zero critical misses."},
        {"icon": "☁️", "title": "Serverless & Scalable", "desc": "Built on AWS Lambda, DynamoDB, and S3, the infrastructure handles massive ticket volumes without manual scaling or performance hit."},
        {"icon": "🛡️", "title": "Secure Dual Portals", "desc": "Separate, secure Streamlit interfaces for User submission and Admin management, secured with bcrypt password hashing."},
    ]
    
    # Create columns for the features
    cols_features = st.columns(4)
    for i, feature in enumerate(features):
        with cols_features[i]:
            st.markdown(f"<div class='feature-icon'>{feature['icon']}</div>", unsafe_allow_html=True)
            st.markdown(f"<h4>{feature['title']}</h4>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size: 0.95rem; color: #666;'>{feature['desc']}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


    # --- 4. CALL TO ACTION (CTA) BUTTONS ---
    
    st.markdown("<h2 style='text-align: center; color: #1a4f78; margin-top: 50px;'>Ready to Streamline Your Support?</h2>", unsafe_allow_html=True)

    col_l_cta, col_btn_1, col_btn_2, col_r_cta = st.columns([1.5, 1, 1, 1.5])
    
    with col_btn_1:
        st.markdown("<div class='cta-button'>", unsafe_allow_html=True)
        if st.button("🚪 Log In to User Portal", key="public_login", use_container_width=True):
            st.session_state.view = 'login'
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
            
    with col_btn_2:
        st.markdown("<div class='cta-button'>", unsafe_allow_html=True)
        if st.button("📝 Create New Account", key="public_register", use_container_width=True):
            st.session_state.view = 'register'
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Small spacer at the bottom
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
# --- Main App Logic ---
main_menu()

if st.session_state.logged_in_as == 'public' and st.session_state.view == 'public':
    public_view()
elif st.session_state.view == 'admin_dashboard' and st.session_state.logged_in_as == 'admin':
    admin_dashboard()
elif st.session_state.view == 'user_dashboard' and st.session_state.logged_in_as != 'public':
    user_dashboard()
elif st.session_state.view == 'login':
    login_page()
elif st.session_state.view == 'register':
    register_page()
elif st.session_state.view == 'forgot_password':
    forgot_password_page()
elif st.session_state.view == 'view_orders' and st.session_state.logged_in_as != 'public':
    view_orders()
# --- NEW VIEW ROUTE ---
elif st.session_state.view == 'raise_general_ticket' and st.session_state.logged_in_as != 'public':
    raise_general_ticket()
# --- END NEW VIEW ROUTE ---
elif st.session_state.view == 'track_tickets' and st.session_state.logged_in_as != 'public':
    track_tickets()
