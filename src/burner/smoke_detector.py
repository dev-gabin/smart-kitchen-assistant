import cv2
from PySide6.QtCore import QObject, Signal


class SmokeDetector(QObject):
    smoke_detected = Signal(float)  # 연기 감지 시작 시 confidence 전달
    smoke_cleared = Signal()        # 연기가 사라졌을 때

    def __init__(self, model_path: str = 'models/custom_smoke_best_v4.pt',
                 conf_threshold: float = 0.6):
        super().__init__()
        self.conf_threshold = conf_threshold
        self._is_smoke = False
        self.model = None

        try:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
            print(f"[SmokeDetector] 모델 로드 완료: {model_path}")
        except Exception as e:
            print(f"[SmokeDetector] 모델 로드 실패: {e}")

    def detect(self, frame):
        """
        프레임에서 연기를 감지만 하고(그리기는 draw_smoke_boxes에서 별도로 처리) 결과를 반환.
        추론이 무거워서 호출 측에서 몇 프레임에 한 번만 부르는 걸 전제로 하며,
        그리기를 분리해야 호출 측에서 감지 결과를 캐싱해 매 프레임 계속 그릴 수 있음
        (안 그러면 박스가 추론이 도는 딱 그 프레임에만 반짝이고 사라짐).

        Returns: (is_smoke: bool, max_conf: float, boxes: list[{'bbox', 'conf'}])
        """
        if self.model is None:
            return False, 0.0, []

        try:
            results = self.model(frame, verbose=False)[0]
        except Exception as e:
            print(f"[SmokeDetector] 추론 오류: {e}")
            return False, 0.0, []

        boxes = []
        max_conf = 0.0

        for box in results.boxes:
            conf = float(box.conf[0])
            if conf >= self.conf_threshold:
                max_conf = max(max_conf, conf)
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                boxes.append({'bbox': (x1, y1, x2, y2), 'conf': conf})

        detected = len(boxes) > 0

        # 상태가 바뀔 때만 시그널 발송 (매 프레임 emit 방지)
        if detected and not self._is_smoke:
            self._is_smoke = True
            self.smoke_detected.emit(max_conf)
        elif not detected and self._is_smoke:
            self._is_smoke = False
            self.smoke_cleared.emit()

        return detected, max_conf, boxes


def draw_smoke_boxes(frame, boxes, color=(0, 0, 255), thickness=2):
    """감지된 연기/화재 바운딩 박스를 프레임 위에 그려서 반환 (캐시된 결과로 매 프레임 호출 가능)"""
    for box in boxes:
        x1, y1, x2, y2 = box['bbox']
        conf = box['conf']
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            frame, f"SMOKE {conf:.0%}", (x1, max(y1 - 8, 12)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA
        )
    return frame
