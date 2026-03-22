from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # master, coordenador, lider_jovens, tesoureiro, secretario

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, roles):
        if isinstance(roles, str):
            return self.role == roles
        return self.role in roles

class TreasuryEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'Entrada' or 'Saída'
    category = db.Column(db.String(50), nullable=False)
    observation = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class Rehearsal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class RehearsalAttendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rehearsal_id = db.Column(db.Integer, db.ForeignKey('rehearsal.id', ondelete='CASCADE'), nullable=False)
    member_name = db.Column(db.String(100), nullable=False)
    is_present = db.Column(db.Boolean, default=False)
