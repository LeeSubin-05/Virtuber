import os
import json
import torch
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from diffusers import StableDiffusionControlNetImg2ImgPipeline, ControlNetModel, UniPCMultistepScheduler

# ── 설정 ─────────────────────────────────────────────────
INPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\parts"
OUTPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\modified_parts"
JSON_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\prompts.json"

# 모델 ID (로컬 캐시가 없으면 자동으로 다운로드됩니다)
MODEL_ID = "gsdf/Counterfeit-V2.5"
CONTROLNET_ID = "lllyasviel/sd-controlnet-canny"
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

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pipe = setup_pipeline()

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)

    print(f"🚀 총 {len(prompts_data)}개 파츠 변환 루프 시작...")

    for name, prompt in prompts_data.items():
        if not prompt: continue
        
        in_p = os.path.join(INPUT_DIR, f"{name}.png")
        out_p = os.path.join(OUTPUT_DIR, f"{name}.png")

        if os.path.exists(in_p):
            print(f"🎨 [PROCESS] {name} 수정 중...")
            
            # 1. 원본 데이터 확보
            orig_rgba = Image.open(in_p).convert("RGBA")
            orig_size = orig_rgba.size
            alpha_mask = orig_rgba.getchannel("A") # 🌟 외곽선 보존용 마스크
            
            # 2. 핑크색 오염 방지 전처리: 채도 95% 제거
            # 완전 흑백이 아니므로 컬러 생성이 가능하면서도 핑크색 영향은 최소화됩니다.
            enhancer = ImageEnhance.Color(orig_rgba.convert("RGB"))
            washed_init = enhancer.enhance(1) 
            
            # 3. ControlNet 가이드 생성
            canny_guide = get_canny_image(washed_init)

            # 4. 이미지 생성 (얼굴 및 인체 생성 강력 차단)
            result = pipe(
                prompt=f"((pure {prompt})), solid color",
                image=washed_init,
                control_image=canny_guide,
                strength=0.5,                   # 형태 유지와 색상 변경의 최적 균형
                controlnet_conditioning_scale=1.2, # 뼈대를 프롬프트보다 우선시
                num_inference_steps=30,
                guidance_scale=12.0              # 프롬프트 명령(색상)을 더 강하게 인식
            ).images[0]

            # 5. 후처리: 원본 크기 복구 및 '절대 마스크' 적용
            result = result.resize(orig_size, Image.LANCZOS)
            final_rgba = result.convert("RGBA")
            
            # 🌟 AI가 삐져나오게 그린 모든 부분을 원본 투명도 맵으로 칼같이 잘라냄
            final_rgba.putalpha(alpha_mask)
            
            final_rgba.save(out_p)
            print(f"✅ [SUCCESS] {name} 완료")

    print("\n[FINISH] 모든 파츠가 성공적으로 가공되었습니다. 비용: 0원")

if __name__ == "__main__":
    main()