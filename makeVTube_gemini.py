import os
import json
import io
import time
from xmlrpc import client
import numpy as np
from PIL import Image
from google import genai
from google.genai import types

# ── 설정 ─────────────────────────────────────────────────
API_KEY = "AIzaSyDE_ywwdmE6jOKyMLpk779SQj-SvwFfPAc"
INPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\parts"
OUTPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\modified_parts"
JSON_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\prompts.json"

# 추가된 경로들
FEATURE_DESCRIPTION_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\baseFeature.json"
ORIGINAL_TEXTURE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\akari_stand.png"
USER_IMAGE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\user.png"

BG_THRESHOLD = 50 
CANVAS_SIZE = 512 # 512x512 최적화
MAX_RETRIES = 3  # 에러 발생 시 최대 재시도 횟수
# ─────────────────────────────────────────────────────────

def process_part(client, name, prompt_text, original_texture_bytes, user_img_bytes, base_features):
    input_path = os.path.join(INPUT_DIR, f"{name}.png")
    output_path = os.path.join(OUTPUT_DIR, f"{name}.png")

    if not os.path.exists(input_path):
        return False

    # 1. 원본 로드 및 형태 보존 마스크 준비
    orig_img = Image.open(input_path).convert("RGBA")
    original_mask = np.array(orig_img)[:, :, 3] > 0 

    # 2. 변형 대상 파츠 이미지 준비 (검정 배경 패딩)
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0))
    temp_img = orig_img.convert("RGB")
    temp_img.thumbnail((CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS)
    canvas.paste(temp_img, (0, 0))
    
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    part_img_bytes = buf.getvalue()

    # 3. 파츠별 상세 명세 로드 (baseFeature.json 활용)
    spec = base_features.get(name, {})
    spec_text = f"Role: {spec.get('role', '')}, Silhouette: {spec.get('silhouette', '')}, Boundary: {spec.get('boundary', '')}"

    # 4. 멀티모달 시스템 프롬프트 구성
    # 사용자 사진(Target)과 파츠(Source)를 직접 비교하도록 지시
    system_prompt = f"""
    [CRITICAL MISSION: SINGLE PART MODIFICATION]
    You are a specialized technician for VTube avatar parts. 
    Your ONLY task is to modify the provided 'Source Image to Transform' (Asset Piece).
    
    1. CURRENT TARGET PART Name: {name}
    2. STRUCTURAL SPECS: {spec_text} (STRICTLY ADHERE TO THIS ROLE)
    3. STYLE GUIDELINE: {prompt_text}
    
    [STRICT OPERATIONAL RULES]
    - NEVER draw a full character or other parts. If the Source Image is only hair, the result MUST ONLY be hair.
    - REPLICATE THE PIECE POSITION: The asset must remain in the EXACT same pixel position as the Source Image.
    - ROLE COMPLIANCE: Adhere strictly to the "Role" above. For example, if the role is 'Main hairstyle provider', do NOT include a face, eyes, or clothing.
    - PURE BLACK BACKGROUND: Any area outside the target asset MUST be (0,0,0) black. 
    - STYLE MATCHING: Match the color and texture of 'Reference Style Image' (User Photo) onto the Source Image.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[
                system_prompt,
                "1. Texture Layout Reference (Image before decomposed):",
                types.Part.from_bytes(data=original_texture_bytes, mime_type="image/png"),
                "2. Target Style Reference (Copy colors/texture from here):",
                types.Part.from_bytes(data=user_img_bytes, mime_type="image/jpeg"),
                "3. THE ONLY IMAGE TO MODIFY (Target Asset):", # 맨 마지막에 강조
                types.Part.from_bytes(data=part_img_bytes, mime_type="image/png")
            ],
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
            )

            # 5. 후처리 및 저장
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    gen_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                    gen_img = gen_img.resize(orig_img.size, Image.LANCZOS)
                    
                    gen_arr = np.array(gen_img.convert("RGBA"))
                    
                    # 배경 제거 (어두운 영역 + 원본 외곽선 밖)
                    rgb_sum = gen_arr[:, :, :3].sum(axis=2)
                    gen_arr[rgb_sum < (BG_THRESHOLD * 3), 3] = 0
                    gen_arr[~original_mask, 3] = 0
                    
                    Image.fromarray(gen_arr, mode="RGBA").save(output_path, "PNG")
                    return True
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = 15 * (attempt + 1) # 에러 시 대기 시간 (15초, 30초...)
                print(f"  [QUOTA] 할당량 초과. {wait_time}초 후 다시 시도합니다... ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait_time)
            else:
                print(f"  [ERROR] {name}: {e}")
                break
    return False

def main():
    client = genai.Client(api_key=API_KEY)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 데이터 로드
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)
    with open(FEATURE_DESCRIPTION_PATH, "r", encoding="utf-8") as f:
        base_features = json.load(f)
    
    # 사용자 이미지 미리 읽기 (매번 읽지 않도록)
    with open(USER_IMAGE_PATH, "rb") as f:
        user_img_bytes = f.read()    
    with open(ORIGINAL_TEXTURE_PATH, "rb") as f:
        original_texture_bytes = f.read()

    print(f"🚀 {len(prompts_data)}개 파츠 변환 시작 (User Image 참조 모드)")
    
    for name, prompt in prompts_data.items():
        if prompt is None:
            continue

        print(f"  [PROCESS] {name}...")
        if process_part(client, name, prompt, original_texture_bytes, user_img_bytes, base_features):
            print(f"  [OK] {name}")
        
        time.sleep(10) # API Rate Limit 방지

if __name__ == "__main__":
    main()