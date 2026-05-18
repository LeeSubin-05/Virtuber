r"""
vtuber_direct_colors.py

1번: parts
2번: parts_black
3번: parts_brown
4번: parts_gray

변경된 동작:
- 사용자가 번호를 직접 입력하지 않음
- C:\Users\82106\OneDrive\바탕 화면\Vtube\model.json 파일에서 숫자를 읽어옴
- 기존 코드 방식 그대로 해당 모델을 하나의 최종 결과물 사진으로 합성함
- 최종 결과는 C:\Users\82106\OneDrive\바탕 화면\Vtube\result 안에 저장함
- 번호별 결과 파일명을 다르게 저장함
  1번 -> result/final_parts.png
  2번 -> result/final_parts_black.png
  3번 -> result/final_parts_brown.png
  4번 -> result/final_parts_gray.png
- 다른 번호를 실행해도 기존 다른 번호 결과물은 삭제하지 않음

설치:
  pip install pillow numpy opencv-python

실행:
  python vtuber_direct_colors.py
"""

import os
import io
import re
import json
import hashlib
import cv2
import numpy as np
from PIL import Image, ImageChops

# 이 버전은 Gemini API를 사용하지 않습니다.
# google-genai / google-generativeai 패키지를 import하지 않으므로
# API 키, 월 사용량, spending cap 오류가 발생하지 않습니다.
genai = None
types = None


# =========================================================
# 기본 설정
# =========================================================

BASE_DIR = r"C:\Users\82106\OneDrive\바탕 화면\Vtube"
COLORS_DOWNLOAD_DIR = r"C:\Users\82106\Downloads"
MODEL_JSON_PATH = os.path.join(BASE_DIR, "model.json")
# 예전 코드와의 호환을 위해 경로 변수는 남겨두지만
# 이 버전은 prompty.py, prompts.json, prompts_cache_meta.json을 사용하지 않습니다.
# 색상은 COLORS_DOWNLOAD_DIR의 최신 color/colors JSON에서 직접 읽습니다.
PROMPTS_JSON_PATH = os.path.join(BASE_DIR, "prompts.json")
PROMPTS_CACHE_META_PATH = os.path.join(BASE_DIR, "prompts_cache_meta.json")
PROMPTS_PATH = PROMPTS_JSON_PATH

PARTS_LOCATION_DIR = os.path.join(BASE_DIR, "parts_location")

RESULT_DIR = os.path.join(BASE_DIR, "result")
os.makedirs(RESULT_DIR, exist_ok=True)

MODEL_NAME = "local-rgb-only"
SHEET_PADDING = 30
COLOR_STRENGTH = 0.95
GEMINI_BATCH_SIZE = 8

# 행사 안정성을 위해 Gemini 이미지 편집 API를 사용하지 않습니다.
# True로 바꾸지 않는 이상 vtuber.py는 로컬 RGB 색 입히기와 bbox 합성만 수행합니다.
API_IMAGE_EDIT_ENABLED = False

# True면 같은 프롬프트/파츠 조합에서 Gemini 결과를 재사용
# 캐시는 result 폴더가 아니라 BASE_DIR/result_cache_* 폴더에 저장됨
USE_CACHE = True


# =========================================================
# 피부색 변경 / 이음새 제거 설정
# =========================================================

# 핵심 변경점:
# skin 파츠를 하나씩 따로 색칠하면 face neck mouth 파츠마다 색/명암 평균이 달라져서 경계가 생긴다.
# 그래서 skin은 개별 파츠 색칠을 하지 않고 최종 합성 후 skin 영역 전체를 한 번에 색칠한다.
SKIN_RECOLOR_AT_FINAL_MERGE_ONLY = True

# 혹시 예전 방식으로 돌리고 싶으면 False로 바꾸면 된다.
SKIN_COLOR_STRENGTH = 1.0
SKIN_SHADE_STRENGTH = 0.10
SKIN_SHADE_MIN = 0.94
SKIN_SHADE_MAX = 1.06
SKIN_PART_BLUR_RADIUS = 2.0

# 최종 합성 후 skin 영역 전체 색칠 설정
POSTPROCESS_SKIN_SEAMS = True
POSTPROCESS_SKIN_BLEND = 0.985
POSTPROCESS_SKIN_DETAIL_STRENGTH = 0.035
POSTPROCESS_SKIN_SHADE_MIN = 0.965
POSTPROCESS_SKIN_SHADE_MAX = 1.035
POSTPROCESS_SKIN_MASK_DILATE = 1
POSTPROCESS_SKIN_MASK_CLOSE = 3
POSTPROCESS_SKIN_FEATHER_SIGMA = 0.8
POSTPROCESS_SKIN_LUM_SIGMA = 4.0

# True면 skin mask가 머리카락 아래까지 겹쳐 있어도 파란 머리/눈/옷은 보호한다.
PROTECT_NON_SKIN_COLORS_WHEN_FINAL_SKIN_RECOLOR = True

# eye 색 변경에서 제외할 파츠 이름 키워드
# 예: eye_white_001.png, sclera_001.png, highlight1.png
EYE_COLOR_EXCLUDE_KEYWORDS = [
    "white",
    "whites",
    "sclera",
    "highlight",
    "eye_white",
]

# skin 색 변경에서 제외할 파츠 이름 키워드
# 예: skin_blush_009.png, blush_009.png
SKIN_COLOR_EXCLUDE_KEYWORDS = [
    "blush",
    "skin_blush",
]


# =========================================================
# 모델별 설정
# =========================================================

