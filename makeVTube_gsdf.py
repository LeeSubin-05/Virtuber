import os
import json
import torch
import cv2
import numpy as np
from PIL import Image
from diffusers import StableDiffusionControlNetImg2ImgPipeline, ControlNetModel, UniPCMultistepScheduler
from rembg import remove, new_session

# ── 설정 ─────────────────────────────────────────────────
INPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\parts"
OUTPUT_DIR = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\modified_parts"
JSON_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\prompts.json"

MODEL_ID = "gsdf/Counterfeit-V2.5"
CONTROLNET_ID = "lllyasviel/sd-controlnet-canny" # 외곽선 고정용 모델

def get_canny_image(image, low_threshold=100, high_threshold=200):
    """이미지에서 외곽선(Canny)을 추출합니다."""
    image = np.array(image)
    image = cv2.Canny(image, low_threshold, high_threshold)
    image = image[:, :, None]
    image = np.concatenate([image, image, image], axis=2)
    return Image.fromarray(image)

def setup_pipeline():
    print("[INFO] ControlNet 및 메인 모델 로드 중...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    controlnet = ControlNetModel.from_pretrained(CONTROLNET_ID, torch_dtype=torch.float16).to(device)
    pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
        MODEL_ID, controlnet=controlnet, torch_dtype=torch.float16, use_safetensors=True
    ).to(device)
    
    # 가속 설정
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.enable_xformers_memory_efficient_attention()
    return pipe

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rembg_session = new_session()
    pipe = setup_pipeline()

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)

    for name, prompt in prompts_data.items():
        if not prompt: continue
        
        in_p = os.path.join(INPUT_DIR, f"{name}.png")
        out_p = os.path.join(OUTPUT_DIR, f"{name}.png")

        if os.path.exists(in_p):
            print(f"[PROCESS] {name} 변형 중 (ControlNet 적용)...")
            init_image = Image.open(in_p).convert("RGB")
            grayscale_init = init_image.convert("L").convert("RGB")
            canny_image = get_canny_image(grayscale_init) # 뼈대 추출

            # 🌟 이미지 생성
            # combined_prompt에 'black outlines'를 추가하여 선명도 강화
            result = pipe(
                prompt=f"masterpiece, best quality, {prompt}, black outlines, clean lineart",
                image=init_image,
                control_image=canny_image,
                strength=0.5,           # 스타일 변경 강도
                controlnet_conditioning_scale=1.0, # 뼈대 유지 강도 (1.0이면 거의 완벽 고정)
                num_inference_steps=30,
                guidance_scale=7.5
            ).images[0]

            # 원본 크기로 복구 및 배경 제거
            orig_size = Image.open(in_p).size
            upscaled = result.resize(orig_size, Image.LANCZOS)
            final_img = upscaled#remove(upscaled, session=rembg_session, alpha_matting=True)
            final_img.save(out_p)

    print("\n[SUCCESS] ControlNet을 사용하여 모든 파츠의 뼈대를 고정하며 변형을 완료했습니다!")

if __name__ == "__main__":
    main()