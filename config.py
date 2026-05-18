import os
import sys
import subprocess
import shutil

# ─────────────────────────────────────────────────────────
# 🔧 프로젝트 경로 설정
# ─────────────────────────────────────────────────────────

# config.py 파일 기준으로 경로를 자동 계산합니다.
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = SCRIPT_DIR
PARTS_DIR = os.path.join(BASE_DIR, "parts")
SKIN_DIR = os.path.join(PARTS_DIR, "skin")
BLACKLIST_DIR = os.path.join(PARTS_DIR, "blacklist")
MODIFIED_PARTS_DIR = os.path.join(BASE_DIR, "modified_parts")
DATA_DIR = os.path.join(BASE_DIR, "data")

# requirements 파일 경로
REQUIREMENTS_PATH = os.path.join(BASE_DIR, "requirements.txt")

# JSON 파일 경로
JSON_PATH = os.path.join(DATA_DIR, "prompts.json")
FEATURE_PATH = os.path.join(DATA_DIR, "baseFeature.json")
PARTS_BBOX_PATH = os.path.join(DATA_DIR, "parts_bbox.json")

# 이미지 파일 경로
ORIGINAL_IMAGE_PATH = os.path.join(DATA_DIR, "akari.png")
OUTPUT_RECOLORED_PATH = os.path.join(BASE_DIR, "akari_recolored.png")
# texture 저장 경로
TEXTURE_OUTPUT_DIR = r"C:/Program Files (x86)/Steam/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/akari_vts/akari.4096"
TEXTURE_FILE_NAME = "texture_00.png"
TEXTURE_OUTPUT_PATH = os.path.join(TEXTURE_OUTPUT_DIR, TEXTURE_FILE_NAME)
# ─────────────────────────────────────────────────────────
#  패키지 설치 도우미
# ─────────────────────────────────────────────────────────

def install_requirements():
    """requirements.txt 파일에 명시된 패키지를 설치합니다."""
    if not os.path.exists(REQUIREMENTS_PATH):
        raise FileNotFoundError(f"requirements.txt를 찾을 수 없습니다: {REQUIREMENTS_PATH}")

    print(f"[INSTALL] {REQUIREMENTS_PATH}에 명시된 패키지를 설치합니다...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_PATH])


def ensure_dependencies():
    """requirements.txt에 명시된 패키지를 설치합니다."""
    print("[INFO] requirements.txt 기반 의존성 설치를 시작합니다...")
    install_requirements()

def save_recolored_texture(src_path: str = OUTPUT_RECOLORED_PATH, target_path: str = TEXTURE_OUTPUT_PATH):
    """akari_recolored.png를 texture_00.png로 복사해서 저장합니다. 기존 파일이 있으면 덮어씁니다."""
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"원본 리컬러 이미지가 존재하지 않습니다: {src_path}")

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    if os.path.exists(target_path):
        print(f"[INFO] 기존 텍스처 파일을 덮어씁니다: {target_path}")
        os.remove(target_path)

    shutil.copy2(src_path, target_path)
    print(f"✅ 텍스처 파일 저장 완료: {target_path}")
    return target_path
# ─────────────────────────────────────────────────────────
# �🎨 Stable Diffusion 모델 설정
# ─────────────────────────────────────────────────────────

MODEL_ID = "gsdf/Counterfeit-V2.5"
CONTROLNET_ID = "lllyasviel/sd-controlnet-canny"

# ─────────────────────────────────────────────────────────
# ✅ 경로 검증
# ─────────────────────────────────────────────────────────

def validate_paths():
    """필수 디렉토리가 존재하는지 확인"""
    required_dirs = [SCRIPT_DIR, PARTS_DIR, BASE_DIR]
    for dir_path in required_dirs:
        os.makedirs(dir_path, exist_ok=True)
    
    # modified_parts 디렉토리 생성
    os.makedirs(MODIFIED_PARTS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    return True

if __name__ == "__main__":
    print("🔧 프로젝트 경로 설정:")
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"SCRIPT_DIR: {SCRIPT_DIR}")
    print(f"PARTS_DIR: {PARTS_DIR}")
    print(f"SKIN_DIR: {SKIN_DIR}")
    print(f"MODIFIED_PARTS_DIR: {MODIFIED_PARTS_DIR}")
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"\n📄 파일 경로:")
    print(f"JSON_PATH: {JSON_PATH}")
    print(f"FEATURE_PATH: {FEATURE_PATH}")
    print(f"PARTS_BBOX_PATH: {PARTS_BBOX_PATH}")
    print(f"ORIGINAL_IMAGE_PATH: {ORIGINAL_IMAGE_PATH}")
    print(f"OUTPUT_RECOLORED_PATH: {OUTPUT_RECOLORED_PATH}")
    print("\n📦 의존성 설치를 시작합니다...")
    ensure_dependencies()
    print("\n✅ config.py 자동 설치가 완료되었습니다.")
