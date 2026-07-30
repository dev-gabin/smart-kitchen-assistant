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
    6: 'six', 7: 'rock', 8: 'spiderman', 9: 'two', 10: 'ok', 11: 'thumbsup',
}

_PARENT_JOINTS = [0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19]
_CHILD_JOINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
_ANGLE_FROM = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18]
_ANGLE_TO = [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19]


class GestureController(QObject):
    swipe_detected = Signal()

    pot_selected_signal = Signal(int)
    timer_start_signal = Signal()
    timer_pause_signal = Signal()
    timer_reset_signal = Signal()

    timer_pause_all_signal = Signal()
    timer_reset_all_signal = Signal()
    
    sidebar_focus_signal = Signal(int)
    sidebar_select_signal = Signal()
    
    timer_add_time_signal = Signal(int)       
    timer_toggle_long_mode_signal = Signal()  
    timer_confirm_signal = Signal()           
    timer_smart_start_signal = Signal() 

    def __init__(self, max_num_hands: int = 2, gesture_data_path: str = 'data/gesture_train.csv'):
        super().__init__()
        self.cooldown_sec = 1.0           
        self.time_add_cooldown_sec = 3.0  
        self.toggle_cooldown_sec = 2.5    
        
        self.last_action_time = 0
        self.last_time_add_action = 0
        self.last_toggle_action = 0       

        self.last_seen_gesture = None
        self.gesture_hold_start = 0

        self.last_swipe_time = 0
        self._swipe_history: list = []

        self.input_mode = 'POT_SELECT'
        self.selected_pot_num = None

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
        angle = np.degrees(np.arccos(np.einsum('nt,nt->n', v[_ANGLE_FROM, :], v[_ANGLE_TO, :])))
        data = np.array([angle], dtype=np.float32)
        _, knn_results, _, _ = self.knn.findNearest(data, 3)
        idx = int(knn_results[0][0])
        return GESTURE_NAMES.get(idx, '?')

    def set_mode_pot_select(self):
        self.input_mode = 'POT_SELECT'
        print("[CONTROLLER] 모드 변경 ➔ [대기 모드 (화구 포커스 유지됨)]")

    def process(self, frame):
        gestures = []
        current_frame_gestures = []
        hand_x_positions = []

        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
        except Exception as e:
            return frame, gestures

        if results.multi_hand_landmarks:
            h, w, _ = frame.shape
            
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                try:
                    gesture_name = self._classify_gesture(hand_landmarks)
                    
                    # 🔥 [강력한 주먹 vs 엄지척 분리기!] 좌표로 수학적 판단!
                    thumb_tip_y = hand_landmarks.landmark[4].y
                    index_mcp_y = hand_landmarks.landmark[5].y
                    
                    # 검지(8), 중지(12), 약지(16), 새끼(20)의 손끝이 두번째 마디(6,10,14,18)보다 아래(Y값이 큼)에 있는지 검사
                    tips = [8, 12, 16, 20]
                    pips = [6, 10, 14, 18]
                    is_curled = all(hand_landmarks.landmark[tip].y > hand_landmarks.landmark[pip].y for tip, pip in zip(tips, pips))
                    
                    if is_curled:
                        # 4손가락이 접혀있는데 엄지만 위로 확 솟아있으면 -> 엄지척
                        if thumb_tip_y < (index_mcp_y - 0.04):
                            gesture_name = 'thumbsup'
                        # 엄지까지 얌전히 내려와있으면 -> 무조건 주먹 (모델이 ? 띄워도 강제 주먹화)
                        else:
                            gesture_name = 'fist'
                            
                except Exception:
                    gesture_name = '?'

                wrist = hand_landmarks.landmark[0]
                position = (int(wrist.x * w), int(wrist.y * h))
                gestures.append({'gesture': gesture_name, 'position': position})
                current_frame_gestures.append(gesture_name)
                hand_x_positions.append(wrist.x)

                cv2.putText(
                    frame, f"{gesture_name.upper()} ({self.input_mode})", (position[0], position[1] + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0) if self.input_mode=='TIME_INPUT' else (255, 255, 255), 2, cv2.LINE_AA
                )

                if wrist.x < 0.3 and len(results.multi_hand_landmarks) == 1:
                    curr_time = time.time()
                    if curr_time - self.last_action_time > self.cooldown_sec:
                        if gesture_name in ['one', 'two', 'yeah', 'three', 'four', 'five']:
                            menu_map = {'one': 0, 'two': 1, 'yeah': 1, 'three': 2, 'four': 3, 'five': 4}
                            idx = menu_map[gesture_name]
                            self.sidebar_focus_signal.emit(idx)
                            self.last_action_time = curr_time
                        elif gesture_name == 'ok':
                            self.sidebar_select_signal.emit()
                            self.last_action_time = curr_time

            if len(results.multi_hand_landmarks) == 1:
                wrist_x = results.multi_hand_landmarks[0].landmark[0].x
                if wrist_x < 0.3:
                    self._swipe_history.clear()
                else:
                    self._handle_snap_swipe(results.multi_hand_landmarks[0])
            else:
                self._swipe_history.clear()

            curr_time = time.time()

            if curr_time - self.last_action_time > self.cooldown_sec:
                combo_executed = False
                if len(current_frame_gestures) == 2:
                    at_least_one_in_zone = any(x >= 0.15 for x in hand_x_positions)
                    if at_least_one_in_zone:
                        if current_frame_gestures.count('five') == 2:
                            self.timer_pause_all_signal.emit()
                            self.last_action_time = curr_time
                            combo_executed = True
                        elif current_frame_gestures.count('fist') == 2:
                            self.timer_reset_all_signal.emit()
                            self.last_action_time = curr_time
                            combo_executed = True
                            self.set_mode_pot_select()

                if not combo_executed:
                    for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                        wrist = hand_landmarks.landmark[0]
                        
                        if wrist.x >= 0.3:
                            g_name = current_frame_gestures[idx]
                            
                            # 🔥 제스처 유지(Hold) 검사 로직
                            if g_name != '?':
                                if g_name != self.last_seen_gesture:
                                    self.last_seen_gesture = g_name
                                    self.gesture_hold_start = curr_time
                                
                                # 주먹(fist) 유지시간 1.0초 -> 0.5초로 파격 단축! 
                                if g_name == 'fist':
                                    if curr_time - self.gesture_hold_start < 0.5:
                                        break
                            else:
                                self.last_seen_gesture = None
                                break
                            
                            if self.input_mode == 'POT_SELECT':
                                if g_name in ['one', 'two', 'three', 'four', 'yeah']:
                                    num_map = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'yeah': 2}
                                    pot_num = num_map[g_name]
                                    self.selected_pot_num = pot_num
                                    self.input_mode = 'TIME_INPUT'  
                                    self.pot_selected_signal.emit(pot_num)
                                    self.last_action_time = curr_time
                                    break

                            elif self.input_mode == 'TIME_INPUT':
                                if g_name in ['one', 'three', 'five']:
                                    if curr_time - self.last_time_add_action > self.time_add_cooldown_sec:
                                        min_map = {'one': 1, 'three': 3, 'five': 5}
                                        mins = min_map[g_name]
                                        self.timer_add_time_signal.emit(mins)
                                        self.last_time_add_action = curr_time
                                        self.last_action_time = curr_time
                                    break
                                elif g_name == 'rock':
                                    self.timer_toggle_long_mode_signal.emit()
                                    self.last_action_time = curr_time
                                    break
                                elif g_name == 'ok':
                                    self.timer_confirm_signal.emit()
                                    self.last_action_time = curr_time
                                    self.set_mode_pot_select()  
                                    break

                            # 마스터 토글
                            if g_name == 'thumbsup':
                                if curr_time - self.last_toggle_action > self.toggle_cooldown_sec:
                                    self.timer_smart_start_signal.emit()
                                    self.last_toggle_action = curr_time
                                    self.last_action_time = curr_time
                                    self.set_mode_pot_select()
                                break

                            # 개별 정지
                            if g_name == 'five' and self.input_mode == 'POT_SELECT':
                                if curr_time - self.last_toggle_action > self.toggle_cooldown_sec:
                                    self.timer_pause_signal.emit()
                                    self.last_toggle_action = curr_time
                                    self.last_action_time = curr_time
                                break
                            
                            # 개별 초기화 (이제 0.5초만 쥐면 바로 작동!)
                            elif g_name == 'fist':
                                self.timer_reset_signal.emit()
                                self.set_mode_pot_select()
                                self.last_action_time = curr_time
                                break

        return frame, gestures

    def _handle_snap_swipe(self, hand_landmarks):
        fingertips = [hand_landmarks.landmark[i] for i in (8, 12, 16, 20)]
        curr_x = sum(lm.x for lm in fingertips) / len(fingertips)
        curr_y = sum(lm.y for lm in fingertips) / len(fingertips)
        curr_time = time.time()
        self._swipe_history.append((curr_time, curr_x, curr_y))
        self._swipe_history = [(t, x, y) for t, x, y in self._swipe_history if curr_time - t <= 0.4]

        try:
            if curr_time - self.last_swipe_time <= self.cooldown_sec: return
            if len(self._swipe_history) < 3: return
            oldest_time, oldest_x, oldest_y = self._swipe_history[0]
            dt = curr_time - oldest_time
            if dt <= 0: return
            disp_x = curr_x - oldest_x
            disp_y = curr_y - oldest_y
            speed_x = disp_x / dt
            speed_y = disp_y / dt

            if (abs(speed_x) > 0.8 and abs(disp_x) > 0.15 and abs(disp_y) < 0.15 and abs(speed_x) > abs(speed_y) * 2.5):
                if disp_x < 0 and curr_x < 0.5: return
                self.swipe_detected.emit()
                self.last_swipe_time = curr_time
                self._swipe_history.clear()
        except Exception:
            pass