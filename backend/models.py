from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(64))
    text = db.Column(db.Text)
    image_url = db.Column(db.String(256))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)