MODEL_CONFIGS = {
    "1": {
        "label": "parts",
        "display_name": "parts",
        "original_dir": "parts",
        "result_filename": "final_parts.png",
        "bbox_candidates": [
            ("original", "parts_bbox_corrected.json"),
            ("location", "parts_bbox_corrected.json"),
            ("location", "parts_bbox.json"),
            ("original", "parts_bbox.json"),
        ],
        "exclude_keywords": ["pin", "hairband"],
        "exclude_files": [],
        # 예전 수동 파츠명과 새 자동분류 파츠명 둘 다 대응
        # 파츠 분리 코드가 eye.png / hair.png / skin_face.png처럼 저장하는 경우까지 대응
        "eye_files": ["eye.png", "eye_1.png", "eye_2.png", "eye_3.png", "eye_4.png"],
        "hair_files": ["hair.png", "hair_back.png"],
        "skin_files": [
            "skin_face.png", "skin_neck.png", "skin_extra.png",
            "face.png", "neck.png", "part_128.png", "part_129.png",
        ],
        "prefix_mode": "mixed",
        "gemini_groups": [],
        "local_color_groups": ["eye", "skin", "hair"],
    },
    "2": {
        "label": "black",
        "display_name": "parts_black",
        "original_dir": "parts_black",
        "result_filename": "final_parts_black.png",
        "bbox_candidates": [
            ("original", "parts_bbox_corrected.json"),
            ("location", "black_parts_bbox_corrected.json"),
            ("location", "parts_bbox_corrected.json"),
            ("location", "black_parts_bbox.json"),
            ("location", "parts_bbox.json"),
            ("original", "parts_bbox.json"),
        ],
        "exclude_keywords": [],
        "exclude_files": [],
        "eye_files": ["eye_1.png", "eye_2.png", "eye_5.png", "eye_6.png"],
        "hair_files": [
            "hair_l.png", "hair_l2.png", "hair_back.png", "hair_2.png",
            "hair_#.png", "hair_4.png", "hair_5.png", "hair_6.png",
            "hair7.png", "hair_8.png", "hair_9.png", "hair_10.png",
            "hair_11.png", "hair_13.png", "hair_14.png",
            "part_029.png", "part_030.png", "part_039.png",
        ],
        "skin_files": None,
        "prefix_mode": "black",
        "gemini_groups": [],
        "local_color_groups": ["eye", "skin", "hair"],
    },
    "3": {
        "label": "brown",
        "display_name": "parts_brown",
        "original_dir": "parts_brown",
        "result_filename": "final_parts_brown.png",
        "bbox_candidates": [
            ("original", "parts_bbox_corrected.json"),
            ("location", "brown_parts_bbox_corrected.json"),
            ("location", "parts_bbox_corrected.json"),
            ("location", "brown_parts_bbox.json"),
        ],
        "exclude_keywords": [],
        "exclude_files": [],
        "eye_files": None,
        "hair_files": None,
        "skin_files": None,
        "prefix_mode": "prefix",
        "gemini_groups": [],
        "local_color_groups": ["eye", "skin", "hair", "cloth"],
    },
    "4": {
        "label": "gray",
        "display_name": "parts_gray",
        "original_dir": "parts_gray",
        "result_filename": "final_parts_gray.png",
        "bbox_candidates": [
            ("original", "parts_bbox_corrected.json"),
            ("location", "gray_parts_bbox_corrected.json"),
            ("location", "parts_bbox_corrected.json"),
            ("location", "gray_parts_bbox.json"),
        ],
        "exclude_keywords": [],
        "exclude_files": [],
        "eye_files": None,
        "hair_files": None,
        "skin_files": None,
        "prefix_mode": "prefix",
        "gemini_groups": [],
        "local_color_groups": ["eye", "skin", "hair", "cloth"],
    },
}


