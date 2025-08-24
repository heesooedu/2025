import os
import csv
import uuid
from datetime import datetime, timezone, timedelta

from flask import Flask # 새로 추가
from flask import render_template

# 성능을 위해 eventlet 사용
import eventlet
eventlet.monkey_patch()

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_from_directory
)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, join_room, leave_room
from werkzeug.utils import secure_filename
from passlib.hash import bcrypt

from config import Config
from models import db, User, Booth, Transaction, MapImage, WaitEntry

app = Flask(__name__)
app.config.from_object(Config)

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['QR_FOLDER'], exist_ok=True)
LOG_FOLDER = os.path.join(app.root_path, 'logs')
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_NOTI_PATH = os.path.join(LOG_FOLDER, 'notifications.csv')

db.init_app(app)

socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --------------- Helpers ---------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def parse_qr_payload(payload: str):
    # "SCHOOLFEST|<student_id>|<token>" 또는 raw token 모두 허용
    if '|' in payload:
        parts = payload.split('|')
        token = parts[-1].strip()
        return token
    return payload.strip()

def is_admin(user):
    return user.is_authenticated and user.role in ('admin', 'superadmin')

def is_superadmin(user):
    return user.is_authenticated and user.role == 'superadmin'

def kst_now_iso():
    KST = timezone(timedelta(hours=9))
    return datetime.now(KST).isoformat(timespec='seconds')

def log_notification(sender: User, target: str, target_value: str, message: str):
    # CSV: time, admin_id, admin_name, role, target, target_value, message
    msg = (message or '').replace('\r', ' ').replace('\n', ' ').strip()
    exists = os.path.exists(LOG_NOTI_PATH)
    with open(LOG_NOTI_PATH, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['time', 'admin_id', 'admin_name', 'role', 'target', 'target_value', 'message'])
        w.writerow([kst_now_iso(), sender.id, sender.name, sender.role, target, target_value, msg])

def _broadcast_waitlist(booth_id: int):
    # 목록 만들기
    entries = WaitEntry.query.filter_by(booth_id=booth_id).order_by(WaitEntry.created_at.asc(), WaitEntry.id.asc()).all()
    data = [{'id': e.id, 'student_id': e.student_id, 'name': e.name, 'created_at': e.created_at.isoformat()} for e in entries]
    count = len(data)
    # booth.queue_length 동기화
    booth = Booth.query.get(booth_id)
    if booth:
        booth.queue_length = count
        db.session.commit()
    # 실시간 전파 (기존 index가 쓰는 queue_update도 함께 쏨)
    socketio.emit('waitlist_update', {'booth_id': booth_id, 'entries': data, 'count': count}, room=f'booth_{booth_id}')
    socketio.emit('queue_update', {'booth_id': booth_id, 'queue_length': count}, room='booths')


# --------------- Routes (Public) ---------------
@app.route('/')
def index():
    booths = Booth.query.order_by(Booth.name.asc()).all()
    top10 = User.query.filter(User.role == 'student').order_by(User.points.desc()).limit(10).all()
    maps = MapImage.query.order_by(MapImage.sort_order.asc(), MapImage.id.asc()).all()
    return render_template('index.html', booths=booths, top10=top10, maps=maps)

@app.route('/booth/<int:booth_id>')
def booth_page(booth_id):
    booth = Booth.query.get_or_404(booth_id)
    return render_template('booth.html', booth=booth)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --------------- Admin Auth ---------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter(User.role.in_(['admin', 'superadmin']), User.name == username).first()
        if user and user.password_hash and bcrypt.verify(password, user.password_hash):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('로그인 실패: 아이디 또는 비밀번호를 확인하세요.')
    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))


# --------------- Student Auth ---------------
@app.route('/student/login', methods=['GET','POST'])
def student_login():
    if request.method == 'POST':
        sid = (request.form.get('student_id') or '').strip()
        pin = (request.form.get('pin') or '').strip()
        user = User.query.filter_by(role='student', student_id=sid).first()
        if user and user.password_hash and bcrypt.verify(pin, user.password_hash):
            login_user(user)
            flash(f'{user.name}님 환영합니다!')
            return redirect(url_for('index'))
        flash('로그인 실패: 학번 또는 PIN을 확인하세요.')
    return render_template('student_login.html')

@app.route('/student/logout')
@login_required
def student_logout():
    logout_user()
    flash('로그아웃 되었습니다.')
    return redirect(url_for('index'))


