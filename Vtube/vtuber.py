"""
vtuber.py

prompts_cache_meta.json을 읽어서
- eye 또는 eye_prompt가 있으면 Gemini로 눈 모양 수정
- iris_rgb 또는 eye-color로 눈 색상 변경
- skin_rgb 또는 skin-color로 피부색 변경
- hair_rgb 또는 hair-color로 머리색 변경
을 수행한 뒤

1 원본 parts 폴더를 parts_modified 폴더로 복사
2 수정은 parts_modified 폴더 안에서만 진행
3 원본 parts 폴더는 건드리지 않음
4 parts 폴더의 parts_bbox_corrected.json 좌표를 참고
5 parts_modified 안의 파츠들을 합성
6 EXCLUDE_KEYWORDS에 해당하는 파츠는 합성에서 제외하고 빈 공간으로 둠

설치:
  pip install google-genai pillow numpy

실행:
  python vtuber.py
"""

import os
import io
import re
import json
import shutil
import hashlib
import numpy as np
from PIL import Image

from google import genai
from google.genai import types


# ── 경로 설정 ─────────────────────────────────────────────

BASE_DIR = r"C:\Users\82106\OneDrive\바탕 화면\Vtube"

PROMPTS_PATH = os.path.join(BASE_DIR, "prompts_cache_meta.json")

# 원본 parts 폴더
ORIGINAL_PARTS_DIR = os.path.join(BASE_DIR, "parts")

# 수정 작업용 복사본 parts 폴더
WORK_PARTS_DIR = os.path.join(BASE_DIR, "parts_modified")

PARTS_LOCATION_DIR = os.path.join(BASE_DIR, "parts_location")
RESULT_DIR = os.path.join(BASE_DIR, "result")

os.makedirs(RESULT_DIR, exist_ok=True)

FINAL_MERGED_PATH = os.path.join(RESULT_DIR, "final_merged_from_bbox.png")
DEBUG_EYE_SHEET_INPUT = os.path.join(RESULT_DIR, "_debug_eye_sheet_input.png")
DEBUG_EYE_SHEET_OUTPUT = os.path.join(RESULT_DIR, "_debug_eye_sheet_output.png")

# Gemini 캐시용 수정 눈 파츠 저장 폴더
EYE_CACHE_DIR = os.path.join(RESULT_DIR, "eye_edit_cache")

os.makedirs(EYE_CACHE_DIR, exist_ok=True)


# ── 복사 설정 ─────────────────────────────────────────────

# True면 실행할 때마다 원본 parts를 parts_modified로 새로 복사
# 원본 보존을 위해 기본 True 권장
RESET_WORK_PARTS_EACH_RUN = True


# ── 제외할 파츠 설정 ─────────────────────────────────────

# 파일명에 아래 단어가 들어가면 최종 합성에서 제외
# 예: hairband.png, hairband_left.png, hairband_right.png, pin_xxx.png
EXCLUDE_KEYWORDS = [
    "pin",
    "hairband",
]

# 정확한 파일명으로 제외하고 싶으면 여기에 추가
EXCLUDE_FILES = [
    # "hairband.png",
    # "hairband_left.png",
    # "hairband_right.png",
]


# ── API 설정 ─────────────────────────────────────────────

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY 환경변수가 없습니다\n"
        "CMD에서 먼저 실행하세요\n"
        "setx GEMINI_API_KEY \"새_API_KEY\""
    )

MODEL_NAME = "gemini-2.5-flash-image"

USE_CACHE = True
MANIFEST_PATH = os.path.join(RESULT_DIR, "vtuber_manifest.json")

SHEET_PADDING = 30
COLOR_STRENGTH = 0.95


# ── 파츠 그룹 정의 ───────────────────────────────────────

EYE_PARTS = ["eye_1.png", "eye_2.png","eye_3.png", "eye_4.png"]
FACE_PARTS = ["face.png"]
NECK_PARTS = ["neck.png"]


