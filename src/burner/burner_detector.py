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


def detect_pans(frame, min_radius_ratio=0.03, max_radius_ratio=0.35):
    """
    탑다운 뷰에서 프라이팬/냄비 등 원형 조리도구의 가장자리를 프레임 전체에서 직접 탐지.

    기존에는 화구의 원형 테두리를 먼저 찾고 그 안에서만 팬을 찾았는데, 팬이 화구를
    완전히 덮으면(특히 검은 팬 + 검은 배경) 화구 테두리 자체가 안 보여서 아예 탐지가
    안 되는 구조적 문제가 있었음. 이제는 화구를 거치지 않고 CLAHE로 국소 명암 대비를
    끌어올린 뒤 팬 윤곽선을 바로 찾음.

    Returns: [{'center': (x, y), 'radius': r, 'contour': ndarray}, ...] (좌표는 원본 프레임 기준)
    """
    small, scale = _to_detect_scale(frame)
    sh, sw = small.shape[:2]

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # 검은 팬 위 검은 배경처럼 명암 차가 거의 없는 경계도 살리기 위한 국소 대비 강화
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)

    edges = cv2.Canny(blurred, 30, 90)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    frame_area = sh * sw
    min_area = frame_area * (min_radius_ratio ** 2) * np.pi
    max_area = frame_area * (max_radius_ratio ** 2) * np.pi

    pans = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * area / (perimeter ** 2)
        if circularity < 0.65:  # 원형에 가까운 조리도구만 통과, 각지거나 불규칙한 윤곽은 배제
            continue

        _, _, bw, bh = cv2.boundingRect(cnt)
        if bh == 0 or not (0.7 <= bw / bh <= 1.4):  # 가로세로 비율로 원형 여부 재검증 (오탐 억제)
            continue

        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        pans.append({
            'center': (int(cx / scale), int(cy / scale)),
            'radius': int(radius / scale),
            'contour': (cnt / scale).astype(np.int32),
        })

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
