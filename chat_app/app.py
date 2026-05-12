from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from functools import wraps

# Initialisation de l'application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'ma_cle_secrete_ultra_longue_123456789'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ==================== MODÈLES ====================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    online_status = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sent_requests = db.relationship('FriendRequest', foreign_keys='FriendRequest.sender_id', backref='sender', lazy='dynamic')
    received_requests = db.relationship('FriendRequest', foreign_keys='FriendRequest.receiver_id', backref='receiver', lazy='dynamic')
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')

class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id], backref='friendships')
    friend = db.relationship('User', foreign_keys=[friend_id])

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== TEMPLATES HTML ====================

BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat App - Communication</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 90%;
            max-width: 500px;
            padding: 40px;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        h1 {
            color: #667eea;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: 500;
        }
        
        input[type="text"],
        input[type="email"],
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        
        .link {
            text-align: center;
            margin-top: 20px;
        }
        
        .link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }
        
        .alert {
            padding: 12px;
            background: #f8d7da;
            color: #721c24;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .success {
            background: #d4edda;
            color: #155724;
        }
        
        .nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
        }
        
        .status-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 5px;
        }
        
        .online { background: #28a745; }
        .offline { background: #dc3545; }
        
        .friend-list, .request-list {
            list-style: none;
        }
        
        .friend-item, .request-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: #f8f9fa;
            margin-bottom: 10px;
            border-radius: 8px;
            transition: background 0.3s;
        }
        
        .friend-item:hover {
            background: #e9ecef;
        }
        
        .chat-container {
            max-width: 800px;
            height: 600px;
            display: flex;
            flex-direction: column;
        }
        
        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 20px 20px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f8f9fa;
        }
        
        .message {
            margin-bottom: 15px;
            display: flex;
            flex-direction: column;
        }
        
        .message.sent {
            align-items: flex-end;
        }
        
        .message.received {
            align-items: flex-start;
        }
        
        .message-content {
            max-width: 70%;
            padding: 10px 15px;
            border-radius: 15px;
            word-wrap: break-word;
        }
        
        .sent .message-content {
            background: #667eea;
            color: white;
        }
        
        .received .message-content {
            background: white;
            border: 1px solid #e0e0e0;
        }
        
        .message-time {
            font-size: 0.8em;
            color: #999;
            margin-top: 5px;
        }
        
        .chat-input {
            padding: 20px;
            background: white;
            border-radius: 0 0 20px 20px;
            display: flex;
            gap: 10px;
        }
        
        .chat-input input {
            flex: 1;
        }
        
        .btn-small {
            width: auto;
            padding: 8px 15px;
            font-size: 14px;
        }
        
        .btn-accept {
            background: #28a745;
            margin-right: 5px;
        }
        
        .btn-reject {
            background: #dc3545;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert {% if category == 'success' %}success{% endif %}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
    
    {% block scripts %}{% endblock %}
</body>
</html>
'''

# ==================== PAGES HTML ====================

REGISTER_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
    <h1>📝 Inscription</h1>
    <form method="POST">
        <div class="form-group">
            <label>Nom d'utilisateur</label>
            <input type="text" name="username" required>
        </div>
        <div class="form-group">
            <label>Email</label>
            <input type="email" name="email" required>
        </div>
        <div class="form-group">
            <label>Mot de passe</label>
            <input type="password" name="password" required>
        </div>
        <button type="submit" class="btn">S'inscrire</button>
    </form>
    <div class="link">
        Déjà un compte ? <a href="{{ url_for('login') }}">Se connecter</a>
    </div>
{% endblock %}
''')

LOGIN_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
    <h1>🔐 Connexion</h1>
    <form method="POST">
        <div class="form-group">
            <label>Email</label>
            <input type="email" name="email" required>
        </div>
        <div class="form-group">
            <label>Mot de passe</label>
            <input type="password" name="password" required>
        </div>
        <button type="submit" class="btn">Se connecter</button>
    </form>
    <div class="link">
        Pas encore de compte ? <a href="{{ url_for('register') }}">S'inscrire</a>
    </div>
{% endblock %}
''')

DASHBOARD_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
    <h1>👋 Bienvenue {{ current_user.username }}</h1>
    
    <div style="text-align: center; margin-bottom: 30px;">
        <span class="status-dot online"></span> En ligne
        <span style="margin-left: 20px;">Dernière connexion : {{ current_user.last_seen.strftime('%d/%m/%Y %H:%M') }}</span>
    </div>
    
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
        <a href="{{ url_for('friends') }}" style="text-decoration: none;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h2>👥 {{ current_user.friendships|length }}</h2>
                <p>Amis</p>
            </div>
        </a>
        <a href="{{ url_for('friends') }}" style="text-decoration: none;">
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h2>💬 {{ current_user.received_requests.filter_by(status='pending').count() }}</h2>
                <p>Demandes</p>
            </div>
        </a>
    </div>
    
    <div style="text-align: center; margin-top: 30px;">
        <a href="{{ url_for('friends') }}" class="btn" style="display: inline-block; text-decoration: none; width: auto; margin-right: 10px;">Gérer mes amis</a>
        <a href="{{ url_for('logout') }}" class="btn" style="display: inline-block; text-decoration: none; width: auto; background: #dc3545;">Déconnexion</a>
    </div>
{% endblock %}
''')