def prepare_work_parts_folder():
    """
    원본 parts 폴더를 parts_modified 폴더로 복사한다
    이후 모든 수정은 parts_modified 안에서만 진행한다
    """

    if not os.path.exists(ORIGINAL_PARTS_DIR):
        raise FileNotFoundError(f"원본 parts 폴더가 없습니다: {ORIGINAL_PARTS_DIR}")

    if RESET_WORK_PARTS_EACH_RUN:
        if os.path.exists(WORK_PARTS_DIR):
            shutil.rmtree(WORK_PARTS_DIR)

        shutil.copytree(ORIGINAL_PARTS_DIR, WORK_PARTS_DIR)

        print(f"[COPY] 원본 parts 폴더 복사 완료")
        print(f"       from: {ORIGINAL_PARTS_DIR}")
        print(f"       to  : {WORK_PARTS_DIR}")

    else:
        if not os.path.exists(WORK_PARTS_DIR):
            shutil.copytree(ORIGINAL_PARTS_DIR, WORK_PARTS_DIR)
            print(f"[COPY] parts_modified 폴더가 없어 새로 복사했습니다: {WORK_PARTS_DIR}")
        else:
            print(f"[INFO] 기존 parts_modified 폴더 사용: {WORK_PARTS_DIR}")


def get_hair_parts():
    parts = []

    if not os.path.exists(WORK_PARTS_DIR):
        return parts

    for name in sorted(os.listdir(WORK_PARTS_DIR)):
        lower = name.lower()

        if not lower.endswith(".png"):
            continue

        if lower.startswith("hair_") and not lower.startswith("hair_shadow_"):
            parts.append(name)
        elif lower == "hair_back.png":
            parts.append(name)

    return parts


def get_hair_shadow_parts():
    parts = []

    if not os.path.exists(WORK_PARTS_DIR):
        return parts

    for name in sorted(os.listdir(WORK_PARTS_DIR)):
        lower = name.lower()

        if lower.endswith(".png") and lower.startswith("hair_shadow_"):
            parts.append(name)

    return parts


# ── 기본 유틸 ─────────────────────────────────────────────

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def extract_prompts(data):
    """
    prompts_cache_meta.json에서 아래 키들을 코드가 쓰는 표준 키로 변환한다

    입력 가능:
    - hair_rgb
    - iris_rgb
    - skin_rgb
    - eye
    - eye_prompt
    - eye-shape
    - eye_shape

    코드 내부 표준 키:
    - hair-color
    - eye-color
    - skin-color
    - eye
    """

    if not isinstance(data, dict):
        raise ValueError("prompts_cache_meta.json 내용은 dict 형식이어야 합니다")

    for key in ["prompts", "prompt", "data", "result"]:
        value = data.get(key)

        if isinstance(value, dict):
            data = value
            break

    normalized = {}

    normalized["eye"] = (
        data.get("eye")
        or data.get("eye_prompt")
        or data.get("eye-shape")
        or data.get("eye_shape")
    )

    normalized["eye-color"] = (
        data.get("eye-color")
        or data.get("iris_rgb")
        or data.get("iris-color")
        or data.get("iris_color")
    )

    normalized["skin-color"] = (
        data.get("skin-color")
        or data.get("skin_rgb")
        or data.get("skin-color-rgb")
        or data.get("skin_color")
    )

    normalized["hair-color"] = (
        data.get("hair-color")
        or data.get("hair_rgb")
        or data.get("hair-color-rgb")
        or data.get("hair_color")
    )

    return normalized


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_sha256(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return sha256_bytes(buf.getvalue())


def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {}

    try:
        return load_json(MANIFEST_PATH)
    except Exception:
        return {}


def save_manifest(manifest):
    save_json(MANIFEST_PATH, manifest)


def parse_rgb(value):
    """
    허용 형식:
    - "rgb(55, 38, 25)"
    - [55, 38, 25]
    - (55, 38, 25)
    """

    if value is None:
        return None

    if isinstance(value, (list, tuple)) and len(value) == 3:
        r, g, b = value
        return int(r), int(g), int(b)

    if isinstance(value, str):
        m = re.match(
            r"rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)",
            value.strip(),
            re.IGNORECASE
        )

        if m:
            return tuple(int(x) for x in m.groups())

    return None


def file_exists_in_work_parts(filename):
    return os.path.exists(os.path.join(WORK_PARTS_DIR, filename))


def load_part(filename):
    path = os.path.join(WORK_PARTS_DIR, filename)
    return Image.open(path).convert("RGBA")


def save_part(img, filename):
    """
    원본 parts가 아니라 parts_modified 안에 저장한다
    """
    path = os.path.join(WORK_PARTS_DIR, filename)
    img.save(path, "PNG")
    print(f"[SAVE] {path}")


def list_existing_parts(file_list):
    return [f for f in file_list if file_exists_in_work_parts(f)]


def should_exclude_part(filename):
    """
    최종 합성에서 제외할 파츠인지 판단
    """
    lower = filename.lower()

    for exact in EXCLUDE_FILES:
        if lower == exact.lower():
            return True

    for keyword in EXCLUDE_KEYWORDS:
        if keyword.lower() in lower:
            return True

    return False


def clear_bbox_area(canvas, x1, y1, x2, y2):
    """
    제외 파츠 영역을 투명하게 비운다
    others.png에 해당 파츠 흔적이 남아 있어도 제거하기 위한 처리
    """
    arr = np.array(canvas.convert("RGBA"))
    h, w = arr.shape[:2]

    x1 = max(0, min(x1, w))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h))
    y2 = max(0, min(y2, h))

    if x2 <= x1 or y2 <= y1:
        return canvas

    arr[y1:y2, x1:x2, :] = 0
    return Image.fromarray(arr, "RGBA")


