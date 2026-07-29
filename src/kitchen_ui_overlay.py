import cv2
from PySide6.QtWidgets import (QWidget,
                               QLabel, QPushButton,
                               QVBoxLayout, QHBoxLayout)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap


class kitchen_App(QWidget):
    def __init__(self):
        super().__init__()

        # 웹캠 관련 변수
        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame) # 타이머가 울릴 때마다 프레임 갱신

        self.init_UI()

    def init_UI(self):
        self.setWindowTitle("실시간 웹캠 플레이어")
        self.resize(680, 560)

        # 1. 웹캠 화면을 출력할 QLabel 생성
        self.image_label = QLabel("웹캠 화면이 여기에 표시됩니다.", self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #222; color: #fff; font-size: 16px;")
        self.image_label.setMinimumSize(640, 480)

        # 2. 시작 / 일시정지 버튼 생성
        self.btn_start = QPushButton("시작", self)
        self.btn_pause = QPushButton("일시정지", self)

        # 버튼 스타일링 (선택 사항)
        self.btn_start.setFixedHeight(40)
        self.btn_pause.setFixedHeight(40)

        # 버튼 클릭 이벤트 연결
        self.btn_start.clicked.connect(self.start_webcam)
        self.btn_pause.clicked.connect(self.pause_webcam)

        # 3. 레이아웃 배치
        # 하단 버튼용 수평 레이아웃 (HBox)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_pause)

        # 전체 메인 수직 레이아웃 (VBox)
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.image_label) # 상단: 웹캠 화면
        main_layout.addLayout(btn_layout)        # 하단: 버튼 레이아웃

        self.setLayout(main_layout)

    def start_webcam(self):
        """웹캠 시작"""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0) # 0번 기본 웹캠 열기

        if not self.timer.isActive():
            self.timer.start(30) # 30ms 간격으로 update_frame 호출 (약 33 FPS)

    def pause_webcam(self):
        """웹캠 일시정지"""
        if self.timer.isActive():
            self.timer.stop() # 타이머 멈춤 (프레임 갱신 중단)

    def update_frame(self):
        """OpenCV 프레임을 읽어서 PySide QLabel에 그리기"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # 1. OpenCV(BGR) -> RGB 변환
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 2. QImage 변환
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

                # 3. QLabel 크기에 맞게 Scaled Pixmap 생성 후 적용
                pixmap = QPixmap.fromImage(qt_image)
                scaled_pixmap = pixmap.scaled(
                    self.image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)

    def closeEvent(self, event):
        """프로그램 종료 시 웹캠 자원 해제"""
        self.timer.stop()
        if self.cap and self.cap.isOpened():
            self.cap.release()
        event.accept()