# =========================================================
# 공통 유틸
# =========================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_model_choice_from_json(json_path):
    """
    model.json에서 실행할 모델 번호를 읽는다.

    허용 형식:
    2
    "2"
    {"model": 2}
    {"model_number": 2}
    {"choice": 2}
    {"number": 2}
    """

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"model.json 파일이 없습니다: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, int):
        choice = str(data)

    elif isinstance(data, str):
        choice = data.strip()

    elif isinstance(data, dict):
        value = (
            data.get("model")
            or data.get("model_number")
            or data.get("choice")
            or data.get("number")
        )

        if value is None:
            raise ValueError(
                "model.json이 dict 형식이면 model model_number choice number 중 하나의 키가 필요합니다\n"
                f"현재 내용: {data}"
            )

        choice = str(value).strip()

    else:
        raise ValueError(
            "model.json은 숫자 문자열 또는 dict 형식이어야 합니다\n"
            f"현재 타입: {type(data)} / 현재 내용: {data}"
        )

    if choice not in MODEL_CONFIGS:
        raise ValueError(
            "model.json의 숫자는 1 2 3 4 중 하나여야 합니다\n"
            f"현재 값: {choice}"
        )

    return choice


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_sha256(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return sha256_bytes(buf.getvalue())


def parse_rgb(value):
    """
    허용 형식
    - "rgb(55, 38, 25)"
    - [55, 38, 25]
    - (55, 38, 25)
    """

    if value is None:
        return None

    if isinstance(value, dict):
        try:
            rgb = (int(value["r"]), int(value["g"]), int(value["b"]))
        except (KeyError, TypeError, ValueError):
            return None

        if all(0 <= v <= 255 for v in rgb):
            return rgb

        return None

    if isinstance(value, (list, tuple)) and len(value) == 3:
        rgb = tuple(int(v) for v in value)
        if all(0 <= v <= 255 for v in rgb):
            return rgb
        return None

    if isinstance(value, str):
        m = re.match(
            r"rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)",
            value.strip(),
            re.IGNORECASE,
        )

        if m:
            rgb = tuple(int(x) for x in m.groups())
            if all(0 <= v <= 255 for v in rgb):
                return rgb

    return None


def get_original_dir(config):
    original_dir = os.path.join(BASE_DIR, config["original_dir"])

    if not os.path.exists(original_dir):
        raise FileNotFoundError(f"원본 파츠 폴더가 없습니다: {original_dir}")

    return original_dir


def get_result_path(config):
    os.makedirs(RESULT_DIR, exist_ok=True)
    return os.path.join(RESULT_DIR, config["result_filename"])


def list_png_files(parts_dir):
    if not os.path.exists(parts_dir):
        return []

    return sorted([
        name for name in os.listdir(parts_dir)
        if name.lower().endswith(".png")
    ])


def load_original_part(parts_dir, filename):
    path = os.path.join(parts_dir, filename)
    return Image.open(path).convert("RGBA")


def load_current_part(parts_dir, edited_parts, filename):
    """
    수정된 파츠가 메모리에 있으면 그것을 사용하고
    없으면 원본 parts 폴더에서 읽는다
    """

    if filename in edited_parts:
        return edited_parts[filename].copy()

    return load_original_part(parts_dir, filename)


def set_edited_part(edited_parts, img, filename):
    """
    수정 파츠를 파일로 저장하지 않고 메모리에만 보관한다
    """

    edited_parts[filename] = img.convert("RGBA")
    print(f"[MEMORY] {filename} 수정본 저장")


def file_exists(parts_dir, filename):
    return os.path.exists(os.path.join(parts_dir, filename))


def list_existing_parts(parts_dir, file_list):
    if not file_list:
        return []
    return [name for name in file_list if file_exists(parts_dir, name)]


def get_parts_by_prefix(parts_dir, prefix):
    result = []

    for name in list_png_files(parts_dir):
        lower = name.lower()

        if lower == "others.png":
            continue

        if lower.startswith(prefix.lower() + "_"):
            result.append(name)

    return sorted(result)


def get_skin_parts_by_prefix(parts_dir):
    result = []

    for name in list_png_files(parts_dir):
        lower = name.lower()

        if lower == "others.png":
            continue

        # skin_blush는 피부색 변경 대상에서 제외한다
        if lower.startswith("skin_") and not lower.startswith("skin_blush_"):
            result.append(name)

    return sorted(result)


def get_skin_parts_contains(parts_dir):
    result = []

    for name in list_png_files(parts_dir):
        lower = name.lower()

        if lower == "others.png":
            continue

        # skin_blush 같은 블러셔 파츠는 피부색 변경 대상에서 제외한다
        if "skin" in lower and "blush" not in lower:
            result.append(name)

    return sorted(result)


def get_hair_parts_for_parts_model(parts_dir):
    result = []

    for name in list_png_files(parts_dir):
        lower = name.lower()

        if lower == "others.png":
            continue

        if lower == "hair.png":
            result.append(name)
        elif lower.startswith("hair_") and not lower.startswith("hair_shadow_"):
            result.append(name)
        elif lower == "hair_back.png":
            result.append(name)

    return sorted(result)


def get_hair_shadow_parts_for_parts_model(parts_dir):
    result = []

    for name in list_png_files(parts_dir):
        lower = name.lower()

        if lower == "others.png":
            continue

        if lower == "hair_shadow.png":
            result.append(name)
        elif lower.startswith("hair_shadow_"):
            result.append(name)

    return sorted(result)


def filter_exception_parts(group_name, filenames):
    """
    색 변경/프롬프트 수정 대상에서 예외 파츠를 제거한다
    - eye: 흰자위, 하이라이트 등은 눈동자 색과 같이 바뀌지 않게 제외
    - skin: 블러셔는 피부색과 같이 바뀌지 않게 제외
    """

    if not filenames:
        return []

    if group_name == "eye":
        keywords = EYE_COLOR_EXCLUDE_KEYWORDS
    elif group_name == "skin":
        keywords = SKIN_COLOR_EXCLUDE_KEYWORDS
    else:
        return sorted(filenames)

    filtered = []

    for name in filenames:
        lower = name.lower()

        if any(keyword.lower() in lower for keyword in keywords):
            print(f"[EXCEPTION] {group_name} 색 변경 대상에서 제외: {name}")
            continue

        filtered.append(name)

    return sorted(filtered)


def get_group_parts(config, parts_dir, group_name):
    mode = config.get("prefix_mode", "prefix")

    if group_name == "eye":
        explicit = list_existing_parts(parts_dir, config.get("eye_files"))
        prefixed = get_parts_by_prefix(parts_dir, "eye")
        return filter_exception_parts(group_name, sorted(set(explicit + prefixed)))

    if group_name == "skin":
        explicit = list_existing_parts(parts_dir, config.get("skin_files"))

        if mode == "black":
            auto = get_skin_parts_contains(parts_dir)
        else:
            auto = get_skin_parts_by_prefix(parts_dir)

        return filter_exception_parts(group_name, sorted(set(explicit + auto)))

    if group_name == "hair":
        explicit = list_existing_parts(parts_dir, config.get("hair_files"))

        if mode == "mixed":
            auto = get_hair_parts_for_parts_model(parts_dir)
        else:
            auto = get_parts_by_prefix(parts_dir, "hair")

        return sorted(set(explicit + auto))

    if group_name == "hair_shadow":
        return get_hair_shadow_parts_for_parts_model(parts_dir)

    return get_parts_by_prefix(parts_dir, group_name)


def should_exclude_part(config, filename):
    lower = filename.lower()

    for exact in config.get("exclude_files", []):
        if lower == exact.lower():
            return True

    for keyword in config.get("exclude_keywords", []):
        if keyword.lower() in lower:
            return True

    return False



# =========================================================
# 최신 colors JSON 읽기
# =========================================================

def find_latest_colors_json(download_dir):
    """
    다운로드 폴더에서 파일명에 color 또는 colors가 들어간 json 파일 중
    가장 최근에 수정된 파일 경로를 반환한다.

    예:
      colors.json
      colors (2).json
      colors (3).json
      color (4).json
    """
    if not os.path.isdir(download_dir):
        raise FileNotFoundError(f"다운로드 폴더를 찾을 수 없습니다: {download_dir}")

    candidates = []

    for filename in os.listdir(download_dir):
        lower_name = filename.lower()

        if "color" in lower_name and lower_name.endswith(".json"):
            full_path = os.path.join(download_dir, filename)

            if os.path.isfile(full_path):
                candidates.append(full_path)

    if not candidates:
        raise FileNotFoundError(
            f"{download_dir} 안에서 파일명에 color가 들어간 json 파일을 찾지 못했습니다"
        )

    return max(candidates, key=os.path.getmtime)


def validate_rgb_value(category, name, value):
    """
    RGB 값 하나를 0~255 정수로 검증한다.
    """
    try:
        value = int(value)
    except Exception as e:
        raise ValueError(f"{category}.{name} 값이 정수가 아닙니다: {value}") from e

    if not 0 <= value <= 255:
        raise ValueError(f"{category}.{name} 값이 RGB 범위를 벗어났습니다: {value}")

    return value


def get_rgb_from_item(colors, category, colors_path, required=True):
    """
    colors JSON에서 특정 category의 RGB 튜플을 꺼낸다.

    기본 필수 항목:
      eye, hair, skin

    선택 항목:
      cloth
    """
    if category not in colors:
        if required:
            raise KeyError(f"colors JSON에 '{category}' 항목이 없습니다: {colors_path}")
        return None

    item = colors[category]

    if not isinstance(item, dict):
        raise ValueError(f"'{category}' 항목은 dict 형식이어야 합니다: {item}")

    missing_keys = [key for key in ["r", "g", "b"] if key not in item]
    if missing_keys:
        raise KeyError(
            f"'{category}' 항목에 RGB 키가 없습니다: {missing_keys} / 파일: {colors_path}"
        )

    r = validate_rgb_value(category, "r", item["r"])
    g = validate_rgb_value(category, "g", item["g"])
    b = validate_rgb_value(category, "b", item["b"])

    return (r, g, b)


def rgb_to_text(rgb):
    """
    RGB 튜플을 vtuber.py 내부 parse_rgb가 읽을 수 있는 문자열로 변환한다.
    """
    if rgb is None:
        return None

    r, g, b = rgb
    return f"rgb({r}, {g}, {b})"


def load_latest_colors_as_prompt_inputs():
    """
    prompty.py 없이 최신 colors JSON을 직접 읽어서
    기존 vtuber.py의 extract_prompts 함수가 이해할 수 있는 dict로 변환한다.
    """
    colors_path = find_latest_colors_json(COLORS_DOWNLOAD_DIR)

    with open(colors_path, "r", encoding="utf-8") as f:
        colors = json.load(f)

    if not isinstance(colors, dict):
        raise ValueError(f"colors JSON은 dict 형식이어야 합니다: {colors_path}")

    hair_rgb = get_rgb_from_item(colors, "hair", colors_path, required=True)
    iris_rgb = get_rgb_from_item(colors, "eye", colors_path, required=True)
    skin_rgb = get_rgb_from_item(colors, "skin", colors_path, required=True)
    cloth_rgb = get_rgb_from_item(colors, "cloth", colors_path, required=False)

    print(f"[INFO] 색상 JSON 사용: {colors_path}")
    print(f"[INFO] hair RGB: {hair_rgb}")
    print(f"[INFO] eye RGB: {iris_rgb}")
    print(f"[INFO] skin RGB: {skin_rgb}")

    if cloth_rgb is not None:
        print(f"[INFO] cloth RGB: {cloth_rgb}")
    else:
        print("[INFO] cloth RGB: 없음 옷 색은 변경하지 않습니다")

    # extract_prompts 함수가 기존 방식 그대로 읽을 수 있도록
    # 여러 키 이름을 같이 넣어 둔다.
    data = {
        "mode": "direct_colors_json_no_prompty_no_api",
        "colors_path": colors_path,

        "hair_rgb": list(hair_rgb),
        "iris_rgb": list(iris_rgb),
        "skin_rgb": list(skin_rgb),

        "hair_color": rgb_to_text(hair_rgb),
        "eye_color": rgb_to_text(iris_rgb),
        "skin_color": rgb_to_text(skin_rgb),

        "hair_prompt": None,
        "eye_prompt": None,
        "skin_prompt": None,
        "cloth_prompt": None,
        "mouth_prompt": None,
        "shoes_prompt": None,
        "pin_prompt": None,
    }

    if cloth_rgb is not None:
        data["cloth_rgb"] = list(cloth_rgb)
        data["cloth_color"] = rgb_to_text(cloth_rgb)

    return data

# =========================================================
# prompts_cache_meta.json 해석
# =========================================================

def normalize_prompt_value(value):
    """
    prompts.json 값이 문자열이면 그대로 쓰고
    null 빈 문자열이면 None으로 정리한다.
    """
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        return value

    return None


def combine_prompt_values(*values):
    """
    여러 파츠 프롬프트를 한 그룹 프롬프트로 합친다.
    Gemini에게 넘길 때 너무 길어지지 않도록 중복은 제거한다.
    """
    result = []
    seen = set()

    for value in values:
        value = normalize_prompt_value(value)

        if not value:
            continue

        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    if not result:
        return None

    return " / ".join(result)


def extract_prompts(data):
    """
    다양한 키 이름을 내부 표준 키로 변환한다.

    대응하는 입력:
    1. 예전 방식
       {
         "eye": "...",
         "hair": "...",
         "skin": "...",
         "iris_rgb": [255, 0, 0]
       }

    2. 현재 prompty.py 방식
       prompts.json:
       {
         "hair_long_back_left": "...",
         "face_expression_eye_set": "...",
         "upper_body_outfit_set": null
       }

       prompts_cache_meta.json:
       {
         "hair_rgb": [255, 0, 0],
         "iris_rgb": [255, 0, 0],
         "skin_rgb": [214, 249, 255]
       }

    이 함수는 prompts.json과 prompts_cache_meta.json을 합친 dict도 처리한다.
    """

    if not isinstance(data, dict):
        raise ValueError("프롬프트 JSON 내용은 dict 형식이어야 합니다")

    for key in ["prompts", "prompt", "data", "result"]:
        value = data.get(key)
        if isinstance(value, dict):
            data = value
            break

    normalized = {}

    # prompty.py의 PART_NAMES 기준 프롬프트를 vtuber.py의 그룹 프롬프트로 묶는다.
    hair_prompt_from_parts = combine_prompt_values(
        data.get("hair_long_back_left"),
        data.get("hair_bangs_center_set"),
        data.get("hair_pink_twin_set"),
        data.get("hair_or_accessory_purple_lower_left_candidate"),
    )

    eye_prompt_from_parts = combine_prompt_values(
        data.get("face_expression_eye_set"),
    )

    skin_prompt_from_parts = combine_prompt_values(
        data.get("face_head_base_set"),
        data.get("small_detached_body_parts"),
    )

    cloth_prompt_from_parts = combine_prompt_values(
        data.get("upper_body_outfit_set"),
        data.get("skirt"),
        data.get("legs_stockings_pair"),
        data.get("shorts_underwear"),
        data.get("lower_leg_boots_socks_set"),
        data.get("arm_hand_set"),
        data.get("bunny_ears_pair"),
        data.get("ribbon_bow_accessory_set"),
        data.get("small_top_center_parts"),
    )

    shoes_prompt_from_parts = combine_prompt_values(
        data.get("shoes_pair"),
    )

    pin_prompt_from_parts = combine_prompt_values(
        data.get("ribbon_bow_accessory_set"),
        data.get("effect_symbols_top_right"),
        data.get("small_top_center_parts"),
    )

    normalized["eye_prompt"] = (
        normalize_prompt_value(data.get("eye"))
        or normalize_prompt_value(data.get("eye_prompt"))
        or normalize_prompt_value(data.get("eye-shape"))
        or normalize_prompt_value(data.get("eye_shape"))
        or eye_prompt_from_parts
    )

    normalized["hair_prompt"] = (
        normalize_prompt_value(data.get("hair"))
        or normalize_prompt_value(data.get("hair_prompt"))
        or normalize_prompt_value(data.get("hair-shape"))
        or normalize_prompt_value(data.get("hair_shape"))
        or hair_prompt_from_parts
    )

    normalized["skin_prompt"] = (
        normalize_prompt_value(data.get("skin"))
        or normalize_prompt_value(data.get("skin_prompt"))
        or normalize_prompt_value(data.get("skin-tone-prompt"))
        or normalize_prompt_value(data.get("skin_tone_prompt"))
        or skin_prompt_from_parts
    )

    normalized["cloth_prompt"] = (
        normalize_prompt_value(data.get("cloth"))
        or normalize_prompt_value(data.get("cloth_prompt"))
        or normalize_prompt_value(data.get("outfit"))
        or normalize_prompt_value(data.get("outfit_prompt"))
        or cloth_prompt_from_parts
    )

    normalized["mouth_prompt"] = (
        normalize_prompt_value(data.get("mouth"))
        or normalize_prompt_value(data.get("mouth_prompt"))
        or normalize_prompt_value(data.get("expression"))
        or normalize_prompt_value(data.get("expression_prompt"))
    )

    normalized["shoes_prompt"] = (
        normalize_prompt_value(data.get("shoes"))
        or normalize_prompt_value(data.get("shoes_prompt"))
        or shoes_prompt_from_parts
    )

    normalized["pin_prompt"] = (
        normalize_prompt_value(data.get("pin"))
        or normalize_prompt_value(data.get("pin_prompt"))
        or normalize_prompt_value(data.get("accessory"))
        or normalize_prompt_value(data.get("accessory_prompt"))
        or pin_prompt_from_parts
    )

    normalized["eye_color"] = (
        data.get("eye-color")
        or data.get("iris_rgb")
        or data.get("iris-color")
        or data.get("iris_color")
        or data.get("eye_rgb")
        or data.get("eye_color")
    )

    normalized["skin_color"] = (
        data.get("skin-color")
        or data.get("skin_rgb")
        or data.get("skin-color-rgb")
        or data.get("skin_color")
    )

    normalized["hair_color"] = (
        data.get("hair-color")
        or data.get("hair_rgb")
        or data.get("hair-color-rgb")
        or data.get("hair_color")
    )

    normalized["cloth_color"] = (
        data.get("cloth-color")
        or data.get("cloth_rgb")
        or data.get("outfit-color")
        or data.get("outfit_rgb")
        or data.get("cloth_color")
    )

    return normalized


def load_prompt_inputs():
    """
    최신 colors JSON을 직접 읽어 vtuber.py에서 쓰기 쉬운 dict로 반환한다.

    이 버전에서는 prompty.py, prompts.json, prompts_cache_meta.json이 필요 없다.
    """
    return load_latest_colors_as_prompt_inputs()

# =========================================================
# 색상 변경
# =========================================================

def recolor_preserve_shading(img_rgba: Image.Image, target_rgb, strength=0.95):
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
        255,
    )

    return Image.fromarray(out.astype(np.uint8), "RGBA")


