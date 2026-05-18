import os
import json
import sys

# scripts 폴더에서 상위 Virtuber 폴더의 config.py를 찾도록 경로를 추가
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import MODIFIED_PARTS_DIR
# JSON 데이터
rename_mapping = {
    "collar_left": "part_005",
    "collar_right": "part_006",
    "headband_accessory_left": "part_008",
    "headband_accessory_right": "part_009",
    "shirt_shoulder_left": "part_010",
    "shirt_shoulder_right": "part_011",
    "shirt_neck_background": "part_012",
    "headband": "part_015",
    "shirt_chest_right": "part_016",
    "shirt_chest_left": "part_017",
    "shirt_stomach_right": "part_023",
    "shirt_stomach_left": "part_024",
    "hair_extra_outter_right": "part_054",
    "hair_root_base": "part_055",
    "hair_extra_outter_left": "part_056",
    "hair_outter_left": "part_063",
    "hair_outter_right": "part_064",
    "hair_front_left": "part_068",
    "hair_front_right": "part_069",
    "hair_mid": "part_070",
    "hair_back": "part_071",
    "eye_left_1": "part_115",
    "eye_right_1": "part_116",
    "eye_left_2": "part_117",
    "eye_right_2": "part_119",
    "skirt": "part_040"
}

OUTPUT_DIR = MODIFIED_PARTS_DIR

def rename_files():
    """modified_parts 폴더의 파일명을 JSON 매핑에 따라 변경"""
    for old_name, new_name in rename_mapping.items():
        # 모든 확장자 검색
        found_files = []
        for f in os.listdir(OUTPUT_DIR):
            if f.lower().startswith(old_name.lower()):
                found_files.append(f)
        
        for old_file in found_files:
            # 확장자 추출
            _, ext = os.path.splitext(old_file)
            new_file = new_name + ext
            
            old_path = os.path.join(OUTPUT_DIR, old_file)
            new_path = os.path.join(OUTPUT_DIR, new_file)
            
            if os.path.isfile(old_path):
                try:
                    # 기존 파일이 있으면 삭제하고 rename
                    if os.path.exists(new_path):
                        os.remove(new_path)
                        print(f"🗑️  기존 파일 삭제: {new_file}")
                    os.rename(old_path, new_path)
                    print(f"✅ {old_file} → {new_file}")
                except Exception as e:
                    print(f"❌ 오류 ({old_file}): {e}")
            else:
                print(f"⚠️  파일 없음: {old_file}")

if __name__ == "__main__":
    print(f"[START] {OUTPUT_DIR} 폴더의 파일명 변경 시작...\n")
    rename_files()
    print(f"\n[FINISH] 파일명 변경이 완료되었습니다.")
