<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>나만의 버튜버 만들기</title>
    <style>
        /* 모든 요소의 박스 크기 계산 방식을 border-box로 통일하고 기본 여백 초기화 */
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Segoe UI', sans-serif;
            background: #f5f5f5;
            display: flex;
            justify-content: center; /* 가로 방향 가운데 정렬 */
            padding: 40px 20px;
        }

        /* 전체 카드 컨테이너 */
        .container {
            width: 480px;
            background: #fff;
            border-radius: 16px;
            padding: 32px;
            box-shadow: 0 2px 20px rgba(0,0,0,0.08);
        }

        h1 {
            font-size: 18px;
            font-weight: 600;
            color: #111;
            margin-bottom: 28px;
        }

        /* 눈/머리/피부 색상 각각의 섹션 래퍼 */
        .section { margin-bottom: 32px; }

        /* 섹션 제목 레이블 (예: "눈 색상") */
        .section-label {
            font-size: 13px;
            font-weight: 600;
            color: #666;
            margin-bottom: 12px;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* 미리보기 박스 + 컨트롤을 가로로 나란히 배치하는 행 */
        .picker-row {
            display: flex;
            gap: 14px;
            align-items: flex-start;
        }

        /* 선택된 색상을 실시간으로 표시하는 정사각형 미리보기 박스 */
        .preview-box {
            width: 72px;
            height: 72px;
            border-radius: 10px;
            border: 1px solid rgba(0,0,0,0.1);
            flex-shrink: 0; /* 공간이 부족해도 크기 유지 */
            background: #000;
        }

        /* 미리보기 박스 하단의 HEX 코드 텍스트 */
        .hex-text {
            font-size: 11px;
            font-family: monospace;
            color: #999;
            margin-top: 5px;
            text-align: center;
        }

        /* 색상 팔레트 캔버스 + 색조 슬라이더를 세로로 쌓는 컬럼 래퍼 */
        .picker-controls {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        /* 채도·명도 그라디언트 캔버스의 상대 위치 컨테이너 (커서 오버레이 기준점) */
        .canvas-wrap {
            position: relative;
            width: 100%;
            height: 110px;
            border-radius: 8px;
            overflow: hidden;
            cursor: crosshair; /* 십자 커서로 드래그 UX 표현 */
        }

        .canvas-wrap canvas { display: block; width: 100%; height: 100%; }

        /* 현재 선택 위치를 나타내는 원형 커서 도트 (캔버스 위에 절대 위치로 표시) */
        .cursor-dot {
            position: absolute;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid #fff;
            box-shadow: 0 0 0 1px rgba(0,0,0,0.35);
            pointer-events: none; /* 마우스 이벤트를 캔버스에 통과시킴 */
            transform: translate(-50%, -50%); /* 중심점 기준으로 위치 보정 */
        }

        /* 색조(Hue) 선택 슬라이더 — 무지개 그라디언트 배경 */
        .hue-slider {
            -webkit-appearance: none;
            appearance: none;
            width: 100%;
            height: 12px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            outline: none;
            /* 0°(빨강) → 60°(노랑) → 120°(초록) → 180°(청록) → 240°(파랑) → 300°(마젠타) → 360°(빨강) */
            background: linear-gradient(to right,
                #f00 0%, #ff0 17%, #0f0 33%,
                #0ff 50%, #00f 67%, #f0f 83%, #f00 100%);
        }

        /* 슬라이더 thumb(핸들) 스타일 — 크로스브라우저 대응 */
        .hue-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #fff;
            border: 2px solid rgba(0,0,0,0.3);
            cursor: pointer;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
        }

        .hue-slider::-moz-range-thumb {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #fff;
            border: 2px solid rgba(0,0,0,0.3);
            cursor: pointer;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
        }

        /* 섹션 구분선 */
        .divider {
            border: none;
            border-top: 1px solid #eee;
            margin: 0 0 28px;
        }

        /* JSON 저장 버튼 */
        .save-btn {
            width: 100%;
            padding: 12px;
            margin-top: 4px;
            border-radius: 10px;
            border: 1px solid #ddd;
            background: #f9f9f9;
            color: #111;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s;
        }

        .save-btn:hover { background: #f0f0f0; }
        .save-btn:active { background: #e8e8e8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>색상 선택도구</h1>

        <!-- 눈 색상 섹션 -->
        <div class="section">
            <p class="section-label">눈 색상</p>
            <div class="picker-row">
                <div>
                    <!-- 선택된 눈 색상 미리보기 + HEX 코드 표시 -->
                    <div class="preview-box" id="prev-eye"></div>
                    <p class="hex-text" id="hex-eye">#000000</p>
                </div>
                <div class="picker-controls">
                    <!-- 채도·명도 팔레트 캔버스 (드래그로 색상 선택) -->
                    <div class="canvas-wrap" id="cw-eye">
                        <canvas id="cv-eye"></canvas>
                        <!-- 현재 선택 위치 표시 커서 -->
                        <div class="cursor-dot" id="cur-eye"></div>
                    </div>
                    <!-- 색조(Hue) 슬라이더 (기본값: 200 = 하늘색 계열) -->
                    <input type="range" class="hue-slider" id="hue-eye" min="0" max="360" value="200" step="1">
                </div>
            </div>
        </div>

        <hr class="divider">

        <!-- 머리 색상 섹션 -->
        <div class="section">
            <p class="section-label">머리 색상</p>
            <div class="picker-row">
                <div>
                    <!-- 선택된 머리 색상 미리보기 + HEX 코드 표시 -->
                    <div class="preview-box" id="prev-hair"></div>
                    <p class="hex-text" id="hex-hair">#000000</p>
                </div>
                <div class="picker-controls">
                    <!-- 채도·명도 팔레트 캔버스 -->
                    <div class="canvas-wrap" id="cw-hair">
                        <canvas id="cv-hair"></canvas>
                        <div class="cursor-dot" id="cur-hair"></div>
                    </div>
                    <!-- 색조 슬라이더 (기본값: 30 = 주황/갈색 계열) -->
                    <input type="range" class="hue-slider" id="hue-hair" min="0" max="360" value="30" step="1">
                </div>
            </div>
        </div>

        <hr class="divider">

        <!-- 피부 색상 섹션 -->
        <div class="section">
            <p class="section-label">피부 색상</p>
            <div class="picker-row">
                <div>
                    <!-- 선택된 피부 색상 미리보기 + HEX 코드 표시 -->
                    <div class="preview-box" id="prev-skin"></div>
                    <p class="hex-text" id="hex-skin">#000000</p>
                </div>
                <div class="picker-controls">
                    <!-- 채도·명도 팔레트 캔버스 -->
                    <div class="canvas-wrap" id="cw-skin">
                        <canvas id="cv-skin"></canvas>
                        <div class="cursor-dot" id="cur-skin"></div>
                    </div>
                    <!-- 색조 슬라이더 (기본값: 20 = 살색/베이지 계열) -->
                    <input type="range" class="hue-slider" id="hue-skin" min="0" max="360" value="20" step="1">
                </div>
            </div>
        </div>

        <!-- 세 가지 색상 데이터를 JSON 파일로 내려받는 버튼 -->
        <button class="save-btn" id="saveBtn">💾 저장</button>
    </div>

    <script>
        /**
         * 전역 색상 상태 객체
         * 각 파트(eye/hair/skin)별로 현재 선택된 RGB 값과 HEX 코드를 저장.
         * saveBtn 클릭 시 이 객체를 직렬화하여 JSON 파일로 내보낸다.
         */
        var colorState = {
            eye:  { r: 0, g: 0, b: 0, hex: '#000000' },
            hair: { r: 0, g: 0, b: 0, hex: '#000000' },
            skin: { r: 0, g: 0, b: 0, hex: '#000000' }
        };

        /**
         * HSV → RGB 변환 함수
         * @param {number} h - 색조 (Hue), 0~360
         * @param {number} s - 채도 (Saturation), 0~1
         * @param {number} v - 명도 (Value), 0~1
         * @returns {number[]} [r, g, b] 각 0~255 정수
         *
         * HSV 색공간을 6개 구간(i)으로 나눠 보간(f)을 통해 RGB를 계산한다.
         */
        function hsvToRgb(h, s, v) {
            var i = Math.floor(h / 60) % 6; // 60° 단위 구간 인덱스 (0~5)
            var f = h / 60 - Math.floor(h / 60); // 구간 내 소수 부분 (보간 비율)
            var p = v * (1 - s);           // 채도 0일 때의 하한값
            var q = v * (1 - f * s);       // 하강 보간값
            var t = v * (1 - (1 - f) * s); // 상승 보간값
            var r, g, b;
            // 구간별 RGB 매핑
            if (i === 0) { r = v; g = t; b = p; }       // 빨강 → 노랑
            else if (i === 1) { r = q; g = v; b = p; }  // 노랑 → 초록
            else if (i === 2) { r = p; g = v; b = t; }  // 초록 → 청록
            else if (i === 3) { r = p; g = q; b = v; }  // 청록 → 파랑
            else if (i === 4) { r = t; g = p; b = v; }  // 파랑 → 마젠타
            else { r = v; g = p; b = q; }                // 마젠타 → 빨강
            return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
        }

        /**
         * 정수 n을 2자리 16진수 문자열로 변환 (예: 12 → "0c", 255 → "ff")
         */
        function toHex2(n) { return n.toString(16).padStart(2, '0'); }

        /**
         * Canvas에 채도·명도 그라디언트를 그리는 함수
         * - 가로: 흰색(왼쪽) → 순색(오른쪽) 채도 그라디언트
         * - 세로: 투명(위) → 검정(아래) 명도 그라디언트 (겹쳐 그림)
         * @param {HTMLCanvasElement} canvas
         * @param {number} hue - 현재 선택된 색조 (0~360)
         */
        function drawGradient(canvas, hue) {
            var ctx = canvas.getContext('2d');
            var w = canvas.width, h = canvas.height;
            var base = hsvToRgb(hue, 1, 1); // 해당 색조의 순색 (채도·명도 최대)

            ctx.clearRect(0, 0, w, h);

            // 1단계: 흰색 → 순색 가로 그라디언트 (채도축)
            var gW = ctx.createLinearGradient(0, 0, w, 0);
            gW.addColorStop(0, '#fff');
            gW.addColorStop(1, 'rgb(' + base[0] + ',' + base[1] + ',' + base[2] + ')');
            ctx.fillStyle = gW;
            ctx.fillRect(0, 0, w, h);

            // 2단계: 투명 → 검정 세로 그라디언트를 덧씌움 (명도축)
            var gB = ctx.createLinearGradient(0, 0, 0, h);
            gB.addColorStop(0, 'rgba(0,0,0,0)');
            gB.addColorStop(1, '#000');
            ctx.fillStyle = gB;
            ctx.fillRect(0, 0, w, h);
        }

        /**
         * 개별 색상 피커를 초기화하고 이벤트를 연결하는 함수
         * @param {string} id       - 피커 식별자 ('eye' | 'hair' | 'skin')
         * @param {number} initHue  - 초기 색조 값 (0~360)
         * @param {number} initSx   - 초기 채도 위치 (0~1, 캔버스 x 비율)
         * @param {number} initSy   - 초기 명도 위치 (0~1, 캔버스 y 비율)
         */
        function setupPicker(id, initHue, initSx, initSy) {
            // DOM 요소 참조
            var canvas    = document.getElementById('cv-'   + id);
            var wrap      = document.getElementById('cw-'   + id);
            var hueSlider = document.getElementById('hue-'  + id);
            var cursor    = document.getElementById('cur-'  + id);
            var preview   = document.getElementById('prev-' + id);
            var hexSpan   = document.getElementById('hex-'  + id);

            // 이 피커의 내부 상태: 현재 색조·채도 위치·명도 위치
            var state = { hue: initHue, sx: initSx, sy: initSy };

            /**
             * 캔버스 크기를 실제 DOM 크기에 맞게 동기화하고 그라디언트를 다시 그림.
             * 레이아웃 변경(창 크기 조절 등) 시 호출된다.
             */
            function resize() {
                canvas.width  = wrap.clientWidth  || 320;
                canvas.height = wrap.clientHeight || 110;
                drawGradient(canvas, state.hue);
            }

            /**
             * 현재 state(hue, sx, sy)를 기반으로 색상을 계산하고 UI를 갱신.
             * - 미리보기 박스 배경색 변경
             * - HEX 코드 텍스트 갱신
             * - 커서 도트 위치 이동
             * - 전역 colorState 객체 업데이트
             */
            function updateColor() {
                // sy가 0(위)일수록 밝고, 1(아래)일수록 어두움 → v = 1 - sy
                var rgb = hsvToRgb(state.hue, state.sx, 1 - state.sy);
                var hex = '#' + toHex2(rgb[0]) + toHex2(rgb[1]) + toHex2(rgb[2]);

                preview.style.background = hex;
                hexSpan.textContent = hex.toUpperCase();

                // 커서 도트를 선택 위치(%)로 이동
                cursor.style.left = (state.sx * 100) + '%';
                cursor.style.top  = (state.sy * 100) + '%';

                // 전역 상태 저장 (JSON 저장 시 사용)
                colorState[id] = { r: rgb[0], g: rgb[1], b: rgb[2], hex: hex.toUpperCase() };
            }

            /**
             * 마우스/터치 이벤트에서 캔버스 내 상대 좌표를 계산하여 색상 위치 갱신.
             * @param {MouseEvent|TouchEvent} e
             */
            function pickAt(e) {
                var rect = canvas.getBoundingClientRect();
                // 터치 이벤트와 마우스 이벤트 모두 처리
                var cx = e.touches ? e.touches[0].clientX : e.clientX;
                var cy = e.touches ? e.touches[0].clientY : e.clientY;
                // 캔버스 범위(0~1)로 정규화 후 클램핑
                state.sx = Math.max(0, Math.min(1, (cx - rect.left)  / rect.width));
                state.sy = Math.max(0, Math.min(1, (cy - rect.top)   / rect.height));
                updateColor();
            }

            // ── 마우스 드래그 이벤트 ──────────────────────────────────────
            var dragging = false;
            wrap.addEventListener('mousedown', function (e) { dragging = true; pickAt(e); });
            // mousemove·mouseup은 document에 걸어 캔버스 밖으로 드래그해도 동작하도록 함
            document.addEventListener('mousemove', function (e) { if (dragging) pickAt(e); });
            document.addEventListener('mouseup',   function ()  { dragging = false; });

            // ── 터치 이벤트 (모바일 대응) ────────────────────────────────
            wrap.addEventListener('touchstart', function (e) { e.preventDefault(); pickAt(e); }, { passive: false });
            wrap.addEventListener('touchmove',  function (e) { e.preventDefault(); pickAt(e); }, { passive: false });

            // ── 색조 슬라이더 변경 이벤트 ────────────────────────────────
            hueSlider.addEventListener('input', function () {
                state.hue = parseInt(this.value);
                drawGradient(canvas, state.hue); // 새 색조로 팔레트 다시 그림
                updateColor();
            });

            // 초기화: 캔버스 크기 설정 및 초기 색상 표시
            resize();
            updateColor();

            // 창 크기 변경 시 캔버스 리사이즈
            window.addEventListener('resize', resize);
        }

        // ── 각 피커 초기화 ───────────────────────────────────────────────
        // setupPicker(id, 초기색조, 초기채도위치, 초기명도위치)
        setupPicker('eye',  200, 0.9, 0.1); // 눈: 하늘색 계열, 높은 채도·밝음
        setupPicker('hair',  30, 0.75, 0.45); // 머리: 갈색 계열, 중간 채도·명도
        setupPicker('skin',  20, 0.4, 0.2);  // 피부: 베이지 계열, 낮은 채도·밝음

        /**
         * JSON 저장 버튼 클릭 핸들러
         * 현재 세 가지 색상(eye/hair/skin)의 RGB + HEX 데이터를
         * 'colors.json' 파일로 사용자 기기에 다운로드한다.
         */
        document.getElementById('saveBtn').addEventListener('click', function () {
            // colorState에서 필요한 값만 추출하여 저장용 객체 구성
            var data = {
                eye:  { r: colorState.eye.r,  g: colorState.eye.g,  b: colorState.eye.b,  hex: colorState.eye.hex  },
                hair: { r: colorState.hair.r, g: colorState.hair.g, b: colorState.hair.b, hex: colorState.hair.hex },
                skin: { r: colorState.skin.r, g: colorState.skin.g, b: colorState.skin.b, hex: colorState.skin.hex }
            };

            // JSON 직렬화 (들여쓰기 2칸으로 가독성 확보)
            var json = JSON.stringify(data, null, 2);

            // Blob → Object URL → <a> 클릭 방식으로 파일 다운로드 트리거
            var blob = new Blob([json], { type: 'application/json' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'colors.json';
            a.click();

            // 메모리 누수 방지를 위해 Object URL 즉시 해제
            URL.revokeObjectURL(url);
        });
    </script>
</body>
</html>