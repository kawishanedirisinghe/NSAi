# Enhanced AI Assistant Web Application
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import mimetypes
import os
import time
from pathlib import Path
import asyncio
import queue
from app.agent.manus import Manus
from app.logger import logger, log_queue
from app.config import config as app_config
import threading
import toml
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import json
import uuid
from werkzeug.utils import secure_filename
import shutil
import hashlib
import secrets
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['WORKSPACE'] = 'workspace'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['CHAT_HISTORY_FILE'] = 'chat_history.json'
app.config['USER_DATA_FILE'] = 'user_data.json'
app.config['ADMIN_DATA_FILE'] = 'admin_data.json'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Create necessary directories
os.makedirs(app.config['WORKSPACE'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('user_sessions', exist_ok=True)
os.makedirs('admin_data', exist_ok=True)

# Global variables
running_tasks = {}
user_sessions = {}
admin_users = {}
chat_rooms = {}

# Load configuration
config = toml.load('config/config.toml')

# User Management System
class UserManager:
    def __init__(self):
        self.users_file = app.config['USER_DATA_FILE']
        self.users = self.load_users()
        self.sessions = {}
    
    def load_users(self):
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=2)
    
    def create_user(self, username, password, email=None, role='user'):
        if username in self.users:
            return False, "Username already exists"
        
        salt = secrets.token_hex(16)
        hashed_password = hashlib.sha256((password + salt).encode()).hexdigest()
        
        self.users[username] = {
            'password_hash': hashed_password,
            'salt': salt,
            'email': email,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'chat_history': [],
            'preferences': {
                'theme': 'dark',
                'language': 'en',
                'notifications': True
            }
        }
        self.save_users()
        return True, "User created successfully"
    
    def authenticate_user(self, username, password):
        if username not in self.users:
            return False, "Invalid username or password"
        
        user = self.users[username]
        hashed_password = hashlib.sha256((password + user['salt']).encode()).hexdigest()
        
        if hashed_password == user['password_hash']:
            user['last_login'] = datetime.now().isoformat()
            self.save_users()
            return True, "Authentication successful"
        
        return False, "Invalid username or password"
    
    def get_user(self, username):
        return self.users.get(username)
    
    def update_user_preferences(self, username, preferences):
        if username in self.users:
            self.users[username]['preferences'].update(preferences)
            self.save_users()
            return True
        return False

# Admin Management System
class AdminManager:
    def __init__(self):
        self.admin_file = app.config['ADMIN_DATA_FILE']
        self.admins = self.load_admins()
    
    def load_admins(self):
        if os.path.exists(self.admin_file):
            try:
                with open(self.admin_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_admins(self):
        with open(self.admin_file, 'w') as f:
            json.dump(self.admins, f, indent=2)
    
    def create_admin(self, username, password, email=None):
        if username in self.admins:
            return False, "Admin username already exists"
        
        salt = secrets.token_hex(16)
        hashed_password = hashlib.sha256((password + salt).encode()).hexdigest()
        
        self.admins[username] = {
            'password_hash': hashed_password,
            'salt': salt,
            'email': email,
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'permissions': ['user_management', 'system_monitoring', 'chat_moderation']
        }
        self.save_admins()
        return True, "Admin created successfully"
    
    def authenticate_admin(self, username, password):
        if username not in self.admins:
            return False, "Invalid admin credentials"
        
        admin = self.admins[username]
        hashed_password = hashlib.sha256((password + admin['salt']).encode()).hexdigest()
        
        if hashed_password == admin['password_hash']:
            admin['last_login'] = datetime.now().isoformat()
            self.save_admins()
            return True, "Admin authentication successful"
        
        return False, "Invalid admin credentials"

# Initialize managers
user_manager = UserManager()
admin_manager = AdminManager()

# Advanced API Key Management System
class AdvancedAPIKeyManager:
    def __init__(self, api_keys_config):
        self.api_keys = []
        self.usage_stats = {}
        self.disabled_keys = {}  # {key: disabled_until_timestamp}
        self.failure_counts = {}  # {key: consecutive_failures}
        self.last_used = {}  # {key: last_used_timestamp}

        # Initialize API keys from config
        for key_config in api_keys_config:
            self.api_keys.append({
                'api_key': key_config['api_key'],
                'name': key_config.get('name', f"Key_{key_config['api_key'][:8]}"),
                'max_requests_per_minute': key_config.get('max_requests_per_minute', 5),
                'max_requests_per_hour': key_config.get('max_requests_per_hour', 100),
                'max_requests_per_day': key_config.get('max_requests_per_day', 100),
                'priority': key_config.get('priority', 1),
                'enabled': key_config.get('enabled', True)
            })

            # Initialize stats for each key
            key = key_config['api_key']
            self.usage_stats[key] = {
                'requests_this_minute': [],
                'requests_this_hour': [],
                'requests_this_day': [],
                'total_requests': 0
            }
            self.failure_counts[key] = 0
            self.last_used[key] = None

        logger.info(f"Initialized advanced API key manager with {len(self.api_keys)} keys")

    def _clean_old_usage_data(self, api_key: str):
        """Clean old usage data for accurate rate limiting"""
        current_time = time.time()
        stats = self.usage_stats[api_key]

        # Clean minute data (older than 60 seconds)
        stats['requests_this_minute'] = [
            t for t in stats['requests_this_minute'] 
            if current_time - t < 60
        ]

        # Clean hour data (older than 3600 seconds)
        stats['requests_this_hour'] = [
            t for t in stats['requests_this_hour'] 
            if current_time - t < 3600
        ]

        # Clean day data (older than 86400 seconds)
        stats['requests_this_day'] = [
            t for t in stats['requests_this_day'] 
            if current_time - t < 86400
        ]

    def _is_key_available(self, key_config: dict) -> bool:
        """Check if an API key is available for use"""
        api_key = key_config['api_key']
        current_time = time.time()

        # Check if key is disabled
        if api_key in self.disabled_keys:
            if current_time < self.disabled_keys[api_key]:
                return False
            else:
                del self.disabled_keys[api_key]

        # Check rate limits
        self._clean_old_usage_data(api_key)
        stats = self.usage_stats[api_key]

        if (len(stats['requests_this_minute']) >= key_config['max_requests_per_minute'] or
            len(stats['requests_this_hour']) >= key_config['max_requests_per_hour'] or
            len(stats['requests_this_day']) >= key_config['max_requests_per_day']):
            return False

        return True

    def _disable_key_for_rate_limit(self, api_key: str, key_name: str):
        """Disable a key temporarily due to rate limiting"""
        disable_duration = 60  # 1 minute
        self.disabled_keys[api_key] = time.time() + disable_duration
        logger.warning(f"API key '{key_name}' disabled for {disable_duration} seconds due to rate limiting")

    def _calculate_key_score(self, key_config: dict) -> float:
        """Calculate a score for key selection (higher is better)"""
        api_key = key_config['api_key']
        current_time = time.time()
        
        # Base score from priority
        score = key_config['priority']
        
        # Bonus for keys that haven't been used recently
        if api_key in self.last_used:
            time_since_last_use = current_time - self.last_used[api_key]
            score += min(time_since_last_use / 3600, 10)  # Max 10 bonus points
        
        # Penalty for recent failures
        if api_key in self.failure_counts:
            score -= self.failure_counts[api_key] * 2
        
        return score

    def get_available_api_key(self, use_random: bool = True) -> Optional[Tuple[str, dict]]:
        """Get the best available API key"""
        available_keys = [
            (key_config['api_key'], key_config) 
            for key_config in self.api_keys 
            if key_config['enabled'] and self._is_key_available(key_config)
        ]

        if not available_keys:
            return None

        if use_random and len(available_keys) > 1:
            # Random selection with weighted scoring
            scored_keys = [(key, config, self._calculate_key_score(config)) for key, config in available_keys]
            scored_keys.sort(key=lambda x: x[2], reverse=True)
            
            # Select from top 3 keys randomly
            top_keys = scored_keys[:min(3, len(scored_keys))]
            selected_key, selected_config, _ = random.choice(top_keys)
        else:
            # Select the highest scoring key
            scored_keys = [(key, config, self._calculate_key_score(config)) for key, config in available_keys]
            scored_keys.sort(key=lambda x: x[2], reverse=True)
            selected_key, selected_config, _ = scored_keys[0]

        return selected_key, selected_config

    def record_successful_request(self, api_key: str):
        """Record a successful API request"""
        current_time = time.time()
        
        if api_key in self.usage_stats:
            stats = self.usage_stats[api_key]
            stats['requests_this_minute'].append(current_time)
            stats['requests_this_hour'].append(current_time)
            stats['requests_this_day'].append(current_time)
            stats['total_requests'] += 1
        
        self.last_used[api_key] = current_time
        
        # Reset failure count on success
        if api_key in self.failure_counts:
            self.failure_counts[api_key] = 0

    def record_rate_limit_error(self, api_key: str, key_name: str):
        """Record a rate limit error"""
        self._disable_key_for_rate_limit(api_key, key_name)
        logger.warning(f"Rate limit error for API key '{key_name}'")

    def record_failure(self, api_key: str, key_name: str, error_type: str = "unknown"):
        """Record an API failure"""
        if api_key in self.failure_counts:
            self.failure_counts[api_key] += 1
        else:
            self.failure_counts[api_key] = 1
        
        logger.error(f"API failure for key '{key_name}': {error_type}")

    def get_keys_status(self) -> List[Dict]:
        """Get status of all API keys"""
        status_list = []
        current_time = time.time()
        
        for key_config in self.api_keys:
            api_key = key_config['api_key']
            stats = self.usage_stats.get(api_key, {})
            
            # Clean old data
            self._clean_old_usage_data(api_key)
            
            status = {
                'name': key_config['name'],
                'enabled': key_config['enabled'],
                'priority': key_config['priority'],
                'is_available': self._is_key_available(key_config),
                'requests_this_minute': len(stats.get('requests_this_minute', [])),
                'requests_this_hour': len(stats.get('requests_this_hour', [])),
                'requests_this_day': len(stats.get('requests_this_day', [])),
                'total_requests': stats.get('total_requests', 0),
                'failure_count': self.failure_counts.get(api_key, 0),
                'is_disabled': api_key in self.disabled_keys,
                'disabled_until': self.disabled_keys.get(api_key, 0),
                'last_used': self.last_used.get(api_key, 0)
            }
            
            status_list.append(status)
        
        return status_list

# Initialize API key manager
api_key_manager = AdvancedAPIKeyManager(config.get('api_keys', []))

# Authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Utility functions
def get_files_pathlib(root_dir):
    files = []
    for path in Path(root_dir).rglob('*'):
        if path.is_file():
            files.append(str(path))
    return files

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        success, message = user_manager.authenticate_user(username, password)
        if success:
            session['user_id'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error=message)
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        success, message = user_manager.create_user(username, password, email)
        if success:
            return redirect(url_for('login'))
        else:
            return render_template('register.html', error=message)
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user = user_manager.get_user(session['user_id'])
    return render_template('dashboard.html', user=user)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        success, message = admin_manager.authenticate_admin(username, password)
        if success:
            session['admin_id'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error=message)
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    admin = admin_manager.admins[session['admin_id']]
    users = user_manager.users
    api_status = api_key_manager.get_keys_status()
    return render_template('admin_dashboard.html', admin=admin, users=users, api_status=api_status)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/file/<filename>')
def file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            response = Response(content, mimetype=mime_type)
            response.headers['Content-Disposition'] = f'inline; filename={filename}'
            return response
        else:
            return "File not found", 404
    except Exception as e:
        logger.error(f"Error serving file {filename}: {str(e)}")
        return "Error serving file", 500

@app.route('/api/keys/status')
def api_keys_status():
    return jsonify(api_key_manager.get_keys_status())

@app.route('/api/agents')
def get_agents():
    try:
        agents = []
        for agent_name, agent_config in config.get('agents', {}).items():
            agent_info = {
                'name': agent_name,
                'description': agent_config.get('description', ''),
                'model': agent_config.get('model', ''),
                'enabled': agent_config.get('enabled', True),
                'capabilities': agent_config.get('capabilities', [])
            }
            agents.append(agent_info)
        
        return jsonify(agents)
    except Exception as e:
        logger.error(f"Error getting agents: {str(e)}")
        return jsonify([])

@app.route('/api/tasks')
def get_tasks():
    try:
        tasks = []
        for task_id, task_info in running_tasks.items():
            task_data = {
                'id': task_id,
                'status': task_info.get('status', 'unknown'),
                'start_time': task_info.get('start_time', ''),
                'user': task_info.get('user', ''),
                'type': task_info.get('type', ''),
                'progress': task_info.get('progress', 0)
            }
            tasks.append(task_data)
        
        return jsonify(tasks)
    except Exception as e:
        logger.error(f"Error getting tasks: {str(e)}")
        return jsonify([])

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'py', 'js', 'html', 'css', 'json', 'xml', 'csv'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_chat_history(chat_data):
    try:
        history_file = app.config['CHAT_HISTORY_FILE']
        history = []
        
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        chat_data['timestamp'] = datetime.now().isoformat()
        history.append(chat_data)
        
        # Keep only last 1000 conversations
        if len(history) > 1000:
            history = history[-1000:]
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        logger.error(f"Error saving chat history: {str(e)}")
        return False

def load_chat_history():
    try:
        history_file = app.config['CHAT_HISTORY_FILE']
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error loading chat history: {str(e)}")
        return []

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            file_info = {
                'filename': filename,
                'original_name': file.filename,
                'size': os.path.getsize(file_path),
                'upload_time': datetime.now().isoformat(),
                'url': url_for('file', filename=filename)
            }
            
            return jsonify({'success': True, 'file': file_info})
        else:
            return jsonify({'error': 'File type not allowed'}), 400
    
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return jsonify({'error': 'Upload failed'}), 500

@app.route('/api/files')
def get_uploaded_files():
    try:
        files = []
        upload_dir = app.config['UPLOAD_FOLDER']
        
        if os.path.exists(upload_dir):
            for filename in os.listdir(upload_dir):
                file_path = os.path.join(upload_dir, filename)
                if os.path.isfile(file_path):
                    file_info = {
                        'filename': filename,
                        'size': os.path.getsize(file_path),
                        'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                        'url': url_for('file', filename=filename)
                    }
                    files.append(file_info)
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)
        return jsonify(files)
    
    except Exception as e:
        logger.error(f"Error getting uploaded files: {str(e)}")
        return jsonify([])

@app.route('/api/chat-history')
def get_chat_history():
    try:
        history = load_chat_history()
        return jsonify(history)
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        return jsonify([])

@app.route('/api/stop-task', methods=['POST'])
def stop_task():
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        
        if task_id in running_tasks:
            task_info = running_tasks[task_id]
            if 'thread' in task_info and task_info['thread'].is_alive():
                # Signal the thread to stop
                task_info['stop_flag'] = True
                task_info['status'] = 'stopping'
            
            return jsonify({'success': True, 'message': 'Task stop signal sent'})
        else:
            return jsonify({'error': 'Task not found'}), 404
    
    except Exception as e:
        logger.error(f"Error stopping task: {str(e)}")
        return jsonify({'error': 'Failed to stop task'}), 500

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit('status', {'message': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")
    if request.sid in user_sessions:
        del user_sessions[request.sid]

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    if room:
        join_room(room)
        emit('status', {'message': f'Joined room: {room}'})

@socketio.on('leave_room')
def handle_leave_room(data):
    room = data.get('room')
    if room:
        leave_room(room)
        emit('status', {'message': f'Left room: {room}'})

@socketio.on('chat_message')
def handle_chat_message(data):
    try:
        message = data.get('message', '')
        user_id = data.get('user_id', 'anonymous')
        room = data.get('room', 'general')
        
        # Process message with AI
        task_id = str(uuid.uuid4())
        running_tasks[task_id] = {
            'status': 'running',
            'start_time': datetime.now().isoformat(),
            'user': user_id,
            'type': 'chat',
            'progress': 0
        }
        
        # Start AI processing in background
        def process_message():
            try:
                # Initialize Manus agent
                manus = Manus()
                
                # Process the message
                response = asyncio.run(manus.run(message))
                
                # Update task status
                running_tasks[task_id]['status'] = 'completed'
                running_tasks[task_id]['progress'] = 100
                
                # Emit response to room
                socketio.emit('ai_response', {
                    'task_id': task_id,
                    'response': response,
                    'user_id': user_id,
                    'timestamp': datetime.now().isoformat()
                }, room=room)
                
                # Save to chat history
                chat_data = {
                    'user_id': user_id,
                    'message': message,
                    'response': response,
                    'room': room
                }
                save_chat_history(chat_data)
                
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                running_tasks[task_id]['status'] = 'error'
                socketio.emit('ai_response', {
                    'task_id': task_id,
                    'error': str(e),
                    'user_id': user_id,
                    'timestamp': datetime.now().isoformat()
                }, room=room)
        
        thread = threading.Thread(target=process_message)
        thread.start()
        running_tasks[task_id]['thread'] = thread
        
        # Emit acknowledgment
        emit('message_received', {
            'task_id': task_id,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error handling chat message: {str(e)}")
        emit('error', {'message': 'Failed to process message'})

# Main AI processing functions
async def main(prompt, task_id=None):
    try:
        # Get available API key
        key_result = api_key_manager.get_available_api_key()
        if not key_result:
            return "❌ No available API keys. Please try again later."
        
        api_key, key_config = key_result
        
        # Initialize Manus agent with the API key
        manus = Manus()
        manus.api_key = api_key
        
        # Record successful request
        api_key_manager.record_successful_request(api_key)
        
        # Process the prompt
        response = await manus.run(prompt)
        
        return response
        
    except Exception as e:
        logger.error(f"Error in main processing: {str(e)}")
        return f"❌ Error processing request: {str(e)}"

def run_async_task(message, task_id=None):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(main(message, task_id))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error in async task: {str(e)}")
        return f"❌ Error in async task: {str(e)}"

@app.route('/api/chat-stream', methods=['POST'])
def chat_stream():
    try:
        data = request.get_json()
        message = data.get('message', '')
        user_id = data.get('user_id', 'anonymous')
        
        if not message.strip():
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Initialize task
        running_tasks[task_id] = {
            'status': 'running',
            'start_time': datetime.now().isoformat(),
            'user': user_id,
            'type': 'chat',
            'progress': 0,
            'stop_flag': False
        }
        
        def generate():
            try:
                # Start processing in background thread
                def process_task():
                    try:
                        result = run_async_task(message, task_id)
                        
                        if running_tasks[task_id].get('stop_flag', False):
                            running_tasks[task_id]['status'] = 'stopped'
                            return
                        
                        running_tasks[task_id]['status'] = 'completed'
                        running_tasks[task_id]['progress'] = 100
                        
                        # Save to chat history
                        chat_data = {
                            'user_id': user_id,
                            'message': message,
                            'response': result,
                            'timestamp': datetime.now().isoformat()
                        }
                        save_chat_history(chat_data)
                        
                    except Exception as e:
                        logger.error(f"Error in task processing: {str(e)}")
                        running_tasks[task_id]['status'] = 'error'
                
                # Start background thread
                thread = threading.Thread(target=process_task)
                thread.start()
                running_tasks[task_id]['thread'] = thread
                
                # Stream progress updates
                while running_tasks[task_id]['status'] == 'running':
                    if running_tasks[task_id].get('stop_flag', False):
                        yield f"data: {json.dumps({'status': 'stopped', 'task_id': task_id})}\n\n"
                        break
                    
                    progress = running_tasks[task_id].get('progress', 0)
                    yield f"data: {json.dumps({'status': 'running', 'progress': progress, 'task_id': task_id})}\n\n"
                    time.sleep(0.5)
                
                # Send final result
                if running_tasks[task_id]['status'] == 'completed':
                    result = run_async_task(message, task_id)
                    yield f"data: {json.dumps({'status': 'completed', 'result': result, 'task_id': task_id})}\n\n"
                elif running_tasks[task_id]['status'] == 'error':
                    yield f"data: {json.dumps({'status': 'error', 'error': 'Processing failed', 'task_id': task_id})}\n\n"
                
            except Exception as e:
                logger.error(f"Error in generate: {str(e)}")
                yield f"data: {json.dumps({'status': 'error', 'error': str(e), 'task_id': task_id})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logger.error(f"Error in chat stream: {str(e)}")
        return jsonify({'error': 'Failed to start chat stream'}), 500

# Flow processing function
async def run_flow_task(prompt, task_id=None):
    try:
        # Get available API key
        key_result = api_key_manager.get_available_api_key()
        if not key_result:
            return "❌ No available API keys. Please try again later."
        
        api_key, key_config = key_result
        
        # Initialize Manus agent with the API key
        manus = Manus()
        manus.api_key = api_key
        
        # Record successful request
        api_key_manager.record_successful_request(api_key)
        
        # Process the prompt with flow
        response = await manus.run_flow(prompt)
        
        return response
        
    except Exception as e:
        logger.error(f"Error in flow processing: {str(e)}")
        return f"❌ Error processing flow request: {str(e)}"

def run_flow_async_task(message, task_id=None):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_flow_task(message, task_id))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error in flow async task: {str(e)}")
        return f"❌ Error in flow async task: {str(e)}"

@app.route('/api/flow-stream', methods=['POST'])
def flow_stream():
    try:
        data = request.get_json()
        message = data.get('message', '')
        user_id = data.get('user_id', 'anonymous')
        
        if not message.strip():
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Initialize task
        running_tasks[task_id] = {
            'status': 'running',
            'start_time': datetime.now().isoformat(),
            'user': user_id,
            'type': 'flow',
            'progress': 0,
            'stop_flag': False
        }
        
        def generate():
            try:
                # Start processing in background thread
                def process_task():
                    try:
                        result = run_flow_async_task(message, task_id)
                        
                        if running_tasks[task_id].get('stop_flag', False):
                            running_tasks[task_id]['status'] = 'stopped'
                            return
                        
                        running_tasks[task_id]['status'] = 'completed'
                        running_tasks[task_id]['progress'] = 100
                        
                        # Save to chat history
                        chat_data = {
                            'user_id': user_id,
                            'message': message,
                            'response': result,
                            'type': 'flow',
                            'timestamp': datetime.now().isoformat()
                        }
                        save_chat_history(chat_data)
                        
                    except Exception as e:
                        logger.error(f"Error in flow task processing: {str(e)}")
                        running_tasks[task_id]['status'] = 'error'
                
                # Start background thread
                thread = threading.Thread(target=process_task)
                thread.start()
                running_tasks[task_id]['thread'] = thread
                
                # Stream progress updates
                while running_tasks[task_id]['status'] == 'running':
                    if running_tasks[task_id].get('stop_flag', False):
                        yield f"data: {json.dumps({'status': 'stopped', 'task_id': task_id})}\n\n"
                        break
                    
                    progress = running_tasks[task_id].get('progress', 0)
                    yield f"data: {json.dumps({'status': 'running', 'progress': progress, 'task_id': task_id})}\n\n"
                    time.sleep(0.5)
                
                # Send final result
                if running_tasks[task_id]['status'] == 'completed':
                    result = run_flow_async_task(message, task_id)
                    yield f"data: {json.dumps({'status': 'completed', 'result': result, 'task_id': task_id})}\n\n"
                elif running_tasks[task_id]['status'] == 'error':
                    yield f"data: {json.dumps({'status': 'error', 'error': 'Flow processing failed', 'task_id': task_id})}\n\n"
                
            except Exception as e:
                logger.error(f"Error in flow generate: {str(e)}")
                yield f"data: {json.dumps({'status': 'error', 'error': str(e), 'task_id': task_id})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logger.error(f"Error in flow stream: {str(e)}")
        return jsonify({'error': 'Failed to start flow stream'}), 500

if __name__ == '__main__':
    # Create default admin if none exists
    if not admin_manager.admins:
        success, message = admin_manager.create_admin('admin', 'admin123', 'admin@example.com')
        logger.info(f"Created default admin: {message}")
    
    # Run the application
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
