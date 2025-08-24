# 🎉 학교 축제 서버 (Flask + Socket.IO)

500명 동시 접속을 고려한 간단한 실시간 웹앱입니다.
- 부스 대기열 실시간 반영
- QR 스캔으로 포인트 증감
- 실시간 TOP10 랭킹
- 부스별 홍보 이미지/소개 업로드
- 관리자/슈퍼관리자 계정

## 1) 설치
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
```

## 2) 최초 DB 생성 & 관리자 만들기
```bash
# DB 생성
flask --app app.py create-db

# 슈퍼관리자 생성(대화형)
flask --app app.py create-superadmin
```

## 3) 학생 CSV 가져오기 & QR 생성
CSV 예시(`students.csv`):
```
student_id,name,points
20230101,홍길동,100
20230102,김철수,100
```
실행:
```bash
python manage.py import_students students.csv 100 SCHOOLFEST
```
- `qr-codes/` 폴더에 PNG가 생성됩니다(인쇄용).

## 4) 부스 만들기 & 관리자 계정 연결
```bash
python manage.py create_booths "게임부스,노래방,먹거리,체험A,체험B,사진관,보물찾기,방탈출,미술,IT"
python manage.py create_admin game_manager P@ssw0rd! "게임부스"
```
- 관리자 아이디는 **표시이름**으로 로그인합니다.
- 슈퍼관리자는 모든 부스 접근 가능, 일반 관리자는 지정 부스만.

## 5) 실행
```bash
python app.py
# 브라우저에서 http://<서버IP>:5000
```
- 같은 와이파이의 스마트폰에서 접속하려면 **서버의 내부 IP**를 사용하세요(예: `http://192.168.0.23:5000`).

## 6) 사용법
- **홈**: 부스 리스트, 대기열, TOP10 실시간 표시
- **관리자 로그인**: 관리자 대시보드 → 대기열 수정, 홍보글/이미지 업로드
- **QR 스캔**: 각 부스 카드의 *QR 스캔* 버튼 → 카메라로 학생 QR 스캔 → 포인트 증감

## 7) 운영 팁
- 동시접속 500명 수준은 i7-12700 + eventlet 환경에서 충분히 처리 가능(정적 리소스는 Nginx로 서빙하면 더 안정적).
- 와이파이 AP가 여러 개라면 **서버 IP가 모두에게 라우팅**되는지 사전 점검하세요.
- `SECRET_KEY`는 운영 전에 환경변수로 바꾸세요.
- html5-qrcode를 내부망에서도 쓰려면 `static/`에 파일로 내려받아 로컬에서 서빙하세요.

## 8) 디자인
- Tailwind CDN 사용(인터넷 필요). 내부망-only 환경이면 빌드된 CSS 파일을 동일 경로로 교체하세요.

행사 끝나고 **`transaction` 테이블**로 부스별 사용량, 인기 부스, 포인트 분포 등을 분석할 수 있습니다.
