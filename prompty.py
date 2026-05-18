import os
import json
import google.generativeai as genai
from PIL import Image

# ── 설정 ─────────────────────────────────────────────────
# 발급받은 Gemini API 키를 입력하세요 (환경 변수 권장)
API_KEY = "AIzaSyCw9_Jpa_0hyy3fD8ak1zeeKzoxzRw9fxA"  # 실제 API 키로 교체하세요
genai.configure(api_key=API_KEY)

# 멀티모달 모델 설정 (gemini-1.5-flash 또는 pro 권장)
model = genai.GenerativeModel('gemini-2.5-flash')

# 이전 단계에서 사용한 파츠 이름 리스트
PART_NAMES = [
    "hair_long_back_left", "hair_bangs_center_set", "hair_pink_twin_set", 
    "hair_or_accessory_purple_lower_left_candidate", "bunny_ears_pair", 
    "face_head_base_set", "face_expression_eye_set", "upper_body_outfit_set", 
    "skirt", "legs_stockings_pair", "shoes_pair", "shorts_underwear", 
    "lower_leg_boots_socks_set", "arm_hand_set", "small_detached_body_parts", 
    "ribbon_bow_accessory_set", "effect_symbols_top_right", "small_top_center_parts"
]

def generate_part_prompts(face_image_path, user_request_text):
    """
    사용자 얼굴 이미지와 텍스트 요청을 분석하여 파츠별 수정 프롬프트를 JSON 형태로 반환합니다.
    """
    try:
        # 1. 사용자 얼굴 이미지 로드
        img = Image.open(face_image_path)
    except Exception as e:
        print(f"[ERROR] 이미지를 불러올 수 없습니다: {e}")
        return None

    # 2. AI에게 내릴 시스템 프롬프트 작성 (프롬프트 엔지니어링 핵심)
    system_instruction = f"""
    당신은 Vtube 캐릭터 에셋 수정 전문가입니다.
    사용자의 얼굴 사진과 텍스트 요구사항을 분석하여, Vtube 모델의 각 파츠를 어떻게 수정해야 할지 구체적인 프롬프트(지시사항)를 작성해주세요.
    
    [텍스트 요구사항]
    "{user_request_text}"
    
    [규칙]
    1. 사진에 나타난 사용자의 특징(눈 모양, 머리 색상 등)을 분석하여 텍스트 요구사항과 융합하세요.
    2. 응답은 반드시 아래 제공된 파츠 이름들을 Key로 가지는 JSON 형식이어야 합니다.
    3. 수정이 필요 없는 파츠는 값을 null로 설정하세요.
    4. 프롬프트는 이미지 변형 알고리즘(예: Stable Diffusion Inpainting, OpenCV 색상 변환 등)에 바로 입력할 수 있도록 구체적인 영단어 키워드 위주로 작성하는 것이 좋습니다.
    
    [파츠 리스트]
    {', '.join(PART_NAMES)}
    
    [JSON 출력 예시]
    {{
        "hair_bangs_center_set": "black color, short length, straight bangs",
        "face_expression_eye_set": "sharp eyes, slightly slanted upwards, dark brown iris",
        "upper_body_outfit_set": "change color to navy blue based on text request",
        ...
    }}
    """

    # 3. 모델에 이미지와 프롬프트 전송
    print("[INFO] AI가 이미지와 텍스트를 분석 중입니다...")
    response = model.generate_content([system_instruction, img])

    # 4. 결과값 정리 (마크다운 백틱 제거 및 JSON 파싱)
    result_text = response.text.strip()
    if result_text.startswith("```json"):
        result_text = result_text[7:-3].strip()
    elif result_text.startswith("```"):
        result_text = result_text[3:-3].strip()

    try:
        prompts_json = json.loads(result_text)
        return prompts_json
    except json.JSONDecodeError:
        print("[ERROR] JSON 파싱 실패. AI 응답이 올바른 형식이 아닙니다.")
        print("원본 응답:\n", result_text)
        return None

# ── 실행 테스트 ──────────────────────────────────────────
if __name__ == "__main__":
    # 1. 설정
    test_image_path = "user.jpg"  # 실제 사용자 사진 경로
    user_text = "사진의 내 모습을 최대한 살려서 만들어줘."
    output_json_path = "prompts.json"  # 저장할 파일 이름
    
    # 이미지 파일 존재 여부 체크 (테스트용 더미 생성 로직은 유지)
    if not os.path.exists(test_image_path):
        print(f"[INFO] 테스트를 위해 {test_image_path} 더미 이미지를 생성합니다.")
        Image.new('RGB', (100, 100), color = 'white').save(test_image_path)
        
    # 2. 프롬프트 생성 요청
    generated_prompts = generate_part_prompts(test_image_path, user_text)
    
    # 3. 결과물 처리 및 파일 저장
    if generated_prompts:
        print("\n[SUCCESS] 파츠별 변형 프롬프트 생성 완료")
        
        # JSON 파일로 저장
        try:
            with open(output_json_path, "w", encoding="utf-8") as f:
                # indent=4: 보기 좋게 들여쓰기, ensure_ascii=False: 한글 깨짐 방지
                json.dump(generated_prompts, f, indent=4, ensure_ascii=False)
            
            print(f"[OK] 결과가 성공적으로 저장되었습니다: {os.path.abspath(output_json_path)}")
            
            # 콘솔에도 확인용 출력
            print(json.dumps(generated_prompts, indent=4, ensure_ascii=False))
            
        except Exception as e:
            print(f"[ERROR] 파일 저장 중 오류 발생: {e}")