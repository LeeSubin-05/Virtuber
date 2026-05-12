import os
import json
import io
from PIL import Image
from google import genai
from google.genai import types

# ── 설정 ─────────────────────────────────────────────────
# 발급받은 Gemini API 키를 입력하세요
API_KEY = ""

# 파일 경로 설정 (사용자 환경에 맞게 수정)
PARTS_LIST_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\parts_list.json"
BASE_FEATURE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\baseFeature.json"
OUTPUT_JSON_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\prompts.json"

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
    당신은 VTube 아바타 제작을 위한 전문 프롬프트 엔지니어입니다.
    사용자의 사진과 요청사항을 분석하여, Stable Diffusion(gsdf 모델)에 최적화된 '부품별' 태그 리스트를 생성하세요.

    [핵심 작업 규칙]
    1. [우선순위]: 1. 파츠의 Role(역할) -> 2. 사용자 특징(색상/재질) -> 3. Silhouette(형태).
    2. [부품 고립]: 절대 전신이나 얼굴을 그리지 마세요. 오직 해당 '부품'의 질감과 색상에만 집중하세요.
    3. [배경 통제]: 모든 파츠의 배경은 "black background"로 설정하세요.
    4. [태그 압축]: 문장이 아닌 영문 태그(Comma-separated tags) 형식으로 작성하세요. 불필요한 설명(예: "A photo of...")은 절대 금지합니다.
    5. [색상 강조]: 사용자의 특징적인 색상을 최우선으로 반영하되, 원본의 색이 배어 나오지 않도록 "vibrant color, solid color" 키워드를 적절히 사용하세요.
    6. [형태 묘사]: 현재 파츠를 사용자에게서 찾아볼 수 없다면 투명하게 처리하세요. (예: "transparent, hidden")
    7. [출력 포맷]: 반드시 순수 JSON 형식으로만 응답하세요. {{"part_name": "tag1, tag2, tag3", ...}}

    [참조 파츠 명세 (baseFeature)]
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
    instruction = "사진 속 나의 흑발 생머리와 깔끔한 검정색 옷 스타일을 그대로 아바타에 적용해줘."

    result = generate_part_prompts(input_user_photo, instruction)

    if result:
        # 결과 저장
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        
        print(f"\n[SUCCESS] {len(result)}개 파츠에 대한 프롬프트가 {OUTPUT_JSON_PATH}에 저장되었습니다.")
        # 간단한 확인
        print("샘플 (hair_back):", result.get("hair_back", "N/A"))