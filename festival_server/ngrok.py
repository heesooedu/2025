import qrcode

url = 'https://d6058c1919d1.ngrok-free.app'  # ngrok에서 얻은 HTTPS URL
qr = qrcode.make(url)

qr.save('student_login_qr.png')  # QR 코드 저장