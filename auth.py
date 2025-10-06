from functools import wraps
from flask import session, redirect, url_for, flash
import os

def load_credentials():
    """Load credentials from credentials.txt file"""
    credentials = {}
    
    # Check if credentials.txt exists
    if not os.path.exists('credentials.txt'):
        print("Warning: credentials.txt not found!")
        return credentials
    
    try:
        with open('credentials.txt', 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Expected format: username:password
                if ':' in line:
                    username, password = line.split(':', 1)
                    credentials[username.strip()] = password.strip()
    except Exception as e:
        print(f"Error reading credentials.txt: {e}")
    
    return credentials

def authenticate_user(username, password):
    """Authenticate a user with username and password"""
    credentials = load_credentials()
    
    # Check if username exists and password matches
    if username in credentials and credentials[username] == password:
        return {'username': username}
    
    return None

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function