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
    6: 'ok', 7: 'rock', 8: 'spiderman', 9: 'two', 10: 'ok',
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
    pot_deselected_signal = Signal()  # 선택된 화구가 없어졌을 때(손이 사라짐 등) 대시보드 선택 표시 초기화
    timer_start_signal = Signal()
    timer_pause_signal = Signal()
    timer_reset_signal = Signal()

    timer_pause_all_signal = Signal()
    timer_resume_all_signal = Signal()  # 화구 미선택 상태에서 손바닥(five) = 전체 타이머 실행
    timer_reset_all_signal = Signal()
    
    sidebar_focus_signal = Signal(int)
    sidebar_select_signal = Signal()
    
    timer_add_time_signal = Signal(int)
    timer_adjust_seconds_signal = Signal(int)  # 화구 선택 상태에서 5(보)=+10초, 주먹=-10초
    timer_toggle_long_mode_signal = Signal()
    timer_confirm_signal = Signal()
    timer_smart_start_signal = Signal()
    timer_auto_start_signal = Signal()  # 시간 설정 후 손이 화면에서 사라지면 선택된 화구의 타이머를 자동으로 시작

    def __init__(self, max_num_hands: int = 2, gesture_data_path: str = 'data/gesture_train.csv'):
        super().__init__()

        self.TEST = "!"
        
        # ⏱️ 동작별 연타 방지 쿨다운 타이머 설정
        self.cooldown_sec = 1.0           # 기본 제스처 쿨다운 (콤보/스와이프 등 1~4 선택 외의 동작에 사용)
        self.pot_select_hold_sec = 1.5    # 1~4 제스처를 이만큼 유지해야 해당 화구가 선택됨
        self.time_add_cooldown_sec = 0.4  # 5(보)/주먹을 계속 유지할 때 10초씩 증감되는 반복 간격

        self.last_action_time = 0
        self.last_time_add_action = 0

        # 화구 선택(1~4) 제스처를 유지하는 동안 선택이 세션당 한 번만 발동하도록 막는 플래그
        self._select_fired_this_hold = False

        # 웹캠 화면에 선택된 화구 번호를 표시할 때, 막 선택된 직후 잠깐 강조색으로 반짝이게 하기 위한 시각
        self._select_flash_until = 0

        # 손 인식이 잠깐 끊기는 순간(트래킹 노이즈, 제스처 전환 중 모션 블러 등)에 오작동하지 않도록 debounce 처리
        # ※ 프레임 카운트 대신 "경과 시간"으로 판단해야 처리 속도(FPS)가 흔들려도 일관되게 동작함
        self._hand_lost_since = None      # 손이 마지막으로 안 보이기 시작한 시각
        self._hand_lost_handled = False   # 그 사라짐에 대해 이미 리셋 처리를 했는지 여부
        self._hand_lost_reset_sec = 0.5   # 이만큼 연속으로 손이 안 보여야 "진짜로 사라졌다"고 판단

        # ✊ 마이다스 손 및 이동 중 오인식 방지 (제스처 유지 시간 체크용)
        self.last_seen_gesture = None
        self.gesture_hold_start = 0

        # 스냅 스와이프(위젯 모드) 감지용 변수
        self.last_swipe_time = 0
        self._swipe_history: list = []
        self._swipe_window_sec = 0.25  # 실제 스냅 동작 시간에 맞춘 짧은 샘플 보관 시간 (너무 길면 정지 구간까지 섞여 속도가 희석됨)

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
            return self.TEST
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
            return self.TEST
        
        idx = int(knn_results[0][0])
        return GESTURE_NAMES.get(idx, self.TEST)

    def set_mode_pot_select(self):
        """화구 포커스를 유지한 채 대기 모드로 복귀하는 함수"""
        self.input_mode = 'POT_SELECT'

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

        # # 🟢 [미니모드 완벽 차단] 대시보드로 돌아가는 스와이프만 허용하고, 타이머/화구 조작 등 모든 제스처는 완전 무시!
        # if self.is_mini_mode:
        #     if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 1:
        #         self._handle_snap_swipe(results.multi_hand_landmarks[0])
        #     return frame, gestures

        

        if results.multi_hand_landmarks:
            self._hand_lost_since = None
            self._hand_lost_handled = False
            h, w, _ = frame.shape
            
            for hand_landmarks in results.multi_hand_landmarks:
                # 손 뼈대 라인 드로잉
                self.mp_drawing.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                try:
                    gesture_name = self._classify_gesture(hand_landmarks)
                    
                    
                except Exception as e:
                    print(f"[GestureController] 제스처 분류 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    gesture_name = self.TEST
                    

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
            # if len(results.multi_hand_landmarks) == 1:
            #     wrist_x = results.multi_hand_landmarks[0].landmark[0].x
            #     if wrist_x < 0.3:
            #         self._swipe_history.clear()
            #     else:
            #         self._handle_snap_swipe(results.multi_hand_landmarks[0])
            # else:
            #     self._swipe_history.clear()

            curr_time = time.time()

            combo_executed = False

            if not self.is_mini_mode and not combo_executed:
                for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                    wrist = hand_landmarks.landmark[0]

                    if wrist.x >= 0.3:
                        g_name = current_frame_gestures[idx]

                        # ⚡ 오인식 방지: 같은 제스처를 일정 시간 이상 유지해야 동작 인정.
                        # 1/2/3/4는 pot_select_hold_sec(1.5초), 그 외 제스처는 cooldown_sec을 기준으로 판단.
                        if g_name != self.TEST:
                            if g_name != self.last_seen_gesture:
                                self.last_seen_gesture = g_name
                                self.gesture_hold_start = curr_time
                                self._select_fired_this_hold = False  # 제스처가 바뀌면 선택 잠금 해제

                            required_hold = self.pot_select_hold_sec if g_name in ['one', 'two', 'three', 'four'] else self.cooldown_sec

                            if curr_time - self.gesture_hold_start < required_hold:
                                break
                        else:
                            self.last_seen_gesture = None
                            self._select_fired_this_hold = False
                            break

                        # 선택: 1/2/3/4를 1.5초 이상 유지하면 해당 화구를 선택 (세션당 1회만 발동)
                        if g_name in ['one', 'two', 'three', 'four']:
                            num_map = {'one': 1, 'two': 2, 'three': 3, 'four': 4}
                            pot_num = num_map[g_name]

                            if not self._select_fired_this_hold:
                                self.selected_pot_num = pot_num
                                self.input_mode = 'TIME_INPUT'
                                self.pot_selected_signal.emit(pot_num)
                                self._select_fired_this_hold = True
                                self.last_action_time = curr_time
                                self._select_flash_until = curr_time + 0.5  # 선택 직후 0.5초간 강조 플래시
                            break

                        # 화구가 선택된 상태: 5(보)를 유지하면 10초씩 증가, 주먹을 유지하면 10초씩 감소
                        # 화구가 선택 안 된 상태: 5(보) = 전체 타이머 실행, 주먹 = 전체 타이머 정지
                        elif g_name == 'five':
                            if self.selected_pot_num is not None:
                                if curr_time - self.last_time_add_action > self.time_add_cooldown_sec:
                                    self.timer_adjust_seconds_signal.emit(10)
                                    self.last_time_add_action = curr_time
                            elif curr_time - self.last_action_time > self.cooldown_sec:
                                self.timer_resume_all_signal.emit()
                                self.last_action_time = curr_time
                            break
                        elif g_name == 'fist':
                            if self.selected_pot_num is not None:
                                if curr_time - self.last_time_add_action > self.time_add_cooldown_sec:
                                    self.timer_adjust_seconds_signal.emit(-10)
                                    self.last_time_add_action = curr_time
                            elif curr_time - self.last_action_time > self.cooldown_sec:
                                self.timer_pause_all_signal.emit()
                                self.last_action_time = curr_time
                            break
        else:
            now = time.time()
            if self._hand_lost_since is None:
                self._hand_lost_since = now
            elif not self._hand_lost_handled and now - self._hand_lost_since >= self._hand_lost_reset_sec:
                # 손이 일정 시간 이상 연속으로 사라지면 시간이 설정된 선택 화구의 타이머를 자동으로 시작시키고 화구 선택 대기 상태로 복귀
                self.timer_auto_start_signal.emit()
                self.selected_pot_num = None
                self.last_seen_gesture = None
                self.gesture_hold_start = 0
                self._select_fired_this_hold = False
                self.set_mode_pot_select()
                self.pot_deselected_signal.emit()  # 대시보드의 선택 표시(테두리 강조 등)도 함께 초기화
                self._hand_lost_handled = True

        self._draw_selected_pot_badge(frame)

        return frame, gestures

    def _draw_selected_pot_badge(self, frame):
        """웹캠 화면 좌상단에 현재 선택된 화구 번호를 뱃지로 표시 (선택 직후 잠깐 강조색으로 반짝임)"""
        if self.selected_pot_num is None:
            return

        center = (60, 60)
        radius = 42

        if time.time() < self._select_flash_until:
            badge_color = (0, 215, 255)   # 선택 직후 짧게 노란색으로 강조 (BGR)
        else:
            badge_color = (83, 109, 140)  # 대시보드 테마 브라운(#8C6D53)과 맞춘 기본색 (BGR)

        cv2.circle(frame, center, radius, badge_color, -1, cv2.LINE_AA)
        cv2.circle(frame, center, radius, (255, 255, 255), 3, cv2.LINE_AA)

        text = str(self.selected_pot_num)
        (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.6, 4)
        text_pos = (center[0] - text_w // 2, center[1] + text_h // 2)
        cv2.putText(frame, text, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 4, cv2.LINE_AA)

    # def _handle_snap_swipe(self, hand_landmarks):
    #     """화면 밖으로 손을 밀어내는 스와이프 제스처(위젯 모드 전환) 감지 함수"""
    #     fingertips = [hand_landmarks.landmark[i] for i in (8, 12, 16, 20)]
    #     curr_x = sum(lm.x for lm in fingertips) / len(fingertips)
    #     curr_y = sum(lm.y for lm in fingertips) / len(fingertips)
    #     curr_time = time.time()
    #     self._swipe_history.append((curr_time, curr_x, curr_y))
    #     self._swipe_history = [(t, x, y) for t, x, y in self._swipe_history if curr_time - t <= self._swipe_window_sec]

    #     try:
    #         if curr_time - self.last_swipe_time <= self.cooldown_sec: return
    #         if len(self._swipe_history) < 2: return
    #         oldest_time, oldest_x, oldest_y = self._swipe_history[0]
    #         dt = curr_time - oldest_time
    #         if dt <= 0: return
    #         disp_x = curr_x - oldest_x
    #         disp_y = curr_y - oldest_y
    #         speed_x = disp_x / dt
    #         speed_y = disp_y / dt

    #         # 실측 [SNAP-DEBUG] 로그 기준으로 재조정
    #         is_snap = (
    #             abs(speed_x) > 0.28
    #             and abs(disp_x) > 0.06
    #             and abs(disp_y) < 0.15
    #             and abs(speed_x) > abs(speed_y) * 1.8
    #         )

    #         # 🔍 임계값에 근접했는데 통과 못 한 경우 콘솔에 실측치를 남겨서 실제 손동작에 맞게 재조정할 수 있게 함
    #         if not is_snap and abs(speed_x) > 0.2:
    #             print(f"[SNAP-DEBUG] speed_x={speed_x:.2f} disp_x={disp_x:.2f} disp_y={disp_y:.2f} speed_y={speed_y:.2f} dt={dt:.2f} samples={len(self._swipe_history)}")
    #             # TODO:: 확인 후 제거할 것
    #         if is_snap:
    #             self.swipe_detected.emit()
    #             pyautogui.hotkey('alt', 'esc')  # 손을 옆으로 휙 스냅하면 Alt+Esc 실행
    #             self.last_swipe_time = curr_time
    #             self._swipe_history.clear()
    #     except Exception as e:
    #         print(f"[GestureController] 스냅 처리 중 오류: {e}")