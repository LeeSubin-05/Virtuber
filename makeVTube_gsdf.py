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
FEATURE_PATH = r"C:\DKU\동아리\SWAG\SWAG5\전공 알림제\Vtube\Virtuber\baseFeature.json"
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

    # 데이터 로드 (프롬프트와 베이스 피처 추가)
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)
    with open(FEATURE_PATH, "r", encoding="utf-8") as f: # baseFeature.json 경로
        base_features = json.load(f)

    for name, prompt in prompts_data.items():
        if not prompt: continue
        
        in_p = os.path.join(INPUT_DIR, f"{name}.png")
        out_p = os.path.join(OUTPUT_DIR, f"{name}.png")

        if os.path.exists(in_p):
            # 🌟 해당 파츠의 Role 정보 추출
            part_info = base_features.get(name, {})
            part_role = part_info.get("role", "VTube asset piece")
            
            print(f"[PROCESS] {name} ({part_role}) 변형 중...")
            
            orig_rgba = Image.open(in_p).convert("RGBA")
            alpha_mask = orig_rgba.getchannel("A")
            
            # 핑크색 잔상 제거를 위한 채도 하향 전처리
            enhancer = ImageEnhance.Color(orig_rgba.convert("RGB"))
            washed_init = enhancer.enhance(0.05) 
            canny_guide = get_canny_image(washed_init)

            # 🌟 프롬프트 구성: (Role) + (Gemini가 뽑은 태그) + (고정 키워드)
            # Role에 가중치를 주어 파츠의 정체성을 강조합니다.
            combined_prompt = f"name = {name}, (({part_role}:3.5)), {prompt}"

            # 🌟 '색상 변경'과 '형태 고정'에만 몰입하는 설정
            result = pipe(
                # 프롬프트: 'flat color'와 'solid'를 넣어 텍스처 변형 방지
                prompt=f"((pure {combined_prompt})), (flat color:1.3), (solid texture:1.2), clean lineart",
                
                # 네거티브: 불필요한 디테일과 입체감을 원천 차단
                negative_prompt="complex details, 3d, render, gradient, shadow, lighting, ornaments, face, eyes, skin",
                
                image=washed_init,
                control_image=canny_guide,
                
                # 🌟 핵심 파라미터 튜닝
                strength=0.6,                   # 형태 변형 최소화 (0.3 ~ 0.35)
                controlnet_conditioning_scale=1.6, # 외곽선을 절대적 법으로 삼음
                num_inference_steps=20,          # 스텝이 짧을수록 불필요한 잔기술을 부리지 않음
                guidance_scale=15.0              # 프롬프트(색상 명령)를 강제로 수행
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