# ── 색상 변경 로직 ───────────────────────────────────────

def recolor_preserve_shading(img_rgba: Image.Image, target_rgb, strength=0.95):
    """
    원본의 음영 밝기와 알파를 유지하면서 타겟 색상으로 재색칠
    """

    arr = np.array(img_rgba.convert("RGBA")).astype(np.float32)

    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3:4] / 255.0

    lum = (
        0.299 * rgb[:, :, 0]
        + 0.587 * rgb[:, :, 1]
        + 0.114 * rgb[:, :, 2]
    ) / 255.0

    lum = np.expand_dims(lum, axis=2)

    target = np.array(target_rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0

    shade = 0.25 + 0.95 * lum
    recolored = target * shade

    original_norm = rgb / 255.0
    mixed = (1.0 - strength) * original_norm + strength * recolored

    out = np.zeros_like(arr)
    out[:, :, :3] = np.clip(mixed * 255.0, 0, 255)
    out[:, :, 3:4] = alpha * 255.0

    return Image.fromarray(out.astype(np.uint8), "RGBA")


def recolor_iris_only(img_rgba: Image.Image, target_rgb, strength=0.95):
    """
    눈 파츠에서 흰자처럼 밝은 부분은 최대한 보존하고
    어두운 홍채/라인 쪽만 타겟 색상으로 바꾼다
    """

    arr = np.array(img_rgba.convert("RGBA")).astype(np.float32)

    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    lum = (
        0.299 * rgb[:, :, 0]
        + 0.587 * rgb[:, :, 1]
        + 0.114 * rgb[:, :, 2]
    ) / 255.0

    visible_mask = alpha > 0
    color_mask = visible_mask & (lum < 0.88)

    if np.count_nonzero(color_mask) < 10:
        return recolor_preserve_shading(img_rgba, target_rgb, strength=strength)

    target = np.array(target_rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0
    original_norm = rgb / 255.0

    lum_expanded = np.expand_dims(lum, axis=2)
    shade = 0.25 + 0.95 * lum_expanded
    recolored = target * shade

    mixed = (1.0 - strength) * original_norm + strength * recolored

    out = arr.copy()
    out[:, :, :3][color_mask] = np.clip(
        mixed[:, :, :3][color_mask] * 255.0,
        0,
        255
    )

    return Image.fromarray(out.astype(np.uint8), "RGBA")


# ── 시트 생성 / 분리 ─────────────────────────────────────

def make_horizontal_sheet(filenames, padding=30):
    """
    여러 파츠를 가로로 붙인 투명 시트 생성
    Gemini 호출 횟수를 줄이기 위해 사용
    """

    images = []

    for name in filenames:
        img = load_part(name)
        images.append((name, img))

    if not images:
        return None, None

    total_width = padding
    max_height = 0

    for _, img in images:
        total_width += img.width + padding
        max_height = max(max_height, img.height)

    total_height = max_height + padding * 2

    sheet = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 0))
    placements = []

    x = padding

    for name, img in images:
        y = (total_height - img.height) // 2

        sheet.paste(img, (x, y), img)

        placements.append({
            "filename": name,
            "x": x,
            "y": y,
            "w": img.width,
            "h": img.height
        })

        x += img.width + padding

    return sheet, placements


def split_sheet(sheet_img, placements):
    """
    편집된 시트에서 개별 파츠 재추출
    """

    result = {}

    for item in placements:
        x = item["x"]
        y = item["y"]
        w = item["w"]
        h = item["h"]

        crop = sheet_img.crop((x, y, x + w, y + h)).convert("RGBA")
        result[item["filename"]] = crop

    return result


