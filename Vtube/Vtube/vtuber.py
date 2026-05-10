"""
vtuber.py - prompts.json + PARTS 좌표를 이용해 파츠별 수정 후 최종 texture PNG 저장

설치:
  pip install google-genai pillow numpy

실행:
  python vtuber.py
"""

import os
import sys
import json
import io
import time
import numpy as np
from PIL import Image
"""
vtuber.py - prompts.json + PARTS 좌표를 이용해 파츠별 수정 후 최종 texture PNG 저장

설치:
  pip install google-genai pillow numpy

실행:
  python vtuber.py
"""

import os
import sys
import json
import io
import time
import hashlib

import numpy as np
from PIL import Image

from google import genai
from google.genai import types


# ── 설정 ─────────────────────────────────────────────────

TEXTURE_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\akari_vts_ai_test\akari.4096\texture_00.png"

# 2번 코드에서 만든 JSON 파일
PROMPTS_PATH = r"C:\Users\82106\OneDrive\바탕 화면\Vtube\prompt\prompts.json"

# 결과 저장 위치
OUTPUT_DIR = r"C:\Users\82106\OneDrive\바탕 화면\Vtube\result"
EDITED_PARTS_DIR = os.path.join(OUTPUT_DIR, "edited_parts")
FINAL_TEXTURE_PATH = os.path.join(OUTPUT_DIR, "texture_test_result.png")

# Gemini 이미지 모델
MODEL_NAME = "gemini-2.5-flash-image"

# 테스트할 때 특정 파츠만 하고 싶으면 여기에 이름 넣기
# 예: ONLY_PARTS = ["face_expression_eye_set"]
# 전체 prompts.json 기준으로 돌릴 거면 빈 리스트 유지
ONLY_PARTS = []

# 요청 사이 대기 시간
# quota 오류가 자주 나면 30 이상으로 늘리기
REQUEST_SLEEP_SECONDS = 3

# 캐시 설정
# 같은 원본 파츠 + 같은 프롬프트면 Gemini 호출하지 않고 기존 결과 재사용
USE_PART_CACHE = True

# True로 바꾸면 캐시 무시하고 Gemini를 다시 호출
FORCE_REGENERATE_PARTS = False

# 파츠별 캐시 기록 파일
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "edited_parts_manifest.json")

# 기존 결과를 최대한 유지하기 위해 1024 유지
# 결과가 조금 달라져도 토큰을 더 줄이고 싶으면 768 또는 512로 변경 가능
IMAGE_INPUT_SIZE = 1024


# extract_parts.py에서 가져온 PARTS 좌표
PARTS = {
    "hair_long_back_left":                              [84, 96, 908, 1732],
    "hair_bangs_center_set":                            [724, 2014, 2268, 3012],
    "hair_pink_twin_set":                               [2450, 2200, 3962, 3418],
    "hair_or_accessory_purple_lower_left_candidate":    [34, 3762, 662, 4062],
    "bunny_ears_pair":                                  [2890, 80, 3888, 314],
    "face_head_base_set":                               [3016, 356, 3758, 1420],
    "face_expression_eye_set":                          [2290, 3584, 4024, 4014],
    "upper_body_outfit_set":                            [1780, 212, 2866, 1498],
    "skirt":                                            [1924, 1528, 2614, 2028],
    "legs_stockings_pair":                              [1016, 16, 1678, 1532],
    "shoes_pair":                                       [1194, 1454, 1714, 1876],
    "shorts_underwear":                                 [40, 1878, 790, 2426],
    "lower_leg_boots_socks_set":                        [40, 2504, 742, 3782],
    "arm_hand_set":                                     [766, 3056, 1264, 4062],
    "small_detached_body_parts":                        [958, 1454, 1896, 1780],
    "ribbon_bow_accessory_set":                         [2770, 1468, 3528, 1790],
    "effect_symbols_top_right":                         [3836, 324, 4038, 872],
    "small_top_center_parts":                           [1882, 10, 2662, 258],
}


def load_prompts():
    """prompts.json 불러오기"""
    if not os.path.exists(PROMPTS_PATH):
        print(f"❌ prompts.json 파일 없음: {PROMPTS_PATH}")
        sys.exit(1)

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    return prompts


