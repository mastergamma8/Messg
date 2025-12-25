from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_change_me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messenger.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

# --- Модели Базы Данных ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    
class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    contact_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    text = db.Column(db.Text)

# Создаем БД при запуске
with app.app_context():
    db.create_all()

# --- Роуты ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()
    session['username'] = username
    return jsonify({'status': 'success', 'username': username})

@app.route('/search_user', methods=['POST'])
def search_user():
    query = request.json.get('query')
    users = User.query.filter(User.username.contains(query)).all()
    # Исключаем себя
    results = [u.username for u in users if u.username != session.get('username')]
    return jsonify(results)

@app.route('/add_contact', methods=['POST'])
def add_contact():
    target_name = request.json.get('username')
    curr_user = User.query.filter_by(username=session.get('username')).first()
    target_user = User.query.filter_by(username=target_name).first()
    
    if curr_user and target_user:
        # Проверка, есть ли уже в контактах
        exists = Contact.query.filter_by(owner_id=curr_user.id, contact_id=target_user.id).first()
        if not exists:
            new_contact = Contact(owner_id=curr_user.id, contact_id=target_user.id)
            db.session.add(new_contact)
            db.session.commit()
            return jsonify({'status': 'added'})
    return jsonify({'status': 'error'})

@app.route('/get_contacts', methods=['GET'])
def get_contacts():
    curr_user = User.query.filter_by(username=session.get('username')).first()
    if not curr_user: return jsonify([])
    
    contacts = Contact.query.filter_by(owner_id=curr_user.id).all()
    names = []
    for c in contacts:
        u = User.query.get(c.contact_id)
        names.append(u.username)
    return jsonify(names)

@app.route('/get_history', methods=['POST'])
def get_history():
    partner = request.json.get('partner')
    me = session.get('username')
    # Ищем сообщения между мной и партнером
    msgs = Message.query.filter(
        ((Message.sender == me) & (Message.receiver == partner)) |
        ((Message.sender == partner) & (Message.receiver == me))
    ).all()
    return jsonify([{'sender': m.sender, 'text': m.text} for m in msgs])

# --- SocketIO (Реал-тайм) ---
@socketio.on('join')
def on_join(data):
    username = data['username']
    join_room(username) # Каждый юзер слушает свою "комнату"

@socketio.on('send_message')
def handle_message(data):
    sender = data['sender']
    receiver = data['receiver']
    text = data['text']
    
    # Сохраняем в БД
    msg = Message(sender=sender, receiver=receiver, text=text)
    db.session.add(msg)
    db.session.commit()
    
    # Отправляем получателю и себе (чтобы отобразилось)
    emit('new_message', data, room=receiver)
    emit('new_message', data, room=sender)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