FRIENDS_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
    <div class="nav">
        <h1>👥 Amis</h1>
        <a href="{{ url_for('dashboard') }}">← Retour</a>
    </div>
    
    <div class="form-group">
        <h3>Ajouter un ami</h3>
        <form method="POST" action="{{ url_for('send_friend_request') }}">
            <div style="display: flex; gap: 10px;">
                <input type="text" name="username" placeholder="Nom d'utilisateur" required>
                <button type="submit" class="btn btn-small">Envoyer</button>
            </div>
        </form>
    </div>
    
    <h3>Demandes en attente</h3>
    <ul class="request-list">
        {% for request in current_user.received_requests.filter_by(status='pending') %}
        <li class="request-item">
            <span>{{ request.sender.username }}</span>
            <div>
                <a href="{{ url_for('respond_friend_request', request_id=request.id, action='accept') }}" class="btn btn-small btn-accept">Accepter</a>
                <a href="{{ url_for('respond_friend_request', request_id=request.id, action='reject') }}" class="btn btn-small btn-reject">Refuser</a>
            </div>
        </li>
        {% else %}
        <p>Aucune demande en attente</p>
        {% endfor %}
    </ul>
    
    <h3>Mes amis</h3>
    <ul class="friend-list">
        {% for friendship in current_user.friendships %}
        <li class="friend-item">
            <div class="user-info">
                <div class="avatar">{{ friendship.friend.username[0].upper() }}</div>
                <span>{{ friendship.friend.username }}</span>
                <span class="status-dot {% if friendship.friend.online_status %}online{% else %}offline{% endif %}"></span>
                <small>{{ 'En ligne' if friendship.friend.online_status else 'Hors ligne' }}</small>
            </div>
            <a href="{{ url_for('chat', user_id=friendship.friend.id) }}" class="btn btn-small">Message</a>
        </li>
        {% else %}
        <p>Pas encore d'amis. Ajoutez-en !</p>
        {% endfor %}
    </ul>
{% endblock %}
''')

CHAT_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
    <div class="chat-container" style="max-width: 600px;">
        <div class="chat-header">
            <div class="user-info">
                <div class="avatar">{{ friend.username[0].upper() }}</div>
                <span>{{ friend.username }}</span>
                <span class="status-dot {% if friend.online_status %}online{% else %}offline{% endif %}"></span>
            </div>
            <a href="{{ url_for('friends') }}" style="color: white;">← Retour</a>
        </div>
        
        <div class="chat-messages" id="messages">
            {% for message in messages %}
            <div class="message {% if message.sender_id == current_user.id %}sent{% else %}received{% endif %}">
                <div class="message-content">{{ message.content }}</div>
                <div class="message-time">{{ message.timestamp.strftime('%H:%M') }}</div>
            </div>
            {% endfor %}
        </div>
        
        <div class="chat-input">
            <input type="text" id="messageInput" placeholder="Votre message...">
            <button onclick="sendMessage()" class="btn btn-small">Envoyer</button>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        const socket = io();
        const currentUserId = {{ current_user.id }};
        const friendId = {{ friend.id }};
        const room = [currentUserId, friendId].sort().join('_');
        
        socket.on('connect', function() {
            socket.emit('join', {'room': room});
        });
        
        socket.on('new_message', function(data) {
            const messagesDiv = document.getElementById('messages');
            const messageClass = data.sender_id === currentUserId ? 'sent' : 'received';
            const time = new Date().toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'});
            
            messagesDiv.innerHTML += `
                <div class="message ${messageClass}">
                    <div class="message-content">${data.content}</div>
                    <div class="message-time">${time}</div>
                </div>
            `;
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        });
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            const content = input.value.trim();
            
            if (content) {
                socket.emit('send_message', {
                    'sender_id': currentUserId,
                    'receiver_id': friendId,
                    'content': content,
                    'room': room
                });
                input.value = '';
            }
        }
        
        document.getElementById('messageInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        // Scroll to bottom
        const messagesDiv = document.getElementById('messages');
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    </script>
{% endblock %}
''')

