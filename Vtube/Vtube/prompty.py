import os
import json
import hashlib
import google.generativeai as genai
from PIL import Image

# ── 설정 ─────────────────────────────────────────────────
API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY 환경변수가 없습니다\n"
        "윈도우 CMD에서 먼저 실행하세요\n"
        "setx GEMINI_API_KEY \"새_API_KEY\""
    )

genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"
model = genai.GenerativeModel(MODEL_NAME)

PART_NAMES = [
    "hair_long_back_left", "hair_bangs_center_set", "hair_pink_twin_set",
    "hair_or_accessory_purple_lower_left_candidate", "bunny_ears_pair",
    "face_head_base_set", "face_expression_eye_set", "upper_body_outfit_set",
    "skirt", "legs_stockings_pair", "shoes_pair", "shorts_underwear",
    "lower_leg_boots_socks_set", "arm_hand_set", "small_detached_body_parts",
    "ribbon_bow_accessory_set", "effect_symbols_top_right", "small_top_center_parts"
]

OUTPUT_JSON_PATH = "prompts.json"
CACHE_META_PATH = "prompts_cache_meta.json"

# True면 같은 입력일 때 API 호출 안 하고 기존 prompts.json 사용
USE_CACHE = True

# 강제로 새로 만들고 싶을 때만 True
FORCE_REGENERATE_PROMPTS = False


def file_sha256(path):
    """파일 내용 기준 해시 생성"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_prompt_cache_key(face_image_path, user_request_text):
    """사진 + 요청문 + 파츠목록 + 모델명이 같으면 같은 cache key"""
    payload = {
        "model": MODEL_NAME,
        "image_sha256": file_sha256(face_image_path),
        "user_request_text": user_request_text,
        "part_names": PART_NAMES,
    }

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cached_prompts(cache_key):
    """기존 prompts.json이 같은 입력으로 만들어진 것이면 재사용"""
    if not USE_CACHE or FORCE_REGENERATE_PROMPTS:
        return None

    if not os.path.exists(OUTPUT_JSON_PATH):
        return None

    if not os.path.exists(CACHE_META_PATH):
        return None

    try:
        with open(CACHE_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)

        if meta.get("cache_key") != cache_key:
            return None

        with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
            prompts = json.load(f)

        print("[CACHE] 같은 입력이므로 Gemini 호출 없이 prompts.json을 재사용합니다")
        return prompts

    except Exception as e:
        print(f"[WARN] 캐시 확인 실패 새로 생성합니다: {e}")
        return None


def save_prompt_cache_meta(cache_key):
    meta = {
        "cache_key": cache_key,
        "model": MODEL_NAME,
        "part_names": PART_NAMES,
    }

    with open(CACHE_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)


def generate_part_prompts(face_image_path, user_request_text):
    """
    사용자 얼굴 이미지와 텍스트 요청을 분석하여 파츠별 수정 프롬프트를 JSON 형태로 반환
    같은 입력이면 API를 다시 호출하지 않고 캐시 사용
    """
    try:
        cache_key = make_prompt_cache_key(face_image_path, user_request_text)
    except Exception as e:
        print(f"[ERROR] 캐시 키 생성 실패: {e}")
        return None

    cached = load_cached_prompts(cache_key)
    if cached is not None:
        return cached

    try:
        img = Image.open(face_image_path)
    except Exception as e:
        print(f"[ERROR] 이미지를 불러올 수 없습니다: {e}")
        return None

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
    "upper_body_outfit_set": "change color to navy blue based on text request"
}}
"""

    print("[INFO] AI가 이미지와 텍스트를 분석 중입니다...")

    response = model.generate_content(
        [system_instruction, img],
        generation_config={
            "response_mime_type": "application/json"
        }
    )

    result_text = response.text.strip()

    if result_text.startswith("```json"):
        result_text = result_text[7:-3].strip()
    elif result_text.startswith("```"):
        result_text = result_text[3:-3].strip()

    try:
        prompts_json = json.loads(result_text)

        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(prompts_json, f, indent=4, ensure_ascii=False)

        save_prompt_cache_meta(cache_key)

        return prompts_json

    except json.JSONDecodeError:
        print("[ERROR] JSON 파싱 실패 AI 응답이 올바른 형식이 아닙니다")
        print("원본 응답:\n", result_text)
        return None


if __name__ == "__main__":
    test_image_path = "user.jpg"
    user_text = "사진의 내 모습을 최대한 살려서 만들어줘."

    if not os.path.exists(test_image_path):
        print(f"[INFO] 테스트를 위해 {test_image_path} 더미 이미지를 생성합니다")
        Image.new("RGB", (100, 100), color="white").save(test_image_path)

    generated_prompts = generate_part_prompts(test_image_path, user_text)

    if generated_prompts:
        print("\n[SUCCESS] 파츠별 변형 프롬프트 준비 완료")
        print(f"[OK] 결과 저장 위치: {os.path.abspath(OUTPUT_JSON_PATH)}")
        print(json.dumps(generated_prompts, indent=4, ensure_ascii=False))