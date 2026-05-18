import os
import json
import torch
import cv2
import numpy as np
import sys
from PIL import Image, ImageEnhance
from diffusers import StableDiffusionControlNetImg2ImgPipeline, ControlNetModel, UniPCMultistepScheduler
# scripts 폴더에서 상위 Virtuber 폴더의 config.py를 찾도록 경로를 추가
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import PARTS_DIR, SKIN_DIR, BLACKLIST_DIR, MODIFIED_PARTS_DIR, JSON_PATH, FEATURE_PATH, MODEL_ID, CONTROLNET_ID

# ── 설정 ─────────────────────────────────────────────────
INPUT_DIR = PARTS_DIR
INPUT_SKIN_DIR = SKIN_DIR
OUTPUT_DIR = MODIFIED_PARTS_DIR
# ─────────────────────────────────────────────────────────

def get_canny_image(image, low_threshold=100, high_threshold=200):
    """ControlNet용 외곽선 가이드 생성"""
    image_np = np.array(image)
    canny = cv2.Canny(image_np, low_threshold, high_threshold)
    canny = canny[:, :, None]
    canny = np.concatenate([canny, canny, canny], axis=2)
    return Image.fromarray(canny)

def setup_pipeline():
    print("[INFO] 로컬 GPU를 사용하여 SD 파이프라인을 준비합니다...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    controlnet = ControlNetModel.from_pretrained(CONTROLNET_ID, torch_dtype=torch.float16).to(device)
    pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
        MODEL_ID, controlnet=controlnet, torch_dtype=torch.float16, use_safetensors=True
    ).to(device)
    
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
    # RTX 3060 이상 권장: 메모리 효율화
    if device == "cuda":
        pipe.enable_xformers_memory_efficient_attention()
    return pipe

def hex_to_rgb(hex_str: str):
    """Hex Code (#RRGGBB 또는 RRGGBB)를 (R, G, B) 튜플로 변환하는 유틸리티"""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        raise ValueError("정확한 6자리 Hex Code를 입력해주세요. (예: #FF0000 또는 FF0000)")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def load_blacklist_files():
    if not os.path.isdir(BLACKLIST_DIR):
        return set()
    return {f.lower() for f in os.listdir(BLACKLIST_DIR) if os.path.isfile(os.path.join(BLACKLIST_DIR, f)) and f.lower().endswith('.png')}


