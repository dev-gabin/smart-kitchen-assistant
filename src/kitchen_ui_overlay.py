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
from src.burner import SmokeDetector, draw_smoke_boxes, detect_pans, PanTracker, draw_pans

class KitchenApp(QWidget):
    def __init__(self):
        super().__init__()

        self.smoke_dialog = QDialog(self)
        # self.video_source=0 #모드 설정
        self.video_source="data/pots.mp4"
        # 웹캠 및 제스처 컨트롤러 초기화
        self.cap = None
        self.gesture_controller = GestureController()
        
        # 제스처 스와이프 시그널 연결 (위젯 모드 토글 연동)
        self.gesture_controller.swipe_detected.connect(self.on_snap_swipe)

        # 2) SmokeDetector 생성 및 시그널 연결
        # YOLO 모델 로딩이 무거워서(수 초 소요) __init__에서 바로 만들면 창이 뜨기도 전에 멈춰버림.
        # 창이 먼저 보이도록 이벤트 루프가 돌기 시작한 직후(0ms 뒤)로 로딩을 미룸.
        self.smoke_detector = None
        QTimer.singleShot(0, self._init_smoke_detector)

        # 경고음 반복 타이머 (2초 간격)
        self._alarm_timer = QTimer(self)
        self._alarm_timer.setInterval(2000)
        self._alarm_timer.timeout.connect(self._play_alarm)

        self._smoke_frame_count = 0
        self._smoke_box_cache = []
        self.somoke_dialog=None #팝업창 변수

        # 화구 위 팬 감지 캐시 (5프레임마다 한 번만 다시 탐지하고, 그 사이엔 캐시된 결과를 그림)
        self._pan_tracker = PanTracker()
        self._pan_cache = []
        self._pan_detect_interval = 5
        self._pan_frame_count = 0


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

        
        widget_layout.addWidget(self.btn_widget)
        header_layout.addLayout(widget_layout)
        header_layout.addSpacing(15)

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
        cam_icon_lbl.setStyleSheet("border: none; background: transparent;")
        
        cam_title = QLabel(" 카메라 뷰")
        cam_title.setStyleSheet("font-size: 15px; font-weight: 800; border: none;")
        
        cam_header_left = QHBoxLayout()
        cam_header_left.setSpacing(5)
        cam_header_left.addWidget(cam_icon_lbl)
        cam_header_left.addWidget(cam_title)
        
        cam_header.addLayout(cam_header_left)
        cam_header.addStretch()
        
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
        self.control_frame.setStyleSheet("background-color: transparent; border: none;")
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
        self.gesture_controller.pot_deselected_signal.connect(self.deselect_burner)
        self.gesture_controller.timer_pause_signal.connect(self.pause_selected_timer)
        self.gesture_controller.timer_reset_signal.connect(self.reset_selected_timer)
        self.gesture_controller.timer_pause_all_signal.connect(self.pause_all_timers)
        self.gesture_controller.timer_reset_all_signal.connect(self.reset_all_timers)
        self.gesture_controller.timer_add_time_signal.connect(self.add_time_to_selected_pot)
        self.gesture_controller.timer_adjust_seconds_signal.connect(self.adjust_selected_pot_seconds)
        self.gesture_controller.timer_auto_start_signal.connect(self.start_selected_timer_if_ready)
        self.gesture_controller.timer_confirm_signal.connect(self.confirm_pot_setting)

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

    def deselect_burner(self):
        """화면에 화구 선택 제스처(1~4)가 없어서 선택이 풀렸을 때, 대시보드의 선택 표시를 초기화하는 메서드"""
        self.selected_pot = None
        self.lbl_selected.setText("-")
        if not self.is_mini_mode:
            for w in self.pot_wrappers:
                w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")

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

    def adjust_selected_pot_seconds(self, seconds: int):
        """선택된 화구의 타이머를 초 단위로 증감하는 메서드 (제스처 5=+10초 유지, 주먹=-10초 유지)"""
        if self.selected_pot is None:
            return

        idx = self.selected_pot - 1
        self.pot_times[idx] = max(0, self.pot_times[idx] + seconds)
        self.refresh_pot_label(idx)
        self.lbl_selected.setText(f"0{self.selected_pot} [{self.pot_times[idx]//60}분 {self.pot_times[idx]%60}초 설정됨]")

    def start_selected_timer_if_ready(self):
        """시간 설정 후 손이 화면에서 사라졌을 때, 선택된 화구가 대기/정지 중이고 시간이 설정돼 있으면 자동으로 시작시키는 메서드"""
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            if self.pot_states[idx] in ["대기", "정지"] and self.pot_times[idx] > 0:
                self.pot_states[idx] = "실행"
                self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #EAE0D5; border-radius: 16px; border: none;")
                self.lbl_selected.setText(f"0{self.selected_pot} [자동 시작됨]")

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

    def _force_to_front(self):
        """
        다른 창(브라우저 등)이 OS 포그라운드를 쥐고 있으면 raise_()/activateWindow()가
        내부적으로 쓰는 SetForegroundWindow가 Windows에 의해 막혀서 조용히 실패함.
        WindowStaysOnTopHint를 잠깐 켰다 끄면 SetWindowPos(HWND_TOPMOST)가 호출되는데,
        이건 포그라운드 권한 없이도 항상 허용되므로 이 방법으로 강제로 맨 위로 끌어올림.
        """
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

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
            self.raise_()
            self.activateWindow()
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
            
            self._force_to_front()
            self.is_mini_mode = False ##대시보드로 돌아 올때 제스처 조작 락 해제!
            self.gesture_controller.is_mini_mode=False

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

    def _init_smoke_detector(self):
        """무거운 YOLO 모델 로딩을 창이 뜬 뒤로 미루는 지연 초기화 메서드 (시작 시 멈춤 방지용)"""
        self.smoke_detector = SmokeDetector()
        self.smoke_detector.smoke_detected.connect(self.on_smoke_detected)
        self.smoke_detector.smoke_cleared.connect(self.on_smoke_cleared)

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
                except Exception as e:
                    print(f"[KitchenApp] 제스처 처리 중 오류 발생: {e}")
                    import traceback  #에러 추론 위해 추가!!!
                    traceback.print_exc

                # 화구 위 프라이팬/조리도구 가장자리 감지 및 붉은색 표시
                # (5프레임마다만 다시 탐지 + 최근 감지 이력으로 확인된 것만 그려서 오탐 억제)
                try:
                    self._pan_frame_count += 1
                    if self._pan_frame_count % self._pan_detect_interval == 0:
                        raw_pans = detect_pans(frame)
                        self._pan_cache = self._pan_tracker.update(raw_pans)
                    frame = draw_pans(frame, self._pan_cache)
                except Exception as e:
                    print(f"[KitchenApp] 화구/팬 감지 중 오류 발생: {e}")

                self._smoke_frame_count += 1
                if self.smoke_detector is not None and self._smoke_frame_count % 5 == 0:
                    is_smoke, conf, self._smoke_box_cache = self.smoke_detector.detect(frame)
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
                frame = draw_smoke_boxes(frame, self._smoke_box_cache)

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