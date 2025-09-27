from flask import Flask, request, jsonify, g
import sqlite3
import hashlib
import jwt
import datetime
from functools import wraps
import os

# Create Flask application instance
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Database configuration
DATABASE = 'tasks.db'

def get_db():
    """Get database connection for the current request"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # Return rows as dictionaries
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection when request ends"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize database with required tables"""
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        ''')
        db.commit()

def token_required(f):
    """Decorator that requires valid JWT token for access"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]  # Remove 'Bearer ' prefix
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        
        return f(current_user_id, *args, **kwargs)
    return decorated

def hash_password(password):
    """Securely hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def home():
    """Root endpoint - API information"""
    return jsonify({
        'message': 'Python Task Management API',
        'version': '1.0.0',
        'status': 'running',
        'endpoints': {
            'health': '/health',
            'auth': '/auth',
            'tasks': '/tasks'
        }
    })

@app.route('/health')
def health():
    """Health check endpoint for monitoring"""
    db_status = check_database()
    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/auth/register', methods=['POST'])
def register():
    """Register a new user account"""
    data = request.get_json()
    
    # Validate required fields
    if not data or not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Username, email and password required'}), 400
    
    try:
        db = get_db()
        password_hash = hash_password(data['password'])
        
        # Insert new user into database
        db.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (data['username'], data['email'], password_hash)
        )
        db.commit()
        
        # Get the created user
        user = db.execute(
            'SELECT id, username, email FROM users WHERE email = ?',
            (data['email'],)
        ).fetchone()
        
        # Generate JWT token
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'message': 'User created successfully',
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email']
            }
        }), 201
        
    except sqlite3.IntegrityError:
        return jsonify({'message': 'Username or email already exists'}), 400

@app.route('/auth/login', methods=['POST'])
def login():
    """Login existing user"""
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Email and password required'}), 400
    
    try:
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE email = ?',
            (data['email'],)
        ).fetchone()
        
        # Verify user exists and password is correct
        if not user or user['password_hash'] != hash_password(data['password']):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        # Generate JWT token
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email']
            }
        })
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/tasks', methods=['GET'])
@token_required
def get_tasks(current_user_id):
    """Get all tasks for the current user"""
    try:
        db = get_db()
        tasks = db.execute(
            'SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC',
            (current_user_id,)
        ).fetchall()
        
        # Convert database rows to dictionaries
        task_list = []
        for task in tasks:
            task_list.append({
                'id': task['id'],
                'title': task['title'],
                'description': task['description'],
                'status': task['status'],
                'priority': task['priority'],
                'created_at': task['created_at']
            })
        
        return jsonify({
            'success': True,
            'tasks': task_list,
            'count': len(task_list)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/tasks', methods=['POST'])
@token_required
def create_task(current_user_id):
    """Create a new task"""
    data = request.get_json()
    
    if not data or not data.get('title'):
        return jsonify({'message': 'Title is required'}), 400
    
    try:
        db = get_db()
        cursor = db.execute(
            'INSERT INTO tasks (title, description, status, priority, user_id) VALUES (?, ?, ?, ?, ?)',
            (
                data['title'],
                data.get('description', ''),
                data.get('status', 'pending'),
                data.get('priority', 'medium'),
                current_user_id
            )
        )
        db.commit()
        
        # Return the created task
        task = db.execute(
            'SELECT * FROM tasks WHERE id = ?',
            (cursor.lastrowid,)
        ).fetchone()
        
        return jsonify({
            'success': True,
            'message': 'Task created successfully',
            'task': {
                'id': task['id'],
                'title': task['title'],
                'description': task['description'],
                'status': task['status'],
                'priority': task['priority']
            }
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def check_database():
    """Check if database is accessible"""
    try:
        db = get_db()
        cursor = db.execute('SELECT 1')
        cursor.fetchone()
        return 'connected'
    except Exception as e:
        return f'error: {str(e)}'

# Initialize database and start application
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=3000)