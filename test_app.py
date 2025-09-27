import pytest
import json
import os
import tempfile
from app import app, init_db

@pytest.fixture
def client():
    """Create a test client for the Flask application"""
    # Create temporary database for testing
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        with app.app_context():
            init_db()
        yield client
    
    # Clean up temporary files
    os.close(db_fd)
    os.unlink(app.config['DATABASE'])

def test_home_endpoint(client):
    """Test the root endpoint returns API information"""
    response = client.get('/')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == 'Python Task Management API'
    assert data['status'] == 'running'

def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert 'database' in data

def test_user_registration(client):
    """Test user can register successfully"""
    user_data = {
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'testpassword123'
    }
    
    response = client.post('/auth/register', 
                          data=json.dumps(user_data),
                          content_type='application/json')
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['message'] == 'User created successfully'
    assert 'token' in data

def test_user_login(client):
    """Test user can login with correct credentials"""
    # First register a user
    user_data = {
        'username': 'loginuser',
        'email': 'login@example.com', 
        'password': 'password123'
    }
    client.post('/auth/register',
                data=json.dumps(user_data),
                content_type='application/json')
    
    # Then login
    login_data = {
        'email': 'login@example.com',
        'password': 'password123'
    }
    
    response = client.post('/auth/login',
                          data=json.dumps(login_data),
                          content_type='application/json')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == 'Login successful'
    assert 'token' in data

def test_create_task(client):
    """Test authenticated user can create tasks"""
    # Register and login user
    user_data = {
        'username': 'taskuser',
        'email': 'task@example.com',
        'password': 'password123'
    }
    register_response = client.post('/auth/register',
                                   data=json.dumps(user_data),
                                   content_type='application/json')
    
    token = json.loads(register_response.data)['token']
    
    # Create task
    task_data = {
        'title': 'Test Task',
        'description': 'This is a test task',
        'priority': 'high'
    }
    
    response = client.post('/tasks',
                          data=json.dumps(task_data),
                          content_type='application/json',
                          headers={'Authorization': f'Bearer {token}'})
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['success'] == True
    assert data['task']['title'] == 'Test Task'

def test_unauthorized_access(client):
    """Test that accessing tasks without token fails"""
    response = client.get('/tasks')
    assert response.status_code == 401