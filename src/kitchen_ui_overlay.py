import mediapipe as mp
import sys
import cv2
import pyautogui
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QSizePolicy
)
from src.gesture import GestureController


class kitchen_App(QWidget):
    def __init__(self):
        super().__init__()
        
        # 기본 변수 초기화
        self.cap = None
        
        # 1) 팀원분의 GestureController 생성
        self.gesture_controller = GestureController()
        
        # 2) 팀원분 코드의 스와이프 신호(swipe_detected)를 내 창 축소 함수(on_snap_swipe)와 연결!
        self.gesture_controller.swipe_detected.connect(self.on_snap_swipe)
        
        self.is_mini_mode = False

        # 타이머 설정 (웹캠 프레임 갱신용)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        # UI 화면 배치 초기화 (새로운 다크모드 적용!)
        self.init_UI()
        
        # 앱 실행 시 웹캠 자동 시작
        self.start_webcam()


    # ==========================================
    # 🎨 1. 새로운 UI 디자인 (init_UI)
    # ==========================================
    def init_UI(self):
        self.setWindowTitle("🍳 Smart Kitchen Assistant")
        self.resize(1100, 700) # 예쁜 비율로 살짝 키웠습니다.
        self.setStyleSheet("background-color: #181824; font-family: 'Segoe UI';")

        main_layout = QVBoxLayout()

        # ---------------------------
        # [상단] 카메라 & 상태창 영역
        # ---------------------------
        top_layout = QHBoxLayout()
        
        # 카메라 영역
        self.image_label = QLabel("📷 카메라 연결 대기 중...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: white; border-radius: 15px;")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 우측 상태창 (제스처, 선택된 화구, 연기 감지)
        status_layout = QVBoxLayout()
        self.label_gesture = QLabel("👍 제스처 : 없음")
        self.label_selected = QLabel("🔥 선택 : -")
        self.label_smoke = QLabel("🟢 SAFE")
        
        for label in [self.label_gesture, self.label_selected, self.label_smoke]:
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumHeight(60)
            label.setStyleSheet("""
                background-color: #2b2b3c;
                color: white;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            """)
            status_layout.addWidget(label)
        status_layout.addStretch()

        top_layout.addWidget(self.image_label, stretch=3)
        top_layout.addLayout(status_layout, stretch=1)

        # ---------------------------
        # [하단] 화구 카드 영역 (4개)
        # ---------------------------
        cards_layout = QHBoxLayout()
        self.timer_cards = [] # 선택 시 테두리 색을 바꾸기 위해 카드를 리스트에 저장
        
        # 반복문으로 화구 카드 4개를 뚝딱 생성!
        for i in range(1, 5):
            card = self.create_burner_card(f"{i}번 화구")
            self.timer_cards.append(card)
            cards_layout.addWidget(card)

        main_layout.addLayout(top_layout, stretch=2)
        main_layout.addLayout(cards_layout, stretch=1)
        self.setLayout(main_layout)

    # ==========================================
    # 🛠️ 2. 화구 카드 찍어내는 함수
    # ==========================================
    def create_burner_card(self, burner_title):
        card_layout = QVBoxLayout()
        
        # ------------------------------------------------
        # 🍳 1. 가출한 냄비 아이콘 찾아오기 & 크기 키우기
        # ------------------------------------------------
        icon_label = QLabel()
        
        # 🚨 주의: 파일 이름이 "cooking.png"가 맞는지 꼭 확인해 주세요! (images 폴더 안)
        # 만약 다른 이름(예: cooking2.png)으로 저장하셨다면 그 이름으로 바꿔주세요!
        pixmap = QPixmap("images/cooking.png.png").scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation) # 크기도 50->60으로 키움!
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)

        title_label = QLabel(burner_title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white; background: transparent;")

        card_layout.addWidget(icon_label)
        card_layout.addWidget(title_label)

        # 남은 시간 표시
        time_label = QLabel("00:00")
        time_label.setAlignment(Qt.AlignCenter)
        time_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #ff9f43; background: transparent;")
        card_layout.addWidget(time_label)

        # ------------------------------------------------
        # ➕➖ 2. 콩알만한 버튼 아이콘 큼직하게 키우기
        # ------------------------------------------------
        btn_layout = QHBoxLayout()
        
        btn_minus = QPushButton(" -10초")
        btn_minus.setIcon(QIcon("images/minus.png.png")) # 마이너스 이미지 이름 확인!
        btn_minus.setIconSize(QSize(28, 28)) # 👈 16에서 28로 확 키웠습니다!

        btn_plus = QPushButton(" +10초")
        btn_plus.setIcon(QIcon("images/plus.png.png"))   # 플러스 이미지 이름 확인!
        btn_plus.setIconSize(QSize(28, 28)) # 👈 16에서 28로 확 키웠습니다!
        
        btn_layout.addWidget(btn_minus)
        btn_layout.addWidget(btn_plus)
        card_layout.addLayout(btn_layout)

        card_widget = QWidget()
        card_widget.setLayout(card_layout)
        
        # 카드 기본 디자인
        card_widget.setStyleSheet("""
            QWidget {
                background-color: #2b2b3c;
                border-radius: 15px;
            }
            QPushButton {
                background-color: #3b3b58;
                color: white;
                border-radius: 8px;
                padding: 10px;       /* 👈 아이콘이 커진 만큼 여백도 조금 늘려줬어요 */
                font-size: 14px;     /* 👈 글자 크기도 살짝 키움 */
                font-weight: bold;
                border: none;
            }
            QPushButton:hover { background-color: #4e4e76; }
        """)
        return card_widget

    # ==========================================
    # 🎯 3. 제스처로 화구 선택 시 테두리 강조!
    # ==========================================
    def select_burner(self, num):
        # 1. 모든 카드를 원래 기본 색상으로 되돌리기
        for card in self.timer_cards:
            card.setStyleSheet("""
                QWidget { background-color: #2b2b3c; border: none; border-radius: 15px; }
                QPushButton { background-color: #3b3b58; color: white; border-radius: 8px; padding: 8px; font-weight: bold; border: none; }
            """)
        
        # 2. 선택된 카드(num)만 화려한 오렌지색 테두리 적용!
        if 1 <= num <= len(self.timer_cards):
            self.timer_cards[num - 1].setStyleSheet("""
                QWidget { background-color: #2b2b3c; border: 3px solid #ff9f43; border-radius: 15px; }
                QPushButton { background-color: #3b3b58; color: white; border-radius: 8px; padding: 8px; font-weight: bold; border: none; }
            """)


    # (이 아래는 기존 카메라 및 제스처 연동 코드 그대로 유지)
    def on_snap_swipe(self):
        screen = QApplication.primaryScreen().geometry()
        if not self.is_mini_mode:
            self.resize(300, 220)
            self.move(screen.width() - 320, screen.height() - 260)
            self.is_mini_mode = True
            print(">> [UI] 미니 모드 전환 (우측 하단)")
        else:
            self.resize(1100, 700)
            center_x = (screen.width() - 1100) // 2
            center_y = (screen.height() - 700) // 2
            self.move(center_x, center_y)
            self.is_mini_mode = False
            print(">> [UI] 기본 모드 전환 (화면 중앙)")
        pyautogui.hotkey('alt', 'tab')

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
                        print(gestures)

                        if gestures:
                            gesture_name = gestures[0]["gesture"]
                            self.label_gesture.setText(f"Gesture : {gesture_name}")

                            if gesture_name == "one":
                                self.label_selected.setText("Selected : 🔥 1번")
                                self.select_burner(1)
                            elif gesture_name == "two":
                                self.label_selected.setText("Selected : 🔥 2번")
                                self.select_burner(2)
                            elif gesture_name == "three":
                                self.label_selected.setText("Selected : 🔥 3번")
                                self.select_burner(3)
                            elif gesture_name == "four":
                                self.label_selected.setText("Selected : 🔥 4번")
                                self.select_burner(4)
                    except Exception as e:
                        print(f"[kitchen_App] 제스처 처리 중 오류 발생: {e}")

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
        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = kitchen_App()
    window.show()
    sys.exit(app.exec())