def recolor_image_with_hex(img_pil: Image.Image, hex_code: str, strength: float = 0.95) -> Image.Image:
    """
    제공된 vtuber.py의 'recolor_preserve_shading' 논리를 그대로 구현한 함수.
    원본의 명암(Shading)과 투명도(Alpha)를 유지하면서 지정한 Hex 색상으로 재색칠합니다.
    
    :param img_pil: PIL.Image 객체 (RGBA 포맷 권장)
    :param hex_code: 변환하고자 하는 색상의 Hex Code (예: '#372619')
    :param strength: 색상 적용 강도 (0.0이면 원본 그대로, 1.0이면 타겟 색상 100% 반영)
    :return: 색상이 변경된 새로운 PIL.Image 객체
    """
    # 1. Hex Code를 RGB 숫자로 변환
    target_rgb = hex_to_rgb(hex_code)
    
    # 2. 이미지를 RGBA 넘파이 float32 배열로 변환 (정밀한 수학 연산을 위함)
    arr = np.array(img_pil.convert("RGBA")).astype(np.float32)
    
    rgb = arr[:, :, :3]          # R, G, B 채널 분리
    alpha = arr[:, :, 3:4] / 255.0  # 알파(투명도) 채널 분리 및 0~1 규격화
    
    # 3. [핵심 논리] ITU-R BT.601 가중치를 이용해 각 픽셀의 휘도(Luminance, 밝기) 계산
    #    이를 통해 이미지의 선, 주름, 하이라이트, 그림자 정보를 추출합니다.
    lum = (
        0.299 * rgb[:, :, 0]
        + 0.587 * rgb[:, :, 1]
        + 0.114 * rgb[:, :, 2]
    ) / 255.0
    lum = np.expand_dims(lum, axis=2) # 연산을 위해 차원 확장 (H, W, 1)
    
    # 4. 타겟 RGB 값을 0~1 범위로 규격화
    target = np.array(target_rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0
    
    # 5. [핵심 논리] 밝기에 따른 명암 효과(Shade) 계산 및 적용
    #    0.25는 최소 어두움 보정치, 0.95는 명암의 대비 비율입니다.
    shade = 0.25 + 0.95 * lum
    recolored = target * shade   # 사용자가 원하는 색상에 음영 레이어를 곱함
    
    # 6. 원래 이미지와 재색칠된 이미지를 설정한 강도(strength) 비율로 블렌딩
    original_norm = rgb / 255.0
    mixed = (1.0 - strength) * original_norm + strength * recolored
    
    # 7. 다시 0~255 범위의 8비트 정수형 데이터로 복원 및 알파 채널 결합
    out = np.zeros_like(arr)
    out[:, :, :3] = np.clip(mixed * 255.0, 0, 255) # 0~255 범위를 벗어나는 값 잘라내기
    out[:, :, 3:4] = alpha * 255.0                 # 원본 투명도 그대로 유지
    
    # 8. 최종 PIL 이미지로 변환하여 반환
    return Image.fromarray(out.astype(np.uint8), "RGBA")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pipe = setup_pipeline()

    # 데이터 로드 (프롬프트와 베이스 피처 추가)
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)
    with open(FEATURE_PATH, "r", encoding="utf-8") as f: # baseFeature.json 경로
        base_features = json.load(f)

    for name, prompt in prompts_data.items():
        
        if not prompt:
            continue
        if name == "eye_left" or name == "eye_right":
            print(f"[PROCESS] {name} 폴더의 모든 눈동자 이미지 색상 변경 중... {prompt}")
            eye_files = sorted(
                f for f in os.listdir(INPUT_DIR)
                if os.path.isfile(os.path.join(INPUT_DIR, f)) and f.lower().startswith(name) and f.lower().endswith(".png")
            )
            if not eye_files:
                print(f"[ERROR] {name} 폴더에 처리할 PNG 이미지가 없습니다: {INPUT_DIR}")
            for eye_file in eye_files:
                in_p = os.path.join(INPUT_DIR, eye_file)
                out_p = os.path.join(OUTPUT_DIR, eye_file)
                orig_rgba = Image.open(in_p).convert("RGBA")
                alpha = orig_rgba.getchannel("A")
                washed_rgb = ImageEnhance.Color(orig_rgba.convert("RGB")).enhance(0.05)
                washed = washed_rgb.convert("RGBA")
                washed.putalpha(alpha)
                recolored = recolor_image_with_hex(washed, prompt, strength=0.70)
                recolored.save(out_p)
                print(f"✅ {eye_file} 저장 완료")
            continue
        if name == "skin":
            print(f"[PROCESS] skin 폴더의 모든 피부 이미지 색상 변경 중... {prompt}")
            skin_files = sorted(
                f for f in os.listdir(INPUT_SKIN_DIR)
                if os.path.isfile(os.path.join(INPUT_SKIN_DIR, f)) and f.lower().endswith(".png")
            )
            if not skin_files:
                print(f"[ERROR] skin 폴더에 처리할 PNG 이미지가 없습니다: {INPUT_SKIN_DIR}")
            blacklist = load_blacklist_files()
            for skin_file in skin_files:
                in_p = os.path.join(INPUT_SKIN_DIR, skin_file)
                out_p = os.path.join(OUTPUT_DIR, skin_file)
                orig_rgba = Image.open(in_p).convert("RGBA")
                alpha = orig_rgba.getchannel("A")
                washed_rgb = ImageEnhance.Color(orig_rgba.convert("RGB")).enhance(0.05)
                washed = washed_rgb.convert("RGBA")
                washed.putalpha(alpha)
                recolored = recolor_image_with_hex(washed, prompt, strength=0.70)
                recolored.save(out_p)
                print(f"✅ {skin_file} 저장 완료")
            for black in blacklist:
                black_path = os.path.join(BLACKLIST_DIR, black)
                if os.path.exists(black_path):
                    out_p = os.path.join(OUTPUT_DIR, black)
                    orig_rgba = Image.open(black_path).convert("RGBA")
                    alpha = orig_rgba.getchannel("A")
                    transparent = Image.new("RGBA", orig_rgba.size, (0, 0, 0, 0))
                    transparent.putalpha(alpha)
                    transparent.save(out_p)
                    print(f"✅ {black} 저장 완료 (블랙리스트 투명 처리)")
                else:
                    print(f"[WARNING] 블랙리스트에 있는 파일이 존재하지 않습니다: {black_path}")
            continue
        in_p = os.path.join(INPUT_DIR, f"{name}.png")
        out_p = os.path.join(OUTPUT_DIR, f"{name}.png")

        if os.path.exists(in_p):
            # 🌟 해당 파츠의 Role 정보 추출
            part_info = base_features.get(name, {})
            part_role = part_info.get("role", "VTube asset piece")
            
            print(f"[PROCESS] {name} ({part_role}) 변형 중... {prompt}")
            
            orig_rgba = Image.open(in_p).convert("RGBA")
            alpha_mask = orig_rgba.getchannel("A")
            
            # 핑크색 잔상 제거를 위한 채도 하향 전처리
            enhancer = ImageEnhance.Color(orig_rgba.convert("RGB"))
            washed_init = enhancer.enhance(0.05) 
            canny_guide = get_canny_image(washed_init)
            strengthVal = 0.99
            if(name == "face_shape" or name == "body_neck_shoulder_base"):
                strengthVal = 0.85

            # 🌟 프롬프트 구성: (Role) + (Gemini가 뽑은 태그) + (고정 키워드)
            # Role에 가중치를 주어 파츠의 정체성을 강조합니다.
            combined_prompt = f"you are expert in painting color. just fill all the area with {prompt} color monochromatic. do not change the shape"
            combined_prompt +=", (flat color:1.3), (solid texture:1.2), clean lineart"
            negative_prompt = "complex details, 3d, render, gradient, shadow, lighting, ornaments, face, eyes, skin, completed character, created by, signature, watermark, text, logo"

            if "white" not in prompt:
                negative_prompt += ", white color. white"

            # 🌟 '색상 변경'과 '형태 고정'에만 몰입하는 설정
            result = pipe(
                # 프롬프트: 'flat color'와 'solid'를 넣어 텍스처 변형 방지
                prompt=combined_prompt,               

                # 네거티브: 불필요한 디테일과 입체감을 원천 차단
                negative_prompt=negative_prompt,               

                image=washed_init,
                control_image=canny_guide,               

                # 🌟 핵심 파라미터 튜닝
                strength=strengthVal,                   # 형태 변형 최소화 (0.3 ~ 0.35)
                controlnet_conditioning_scale=2.2, # 외곽선을 절대적 법으로 삼음
                num_inference_steps=33,          
                guidance_scale=18.0              # 프롬프트(색상 명령)를 강제로 수행
            ).images[0]
            # 후처리: 마스크 복구
            result = result.resize(orig_rgba.size, Image.LANCZOS)
            final_rgba = result.convert("RGBA")
            final_rgba.putalpha(alpha_mask)
            
            final_rgba.save(out_p)
            print(f"✅ {name} 저장 완료")

    print("\n[FINISH] 모든 파츠가 성공적으로 가공되었습니다. 비용: 0원")

if __name__ == "__main__":
    main()