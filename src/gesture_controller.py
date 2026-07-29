import os
import time
import pyautogui
from ultralytics import YOLO


class GestureController:
    """YOLO Pose 기반 관절 추적 및 OS 조작 클래스"""

    def __init__(self, pose_model_path: str = "models/yolov8n-pose.pt", cooldown_sec: float = 1.5):
        self.cooldown_sec = cooldown_sec
        self.last_action_time = 0

        # models 디렉터리가 없으면 자동 생성
        os.makedirs(os.path.dirname(pose_model_path), exist_ok=True)

        # 모델 로드 (파일이 없을 경우 Ultralytics가 자동으로 다운로드)
        print(f"[INFO] Pose 모델 로드 중: {pose_model_path}")
        self.model = YOLO(pose_model_path)

    def process(self, frame):
        # ... 제스처 처리 로직 ...
        pass