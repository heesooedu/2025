from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(32), unique=True, nullable=True)  # only for students
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='student')  # 'student', 'admin', 'superadmin'
    qr_token = db.Column(db.String(64), unique=True, index=True)  # for students
    points = db.Column(db.Integer, default=0)
    # 학생 PIN(8자리) & 관리자 비밀번호 모두 해시로 저장
    password_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        return str(self.id)

class Booth(db.Model):
    __tablename__ = 'booth'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    image_path = db.Column(db.String(255))
    queue_length = db.Column(db.Integer, default=0)  # 대기명단 길이를 동기화해서 보관
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    admin = db.relationship('User', foreign_keys=[admin_id])

class Transaction(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # student
    booth_id = db.Column(db.Integer, db.ForeignKey('booth.id'))
    delta = db.Column(db.Integer, nullable=False)  # positive or negative
    reason = db.Column(db.String(255))
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # admin who did it
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    booth = db.relationship('Booth', foreign_keys=[booth_id])
    admin = db.relationship('User', foreign_keys=[admin_id])

# ⭐ 메인 화면의 학교 지도 이미지
class MapImage(db.Model):
    __tablename__ = 'map_image'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ⭐ 대기명단: 부스별로 학생을 순서대로 적재
class WaitEntry(db.Model):
    __tablename__ = 'wait_entry'
    id = db.Column(db.Integer, primary_key=True)
    booth_id = db.Column(db.Integer, db.ForeignKey('booth.id'), nullable=False, index=True)
    student_id = db.Column(db.String(32), nullable=True)  # 학번(선택)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