def recolor_skin_clean(img_rgba: Image.Image, target_rgb, strength=1.0):
    """
    예전 방식으로 skin 파츠를 개별 색칠할 때 쓰는 함수.
    현재 기본값에서는 SKIN_RECOLOR_AT_FINAL_MERGE_ONLY=True라서 보통 사용되지 않는다.
    """

    arr = np.array(img_rgba.convert("RGBA")).astype(np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    visible = alpha > 0

    if np.count_nonzero(visible) < 10:
        return recolor_preserve_shading(img_rgba, target_rgb, strength=strength)

    lum = (
        0.299 * rgb[:, :, 0]
        + 0.587 * rgb[:, :, 1]
        + 0.114 * rgb[:, :, 2]
    ) / 255.0

    lum_blur = cv2.GaussianBlur(
        lum.astype(np.float32),
        (0, 0),
        sigmaX=SKIN_PART_BLUR_RADIUS,
        sigmaY=SKIN_PART_BLUR_RADIUS,
    )

    median_lum = float(np.median(lum_blur[visible]))
    shade = 1.0 + (lum_blur - median_lum) * SKIN_SHADE_STRENGTH
    shade = np.clip(shade, SKIN_SHADE_MIN, SKIN_SHADE_MAX)

    target = np.array(target_rgb, dtype=np.float32).reshape(1, 1, 3)
    clean_rgb = target * shade[:, :, None]

    out = arr.copy()
    mixed = (1.0 - strength) * rgb + strength * clean_rgb
    out[:, :, :3] = np.clip(mixed, 0, 255)

    return Image.fromarray(out.astype(np.uint8), "RGBA")


def build_visible_skin_mask_from_canvas(canvas_arr, skin_mask_float):
    """
    skin 파츠 alpha mask가 머리카락이나 눈 아래까지 깔려 있을 수 있어서
    최종 캔버스에서 실제로 skin처럼 보이는 색만 한 번 더 골라낸다.
    """

    if not PROTECT_NON_SKIN_COLORS_WHEN_FINAL_SKIN_RECOLOR:
        return skin_mask_float

    rgb = canvas_arr[:, :, :3].astype(np.uint8)
    alpha = canvas_arr[:, :, 3]

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)

    visible = alpha > 0

    # 원본 skin은 대체로 살구색/분홍/저채도 밝은 색이다.
    # 입선처럼 어두운 선도 저채도라면 포함한다.
    skin_like_1 = ((h <= 24) | (h >= 165)) & (s <= 155) & (v >= 35)
    skin_like_2 = (s <= 80) & (v >= 45)
    skin_like_3 = (r >= 120) & (r >= g - 12) & (g >= b - 18) & (s <= 150)

    # 명확하게 보호할 색: 파란 머리 고채도 빨강 장식 진한 보라 등
    strong_blue = (h >= 90) & (h <= 140) & (s >= 70)
    strong_green = (h >= 45) & (h <= 89) & (s >= 90)
    strong_purple = (h >= 135) & (h <= 164) & (s >= 90)
    strong_red = ((h <= 8) | (h >= 172)) & (s >= 170) & (v >= 80)

    protect = strong_blue | strong_green | strong_purple | strong_red
    skin_like = visible & (skin_like_1 | skin_like_2 | skin_like_3) & (~protect)

    refined = skin_mask_float * skin_like.astype(np.float32)
    return refined


