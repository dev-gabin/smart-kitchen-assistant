import time

import cv2
import numpy as np
import mediapipe as mp
import pyautogui

# 관절 각도 -> 제스처 라벨 (gesture_train.csv 의 마지막 컬럼과 대응)
GESTURE_NAMES = {
    0: 'fist', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
    6: 'six', 7: 'rock', 8: 'spiderman', 9: 'yeah', 10: 'ok',
}

# 관절 각도 계산에 쓰이는 부모/자식 관절 인덱스
_PARENT_JOINTS = [0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19]
_CHILD_JOINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
_ANGLE_FROM = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18]
_ANGLE_TO = [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19]


class GestureController:
    """MediaPipe Hands 기반 손 추적 및 제스처(KNN) 인식 클래스"""

    def __init__(self, max_num_hands: int = 1, cooldown_sec: float = 1.5,
                 gesture_data_path: str = 'data/gesture_train.csv'):
        self.cooldown_sec = cooldown_sec
        self.last_action_time = 0

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.mp_drawing = mp.solutions.drawing_utils

        self.knn = self._train_knn(gesture_data_path)

    def _train_knn(self, gesture_data_path):
        file = np.genfromtxt(gesture_data_path, delimiter=',')
        angle = file[:, :-1].astype(np.float32)
        label = file[:, -1].astype(np.float32)

        knn = cv2.ml.KNearest_create()
        knn.train(angle, cv2.ml.ROW_SAMPLE, label)
        return knn

    def _classify_gesture(self, hand_landmarks) -> str:
        """21개 손 랜드마크로부터 관절 각도를 계산해 KNN으로 제스처를 분류"""
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
        """프레임에서 손을 감지해 랜드마크를 그리고, 인식된 제스처 목록을 함께 반환"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)

        gestures = []
        if results.multi_hand_landmarks:
            h, w, _ = frame.shape
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                )

                gesture_name = self._classify_gesture(hand_landmarks)
                wrist = hand_landmarks.landmark[0]
                position = (int(wrist.x * w), int(wrist.y * h))
                gestures.append({'gesture': gesture_name, 'position': position})

                cv2.putText(
                    frame, gesture_name.upper(), (position[0], position[1] + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA
                )

        return frame, gestures
