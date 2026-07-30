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
    6: 'six', 7: 'rock', 8: 'spiderman', 9: 'two', 10: 'ok',    # 2가 yeah 로 인식되므로 9는 two로 변경
}

_PARENT_JOINTS = [0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19]
_CHILD_JOINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
_ANGLE_FROM = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18]
_ANGLE_TO = [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19]


class GestureController(QObject):
    swipe_detected = Signal()

    # 타이머 제어용 시그널 정의
    pot_selected_signal = Signal(int)
    timer_start_signal = Signal()
    timer_pause_signal = Signal()
    timer_reset_signal = Signal()

    def __init__(self, max_num_hands: int = 1, cooldown_sec: float = 1.0,
                 gesture_data_path: str = 'data/gesture_train.csv'):
        super().__init__()
        self.cooldown_sec = 1.0
        self.last_action_time = 0

        # A: 스냅 전용 쿨다운 — 제스처 쿨다운과 분리
        self.last_swipe_time = 0
        # B: 최근 0.4초 (timestamp, x) 이력 버퍼
        self._swipe_history: list = []

        # 세로 이동 추적 변수
        self.prev_y = None
        self.prev_y_time = None
        self.last_vertical_time = 0

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
                curr_time = time.time()

                # 제스처 액션 처리 (쿨다운 적용)
                if curr_time - self.last_action_time > self.cooldown_sec:
                    if gesture_name in ['one', 'two', 'three', 'four', 'yeah']:
                        num_map = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'yeah': 2}
                        pot_num = num_map[gesture_name]
                        self.pot_selected_signal.emit(pot_num)
                        self.last_action_time = curr_time
                        print(f"[GESTURE] {pot_num}번 화구 선택 시그널 발송!")
                    elif gesture_name == 'ok':
                        self.timer_start_signal.emit()
                        self.last_action_time = curr_time
                        print("[GESTURE] 타이머 시작 시그널 발송!")
                    elif gesture_name == 'five':
                        self.timer_pause_signal.emit()
                        self.last_action_time = curr_time
                        print("[GESTURE] 타이머 일시정지 시그널 발송!")
                    elif gesture_name == 'fist':
                        self.timer_reset_signal.emit()
                        self.last_action_time = curr_time
                        print("[GESTURE] 타이머 초기화 시그널 발송!")

                # 손가락 끝 스냅 감지 (검지 끝 landmark[8] 기준)
                self._handle_snap_swipe(hand_landmarks)

        return frame, gestures

    def _handle_snap_swipe(self, hand_landmarks):
        # 검지(8), 중지(12), 약지(16), 소지(20) 끝의 x, y 평균
        fingertips = [hand_landmarks.landmark[i] for i in (8, 12, 16, 20)]
        curr_x = sum(lm.x for lm in fingertips) / len(fingertips)
        curr_y = sum(lm.y for lm in fingertips) / len(fingertips)
        curr_time = time.time()

        # 이력 추가 후 0.4초 밖 항목 제거 (x, y 모두 기록)
        self._swipe_history.append((curr_time, curr_x, curr_y))
        self._swipe_history = [(t, x, y) for t, x, y in self._swipe_history if curr_time - t <= 0.4]

        try:
            # A: 제스처 쿨다운과 독립된 스냅 전용 쿨다운
            if curr_time - self.last_swipe_time <= self.cooldown_sec:
                return

            if len(self._swipe_history) < 3:
                return

            oldest_time, oldest_x, oldest_y = self._swipe_history[0]
            dt = curr_time - oldest_time
            if dt <= 0:
                return

            disp_x = curr_x - oldest_x
            disp_y = curr_y - oldest_y
            speed_x = disp_x / dt
            speed_y = disp_y / dt

            # 스냅 판정 — 아래 4가지 조건 모두 충족해야 인정
            # 1) 수평 속도가 충분히 빠를 것
            # 2) 수평 이동거리가 충분할 것
            # 3) 수직 이동거리가 절대적으로 작을 것 (손 올리기 차단 핵심)
            # 4) 수평 속도가 수직 속도의 3배 이상일 것
            if (abs(speed_x) > 0.5
                    and abs(disp_x) > 0.15
                    and abs(disp_y) < 0.10
                    and abs(speed_x) > abs(speed_y) * 3.0):
                direction = "right" if disp_x > 0 else "left"
                print(f"[SWIPE] {direction} | SpeedX:{speed_x:.2f} SpeedY:{speed_y:.2f} DispX:{disp_x:.2f} DispY:{disp_y:.2f}")
                self.swipe_detected.emit()
                self.last_swipe_time = curr_time
                self._swipe_history.clear()

        except Exception as e:
            print(f"[GestureController] 스냅 처리 중 오류: {e}")
