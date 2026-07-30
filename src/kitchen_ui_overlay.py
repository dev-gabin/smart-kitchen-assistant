import mediapipe as mp
import sys
import cv2
import threading
import winsound
import pyautogui
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame
)
from src.gesture import GestureController
from src.gesture.youtube_control import YoutubeController
from src.smoke import SmokeDetector

class kitchen_App(QWidget):
    def __init__(self):
        super().__init__()
        
        # 기본 변수 초기화
        self.cap = None
        
        # 1) 팀원분의 GestureController 생성
        self.gesture_controller = GestureController()
        
        # 2) 스와이프 신호를 창 축소 함수와 연결
        self.gesture_controller.swipe_detected.connect(self.on_snap_swipe)

        # 2) SmokeDetector 생성 및 시그널 연결
        self.smoke_detector = SmokeDetector()
        self.smoke_detector.smoke_detected.connect(self.on_smoke_detected)
        self.smoke_detector.smoke_cleared.connect(self.on_smoke_cleared)

        # 경고음 반복 타이머 (2초 간격)
        self._alarm_timer = QTimer(self)
        self._alarm_timer.setInterval(2000)
        self._alarm_timer.timeout.connect(self._play_alarm)

        # 연기 감지는 매 5프레임마다 실행 (성능 최적화)
        self._smoke_frame_count = 0

        self.is_mini_mode = False

        # 타이머 설정 (웹캠 프레임 갱신용)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        # UI 화면 배치 초기화 (✨새로운 화이트&블랙 모던 UI 적용!)
        self.init_UI()
        
        # 앱 실행 시 웹캠 자동 시작
        self.start_webcam()

    # ==========================================
    # 🎨 1. 새로운 UI 디자인 (화이트 & 블랙)
    # ==========================================
    def init_UI(self):
        self.setWindowTitle("🍳 Smart Kitchen Assistant")
        self.resize(1100, 700) 
        
        # 전체 색상 테마 (화이트 앤 블랙 모던)
        self.setStyleSheet("""
            QWidget { 
                background-color: #FFFFFF; 
                color: #000000; 
                font-family: 'Malgun Gothic', 'Segoe UI', sans-serif; 
            }
            QLabel { font-size: 14px; font-weight: bold; }
            QPushButton { 
                background-color: #F8F9FA; 
                border: 1.5px solid #000000; 
                border-radius: 6px; 
                padding: 6px 12px; 
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #E9ECEF; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # [상단] 타이틀 바 ->self추가
        self.title_label = QLabel("🔍 Smart Kitchen Assistant")
        self.title_label.setStyleSheet("font-size: 16px; padding: 5px;")
        main_layout.addWidget(self.title_label)

        self.line1 = QFrame(); self.line1.setFrameShape(QFrame.HLine)
        self.line1.setStyleSheet("border-top: 1.5px solid #000000;")
        main_layout.addWidget(self.line1)

        # ----------------------------------------------------
        # [중단] 메인 화면 (웹캠 뷰 + 우측 냄비 타이머)
        # ----------------------------------------------------
        middle_layout = QHBoxLayout()

        # 📷 카메라 뷰 (웹캠 화면이 들어갈 자리)
        self.image_label = QLabel("카메라 연결 대기 중...")
        self.image_label.setAlignment(Qt.AlignCenter)

        self.image_label.setMinimumSize(640, 480) # 카메라가 맘대로 줄거나 커지지 않게 뼈대 고정 함수 추가
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        #카메라 무한 증식오류 Expanding-> Ignored(카메라 원래 사진크기 무시)
        self.image_label.setStyleSheet("""
            background-color: #F8F9FA; 
            border: 1.5px dashed #000000; 
            border-radius: 8px;
            color: #ADB5BD;
        """)

        # 🍲 우측 냄비 타이머 리스트
        timer_layout = QVBoxLayout()
        timer_layout.setSpacing(15)
        
        self.lbl_pot1 = QLabel("🍲 1 --:--")
        self.lbl_pot2 = QLabel("🍲 2 --:--")
        self.lbl_pot3 = QLabel("🍲 3 --:--")
        self.lbl_pot4 = QLabel("🍲 4 --:--")
        
        # (나중에 제스처로 선택 시 색상이 반전되도록 기본값 설정)
        for pot_lbl in [self.lbl_pot1, self.lbl_pot2, self.lbl_pot3, self.lbl_pot4]:
            pot_lbl.setStyleSheet("padding: 4px;")
            timer_layout.addWidget(pot_lbl)
            
        timer_layout.addStretch()

        middle_layout.addWidget(self.image_label, stretch=4) # 카메라 화면을 넓게!
        middle_layout.addSpacing(20)
        middle_layout.addLayout(timer_layout, stretch=1)
        
        main_layout.addLayout(middle_layout, stretch=1)

        line2 = QFrame(); line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("border-top: 1.5px solid #000000;")
        main_layout.addWidget(line2)

        # ----------------------------------------------------
        # [하단 1] 상태창 (Gesture, Selected, Smoke)
        # ----------------------------------------------------
        status_layout = QHBoxLayout()
        self.lbl_gesture = QLabel("Gesture: ✋ 없음")
        self.lbl_selected = QLabel("Pot: -")
        self.lbl_smoke = QLabel("Smoke: ✔️ Safe")

        for lbl in [self.lbl_gesture, self.lbl_selected, self.lbl_smoke]:
            lbl.setAlignment(Qt.AlignCenter)
            status_layout.addWidget(lbl)
            
        main_layout.addLayout(status_layout)

        line3 = QFrame(); line3.setFrameShape(QFrame.HLine)
        line3.setStyleSheet("border-top: 1.5px solid #000000;")
        main_layout.addWidget(line3)

        # ----------------------------------------------------
        # [하단 2] 컨트롤 버튼창
        # ----------------------------------------------------
        control_layout = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_reset = QPushButton("↺ Reset")
        self.btn_widget = QPushButton("📌 Widget Mode")
        
        control_layout.addWidget(self.btn_pause)
        control_layout.addWidget(self.btn_reset)
        control_layout.addWidget(self.btn_widget)
        control_layout.addStretch()
        
        self.lbl_fps = QLabel("FPS 60")
        control_layout.addWidget(self.lbl_fps)
        
        main_layout.addLayout(control_layout)
        self.setLayout(main_layout)
        # ==========================================
        # 📌 [트러블슈팅 포인트 5] 타이머 데이터 초기화 및 QTimer 설정
        # - 제어할 화구 상태와 남은 시간을 기록하는 변수들입니다.
        # - ⚠️ 주의: 반드시 self.lbl_pot1 ~ 4 가 만들어진 이후(아래쪽)에 이 코드가 와야 에러가 안 납니다!
        # ==========================================
        self.selected_pot = None           
        self.pot_times = [0, 0, 0, 0]      
        self.pot_states = ["대기", "대기", "대기", "대기"]  
        self.pot_labels = [self.lbl_pot1, self.lbl_pot2, self.lbl_pot3, self.lbl_pot4]

        # 1초(1000ms)마다 카운트다운을 수행할 메인 타이머 심장박동 시작!
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.update_countdowns)
        self.master_timer.start(1000)

        # ==========================================
        # 📌 [트러블슈팅 포인트 6] 리모컨(Gesture)과 기계(UI) 연결
        # - 제스처 코드에서 쏜 전파(Signal)를 메인 UI의 함수들과 연결하는 끈입니다.
        # ==========================================
        self.gesture_controller.pot_selected_signal.connect(self.select_pot)
        self.gesture_controller.timer_start_signal.connect(self.start_selected_timer)
        self.gesture_controller.timer_pause_signal.connect(self.pause_selected_timer)
        self.gesture_controller.timer_reset_signal.connect(self.reset_selected_timer)
    # ==========================================
    # 🎯 2. 화구 선택 시 블랙 박스로 반전! (하이라이트)
    # ==========================================
    def select_burner(self, num):
        # 1. 전부 기본 텍스트(흰 배경, 검은 글씨)로 초기화
        default_style = "color: #000000; background-color: transparent; padding: 4px;"
        self.lbl_pot1.setStyleSheet(default_style)
        self.lbl_pot2.setStyleSheet(default_style)
        self.lbl_pot3.setStyleSheet(default_style)
        self.lbl_pot4.setStyleSheet(default_style)
        
        # 2. 선택된 화구만 모던하게 블랙 박스로 반전!
        active_style = "color: #FFFFFF; background-color: #000000; border-radius: 4px; padding: 4px;"
        if num == 1: self.lbl_pot1.setStyleSheet(active_style)
        elif num == 2: self.lbl_pot2.setStyleSheet(active_style)
        elif num == 3: self.lbl_pot3.setStyleSheet(active_style)
        elif num == 4: self.lbl_pot4.setStyleSheet(active_style)

    # ==========================================
    # 🛠️ 3. 이하 웹캠 및 제스처 기능 (수정 없이 유지)
    # ==========================================
    def on_snap_swipe(self):
        # 📌 [트러블슈팅 포인트 1] 모니터 인식 위치
        # - 듀얼 모니터 환경에서 창이 현재 떠 있는 그 특정 모니터의 좌표/크기 정보를 가져옵니다.
        # - 만약 엉뚱한 모니터로 튀거나 좌표가 이상하다면 이 부분을 확인하세요!
        screen = self.screen().geometry()
        
        if not self.is_mini_mode:
            # 📌 [트러블슈팅 포인트 2] 미니모드 진입: 항상 위 속성 부여 및 테두리(제목바) 제거
            # - 창이 다른 프로그램(유튜브, VSCode 등) 뒤로 숨지 않도록 최상단 고정 속성을 줍니다.
            # - 알람 시계처럼 깔끔하게 보이도록 창 테두리(Frameless)를 없애 상단 제목바를 숨깁니다.
            self.setWindowFlags(
                Qt.Window | 
                Qt.FramelessWindowHint | 
                Qt.WindowStaysOnTopHint
            )
            
            # 🔥 [추가된 핵심] 카메라 때문에 걸어뒀던 최소 크기 제한을 일시적으로 풀어줍니다!
            self.setMinimumSize(1, 1)
            
            # 📌 [트러블슈팅 포인트 11] 지능형 타이머 (작동 중인 것만 남기기)
            # - 글씨에 "--:--" 가 있으면 타이머가 멈춘 상태이므로 숨깁니다.
            # - 숫자가 돌아가는(작동 중인) 타이머만 찾아서 남기고 개수를 셉니다.
            active_timers = 0
            pot_labels = [self.lbl_pot1, self.lbl_pot2, self.lbl_pot3, self.lbl_pot4]
            
            for pot_lbl in pot_labels:
                if "--:--" in pot_lbl.text():
                    pot_lbl.hide()
                else:
                    pot_lbl.show()
                    active_timers += 1
            
            # 📌 [트러블슈팅 포인트 12] 다이내믹 창 크기 및 위치 조정
            # - 살아남은 타이머 개수에 맞춰 창의 세로 길이를 알아서 조절합니다.
            if active_timers == 0:
                self.resize(180, 80) # 모두 멈춰있으면 기본 미니 사이즈
            else:
                self.resize(180, 40 + (active_timers * 40)) # 1개면 80, 2개면 120... 늘어남
            
            # ✨ 변경된 크기(self.height)를 기준으로 우측 하단 구석에 딱 맞게 좌표를 이동시킵니다!
            self.move(
                screen.width() + screen.x() - self.width() - 20,   # 오른쪽 벽에서 안쪽으로 20픽셀 여백
                screen.height() + screen.y() - self.height() - 20  # 아래쪽 벽에서 안쪽으로 20픽셀 여백
            )
            
            # 📌 [트러블슈팅 포인트 4] 불필요한 위젯 숨기기
            self.image_label.hide()
            self.btn_pause.hide()
            self.btn_reset.hide()
            self.btn_widget.hide()
            self.lbl_gesture.hide()
            self.lbl_selected.hide()
            self.lbl_smoke.hide()
            self.lbl_fps.hide()
            # 🔥 제목과 가로줄 숨기기
            self.title_label.hide()
            self.line1.hide()
            
            # 📌 [트러블슈팅 포인트 5] 속성 변경 후 UI 새로고침
            self.show() 
            self.is_mini_mode = True
            print(f">> [DEBUG] 미니 모드로 전환 완료 (돌아가는 타이머: {active_timers}개)")
            
        else:
            # 📌 [트러블슈팅 포인트 6] 기본모드 복귀: 항상 위 속성 해제
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            
            # 🔄 기본모드로 돌아갈 때는 최소 크기 제한도 원래대로 복구해 줍니다.
            self.setMinimumSize(0, 0)
            
            # 📌 [트러블슈팅 포인트 7] 원래 크기(1100x700) 및 화면 정중앙 좌표 재계산
            self.resize(1100, 700)
            center_x = screen.x() + (screen.width() - 1100) // 2
            center_y = screen.y() + (screen.height() - 700) // 2
            self.move(center_x, center_y)
            
            # 📌 [트러블슈팅 포인트 8] 숨겨두었던 카메라와 모든 버튼들 다시 복구하기
            self.image_label.show()
            self.btn_pause.show()
            self.btn_reset.show()
            self.btn_widget.show()
            self.lbl_gesture.show()
            self.lbl_selected.show()
            self.lbl_smoke.show()
            self.lbl_fps.show()
            self.title_label.show()
            self.line1.show()
            
            # 🔥 [추가] 미니모드에서 숨겼던 타이머 4개를 다시 전부 보이게 살려냅니다!
            self.lbl_pot1.show()
            self.lbl_pot2.show()
            self.lbl_pot3.show()
            self.lbl_pot4.show()
            
            # 📌 [트러블슈팅 포인트 9] 복귀 후 UI 새로고침
            self.show()
            self.is_mini_mode = False
            print(">> [DEBUG] 기본 모드로 복귀 완료 (중앙 정렬)")
            
        # 📌 [트러블슈팅 포인트 10] 초점(Focus) 강제 전환 제어
        pyautogui.hotkey('alt', 'esc')
    # ==========================================
    # 📌 [트러블슈팅 포인트 7] 타이머 제어 핵심 함수들
    # - 제스처 신호를 받아서 실제로 타이머를 돌리고 화면 글씨를 바꾸는 기계 역할입니다.
    # ==========================================

    def select_pot(self, pot_num):
        """손가락 1~4개 감지 시 실행: 제어할 화구 선택 및 강조"""
        if 1 <= pot_num <= 4:
            self.selected_pot = pot_num
            self.update_pot_styles()
            print(f">> [화구 선택] {pot_num}번 화구가 선택되었습니다.")

    def start_selected_timer(self):
        """엄지 척(주먹) 감지 시 실행: 선택된 화구 타이머 시작"""
        if self.selected_pot is None:
            print(">> [알림] 제어할 화구를 먼저 선택해주세요!")
            return

        idx = self.selected_pot - 1
        # 시간이 0초이면 기본 5분(300초)을 자동으로 세팅해줍니다.
        if self.pot_times[idx] == 0:
            self.pot_times[idx] = 300
            
        self.pot_states[idx] = "실행"
        print(f">> [타이머 시작] {self.selected_pot}번 화구 작동!")

    def pause_selected_timer(self):
        """손바닥 감지 시 실행: 선택된 화구 일시정지"""
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            self.pot_states[idx] = "정지"
            print(f">> [타이머 정지] {self.selected_pot}번 화구 일시정지!")

    def reset_selected_timer(self):
        """주먹 감지 시 실행: 선택된 화구 0초로 리셋"""
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            self.pot_times[idx] = 0
            self.pot_states[idx] = "대기"
            self.refresh_pot_label(idx)
            print(f">> [초기화] {self.selected_pot}번 화구 타이머 리셋!")

    def update_countdowns(self):
        """1초마다 째깍째깍 실행되며 숫자를 깎는 카운트다운 함수"""
        for i in range(4):
            if self.pot_states[i] == "실행" and self.pot_times[i] > 0:
                self.pot_times[i] -= 1
                self.refresh_pot_label(i)
                
                # 0초가 땡! 하고 끝났을 때 알람 발생
                if self.pot_times[i] == 0:
                    self.pot_states[i] = "대기"
                    self.refresh_pot_label(i)
                    print(f"🔔 [알람] {i+1}번 화구 조리가 완료되었습니다! 삐비빅!!")

    def refresh_pot_label(self, idx):
        """글씨를 분:초(MM:SS) 예쁜 모양으로 바꿔서 화면에 표시"""
        pot_num = idx + 1
        t = self.pot_times[idx]
        
        if t > 0:
            minutes = t // 60
            seconds = t % 60
            time_str = f"{minutes:02d}:{seconds:02d}"
            self.pot_labels[idx].setText(f"🍲 {pot_num} {time_str}")
        else:
            self.pot_labels[idx].setText(f"🍲 {pot_num} --:--")

    def update_pot_styles(self):
        """선택된 화구만 까만색으로 눈에 띄게 강조해주는 함수"""
        for i, lbl in enumerate(self.pot_labels):
            if (i + 1) == self.selected_pot:
                # 선택된 화구: 까만 바탕에 하얀 글씨, 굵게!
                lbl.setStyleSheet("background-color: #000000; color: #FFFFFF; padding: 4px; border-radius: 4px; font-weight: bold;")
            else:
                # 안 선택된 화구: 원래대로 투명하게
                lbl.setStyleSheet("background-color: transparent; color: #000000; padding: 4px;")
        
    # ==========================================
    # 연기 감지 핸들러
    # ==========================================
    def on_smoke_detected(self, conf: float):
        print(f"[SMOKE] 연기 감지! 신뢰도: {conf:.0%}")
        self._play_alarm()
        self._alarm_timer.start()

    def on_smoke_cleared(self):
        print("[SMOKE] 연기 사라짐 — 경고 해제")
        self._alarm_timer.stop()

    def _play_alarm(self):
        """별도 스레드에서 경고음 재생 (UI 블로킹 방지)"""
        def _beep():
            for _ in range(3):
                winsound.Beep(1000, 300)
        threading.Thread(target=_beep, daemon=True).start()

    def start_webcam(self):
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        if not self.timer.isActive():
            self.timer.start(30)

    def pause_webcam(self):
        if self.timer.isActive():
            self.timer.stop()

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                if getattr(self, 'gesture_controller', None) is not None:
                    try:
                        frame, gestures = self.gesture_controller.process(frame)
                        
                        # 제스처가 감지되었을 때 UI 업데이트 (새로운 라벨 변수명 적용)
                        if gestures:
                            gesture_name = gestures[0]["gesture"]
                            self.lbl_gesture.setText(f"Gesture: 👍 {gesture_name}")

                            if gesture_name == "one":
                                self.lbl_selected.setText("Pot: ♨️ 1")
                                self.select_burner(1)
                            elif gesture_name == "two":
                                self.lbl_selected.setText("Pot: ♨️ 2")
                                self.select_burner(2)
                            elif gesture_name == "three":
                                self.lbl_selected.setText("Pot: ♨️ 3")
                                self.select_burner(3)
                            elif gesture_name == "four":
                                self.lbl_selected.setText("Pot: ♨️ 4")
                                self.select_burner(4)
                    except Exception as e:
                        print(f"[kitchen_App] 제스처 처리 중 오류 발생: {e}")

                # 연기 감지 (매 5프레임마다 추론)
                self._smoke_frame_count += 1
                if self._smoke_frame_count % 5 == 0:
                    frame, is_smoke, conf = self.smoke_detector.process(frame)
                    if is_smoke:
                        self.lbl_smoke.setText(f"Smoke: ⚠️ DETECTED ({conf:.0%})")
                        self.lbl_smoke.setStyleSheet(
                            "color: #FFFFFF; background-color: #CC0000; "
                            "font-weight: bold; padding: 4px; border-radius: 4px;"
                        )
                    else:
                        self.lbl_smoke.setText("Smoke: ✔️ Safe")
                        self.lbl_smoke.setStyleSheet("")

                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

                pixmap = QPixmap.fromImage(qt_image)
                scaled_pixmap = pixmap.scaled(
                    self.image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)

    def closeEvent(self, event):
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, '_alarm_timer'):
            self._alarm_timer.stop()
        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = kitchen_App()
    window.show()
    sys.exit(app.exec())