# ── Gemini 편집 ──────────────────────────────────────────

def make_eye_edit_prompt(eye_prompt):
    return f"""
You are editing a transparent sprite sheet containing only eye parts for a 2D anime Live2D character.

Edit instruction:
{eye_prompt}

Strict rules:
1. Edit only the eye shape and eye line details.
2. Keep the same number of eye parts.
3. Keep each eye sprite in the exact same place on the canvas.
4. Keep the transparent background fully transparent.
5. Preserve the original anime Live2D style.
6. Preserve the original shading direction and general lighting.
7. Do not add extra objects.
8. Do not change the canvas size.
9. Do not crop the image.
10. Keep colors as close as possible because recoloring may happen later.

Return an edited image only.
"""


def edit_eye_sheet_with_gemini(client, sheet_img, eye_prompt):
    """
    눈 모양 수정용 Gemini 호출
    """

    buf = io.BytesIO()
    sheet_img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    prompt = make_eye_edit_prompt(eye_prompt)

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
        raise RuntimeError("Gemini 응답에서 편집된 eye 시트를 찾지 못했습니다")

    return result_img


# ── bbox json 로드 및 합성 ───────────────────────────────

def find_bbox_json():
    """
    parts 폴더 안의 parts_bbox_corrected.json을 우선 사용
    이 파일은 new_file과 bbox를 가지고 있음
    """

    candidates = [
        os.path.join(ORIGINAL_PARTS_DIR, "parts_bbox_corrected.json"),
        os.path.join(WORK_PARTS_DIR, "parts_bbox_corrected.json"),
        os.path.join(PARTS_LOCATION_DIR, "parts_bbox_corrected.json"),
        os.path.join(PARTS_LOCATION_DIR, "parts_bbox.json"),
        os.path.join(ORIGINAL_PARTS_DIR, "parts_bbox.json"),
        os.path.join(WORK_PARTS_DIR, "parts_bbox.json"),
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    raise FileNotFoundError(
        "parts_bbox.json 또는 parts_bbox_corrected.json 파일을 찾을 수 없습니다"
    )


def normalize_bbox_records(raw_data):
    """
    bbox를 무조건 [x1, y1, x2, y2] 형식으로 해석한다
    """

    records = []

    if isinstance(raw_data, dict):
        if "parts" in raw_data:
            raw_data = raw_data["parts"]
        elif "items" in raw_data:
            raw_data = raw_data["items"]
        elif "data" in raw_data:
            raw_data = raw_data["data"]
        else:
            temp = []

            for key, value in raw_data.items():
                if isinstance(value, dict):
                    item = value.copy()
                    item.setdefault("filename", key)
                    temp.append(item)

            raw_data = temp

    if not isinstance(raw_data, list):
        return records

    for item in raw_data:
        if not isinstance(item, dict):
            continue

        filename = (
            item.get("new_file")
            or item.get("filename")
            or item.get("file")
            or item.get("name")
            or item.get("part")
        )

        if not filename:
            continue

        if not str(filename).lower().endswith(".png"):
            filename = f"{filename}.png"

        bbox = item.get("bbox")

        if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            continue

        x1, y1, x2, y2 = bbox[:4]

        records.append({
            "filename": str(filename),
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2),
        })

    return records