# ==================== ROUTES ====================

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur existe déjà', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé', 'error')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Inscription réussie ! Connectez-vous.', 'success')
        return redirect(url_for('login'))
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            user.online_status = True
            user.last_seen = datetime.utcnow()
            db.session.commit()
            socketio.emit('user_status_change', {'user_id': user.id, 'status': True}, broadcast=True)
            flash('Connecté avec succès !', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou mot de passe incorrect', 'error')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE)

@app.route('/friends')
@login_required
def friends():
    return render_template_string(FRIENDS_TEMPLATE)

@app.route('/send_friend_request', methods=['POST'])
@login_required
def send_friend_request():
    username = request.form.get('username')
    user = User.query.filter_by(username=username).first()
    
    if not user:
        flash('Utilisateur non trouvé', 'error')
        return redirect(url_for('friends'))
    
    if user.id == current_user.id:
        flash('Vous ne pouvez pas vous ajouter vous-même', 'error')
        return redirect(url_for('friends'))
    
    # Vérifier si déjà amis
    existing_friendship = Friendship.query.filter(
        ((Friendship.user_id == current_user.id) & (Friendship.friend_id == user.id)) |
        ((Friendship.user_id == user.id) & (Friendship.friend_id == current_user.id))
    ).first()
    
    if existing_friendship:
        flash('Vous êtes déjà amis', 'error')
        return redirect(url_for('friends'))
    
    # Vérifier si demande existante
    existing_request = FriendRequest.query.filter(
        ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == user.id)) |
        ((FriendRequest.sender_id == user.id) & (FriendRequest.receiver_id == current_user.id))
    ).filter_by(status='pending').first()
    
    if existing_request:
        flash('Une demande d\'ami est déjà en cours', 'error')
        return redirect(url_for('friends'))
    
    friend_request = FriendRequest(sender_id=current_user.id, receiver_id=user.id)
    db.session.add(friend_request)
    db.session.commit()
    
    flash(f'Demande d\'ami envoyée à {username}', 'success')
    return redirect(url_for('friends'))

@app.route('/respond_friend_request/<int:request_id>/<action>')
@login_required
def respond_friend_request(request_id, action):
    friend_request = FriendRequest.query.get_or_404(request_id)
    
    if friend_request.receiver_id != current_user.id:
        flash('Action non autorisée', 'error')
        return redirect(url_for('friends'))
    
    if action == 'accept':
        friend_request.status = 'accepted'
        friendship1 = Friendship(user_id=current_user.id, friend_id=friend_request.sender_id)
        friendship2 = Friendship(user_id=friend_request.sender_id, friend_id=current_user.id)
        db.session.add(friendship1)
        db.session.add(friendship2)
        flash('Demande d\'ami acceptée !', 'success')
    else:
        friend_request.status = 'rejected'
        flash('Demande d\'ami refusée', 'success')
    
    db.session.commit()
    return redirect(url_for('friends'))

@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    friend = User.query.get_or_404(user_id)
    
    # Vérifier si amis
    friendship = Friendship.query.filter_by(user_id=current_user.id, friend_id=user_id).first()
    if not friendship:
        flash('Vous devez être amis pour discuter', 'error')
        return redirect(url_for('friends'))
    
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()
    
    return render_template_string(CHAT_TEMPLATE, friend=friend, messages=messages)

@app.route('/logout')
@login_required
def logout():
    current_user.online_status = False
    current_user.last_seen = datetime.utcnow()
    db.session.commit()
    socketio.emit('user_status_change', {'user_id': current_user.id, 'status': False}, broadcast=True)
    logout_user()
    return redirect(url_for('login'))

# ==================== SOCKET.IO ====================

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        current_user.online_status = True
        db.session.commit()
        emit('user_status_change', {'user_id': current_user.id, 'status': True}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        current_user.online_status = False
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        emit('user_status_change', {'user_id': current_user.id, 'status': False}, broadcast=True)

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

@socketio.on('send_message')
def handle_message(data):
    sender_id = data['sender_id']
    receiver_id = data['receiver_id']
    content = data['content']
    room = data['room']
    
    message = Message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        content=content
    )
    db.session.add(message)
    db.session.commit()
    
    emit('new_message', {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'content': content,
        'timestamp': message.timestamp.strftime('%H:%M')
    }, room=room)

# ==================== DÉMARRAGE ====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)