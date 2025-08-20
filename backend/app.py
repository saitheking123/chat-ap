# --- MUST be first ---
import eventlet
eventlet.monkey_patch()
from dotenv import load_dotenv
load_dotenv()

# --- Imports ---
import os
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime

# --- Config ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = "uploads"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- MySQL / SQLAlchemy ---
DB_USER = 'avnadmin'
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = 'saidata-colimarl-14a4.c.aivencloud.com'
DB_PORT = 18883
DB_NAME = 'defaultdb'

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'ssl': {
            'ca': os.path.join(os.path.dirname(__file__), "certs", "ca.pem")
        }
    }
}

app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB max

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# --- Models ---
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(64))
    text = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)  # store file path instead of blob
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

with app.app_context():
    db.create_all()

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    user = request.form.get('user', 'Anonymous')
    if file and allowed_file(file.filename):
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        image_url = f"/uploads/{filename}"
        msg = Message(user=user, text=None, image_url=image_url)
        db.session.add(msg)
        db.session.commit()

        payload = {
            'user': user,
            'text': None,
            'image_url': image_url,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
        socketio.emit('message', payload, broadcast=True)
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

# --- SocketIO ---
@socketio.on('message')
def handle_message(data):
    user = data.get('user', 'Anonymous')
    text = data.get('text')
    msg = Message(user=user, text=text)
    db.session.add(msg)
    db.session.commit()

    payload = {
        'user': user,
        'text': text,
        'image_url': None,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    emit('message', payload, broadcast=True)

@socketio.on('connect')
def handle_connect():
    messages = Message.query.order_by(Message.timestamp).all()
    for m in messages:
        emit('message', {
            'user': m.user,
            'text': m.text,
            'image_url': m.image_url,
            'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })

# --- Run ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
