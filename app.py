from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import requests
import json
from datetime import datetime, timedelta
import sqlite3
import uuid
import os
from collections import defaultdict, Counter
import plotly.graph_objs as go
import plotly.utils

# Import authentication module
from auth import authenticate_user, login_required

# Import the visual processor
try:
    from visual import process_visual_response
    VISUAL_PROCESSING_ENABLED = True
except ImportError:
    print("Warning: visual.py not found. Visual KPI processing disabled.")
    VISUAL_PROCESSING_ENABLED = False

app = Flask(__name__)

# PRODUCTION CHANGE: Use environment variable or generate random key
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Session configuration - session will expire when browser closes
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# PRODUCTION CHANGE: Use environment variables for configuration
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', "http://localhost:5678/webhook/1381ce10-c93f-4d4f-a56a-b8755e2877ca")
DATABASE_PATH = os.environ.get('DATABASE_PATH', '/qond/qad-assistant/chat_analytics.db')

# PRODUCTION CHANGE: Ensure database directory exists
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

# Initialize database
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        user_message TEXT,
        bot_response TEXT,
        message_type TEXT,
        intent TEXT,
        query_category TEXT,
        has_requisition_offer BOOLEAN,
        requisition_created BOOLEAN,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        action_type TEXT,
        action_details TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def categorize_query(user_message):
    """Categorize user query based on keywords"""
    message_lower = user_message.lower()
    
    inventory_keywords = ['inventory', 'stock', 'low stock', 'reorder', 'shortage', 'order']
    purchase_keywords = ['purchase', 'buy', 'supplier', 'vendor', 'requisition']
    report_keywords = ['report', 'analytics', 'data', 'show', 'list']
    
    if any(keyword in message_lower for keyword in inventory_keywords):
        return 'inventory'
    elif any(keyword in message_lower for keyword in purchase_keywords):
        return 'purchase'
    elif any(keyword in message_lower for keyword in report_keywords):
        return 'reporting'
    else:
        return 'general'

def log_chat_message(session_id, user_message, bot_response, intent='normal_query'):
    """Log chat message to database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Ensure session exists
    cursor.execute('INSERT OR IGNORE INTO chat_sessions (session_id) VALUES (?)', (session_id,))
    
    query_category = categorize_query(user_message)
    has_requisition_offer = 'Would you like me to create purchase requisitions' in bot_response
    requisition_created = 'Requisition Created' in bot_response
    
    cursor.execute('''
    INSERT INTO chat_messages 
    (session_id, user_message, bot_response, message_type, intent, query_category, 
     has_requisition_offer, requisition_created)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, user_message, bot_response, 'chat', intent, query_category, 
          has_requisition_offer, requisition_created))
    
    conn.commit()
    conn.close()

def log_user_action(session_id, action_type, action_details):
    """Log user actions"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO user_actions (session_id, action_type, action_details)
    VALUES (?, ?, ?)
    ''', (session_id, action_type, action_details))
    
    conn.commit()
    conn.close()

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect to home
    if 'user' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = authenticate_user(username, password)
        
        if user:
            session['user'] = user
            session.permanent = False  # Session expires when browser closes
            
            # Log login action
            log_user_action(session.get('session_id', str(uuid.uuid4())), 'user_login', f"User: {username}")
            
            flash(f'Welcome, {username}!', 'success')
            
            # Redirect to home
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials. Please check your User ID and Password.', 'error')
            log_user_action('anonymous', 'failed_login', f"Attempted username: {username}")
    
    return render_template('login.html')

# ==================== PROTECTED ROUTES ====================

@app.route('/')
@login_required
def index():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return render_template('index.html')

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@app.route('/visual_chat')
@login_required
def visual_chat():
    return render_template('visual_chat.html')

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    try:
        user_message = request.json.get('message', '')
        session_id = session.get('session_id', str(uuid.uuid4()))
        is_visual_request = request.json.get('visual', False)

        # Send to n8n webhook
        payload = {
            'chatInput': user_message,
            'sessionId': session_id
        }
        
        # PRODUCTION CHANGE: Increased timeout and better error handling
        response = requests.post(WEBHOOK_URL, json=payload, timeout=120)

        normalized_table = []
        normalized_message = ''

        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    normalized_table = data.get('tableData', []) or []
                    normalized_message = data.get('chatMessage', '') or data.get('message', '') or data.get('response', '') or ''
                elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    first = data[0]
                    normalized_table = first.get('tableData', []) or []
                    normalized_message = first.get('chatMessage', '') or first.get('message', '') or first.get('response', '') or ''
                else:
                    normalized_message = json.dumps(data, ensure_ascii=False)
            except Exception as e:
                print(f"Error parsing JSON response: {e}")
                normalized_message = response.text or ''
        else:
            normalized_message = f"Sorry, an error occurred while contacting the workflow. Status: {response.status_code}"

        bot_response = normalized_message
        table_data = normalized_table

        # Process with Gemini for visual chat requests
        kpi_data = None
        if is_visual_request and VISUAL_PROCESSING_ENABLED:
            try:
                kpi_data = process_visual_response(bot_response, table_data)
            except Exception as e:
                print(f"Error processing visual KPIs: {e}")

        # Log the interaction
        log_chat_message(session_id, user_message, bot_response)
        log_user_action(session_id, 'message_sent', f"Query: {user_message[:100]}...")

        response_data = {
            'response': bot_response,
            'tableData': table_data,
            'chatMessage': bot_response,
            'session_id': session_id
        }

        if kpi_data:
            response_data['kpiData'] = kpi_data

        return jsonify(response_data)

    except Exception as e:
        print("Error in /api/chat:", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/overview')
@login_required
def analytics_overview():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM chat_messages')
    total_queries = cursor.fetchone()[0]
    
    cursor.execute('''
    SELECT COUNT(*) FROM chat_messages 
    WHERE DATE(timestamp) = DATE('now')
    ''')
    queries_today = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM chat_messages WHERE requisition_created = 1')
    total_requisitions = cursor.fetchone()[0]
    
    cursor.execute('''
    SELECT COUNT(DISTINCT session_id) FROM chat_messages 
    WHERE timestamp > datetime('now', '-24 hours')
    ''')
    active_sessions = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_queries': total_queries,
        'queries_today': queries_today,
        'total_requisitions': total_requisitions,
        'active_sessions': active_sessions
    })

@app.route('/api/analytics/query_categories')
@login_required
def query_categories():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT query_category, COUNT(*) as count
    FROM chat_messages
    GROUP BY query_category
    ''')
    
    data = cursor.fetchall()
    conn.close()
    
    categories = [row[0] for row in data]
    counts = [row[1] for row in data]
    
    fig = go.Figure(data=[go.Pie(labels=categories, values=counts, hole=0.3)])
    fig.update_layout(title="Query Categories Distribution")
    
    return jsonify(json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig)))

