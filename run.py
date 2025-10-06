from flask import Flask
from app import app
import os

if __name__ == '__main__':
    # Create templates directory structure
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("🚀 Starting QAD ERP Chat Dashboard...")
    print("📊 Analytics available at: http://localhost:5000/analytics")
    print("💬 Chat interface at: http://localhost:5000/")
    print("⚙️  Make sure to update WEBHOOK_URL in the configuration!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)