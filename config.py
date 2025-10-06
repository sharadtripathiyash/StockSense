import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-in-production'
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL') or 'http://localhost:5678/webhook/1381ce10-c93f-4d4f-a56a-b8755e2877ca'
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or 'chat_analytics.db'
    
    # Analytics settings
    AUTO_REFRESH_INTERVAL = 300000  # 5 minutes in milliseconds
    MAX_CHAT_HISTORY = 1000  # Maximum messages to store per session
    
    # Chart colors
    CHART_COLORS = [
        '#667eea', '#764ba2', '#f093fb', '#f5576c',
        '#4facfe', '#00f2fe', '#43e97b', '#38f9d7'
    ]