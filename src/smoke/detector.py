import cv2
from PySide6.QtCore import QObject, Signal


class SmokeDetector(QObject):
    smoke_detected = Signal(float)  # 연기 감지 시작 시 confidence 전달
    smoke_cleared = Signal()        # 연기가 사라졌을 때

    def __init__(self, model_path: str = 'models/custom_smoke_best.pt',
                 conf_threshold: float = 0.4):
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

    def process(self, frame):
        """
        프레임에서 연기를 감지하고 바운딩 박스를 그려 반환.
        Returns: (frame, is_smoke: bool, max_conf: float)
        """
        if self.model is None:
            return frame, False, 0.0

        try:
            results = self.model(frame, verbose=False)[0]
        except Exception as e:
            print(f"[SmokeDetector] 추론 오류: {e}")
            return frame, False, 0.0

        detected = False
        max_conf = 0.0

        for box in results.boxes:
            conf = float(box.conf[0])
            if conf >= self.conf_threshold:
                detected = True
                max_conf = max(max_conf, conf)

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(
                    frame,
                    f"SMOKE {conf:.0%}",
                    (x1, max(y1 - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA
                )

        # 상태가 바뀔 때만 시그널 발송 (매 프레임 emit 방지)
        if detected and not self._is_smoke:
            self._is_smoke = True
            self.smoke_detected.emit(max_conf)
        elif not detected and self._is_smoke:
            self._is_smoke = False
            self.smoke_cleared.emit()

        return frame, detected, max_conf
