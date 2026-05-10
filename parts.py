"""
extract_parts.py - 텍스처에서 파츠별 영역을 잘라 저장하여 추출 검증

설치:
  pip install pillow

실행:
  python extract_parts.py
"""

import os
import json
from PIL import Image, ImageDraw, ImageFont

# ── 설정 ─────────────────────────────────────────────────
TEXTURE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\akari.png"     # 원본 텍스처
OUTPUT_DIR   = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\parts"         # 잘라낸 파츠 저장 폴더

# 파츠별 영역 좌표 [x1, y1, x2, y2]
PARTS = {
    "hair_inner":                                       [724, 2014, 2268, 3012],
    "hair_outter":                                      [2450, 2200, 3962, 3418],
    "headband":                                         [2890, 80, 3888, 314],
    "face_head_base_set":                               [3016, 356, 3758, 1420],
    "face_expression_eye_set":                          [2290, 3584, 4024, 4014],
    "upper_body_outfit_set":                            [1780, 212, 2866, 1498],
    "skirt_outter":                                     [1924, 1528, 2614, 2028],
    "legs_stockings_pair":                              [1016, 16, 1678, 1532],
    "shoes_pair":                                       [1194, 1454, 1714, 1876],
    "skirt_inner":                                      [40, 1878, 790, 2426],
    "arm_hand_set":                                     [766, 3056, 1264, 4062],
    "ribbon_bow_accessory_set":                         [2770, 1468, 3528, 1790],
    #"effect_symbols_top_right":                         [3836, 324, 4038, 872],
    "cloth_collar":                                     [1882, 10, 2662, 258],
}

# 오버뷰에 사용할 색상 팔레트
COLORS = [
    "#FF3B30", "#007AFF", "#34C759", "#FFCC00", "#AF52DE", "#FF2D55",
    "#5AC8FA", "#FF9500", "#A2845E", "#00C7BE", "#FF6482", "#30B0C7",
    "#BF5AF2", "#32D74B", "#FFD60A", "#64D2FF", "#FF453A", "#5E5CE6",
]


def crop_and_save(img, parts, out_dir):
    """각 파츠를 잘라서 개별 PNG로 저장"""
    W, H = img.size
    for name, (x1, y1, x2, y2) in parts.items():
        # 좌표 클램핑 (이미지 범위 벗어남 방지)
        cx1, cy1 = max(0, min(x1, W)), max(0, min(y1, H))
        cx2, cy2 = max(0, min(x2, W)), max(0, min(y2, H))

        if cx2 <= cx1 or cy2 <= cy1:
            print(f"[SKIP] {name}: 잘못된 영역 ({x1},{y1},{x2},{y2})")
            continue

        crop = img.crop((cx1, cy1, cx2, cy2))
        out_path = os.path.join(out_dir, f"{name}.png")
        crop.save(out_path, "PNG")
        print(f"[OK]   {name:50s} {cx2-cx1:>5d} x {cy2-cy1:<5d} → {out_path}")


def make_overview(img, parts, out_path, scale=0.25):
    """원본에 모든 영역을 그려 한눈에 확인할 수 있는 오버뷰 생성"""
    overview = img.copy().convert("RGBA")
    draw = ImageDraw.Draw(overview)

    # 폰트 로드 (윈도우 기본 폰트 시도)
    font = None
    for fp in ["malgun.ttf", "arial.ttf", "C:/Windows/Fonts/malgun.ttf"]:
        try:
            font = ImageFont.truetype(fp, 36)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    for i, (name, (x1, y1, x2, y2)) in enumerate(parts.items()):
        color = COLORS[i % len(COLORS)]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=6)
        # 라벨 배경 + 텍스트
        text = f"{i+1}. {name}"
        bbox = draw.textbbox((x1 + 6, y1 + 6), text, font=font)
        draw.rectangle(bbox, fill=(0, 0, 0, 180))
        draw.text((x1 + 6, y1 + 6), text, fill=color, font=font)

    # 너무 크면 축소해서 저장 (보기 편하게)
    if scale != 1.0:
        new_size = (int(overview.width * scale), int(overview.height * scale))
        overview = overview.resize(new_size, Image.LANCZOS)

    overview.save(out_path, "PNG")
    print(f"\n[OK] 오버뷰 저장: {out_path}  ({overview.width}x{overview.height})")


def main():
    if not os.path.exists(TEXTURE_PATH):
        print(f"[ERROR] 텍스처 파일을 찾을 수 없습니다: {TEXTURE_PATH}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    img = Image.open(TEXTURE_PATH).convert("RGBA")
    print(f"[INFO] 텍스처 로드: {img.size[0]} x {img.size[1]}")
    print(f"[INFO] 출력 폴더 : {OUTPUT_DIR}\n")

    # 1) 개별 파츠 크롭 저장
    crop_and_save(img, PARTS, OUTPUT_DIR)

    # 2) 전체 영역이 표시된 오버뷰 저장
    overview_path = os.path.join(OUTPUT_DIR, "_overview.png")
    make_overview(img, PARTS, overview_path, scale=0.25)

    parts_list_path = os.path.join(OUTPUT_DIR, "parts_list.json")
    with open(parts_list_path, "w", encoding="utf-8") as f:
        # PARTS 딕셔너리의 키(keys)만 뽑아서 리스트로 변환 후 저장
        json.dump(list(PARTS.keys()), f, indent=4, ensure_ascii=False)
    print(f"[OK] 파츠 키 리스트 저장: {parts_list_path}")

    print("\n[DONE] 추출 검증용 파일 생성 완료")


if __name__ == "__main__":
    main()
