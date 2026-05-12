import os
import json
import io
import time
import hashlib
import numpy as np
from PIL import Image
from google import genai
from google.genai import types

# ── 설정 ─────────────────────────────────────────────────
API_KEY = "AIzaSyC591fZ9vohnOf8rXJovMsocvaV8joM4KM"
INPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\parts"
OUTPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\modified_parts"
JSON_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\prompts.json"
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "parts_manifest.json") # 캐시 기록

# 참조 경로
FEATURE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\baseFeature.json"
USER_IMAGE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\user.png"
AKARI_STAND_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\akari_stand.png"

CANVAS_SIZE = 1024
# ─────────────────────────────────────────────────────────

def get_image_hash(img):
    """이미지 내용 기반 해시 생성 (캐시용)"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()

def process_part_perfect(client, name, prompt_text, user_bytes, stand_bytes, base_features):
    input_path = os.path.join(INPUT_DIR, f"{name}.png")
    output_path = os.path.join(OUTPUT_DIR, f"{name}.png")

    # 1. 파츠 로드 및 마스크 추출
    orig_img = Image.open(input_path).convert("RGBA")
    orig_arr = np.array(orig_img)
    original_mask = orig_arr[:, :, 3] > 10 # 투명도 기반 마스크

    # 2. Gemini 입력용 캔버스 (검정 배경)
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0))
    temp_img = orig_img.convert("RGB")
    temp_img.thumbnail((CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS)
    canvas.paste(temp_img, (0, 0))
    
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    part_bytes = buf.getvalue()

    # 3. 강화된 Role 기반 프롬프트
    spec = base_features.get(name, {})
    part_role = spec.get('role', 'VTube asset piece')
    
    system_prompt = f"""
    This is one cropped part from a Live2D texture atlas.

    Part name:
    {name}

    Edit instruction:
    {part_role}에 어울리도록, 그리고 아래의 사용자 지침과 참조 이미지를 최대한 활용하여, 이 부분을 스타일과 일치하도록 수정하세요.

    Strict rules:
    1. Edit only this part according to the edit instruction.
    2. Keep the exact same layout, position, scale, and composition.
    3. Do not move, rotate, resize, crop, or rearrange any visible piece.
    4. Keep the same 2D anime Live2D texture style.
    5. Preserve the original line art and shading direction as much as possible.
    6. Do not add text, logos, signatures, or extra objects.
    7. Keep the background transparent or empty.
    8. The output must keep the same composition as the input image.
    """

    # 4. 멀티모달 요청 (라벨링 강화)
    try:
# contents 구성 부분
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                system_prompt,
                "REFERENCE 1 (Target Style Source):", 
                types.Part.from_bytes(data=user_bytes, mime_type="image/jpeg"),
                
                "TARGET PART TO MODIFY (Modify ONLY this):", 
                types.Part.from_bytes(data=part_bytes, mime_type="image/png")
            ],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
        )

        # 5. 후처리 (알파 채널 복구 및 형태 강제 고정)
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                gen_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                gen_img = gen_img.resize(orig_img.size, Image.LANCZOS)
                gen_arr = np.array(gen_img.convert("RGBA"))
                
                # 원본 마스크 영역 밖은 무조건 투명화 (전신 그림 방어 최전선)
                gen_arr[~original_mask, 3] = 0
                
                # 살아남은 영역 중 너무 어두운 배경 제거
                rgb_sum = gen_arr[:, :, :3].sum(axis=2)
                gen_arr[rgb_sum < 40, 3] = 0
                
                Image.fromarray(gen_arr, mode="RGBA").save(output_path, "PNG")
                return True
    except Exception as e:
        print(f"Error in {name}: {e}")
    return False

def main():
    client = genai.Client(api_key=API_KEY)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(JSON_PATH, "r", encoding="utf-8") as f: prompts_data = json.load(f)
    with open(FEATURE_PATH, "r", encoding="utf-8") as f: base_features = json.load(f)
    with open(USER_IMAGE_PATH, "rb") as f: user_bytes = f.read()
    with open(AKARI_STAND_PATH, "rb") as f: stand_bytes = f.read()

    # 매니페스트(캐시) 로드
    manifest = {}
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f: manifest = json.load(f)

    for name, prompt in prompts_data.items():
        if not prompt: continue
        
        # 캐시 체크
        input_path = os.path.join(INPUT_DIR, f"{name}.png")
        if os.path.exists(input_path):
            current_hash = get_image_hash(Image.open(input_path))
            cache_key = f"{name}_{hashlib.sha256(prompt.encode()).hexdigest()[:10]}_{current_hash[:10]}"
            
            if manifest.get(name) == cache_key and os.path.exists(os.path.join(OUTPUT_DIR, f"{name}.png")):
                print(f"[CACHE] {name} 사용 가능. 건너뜁니다.")
                continue

            print(f"[NEW] {name} 생성 시작...")
            if process_part_perfect(client, name, prompt, user_bytes, stand_bytes, base_features):
                manifest[name] = cache_key
                with open(MANIFEST_PATH, "w") as f: json.dump(manifest, f)
                print(f"  -> {name} 완료")
                time.sleep(10) # 무료 티어 속도 조절

if __name__ == "__main__":
    main()