def smooth_skin_regions_on_canvas(canvas: Image.Image, target_rgb, skin_mask_image: Image.Image):
    """
    최종 합성된 캔버스에서 skin 파츠 영역 전체를 한 번에 색칠한다.

    이전 문제의 핵심은 skin 파츠를 각각 따로 색칠해서 생긴 경계였으므로
    여기서는 skin을 한 덩어리로 보고 색을 다시 입힌다.
    """

    if target_rgb is None or skin_mask_image is None:
        return canvas

    canvas_rgba = canvas.convert("RGBA")
    arr = np.array(canvas_rgba).astype(np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    raw_mask = np.array(skin_mask_image.convert("L")).astype(np.uint8)

    if np.count_nonzero(raw_mask > 0) < 20:
        return canvas

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    if POSTPROCESS_SKIN_MASK_CLOSE > 0:
        raw_mask = cv2.morphologyEx(
            raw_mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=POSTPROCESS_SKIN_MASK_CLOSE,
        )

    if POSTPROCESS_SKIN_MASK_DILATE > 0:
        raw_mask = cv2.dilate(
            raw_mask,
            kernel,
            iterations=POSTPROCESS_SKIN_MASK_DILATE,
        )

    mask_float = raw_mask.astype(np.float32) / 255.0
    mask_float = build_visible_skin_mask_from_canvas(arr, mask_float)

    mask_float = cv2.GaussianBlur(
        mask_float,
        (0, 0),
        sigmaX=POSTPROCESS_SKIN_FEATHER_SIGMA,
        sigmaY=POSTPROCESS_SKIN_FEATHER_SIGMA,
    )

    mask_float = np.clip(mask_float * POSTPROCESS_SKIN_BLEND, 0.0, POSTPROCESS_SKIN_BLEND)

    visible = (alpha > 0) & (mask_float > 0.02)

    if np.count_nonzero(visible) < 20:
        return canvas

    lum = (
        0.299 * rgb[:, :, 0]
        + 0.587 * rgb[:, :, 1]
        + 0.114 * rgb[:, :, 2]
    ) / 255.0

    # 큰 반경으로 흐리게 해서 파츠별 경계 명암을 날린다.
    lum_blur = cv2.GaussianBlur(
        lum.astype(np.float32),
        (0, 0),
        sigmaX=POSTPROCESS_SKIN_LUM_SIGMA,
        sigmaY=POSTPROCESS_SKIN_LUM_SIGMA,
    )

    median_lum = float(np.median(lum_blur[visible]))

    shade = 1.0 + (lum_blur - median_lum) * POSTPROCESS_SKIN_DETAIL_STRENGTH
    shade = np.clip(shade, POSTPROCESS_SKIN_SHADE_MIN, POSTPROCESS_SKIN_SHADE_MAX)

    target = np.array(target_rgb, dtype=np.float32).reshape(1, 1, 3)
    clean_rgb = target * shade[:, :, None]

    blend = mask_float[:, :, None]
    out_rgb = rgb * (1.0 - blend) + clean_rgb * blend

    out = arr.copy()
    out[:, :, :3] = np.clip(out_rgb, 0, 255)

    return Image.fromarray(out.astype(np.uint8), "RGBA")


# =========================================================
# Gemini 편집
# =========================================================

def chunk_list(items, chunk_size):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def make_horizontal_sheet(parts_dir, edited_parts, filenames, padding=30):
    images = []

    for name in filenames:
        img = load_current_part(parts_dir, edited_parts, name)
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
            "h": img.height,
        })

        x += img.width + padding

    return sheet, placements