def merge_all_parts_from_bbox():
    """
    parts_modified의 others.png를 배경으로 깔고
    bbox에 있는 파츠들을 원래 위치에 붙인다

    EXCLUDE_KEYWORDS 또는 EXCLUDE_FILES에 해당하는 파츠는 붙이지 않고
    해당 영역은 투명하게 비운다
    """

    bbox_path = find_bbox_json()
    raw = load_json(bbox_path)
    records = normalize_bbox_records(raw)

    if not records:
        raise RuntimeError(f"bbox json 파싱 실패: {bbox_path}")

    print(f"[INFO] bbox 파일 사용: {bbox_path}")
    print(f"[INFO] bbox 레코드 수: {len(records)}")
    print(f"[INFO] 제외 키워드: {EXCLUDE_KEYWORDS}")
    print(f"[INFO] 제외 파일명: {EXCLUDE_FILES}")

    others_path = os.path.join(WORK_PARTS_DIR, "others.png")

    if os.path.exists(others_path):
        canvas = Image.open(others_path).convert("RGBA")
        print(f"[INFO] parts_modified의 others.png를 배경으로 사용: {others_path}")
    else:
        canvas = Image.new("RGBA", (4096, 4096), (0, 0, 0, 0))
        print("[WARN] others.png가 없어 4096x4096 투명 캔버스에서 시작합니다")

    for rec in records:
        filename = rec["filename"]

        x1 = rec["x1"]
        y1 = rec["y1"]
        x2 = rec["x2"]
        y2 = rec["y2"]

        target_w = x2 - x1
        target_h = y2 - y1

        if target_w <= 0 or target_h <= 0:
            print(f"[WARN] 잘못된 bbox 스킵: {filename} / {rec}")
            continue

        if should_exclude_part(filename):
            canvas = clear_bbox_area(canvas, x1, y1, x2, y2)
            print(f"[EXCLUDE] {filename} 영역 비움 -> ({x1}, {y1}, {x2}, {y2})")
            continue

        part_path = os.path.join(WORK_PARTS_DIR, filename)

        if not os.path.exists(part_path):
            print(f"[WARN] 파츠 없음 스킵: {part_path}")
            continue

        img = Image.open(part_path).convert("RGBA")

        if img.size != (target_w, target_h):
            print(
                f"[RESIZE] {filename}: "
                f"{img.size} -> {(target_w, target_h)}"
            )
            img = img.resize((target_w, target_h), Image.LANCZOS)

        canvas.paste(img, (x1, y1), img)
        print(f"[MERGE] {filename} -> ({x1}, {y1})")

    canvas.save(FINAL_MERGED_PATH, "PNG")
    print(f"[DONE] 최종 합성 저장: {FINAL_MERGED_PATH}")


# ── 캐시 키 ──────────────────────────────────────────────

def make_cache_key_for_eye_edit(eye_prompt, eye_part_names):
    payload = {
        "model": MODEL_NAME,
        "eye_prompt": eye_prompt,
        "eye_parts": eye_part_names,
    }

    hashes = {}

    for name in eye_part_names:
        if file_exists_in_work_parts(name):
            hashes[name] = image_sha256(load_part(name))

    payload["eye_part_hashes"] = hashes

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha256_bytes(text.encode("utf-8"))


def save_eye_cache_parts(cache_key, part_images):
    """
    Gemini로 수정된 eye 파츠를 result/eye_edit_cache/cache_key 폴더에 저장
    이후 같은 조건에서는 API 재호출 없이 이 파일들을 복사해 사용
    """

    cache_dir = os.path.join(EYE_CACHE_DIR, cache_key)
    os.makedirs(cache_dir, exist_ok=True)

    for filename, img in part_images.items():
        img.save(os.path.join(cache_dir, filename), "PNG")


def load_eye_cache_parts(cache_key, filenames):
    """
    캐시된 eye 파츠가 있으면 불러온다
    """

    cache_dir = os.path.join(EYE_CACHE_DIR, cache_key)

    if not os.path.exists(cache_dir):
        return None

    result = {}

    for filename in filenames:
        path = os.path.join(cache_dir, filename)

        if not os.path.exists(path):
            return None

        result[filename] = Image.open(path).convert("RGBA")

    return result


# ── 메인 처리 ────────────────────────────────────────────