def make_gemini_prompt(part_name, part_prompt):
    """파츠별 Gemini 이미지 수정 프롬프트 생성"""
    return f"""
This is one cropped part from a Live2D texture atlas.

Part name:
{part_name}

Edit instruction:
{part_prompt}

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


def sha256_bytes(data):
    """bytes 기준 sha256 생성"""
    return hashlib.sha256(data).hexdigest()


def image_sha256(img):
    """
    이미지 내용을 기준으로 해시 생성
    원본 파츠가 바뀌면 해시도 바뀌어서 캐시를 재사용하지 않음
    """
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return sha256_bytes(buf.getvalue())


def load_manifest():
    """캐시 manifest 불러오기"""
    if not os.path.exists(MANIFEST_PATH):
        return {}

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"[WARN] manifest 로드 실패 새로 시작합니다: {e}")
        return {}


def save_manifest(manifest):
    """캐시 manifest 저장"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)


def make_part_cache_key(part_name, part_img, part_prompt):
    """
    같은 파츠 이미지 + 같은 프롬프트 + 같은 모델 + 같은 입력 크기면 같은 캐시 키
    """
    prompt_text = make_gemini_prompt(part_name, part_prompt)

    payload = {
        "model": MODEL_NAME,
        "part_name": part_name,
        "part_prompt": str(part_prompt).strip(),
        "source_crop_sha256": image_sha256(part_img),
        "prompt_template_sha256": sha256_bytes(prompt_text.encode("utf-8")),
        "image_input_size": IMAGE_INPUT_SIZE,
    }

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha256_bytes(text.encode("utf-8"))


def load_cached_edited_part(part_name, cache_key, crop_size, manifest):
    """
    기존에 같은 조건으로 생성된 수정 파츠가 있으면 불러오기
    """
    if not USE_PART_CACHE or FORCE_REGENERATE_PARTS:
        return None

    entry = manifest.get(part_name)

    if not entry:
        return None

    if entry.get("cache_key") != cache_key:
        return None

    cached_path = entry.get("path")

    if not cached_path or not os.path.exists(cached_path):
        return None

    try:
        cached_img = Image.open(cached_path).convert("RGBA")

        if cached_img.size != crop_size:
            return None

        print(f"[CACHE] Gemini 호출 없이 기존 수정 파츠 재사용: {part_name}")
        return cached_img

    except Exception as e:
        print(f"[WARN] 캐시 파츠 로드 실패 새로 생성합니다: {part_name} / {e}")
        return None


def edit_part_with_gemini(client, part_name, part_img, part_prompt):
    """파츠 하나를 Gemini로 수정하고 원래 크기로 되돌림"""

    crop_size = part_img.size
    crop_arr = np.array(part_img.convert("RGBA"))

    # 원본 알파 저장
    original_alpha = crop_arr[:, :, 3].copy()
    has_alpha_bg = (original_alpha < 10).sum() > 0

    # Gemini 입력용 정사각형 이미지
    # 기존 결과 흐름을 유지하기 위해 기본값 1024x1024 사용
    input_rgb = part_img.convert("RGB")
    small = input_rgb.resize((IMAGE_INPUT_SIZE, IMAGE_INPUT_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    small.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    prompt = make_gemini_prompt(part_name, part_prompt)

    print(f"\n⏳ Gemini 요청 중: {part_name}")
    print(f"   수정 프롬프트: {part_prompt}")

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        ],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        )
    )

    result_img = None

    try:
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                result_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                break

    except Exception as e:
        print(f"❌ Gemini 응답 처리 중 오류: {part_name}")
        print(e)
        return None

    if result_img is None:
        print(f"❌ Gemini 응답에 이미지 없음: {part_name}")
        return None

    # 원래 crop 크기로 복원
    result_img = result_img.resize(crop_size, Image.LANCZOS)
    result_arr = np.array(result_img.convert("RGBA"))

    # 원본에 투명 배경이 있으면 원본 alpha를 그대로 적용
    if has_alpha_bg:
        result_arr[:, :, 3] = original_alpha

    else:
        # 투명 알파가 없는 경우 기존 코드처럼 어두운 배경을 제거
        original_bg_mask = crop_arr[:, :, :3].sum(axis=2) < 90
        result_arr[original_bg_mask, 3] = 0

        result_rgb_sum = result_arr[:, :, :3].sum(axis=2)
        dark_mask = result_rgb_sum < (60 * 3)
        result_arr[dark_mask, 3] = 0

        bright_mask = (
            (result_arr[:, :, 0] > 240) &
            (result_arr[:, :, 1] > 240) &
            (result_arr[:, :, 2] > 240)
        )
        result_arr[bright_mask, 3] = 0

    edited_part = Image.fromarray(result_arr, mode="RGBA")
    return edited_part


