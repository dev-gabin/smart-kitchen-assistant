import time
import cv2
import numpy as np
import mediapipe as mp
import pyautogui
from PySide6.QtCore import QObject, Signal

# 마우스 자동 제어 설정 (안전 장치 해제 및 딜레이 설정)
pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = False

# 제스처 ID와 이름 매핑 딕셔너리
GESTURE_NAMES = {
    0: 'fist', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
    6: 'ok', 7: 'rock', 8: 'spiderman', 9: 'two', 10: 'ok', 11: 'thumbsup',
}

# MediaPipe 랜드마크 연결 및 각도 계산용 인덱스 정의
_PARENT_JOINTS = [0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19]
_CHILD_JOINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
_ANGLE_FROM = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18]
_ANGLE_TO = [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19]


class GestureController(QObject):
    # PySide6 UI 메인 창과 통신하기 위한 커스텀 시그널 정의
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
        
        # ⏱️ 동작별 연타 방지 쿨다운 타이머 설정
        self.cooldown_sec = 1.0           # 기본 제스처 쿨다운
        self.time_add_cooldown_sec = 3.0  # 시간 추가 연타 방지
        self.toggle_cooldown_sec = 2.5    # 토글 동작 널뛰기 방지
        
        self.last_action_time = 0
        self.last_time_add_action = 0
        self.last_toggle_action = 0       

        # ✊ 마이다스 손 및 이동 중 오인식 방지 (제스처 유지 시간 체크용)
        self.last_seen_gesture = None
        self.gesture_hold_start = 0

        # 스냅 스와이프(위젯 모드) 감지용 변수
        self.last_swipe_time = 0
        self._swipe_history: list = []

        # 초기 작동 모드: 화구 선택 대기 상태
        self.input_mode = 'POT_SELECT'
        self.selected_pot_num = None

        ##추가 미니모드 여부 상태값(기본은 대시보드 모드인 False)
        self.is_mini_mode=False

        # MediaPipe Hands 모듈 초기화
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=0.85, #<-기존0.7 (애매한 손 인식 차단)
            min_tracking_confidence=0.85,#기존0.7(추적 안정성 강화)
        )
        self.mp_drawing = mp.solutions.drawing_utils

        # KNN 제스처 분류 모델 학습 데이터 로드
        try:
            self.knn = self._train_knn(gesture_data_path)
        except Exception as e:
            print(f"[GestureController] 제스처 학습 데이터 로드 실패 ({gesture_data_path}): {e}")
            self.knn = None

    def _train_knn(self, gesture_data_path):
        """CSV 학습 데이터를 불러와 KNN 모델을 학습시키는 함수"""
        file = np.genfromtxt(gesture_data_path, delimiter=',')
        angle = file[:, :-1].astype(np.float32)
        label = file[:, -1].astype(np.float32)

        knn = cv2.ml.KNearest_create()
        knn.train(angle, cv2.ml.ROW_SAMPLE, label)
        return knn

    def _classify_gesture(self, hand_landmarks) -> str:
        """손 랜드마크 관절 각도를 계산하여 KNN으로 제스처를 분류하는 함수"""
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
        # 🟢 네 번째 값으로 거리(dists)를 받아옴
        _, knn_results, _, dists = self.knn.findNearest(data, 3)
        # 🟢 거리가 너무 멀다는 것은 '제스처를 취한 게 아니라 그냥 손을 움직인 것'이므로 오인식으로 차단!
        # (임계값 6000.0은 테스트해보면서 조절 가능하며, 값이 낮을수록 깐깐하게 판정)
        if dists is not None and dists[0][0]>6000.0:
            return '?'
        
        idx = int(knn_results[0][0])
        return GESTURE_NAMES.get(idx, '?')

    def set_mode_pot_select(self):
        """화구 포커스를 유지한 채 대기 모드로 복귀하는 함수"""
        self.input_mode = 'POT_SELECT'
        print("[CONTROLLER] 모드 변경 ➔ [대기 모드 (화구 포커스 유지됨)]")

    def process(self, frame):
        """웹캠 프레임을 받아 손을 감지하고 제스처를 판정하여 UI로 신호를 보내는 핵심 메인 루프"""
        gestures = []
        current_frame_gestures = []
        hand_x_positions = []

        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
        except Exception as e:
            return frame, gestures

        # 🟢 [미니모드 완벽 차단] 대시보드로 돌아가는 스와이프만 허용하고, 타이머/화구 조작 등 모든 제스처는 완전 무시!
        if self.is_mini_mode:
            if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 1:
                self._handle_snap_swipe(results.multi_hand_landmarks[0])
            return frame, gestures

        

        if results.multi_hand_landmarks:
            h, w, _ = frame.shape
            
            for hand_landmarks in results.multi_hand_landmarks:
                # 손 뼈대 라인 드로잉
                self.mp_drawing.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                try:
                    gesture_name = self._classify_gesture(hand_landmarks)
                    
                    
                except Exception:
                    print(f"[GestureController] 제스처 분류 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    gesture_name = '?'
                    

                wrist = hand_landmarks.landmark[0]
                position = (int(wrist.x * w), int(wrist.y * h))
                gestures.append({'gesture': gesture_name, 'position': position})
                current_frame_gestures.append(gesture_name)
                hand_x_positions.append(wrist.x)

                # 화면에 실시간 제스처 이름 오버레이 렌더링
                cv2.putText(
                    frame, f"{gesture_name.upper()} ({self.input_mode})", (position[0], position[1] + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0) if self.input_mode=='TIME_INPUT' else (255, 255, 255), 2, cv2.LINE_AA
                )

                # 화면 왼쪽 영역(사이드바 제어 구역) 인식 처리
                if wrist.x < 0.3 and len(results.multi_hand_landmarks) == 1:
                    curr_time = time.time()
                    # 3번 메뉴(가이드 팝업 토글)는 2초의 넉넉한 쿨다운 적용
                    active_cooldown = 2.0 if gesture_name == 'three' else self.cooldown_sec
                    
                    if curr_time - self.last_action_time > active_cooldown:
                        if gesture_name in ['one', 'two', 'yeah', 'three', 'four', 'five']:
                            menu_map = {'one': 0, 'two': 1, 'yeah': 1, 'three': 2, 'four': 3, 'five': 4}
                            idx = menu_map[gesture_name]
                            self.sidebar_focus_signal.emit(idx)
                            self.last_action_time = curr_time
                        elif gesture_name == 'ok':
                            self.sidebar_select_signal.emit()
                            self.last_action_time = curr_time

            # 스냅 스와이프(위젯 모드 전환) 감지 로직
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
                
                # 양손 동시 제스처 감지 (양손 보 = 전체 일시정지 / 양손 주먹 = 전체 초기화)
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

                if not self.is_mini_mode and not combo_executed:
                    for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                        wrist = hand_landmarks.landmark[0]
                        
                        if wrist.x >= 0.3:
                            g_name = current_frame_gestures[idx]
                            
                            # ⚡ [반응성 개선된 오인식 방지] 0.18초(약 5프레임)로 반응 속도를 대폭 높여 쾌적하게 인식되도록 조정
                            if g_name != '?':
                                if g_name != self.last_seen_gesture:
                                    self.last_seen_gesture = g_name
                                    self.gesture_hold_start = curr_time
                                
                                if curr_time - self.gesture_hold_start < 1.0: #0.18에서 변경 제스쳐 오인식 방지
                                    break
                            else:
                                self.last_seen_gesture = None
                                
                                break
                            
                            # 1️⃣ 대기 모드: 화구 선택
                            if self.input_mode == 'POT_SELECT':
                                if g_name in ['one', 'two', 'three', 'four', 'yeah']:
                                    num_map = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'yeah': 2}
                                    pot_num = num_map[g_name]
                                    self.selected_pot_num = pot_num
                                    self.input_mode = 'TIME_INPUT'  
                                    self.pot_selected_signal.emit(pot_num)
                                    self.last_action_time = curr_time
                                    break

                            # 2️⃣ 시간 설정 모드: 시간 추가 및 모드 토글
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

                            # 👍 엄지 척 마스터 토글 (전체 시작/정지)
                            if g_name == 'thumbsup':
                                if curr_time - self.last_toggle_action > self.toggle_cooldown_sec:
                                    self.timer_smart_start_signal.emit()
                                    self.last_toggle_action = curr_time
                                    self.last_action_time = curr_time
                                    self.set_mode_pot_select()
                                break

                            # ✋ 개별 화구 정지/재생 토글
                            if g_name == 'five' and self.input_mode == 'POT_SELECT':
                                if curr_time - self.last_toggle_action > self.toggle_cooldown_sec:
                                    self.timer_pause_signal.emit()
                                    self.last_toggle_action = curr_time
                                    self.last_action_time = curr_time
                                break
                            
                            # ✊ 개별 화구 초기화
                            elif g_name == 'fist':
                                self.timer_reset_signal.emit()
                                self.set_mode_pot_select()
                                self.last_action_time = curr_time
                                break

        return frame, gestures

    def _handle_snap_swipe(self, hand_landmarks):
        """화면 밖으로 손을 밀어내는 스와이프 제스처(위젯 모드 전환) 감지 함수"""
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
                # if disp_x < 0 and curr_x < 0.3: return
                self.swipe_detected.emit()
                self.last_swipe_time = curr_time
                self._swipe_history.clear()
        except Exception as e:
            print(f"[GestureController] 스냅 처리 중 오류: {e}")