def split_sheet(sheet_img, placements):
    result = {}

    for item in placements:
        x = item["x"]
        y = item["y"]
        w = item["w"]
        h = item["h"]

        crop = sheet_img.crop((x, y, x + w, y + h)).convert("RGBA")
        result[item["filename"]] = crop

    return result


def make_group_edit_prompt(group_name, user_prompt):
    return f"""
You are editing a transparent sprite sheet containing only {group_name} parts for a 2D anime Live2D character.

Edit instruction:
{user_prompt}

Strict rules:
1. Edit only the visible {group_name} parts.
2. Keep the same number of sprites.
3. Keep each sprite in the exact same place on the canvas.
4. Keep the transparent background fully transparent.
5. Preserve the original anime Live2D style.
6. Preserve the original shading direction and general lighting.
7. Do not add extra objects outside the given parts.
8. Do not change the canvas size.
9. Do not crop the image.
10. Keep the alpha shape as stable as possible.
11. Do not merge separate sprites into one sprite.
12. Return an edited image only.
"""


def edit_sheet_with_gemini(client, sheet_img, group_name, user_prompt):
    if genai is None or types is None:
        raise RuntimeError(
            "google-genai 패키지가 없습니다. 먼저 설치하세요\n"
            "pip install google-genai"
        )

    buf = io.BytesIO()
    sheet_img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    prompt = make_group_edit_prompt(group_name, user_prompt)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            prompt,
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        ),
    )

    result_img = None

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            result_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
            break

    if result_img is None:
        raise RuntimeError(f"Gemini 응답에서 편집된 {group_name} 시트를 찾지 못했습니다")

    return result_img


def make_cache_key_for_group_edit(parts_dir, edited_parts, group_name, group_prompt, part_names):
    payload = {
        "model": MODEL_NAME,
        "group_name": group_name,
        "group_prompt": group_prompt,
        "parts": part_names,
    }

    hashes = {}

    for name in part_names:
        if file_exists(parts_dir, name):
            hashes[name] = image_sha256(load_current_part(parts_dir, edited_parts, name))

    payload["part_hashes"] = hashes

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha256_bytes(text.encode("utf-8"))


def cache_dir_for_model(label):
    path = os.path.join(BASE_DIR, f"result_cache_{label}")
    os.makedirs(path, exist_ok=True)
    return path


def save_cache_parts(model_cache_dir, cache_key, part_images):
    cache_dir = os.path.join(model_cache_dir, cache_key)
    os.makedirs(cache_dir, exist_ok=True)

    for filename, img in part_images.items():
        img.save(os.path.join(cache_dir, filename), "PNG")


def load_cache_parts(model_cache_dir, cache_key, filenames):
    cache_dir = os.path.join(model_cache_dir, cache_key)

    if not os.path.exists(cache_dir):
        return None

    result = {}

    for filename in filenames:
        path = os.path.join(cache_dir, filename)

        if not os.path.exists(path):
            return None

        result[filename] = Image.open(path).convert("RGBA")

    return result


