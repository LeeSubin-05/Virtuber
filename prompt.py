import os
import json
import google.generativeai as genai
from PIL import Image

# ── 사용 ─────────────────────────────────────────────────
# pip install google-generativeai Pillow

# python prompt.py

# ── 설정 ─────────────────────────────────────────────────
# 발급받은 Gemini API 키를 입력하세요 (환경 변수 권장)
API_KEY = "AIzaSyDE_ywwdmE6jOKyMLpk779SQj-SvwFfPAc"
genai.configure(api_key=API_KEY)

# 멀티모달 모델 설정 (gemini-1.5-flash 또는 pro 권장)
model = genai.GenerativeModel('gemini-2.5-flash')

PARTS_LIST_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\parts\parts_list.json"
BASE_FEATURE_PATH = "baseFeature.json"

try:
    with open(PARTS_LIST_PATH, "r", encoding="utf-8") as f:
        PART_NAMES = json.load(f)
    print(f"[INFO] 파츠 리스트({len(PART_NAMES)}개)를 성공적으로 불러왔습니다.")
except FileNotFoundError:
    print(f"[ERROR] 파츠 리스트 파일이 없습니다. 먼저 parts.py를 실행해주세요: {PARTS_LIST_PATH}")
    PART_NAMES = [] # 오류 방지용 빈 리스트

PART_DESCRIPTIONS = {}
try:
    with open(BASE_FEATURE_PATH, "r", encoding="utf-8") as f:
        base_features = json.load(f)
        
    for part, features in base_features.items():
        # 각 요소들을 하나의 가이드라인 텍스트로 통합
        description = (
            f"Role: {features.get('role', '')}\n"
            f"- Silhouette: {features.get('silhouette', '')}\n"
            f"- Color Identity: {features.get('color', '')}\n"
            f"- Lighting: {features.get('light', '')}\n"
            f"- Boundary: {features.get('boundary', '')}"
        )
        PART_DESCRIPTIONS[part] = description
    print(f"[INFO] baseFeature로부터 {len(PART_DESCRIPTIONS)}개의 정밀 명세를 로드했습니다.")
except FileNotFoundError:
    print(f"[ERROR] baseFeature.json 파일을 찾을 수 없습니다: {BASE_FEATURE_PATH}")

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

    # 2. AI에게 내릴 시스템 프롬프트 작성
    system_instruction = f"""
    당신은 Vtube Studio 프로그램의 캐릭터 Akari의 파츠 수정 전문가입니다.
    사용자의 얼굴 사진과 텍스트 요구사항을 분석하여, Vtube 모델의 각 파츠를 어떻게 수정해야 할지 구체적인 프롬프트(지시사항)를 작성해주세요.
    
    [각 파츠별 역할 및 특징 설명]
    이후에 나타날 json 형식의 파일은 다음과 같이 이루어져 있습니다.
        - Key: 파츠의 영문 ID (예: "hair_outter", "face_expression_eye_set" 등)
        - Value: 해당 파츠의 역할과 특징을 설명하는 텍스트 (예: "Role: hair_outter\n- Silhouette: ...\n- Color Identity: ...\n- Lighting: ...\n- Boundary: ...")
        또한, 각 Value는 해당 파츠의 '역할(Role)', '실루엣(Silhouette)', '색상 정체성(Color Identity)', '조명(Lighting)', '경계(Boundary)'에 대한 상세 설명을 포함하고 있습니다.
    {json.dumps(PART_DESCRIPTIONS, indent=2)}

    [텍스트 요구사항]
    "{user_request_text}"
    
    [규칙]
    1. 사진에 나타난 사용자의 특징(눈 모양, 머리 색상 등)을 분석하여 텍스트 요구사항과 융합하세요.
    2. 응답은 반드시 아래 제공된 파츠의 '영문 ID'들을 Key로 가지는 JSON 형식이어야 합니다.
    3. 각 파츠의 '설명'을 참고하여 해당 부위에 맞는 올바른 지시사항을 작성하세요.
    4. 수정이 필요 없는 파츠는 값을 null로 설정하세요. (예: 배경 머리카락이나 효과 기호 등 변경이 불필요한 경우)
    5. 프롬프트는 이미지 변형 알고리즘(예: Stable Diffusion)에 바로 입력할 수 있도록 구체적인 영단어 키워드 위주로 작성하세요.
    6. 크기나 규격이 변경된다면 반드시 원본 특징보다 얼마나 더 크거나 작은지 명시적으로 표현하세요. (예: "slightly larger", "much smaller", "same size")
    7. 색상 변경이 필요한 경우, 기존 색상과의 관계를 명확히 표현하세요. (예: "change color to navy blue based on text request", "keep the original black color but add blue highlights")
     
    [JSON 출력 예시]
    {{
        "hair_outter": "black color, short length, straight bob cut",
        "hair_inner": "dark black color, deeply shadowed",
        "face_expression_eye_set": "sharp eyes, slightly slanted upwards, dark brown iris",
        "upper_body_outfit_set": "change color to navy blue based on text request",
        ... (나머지 파츠들)
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
    test_image_path = "user.png"  # 실제 사용자 사진 경로
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