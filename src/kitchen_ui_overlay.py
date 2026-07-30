import sys
import os
import cv2
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame, QScrollArea
)
from src.gesture.controller import GestureController

class kitchen_App(QWidget):
    def __init__(self):
        super().__init__()
        
        self.cap = None
        self.gesture_controller = GestureController()
        
        # 스와이프 시그널 연결 (위젯 모드 토글)
        self.gesture_controller.swipe_detected.connect(self.on_snap_swipe)
        self.is_mini_mode = False
        self.normal_window_flags = self.windowFlags()  # 정상 모드 원래 창 플래그 보관

        # 웹캠 프레임 갱신용 타이머
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        self.init_UI()
        self.start_webcam()

    def get_icon(self, filename):
        path = os.path.join("img", filename)
        return QIcon(path) if os.path.exists(path) else QIcon()

    def init_UI(self):
        self.setWindowTitle("Smart Kitchen Assistant")
        self.resize(1150, 750) 
        self.setMinimumSize(0, 0)
        
        # 💛 따뜻하고 노란끼 감도는 바닐라 크림 테마 스타일 적용
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
        # [좌측] 사이드바 영역
        # ----------------------------------------------------
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(85)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(10)
        
        logo_label = QLabel()
        logo_pixmap = QPixmap("img/01_chef_hat.png")
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo_label)
        sidebar_layout.addSpacing(15)

        btn_style = """
            QPushButton { background: transparent; border: none; font-size: 11px; color: #786C61; padding: 12px 0px; font-weight: bold; border-radius: 12px; }
            QPushButton:hover { background-color: #F3EFEA; }
        """
        active_btn_style = """
            QPushButton { background-color: #F4EBE1; border: 1px solid #E5D8CC; border-radius: 12px; font-size: 11px; color: #3E3832; padding: 12px 0px; font-weight: bold; }
        """
        
        self.btn_home = QPushButton("대시보드"); self.btn_home.setIcon(self.get_icon("02_home.png"))
        self.btn_timer = QPushButton("타이머"); self.btn_timer.setIcon(self.get_icon("03_clock_1.png"))
        self.btn_gesture = QPushButton("제스처"); self.btn_gesture.setIcon(self.get_icon("06_hand_gesture.png"))
        self.btn_env = QPushButton("환경 상태"); self.btn_env.setIcon(self.get_icon("07_leaf.png"))
        self.btn_setting = QPushButton("설정"); self.btn_setting.setIcon(self.get_icon("08_settings.png"))

        self.btn_home.setStyleSheet(active_btn_style)
        for btn in [self.btn_home, self.btn_timer, self.btn_gesture, self.btn_env, self.btn_setting]:
            btn.setIconSize(QSize(24, 24))
            btn.setFixedHeight(75)
            sidebar_layout.addWidget(btn)
        
        self.sidebar_buttons = [self.btn_home, self.btn_timer, self.btn_gesture, self.btn_env, self.btn_setting]
        self.current_sidebar_index = 0

        # 사이드바 버튼 마우스 클릭 시그널 연결
        self.btn_home.clicked.connect(lambda: self.set_sidebar_focus(0))
        self.btn_timer.clicked.connect(lambda: self.set_sidebar_focus(1))
        self.btn_gesture.clicked.connect(lambda: self.set_sidebar_focus(2))
        self.btn_env.clicked.connect(lambda: self.set_sidebar_focus(3))
        self.btn_setting.clicked.connect(lambda: self.set_sidebar_focus(4))
        
        sidebar_layout.addStretch()

        # 사이드바 하단 위젯 모드 전환부 (아이콘 + 텍스트 + 토글 스위치)
        self.widget_container = QFrame()
        self.widget_container.setStyleSheet("background: transparent; border: none;")
        widget_layout = QVBoxLayout(self.widget_container)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widget_layout.setSpacing(6)

        self.btn_widget = QPushButton("Widget 모드")
        self.btn_widget.setIcon(self.get_icon("23_fullscreen.png"))
        self.btn_widget.setIconSize(QSize(22, 22))
        self.btn_widget.setStyleSheet(btn_style)
        self.btn_widget.setFixedHeight(45)
        self.btn_widget.clicked.connect(self.on_snap_swipe)

        self.toggle_switch = QPushButton()
        self.toggle_switch.setFixedSize(46, 24)
        self.toggle_switch.setCheckable(True)
        self.toggle_switch.setStyleSheet("""
            QPushButton {
                background-color: #E2D6CB;
                border: none;
                border-radius: 12px;
            }
            QPushButton:checked {
                background-color: #8C6D53;
            }
        """)
        self.toggle_switch.clicked.connect(self.on_snap_swipe)

        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(12, 0, 12, 0)
        toggle_layout.addStretch()
        toggle_layout.addWidget(self.toggle_switch)
        toggle_layout.addStretch()

        widget_layout.addWidget(self.btn_widget)
        widget_layout.addLayout(toggle_layout)
        sidebar_layout.addWidget(self.widget_container)

        self.main_layout.addWidget(self.sidebar)

        # ----------------------------------------------------
        # [우측] 메인 콘텐츠 영역
        # ----------------------------------------------------
        self.content_frame = QFrame()
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(15)

        # 상단 헤더
        self.header_frame = QFrame()
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_title = QLabel("Smart Kitchen")
        title_title.setStyleSheet("font-size: 24px; font-weight: 900; color: #3E3832; background: transparent;")
        title_sub = QLabel("Assistant    ✨ 주방 안전 모드")
        title_sub.setStyleSheet("font-size: 12px; color: #8C6D53; font-weight: bold; background: transparent;")
        title_box.addWidget(title_title)
        title_box.addWidget(title_sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        
        for icon_file in ["08_settings.png", "24_brightness.png", "23_fullscreen.png"]:
            btn = QPushButton()
            btn.setIcon(self.get_icon(icon_file))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(45, 45)
            btn.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 12px;")
            header_layout.addWidget(btn)
            
        self.content_layout.addWidget(self.header_frame)

        # 중단 (카메라 + 타이머 리스트)
        self.middle_layout = QHBoxLayout()
        self.middle_layout.setSpacing(15)

        # 1. 카메라 뷰 카드
        self.cam_frame = QFrame()
        self.cam_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
        cam_layout = QVBoxLayout(self.cam_frame)
        cam_layout.setContentsMargins(15, 15, 15, 15)
        
        cam_header = QHBoxLayout()
        cam_title = QLabel("📹 카메라 뷰")
        cam_title.setStyleSheet("font-size: 15px; font-weight: 800; border: none;")
        cam_live = QLabel("🔴 LIVE")
        cam_live.setStyleSheet("background-color: #594A42; color: white; border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        cam_live.setAlignment(Qt.AlignCenter)
        cam_header.addWidget(cam_title)
        cam_header.addStretch()
        cam_header.addWidget(cam_live)
        
        self.image_label = QLabel("웹캠 연결 중...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(500, 340)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        # 카메라 양옆 레터박스 다크 모던 톤(#1A1A1A) 적용
        self.image_label.setStyleSheet("background-color: #1A1A1A; border-radius: 14px;")
        
        cam_layout.addLayout(cam_header)
        cam_layout.addSpacing(10)
        cam_layout.addWidget(self.image_label, stretch=1)
        self.middle_layout.addWidget(self.cam_frame, stretch=6)

        # 2. 타이머 리스트 카드
        self.timer_frame = QFrame()
        self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
        self.timer_layout = QVBoxLayout(self.timer_frame)
        self.timer_layout.setContentsMargins(15, 15, 15, 15)
        self.timer_layout.setSpacing(10)
        
        self.t_header_frame = QFrame()
        self.t_header_frame.setStyleSheet("background: transparent; border: none;")
        t_header = QHBoxLayout(self.t_header_frame)
        t_header.setContentsMargins(0,0,0,0)
        
        self.lbl_t_title = QLabel("⏱️ 타이머")
        self.lbl_t_title.setStyleSheet("font-size: 15px; font-weight: 800; border: none;")
        self.btn_t_add = QPushButton()
        self.btn_t_add.setIcon(self.get_icon("20_plus.png"))
        self.btn_t_add.setStyleSheet("background: transparent; border: none;")
        
        t_header.addWidget(self.lbl_t_title)
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
        self.middle_layout.addWidget(self.timer_frame, stretch=4)
        self.content_layout.addLayout(self.middle_layout, stretch=1)

        # 하단 상태 표시바
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

        # 최하단 전체 컨트롤 버튼
        self.control_frame = QFrame()
        self.control_frame.setFixedHeight(55)
        control_layout = QHBoxLayout(self.control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(12)
        
        btn_base = "background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 14px; font-size: 14px; font-weight: 800; color: #594A42;"
        
        self.btn_pause = QPushButton(" 전체 정지"); self.btn_pause.setIcon(self.get_icon("22_pause.png"))
        self.btn_pause.setStyleSheet(btn_base)
        
        self.btn_reset = QPushButton(" 전체 초기화"); self.btn_reset.setIcon(self.get_icon("25_refresh.png"))
        self.btn_reset.setStyleSheet(btn_base)
        
        self.btn_alert_off = QPushButton(" 경보 끄기"); self.btn_alert_off.setIcon(self.get_icon("19_muted_bell.png"))
        self.btn_alert_off.setStyleSheet("background-color: #FDF2F2; border: 1px solid #F5CDCD; border-radius: 14px; font-size: 14px; font-weight: 800; color: #B23B3B;")
        
        self.btn_pause.clicked.connect(self.pause_all_timers)
        self.btn_reset.clicked.connect(self.reset_all_timers)

        for b in [self.btn_pause, self.btn_reset, self.btn_alert_off]:
            b.setIconSize(QSize(18, 18))

        self.lbl_fps = QLabel("FPS\n60")
        self.lbl_fps.setAlignment(Qt.AlignCenter)
        self.lbl_fps.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 14px; font-size: 11px; font-weight: bold; color: #888;")
        
        control_layout.addWidget(self.btn_pause, stretch=1)
        control_layout.addWidget(self.btn_reset, stretch=1)
        control_layout.addWidget(self.btn_alert_off, stretch=1)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.lbl_fps)

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

        # 컨트롤러 제스처 시그널 바인딩
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
        """개별 타이머 카드 위젯 생성 함수 (아이콘 테두리 제거 및 40x40 큼직한 크기 정돈)"""
        wrapper = QFrame()
        wrapper.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
        wrapper.setFixedHeight(75)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(15, 0, 15, 0)
        
        lbl_num = QLabel(num)
        lbl_num.setStyleSheet("font-size: 14px; font-weight: bold; color: #3E3832; border: none;")
        
        lbl_icon = QLabel()
        lbl_icon.setStyleSheet("border: none; background: transparent;")
        pixmap = QPixmap(os.path.join("img", icon_file))
        if not pixmap.isNull():
            lbl_icon.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("font-size: 13px; color: #786C61; font-weight: bold; border: none;")
        
        time_lbl.setStyleSheet("font-size: 18px; font-weight: 900; color: #3E3832; border: none;")
        
        btn_play = QPushButton()
        btn_play.setIcon(self.get_icon("21_play.png"))
        btn_play.setIconSize(QSize(14, 14))
        btn_play.setFixedSize(30, 30)
        btn_play.setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")
        
        self.timer_buttons.append(btn_play)
        
        layout.addWidget(lbl_num)
        layout.addSpacing(16)
        layout.addWidget(lbl_icon)
        layout.addSpacing(12)
        layout.addWidget(lbl_name)
        layout.addStretch()
        layout.addWidget(time_lbl)
        layout.addSpacing(12)
        layout.addWidget(btn_play)
        
        return wrapper, btn_play

    def create_status_item(self, icon_file, title, val_lbl, sub, dot_color):
        widget = QFrame()
        widget.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 15, 20, 15)
        
        icon_lbl = QLabel()
        pixmap = QPixmap(os.path.join("img", icon_file))
        if not pixmap.isNull():
            icon_lbl.setPixmap(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_lbl.setFixedSize(45, 45)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background-color: #F4EBE1; border-radius: 22px;")
        
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
        self.is_long_time_mode = not self.is_long_time_mode
        mode_str = "장시간 모드" if self.is_long_time_mode else "기본 모드"
        if self.selected_pot:
            self.lbl_selected.setText(f"0{self.selected_pot} [{mode_str}]")
        else:
            self.lbl_selected.setText(f"모드: {mode_str}")

    def select_burner(self, num):
        self.selected_pot = num
        if not self.is_mini_mode:
            for i, w in enumerate(self.pot_wrappers):
                if (i + 1) == num:
                    w.setStyleSheet("background-color: #FFFDF9; border: 2px solid #8C6D53; border-radius: 16px;")
                else:
                    w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
        
        self.lbl_selected.setText(f"0{num} [시간 설정 중]")

    def add_time_to_selected_pot(self, base_mins: int):
        if self.selected_pot is None:
            return
        
        idx = self.selected_pot - 1
        multiplier = 10 if self.is_long_time_mode else 1
        add_mins = base_mins * multiplier
        
        self.pot_times[idx] += add_mins * 60  
        self.refresh_pot_label(idx)
        self.lbl_selected.setText(f"0{self.selected_pot} [{self.pot_times[idx]//60}분 설정됨]")

    def confirm_pot_setting(self):
        if self.selected_pot is not None:
            self.lbl_selected.setText(f"0{self.selected_pot} [세팅 완료 / 조작 가능]")

    def pause_selected_timer(self):
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            if self.pot_states[idx] == "실행":
                self.pot_states[idx] = "정지"
                self.timer_buttons[idx].setIcon(self.get_icon("21_play.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")
                self.lbl_selected.setText(f"0{self.selected_pot} [일시 정지됨]")
            elif self.pot_states[idx] == "정지" and self.pot_times[idx] > 0:
                self.pot_states[idx] = "실행"
                self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #EAE0D5; border-radius: 15px; border: none;")
                self.lbl_selected.setText(f"0{self.selected_pot} [재시작 됨]")

    def reset_selected_timer(self):
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            self.pot_times[idx] = 0
            self.pot_states[idx] = "대기"
            self.refresh_pot_label(idx)
            self.timer_buttons[idx].setIcon(self.get_icon("21_play.png"))
            self.timer_buttons[idx].setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")
            self.lbl_selected.setText(f"0{self.selected_pot} [초기화 됨]")

    def smart_start_timers(self):
        ready_indices = [i for i in range(4) if self.pot_times[i] > 0 and self.pot_states[i] in ["대기", "정지"]]
        running_indices = [i for i in range(4) if self.pot_states[i] == "실행"]
        
        if running_indices:
            for i in running_indices:
                self.pot_states[i] = "정지"
                self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")
        elif len(ready_indices) == 1:
            idx = ready_indices[0]
            self.pot_states[idx] = "실행"
            self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
            self.timer_buttons[idx].setStyleSheet("background-color: #EAE0D5; border-radius: 15px; border: none;")
        elif len(ready_indices) > 1:
            for idx in ready_indices:
                self.pot_states[idx] = "실행"
                self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
                self.timer_buttons[idx].setStyleSheet("background-color: #EAE0D5; border-radius: 15px; border: none;")
        
        if self.selected_pot:
            self.lbl_selected.setText(f"0{self.selected_pot} [스마트 제어됨]")

    def pause_all_timers(self):
        any_running = any(state == "실행" for state in self.pot_states)
        if any_running:
            for i in range(4):
                if self.pot_states[i] == "실행":
                    self.pot_states[i] = "정지"
                    self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")
            self.btn_pause.setText(" 전체 재생")
            self.btn_pause.setIcon(self.get_icon("21_play.png"))
        else:
            for i in range(4):
                if self.pot_states[i] == "정지" and self.pot_times[i] > 0:
                    self.pot_states[i] = "실행"
                    self.timer_buttons[i].setIcon(self.get_icon("22_pause.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #EAE0D5; border-radius: 15px; border: none;")
            self.btn_pause.setText(" 전체 정지")
            self.btn_pause.setIcon(self.get_icon("22_pause.png"))

    def reset_all_timers(self):
        for i in range(4):
            self.pot_times[i] = 0
            self.pot_states[i] = "대기"
            self.refresh_pot_label(i)
            self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
            self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")
        
        self.btn_pause.setText(" 전체 정지")
        self.btn_pause.setIcon(self.get_icon("22_pause.png"))
        
        self.selected_pot = None
        self.lbl_selected.setText("-")
        for w in self.pot_wrappers:
            w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")

    def set_sidebar_focus(self, idx: int):
        normal_style = """
            QPushButton { background: transparent; border: none; font-size: 11px; color: #786C61; padding: 12px 0px; font-weight: bold; border-radius: 12px; }
            QPushButton:hover { background-color: #F3EFEA; }
        """
        active_btn_style = """
            QPushButton { background-color: #F4EBE1; border: 1px solid #E5D8CC; border-radius: 12px; font-size: 11px; color: #3E3832; padding: 12px 0px; font-weight: bold; }
        """

        self.sidebar_buttons[self.current_sidebar_index].setStyleSheet(normal_style)
        self.current_sidebar_index = idx
        self.sidebar_buttons[self.current_sidebar_index].setStyleSheet(active_btn_style)

        # 3번 메뉴(제스처): 팝업창 토글 켜기/끄기
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
        for i in range(4):
            if self.pot_states[i] == "실행" and self.pot_times[i] > 0:
                self.pot_times[i] -= 1
                self.refresh_pot_label(i)
                if self.pot_times[i] == 0:
                    self.pot_states[i] = "대기"
                    self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #D5BDAF; border-radius: 15px; border: none;")

    def refresh_pot_label(self, idx):
        t = self.pot_times[idx]
        self.pot_labels[idx].setText(f"{t//60:02d}:{t%60:02d}" if t > 0 else "--:--")

    def on_snap_swipe(self):
        """전체 화면 ↔ 우측 하단 고정 미니 위젯 모드 전환 함수 (검은 테두리 버그 완전 해결)"""
        screen = self.screen().geometry()
        self.hide()
        
        if not self.is_mini_mode:
            # [미니모드 진입]
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

            self.sidebar.hide(); self.cam_frame.hide(); self.status_frame.hide(); self.control_frame.hide(); self.header_frame.hide(); self.t_header_frame.hide()
            self.image_label.setMinimumSize(0, 0)
            self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
            self.content_layout.setContentsMargins(0, 0, 0, 0); self.content_layout.setSpacing(0)
            self.middle_layout.setSpacing(0); self.timer_layout.setContentsMargins(0, 0, 0, 0); self.timer_layout.setSpacing(0)
            
            self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1.5px solid #EAE0D5; border-radius: 20px;")
            
            active_timers = 0
            for i in range(4):
                if self.pot_times[i] > 0:
                    self.pot_wrappers[i].show()
                    self.pot_wrappers[i].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
                    active_timers += 1
                else: 
                    self.pot_wrappers[i].hide()
            
            if active_timers == 0:
                self.pot_wrappers[0].show()
                self.pot_wrappers[0].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
                target_height = 95
            else: 
                target_height = (active_timers * 75) + 20
            
            self.setMinimumSize(0, 0); self.setFixedSize(280, target_height)
            self.move(screen.width() + screen.x() - self.width() - 20, screen.height() + screen.y() - self.height() - 20)
            self.show(); self.is_mini_mode = True
            self.toggle_switch.setChecked(True)
        else:
            # 🔥 [대시보드 복구 시 검은 테두리/오류 완벽 차단 리셋]
            self.setWindowFlags(self.normal_window_flags)  # 실행 시작 당시 정상 창 모양 그대로 복원
            self.setStyleSheet("""
                QWidget { 
                    background-color: #FDF9F3; 
                    color: #3E3832; 
                    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; 
                }
            """)
            
            self.image_label.setMinimumSize(500, 340)
            self.main_layout.setContentsMargins(15, 15, 15, 15); self.main_layout.setSpacing(20)
            self.content_layout.setContentsMargins(0, 0, 0, 0); self.content_layout.setSpacing(15)
            self.middle_layout.setSpacing(15); self.timer_layout.setContentsMargins(15, 15, 15, 15); self.timer_layout.setSpacing(10)
            self.setMinimumSize(1150, 750); self.setMaximumSize(16777215, 16777215); self.resize(1150, 750)
            self.move(screen.x() + (screen.width() - 1150) // 2, screen.y() + (screen.height() - 750) // 2)
            self.sidebar.show(); self.cam_frame.show(); self.status_frame.show(); self.control_frame.show(); self.header_frame.show(); self.t_header_frame.show()
            self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 20px;")
            
            for i, w in enumerate(self.pot_wrappers):
                w.show()
                w.setStyleSheet("background-color: #FFFDF9; border: 2px solid #8C6D53; border-radius: 16px;" if self.selected_pot == (i + 1) else "background-color: #FFFFFF; border: 1px solid #EAE0D5; border-radius: 16px;")
            
            self.show(); self.raise_(); self.activateWindow(); self.is_mini_mode = False
            self.toggle_switch.setChecked(False)

    # 미니모드 복구 백업 (더블클릭)
    def mouseDoubleClickEvent(self, event):
        if self.is_mini_mode and event.button() == Qt.LeftButton:
            self.on_snap_swipe()
            event.accept()

    def start_webcam(self):
        """웹캠 비디오 스트리밍 시작 함수"""
        if self.cap is None or not self.cap.isOpened(): 
            self.cap = cv2.VideoCapture(0)
        if not self.timer.isActive(): 
            self.timer.start(30)

    def update_frame(self):
        """매 프레임마다 웹캠 이미지를 읽어와 제스처를 처리하고 UI에 렌더링하는 함수"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                try:
                    frame, gestures = self.gesture_controller.process(frame)
                    if gestures: 
                        self.lbl_gesture.setText(gestures[0]["gesture"].upper())
                except Exception: 
                    pass
                
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                self.image_label.setPixmap(QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)).scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, event):
        """앱 종료 시 웹캠 및 타이머 자원 해제"""
        if hasattr(self, 'timer'): 
            self.timer.stop()
        if self.cap and self.cap.isOpened(): 
            self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = kitchen_App()
    window.show()
    sys.exit(app.exec())