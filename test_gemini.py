"""
test_gemini.py - 머리 영역만 잘라서 처리 + 강제 RGBA 저장

설치:
  pip install google-genai pillow numpy

실행:
  python test_gemini.py
"""

import os
import sys
from google import genai
from google.genai import types
from PIL import Image
import io
import numpy as np

# ── 설정 ─────────────────────────────────────────────────
TEXTURE_PATH = "C:/Program Files (x86)/Steam/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/akari_vts/akari.4096/texture_00.png"
#TEST_DESC = "은발 단발머리"

# 머리 파츠 영역 (texture_00.png 기준 좌표)
HAIR_REGION = (1900, 3450, 3550, 4050)  # 눈 영역으로 변경
TEST_DESC = "파란색 눈동자"

BG_THRESHOLD = 60
# ─────────────────────────────────────────────────────────


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyDExzwr6SylgXWvumjs0jLkhrWkes1olys")
    if not api_key:
        print("❌ GEMINI_API_KEY 환경변수가 없어요")
        sys.exit(1)

    if not os.path.exists(TEXTURE_PATH):
        print(f"❌ 텍스처 파일 없음: {TEXTURE_PATH}")
        sys.exit(1)

    print(f"✅ 텍스처 로드: {TEXTURE_PATH}")
    print(f"🎨 변경: 머리 → {TEST_DESC}")

    client = genai.Client(api_key=api_key)

    # 원본 텍스처 로드
    texture = Image.open(TEXTURE_PATH).convert("RGBA")
    original_size = texture.size

    # 머리 영역만 크롭
    hair_crop = texture.crop(HAIR_REGION)
    crop_size = hair_crop.size
    print(f"  머리 영역 크롭: {crop_size}")

    # 원본 크롭의 검정 배경 위치 기억
    crop_arr = np.array(hair_crop)
    original_bg_mask = (crop_arr[:, :, :3].sum(axis=2) < 90)
    print(f"  원본 배경 픽셀: {original_bg_mask.sum():,}")

    # Gemini로 보내기 위한 RGB 변환 + 축소
    hair_rgb = hair_crop.convert("RGB")
    small = hair_rgb.resize((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # 머리만 크롭한 이미지라 프롬프트가 단순해짐
    prompt = f"""
This is a Live2D eyes texture. The image contains scattered eyes pieces on a black background.

Task: Change the eyes color and style to: {TEST_DESC}

Strict rules:
1. Keep the EXACT same layout and positions of all eyes pieces
2. Keep the pure black background (RGB 0,0,0) - do NOT change to brown/dark red/any other color
3. Keep the same 2D anime art style
4. Output 1024x1024 same composition

Only change the eyes appearance. Layout and background must remain identical.
"""

    print("⏳ Gemini 요청 중...\n")

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
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
                result_img = Image.open(io.BytesIO(part.inline_data.data))
                break

        if result_img is None:
            print("❌ Gemini 응답에 이미지 없음")
            sys.exit(1)

        # 원본 크롭 크기로 복원
        result_img = result_img.resize(crop_size, Image.LANCZOS)

        # ── 강제 RGBA 변환 + 배경 제거 ──
        print("🪄 배경 제거 중...")

        # 명시적으로 RGBA로 변환
        result_rgba = result_img.convert("RGBA")
        result_arr = np.array(result_rgba)

        # 알파 채널 명시적으로 추가/생성
        if result_arr.shape[2] == 3:
            alpha = np.full((result_arr.shape[0], result_arr.shape[1], 1), 255, dtype=np.uint8)
            result_arr = np.concatenate([result_arr, alpha], axis=2)

        # 1) 원본에서 검정 배경이었던 위치 → 투명
        result_arr[original_bg_mask, 3] = 0

        # 2) 어두운 픽셀 (검정 배경) → 투명
        result_rgb_sum = result_arr[:, :, :3].sum(axis=2)
        dark_mask = result_rgb_sum < (BG_THRESHOLD * 3)
        result_arr[dark_mask, 3] = 0

        # 3) 밝은 픽셀 (흰색 배경) → 투명
        bright_mask = (result_arr[:, :, 0] > 240) & \
                    (result_arr[:, :, 1] > 240) & \
                    (result_arr[:, :, 2] > 240)
        result_arr[bright_mask, 3] = 0

        # 새 머리 크롭 (RGBA, 투명 배경)
        new_hair = Image.fromarray(result_arr, mode="RGBA")

        # 머리만 따로 저장 (확인용)
        new_hair.save("hair_new.png", "PNG")
        print("💾 새 머리 파츠: hair_new.png")

        # ── 원본 텍스처에 새 머리 합성 ──
        print("🎨 텍스처 합성 중...")
        final_texture = texture.copy()
        final_texture.paste(new_hair, (HAIR_REGION[0], HAIR_REGION[1]), new_hair)

        # 최종 텍스처 저장 (RGBA로 명시)
        final_texture.save("texture_test_result.png", "PNG")
        print("✅ 최종 결과: texture_test_result.png")

        # 검증
        check = Image.open("texture_test_result.png")
        print(f"\n검증:")
        print(f"  모드: {check.mode}")
        print(f"  크기: {check.size}")

        if check.mode == "RGBA":
            check_arr = np.array(check)
            transparent = (check_arr[:, :, 3] == 0).sum()
            print(f"  투명 픽셀: {transparent:,}")
            print(f"  ✅ 알파 채널 존재")
        else:
            print(f"  ⚠️ RGBA 아님")

    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()