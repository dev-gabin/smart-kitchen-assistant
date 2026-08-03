import cv2
import numpy as np

# 원본 해상도가 아무리 커도 감지 연산 비용을 일정하게 유지하기 위해 이 폭으로 축소해서 처리
_DETECT_WIDTH = 480


def _to_detect_scale(frame):
    """프레임을 감지용 저해상도로 축소하고, 원본 좌표로 되돌리기 위한 배율을 함께 반환"""
    h, w = frame.shape[:2]
    if w <= _DETECT_WIDTH:
        return frame, 1.0
    scale = _DETECT_WIDTH / w
    small = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return small, scale


def _circle_contour(cx, cy, r, n=60):
    angles = np.linspace(0, 2 * np.pi, n)
    pts = np.array([[cx + r * np.cos(a), cy + r * np.sin(a)] for a in angles], dtype=np.float32)
    return pts.reshape((-1, 1, 2))


def _boundary_texture_std(gray, cx, cy, r):
    """
    원 경계 바로 안쪽 얇은 고리 영역의 밝기 표준편차.
    실제 냄비/팬은 손잡이·테두리 반사·그림자 때문에 경계 부근 밝기 편차가 크지만,
    인덕션 위에 인쇄된 화구 표시 같은 납작한 원형 무늬는 편차가 거의 없어서
    이 값으로 "입체감 있는 실제 물체"와 "평면 무늬"를 구분할 수 있음.
    """
    h, w = gray.shape[:2]
    outer = min(int(r) + 3, min(h, w) // 2 - 1)
    inner = max(int(r) - 3, 1)
    if outer <= inner:
        return 0.0
    mask = np.zeros((h, w), np.uint8)
    cv2.circle(mask, (int(cx), int(cy)), outer, 255, -1)
    cv2.circle(mask, (int(cx), int(cy)), inner, 0, -1)
    vals = gray[mask == 255]
    return float(vals.std()) if vals.size else 0.0


def detect_pans(frame, min_radius_ratio=0.16, max_radius_ratio=0.34, texture_std_thresh=15.0):
    """
    탑다운 뷰에서 프라이팬/냄비 등 원형 조리도구의 가장자리를 프레임 전체에서 직접 탐지.

    이전 버전은 Canny + findContours만으로 원형 윤곽선을 찾았는데, 반사가 심한 금속
    냄비/뚜껑은 표면 반사 때문에 테두리가 여러 조각으로 끊기고 손잡이가 둘레 모양을
    망가뜨려서(원형도가 낮아짐) 큰 냄비류가 거의 탐지되지 않는 문제가 있었음.
    HoughCircles는 원 둘레의 일부만 남아 있어도 투표 방식으로 원을 찾아내기 때문에
    이런 반사/손잡이에 훨씬 강건해서 1차 탐지 방식으로 사용.

    다만 HoughCircles는 인덕션에 인쇄된 화구 표시 같은 "평면에 그려진 원"도 똑같이
    원으로 잡아내므로, 경계 부근의 밝기 편차(_boundary_texture_std)로 입체감 있는
    실제 물체만 남기는 필터를 추가로 적용함.

    Returns: [{'center': (x, y), 'radius': r, 'contour': ndarray}, ...] (좌표는 원본 프레임 기준)
    """
    small, scale = _to_detect_scale(frame)
    sh, sw = small.shape[:2]
    min_dim = min(sh, sw)

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # 검은 팬 위 검은 배경처럼 명암 차가 거의 없는 경계도 살리기 위한 국소 대비 강화
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (7, 7), 1.5)

    min_r = max(int(min_dim * min_radius_ratio), 10)
    max_r = int(min_dim * max_radius_ratio)

    pans = []
    seen = []  # (cx, cy, r) — 중복 후보 제거용

    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.5, minDist=int(min_dim * 0.35),
        param1=70, param2=45, minRadius=min_r, maxRadius=max_r
    )
    if circles is not None:
        for cx, cy, r in circles[0, :]:
            if _boundary_texture_std(gray, cx, cy, r) < texture_std_thresh:
                continue  # 평면 무늬(인쇄된 화구 표시 등)로 판단해서 제외
            pans.append({
                'center': (int(cx / scale), int(cy / scale)),
                'radius': int(r / scale),
                'contour': (_circle_contour(cx, cy, r) / scale).astype(np.int32),
            })
            seen.append((cx, cy, r))

    # HoughCircles가 놓칠 수 있는 팬을 보완하기 위한 컨투어 기반 보조 탐지
    edges = cv2.Canny(blurred, 30, 90)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    min_area = np.pi * (min_r ** 2)
    max_area = np.pi * (max_r ** 2)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        if r <= 0:
            continue

        # 손잡이 같은 작은 돌출부에 흔들리지 않도록, 둘레 기반 원형도 대신
        # "외접원 대비 실제 면적 비율(roundness)"로 원형 여부를 판단
        roundness = area / (np.pi * r ** 2)
        if roundness < 0.55:
            continue

        if any(((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5 < max(r, sr) * 0.5 for sx, sy, sr in seen):
            continue  # 이미 Hough로 잡은 것과 같은 물체

        if _boundary_texture_std(gray, cx, cy, r) < texture_std_thresh:
            continue

        pans.append({
            'center': (int(cx / scale), int(cy / scale)),
            'radius': int(r / scale),
            'contour': (cnt / scale).astype(np.int32),
        })
        seen.append((cx, cy, r))

    return pans


class PanTracker:
    """
    한 프레임짜리 오탐(반사광, 무늬 등으로 인한 원형 노이즈)에 흔들리지 않도록,
    최근 몇 번의 감지 중 일정 횟수 이상 같은 위치에서 잡힌 윤곽선만
    "확정된 팬"으로 인정해서 반환하는 아주 가벼운 시간적 필터.
    """

    def __init__(self, confirm_count=2, history=3, match_dist_ratio=0.6):
        self.confirm_count = confirm_count
        self.history = history
        self.match_dist_ratio = match_dist_ratio
        self._recent = []

    def update(self, pans):
        self._recent.append(pans)
        if len(self._recent) > self.history:
            self._recent.pop(0)

        confirmed = []
        for pan in pans:
            cx, cy = pan['center']
            r = max(pan['radius'], 1)
            hits = 0
            for past in self._recent:
                for p in past:
                    px, py = p['center']
                    if ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 < r * self.match_dist_ratio:
                        hits += 1
                        break
            if hits >= self.confirm_count:
                confirmed.append(pan)
        return confirmed


def draw_pans(frame, pans, color=(0, 0, 255), thickness=2):
    """감지된 프라이팬/조리도구의 가장자리를 프레임 위에 붉은색으로 그려서 반환"""
    for pan in pans:
        cv2.drawContours(frame, [pan['contour']], -1, color, thickness)
    return frame