def main():
    if not os.path.exists(PROMPTS_PATH):
        raise FileNotFoundError(
            f"prompts_cache_meta.json 파일이 없습니다: {PROMPTS_PATH}"
        )

    prepare_work_parts_folder()

    raw_prompts = load_json(PROMPTS_PATH)
    prompts = extract_prompts(raw_prompts)

    eye_prompt = prompts.get("eye")
    eye_color = parse_rgb(prompts.get("eye-color"))
    skin_color = parse_rgb(prompts.get("skin-color"))
    hair_color = parse_rgb(prompts.get("hair-color"))

    print("[INFO] 읽은 프롬프트/색상")
    print("eye:", eye_prompt)
    print("eye-color:", eye_color)
    print("skin-color:", skin_color)
    print("hair-color:", hair_color)

    if eye_prompt is None:
        print("[WARN] eye 프롬프트가 없습니다. 눈 모양 수정은 스킵됩니다.")

    if eye_color is None:
        print("[WARN] iris_rgb / eye-color가 없거나 형식이 잘못되었습니다")

    if skin_color is None:
        print("[WARN] skin_rgb / skin-color가 없거나 형식이 잘못되었습니다")

    if hair_color is None:
        print("[WARN] hair_rgb / hair-color가 없거나 형식이 잘못되었습니다")

    client = genai.Client(api_key=API_KEY)
    manifest = load_manifest()

    # 1 눈 모양 Gemini 수정
    existing_eye_parts = list_existing_parts(EYE_PARTS)

    if eye_prompt and existing_eye_parts:
        cache_key = make_cache_key_for_eye_edit(eye_prompt, existing_eye_parts)

        cached_parts = None

        if USE_CACHE:
            cached_parts = load_eye_cache_parts(cache_key, existing_eye_parts)

        if cached_parts is not None:
            print("[CACHE] eye 편집 결과 파츠를 캐시에서 불러와 적용합니다")

            for filename, img in cached_parts.items():
                save_part(img, filename)

            manifest["eye_edit"] = {
                "cache_key": cache_key,
                "eye_parts": existing_eye_parts,
                "cache_dir": os.path.join(EYE_CACHE_DIR, cache_key),
            }

            save_manifest(manifest)

        else:
            print("[STEP] eye Gemini 수정 시작")

            eye_sheet, placements = make_horizontal_sheet(
                existing_eye_parts,
                padding=SHEET_PADDING
            )

            eye_sheet.save(DEBUG_EYE_SHEET_INPUT, "PNG")

            edited_sheet = edit_eye_sheet_with_gemini(
                client,
                eye_sheet,
                eye_prompt
            )

            edited_sheet.save(DEBUG_EYE_SHEET_OUTPUT, "PNG")

            split_parts = split_sheet(edited_sheet, placements)

            for filename, img in split_parts.items():
                save_part(img, filename)

            save_eye_cache_parts(cache_key, split_parts)

            manifest["eye_edit"] = {
                "cache_key": cache_key,
                "eye_parts": existing_eye_parts,
                "cache_dir": os.path.join(EYE_CACHE_DIR, cache_key),
            }

            save_manifest(manifest)

    else:
        print("[SKIP] eye Gemini 수정 없음")

    # 2 eye-color / iris_rgb 로컬 재색칠
    if eye_color is not None and existing_eye_parts:
        print("[STEP] iris_rgb 기준 눈 색 로컬 재색칠 시작")
        print("[INFO] eye 대상:", existing_eye_parts)

        for filename in existing_eye_parts:
            img = load_part(filename)
            recolored = recolor_iris_only(
                img,
                eye_color,
                strength=COLOR_STRENGTH
            )
            save_part(recolored, filename)

    else:
        print("[SKIP] eye-color 재색칠 없음")

    # 3 skin-color / skin_rgb 로컬 재색칠
    skin_targets = list_existing_parts(
        FACE_PARTS
        + NECK_PARTS
        + [
            "part_128.png",
            "part_129.png",
        ]
    )

    if skin_color is not None and skin_targets:
        print("[STEP] skin_rgb 기준 피부색 로컬 재색칠 시작")
        print("[INFO] skin 대상:", skin_targets)

        for filename in skin_targets:
            img = load_part(filename)
            recolored = recolor_preserve_shading(
                img,
                skin_color,
                strength=COLOR_STRENGTH
            )
            save_part(recolored, filename)

    else:
        print("[SKIP] skin-color 재색칠 없음")

    # 4 hair-color / hair_rgb 로컬 재색칠
    hair_parts = get_hair_parts()
    hair_shadow_parts = get_hair_shadow_parts()
    hair_targets = list_existing_parts(hair_parts + hair_shadow_parts)

    if hair_color is not None and hair_targets:
        print("[STEP] hair_rgb 기준 머리색 로컬 재색칠 시작")
        print("[INFO] hair 대상:", hair_targets)

        for filename in hair_targets:
            img = load_part(filename)
            recolored = recolor_preserve_shading(
                img,
                hair_color,
                strength=COLOR_STRENGTH
            )
            save_part(recolored, filename)

    else:
        print("[SKIP] hair-color 재색칠 없음")

    # 5 bbox 기준 전체 합성
    print("[STEP] 전체 파츠 bbox 합성 시작")
    merge_all_parts_from_bbox()

    print("\n[DONE] 모든 작업 완료")
    print(f"[RESULT] 최종 결과: {FINAL_MERGED_PATH}")
    print(f"[RESULT] 수정된 파츠 폴더: {WORK_PARTS_DIR}")
    print(f"[INFO] 원본 parts 폴더는 보존됨: {ORIGINAL_PARTS_DIR}")


if __name__ == "__main__":
    main()