def edit_group_parts_with_gemini(client, config, parts_dir, edited_parts, group_name, filenames, group_prompt):
    if not group_prompt:
        print(f"[SKIP] {group_name} 프롬프트 없음")
        return

    if not filenames:
        print(f"[SKIP] {group_name} 대상 파츠 없음")
        return

    print(f"[STEP] {group_name} Gemini 수정 시작")
    print(f"[INFO] {group_name} 대상 수:", len(filenames))

    model_cache_dir = cache_dir_for_model(config["label"])

    for batch_index, batch_names in enumerate(chunk_list(filenames, GEMINI_BATCH_SIZE), start=1):
        cache_key = make_cache_key_for_group_edit(
            parts_dir,
            edited_parts,
            group_name,
            group_prompt,
            batch_names,
        )

        cached_parts = None
        if USE_CACHE:
            cached_parts = load_cache_parts(model_cache_dir, cache_key, batch_names)

        if cached_parts is not None:
            print(f"[CACHE] {group_name} batch {batch_index} 캐시 사용")
            for filename, img in cached_parts.items():
                set_edited_part(edited_parts, img, filename)
            continue

        sheet, placements = make_horizontal_sheet(
            parts_dir,
            edited_parts,
            batch_names,
            padding=SHEET_PADDING,
        )

        edited_sheet = edit_sheet_with_gemini(
            client,
            sheet,
            group_name,
            group_prompt,
        )

        split_parts = split_sheet(edited_sheet, placements)

        for filename, img in split_parts.items():
            set_edited_part(edited_parts, img, filename)

        if USE_CACHE:
            save_cache_parts(model_cache_dir, cache_key, split_parts)

    print(f"[DONE] {group_name} Gemini 수정 완료")


# =========================================================
# bbox 합성
# =========================================================

def find_bbox_json(config, original_dir):
    base_map = {
        "original": original_dir,
        "location": PARTS_LOCATION_DIR,
    }

    for base_key, filename in config["bbox_candidates"]:
        path = os.path.join(base_map[base_key], filename)
        if os.path.exists(path):
            return path

    raise FileNotFoundError(f"{config['label']} 모델 bbox json을 찾을 수 없습니다")


def normalize_bbox_records(raw_data):
    if isinstance(raw_data, dict):
        if "extracted_parts" in raw_data:
            raw_data = raw_data["extracted_parts"]
        elif "parts" in raw_data:
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

    records = []

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



def clear_bbox_area(canvas, x1, y1, x2, y2):
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



def add_part_alpha_to_skin_mask(skin_mask_canvas, img, x1, y1):
    alpha = img.getchannel("A")
    temp_mask = Image.new("L", skin_mask_canvas.size, 0)
    temp_mask.paste(alpha, (x1, y1))
    return ImageChops.lighter(skin_mask_canvas, temp_mask)

def merge_all_parts_from_bbox(config, original_dir, edited_parts, skin_color=None, skin_filenames=None):
    bbox_path = find_bbox_json(config, original_dir)
    raw = load_json(bbox_path)
    records = normalize_bbox_records(raw)

    if not records:
        raise RuntimeError(f"bbox json 파싱 실패: {bbox_path}")

    print(f"[INFO] bbox 파일 사용: {bbox_path}")
    print(f"[INFO] bbox 레코드 수: {len(records)}")

    others_path = os.path.join(original_dir, "others.png")

    if os.path.exists(others_path):
        canvas = Image.open(others_path).convert("RGBA")
        print(f"[INFO] others.png를 배경으로 사용: {others_path}")
    else:
        max_x = max(rec["x2"] for rec in records)
        max_y = max(rec["y2"] for rec in records)
        canvas = Image.new("RGBA", (max_x, max_y), (0, 0, 0, 0))
        print("[WARN] others.png가 없어 투명 캔버스에서 시작합니다")

    skin_filenames = set(skin_filenames or [])
    skin_mask_canvas = Image.new("L", canvas.size, 0)

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

        if should_exclude_part(config, filename):
            canvas = clear_bbox_area(canvas, x1, y1, x2, y2)
            print(f"[EXCLUDE] {filename} 영역 비움 -> ({x1}, {y1}, {x2}, {y2})")
            continue

        part_path = os.path.join(original_dir, filename)

        if filename in edited_parts:
            img = edited_parts[filename].copy().convert("RGBA")
        elif os.path.exists(part_path):
            img = Image.open(part_path).convert("RGBA")
        else:
            print(f"[WARN] 파츠 없음 스킵: {part_path}")
            continue

        if img.size != (target_w, target_h):
            print(f"[RESIZE] {filename}: {img.size} -> {(target_w, target_h)}")
            img = img.resize((target_w, target_h), Image.LANCZOS)

        canvas.paste(img, (x1, y1), img)

        if filename in skin_filenames:
            skin_mask_canvas = add_part_alpha_to_skin_mask(
                skin_mask_canvas,
                img,
                x1,
                y1,
            )

        print(f"[MERGE] {filename} -> ({x1}, {y1})")

    if POSTPROCESS_SKIN_SEAMS and skin_color is not None and skin_filenames:
        print("[STEP] 최종 skin 이음새 제거용 전체 재색칠 시작")
        canvas = smooth_skin_regions_on_canvas(
            canvas,
            skin_color,
            skin_mask_canvas,
        )
        print("[DONE] 최종 skin 이음새 제거용 전체 재색칠 완료")

    result_path = get_result_path(config)
    os.makedirs(RESULT_DIR, exist_ok=True)
    canvas.save(result_path, "PNG")

    print(f"[DONE] 최종 합성 저장: {result_path}")
    return result_path


# =========================================================
# 실행
# =========================================================

def needs_gemini(prompts, config):
    """
    현재 버전은 행사 안정성을 위해 Gemini 이미지 편집 API를 기본 비활성화한다.
    따라서 프롬프트가 있어도 RGB 로컬 색 입히기만 수행한다.
    """
    if not API_IMAGE_EDIT_ENABLED:
        return False

    for group in config.get("gemini_groups", []):
        if prompts.get(f"{group}_prompt"):
            return True
    return False


