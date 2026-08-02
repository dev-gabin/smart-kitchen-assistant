import sys
import os
import cv2
import threading
import winsound
import pyautogui

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QBrush, QImage
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QToolButton, QDialog,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame, QScrollArea
)
from src.gesture import GestureController
from src.smoke import SmokeDetector

class ToggleSwitch(QPushButton):
    """
    [커스텀 토글 스위치]
    - 시안과 동일하게 회색/브라운 트랙 배경과 하얀색 동그라미 손잡이가 
      부드럽게 움직이는 미니멀 토글 스위치 컴포넌트입니다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(54, 28)
        self.setCheckable(True)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 트랙 배경 색상 지정 (활성화 시 브라운, 비활성화 시 회색)
        track_color = QColor("#8C6D53") if self.isChecked() else QColor("#D6CEC7")
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        
        # 내부 하얀색 원형 손잡이 위치 계산 및 드로잉
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        handle_x = 28 if self.isChecked() else 3
        painter.drawEllipse(handle_x, 3, 22, 22)

class KitchenApp(QWidget):
    def __init__(self):
        super().__init__()

        self.smoke_dialog = QDialog(self)
        self.video_source=0 #모드 설정
        # self.video_source="data/smoke5.mp4"
        # 웹캠 및 제스처 컨트롤러 초기화
        self.cap = None
        self.gesture_controller = GestureController()
        
        # 제스처 스와이프 시그널 연결 (위젯 모드 토글 연동)
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
        self.somoke_dialog=None #팝업창 변수


        self.is_mini_mode = False
        self.first_mini_entry = True  # 앱 실행 후 첫 미니모드 진입 여부 체크용 플래그
        self.normal_window_flags = self.windowFlags()  # 대시보드 복구 시 원래 창 플래그 보관용

        # 웹캠 프레임 갱신 타이머 (30FPS 주기)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        self.init_UI()
        self.start_webcam()

    def get_icon(self, filename):
        """img 폴더 내의 아이콘 파일을 안전하게 로드하는 헬퍼 메서드"""
        path = os.path.join("img", filename)
        return QIcon(path) if os.path.exists(path) else QIcon()

    def init_UI(self):
        """메인 GUI 레이아웃 및 스타일을 초기화하는 메서드"""
        self.setWindowTitle("Smart Kitchen Assistant")
        self.resize(1150, 750) 
        self.setMinimumSize(0, 0)
        
        # 따뜻하고 노란끼 감도는 바닐라 크림 테마 전역 스타일 적용
        self.setStyleSheet("""
            QWidget { 
                background-color: #FDF9F3; 
                color: #3E3832; 
                font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; 
            }
        """)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(20)


        # ----------------------------------------------------
        # [우측] 메인 콘텐츠 대시보드 영역
        # ----------------------------------------------------
        self.content_frame = QFrame()
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(15)

        # 상단 타이틀 및 모드 배지 헤더
        self.header_frame = QFrame()
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        
        title_top_layout = QHBoxLayout()
        title_top_layout.setContentsMargins(0, 0, 0, 0)
        title_top_layout.setSpacing(8)
        
        title_title = QLabel("Smart Kitchen")
        title_title.setStyleSheet("font-size: 24px; font-weight: 900; color: #3E3832; background: transparent;")
        title_top_layout.addWidget(title_title)
        header_layout.addLayout(title_top_layout)

        sub_layout = QHBoxLayout()
        sub_layout.setContentsMargins(0, 0, 0, 0)
        sub_layout.setSpacing(8)
        
        title_sub = QLabel("Assistant")
        title_sub.setStyleSheet("font-size: 12px; color: #8C6D53; font-weight: bold; background: transparent;")
        
        mode_badge = QLabel("주방 안전 모드")
        mode_badge.setStyleSheet("""
            background-color: #F4EBE1; 
            color: #8C6D53; 
            border: 1px solid #E5D8CC; 
            border-radius: 12px; 
            padding: 3px 10px; 
            font-size: 11px; 
            font-weight: bold;
        """)
        
        sub_layout.addWidget(title_sub)
        sub_layout.addWidget(mode_badge)
        sub_layout.addStretch()
        
        title_box.addWidget(title_title)
        title_box.addLayout(sub_layout)
        
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        ##위젯 모드 버튼 이식
        widget_layout = QHBoxLayout()
        widget_layout.setSpacing(10)
        
        self.btn_widget = QPushButton(" 위젯 모드")
        self.btn_widget.setIcon(self.get_icon("widget.png"))
        self.btn_widget.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 12px; font-weight: bold; color: #594A42; padding: 8px 12px;")
        self.btn_widget.clicked.connect(self.on_snap_swipe)

        self.toggle_switch = ToggleSwitch()
        self.toggle_switch.clicked.connect(self.on_snap_swipe)
        
        widget_layout.addWidget(self.btn_widget)
        widget_layout.addWidget(self.toggle_switch)
        header_layout.addLayout(widget_layout)
        header_layout.addSpacing(15)

        for icon_file in ["08_settings.png", "24_brightness.png", "23_fullscreen.png"]:
            btn = QPushButton()
            btn.setIcon(self.get_icon(icon_file))
            btn.setIconSize(QSize(26, 26))
            btn.setFixedSize(50, 50)
            btn.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 12px;")
            header_layout.addWidget(btn)
            
        self.content_layout.addWidget(self.header_frame)

        # 중단 영역 (웹캠 카메라 뷰 카드 + 화구 타이머 리스트 카드)
        self.middle_layout = QHBoxLayout()
        self.middle_layout.setSpacing(15)

        # 1. 카메라 뷰 카드 (와이드 가로형 비율)
        self.cam_frame = QFrame()
        self.cam_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
        cam_layout = QVBoxLayout(self.cam_frame)
        cam_layout.setContentsMargins(15, 15, 15, 15)
        
        cam_header = QHBoxLayout()
        
        cam_icon_lbl = QLabel()
        cam_pixmap = QPixmap("img/08_settings.png")
        if not cam_pixmap.isNull():
            cam_icon_lbl.setPixmap(cam_pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        cam_icon_lbl.setStyleSheet("border: none; background: transparent;")
        
        cam_title = QLabel(" 카메라 뷰")
        cam_title.setStyleSheet("font-size: 15px; font-weight: 800; border: none;")
        
        # 실시간 LIVE 상태 인디케이터 (제스처 감지 여부에 따라 노랑/빨강 동적 반영)
        self.cam_live = QLabel("● LIVE")
        self.cam_live.setStyleSheet("""
            background-color: #1A1A1A; 
            color: #E2B714; 
            border-radius: 12px; 
            padding: 4px 12px; 
            font-size: 11px; 
            font-weight: bold;
        """)
        self.cam_live.setAlignment(Qt.AlignCenter)
        
        cam_header_left = QHBoxLayout()
        cam_header_left.setSpacing(5)
        cam_header_left.addWidget(cam_icon_lbl)
        cam_header_left.addWidget(cam_title)
        
        cam_header.addLayout(cam_header_left)
        cam_header.addStretch()
        cam_header.addWidget(self.cam_live)
        
        self.image_label = QLabel("웹캠 연결 중...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(540, 310)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setStyleSheet("background-color: #1A1A1A; border-radius: 14px;")
        
        cam_layout.addLayout(cam_header)
        cam_layout.addSpacing(10)
        cam_layout.addWidget(self.image_label, stretch=1)
        
        self.middle_layout.addWidget(self.cam_frame, stretch=7)

        # 2. 화구 타이머 리스트 카드
        self.timer_frame = QFrame()
        self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
        self.timer_layout = QVBoxLayout(self.timer_frame)
        self.timer_layout.setContentsMargins(15, 15, 15, 15)
        self.timer_layout.setSpacing(10)
        
        self.t_header_frame = QFrame()
        self.t_header_frame.setStyleSheet("background: transparent; border: none;")
        t_header = QHBoxLayout(self.t_header_frame)
        t_header.setContentsMargins(0,0,0,0)
        
        t_icon_lbl = QLabel()
        t_pixmap = QPixmap("img/03_clock_1.png")
        if not t_pixmap.isNull():
            t_icon_lbl.setPixmap(t_pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        t_icon_lbl.setStyleSheet("border: none; background: transparent;")
        
        self.lbl_t_title = QLabel(" 타이머")
        self.lbl_t_title.setStyleSheet("font-size: 15px; font-weight: 800; border: none;")
        
        t_title_layout = QHBoxLayout()
        t_title_layout.setSpacing(6)
        t_title_layout.addWidget(t_icon_lbl)
        t_title_layout.addWidget(self.lbl_t_title)
        
        self.btn_t_add = QPushButton()
        self.btn_t_add.setIcon(self.get_icon("20_plus.png"))
        self.btn_t_add.setStyleSheet("background: transparent; border: none;")
        
        t_header.addLayout(t_title_layout)
        t_header.addStretch()
        t_header.addWidget(self.btn_t_add)
        self.timer_layout.addWidget(self.t_header_frame)

        self.lbl_pot1 = QLabel("--:--")
        self.lbl_pot2 = QLabel("--:--")
        self.lbl_pot3 = QLabel("--:--")
        self.lbl_pot4 = QLabel("--:--")
        
        self.pot_wrappers = []
        self.timer_buttons = []
        
        for num, icon_file, name, time_lbl in [
            ("01", "11_noodle_bowl.png", "라면", self.lbl_pot1),
            ("02", "10_pot.png", "계란 삶기", self.lbl_pot2),
            ("03", "13_pasta_bowl.png", "파스타", self.lbl_pot3),
            ("04", "15_steaming_pot.png", "찜 요리", self.lbl_pot4)
        ]:
            w, b_play = self.create_timer_item(num, icon_file, name, time_lbl)
            self.timer_layout.addWidget(w)
            self.pot_wrappers.append(w)
            
        self.timer_layout.addStretch()
        self.middle_layout.addWidget(self.timer_frame, stretch=3)
        self.content_layout.addLayout(self.middle_layout, stretch=1)

        # 하단 상태 표시바 (제스처 인식, 포커스 화구, 연기 감지 상태)
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
        self.status_frame.setFixedHeight(95)
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)
        
        self.lbl_gesture = QLabel("정상")
        self.lbl_selected = QLabel("-")
        self.lbl_smoke = QLabel("안전")
        
        stat1 = self.create_status_item("06_hand_gesture.png", "제스처 인식", self.lbl_gesture, "인식 상태 양호", "#8C6D53")
        stat2 = self.create_status_item("16_hourglass.png", "포커스 화구", self.lbl_selected, "제어 대기중", "#D5BDAF")
        stat3 = self.create_status_item("17_smoke_status.png", "연기 감지 상태", self.lbl_smoke, "정상 범위", "#8C6D53")
        
        status_layout.addWidget(stat1)
        div1 = QFrame(); div1.setFixedWidth(1); div1.setStyleSheet("background-color: #EAE0D5;")
        status_layout.addWidget(div1)
        status_layout.addWidget(stat2)
        div2 = QFrame(); div2.setFixedWidth(1); div2.setStyleSheet("background-color: #EAE0D5;")
        status_layout.addWidget(div2)
        status_layout.addWidget(stat3)

        self.content_layout.addWidget(self.status_frame)

        # 최하단 전체 컨트롤 버튼 (pause.png, reset.png, bell.png 적용)
        self.control_frame = QFrame()
        self.control_frame.setFixedHeight(65)
        control_layout = QHBoxLayout(self.control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)
        
        btn_base = """
            QPushButton {
                background-color: #FFFFFF; 
                border: 1px solid #EAE0D5; 
                border-radius: 16px; 
                font-size: 14px; 
                font-weight: 800; 
                color: #594A42;
                padding: 10px 20px;
            }
            QPushButton:hover { background-color: #F8F5F0; }
        """
        
        self.btn_pause = QPushButton(" 전체 정지"); self.btn_pause.setIcon(self.get_icon("pause.png"))
        self.btn_pause.setStyleSheet(btn_base)
        
        self.btn_reset = QPushButton(" 전체 초기화"); self.btn_reset.setIcon(self.get_icon("reset.png"))
        self.btn_reset.setStyleSheet(btn_base)
        
        self.btn_alert_off = QPushButton(" 경보 끄기"); self.btn_alert_off.setIcon(self.get_icon("bell.png"))
        self.btn_alert_off.setStyleSheet("""
            QPushButton {
                background-color: #FDF2F2; 
                border: 1px solid #F5CDCD; 
                border-radius: 16px; 
                font-size: 14px; 
                font-weight: 800; 
                color: #B23B3B;
                padding: 10px 20px;
            }
            QPushButton:hover { background-color: #FAEEEE; }
        """)
        
        self.btn_pause.clicked.connect(self.pause_all_timers)
        self.btn_reset.clicked.connect(self.reset_all_timers)

        for b in [self.btn_pause, self.btn_reset, self.btn_alert_off]:
            b.setIconSize(QSize(28, 28))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setFixedHeight(55)

        control_layout.addWidget(self.btn_pause)
        control_layout.addWidget(self.btn_reset)
        control_layout.addWidget(self.btn_alert_off)
        control_layout.addSpacing(5)

        self.content_layout.addWidget(self.control_frame)
        self.main_layout.addWidget(self.content_frame)

        # 타이머 데이터 상태 변수 초기화
        self.selected_pot = None           
        self.pot_times = [0, 0, 0, 0]      
        self.pot_states = ["대기", "대기", "대기", "대기"]  
        self.pot_labels = [self.lbl_pot1, self.lbl_pot2, self.lbl_pot3, self.lbl_pot4]
        self.is_long_time_mode = False

        # 마스터 카운트다운 타이머 (1초 주기)
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.update_countdowns)
        self.master_timer.start(1000)

        # 컨트롤러 제스처 및 기능 시그널 바인딩
        self.gesture_controller.pot_selected_signal.connect(self.select_burner)
        self.gesture_controller.timer_pause_signal.connect(self.pause_selected_timer)
        self.gesture_controller.timer_reset_signal.connect(self.reset_selected_timer)
        self.gesture_controller.timer_pause_all_signal.connect(self.pause_all_timers)
        self.gesture_controller.timer_reset_all_signal.connect(self.reset_all_timers)
        self.gesture_controller.sidebar_focus_signal.connect(self.set_sidebar_focus)
        self.gesture_controller.timer_toggle_long_mode_signal.connect(self.toggle_long_time_mode)
        self.gesture_controller.timer_add_time_signal.connect(self.add_time_to_selected_pot)
        self.gesture_controller.timer_confirm_signal.connect(self.confirm_pot_setting)
        self.gesture_controller.timer_smart_start_signal.connect(self.smart_start_timers)

    def create_timer_item(self, num, icon_file, name, time_lbl):
        """개별 타이머 카드 위젯 생성 헬퍼 함수"""
        wrapper = QFrame()
        wrapper.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
        wrapper.setFixedHeight(75)
        layout = QHBoxLayout(wrapper)
        
        # 카드 내부 좌우 여백을 줄여서 미니창(280px) 안에서도 시간이 잘리지 않게 확보!
        layout.setContentsMargins(10, 0, 10, 0)
        
        lbl_num = QLabel(num)
        lbl_num.setStyleSheet("font-size: 14px; font-weight: bold; color: #3E3832; border: none;")
        
        lbl_icon = QLabel()
        lbl_icon.setStyleSheet("border: none; background: transparent;")
        pixmap = QPixmap(os.path.join("img", icon_file))
        if not pixmap.isNull():
            lbl_icon.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("font-size: 13px; color: #786C61; font-weight: bold; border: none;")
        
        # 시간 레이블이 오른쪽 끝에 찰싹 붙도록 너비를 살짝 줄이고 우측 정렬
        time_lbl.setStyleSheet("font-size: 18px; font-weight: 900; color: #3E3832; border: none;")
        time_lbl.setMinimumWidth(55)
        time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        btn_play = QPushButton()
        btn_play.setIcon(self.get_icon("21_play.png"))
        btn_play.setIconSize(QSize(18, 18))
        btn_play.setFixedSize(36, 36)
        btn_play.setStyleSheet("background-color: #D5BDAF; border-radius: 18px; border: none;")
        
        self.timer_buttons.append(btn_play)
        
        # 요소들 사이의 간격을 쫀쫀하게 줄여서 280px 창에 쏙 들어가게 세팅!
        layout.addWidget(lbl_num)
        layout.addSpacing(5)
        layout.addWidget(lbl_icon)
        layout.addSpacing(5)
        layout.addWidget(lbl_name)
        layout.addStretch()  # 남는 공간을 모두 흡수해서 시간과 버튼을 오른쪽 끝으로 밀어줌
        layout.addWidget(time_lbl)
        layout.addSpacing(5)
        layout.addWidget(btn_play)
        
        return wrapper, btn_play

    def create_status_item(self, icon_file, title, val_lbl, sub, dot_color):
        """하단 상태 표시바 아이템 생성 헬퍼 함수"""
        widget = QFrame()
        widget.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 15, 20, 15)
        
        icon_lbl = QLabel()
        pixmap = QPixmap(os.path.join("img", icon_file))
        if not pixmap.isNull():
            icon_lbl.setPixmap(pixmap.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_lbl.setFixedSize(50, 50)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background-color: #F4EBE1; border-radius: 25px;")
        
        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 11px; color: #786C61; font-weight: bold;")
        val_lbl.setStyleSheet("font-size: 17px; font-weight: 900; color: #3E3832;")
        s_lbl = QLabel(sub)
        s_lbl.setStyleSheet("font-size: 10px; color: #A69B91;")
        text_box.addWidget(t_lbl)
        text_box.addWidget(val_lbl)
        text_box.addWidget(s_lbl)
        
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")
        dot.setAlignment(Qt.AlignTop | Qt.AlignRight)
        
        layout.addWidget(icon_lbl)
        layout.addSpacing(12)
        layout.addLayout(text_box)
        layout.addStretch()
        layout.addWidget(dot)
        return widget

    def toggle_long_time_mode(self):
        """장시간 모드(x10 배속) 토글 메서드"""
        self.is_long_time_mode = not self.is_long_time_mode
        mode_str = "장시간 모드" if self.is_long_time_mode else "기본 모드"
        if self.selected_pot:
            self.lbl_selected.setText(f"0{self.selected_pot} [{mode_str}]")
        else:
            self.lbl_selected.setText(f"모드: {mode_str}")

    def select_burner(self, num):
        """특정 화구를 선택(포커스)하는 메서드"""
        self.selected_pot = num
        if not self.is_mini_mode:
            for i, w in enumerate(self.pot_wrappers):
                if (i + 1) == num:
                    w.setStyleSheet("background-color: #FFFDF9; border: 2px solid #8C6D53; border-radius: 16px;")
                else:
                    w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
        
        self.lbl_selected.setText(f"0{num} [시간 설정 중]")
        
        # 미니모드 중에 숨겨져 있던 화구를 제스처로 선택하면 즉시 뿅! 나타나게 갱신
        if self.is_mini_mode:
            self.update_mini_mode_layout()

    def add_time_to_selected_pot(self, base_mins: int):
        """선택된 화구에 타이머 시간을 추가하는 메서드"""
        if self.selected_pot is None:
            return
        
        idx = self.selected_pot - 1
        multiplier = 10 if self.is_long_time_mode else 1
        add_mins = base_mins * multiplier
        
        self.pot_times[idx] += add_mins * 60  
        self.refresh_pot_label(idx)
        self.lbl_selected.setText(f"0{self.selected_pot} [{self.pot_times[idx]//60}분 설정됨]")

    def confirm_pot_setting(self):
        """화구 시간 세팅을 확정하는 메서드"""
        if self.selected_pot is not None:
            self.lbl_selected.setText(f"0{self.selected_pot} [세팅 완료 / 조작 가능]")

    def pause_selected_timer(self):
        """
        💡 [수정] ✋ (보) 제스처:
        선택된 개별 화구의 타이머를 재생/정지하는 기능!
        - 실행 중이면 -> 일시 정지
        - 정지 또는 대기 중(시간 세팅됨)이면 -> 개별 시작
        """
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            if self.pot_states[idx] == "실행":
                self.pot_states[idx] = "정지"
                self.timer_buttons[idx].setIcon(self.get_icon("21_play.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #D5BDAF; border-radius: 16px; border: none;")
                self.lbl_selected.setText(f"0{self.selected_pot} [일시 정지됨]")
            
            # 기존에는 "정지" 상태만 다시 켰지만, 이제 "대기"(방금 세팅함) 상태도 개별 시작 가능!
            elif self.pot_states[idx] in ["정지", "대기"] and self.pot_times[idx] > 0:
                self.pot_states[idx] = "실행"
                self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #EAE0D5; border-radius: 16px; border: none;")
                self.lbl_selected.setText(f"0{self.selected_pot} [개별 시작됨]")

    def reset_selected_timer(self):
        """선택된 화구의 타이머를 초기화하는 메서드"""
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            self.pot_times[idx] = 0
            self.pot_states[idx] = "대기"
            self.refresh_pot_label(idx)
            self.timer_buttons[idx].setIcon(self.get_icon("21_play.png"))
            self.timer_buttons[idx].setStyleSheet("background-color: #D5BDAF; border-radius: 16px; border: none;")
            
            # 초기화 시 해당 화구 포커스 해제 (미니모드에서 즉시 숨기기 위함)
            self.selected_pot = None
            self.lbl_selected.setText("-")
            for w in self.pot_wrappers:
                w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
                
            # 미니모드일 경우 초기화된 화구를 화면에서 즉시 쏙! 지우고 창을 줄임
            if self.is_mini_mode:
                self.update_mini_mode_layout()

    def smart_start_timers(self):
        """
        💡 [수정] 👍 (엄지 척) 제스처 (스마트 마스터 제어):
        1. 세팅 후 대기/정지 중인 화구가 하나라도 있으면 -> 기존 실행 중인 건 건드리지 않고, 대기 중인 놈들만 쿨하게 추가 시작!
        2. 전부 다 신나게 실행 중이면 -> 그때서야 전체 일시 정지 쾅!
        """
        ready_indices = [i for i in range(4) if self.pot_times[i] > 0 and self.pot_states[i] in ["대기", "정지"]]
        running_indices = [i for i in range(4) if self.pot_states[i] == "실행"]
        
        # 1. 방금 세팅해서 대기/정지 중인 게 있다면 무조건 그것들을 우선 시작!
        if ready_indices:
            for idx in ready_indices:
                self.pot_states[idx] = "실행"
                self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #EAE0D5; border-radius: 16px; border: none;")
            if self.selected_pot:
                self.lbl_selected.setText(f"0{self.selected_pot} [스마트 시작됨]")
        
        # 2. 대기/정지 중인 건 하나도 없고, 전부 실행 중일 때만 -> 전체 멈춤!
        elif running_indices:
            for i in running_indices:
                self.pot_states[i] = "정지"
                self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 16px; border: none;")
            if self.selected_pot:
                self.lbl_selected.setText("전체 일시 정지됨")

    def pause_all_timers(self):
        """모든 화구의 타이머를 일괄 정지 또는 재개하는 메서드"""
        any_running = any(state == "실행" for state in self.pot_states)
        if any_running:
            for i in range(4):
                if self.pot_states[i] == "실행":
                    self.pot_states[i] = "정지"
                    self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 16px; border: none;")
            self.btn_pause.setText(" 전체 재생")
            self.btn_pause.setIcon(self.get_icon("pause.png"))
        else:
            for i in range(4):
                if self.pot_states[i] == "정지" and self.pot_times[i] > 0:
                    self.pot_states[i] = "실행"
                    self.timer_buttons[i].setIcon(self.get_icon("22_pause.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #EAE0D5; border-radius: 16px; border: none;")
            self.btn_pause.setText(" 전체 정지")
            self.btn_pause.setIcon(self.get_icon("pause.png"))

    def reset_all_timers(self):
        """모든 화구의 타이머와 상태를 초기화하는 메서드"""
        for i in range(4):
            self.pot_times[i] = 0
            self.pot_states[i] = "대기"
            self.refresh_pot_label(i)
            self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
            self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 16px; border: none;")
        
        self.btn_pause.setText(" 전체 정지")
        self.btn_pause.setIcon(self.get_icon("pause.png"))
        
        self.selected_pot = None
        self.lbl_selected.setText("-")
        for w in self.pot_wrappers:
            w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
            
        # 미니모드일 경우 전체 화구가 사라지고 기본값만 남도록 동적 업데이트
        if self.is_mini_mode:
            self.update_mini_mode_layout()

    def set_sidebar_focus(self, idx: int):
        """사이드바는 제거되었지만, 제스처(idx==2) 가이드 팝업 기능은 유지"""
        self.current_sidebar_index = idx

        # 3번 메뉴(제스처) 조작 매뉴얼 팝업 토글
        if idx == 2:
            if hasattr(self, 'guide_window') and self.guide_window.isVisible():
                self.guide_window.close()
                self.toggle_switch.setChecked(False)
            else:
                self.show_gesture_guide()
                self.toggle_switch.setChecked(True)
    def show_gesture_guide(self):
        """제스처 조작 매뉴얼 팝업 창 생성 (스크롤 지원)"""
        if hasattr(self, 'guide_window') and self.guide_window.isVisible():
            self.guide_window.raise_()
            self.guide_window.activateWindow()
            return

        self.guide_window = QWidget()
        self.guide_window.setWindowTitle("제스처 조작 매뉴얼")
        self.guide_window.setFixedSize(600, 750) 
        self.guide_window.setStyleSheet("background-color: #FDF9F3;")
        
        main_layout = QVBoxLayout(self.guide_window)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 15, 0)
        
        guide_label = QLabel()
        guide_label.setTextFormat(Qt.RichText)
        guide_label.setWordWrap(True)
        
        gesture_guide_text = """
        <div style="font-family: 'Malgun Gothic', sans-serif; color: #3E3832; font-size: 13px;">
            <h3 style="color: #8C6D53;">👨‍🍳 1. 기본 요리 시나리오 (Step-by-Step)</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <tr style="background-color: #F5EBE6; border-bottom: 2px solid #E3D5CA;">
                    <th style="padding: 10px;">순서</th><th style="padding: 10px;">기능</th><th style="padding: 10px;">제스처</th><th style="padding: 10px;">설명</th>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">STEP 1</td><td style="padding: 10px; font-weight: bold;">화구 선택</td>
                    <td style="padding: 10px;">☝✌🤟 (1,2,3,4)</td><td style="padding: 10px;">원하는 화구를 가리켜 포커스 지정</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">STEP 2</td><td style="padding: 10px; font-weight: bold;">시간 추가</td>
                    <td style="padding: 10px;">☝🤟🖐 (1,3,5분)</td><td style="padding: 10px;">선택된 화구에 +1분, +3분, +5분 누적</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-style: italic; color: #786C61;">옵션</td><td style="padding: 10px; font-style: italic; color: #786C61;">단위 변경</td>
                    <td style="padding: 10px;">🤘 (ROCK)</td><td style="padding: 10px;">기본 모드(분) ↔ 장시간 모드(x10 단위)</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">STEP 3</td><td style="padding: 10px; font-weight: bold;">세팅 확정</td>
                    <td style="padding: 10px;">👌 (OK)</td><td style="padding: 10px;">시간을 저장하고 다른 화구 조작 대기</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">STEP 4</td><td style="padding: 10px; font-weight: bold;">요리 시작</td>
                    <td style="padding: 10px; color: #8C6D53; font-weight: bold;">👍 (엄지 척)</td><td style="padding: 10px; font-weight: bold;">세팅 완료된 모든 화구 일괄 시작!</td>
                </tr>
            </table>
            
            <br><br>
            
            <h3 style="color: #8C6D53;">🎯 2. 개별 제어 (포커스된 화구 대상)</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <tr style="background-color: #F5EBE6; border-bottom: 2px solid #E3D5CA;">
                    <th style="padding: 10px;">기능</th><th style="padding: 10px;">제스처</th><th style="padding: 10px;">설명 (작동 조건)</th>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">재생/일시정지</td><td style="padding: 10px;">✋ (보)</td><td style="padding: 10px;"><b>선택된 화구만</b> 조작 (0.8초 유지)</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">타이머 초기화</td><td style="padding: 10px;">✊ (주먹)</td><td style="padding: 10px;"><b>선택된 화구</b> 리셋 (0.5초 유지)</td>
                </tr>
            </table>

            <br><br>

            <h3 style="color: #8C6D53;">👑 3. 마스터 스위치 (전체 제어)</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <tr style="background-color: #F5EBE6; border-bottom: 2px solid #E3D5CA;">
                    <th style="padding: 10px;">기능</th><th style="padding: 10px;">제스처</th><th style="padding: 10px;">설명 (작동 조건)</th>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">스마트 일괄 제어</td><td style="padding: 10px;">👍 (엄지 척)</td><td style="padding: 10px;">[요리중] 전체 정지 / [대기중] 전체 시작</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold; color: #B23B3B;">긴급 전체 정지</td><td style="padding: 10px;">🙌 (양손 보)</td><td style="padding: 10px;">작동 중인 모든 화구 즉시 정지</td>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold; color: #B23B3B;">긴급 전체 초기화</td><td style="padding: 10px;">🤜🤛 (양손 주먹)</td><td style="padding: 10px;">모든 화구 타이머 및 상태 리셋</td>
                </tr>
            </table>

            <br><br>

            <h3 style="color: #8C6D53;">✨ 4. 특수 기능</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <tr style="background-color: #F5EBE6; border-bottom: 2px solid #E3D5CA;">
                    <th style="padding: 10px;">기능</th><th style="padding: 10px;">제스처</th><th style="padding: 10px;">설명 (작동 조건)</th>
                </tr>
                <tr style="border-bottom: 1px solid #EAE0D5;">
                    <td style="padding: 10px; font-weight: bold;">위젯 모드 전환</td><td style="padding: 10px;">👋 (스와이프)</td><td style="padding: 10px;">손을 화면 밖으로 밀어내면 미니화면 전환</td>
                </tr>
            </table>
        </div>
        """
        guide_label.setText(gesture_guide_text)
        guide_label.setAlignment(Qt.AlignTop)
        
        scroll_layout.addWidget(guide_label)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        btn_close = QPushButton("확인했습니다")
        btn_close.setFixedHeight(50)
        btn_close.setStyleSheet("background-color: #8C6D53; color: white; font-weight: bold; font-size: 15px; border-radius: 12px; margin-top: 10px;")
        btn_close.clicked.connect(self.guide_window.close)
        main_layout.addWidget(btn_close)
        
        self.guide_window.destroyed.connect(lambda: self.toggle_switch.setChecked(False))
        self.guide_window.show()

    def update_countdowns(self):
        """1초마다 실행되며 작동 중인 타이머의 남은 시간을 깎아주는 카운트다운 메서드"""
        for i in range(4):
            if self.pot_states[i] == "실행" and self.pot_times[i] > 0:
                self.pot_times[i] -= 1
                self.refresh_pot_label(i)
                if self.pot_times[i] == 0:
                    self.pot_states[i] = "대기"
                    self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 16px; border: none;")

    def refresh_pot_label(self, idx):
        """특정 화구의 타이머 텍스트를 mm:ss 형식으로 갱신하는 메서드"""
        t = self.pot_times[idx]
        self.pot_labels[idx].setText(f"{t//60:02d}:{t%60:02d}" if t > 0 else "--:--")

    def update_mini_mode_layout(self):
        """
        미니모드 창에서 초기화나 포커스 변경 등 이벤트 발생 시 
        표시되는 화구 목록과 창 크기를 동적으로 바로바로 갱신해주는 메서드!
        """
        if not self.is_mini_mode:
            return
            
        active_timers = 0
        for i in range(4):
            # 시간이 설정되었거나(>0), 실행/정지 중이거나, 사용자가 방금 포커스한 화구라면 보여주기!
            if self.pot_times[i] > 0 or self.pot_states[i] != "대기" or self.selected_pot == (i + 1):
                self.pot_wrappers[i].show()
                # 현재 선택된 화구는 미니모드에서도 예쁘게 테두리 하이라이트 적용
                if self.selected_pot == (i + 1):
                    self.pot_wrappers[i].setStyleSheet("background-color: #FFFDF9; border: 2px solid #8C6D53; border-radius: 16px;")
                else:
                    self.pot_wrappers[i].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
                active_timers += 1
            else: 
                # 💡 조건에 안 맞으면(초기화돼서 00:00이고 포커스도 풀렸으면) 가차없이 스르륵 숨김!
                self.pot_wrappers[i].hide() 
        
        # 만약 초기화하다가 전부 싹 다 지워져서 텅 비면 흉하니까 기본 화구 1개 띄워둠
        if active_timers == 0:
            self.pot_wrappers[0].show()
            self.pot_wrappers[0].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
            active_timers = 1
        
        # 표시되는 타이머 개수에 맞춰 미니모드 창 높이 동적 줄임/늘림
        target_height = (active_timers * 75) + ((active_timers - 1) * 5) + 12
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        
        # 컴팩트하고 예쁜 280px 너비로 고정
        self.setFixedSize(280, target_height)
        
        # 창 크기가 변하더라도 무조건 우측 하단 구석 자리를 사수하도록 위치 재보정
        screen = self.screen().geometry()
        self.move(screen.width() + screen.x() - self.width() - 20, screen.height() + screen.y() - self.height() - 20)

    def on_snap_swipe(self):
        """전체 대시보드 화면 ↔ 우측 하단 고정 미니 위젯 모드 간의 전환을 수행하는 메서드"""
        screen = self.screen().geometry()
        
        # 최대화 상태일 때 정상 크기로 되돌림
        if self.isMaximized():
            self.showNormal()

        self.hide()
        
        if not self.is_mini_mode:
            # [미니모드 진입] 프레임리스 창 및 최상단 고정 설정
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.cam_frame.hide(); self.status_frame.hide(); self.control_frame.hide(); self.header_frame.hide(); self.t_header_frame.hide()
            self.image_label.setMinimumSize(0, 0)
            self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
            self.content_layout.setContentsMargins(0, 0, 0, 0); self.content_layout.setSpacing(0)
            self.middle_layout.setContentsMargins(0, 0, 0, 0); self.middle_layout.setSpacing(0)
            
            
            # 타이머 컨테이너가 좁은 창 안에서도 여백을 덜 차지하게 싹 줄임
            self.timer_layout.setContentsMargins(5, 5, 5, 5)
            self.timer_layout.setSpacing(5)
            
            self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1.5px solid #EAE0D5; border-radius: 20px;")
            
            self.is_mini_mode = True # 플래그를 미리 켜야 동적 업데이트 메서드가 동작함
            self.gesture_controller.is_mini_mode=True #미니모드 진입 시 스와이프 제외 손동작 인식 차단!
            if self.first_mini_entry:
               self.first_mini_entry = False
            
            # 어떤 타이머도 작동 안 하고 설정된 시간(초)도 모두 0일 때만 4개 다 표시
            all_inactive = all(t == 0 and s == "대기" for t, s in zip(self.pot_times, self.pot_states))
            if all_inactive:
                active_timers = 4
                for i in range(4):
                    self.pot_wrappers[i].show()
                    self.pot_wrappers[i].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
                target_height = (active_timers * 75) + ((active_timers - 1) * 5) + 12
                self.setMinimumSize(0, 0); self.setMaximumSize(16777215, 16777215)
                self.setFixedSize(280, target_height) 
                self.move(screen.width() + screen.x() - self.width() - 20, screen.height() + screen.y() - self.height() - 20)
            else:
                self.update_mini_mode_layout()
            self.show()
            self.toggle_switch.setChecked(True)
        else:
            # [대시보드 복구] 실행 시작 당시의 정상 창 플래그 및 스타일 완벽 복원
            self.setWindowFlags(self.normal_window_flags)
            self.setStyleSheet("""
                QWidget { 
                    background-color: #FDF9F3; 
                    color: #3E3832; 
                    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; 
                }
            """)
            
            self.image_label.setMinimumSize(540, 310)
            self.main_layout.setContentsMargins(15, 15, 15, 15); self.main_layout.setSpacing(20)
            self.content_layout.setContentsMargins(0, 0, 0, 0); self.content_layout.setSpacing(15)
            self.middle_layout.setContentsMargins(0, 0, 0, 0); self.middle_layout.setSpacing(15)
            
            # 대시보드 모드로 돌아올 때 타이머 여백 넉넉하게 원복
            self.timer_layout.setContentsMargins(15, 15, 15, 15)
            self.timer_layout.setSpacing(10)
            
            # 일반 대시보드 모드로 돌아올 때 창 크기 고정 해제 및 원복
            self.setMinimumSize(1150, 750); self.setMaximumSize(16777215, 16777215); self.resize(1150, 750)
            self.move(screen.x() + (screen.width() - 1150) // 2, screen.y() + (screen.height() - 750) // 2)
            #sidebar 없는데 불러오려 해서오류나서 지움
            self.cam_frame.show(); self.status_frame.show(); self.control_frame.show(); self.header_frame.show(); self.t_header_frame.show()
            self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
            
            for i, w in enumerate(self.pot_wrappers):
                w.show()
                w.setStyleSheet("background-color: #FFFDF9; border: 2px solid #8C6D53; border-radius: 16px;" if self.selected_pot == (i + 1) else "background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
            
            self.show(); self.raise_(); self.activateWindow(); self.is_mini_mode = False ##대시보드로 돌아 올때 제스처 조작 락 해제!
            self.gesture_controller.is_mini_mode=False
            self.toggle_switch.setChecked(False)

    def mouseDoubleClickEvent(self, event):
        """미니모드 창을 더블클릭했을 때 대시보드로 즉시 복구해주는 이벤트 핸들러"""
        if self.is_mini_mode and event.button() == Qt.LeftButton:
            self.on_snap_swipe()
            event.accept()

    # ==========================================
    # 연기 감지 핸들러
    # ==========================================
    def on_smoke_detected(self, conf: float):
        # print(f"[SMOKE] 연기 감지! 신뢰도: {conf:.0%}")
        self._play_alarm()
        self._alarm_timer.start()

        #화재 알림 팝업창#

        if not self.smoke_dialog or not self.smoke_dialog.isVisible():

            self.smoke_dialog.setWindowTitle("화재 주의 경고")
            self.smoke_dialog.setFixedSize(520, 260)
            self.smoke_dialog.setStyleSheet("background-color: #FDF9F3; border-radius: 16px;")
            
            dialog_layout = QVBoxLayout(self.smoke_dialog)
            dialog_layout.setContentsMargins(25, 25, 25, 25)
            
            lbl_warn = QLabel("⚠️\n\n연기가 감지되었습니다!\n화재 위험이 감지되었습니다. 환기를 권장합니다.")
            lbl_warn.setAlignment(Qt.AlignCenter)
            lbl_warn.setStyleSheet("font-size: 15px; font-weight: bold; color: #B23B3B; border: none;")
            dialog_layout.addWidget(lbl_warn)
            
            btn_layout = QHBoxLayout()
            
            btn_alarm_off = QPushButton("경보 끄기")
            btn_alarm_off.setIcon(self.get_icon("bell.png"))
            btn_alarm_off.setFixedHeight(45)
            btn_alarm_off.setStyleSheet("background-color: #FFFFFF; border: 1px solid #F5CDCD; color: #B23B3B; font-weight: bold; border-radius: 12px;")
            btn_alarm_off.clicked.connect(lambda: [self._alarm_timer.stop(), self.btn_alert_off.setText(" 경보 꺼짐")])
            
            btn_confirm = QPushButton("확인")
            btn_confirm.setFixedHeight(45)
            btn_confirm.setStyleSheet("background-color: #3E3832; color: white; font-weight: bold; border-radius: 12px;")
            btn_confirm.clicked.connect(self.smoke_dialog.close)
            
            btn_layout.addWidget(btn_alarm_off)
            btn_layout.addWidget(btn_confirm)
            dialog_layout.addLayout(btn_layout)
            
            self.smoke_dialog.exec()

    def on_smoke_cleared(self):
        # print("[SMOKE] 연기 사라짐 — 경고 해제")
        self._alarm_timer.stop()
        # 🟢 연기가 사라지면 팝업도 자동으로 닫기
        if self.smoke_dialog and self.smoke_dialog.isVisible():
            self.smoke_dialog.close()

    def _play_alarm(self):
        """별도 스레드에서 경고음 재생 (UI 블로킹 방지)"""
        def _beep():
            for _ in range(3):
                winsound.Beep(1000, 300)
        threading.Thread(target=_beep, daemon=True).start()

    def start_webcam(self):
        """웹캠 비디오 스트리밍을 시작하는 메서드"""
        if self.cap is None or not self.cap.isOpened(): 
            #변수 값을 가져와서 비디오 열기!!!
            self.cap = cv2.VideoCapture(self.video_source)
            print(f"[KitchenApp] 비디오 소스 열기 성공: {self.video_source}")
        if not self.timer.isActive(): 
            self.timer.start(30)

    def update_frame(self):
        """매 프레임마다 웹캠 프레임을 읽어와 제스처를 인식하고 UI에 렌더링하는 메서드"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                try:
                    frame, gestures = self.gesture_controller.process(frame)
                    if gestures: 
                        current_gesture = gestures[0]["gesture"].upper()
                        self.lbl_gesture.setText(current_gesture)
                        
                        # 인식된 제스처에 따라 LIVE 상태등 색상 동적 변경 (노랑/빨강)
                        if current_gesture in ["THUMBSUP", "OK", "FIST", "FIVE"]:
                            self.cam_live.setStyleSheet("background-color: #1A1A1A; color: #E2B714; border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
                        else:
                            self.cam_live.setStyleSheet("background-color: #1A1A1A; color: #D9534F; border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
                        
                        # 스냅 보강 (숫자 제스처 인식 시 해당 화구 포커스 연동)
                    if gestures and self.gesture_controller.input_mode=='POT_SELECT': #오작동 방지를 위해 화구 선택 모드일때만 작동하도록함
                        #손이 비어 있는지 아닌지 검사후 넘어감!!!
                        gesture_name = gestures[0]["gesture"]
                        if gesture_name == "one":
                            self.select_burner(1)
                        elif gesture_name == "two":
                            self.select_burner(2)
                        elif gesture_name == "three":
                            self.select_burner(3)
                        elif gesture_name == "four":
                            self.select_burner(4)
                    else:
                        self.cam_live.setStyleSheet("background-color: #1A1A1A; color: #A69B91; border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
                except Exception as e: 
                    print(f"[KitchenApp] 제스처 처리 중 오류 발생: {e}")
                    import traceback  #에러 추론 위해 추가!!!
                    traceback.print_exc

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
                        # 🟢 연기가 감지되었을 때 경고음과 팝업 창을 띄우는 함수 호출!
                        self.on_smoke_detected(conf)
                    else:
                        self.lbl_smoke.setText("Smoke: ✔️ Safe")
                        self.lbl_smoke.setStyleSheet("")
                        # 🟢 연기가 사라졌을 때 팝업 창과 알람을 해제하는 함수 호출!
                        self.on_smoke_cleared()

                # 렌더링 처리
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
        """애플리케이션 종료 시 웹캠 자원 및 타이머를 안전하게 해제하는 메서드"""
        if hasattr(self, 'timer'): 
            self.timer.stop()
        if hasattr(self, '_alarm_timer'):
            self._alarm_timer.stop()
        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KitchenApp()
    window.show()
    sys.exit(app.exec())