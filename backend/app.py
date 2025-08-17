import os
from flask import Flask, render_template, request, send_file, jsonify
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
from io import BytesIO
import eventlet

eventlet.monkey_patch()  # Fix for WebSockets with eventlet

# --- Config ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

# --- MySQL / SQLAlchemy ---
DB_USER = 'avnadmin'
DB_PASSWORD = os.getenv('DB_PASSWORD')  # Render env variable
DB_HOST = 'saidata-colimarl-14a4.c.aivencloud.com'
DB_PORT = 18883
DB_NAME = 'defaultdb'

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4&ssl_disabled=true"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB max

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")  # Use eventlet

# --- Models ---
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(64))
    text = db.Column(db.Text, nullable=True)
    image_data = db.Column(db.LargeBinary, nullable=True)
    image_mime = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

with app.app_context():
    db.create_all()

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/image/<int:msg_id>')
def get_image(msg_id):
    msg = Message.query.get_or_404(msg_id)
    if msg.image_data:
        return send_file(BytesIO(msg.image_data),
                         mimetype=msg.image_mime,
                         as_attachment=False,
                         download_name=f"image_{msg.id}")
    return "No image", 404

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    user = request.form.get('user', 'Anonymous')
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        image_data = file.read()
        image_mime = file.mimetype

        msg = Message(user=user, text=None, image_data=image_data, image_mime=image_mime)
        db.session.add(msg)
        db.session.commit()

        image_url = f"/image/{msg.id}"
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
            'image_url': f"/image/{m.id}" if m.image_data else None,
            'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(result)

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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