def run_model(config):
    print()
    print(f"[MODEL] {config['display_name']} 실행")

    original_dir = get_original_dir(config)
    edited_parts = {}

    raw_prompts = load_prompt_inputs()
    prompts = extract_prompts(raw_prompts)

    eye_color = parse_rgb(prompts.get("eye_color"))
    skin_color = parse_rgb(prompts.get("skin_color"))
    hair_color = parse_rgb(prompts.get("hair_color"))
    cloth_color = parse_rgb(prompts.get("cloth_color"))

    print("[INFO] 읽은 프롬프트/색상")
    print("eye_prompt:", prompts.get("eye_prompt"))
    print("hair_prompt:", prompts.get("hair_prompt"))
    print("skin_prompt:", prompts.get("skin_prompt"))
    print("cloth_prompt:", prompts.get("cloth_prompt"))
    print("mouth_prompt:", prompts.get("mouth_prompt"))
    print("shoes_prompt:", prompts.get("shoes_prompt"))
    print("pin_prompt:", prompts.get("pin_prompt"))
    print("eye_color:", eye_color)
    print("skin_color:", skin_color)
    print("hair_color:", hair_color)
    print("cloth_color:", cloth_color)

    client = None
    if needs_gemini(prompts, config):
        if genai is None:
            raise RuntimeError(
                "google-genai 패키지가 없습니다. 먼저 설치하세요\n"
                "pip install google-genai"
            )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY 환경변수가 없습니다\n"
                "CMD에서 먼저 실행하세요\n"
                "setx GEMINI_API_KEY \"새_API_KEY\""
            )
        client = genai.Client(api_key=api_key)

    # 1 Gemini 프롬프트 기반 파츠 수정
    if client is not None:
        for group in config.get("gemini_groups", []):
            filenames = get_group_parts(config, original_dir, group)
            group_prompt = prompts.get(f"{group}_prompt")
            edit_group_parts_with_gemini(
                client,
                config,
                original_dir,
                edited_parts,
                group,
                filenames,
                group_prompt,
            )
    else:
        print("[SKIP] API 이미지 편집 없음 RGB 로컬 색 입히기만 실행")

    # 2 RGB 기반 로컬 색상 변경
    if "eye" in config.get("local_color_groups", []):
        eye_targets = get_group_parts(config, original_dir, "eye")
        if eye_color is not None and eye_targets:
            print("[STEP] eye_color / iris_rgb 기준 눈 색 로컬 재색칠 시작")
            print("[INFO] eye 대상:", eye_targets)
            for filename in eye_targets:
                img = load_current_part(original_dir, edited_parts, filename)
                recolored = recolor_iris_only(img, eye_color, strength=COLOR_STRENGTH)
                set_edited_part(edited_parts, recolored, filename)
        else:
            print("[SKIP] eye-color 재색칠 없음")

    skin_targets_for_merge = set()

    if "skin" in config.get("local_color_groups", []):
        skin_targets = get_group_parts(config, original_dir, "skin")
        skin_targets_for_merge = set(skin_targets)

        if skin_color is not None and skin_targets:
            if SKIN_RECOLOR_AT_FINAL_MERGE_ONLY:
                print("[STEP] skin은 개별 파츠 색칠을 건너뜁니다")
                print("[INFO] 이유: 최종 합성 후 skin 영역 전체를 한 번에 색칠해야 이음새가 가장 적게 남습니다")
                print("[INFO] 최종 skin 대상:", skin_targets)
            else:
                print("[STEP] skin_rgb 기준 피부색 로컬 재색칠 시작")
                print("[INFO] skin 대상:", skin_targets)
                for filename in skin_targets:
                    img = load_current_part(original_dir, edited_parts, filename)
                    recolored = recolor_skin_clean(img, skin_color, strength=SKIN_COLOR_STRENGTH)
                    set_edited_part(edited_parts, recolored, filename)
        else:
            print("[SKIP] skin-color 재색칠 없음")

    if "hair" in config.get("local_color_groups", []):
        hair_targets = get_group_parts(config, original_dir, "hair")
        hair_shadow_targets = get_group_parts(config, original_dir, "hair_shadow")
        hair_targets = sorted(set(hair_targets + hair_shadow_targets))
        if hair_color is not None and hair_targets:
            print("[STEP] hair_rgb 기준 머리색 로컬 재색칠 시작")
            print("[INFO] hair 대상:", hair_targets)
            for filename in hair_targets:
                img = load_current_part(original_dir, edited_parts, filename)
                recolored = recolor_preserve_shading(img, hair_color, strength=COLOR_STRENGTH)
                set_edited_part(edited_parts, recolored, filename)
        else:
            print("[SKIP] hair-color 재색칠 없음")

    if "cloth" in config.get("local_color_groups", []):
        cloth_targets = get_group_parts(config, original_dir, "cloth")
        if cloth_color is not None and cloth_targets:
            print("[STEP] cloth_rgb 기준 옷 색 로컬 재색칠 시작")
            print("[INFO] cloth 대상:", cloth_targets)
            for filename in cloth_targets:
                img = load_current_part(original_dir, edited_parts, filename)
                recolored = recolor_preserve_shading(img, cloth_color, strength=COLOR_STRENGTH)
                set_edited_part(edited_parts, recolored, filename)
        else:
            print("[SKIP] cloth-color 재색칠 없음")

    # 3 bbox 기준 전체 합성
    print("[STEP] 전체 파츠 bbox 합성 시작")
    result_path = merge_all_parts_from_bbox(
        config,
        original_dir,
        edited_parts,
        skin_color=skin_color,
        skin_filenames=skin_targets_for_merge,
    )

    print()
    print("[DONE] 모든 작업 완료")
    print(f"[RESULT] 최종 결과: {result_path}")
    print(f"[INFO] 수정 파츠 폴더는 만들지 않았습니다")
    print(f"[INFO] 원본 파츠 폴더는 보존됨: {original_dir}")


def main():
    print("model.json에서 실행할 모델 번호를 읽습니다")
    print("model.json 경로:", MODEL_JSON_PATH)
    print("colors JSON 검색 폴더:", COLORS_DOWNLOAD_DIR)
    print("prompty.py prompts.json prompts_cache_meta.json은 사용하지 않습니다")
    print("1번: parts")
    print("2번: parts_black")
    print("3번: parts_brown")
    print("4번: parts_gray")

    choice = read_model_choice_from_json(MODEL_JSON_PATH)

    print("model.json 값:", choice)
    print("실행 모델:", MODEL_CONFIGS[choice]["display_name"])

    run_model(MODEL_CONFIGS[choice])


if __name__ == "__main__":
    main()