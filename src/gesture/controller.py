import time
import cv2
import numpy as np
import mediapipe as mp
import pyautogui
from PySide6.QtCore import QObject, Signal

pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = False

GESTURE_NAMES = {
    0: 'fist', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
    6: 'six', 7: 'rock', 8: 'spiderman', 9: 'yeah', 10: 'ok',
}

_PARENT_JOINTS = [0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19]
_CHILD_JOINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
_ANGLE_FROM = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18]
_ANGLE_TO = [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19]


class GestureController(QObject):
    # 스와이프 발생 시 UI로 전달할 시그널 정의
    swipe_detected = Signal()

    def __init__(self, max_num_hands: int = 1, cooldown_sec: float = 1.0,
                 gesture_data_path: str = 'data/gesture_train.csv'):
        super().__init__()
        self.cooldown_sec = cooldown_sec
        self.last_action_time = 0

        self.prev_x = None
        self.prev_time = None

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        self.mp_drawing = mp.solutions.drawing_utils

        try:
            self.knn = self._train_knn(gesture_data_path)
        except Exception as e:
            print(f"[GestureController] 제스처 학습 데이터 로드 실패 ({gesture_data_path}): {e}")
            self.knn = None

    def _train_knn(self, gesture_data_path):
        file = np.genfromtxt(gesture_data_path, delimiter=',')
        angle = file[:, :-1].astype(np.float32)
        label = file[:, -1].astype(np.float32)

        knn = cv2.ml.KNearest_create()
        knn.train(angle, cv2.ml.ROW_SAMPLE, label)
        return knn

    def _classify_gesture(self, hand_landmarks) -> str:
        if self.knn is None:
            return '?'

        joint = np.zeros((21, 3))
        for j, lm in enumerate(hand_landmarks.landmark):
            joint[j] = [lm.x, lm.y, lm.z]

        v1 = joint[_PARENT_JOINTS, :]
        v2 = joint[_CHILD_JOINTS, :]
        v = v2 - v1
        v = v / np.linalg.norm(v, axis=1)[:, np.newaxis]

        angle = np.degrees(np.arccos(np.einsum(
            'nt,nt->n', v[_ANGLE_FROM, :], v[_ANGLE_TO, :]
        )))

        data = np.array([angle], dtype=np.float32)
        _, knn_results, _, _ = self.knn.findNearest(data, 3)
        idx = int(knn_results[0][0])
        return GESTURE_NAMES.get(idx, '?')

    def process(self, frame):
        gestures = []

        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
        except Exception as e:
            print(f"[GestureController] 손 인식 중 오류 발생: {e}")
            return frame, gestures

        if results.multi_hand_landmarks:
            h, w, _ = frame.shape
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                )

                try:
                    gesture_name = self._classify_gesture(hand_landmarks)
                except Exception as e:
                    gesture_name = '?'

                wrist = hand_landmarks.landmark[0]
                position = (int(wrist.x * w), int(wrist.y * h))
                gestures.append({'gesture': gesture_name, 'position': position})

                cv2.putText(
                    frame, gesture_name.upper(), (position[0], position[1] + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA
                )

                self._handle_snap_swipe(wrist)
        else:
            self.prev_x = None
            self.prev_time = None

        return frame, gestures

    def _handle_snap_swipe(self, wrist):
        curr_x = wrist.x
        curr_time = time.time()

        try:
            if self.prev_x is not None and self.prev_time is not None:
                dt = curr_time - self.prev_time

                if 0 < dt < 0.5:
                    speed_x = (curr_x - self.prev_x) / dt

                    if abs(speed_x) > 1 and (curr_time - self.last_action_time > self.cooldown_sec):
                        print(f"[SWIPE] Speed: {speed_x:.2f} -> 스냅 감지!")
                        
                        # UI로 축소/Alt+Tab 신호 전달
                        self.swipe_detected.emit()

                        self.last_action_time = curr_time
                        self.prev_x = None
                        self.prev_time = None
                        return

        except Exception as e:
            print(f"[GestureController] 스와이프 처리 중 오류 발생: {e}")
        finally:
            self.prev_x = curr_x
            self.prev_time = curr_time