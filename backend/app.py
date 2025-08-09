import os
from flask import Flask, render_template, request, send_from_directory, url_for, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins='*')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(64))
    text = db.Column(db.Text)
    image_url = db.Column(db.String(256))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    user = request.form.get('user','Anonymous')
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.utcnow().timestamp()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        image_url = url_for('uploaded_file', filename=filename)
        # Save image as a message with only image_url
        msg = Message(user=user, text=None, image_url=image_url)
        db.session.add(msg)
        db.session.commit()
        # Send to all clients
        socketio.emit('message', {
            'user': user,
            'text': None,
            'image_url': image_url,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
        return '', 204
    return '', 400

@app.route('/history')
def history():
    messages = Message.query.order_by(Message.timestamp).all()
    result = []
    for m in messages:
        result.append({
            'user': m.user,
            'text': m.text,
            'image_url': m.image_url,
            'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(result)

@socketio.on('message')
def handle_message(data):
    # data is expected to be dict: {user:..., text:...}
    user = data.get('user', 'Anonymous')
    text = data.get('text')
    msg = Message(user=user, text=text, image_url=None)
    db.session.add(msg)
    db.session.commit()
    emit('message', {
        'user': user,
        'text': text,
        'image_url': None,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }, broadcast=True)

if __name__ == '__main__':
    socketio.run(app)