def main():
    api_key = "AIzaSyCw9_Jpa_0hyy3fD8ak1zeeKzoxzRw9fxA"

    if not api_key:
        print("❌ GEMINI_API_KEY 환경변수가 없어요")
        print("예: setx GEMINI_API_KEY \"새_API_KEY\"")
        sys.exit(1)

    if not os.path.exists(TEXTURE_PATH):
        print(f"❌ 텍스처 파일 없음: {TEXTURE_PATH}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(EDITED_PARTS_DIR, exist_ok=True)

    prompts = load_prompts()

    print(f"✅ 텍스처 로드: {TEXTURE_PATH}")
    texture = Image.open(TEXTURE_PATH).convert("RGBA")
    final_texture = texture.copy()

    client = genai.Client(api_key=api_key)

    manifest = load_manifest()

    edited_count = 0
    cached_count = 0
    skipped_count = 0

    for part_name, box in PARTS.items():

        # ONLY_PARTS가 있으면 그 파츠만 실행
        if ONLY_PARTS and part_name not in ONLY_PARTS:
            continue

        # prompts.json에 없으면 건너뜀
        if part_name not in prompts:
            print(f"[SKIP] prompts.json에 없음: {part_name}")
            skipped_count += 1
            continue

        part_prompt = prompts[part_name]

        # null 또는 빈 문자열이면 수정 안 함
        if part_prompt is None or str(part_prompt).strip() == "":
            print(f"[SKIP] 수정 없음: {part_name}")
            skipped_count += 1
            continue

        x1, y1, x2, y2 = box
        part_img = texture.crop((x1, y1, x2, y2))

        edited_part_path = os.path.join(EDITED_PARTS_DIR, f"{part_name}.png")
        cache_key = make_part_cache_key(part_name, part_img, part_prompt)

        # 먼저 캐시 확인
        cached_part = load_cached_edited_part(
            part_name=part_name,
            cache_key=cache_key,
            crop_size=part_img.size,
            manifest=manifest
        )

        if cached_part is not None:
            final_texture.paste(cached_part, (x1, y1), cached_part)
            cached_count += 1
            continue

        try:
            edited_part = edit_part_with_gemini(
                client=client,
                part_name=part_name,
                part_img=part_img,
                part_prompt=part_prompt
            )

            if edited_part is None:
                continue

            # 수정 파츠 저장
            edited_part.save(edited_part_path, "PNG")
            print(f"💾 수정 파츠 저장: {edited_part_path}")

            # 캐시 기록 저장
            manifest[part_name] = {
                "cache_key": cache_key,
                "path": edited_part_path,
                "model": MODEL_NAME,
                "part_prompt": str(part_prompt).strip(),
                "source_crop_sha256": image_sha256(part_img),
                "image_input_size": IMAGE_INPUT_SIZE,
            }
            save_manifest(manifest)

            # 원본 텍스처에 합성
            final_texture.paste(edited_part, (x1, y1), edited_part)
            print(f"🎨 텍스처 합성 완료: {part_name}")

            edited_count += 1

            # quota 방지용 대기
            time.sleep(REQUEST_SLEEP_SECONDS)

        except Exception as e:
            print(f"❌ 오류 발생: {part_name}")
            print(e)
            continue

    # 최종 텍스처 저장
    final_texture.save(FINAL_TEXTURE_PATH, "PNG")

    print("\n[DONE]")
    print(f"새로 수정한 파츠 수: {edited_count}")
    print(f"캐시로 재사용한 파츠 수: {cached_count}")
    print(f"건너뛴 파츠 수: {skipped_count}")
    print(f"최종 결과 저장: {FINAL_TEXTURE_PATH}")

    check = Image.open(FINAL_TEXTURE_PATH)
    print(f"검증 모드: {check.mode}")
    print(f"검증 크기: {check.size}")


if __name__ == "__main__":
    main()
from google import genai
from google.genai import types


# ── 설정 ─────────────────────────────────────────────────

TEXTURE_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\akari_vts_ai_test\akari.4096\texture_00.png"

# 첫 번째 코드에서 만든 JSON 파일
PROMPTS_PATH = r"C:\Users\82106\OneDrive\바탕 화면\Vtube\prompt\prompts.json"

# 결과 저장 위치
OUTPUT_DIR = r"C:\Users\82106\OneDrive\바탕 화면\Vtube\result"
EDITED_PARTS_DIR = os.path.join(OUTPUT_DIR, "edited_parts")
FINAL_TEXTURE_PATH = os.path.join(OUTPUT_DIR, "texture_test_result.png")

# Gemini 이미지 모델
MODEL_NAME = "gemini-2.5-flash-image"

# 테스트할 때 특정 파츠만 하고 싶으면 여기에 이름 넣기
# 예: ONLY_PARTS = ["face_expression_eye_set"]
# 전체 prompts.json 기준으로 돌릴 거면 빈 리스트 유지
ONLY_PARTS = []

# 요청 사이 대기 시간
# quota 오류가 자주 나면 30 이상으로 늘리기
REQUEST_SLEEP_SECONDS = 3


# extract_parts.py에서 가져온 PARTS 좌표
PARTS = {
    "hair_long_back_left":                              [84, 96, 908, 1732],
    "hair_bangs_center_set":                            [724, 2014, 2268, 3012],
    "hair_pink_twin_set":                               [2450, 2200, 3962, 3418],
    "hair_or_accessory_purple_lower_left_candidate":    [34, 3762, 662, 4062],
    "bunny_ears_pair":                                  [2890, 80, 3888, 314],
    "face_head_base_set":                               [3016, 356, 3758, 1420],
    "face_expression_eye_set":                          [2290, 3584, 4024, 4014],
    "upper_body_outfit_set":                            [1780, 212, 2866, 1498],
    "skirt":                                            [1924, 1528, 2614, 2028],
    "legs_stockings_pair":                              [1016, 16, 1678, 1532],
    "shoes_pair":                                       [1194, 1454, 1714, 1876],
    "shorts_underwear":                                 [40, 1878, 790, 2426],
    "lower_leg_boots_socks_set":                        [40, 2504, 742, 3782],
    "arm_hand_set":                                     [766, 3056, 1264, 4062],
    "small_detached_body_parts":                        [958, 1454, 1896, 1780],
    "ribbon_bow_accessory_set":                         [2770, 1468, 3528, 1790],
    "effect_symbols_top_right":                         [3836, 324, 4038, 872],
    "small_top_center_parts":                           [1882, 10, 2662, 258],
}


def load_prompts():
    """prompts.json 불러오기"""
    if not os.path.exists(PROMPTS_PATH):
        print(f"❌ prompts.json 파일 없음: {PROMPTS_PATH}")
        sys.exit(1)

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    return prompts


def make_gemini_prompt(part_name, part_prompt):
    """파츠별 Gemini 이미지 수정 프롬프트 생성"""
    return f"""
This is one cropped part from a Live2D texture atlas.

Part name:
{part_name}

Edit instruction:
{part_prompt}

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


def edit_part_with_gemini(client, part_name, part_img, part_prompt):
    """파츠 하나를 Gemini로 수정하고 원래 크기로 되돌림"""

    crop_size = part_img.size
    crop_arr = np.array(part_img.convert("RGBA"))

    # 원본 알파 저장
    original_alpha = crop_arr[:, :, 3].copy()
    has_alpha_bg = (original_alpha < 10).sum() > 0

    # Gemini 입력용 1024 이미지
    # 기존 코드 흐름을 최대한 유지하기 위해 1024x1024로 변환
    input_rgb = part_img.convert("RGB")
    small = input_rgb.resize((1024, 1024), Image.LANCZOS)

    buf = io.BytesIO()
    small.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    prompt = make_gemini_prompt(part_name, part_prompt)

    print(f"\n⏳ Gemini 요청 중: {part_name}")
    print(f"   수정 프롬프트: {part_prompt}")

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        ],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        )
    )

    result_img = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            result_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
            break

    if result_img is None:
        print(f"❌ Gemini 응답에 이미지 없음: {part_name}")
        return None

    # 원래 crop 크기로 복원
    result_img = result_img.resize(crop_size, Image.LANCZOS)
    result_arr = np.array(result_img.convert("RGBA"))

    # 원본에 투명 배경이 있으면 원본 alpha를 그대로 적용
    if has_alpha_bg:
        result_arr[:, :, 3] = original_alpha
    else:
        # 투명 알파가 없는 경우 기존 코드처럼 어두운 배경을 제거
        original_bg_mask = (crop_arr[:, :, :3].sum(axis=2) < 90)
        result_arr[original_bg_mask, 3] = 0

        result_rgb_sum = result_arr[:, :, :3].sum(axis=2)
        dark_mask = result_rgb_sum < (60 * 3)
        result_arr[dark_mask, 3] = 0

        bright_mask = (
            (result_arr[:, :, 0] > 240) &
            (result_arr[:, :, 1] > 240) &
            (result_arr[:, :, 2] > 240)
        )
        result_arr[bright_mask, 3] = 0

    edited_part = Image.fromarray(result_arr, mode="RGBA")
    return edited_part


def main():
    api_key = "AIzaSyA97xc3LpVqsLbS8RQZRUkVtxjMKRSLzLg"

    if not api_key:
        print("❌ GEMINI_API_KEY 환경변수가 없어요")
        print("예: setx GEMINI_API_KEY \"새_API_KEY\"")
        sys.exit(1)

    if not os.path.exists(TEXTURE_PATH):
        print(f"❌ 텍스처 파일 없음: {TEXTURE_PATH}")
        sys.exit(1)

    os.makedirs(EDITED_PARTS_DIR, exist_ok=True)

    prompts = load_prompts()

    print(f"✅ 텍스처 로드: {TEXTURE_PATH}")
    texture = Image.open(TEXTURE_PATH).convert("RGBA")
    final_texture = texture.copy()

    client = genai.Client(api_key=api_key)

    edited_count = 0

    for part_name, box in PARTS.items():
        # ONLY_PARTS가 있으면 그 파츠만 실행
        if ONLY_PARTS and part_name not in ONLY_PARTS:
            continue

        # prompts.json에 없으면 건너뜀
        if part_name not in prompts:
            print(f"[SKIP] prompts.json에 없음: {part_name}")
            continue

        part_prompt = prompts[part_name]

        # null 또는 빈 문자열이면 수정 안 함
        if part_prompt is None or str(part_prompt).strip() == "":
            print(f"[SKIP] 수정 없음: {part_name}")
            continue

        x1, y1, x2, y2 = box
        part_img = texture.crop((x1, y1, x2, y2))

        try:
            edited_part = edit_part_with_gemini(
                client=client,
                part_name=part_name,
                part_img=part_img,
                part_prompt=part_prompt
            )

            if edited_part is None:
                continue

            # 수정 파츠 저장
            edited_part_path = os.path.join(EDITED_PARTS_DIR, f"{part_name}.png")
            edited_part.save(edited_part_path, "PNG")
            print(f"💾 수정 파츠 저장: {edited_part_path}")

            # 원본 텍스처에 합성
            final_texture.paste(edited_part, (x1, y1), edited_part)
            print(f"🎨 텍스처 합성 완료: {part_name}")

            edited_count += 1

            # quota 방지용 대기
            time.sleep(REQUEST_SLEEP_SECONDS)

        except Exception as e:
            print(f"❌ 오류 발생: {part_name}")
            print(e)
            continue

    # 최종 텍스처 저장
    final_texture.save(FINAL_TEXTURE_PATH, "PNG")

    print("\n[DONE]")
    print(f"수정된 파츠 수: {edited_count}")
    print(f"최종 결과 저장: {FINAL_TEXTURE_PATH}")

    check = Image.open(FINAL_TEXTURE_PATH)
    print(f"검증 모드: {check.mode}")
    print(f"검증 크기: {check.size}")


if __name__ == "__main__":
    main()