# --------------- Admin Pages ---------------
@app.route('/admin')
@login_required
def admin_dashboard():
    if not is_admin(current_user):
        return redirect(url_for('admin_login'))
    my_booths = Booth.query.filter_by(admin_id=current_user.id).all() if current_user.role == 'admin' \
        else Booth.query.order_by(Booth.name.asc()).all()
    maps = MapImage.query.order_by(MapImage.sort_order.asc(), MapImage.id.asc()).all()
    return render_template(
        'admin_dashboard.html',
        booths=my_booths,
        user=current_user,
        maps=maps,
        map_limit=5,
        is_superadmin=is_superadmin(current_user)
    )

@app.route('/admin/booth/<int:booth_id>/upload', methods=['POST'])
@login_required
def admin_booth_upload(booth_id):
    if not is_admin(current_user):
        return jsonify({'ok': False, 'error': '권한 없음'}), 403
    booth = Booth.query.get_or_404(booth_id)
    if current_user.role == 'admin' and booth.admin_id != current_user.id:
        return jsonify({'ok': False, 'error': '이 부스의 관리자만 업로드할 수 있습니다.'}), 403
    file = request.files.get('image')
    desc = request.form.get('description', '')
    if file and allowed_file(file.filename):
        fname = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{fname}")
        file.save(save_path)
        rel = os.path.basename(save_path)
        booth.image_path = rel
    booth.description = desc
    db.session.commit()
    socketio.emit('booth_updated', {'booth_id': booth.id, 'queue_length': booth.queue_length}, room='booths')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/scan/<int:booth_id>')
@login_required
def admin_scan(booth_id):
    if not is_admin(current_user):
        return redirect(url_for('admin_login'))
    booth = Booth.query.get_or_404(booth_id)
    if current_user.role == 'admin' and booth.admin_id != current_user.id:
        flash('이 부스의 관리자만 접근할 수 있습니다.')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_scan.html', booth=booth)


# --------------- Map (학교 지도) 관리 ---------------
@app.route('/admin/maps/upload', methods=['POST'])
@login_required
def admin_maps_upload():
    # 부스 관리자는 지도 관리 불가
    if not is_superadmin(current_user):
        return jsonify({'ok': False, 'error': '최고 관리자만 가능합니다.'}), 403
    files = request.files.getlist('images')
    existing = MapImage.query.count()
    max_allowed = 5
    saved = 0
    for file in files:
        if existing + saved >= max_allowed:
            break
        if file and allowed_file(file.filename):
            fname = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{fname}")
            file.save(save_path)
            rel = os.path.basename(save_path)
            mi = MapImage(filename=rel, sort_order=existing + saved)
            db.session.add(mi)
            saved += 1
    db.session.commit()
    flash(f'지도 이미지 {saved}장 업로드 완료 (최대 {max_allowed}장).')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/maps/delete/<int:image_id>', methods=['POST'])
@login_required
def admin_maps_delete(image_id):
    # 부스 관리자는 지도 관리 불가
    if not is_superadmin(current_user):
        return jsonify({'ok': False, 'error': '최고 관리자만 가능합니다.'}), 403
    mi = MapImage.query.get_or_404(image_id)
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], mi.filename))
    except OSError:
        pass
    db.session.delete(mi)
    # sort 재정렬
    remaining = MapImage.query.order_by(MapImage.sort_order.asc(), MapImage.id.asc()).all()
    for idx, r in enumerate(remaining):
        r.sort_order = idx
    db.session.commit()
    flash('지도 이미지 삭제 완료.')
    return redirect(url_for('admin_dashboard'))


