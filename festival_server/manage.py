import os
import sys
import uuid
import pandas as pd
import qrcode
from passlib.hash import bcrypt

from flask import Flask
from config import Config
from models import db, User, Booth, Transaction

def make_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app

def ensure_dirs(app):
    os.makedirs(app.config['QR_FOLDER'], exist_ok=True)

# ---------------------------
# 기본: 학생/부스/관리자 생성
# ---------------------------
def import_students(csv_path, initial_points=0, tag_prefix='SCHOOLFEST'):
    app = make_app()
    with app.app_context():
        ensure_dirs(app)
        df = pd.read_csv(csv_path, dtype=str).fillna('')
        created = 0
        for _, row in df.iterrows():
            student_id = str(row.get('student_id') or row.get('학번') or '').strip()
            name = str(row.get('name') or row.get('이름') or '').strip()
            if not student_id or not name:
                continue
            token = uuid.uuid4().hex
            user = User(student_id=student_id, name=name, role='student',
                        qr_token=token,
                        points=int(row.get('points', initial_points) or initial_points))
            db.session.add(user)
            # Generate QR: "TAG|student_id|token"
            payload = f"{tag_prefix}|{student_id}|{token}"
            img = qrcode.make(payload)
            out_path = os.path.join(Config.QR_FOLDER, f"{student_id}_{name}.png")
            img.save(out_path)
            created += 1
        db.session.commit()
        print(f"학생 {created}명 등록 및 QR 생성 완료. (폴더: {Config.QR_FOLDER})")

def create_booths(names):
    app = make_app()
    with app.app_context():
        cnt = 0
        for n in names:
            n2 = n.strip()
            if not n2:
                continue
            if not Booth.query.filter_by(name=n2).first():
                db.session.add(Booth(name=n2))
                cnt += 1
        db.session.commit()
        print(f"부스 {cnt}개 생성(이미 존재하는 부스는 유지).")

def create_admin(admin_name, password, booth_name=None):
    app = make_app()
    with app.app_context():
        admin = User(name=admin_name, role='admin', password_hash=bcrypt.hash(password))
        db.session.add(admin)
        db.session.commit()
        if booth_name:
            booth = Booth.query.filter_by(name=booth_name).first()
            if not booth:
                booth = Booth(name=booth_name)
                db.session.add(booth)
                db.session.commit()
            booth.admin_id = admin.id
            db.session.commit()
        print(f"관리자 '{admin_name}' 생성 완료. (부스: {booth_name or '연결 없음'})")

# ---------------------------
# 조회: 목록 확인
# ---------------------------
def list_booths():
    app = make_app()
    with app.app_context():
        rows = Booth.query.order_by(Booth.name.asc()).all()
        if not rows:
            print("부스가 없습니다.")
            return
        print("[부스 목록]")
        for b in rows:
            print(f"- id={b.id}, name={b.name}, admin_id={b.admin_id}, queue={b.queue_length}")

def list_admins():
    app = make_app()
    with app.app_context():
        rows = User.query.filter(User.role=='admin').order_by(User.name.asc()).all()
        if not rows:
            print("관리자 계정이 없습니다.")
            return
        print("[관리자 목록]")
        for u in rows:
            print(f"- id={u.id}, name={u.name}")

# ---------------------------
# 삭제: 부스 / 관리자
# ---------------------------
def delete_booth(booth_name):
    """
    부스 삭제:
      - 연결된 Booth.admin_id는 신경 쓸 필요 없음(행 자체 삭제)
      - Transaction.booth_id 는 None 으로 돌려서 기록 보존
    """
    app = make_app()
    with app.app_context():
        booth = Booth.query.filter_by(name=booth_name).first()
        if not booth:
            print(f"부스 '{booth_name}' 를 찾을 수 없습니다.")
            return
        # 트랜잭션의 booth_id 해제 (기록 보존용)
        txs = Transaction.query.filter_by(booth_id=booth.id).all()
        for t in txs:
            t.booth_id = None
        db.session.commit()
        # 부스 삭제
        db.session.delete(booth)
        db.session.commit()
        print(f"부스 '{booth_name}' 삭제 완료 (관련 거래 {len(txs)}건의 booth_id=None 처리).")

def delete_admin(admin_name):
    """
    관리자 삭제:
      - 이 관리자가 담당하던 Booth.admin_id 를 None으로 설정
      - Transaction.admin_id 도 None 으로 설정(기록 보존)
    """
    app = make_app()
    with app.app_context():
        admins = User.query.filter(User.role=='admin', User.name==admin_name).all()
        if not admins:
            print(f"관리자 '{admin_name}' 을(를) 찾을 수 없습니다.")
            return
        if len(admins) > 1:
            print(f"동일 이름의 관리자가 여러 명입니다. 아이디(id)로 지정해서 삭제하세요:")
            for a in admins:
                print(f"- id={a.id}, name={a.name}")
            return
        admin = admins[0]
        # 이 관리자가 맡은 부스들 admin_id 해제
        booths = Booth.query.filter_by(admin_id=admin.id).all()
        for b in booths:
            b.admin_id = None
        # 트랜잭션의 admin_id 해제 (기록 보존)
        txs = Transaction.query.filter_by(admin_id=admin.id).all()
        for t in txs:
            t.admin_id = None
        db.session.commit()
        # 계정 삭제
        db.session.delete(admin)
        db.session.commit()
        print(f"관리자 '{admin_name}'(id={admin.id}) 삭제 완료. (담당 부스 {len(booths)}개 해제, 관련 거래 {len(txs)}건 admin_id=None)")

