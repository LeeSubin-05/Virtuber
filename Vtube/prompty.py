"""
make_prompts.py - 사용자 얼굴 사진과 사용자가 입력한 RGB값을 합쳐 prompts.json 생성

설치:
  pip install google-generativeai pillow

실행:
  python make_prompts.py
"""

import os
import json
import hashlib
import google.generativeai as genai
from PIL import Image


# ── 설정 ─────────────────────────────────────────────────

# API 키는 코드에 직접 넣지 말고 환경변수 사용 권장
# CMD에서 먼저 실행:
# setx GEMINI_API_KEY "새_API_KEY"
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


# ── 사용자 입력값 ─────────────────────────────────────────

# 사용자 얼굴 사진 경로
FACE_IMAGE_PATH = "photos/v_photo_image.png"

# 사용자가 원하는 전체 방향
USER_REQUEST_TEXT = "사진의 내 모습을 최대한 살려서 만들어줘."

# 사용자가 직접 입력할 RGB값
with open(r'\colors.json', 'r', encoding='utf-8') as f: # !!다운로드 폴더 경로를 colors.json 앞에 작성하기!!
    colors = json.load(f)
USER_HAIR_RGB = (colors['hair']['r'], colors['hair']['g'], colors['hair']['b'])      # 머리카락 색
USER_IRIS_RGB = (colors['eye']['r'], colors['eye']['g'], colors['eye']['b'])      # 눈동자 색
USER_SKIN_RGB = (colors['skin']['r'], colors['skin']['g'], colors['skin']['b'])   # 피부색


# ── 저장 경로 ────────────────────────────────────────────

OUTPUT_JSON_PATH = "prompts.json"
CACHE_META_PATH = "prompts_cache_meta.json"

# True면 같은 입력일 때 API 호출 안 하고 기존 prompts.json 사용
USE_CACHE = True

# 강제로 새로 만들고 싶을 때만 True
FORCE_REGENERATE_PROMPTS = False


# ── 파츠 이름 리스트 ─────────────────────────────────────

PART_NAMES = [
    "hair_long_back_left",
    "hair_bangs_center_set",
    "hair_pink_twin_set",
    "hair_or_accessory_purple_lower_left_candidate",
    "bunny_ears_pair",
    "face_head_base_set",
    "face_expression_eye_set",
    "upper_body_outfit_set",
    "skirt",
    "legs_stockings_pair",
    "shoes_pair",
    "shorts_underwear",
    "lower_leg_boots_socks_set",
    "arm_hand_set",
    "small_detached_body_parts",
    "ribbon_bow_accessory_set",
    "effect_symbols_top_right",
    "small_top_center_parts"
]


def rgb_to_text(rgb):
    """
    RGB 튜플을 프롬프트에 넣기 좋은 문자열로 변환
    예: (45, 32, 25) -> rgb(45, 32, 25)
    """
    r, g, b = rgb
    return f"rgb({r}, {g}, {b})"


def file_sha256(path):
    """파일 내용 기준 해시 생성"""
    h = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def make_system_instruction(user_request_text, hair_rgb, iris_rgb, skin_rgb):
    """
    Gemini에게 전달할 프롬프트 생성

    핵심 변경점:
    1. 사진에서는 인물을 구별할 수 있는 최소한의 외모 특징만 추출
    2. 머리카락 색 눈동자 색 피부색은 사용자가 입력한 RGB값을 최종 기준으로 사용
    3. 둘을 합쳐서 각 파츠별 수정 프롬프트 생성
    """

    hair_rgb_text = rgb_to_text(hair_rgb)
    iris_rgb_text = rgb_to_text(iris_rgb)
    skin_rgb_text = rgb_to_text(skin_rgb)

    return f"""
You are a VTube Live2D character asset prompt designer.

Your task is to analyze the provided face photo and create concise part-editing prompts for a Live2D texture model.

[User request]
"{user_request_text}"

[User-provided exact color values]
- Hair color: {hair_rgb_text}
- Iris color: {iris_rgb_text}
- Skin base color: {skin_rgb_text}

[Important goal]
Create prompts by combining:
1. Minimal visual identity cues extracted from the photo
2. The exact RGB colors provided by the user

[Rules for analyzing the photo]
1. Extract only the minimum appearance features needed to distinguish the person visually.
2. Focus on features such as:
   - eye shape
   - eyelid shape
   - eyebrow shape
   - face shape
   - nose shape
   - lip shape
   - visible hair silhouette or hairstyle
   - overall soft or sharp facial impression
3. Do not over-describe the person.
4. Do not infer private or sensitive identity traits.
5. Do not mention ethnicity, nationality, age, or personality.
6. Do not copy the person realistically. Translate the features into a 2D anime Live2D style.

[Color rules]
1. Use the user's RGB values as the final color source.
2. Do not invent different hair, iris, or skin colors from the image.
3. If the image color and user RGB value conflict, prioritize the user RGB value.
4. Hair-related parts must include: hair color {hair_rgb_text}
5. Eye-related parts must include: iris color {iris_rgb_text}
6. Face or skin-related parts must include: skin base color {skin_rgb_text}

[Prompt construction rules]
1. Each value must be a concise English prompt for image editing.
2. Combine minimal photo-based features with the user's RGB colors.
3. Do not write long sentences.
4. Use concrete visual keywords separated by commas.
5. If a part does not need editing, set its value to null.
6. Output only valid JSON.
7. The JSON must use only the provided part names as keys.

[Part list]
{', '.join(PART_NAMES)}

[Expected JSON style]
{{
    "hair_long_back_left": "hair color {hair_rgb_text}, long dark hair silhouette based on photo, soft anime Live2D shading",
    "hair_bangs_center_set": "hair color {hair_rgb_text}, natural bangs shape based on photo, clean anime line art",
    "face_head_base_set": "skin base color {skin_rgb_text}, soft face shape based on photo, natural anime face contour",
    "face_expression_eye_set": "iris color {iris_rgb_text}, eye shape based on photo, natural eyelid shape, soft anime eyelashes",
    "upper_body_outfit_set": null
}}
"""