# --------------- Notify (학생/개인/부스 시청자) ---------------
@app.route('/api/notify', methods=['POST'])
@login_required
def api_notify():
    if not is_admin(current_user):
        return jsonify({'ok': False, 'error': '권한 없음'}), 403
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    target = (data.get('target') or 'all').strip()  # 'all' | 'student' | 'booth'
    student_id = (data.get('student_id') or '').strip()
    booth_id = data.get('booth_id')

    if not message:
        return jsonify({'ok': False, 'error': '메시지를 입력하세요.'}), 400

    # 부스 관리자는 자신의 부스 시청자에게만 발송 허용
    if current_user.role == 'admin' and target != 'booth':
        return jsonify({'ok': False, 'error': '부스 관리자는 자신의 부스 시청자에게만 발송할 수 있습니다.'}), 403

    # 로깅 준비
    log_target_value = ''

    # 전체 학생: 최고 관리자만
    if target == 'all':
        if not is_superadmin(current_user):
            return jsonify({'ok': False, 'error': '전체 발송은 최고 관리자만 가능합니다.'}), 403
        socketio.emit('notify', {'message': message, 'from': current_user.name}, room='students')
        log_target_value = '*'
        log_notification(current_user, target, log_target_value, message)
        return jsonify({'ok': True, 'sent': 'all'})

    # 특정 학번: 최고 관리자만
    if target == 'student':
        if not is_superadmin(current_user):
            return jsonify({'ok': False, 'error': '특정 학번 발송은 최고 관리자만 가능합니다.'}), 403
        if not student_id:
            return jsonify({'ok': False, 'error': 'student_id 필요'}), 400
        user = User.query.filter_by(role='student', student_id=student_id).first()
        if not user:
            return jsonify({'ok': False, 'error': '해당 학번을 찾을 수 없습니다.'}), 404
        socketio.emit('notify', {'message': message, 'from': current_user.name}, room=f'user_{user.id}')
        log_target_value = student_id
        log_notification(current_user, target, log_target_value, message)
        return jsonify({'ok': True, 'sent': f'user_{user.id}'})

    # 특정 부스 시청자
    if target == 'booth':
        try:
            bid = int(booth_id or 0)
        except Exception:
            bid = 0
        if not bid:
            return jsonify({'ok': False, 'error': 'booth_id 필요'}), 400
        if current_user.role == 'admin':
            booth = Booth.query.get(bid)
            if not booth or booth.admin_id != current_user.id:
                return jsonify({'ok': False, 'error': '해당 부스에 대한 권한이 없습니다.'}), 403
        socketio.emit('notify', {'message': message, 'from': current_user.name}, room=f'booth_{bid}')
        log_target_value = str(bid)
        log_notification(current_user, target, log_target_value, message)
        return jsonify({'ok': True, 'sent': f'booth_{bid}'})

    return jsonify({'ok': False, 'error': '잘못된 target'}), 400


# --------------- Waitlist APIs ---------------
@app.route('/api/waitlist/<int:booth_id>', methods=['GET'])
def api_waitlist_get(booth_id):
    Booth.query.get_or_404(booth_id)  # 존재 확인
    entries = WaitEntry.query.filter_by(booth_id=booth_id).order_by(WaitEntry.created_at.asc(), WaitEntry.id.asc()).all()
    return jsonify({
        'booth_id': booth_id,
        'entries': [{'id': e.id, 'student_id': e.student_id, 'name': e.name, 'created_at': e.created_at.isoformat()} for e in entries],
        'count': len(entries)
    })

@app.route('/api/waitlist/<int:booth_id>/add', methods=['POST'])
@login_required
def api_waitlist_add(booth_id):
    if not is_admin(current_user):
        return jsonify({'ok': False, 'error': '권한 없음'}), 403
    booth = Booth.query.get_or_404(booth_id)
    if current_user.role == 'admin' and booth.admin_id != current_user.id:
        return jsonify({'ok': False, 'error': '이 부스의 관리자만 수정할 수 있습니다.'}), 403

    data = request.get_json(silent=True) or {}
    sid = (data.get('student_id') or '').strip()
    name = (data.get('name') or '').strip()

    if not name:
        # 학번으로 학생 이름 자동 보정
        if sid:
            u = User.query.filter_by(role='student', student_id=sid).first()
            if u:
                name = u.name
    if not name:
        return jsonify({'ok': False, 'error': '이름이 필요합니다.'}), 400

    e = WaitEntry(booth_id=booth.id, student_id=sid if sid else None, name=name)
    db.session.add(e)
    db.session.commit()

    _broadcast_waitlist(booth.id)
    return jsonify({'ok': True})

@app.route('/api/waitlist/<int:booth_id>/remove', methods=['POST'])
@login_required
def api_waitlist_remove(booth_id):
    if not is_admin(current_user):
        return jsonify({'ok': False, 'error': '권한 없음'}), 403
    booth = Booth.query.get_or_404(booth_id)
    if current_user.role == 'admin' and booth.admin_id != current_user.id:
        return jsonify({'ok': False, 'error': '이 부스의 관리자만 수정할 수 있습니다.'}), 403

    data = request.get_json(silent=True) or {}
    entry_id = data.get('entry_id')
    if not entry_id:
        return jsonify({'ok': False, 'error': 'entry_id 필요'}), 400

    entry = WaitEntry.query.filter_by(id=entry_id, booth_id=booth.id).first()
    if not entry:
        return jsonify({'ok': False, 'error': '해당 대기열 항목을 찾을 수 없습니다.'}), 404

    db.session.delete(entry)
    db.session.commit()

    _broadcast_waitlist(booth.id)
    return jsonify({'ok': True})


