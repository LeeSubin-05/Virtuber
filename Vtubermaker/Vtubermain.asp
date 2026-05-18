<%@CODEPAGE=65001 %>
<html>
<head>
<meta charset="utf-8">
<title>나만의 버튜버 만들기</title>
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
        font-family: 'Segoe UI', sans-serif;
        background: #f5f5f5;
        display: flex;
        justify-content: center;
        padding: 40px 20px;
    }

    .container {
        background: #fff;
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 2px 20px rgba(0,0,0,0.08);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 16px;
    }

    h1 {
        font-size: 22px;
        color: #1f1f1f;
        margin-bottom: 4px;
    }

    video, #photo {
        border-radius: 12px;
        display: block;
    }

    #photo {
        display: none;
    }

    /* 공통 버튼 베이스 */
    button {
        padding: 12px 28px;
        border: none;
        border-radius: 30px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        letter-spacing: 0.3px;
    }

    /* 사진 찍기 버튼 */
    #shootBtn {
        background: linear-gradient(135deg, #a78bfa, #7c3aed);
        color: white;
        box-shadow: 0 4px 14px rgba(124, 58, 237, 0.4);
    }
    #shootBtn:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(124, 58, 237, 0.5);
    }
    #shootBtn:active {
        transform: translateY(0);
    }

    /* 다시 찍기 + 확인 버튼 묶음 */
    #afterBtns {
        display: none;
        gap: 12px;
    }

    /* 다시 찍기 버튼 */
    #retakeBtn {
        background: #f3f4f6;
        color: #374151;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    #retakeBtn:hover {
        background: #e5e7eb;
        transform: translateY(-1px);
    }
    #retakeBtn:active {
        transform: translateY(0);
    }

    /* 확인 버튼 */
    #confirmBtn {
        background: linear-gradient(135deg, #34d399, #059669);
        color: white;
        box-shadow: 0 4px 14px rgba(5, 150, 105, 0.4);
    }
    #confirmBtn:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(5, 150, 105, 0.5);
    }
    #confirmBtn:active {
        transform: translateY(0);
    }
</style>
</head>
<body>
    <div class="container">
        <h1>사진 찍기</h1>
        <video id="video" width="360" height="270" autoplay></video>
        <canvas id="canvas" width="360" height="270" style="display:none;"></canvas>
        <img id="photo" width="360" height="270" src="">

        <!-- 사진 찍기 버튼 -->
        <button id="shootBtn" onclick="takePicture()">📷 사진 찍기</button>

        <!-- 촬영 후 버튼 묶음 -->
        <div id="afterBtns">
            <button id="retakeBtn" onclick="retake()">↩ 다시 찍기</button>
            <button id="confirmBtn" onclick="goNext()">✓ 확인</button>
        </div>
    </div>

    <script>
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const photo = document.getElementById('photo');

        // 카메라 스트림 열기
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(stream => {
                video.srcObject = stream;
            })
            .catch(err => {
                alert('카메라 접근 실패: ' + err.message);
            });

        function takePicture() {
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, 360, 270);

            // 이미지 데이터 추출
            const dataURL = canvas.toDataURL('image/png');
            photo.src = dataURL;

            // 비디오 숨기고 사진 보이기
            video.style.display = 'none';
            photo.style.display = 'block';

            // 버튼 전환: 사진찍기 숨기고 다시찍기+확인 표시
            document.getElementById('shootBtn').style.display = 'none';
            document.getElementById('afterBtns').style.display = 'flex';

            // 서버로 전송
            const params = new URLSearchParams();
            params.append("imgData", dataURL);

            fetch("picsave.asp", {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                body: params.toString()
            })
            .then(response => response.text())
            .then(result => {
                console.log("서버 응답:", result);
            })
            .catch(error => {
                console.error("전송 에러:", error);
                alert("전송 중 오류가 발생했습니다.");
            });
        }

        // 다시 찍기: 초기 상태로 복원
        function retake() {
            photo.src = '';
            photo.style.display = 'none';
            video.style.display = 'block';

            document.getElementById('shootBtn').style.display = 'inline-block';
            document.getElementById('afterBtns').style.display = 'none';
        }

        function goNext() {
            location.href = "VtubePalette.asp";
        }
    </script>
</body>
</html>