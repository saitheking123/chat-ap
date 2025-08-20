# --- MUST be first ---
from dotenv import load_dotenv
load_dotenv()

# --- Imports ---
import os
from datetime import datetime
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# --- Config ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")

app = Flask(__name__, static_folder=None, template_folder=None)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB max

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
    "pool_pre_ping": True,  # survive stale connections
    'connect_args': {
        'ssl': {
            'ca': os.path.join(os.path.dirname(__file__), "certs", "ca.pem")
        }
    }
}

db = SQLAlchemy(app)

# --- Use threading mode instead of eventlet ---
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# --- Models ---
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(64))
    text = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- Helpers ---
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

with app.app_context():
    db.create_all()

# --- Routes ---
@app.route('/')
def index():
    # Serve templates/index.html (see file below)
    return render_template('index.html')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Serve uploaded images
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    user = request.form.get('user', 'Anonymous')
    if not file or not allowed_file(file.filename):
        return '', 400

    # Safe filename
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)[:120]}"
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
    # Broadcast to everyone
    socketio.emit('chat_message', payload, broadcast=True)
    return '', 204

@app.route('/history')
def history_http():
    # Optional HTTP history endpoint (not required by the client, but handy for debugging)
    messages = Message.query.order_by(Message.timestamp).all()
    result = [{
        'user': m.user,
        'text': m.text,
        'image_url': m.image_url,
        'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for m in messages]
    return jsonify(result)

@app.route('/healthz')
def healthz():
    return jsonify({"ok": True})

# --- SocketIO ---
@socketio.on('chat_message')
def handle_chat_message(data):
    user = data.get('user', 'Anonymous')
    text = (data.get('text') or '').strip()
    if not text:
        return  # ignore empty

    msg = Message(user=user, text=text)
    db.session.add(msg)
    db.session.commit()

    payload = {
        'user': user,
        'text': text,
        'image_url': None,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    # Broadcast to everyone (WhatsApp-style group)
    emit('chat_message', payload, broadcast=True)

@socketio.on('connect')
def handle_connect():
    # Send full chat history to the newly connected client
    messages = Message.query.order_by(Message.timestamp).all()
    history = [{
        'user': m.user,
        'text': m.text,
        'image_url': m.image_url,
        'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for m in messages]
    emit('chat_history', history)

# --- Run ---
if __name__ == '__main__':
    # On Windows + debug, Werkzeug reloader can start twice → duplicate emits.
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting Flask app with threading on 0.0.0.0:{port} ...")
    socketio.run(app, host="0.0.0.0", port=port, debug=True, use_reloader=False)
