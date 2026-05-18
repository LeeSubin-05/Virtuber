import os
import sys
import json
import io
from PIL import Image
from google import genai
from google.genai import types

# scripts 폴더에서 상위 Virtuber 폴더의 config.py를 찾도록 경로를 추가
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import JSON_PATH, FEATURE_PATH, DATA_DIR

# ── 설정 ─────────────────────────────────────────────────
# 발급받은 Gemini API 키를 입력하세요
API_KEY = ""

# 파일 경로 설정 (환경변수에서 로드)
PARTS_LIST_PATH = os.path.join(DATA_DIR, "parts_list.json")
BASE_FEATURE_PATH = FEATURE_PATH
OUTPUT_JSON_PATH = JSON_PATH

# ── 함수 정의 ─────────────────────────────────────────────

def generate_part_prompts(user_image_path, user_instruction):
    client = genai.Client(api_key=API_KEY)
    
    # 1. 파츠 데이터 및 설명 로드
    try:
        with open(PARTS_LIST_PATH, "r", encoding="utf-8") as f:
            part_names = json.load(f)
        with open(BASE_FEATURE_PATH, "r", encoding="utf-8") as f:
            base_features = json.load(f)
    except Exception as e:
        print(f"[ERROR] JSON 파일 로드 실패: {e}")
        return None

    # 2. 이미지 데이터 로드
    if not os.path.exists(user_image_path):
        print(f"[ERROR] 이미지 파일이 없습니다: {user_image_path}")
        return None
    
    with open(user_image_path, "rb") as f:
        user_img_bytes = f.read()

    # 3. AI에게 전달할 시스템 지시문 작성
    # 파츠별 Role 정보를 포함하여 Gemini가 각 부품의 위치를 이해하게 함
    system_prompt = f"""
    당신은 Stable Diffusion(gsdf 모델) 전용 고성능 프롬프트 엔지니어입니다.
    사용자 사진을 분석하여 각 파츠와 매칭되는 부분의 색깔을 추출하는 것이 당신의 역할입니다.

    [핵심 출력 규칙]
    1. [형식]: 각 파츠별 프롬프트는 JSON 객체로 반환되어야 합니다. 키는 파츠 이름, 값은 해당 파츠에 대한 프롬프트입니다.
    2. [내용]: 프롬프트는 사진 속 해당 파츠의 색깔만을 강력한 소문자 영문 키워드로 표시해야 합니다. 절대로 형태를 묘사해선 안됩니다. 예시) "hair_back": "black", "shirt_shoulder_left": "black" (형태 묘사 X)
    3. [참고사항]: 파츠의 색을 저장할 때, 여러 색깔이 혼재되어 나타난다면 위치에 맞게 여러 색깔을 나열해도 좋습니다. 예시) "hair_back": "top: black, middle: dark brown, bottom: light brown" (형태 묘사 X)
    3-1. 특정 색깔이 나머지 부분을 압도적으로 지배하는 경우, 해당 색깔을 단일 키워드로 표현해도 좋습니다. 이 때, 앞에 whole이라는 수식어를 반드시 추가합니다. 예시) "hair_back": "whole black" (형태 묘사 X)
    3-2. 결과 프롬프트의 색상이 단 한개일 경우, 앞에 pure라는 수식어를 반드시 추가해야 합니다. 예시) "hair_back": "pure black" (형태 묘사 X)
    4. [피부색] 피부 색깔은 json의 마지막 항목으로 지정되어야 하며, 키는 "skin"으로 고정되어야 합니다. 또한 값은 hexcode로 표현되어야 합니다. 예시) "skin": "#f5c9b8"
    5. [눈동자 색] 눈동자 색깔의 값 또한 hexcode로 표현되어야 합니다. 필요하다면 두 값이 다를 수 있습니다. 예시) "eye_left": "#a52a2a", "eye_right": "#00ff00"
    [참조 파츠 명세]
    {json.dumps(base_features, ensure_ascii=False, indent=2)}
    """

    print("⏳ Gemini가 파츠별 프롬프트를 생성 중입니다...")
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", # 최신 모델 사용
            contents=[
                system_prompt,
                "사용자 요청사항: " + user_instruction,
                types.Part.from_bytes(data=user_img_bytes, mime_type="image/jpeg")
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", # JSON 응답 강제
                temperature=0.7
            )
        )
        
        # JSON 파싱 및 결과 반환
        return json.loads(response.text)
        
    except Exception as e:
        print(f"[ERROR] Gemini API 호출 중 오류 발생: {e}")
        return None

# ── 실행부 ───────────────────────────────────────────────

if __name__ == "__main__":
    # 테스트용 설정
    input_user_photo = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\user.png"
    instruction = "눈동자가 오드아이였으면 좋겠어요. 그리고 피부색은 오크처럼 되었으면 좋겠어"

    result = generate_part_prompts(input_user_photo, instruction)

    if result:
        # 결과 저장
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        
        print(f"\n[SUCCESS] {len(result)}개 파츠에 대한 프롬프트가 {OUTPUT_JSON_PATH}에 저장되었습니다.")
        # 간단한 확인
        print("샘플 (hair_back):", result.get("hair_back", "N/A"))