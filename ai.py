import os
import json
import cv2
import numpy as np

# =========================================================
# 경로 설정
# =========================================================

BASE_DIR = r"C:\Users\82106\OneDrive\바탕 화면\Vtube"

USER_IMAGE_PATH = os.path.join(BASE_DIR, "user.jpg")
FACE_DIR = os.path.join(BASE_DIR, "face")
OUTPUT_JSON_PATH = os.path.join(BASE_DIR, "model.json")

MODEL_NUMBERS = [1, 2, 3, 4]
IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]


# =========================================================
# 이미지 읽기 / 저장 유틸
# =========================================================

def read_image(path):
    """
    한글 경로에서도 이미지가 잘 읽히도록
    cv2.imread 대신 np.fromfile + cv2.imdecode 사용
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    data = np.fromfile(path, dtype=np.uint8)

    if data.size == 0:
        raise ValueError(f"파일은 있지만 내용이 비어 있습니다: {path}")

    img = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(
            "이미지 파일을 읽지 못했습니다\n"
            f"경로: {path}\n"
            "확장자는 이미지처럼 보여도 실제 이미지 형식이 아니거나 파일이 손상되었을 수 있습니다\n"
            "그림판에서 열어서 다른 이름으로 저장 -> JPEG 또는 PNG로 다시 저장해보세요"
        )

    return img


def write_json_number(path, number):
    """
    한글 경로 문제 없이 json 저장
    model.json에는 숫자만 저장
    """

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(int(number), f, ensure_ascii=False)


# =========================================================
# 모델 얼굴 이미지 찾기
# =========================================================

def find_model_image(model_number):
    """
    face 폴더 안에서 1.jpg 1.png 1.webp 같은 파일을 찾음
    """

    for ext in IMAGE_EXTS:
        path = os.path.join(FACE_DIR, f"{model_number}{ext}")

        if os.path.exists(path):
            return path

    raise FileNotFoundError(
        f"{model_number}번 모델 얼굴 이미지를 찾을 수 없습니다\n"
        f"아래 중 하나로 저장되어 있어야 합니다\n"
        f"{FACE_DIR}\\{model_number}.jpg\n"
        f"{FACE_DIR}\\{model_number}.png\n"
        f"{FACE_DIR}\\{model_number}.webp"
    )


# =========================================================
# 얼굴 crop
# =========================================================

def center_square_crop(img):
    """
    얼굴 검출이 실패할 때 중앙 정사각형으로 안전하게 crop
    절대 오류를 내지 않는 fallback
    """

    h, w = img.shape[:2]

    if h <= 0 or w <= 0:
        return img

    size = min(h, w)

    x1 = max(0, (w - size) // 2)
    y1 = max(0, (h - size) // 2)
    x2 = x1 + size
    y2 = y1 + size

    return img[y1:y2, x1:x2]


def crop_face_if_possible(img):
    """
    사람 사진에서 얼굴 영역을 찾으면 얼굴 중심으로 crop
    Haar cascade가 없거나 로딩 실패하거나 얼굴 검출 실패하면 중앙 crop 사용
    어떤 경우에도 오류로 멈추지 않게 설계
    """

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        cascade_path = os.path.join(
            cv2.data.haarcascades,
            "haarcascade_frontalface_default.xml"
        )

        if not os.path.exists(cascade_path):
            print("[WARN] Haar cascade 파일 없음 -> 중앙 crop 사용")
            return center_square_crop(img)

        face_cascade = cv2.CascadeClassifier(cascade_path)

        if face_cascade.empty():
            print("[WARN] Haar cascade 로딩 실패 -> 중앙 crop 사용")
            return center_square_crop(img)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(40, 40)
        )

        if len(faces) == 0:
            print("[WARN] 얼굴 검출 실패 -> 중앙 crop 사용")
            return center_square_crop(img)

        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])

        margin = int(max(w, h) * 0.25)

        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img.shape[1], x + w + margin)
        y2 = min(img.shape[0], y + h + margin)

        return img[y1:y2, x1:x2]

    except Exception as e:
        print("[WARN] 얼굴 crop 중 오류 발생 -> 중앙 crop 사용")
        print("[WARN]", str(e))
        return center_square_crop(img)


# =========================================================
# 벡터 유틸
# =========================================================

def normalize_vector(vec):
    vec = np.asarray(vec, dtype=np.float32).flatten()

    if vec.size == 0:
        return vec

    norm = np.linalg.norm(vec)

    if norm < 1e-8:
        return vec

    return vec / norm


def cosine_similarity(a, b):
    a = normalize_vector(a)
    b = normalize_vector(b)

    if a.size == 0 or b.size == 0:
        return 0.0

    if a.shape != b.shape:
        min_len = min(a.size, b.size)
        a = a[:min_len]
        b = b[:min_len]

    return float(np.dot(a, b))


# =========================================================
# 특징 추출 1 HOG
# =========================================================

def extract_hog(img):
    """
    얼굴 윤곽과 명암 구조 비교
    """

    try:
        resized = cv2.resize(img, (128, 128))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        hog = cv2.HOGDescriptor(
            _winSize=(128, 128),
            _blockSize=(16, 16),
            _blockStride=(8, 8),
            _cellSize=(8, 8),
            _nbins=9
        )

        feature = hog.compute(gray)

        if feature is None:
            return np.zeros(8100, dtype=np.float32)

        return normalize_vector(feature)

    except Exception as e:
        print("[WARN] HOG 추출 실패:", str(e))
        return np.zeros(8100, dtype=np.float32)


# =========================================================
# 특징 추출 2 HSV 색상 히스토그램
# =========================================================

def extract_hsv_hist(img):
    """
    전체 색감 비교
    피부색 머리색 분위기 반영
    """

    try:
        resized = cv2.resize(img, (160, 160))
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        hist = cv2.calcHist(
            [hsv],
            [0, 1, 2],
            None,
            [16, 8, 8],
            [0, 180, 0, 256, 0, 256]
        )

        hist = cv2.normalize(hist, hist).flatten()

        return normalize_vector(hist)

    except Exception as e:
        print("[WARN] HSV 히스토그램 추출 실패:", str(e))
        return np.zeros(1024, dtype=np.float32)


# =========================================================
# 특징 추출 3 LBP 질감
# =========================================================

def extract_lbp_hist(img):
    """
    눈 코 입 주변의 간단한 질감 패턴 비교
    """

    try:
        resized = cv2.resize(img, (128, 128))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape

        if h < 3 or w < 3:
            return np.zeros(256, dtype=np.float32)

        lbp = np.zeros((h - 2, w - 2), dtype=np.uint8)
        center = gray[1:-1, 1:-1]

        lbp |= ((gray[:-2, :-2] >= center) << 7).astype(np.uint8)
        lbp |= ((gray[:-2, 1:-1] >= center) << 6).astype(np.uint8)
        lbp |= ((gray[:-2, 2:] >= center) << 5).astype(np.uint8)
        lbp |= ((gray[1:-1, 2:] >= center) << 4).astype(np.uint8)
        lbp |= ((gray[2:, 2:] >= center) << 3).astype(np.uint8)
        lbp |= ((gray[2:, 1:-1] >= center) << 2).astype(np.uint8)
        lbp |= ((gray[2:, :-2] >= center) << 1).astype(np.uint8)
        lbp |= ((gray[1:-1, :-2] >= center) << 0).astype(np.uint8)

        hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
        hist = hist.astype(np.float32)

        return normalize_vector(hist)

    except Exception as e:
        print("[WARN] LBP 추출 실패:", str(e))
        return np.zeros(256, dtype=np.float32)


# =========================================================
# 특징 추출 4 얼굴 색상 요약
# =========================================================

def extract_color_summary(img):
    """
    평균색 중간색 밝기 채도 등을 간단히 요약
    """

    try:
        resized = cv2.resize(img, (160, 160))
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        bgr = resized.reshape(-1, 3).astype(np.float32)
        hsv_flat = hsv.reshape(-1, 3).astype(np.float32)

        b_mean, g_mean, r_mean = np.mean(bgr, axis=0)
        b_med, g_med, r_med = np.median(bgr, axis=0)

        h_mean, s_mean, v_mean = np.mean(hsv_flat, axis=0)
        h_med, s_med, v_med = np.median(hsv_flat, axis=0)

        feature = np.array(
            [
                r_mean, g_mean, b_mean,
                r_med, g_med, b_med,
                h_mean, s_mean, v_mean,
                h_med, s_med, v_med,
            ],
            dtype=np.float32
        )

        return normalize_vector(feature)

    except Exception as e:
        print("[WARN] 색상 요약 추출 실패:", str(e))
        return np.zeros(12, dtype=np.float32)


# =========================================================
# 전체 특징 추출
# =========================================================

def extract_features(path, is_user=False):
    img = read_image(path)

    # user 사진은 얼굴 사진이므로 crop 시도
    # 모델 얼굴 이미지는 이미 얼굴만 들어있을 가능성이 높지만 중앙 crop도 안전함
    face_img = crop_face_if_possible(img)

    features = {
        "hog": extract_hog(face_img),
        "hsv": extract_hsv_hist(face_img),
        "lbp": extract_lbp_hist(face_img),
        "color": extract_color_summary(face_img),
    }

    return features


# =========================================================
# 유사도 계산
# =========================================================

def compare_features(user_features, model_features):
    hog_sim = cosine_similarity(user_features["hog"], model_features["hog"])
    hsv_sim = cosine_similarity(user_features["hsv"], model_features["hsv"])
    lbp_sim = cosine_similarity(user_features["lbp"], model_features["lbp"])
    color_sim = cosine_similarity(user_features["color"], model_features["color"])

    score = (
        0.40 * hog_sim
        + 0.25 * hsv_sim
        + 0.20 * lbp_sim
        + 0.15 * color_sim
    )

    return float(score)


# =========================================================
# 메인 실행
# =========================================================

def main():
    print("[INFO] 실행 시작")

    if not os.path.exists(USER_IMAGE_PATH):
        raise FileNotFoundError(f"user.jpg 파일이 없습니다: {USER_IMAGE_PATH}")

    if not os.path.exists(FACE_DIR):
        raise FileNotFoundError(f"face 폴더가 없습니다: {FACE_DIR}")

    print("[INFO] user.jpg 특징 추출 중")
    user_features = extract_features(USER_IMAGE_PATH, is_user=True)

    scores = {}

    for model_number in MODEL_NUMBERS:
        model_path = find_model_image(model_number)

        print(f"[INFO] {model_number}번 모델 비교 중: {model_path}")

        model_features = extract_features(model_path, is_user=False)
        score = compare_features(user_features, model_features)

        scores[model_number] = score

        print(f"  {model_number}번 점수: {score:.4f}")

    best_model = max(scores, key=scores.get)

    write_json_number(OUTPUT_JSON_PATH, best_model)

    print()
    print("[DONE] 가장 닮은 모델:", best_model)
    print("[SAVE]", OUTPUT_JSON_PATH)


if __name__ == "__main__":
    main()