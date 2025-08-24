# webserver.py
# 튜링테스트 실험해보기


import http.server
import socketserver
import threading

# --- 게임 데이터 ---
click_count = 0
lock = threading.Lock()

# --- 웹페이지 내용 (수정됨) ---
# CSS와 JavaScript의 중괄호 { } 를 {{ }} 로 바꿔서 파이썬 포매팅 에러를 방지합니다.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>함께하는 클릭 게임!</title>
    <style>
        body {{ 
            font-family: 'Malgun Gothic', sans-serif; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            height: 100vh; 
            background-color: #f0f7ff; 
            margin: 0;
            flex-direction: column;
        }}
        .container {{
            text-align: center;
            background-color: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }}
        h1 {{ 
            color: #333; 
        }}
        #count {{ 
            font-size: 5em; 
            color: #007bff; 
            font-weight: bold;
            margin: 20px 0;
        }}
        button {{
            padding: 15px 30px;
            font-size: 1.5em;
            cursor: pointer;
            border: none;
            background-color: #007bff;
            color: white;
            border-radius: 10px;
            transition: background-color 0.2s;
        }}
        button:hover {{
            background-color: #0056b3;
        }}
    </style>
</head>
<body>

    <div class="container">
        <h1>함께하는 클릭 게임!</h1>
        <p>친구들과 함께 버튼을 클릭해서 숫자를 올려보세요!</p>
        <div id="count">{count}</div>
        <button onclick="handleClick()">클릭!</button>
    </div>

    <script>
        // 버튼을 클릭했을 때 호출되는 함수
        function handleClick() {{
            // 서버의 /click 주소로 요청을 보냅니다.
            fetch('/click')
                .then(response => response.text()) // 응답을 텍스트로 변환
                .then(newCount => {{
                    // 서버로부터 받은 새로운 숫자로 화면을 업데이트합니다.
                    document.getElementById('count').innerText = newCount;
                }});
        }}
    </script>

</body>
</html>
"""

class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global click_count
        
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.format(count=click_count).encode('utf-8'))
        
        elif self.path == '/click':
            with lock:
                click_count += 1
            
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(str(click_count).encode('utf-8'))
            
        else:
            # favicon.ico 요청 등은 무시하도록 간단히 404 처리
            self.send_error(404, "File Not Found: {}".format(self.path))

# --- 서버 실행 ---
PORT = 8000
Handler = MyHttpRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("-------------------------------------------------")
    print(f"서버가 포트 {PORT} 에서 실행 중입니다.")
    print("서버를 중지하려면 터미널에서 Ctrl + C 를 누르세요.")
    print("-------------------------------------------------")
    print("나의 접속 주소: http://localhost:8000")
    print("친구에게 알려줄 주소는 아래 '내부 IP 찾기'를 참고하세요!")
    httpd.serve_forever()