def delete_admin_by_id(admin_id: int):
    app = make_app()
    with app.app_context():
        admin = User.query.filter(User.role=='admin', User.id==admin_id).first()
        if not admin:
            print(f"id={admin_id} 인 관리자 계정을 찾을 수 없습니다.")
            return
        booths = Booth.query.filter_by(admin_id=admin.id).all()
        for b in booths:
            b.admin_id = None
        txs = Transaction.query.filter_by(admin_id=admin.id).all()
        for t in txs:
            t.admin_id = None
        db.session.commit()
        db.session.delete(admin)
        db.session.commit()
        print(f"관리자 id={admin_id} 삭제 완료. (담당 부스 {len(booths)}개 해제, 관련 거래 {len(txs)}건 admin_id=None)")

# ---------------------------
# 학생 PIN(8자리) 부여/설정
# ---------------------------
import random
from passlib.hash import bcrypt

def _random_pin(n=8):
    # 0으로 시작해도 되면 아래 그대로, 아니면 1~9로 첫 자리 제한 가능
    return str(random.randint(0, 10**n - 1)).zfill(n)

def assign_pins(length=8, export_csv='assigned_pins.csv'):
    """
    password_hash가 비어있는 학생에게만 무작위 PIN(중복 없이) 부여.
    부여된 (student_id,name,pin) 을 CSV로 내보냄.
    """
    app = make_app()
    with app.app_context():
        students = User.query.filter(User.role=='student').all()
        used = set()
        # 이미 누군가의 PIN이 설정되어 있다면(복구용 용도로) 건드리지 않음
        assigned = []
        for u in students:
            if u.password_hash:
                continue
            while True:
                pin = _random_pin(length)
                if pin not in used:
                    used.add(pin)
                    break
            u.password_hash = bcrypt.hash(pin)
            assigned.append((u.student_id, u.name, pin))
        db.session.commit()
        # CSV 저장
        import csv
        with open(export_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['student_id','name','pin'])
            w.writerows(assigned)
        print(f"PIN 부여 완료: {len(assigned)}명, CSV: {export_csv}")

def set_pin(student_id, pin):
    """특정 학번에 PIN 직접 지정/재설정"""
    app = make_app()
    with app.app_context():
        u = User.query.filter_by(role='student', student_id=str(student_id)).first()
        if not u:
            print(f"학번 {student_id} 학생을 찾을 수 없습니다.")
            return
        u.password_hash = bcrypt.hash(str(pin))
        db.session.commit()
        print(f"학번 {student_id} PIN 설정 완료.")


# ---------------------------
# entry
# ---------------------------
def main():
    if len(sys.argv) < 2:
        print("""\
Usage:
  # 생성/등록
  python manage.py import_students <students.csv> [initial_points] [tag_prefix]
  python manage.py create_booths <부스이름1,부스이름2,...>
  python manage.py create_admin <admin_name> <password> [booth_name]

  # 조회
  python manage.py list_booths
  python manage.py list_admins

  # 삭제
  python manage.py delete_booth <booth_name>
  python manage.py delete_admin <admin_name>
  python manage.py delete_admin_by_id <admin_id>
""")
        return

    cmd = sys.argv[1]
    if cmd == 'import_students':
        csv_path = sys.argv[2]
        initial = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        tag = sys.argv[4] if len(sys.argv) > 4 else 'SCHOOLFEST'
        import_students(csv_path, initial, tag)
    elif cmd == 'create_booths':
        names = sys.argv[2].split(',')
        create_booths(names)
    elif cmd == 'create_admin':
        admin_name = sys.argv[2]
        password = sys.argv[3]
        booth_name = sys.argv[4] if len(sys.argv) > 4 else None
        create_admin(admin_name, password, booth_name)
    elif cmd == 'list_booths':
        list_booths()
    elif cmd == 'list_admins':
        list_admins()
    elif cmd == 'delete_booth':
        delete_booth(sys.argv[2])
    elif cmd == 'delete_admin':
        delete_admin(sys.argv[2])
    elif cmd == 'delete_admin_by_id':
        delete_admin_by_id(int(sys.argv[2]))
    elif cmd == 'assign_pins':
        length = int(sys.argv[2]) if len(sys.argv) > 2 else 8
        export = sys.argv[3] if len(sys.argv) > 3 else 'assigned_pins.csv'
        assign_pins(length, export)
    elif cmd == 'set_pin':
        student_id = sys.argv[2]
        pin = sys.argv[3]
        set_pin(student_id, pin)
    else:
        print('Unknown command.')

if __name__ == '__main__':
    main()
