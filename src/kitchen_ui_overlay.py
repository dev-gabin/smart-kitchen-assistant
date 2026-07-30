import cv2
import pyautogui
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QApplication, QSizePolicy)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from src.gesture import GestureController


class kitchen_App(QWidget):
    def __init__(self):
        super().__init__()

        # 항상 맨 위에 표시 (창이 최소화되거나 뒤로 숨는 것 방지)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.is_mini_mode = False
        self.gesture_controller = None
        try:
            self.gesture_controller = GestureController()
            self.gesture_controller.swipe_detected.connect(self.on_snap_swipe)
        except Exception as e:
            print(f"[kitchen_App] 제스처 컨트롤러 초기화 실패: {e}")

        self.init_UI()

    def changeEvent(self, event):
        """최소화 방지"""
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized():
                self.showNormal()
                self.raise_()
                self.activateWindow()
        super().changeEvent(event)

    def init_UI(self):
        self.setWindowTitle("제스처 컨트롤러")

        # 처음 실행될 때의 기본 크기
        self.resize(900, 760)

        # 웹캠 화면 표시 레이블 (고정 최소 크기 setMinimumSize 제거)
        self.image_label = QLabel("웹캠 준비 중...", self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #222; color: #fff; font-size: 14px;")
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        # 시작 / 일시정지 버튼
        self.btn_start = QPushButton("시작", self)
        self.btn_pause = QPushButton("일시정지", self)
        self.btn_start.setFixedHeight(35)
        self.btn_pause.setFixedHeight(35)

        self.btn_start.clicked.connect(self.start_webcam)
        self.btn_pause.clicked.connect(self.pause_webcam)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_pause)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(self.image_label)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

    def on_snap_swipe(self):
        """스냅 감지 시: 1) 미니 창 축소 & 우하단 이동  2) Alt+Tab 실행"""
        # 1. 미니 PIP 크기로 축소 (320x260)
        screen = QApplication.primaryScreen().geometry()

        if not self.is_mini_mode:
            # 1. 미니 모드로 전환 (작아지면서 우하단 이동)
            self.resize(300, 220)
            self.move(screen.width() - 320, screen.height() - 260)
            self.is_mini_mode = True
            print(">> [UI] 미니 모드 전환 (우측 하단)")
        else:
            # 2. 기본 모드로 복원 (크어지면서 화면 중앙 이동)
            self.resize(900, 760)
            center_x = (screen.width() - 680) // 2
            center_y = (screen.height() - 560) // 2
            self.move(center_x, center_y)
            self.is_mini_mode = False
            print(">> [UI] 기본 모드 전환 (화면 중앙)")

        # 3. Alt+Tab 실행하여 다른 창으로 전환
        pyautogui.hotkey('alt', 'tab')

    def start_webcam(self):
        """웹캠 시작"""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)

        if not self.timer.isActive():
            self.timer.start(30)

    def pause_webcam(self):
        """웹캠 일시정지"""
        if self.timer.isActive():
            self.timer.stop()

    def update_frame(self):
        """OpenCV 프레임을 읽어서 PySide QLabel에 그리기"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                if self.gesture_controller is not None:
                    try:
                        frame, gestures = self.gesture_controller.process(frame)
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
        self.timer.stop()
        if self.cap and self.cap.isOpened():
            self.cap.release()
        event.accept()