def make_prompt_cache_key(face_image_path, user_request_text, hair_rgb, iris_rgb, skin_rgb):
    """
    사진 + 요청문 + RGB값 + 파츠목록 + 모델명이 같으면 같은 cache key
    RGB값이 바뀌면 새로 생성되도록 RGB도 포함
    """

    payload = {
        "model": MODEL_NAME,
        "image_sha256": file_sha256(face_image_path),
        "user_request_text": user_request_text,
        "hair_rgb": hair_rgb,
        "iris_rgb": iris_rgb,
        "skin_rgb": skin_rgb,
        "part_names": PART_NAMES,
    }

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cached_prompts(cache_key):
    """
    기존 prompts.json이 같은 입력으로 만들어진 것이면 재사용
    """
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


def save_prompt_cache_meta(cache_key, hair_rgb, iris_rgb, skin_rgb):
    """
    캐시 정보 저장
    """
    meta = {
        "cache_key": cache_key,
        "model": MODEL_NAME,
        "hair_rgb": hair_rgb,
        "iris_rgb": iris_rgb,
        "skin_rgb": skin_rgb,
        "part_names": PART_NAMES,
    }

    with open(CACHE_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)


def clean_json_text(result_text):
    """
    Gemini가 혹시 ```json 코드블록으로 감싸서 응답할 경우 제거
    """
    result_text = result_text.strip()

    if result_text.startswith("```json"):
        result_text = result_text[7:].strip()

    if result_text.startswith("```"):
        result_text = result_text[3:].strip()

    if result_text.endswith("```"):
        result_text = result_text[:-3].strip()

    return result_text


def validate_prompts_json(prompts_json):
    """
    결과 JSON이 PART_NAMES 기준으로 되어 있는지 간단 검증
    없는 키는 null로 채우고
    알 수 없는 키는 제거
    """

    cleaned = {}

    for part_name in PART_NAMES:
        value = prompts_json.get(part_name, None)

        if value is None:
            cleaned[part_name] = None
        elif isinstance(value, str) and value.strip() == "":
            cleaned[part_name] = None
        else:
            cleaned[part_name] = value

    return cleaned


def generate_part_prompts(
    face_image_path,
    user_request_text,
    hair_rgb,
    iris_rgb,
    skin_rgb
):
    """
    사용자 얼굴 이미지와 사용자 RGB값을 분석하여
    파츠별 수정 프롬프트를 JSON 형태로 반환
    같은 입력이면 API를 다시 호출하지 않고 캐시 사용
    """

    if not os.path.exists(face_image_path):
        print(f"[ERROR] 이미지 파일을 찾을 수 없습니다: {face_image_path}")
        return None

    try:
        cache_key = make_prompt_cache_key(
            face_image_path=face_image_path,
            user_request_text=user_request_text,
            hair_rgb=hair_rgb,
            iris_rgb=iris_rgb,
            skin_rgb=skin_rgb
        )

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

    system_instruction = make_system_instruction(
        user_request_text=user_request_text,
        hair_rgb=hair_rgb,
        iris_rgb=iris_rgb,
        skin_rgb=skin_rgb
    )

    print("[INFO] AI가 이미지에서 최소 외모 특징을 분석하고 RGB값과 합치는 중입니다...")

    try:
        response = model.generate_content(
            [system_instruction, img],
            generation_config={
                "response_mime_type": "application/json"
            }
        )

        result_text = clean_json_text(response.text)

        prompts_json = json.loads(result_text)
        prompts_json = validate_prompts_json(prompts_json)

        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(prompts_json, f, indent=4, ensure_ascii=False)

        save_prompt_cache_meta(
            cache_key=cache_key,
            hair_rgb=hair_rgb,
            iris_rgb=iris_rgb,
            skin_rgb=skin_rgb
        )

        return prompts_json

    except json.JSONDecodeError:
        print("[ERROR] JSON 파싱 실패 AI 응답이 올바른 형식이 아닙니다")
        print("원본 응답:\n", result_text)
        return None

    except Exception as e:
        print(f"[ERROR] Gemini 요청 중 오류 발생: {e}")
        return None


if __name__ == "__main__":
    generated_prompts = generate_part_prompts(
        face_image_path=FACE_IMAGE_PATH,
        user_request_text=USER_REQUEST_TEXT,
        hair_rgb=USER_HAIR_RGB,
        iris_rgb=USER_IRIS_RGB,
        skin_rgb=USER_SKIN_RGB
    )

    if generated_prompts:
        print("\n[SUCCESS] 파츠별 변형 프롬프트 생성 완료")
        print(f"[OK] 결과가 성공적으로 저장되었습니다: {os.path.abspath(OUTPUT_JSON_PATH)}")
        print(json.dumps(generated_prompts, indent=4, ensure_ascii=False))

    else:
        print("\n[FAILED] prompts.json 생성 실패")