@app.route('/api/analytics/daily_activity')
@login_required
def daily_activity():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT DATE(timestamp) as date, COUNT(*) as count
    FROM chat_messages
    WHERE timestamp > datetime('now', '-30 days')
    GROUP BY DATE(timestamp)
    ORDER BY date
    ''')
    
    data = cursor.fetchall()
    conn.close()
    
    dates = [row[0] for row in data]
    counts = [row[1] for row in data]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=counts, mode='lines+markers', name='Daily Queries'))
    fig.update_layout(title="Daily Query Activity (Last 30 Days)", xaxis_title="Date", yaxis_title="Number of Queries")
    
    return jsonify(json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig)))

@app.route('/api/analytics/requisition_trends')
@login_required
def requisition_trends():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT DATE(timestamp) as date, 
           SUM(CASE WHEN has_requisition_offer = 1 THEN 1 ELSE 0 END) as offers,
           SUM(CASE WHEN requisition_created = 1 THEN 1 ELSE 0 END) as created
    FROM chat_messages
    WHERE timestamp > datetime('now', '-30 days')
    GROUP BY DATE(timestamp)
    ORDER BY date
    ''')
    
    data = cursor.fetchall()
    conn.close()
    
    dates = [row[0] for row in data]
    offers = [row[1] for row in data]
    created = [row[2] for row in data]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=dates, y=offers, name='Requisition Offers'))
    fig.add_trace(go.Bar(x=dates, y=created, name='Requisitions Created'))
    fig.update_layout(title="Requisition Activity Trends", xaxis_title="Date", yaxis_title="Count")
    
    return jsonify(json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig)))

@app.route('/api/chat/clear', methods=['POST'])
@login_required
def clear_chat():
    try:
        session_id = session.get('session_id')
        if session_id:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))
            conn.commit()
            conn.close()
            return jsonify({'status': 'success'})
    except Exception as e:
        print("Error clearing chat:", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/top_queries')
@login_required
def top_queries():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT user_message, COUNT(*) as count
    FROM chat_messages
    GROUP BY user_message
    ORDER BY count DESC
    LIMIT 10
    ''')
    
    data = cursor.fetchall()
    conn.close()
    
    return jsonify([{'query': row[0][:100] + '...' if len(row[0]) > 100 else row[0], 'count': row[1]} for row in data])

# PRODUCTION CHANGE: Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    # PRODUCTION CHANGE: Don't run in debug mode in production
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'on']
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))