# --------------- APIs (기존) ---------------
@app.route('/api/booths')
def api_booths():
    booths = Booth.query.order_by(Booth.name.asc()).all()
    return jsonify([{
        'id': b.id,
        'name': b.name,
        'queue_length': b.queue_length,
        'image': url_for('uploaded_file', filename=b.image_path) if b.image_path else None,
        'description': b.description
    } for b in booths])

@app.route('/api/leaderboard')
def api_leaderboard():
    top10 = User.query.filter(User.role == 'student').order_by(User.points.desc()).limit(10).all()
    return jsonify([{'name': u.name, 'student_id': u.student_id, 'points': u.points} for u in top10])

@app.route('/api/queue/<int:booth_id>', methods=['POST'])
@login_required
def api_update_queue(booth_id):
    # (호환 유지용) 직접 숫자 수정은 남겨두지만, 대기명단 기반으로 자동 동기화됨
    if not is_admin(current_user):
        return jsonify({'ok': False, 'error': '권한 없음'}), 403
    booth = Booth.query.get_or_404(booth_id)
    if current_user.role == 'admin' and booth.admin_id != current_user.id:
        return jsonify({'ok': False, 'error': '이 부스의 관리자만 수정할 수 있습니다.'}), 403
    data = request.get_json(silent=True) or {}
    q = int(data.get('queue_length', booth.queue_length))
    booth.queue_length = max(0, q)
    db.session.commit()
    socketio.emit('queue_update', {'booth_id': booth.id, 'queue_length': booth.queue_length}, room='booths')
    return jsonify({'ok': True, 'queue_length': booth.queue_length})

@app.route('/api/transaction', methods=['POST'])
@login_required
def api_transaction():
    if not is_admin(current_user):
        return jsonify({'ok': False, 'error': '권한 없음'}), 403
    data = request.get_json(silent=True) or {}
    raw = data.get('qr') or data.get('token') or ''
    token = parse_qr_payload(raw)
    delta = int(data.get('delta', 0))
    reason = (data.get('reason') or '').strip()[:255]
    booth_id = data.get('booth_id')

    user = User.query.filter_by(qr_token=token).first()
    if not user:
        return jsonify({'ok': False, 'error': 'QR을 인식했지만 등록된 학생을 찾지 못했습니다.'}), 404

    new_points = max(0, (user.points or 0) + delta)
    change = new_points - (user.points or 0)

    user.points = new_points
    tx = Transaction(user_id=user.id, booth_id=booth_id, delta=change, reason=reason, admin_id=current_user.id)
    db.session.add(tx)
    db.session.commit()

    top10 = User.query.filter(User.role == 'student').order_by(User.points.desc()).limit(10).all()
    payload = [{'name': u.name, 'student_id': u.student_id, 'points': u.points} for u in top10]
    socketio.emit('leaderboard', payload, room='leaderboard')

    return jsonify({'ok': True, 'user': {'name': user.name, 'student_id': user.student_id, 'points': user.points}})


# --------------- Socket.IO ---------------
@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room == 'leaderboard':
        join_room('leaderboard')
    elif room == 'booths':
        join_room('booths')
    elif room and room.startswith('booth_'):
        join_room(room)
    elif room == 'students':
        join_room('students')
    elif room and room.startswith('user_'):
        join_room(room)

@socketio.on('leave')
def on_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)


# --------------- CLI / Init ---------------
@app.cli.command('create-db')
def create_db():
    with app.app_context():
        db.create_all()
        print('DB created.')

@app.cli.command('create-superadmin')
def create_superadmin():
    import getpass
    name = input('슈퍼관리자 아이디(표시이름): ').strip()
    pw = getpass.getpass('비밀번호: ').strip()
    user = User(name=name, role='superadmin', password_hash=bcrypt.hash(pw))
    db.session.add(user)
    db.session.commit()
    print('슈퍼관리자 생성 완료.')

# if __name__ == '__main__':
#     with app.app_context():
#         db.create_all()
    
#     ssl_context = ('ssl_cert.pem', 'ssl_key.pem')  # SSL 인증서와 개인 키 파일 경로 설정
#     socketio.run(app, host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # ssl_context 인자에 인증서와 키 파일 경로를 튜플로 전달합니다.
    socketio.run(
    app,
    host='0.0.0.0',
    port=5000,
    debug=True,
    certfile='ssl_cert.pem',
    keyfile='ssl_key.pem'
)