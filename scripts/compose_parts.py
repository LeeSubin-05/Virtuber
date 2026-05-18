import os
import json
import sys
from PIL import Image

# scripts 폴더에서 상위 Virtuber 폴더의 config.py를 찾도록 경로를 추가
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import PARTS_BBOX_PATH, BLACKLIST_DIR, MODIFIED_PARTS_DIR, ORIGINAL_IMAGE_PATH, OUTPUT_RECOLORED_PATH
# 경로 설정
OUTPUT_PATH = OUTPUT_RECOLORED_PATH

def compose_parts():
    """parts_bbox.json의 bbox 정보를 이용해 modified_parts의 이미지들을 원래 위치에 합성"""
    
    # parts_bbox.json 로드
    with open(PARTS_BBOX_PATH, "r", encoding="utf-8") as f:
        parts_data = json.load(f)
    
    # 원본 이미지 크기 파악 (가장 큰 bbox를 통해 캔버스 크기 결정)
    max_right = max(part["bbox"][2] for part in parts_data)
    max_bottom = max(part["bbox"][3] for part in parts_data)
    
    print(f"[INFO] 캔버스 크기: {max_right} x {max_bottom}")
    
    # 투명 배경의 새로운 이미지 생성 (RGBA)
    canvas = Image.new("RGBA", (max_right, max_bottom), (0, 0, 0, 0))
    erase_regions = []
    blacklist_ids = set()
    if os.path.isdir(BLACKLIST_DIR):
        blacklist_ids = {os.path.splitext(f)[0] for f in os.listdir(BLACKLIST_DIR) if os.path.isfile(os.path.join(BLACKLIST_DIR, f)) and f.lower().endswith('.png')}
    
    processed_count = 0
    missing_count = 0
    
    for part_info in parts_data:
        part_id = part_info["id"]
        bbox = part_info["bbox"]  # [left, top, right, bottom]
        
        # modified_parts 폴더에서 해당 파츠 이미지 찾기
        part_path = os.path.join(MODIFIED_PARTS_DIR, f"{part_id}.png")
        
        if os.path.exists(part_path):
            try:
                # 파츠 이미지 로드 (RGBA 포맷)
                part_img = Image.open(part_path).convert("RGBA")
                
                # bbox 좌표로 위치 계산
                left, top, right, bottom = bbox
                
                if part_id in blacklist_ids:
                    erase_regions.append((left, top, right, bottom))
                    print(f"⚠️ {part_id}은 blacklist에 포함되어 원본 영역을 비웁니다.")
                else:
                    alpha = part_img.split()[3]
                    if alpha.getextrema() == (0, 0):
                        # 완전히 투명한 파츠는 원본 영역을 제거하도록 기록
                        erase_regions.append((left, top, right, bottom))
                        print(f"⚠️ {part_id}은 완전히 투명하여 원본 영역을 비웁니다.")
                    else:
                        # 파츠 이미지를 캔버스에 합성 (투명도 유지)
                        canvas.paste(part_img, (left, top), part_img)
                        print(f"✅ {part_id} 합성 완료")
                
                processed_count += 1
            except Exception as e:
                print(f"❌ 오류 ({part_id}): {e}")
                missing_count += 1
        else:
            print(f"⚠️  파일 없음: {part_id}.png")
            missing_count += 1
    
    # 최종 이미지 저장 (RGB로 변환하거나 RGBA 유지)
    # RGBA를 RGB로 변환하는 경우 (배경이 있으면 배경 위에 합성)
    if os.path.exists(ORIGINAL_IMAGE_PATH):
        # 원본 이미지가 있으면 그 위에 합성
        bg = Image.open(ORIGINAL_IMAGE_PATH).convert("RGBA")
        for left, top, right, bottom in erase_regions:
            clear_region = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
            mask = Image.new("L", (right - left, bottom - top), 255)
            bg.paste(clear_region, (left, top), mask)
        bg.paste(canvas, (0, 0), canvas)
        result = bg
    else:
        # 없으면 합성 결과를 RGB로 변환 (투명 배경 → 흰 배경)
        result = Image.new("RGB", canvas.size, (255, 255, 255))
        result.paste(canvas, (0, 0), canvas)
    
    result.save(OUTPUT_PATH)
    print(f"\n[FINISH] 이미지 합성 완료!")
    print(f"처리됨: {processed_count}, 누락됨: {missing_count}")
    print(f"저장 위치: {OUTPUT_PATH}")

if __name__ == "__main__":
    print("[START] 파츠 합성 시작...\n")
    compose_parts()
