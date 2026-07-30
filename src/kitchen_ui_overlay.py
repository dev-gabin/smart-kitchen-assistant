import sys
import os
import cv2
import pyautogui
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame
)
# 제스처 컨트롤러 모듈 (에러 안 나도록 정확하게 유지)
from src.gesture import GestureController

class kitchen_App(QWidget):
    def __init__(self):
        super().__init__()
        
        self.cap = None
        self.gesture_controller = GestureController()
        self.gesture_controller.swipe_detected.connect(self.on_snap_swipe)
        self.is_mini_mode = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        # UI 셋업 및 웹캠 시작
        self.init_UI()
        self.start_webcam()

    def get_icon(self, filename):
        """img 폴더에서 다운로드하신 아이콘을 불러오는 함수"""
        path = os.path.join("img", filename)
        return QIcon(path) if os.path.exists(path) else QIcon()

    def init_UI(self):
        self.setWindowTitle("Smart Kitchen Assistant")
        self.resize(1150, 750) 
        self.setMinimumSize(0, 0)
        
        self.setStyleSheet("""
            QWidget { 
                background-color: #FDFCF9; 
                color: #222222; 
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
            QPushButton { background: transparent; border: none; font-size: 11px; color: #555; padding: 12px 0px; font-weight: bold; border-radius: 12px; }
            QPushButton:hover { background-color: #F0EBE1; }
        """
        active_btn_style = """
            QPushButton { background-color: #FFF4E6; border: 1px solid #FDE0C5; border-radius: 12px; font-size: 11px; color: #333; padding: 12px 0px; font-weight: bold; }
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
        
        sidebar_layout.addStretch()

        self.btn_widget = QPushButton("Widget")
        self.btn_widget.setIcon(self.get_icon("23_fullscreen.png"))
        self.btn_widget.setIconSize(QSize(24, 24))
        self.btn_widget.setStyleSheet(btn_style)
        self.btn_widget.setFixedHeight(75)
        self.btn_widget.clicked.connect(self.on_snap_swipe)
        sidebar_layout.addWidget(self.btn_widget)

        self.main_layout.addWidget(self.sidebar)

        # ----------------------------------------------------
        # [우측] 메인 콘텐츠 영역
        # ----------------------------------------------------
        self.content_frame = QFrame()
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(15)

        # --- 상단 헤더 ---
        self.header_frame = QFrame()
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_title = QLabel("Smart Kitchen")
        title_title.setStyleSheet("font-size: 24px; font-weight: 900; color: #111; background: transparent;")
        title_sub = QLabel("Assistant    ✨ 주방 안전 모드")
        title_sub.setStyleSheet("font-size: 12px; color: #D35400; font-weight: bold; background: transparent;")
        title_box.addWidget(title_title)
        title_box.addWidget(title_sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        
        for icon_file in ["08_settings.png", "24_brightness.png", "23_fullscreen.png"]:
            btn = QPushButton()
            btn.setIcon(self.get_icon(icon_file))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(45, 45)
            btn.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 12px;")
            header_layout.addWidget(btn)
            
        self.content_layout.addWidget(self.header_frame)

        # --- 중단 (카메라 + 타이머) ---
        self.middle_layout = QHBoxLayout()
        self.middle_layout.setSpacing(15)

        # 1. 카메라 뷰 카드
        self.cam_frame = QFrame()
        self.cam_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 20px;")
        cam_layout = QVBoxLayout(self.cam_frame)
        cam_layout.setContentsMargins(15, 15, 15, 15)
        
        cam_header = QHBoxLayout()
        cam_title = QLabel("📹 카메라 뷰")
        cam_title.setStyleSheet("font-size: 15px; font-weight: 800; border: none;")
        cam_live = QLabel("🔴 LIVE")
        cam_live.setStyleSheet("background-color: #222; color: white; border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        cam_live.setAlignment(Qt.AlignCenter)
        cam_header.addWidget(cam_title)
        cam_header.addStretch()
        cam_header.addWidget(cam_live)
        
        self.image_label = QLabel("웹캠 연결 중...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(500, 340)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setStyleSheet("background-color: #F1F1F1; border-radius: 14px;")
        
        cam_layout.addLayout(cam_header)
        cam_layout.addSpacing(10)
        cam_layout.addWidget(self.image_label, stretch=1)
        self.middle_layout.addWidget(self.cam_frame, stretch=6)

        # 2. 타이머 리스트 카드
        self.timer_frame = QFrame()
        self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 20px;")
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

        # --- 하단 상태 표시 ---
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 20px;")
        self.status_frame.setFixedHeight(95)
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)
        
        self.lbl_gesture = QLabel("정상")
        self.lbl_selected = QLabel("-")
        self.lbl_smoke = QLabel("안전")
        
        stat1 = self.create_status_item("06_hand_gesture.png", "제스처 인식", self.lbl_gesture, "인식 상태 양호", "#10B981")
        stat2 = self.create_status_item("16_hourglass.png", "선택된 타이머", self.lbl_selected, "제어 대기중", "#F59E0B")
        stat3 = self.create_status_item("17_smoke_status.png", "연기 감지 상태", self.lbl_smoke, "정상 범위", "#10B981")
        
        status_layout.addWidget(stat1)
        div1 = QFrame(); div1.setFixedWidth(1); div1.setStyleSheet("background-color: #F0F0F0;")
        status_layout.addWidget(div1)
        status_layout.addWidget(stat2)
        div2 = QFrame(); div2.setFixedWidth(1); div2.setStyleSheet("background-color: #F0F0F0;")
        status_layout.addWidget(div2)
        status_layout.addWidget(stat3)

        self.content_layout.addWidget(self.status_frame)

        # --- 최하단 컨트롤 ---
        self.control_frame = QFrame()
        self.control_frame.setFixedHeight(55)
        control_layout = QHBoxLayout(self.control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(12)
        
        btn_base = "background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 14px; font-size: 14px; font-weight: 800; color: #444;"
        
        self.btn_pause = QPushButton(" 일시정지"); self.btn_pause.setIcon(self.get_icon("22_pause.png"))
        self.btn_pause.setStyleSheet(btn_base)
        self.btn_reset = QPushButton(" 초기화"); self.btn_reset.setIcon(self.get_icon("25_refresh.png"))
        self.btn_reset.setStyleSheet(btn_base)
        
        self.btn_alert_off = QPushButton(" 경보 끄기"); self.btn_alert_off.setIcon(self.get_icon("19_muted_bell.png"))
        self.btn_alert_off.setStyleSheet("background-color: #FFF2F2; border: 1px solid #FFCDCD; border-radius: 14px; font-size: 14px; font-weight: 800; color: #D32F2F;")
        
        for b in [self.btn_pause, self.btn_reset, self.btn_alert_off]:
            b.setIconSize(QSize(18, 18))

        self.lbl_fps = QLabel("FPS\n60")
        self.lbl_fps.setAlignment(Qt.AlignCenter)
        self.lbl_fps.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 14px; font-size: 11px; font-weight: bold; color: #888;")
        
        control_layout.addWidget(self.btn_pause, stretch=1)
        control_layout.addWidget(self.btn_reset, stretch=1)
        control_layout.addWidget(self.btn_alert_off, stretch=1)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.lbl_fps)

        self.content_layout.addWidget(self.control_frame)
        self.main_layout.addWidget(self.content_frame)

        # 타이머 데이터 초기화
        self.selected_pot = None           
        self.pot_times = [0, 0, 0, 0]      
        self.pot_states = ["대기", "대기", "대기", "대기"]  
        self.pot_labels = [self.lbl_pot1, self.lbl_pot2, self.lbl_pot3, self.lbl_pot4]

        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.update_countdowns)
        self.master_timer.start(1000)

        # 제스처 시그널 연결
        self.gesture_controller.pot_selected_signal.connect(self.select_pot)
        self.gesture_controller.timer_start_signal.connect(self.start_selected_timer)
        self.gesture_controller.timer_pause_signal.connect(self.pause_selected_timer)
        self.gesture_controller.timer_reset_signal.connect(self.reset_selected_timer)

    def create_timer_item(self, num, icon_file, name, time_lbl):
        wrapper = QFrame()
        wrapper.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 16px;")
        wrapper.setFixedHeight(75)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(15, 0, 15, 0)
        
        lbl_num = QLabel(num)
        lbl_num.setStyleSheet("font-size: 14px; font-weight: bold; color: #222; border: none;")
        
        lbl_icon = QLabel()
        pixmap = QPixmap(os.path.join("img", icon_file))
        if not pixmap.isNull():
            lbl_icon.setPixmap(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("font-size: 13px; color: #555; font-weight: bold; border: none;")
        
        time_lbl.setStyleSheet("font-size: 18px; font-weight: 900; color: #222; border: none;")
        
        btn_play = QPushButton()
        btn_play.setIcon(self.get_icon("21_play.png"))
        btn_play.setIconSize(QSize(14, 14))
        btn_play.setFixedSize(30, 30)
        btn_play.setStyleSheet("background-color: #E2AD64; border-radius: 15px; border: none;")
        
        self.timer_buttons.append(btn_play)
        
        layout.addWidget(lbl_num)
        layout.addSpacing(10)
        layout.addWidget(lbl_icon)
        layout.addSpacing(5)
        layout.addWidget(lbl_name)
        layout.addStretch()
        layout.addWidget(time_lbl)
        layout.addSpacing(10)
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
        icon_lbl.setStyleSheet("background-color: #F5F5F5; border-radius: 22px;")
        
        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
        val_lbl.setStyleSheet("font-size: 17px; font-weight: 900; color: #111;")
        s_lbl = QLabel(sub)
        s_lbl.setStyleSheet("font-size: 10px; color: #999;")
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

    def select_burner(self, num):
        self.selected_pot = num
        if not self.is_mini_mode:
            for i, w in enumerate(self.pot_wrappers):
                if (i + 1) == num:
                    w.setStyleSheet("background-color: #FFFDF8; border: 2px solid #F39C12; border-radius: 16px;")
                else:
                    w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 16px;")
        self.lbl_selected.setText(f"0{num}")

    # ==========================================
    # 🔥 미니모드 전환 
    # ==========================================
    def on_snap_swipe(self):
        screen = self.screen().geometry()
        
        if not self.is_mini_mode:
            # 창 테두리 없애고(위젯처럼) 최상단 고정
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            
            # 불필요한 UI 모조리 숨기기
            self.sidebar.hide()
            self.cam_frame.hide()
            self.status_frame.hide()
            self.control_frame.hide()
            self.header_frame.hide()
            self.t_header_frame.hide()

            # 🛠️ 최소 크기 박살내기!
            self.image_label.setMinimumSize(0, 0)
            
            # 🛠️ 레이아웃 여백 강제 0으로 날리기!
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(0)
            self.middle_layout.setSpacing(0)
            self.timer_layout.setContentsMargins(0, 0, 0, 0)
            self.timer_layout.setSpacing(0)
            
            self.timer_frame.setStyleSheet("background: transparent; border: none;")

            active_timers = 0
            for i, state in enumerate(self.pot_states):
                if state == "실행":
                    self.pot_wrappers[i].show()
                    self.pot_wrappers[i].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 16px;")
                    active_timers += 1
                else:
                    self.pot_wrappers[i].hide()

            if active_timers == 0:
                self.pot_wrappers[0].show()
                self.pot_wrappers[0].setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 16px;")
                target_height = 75
            else:
                target_height = active_timers * 75

            # 🛠️ 강제 크기 고정!
            self.setMinimumSize(0, 0)
            self.setFixedSize(280, target_height)
            
            # 우측 하단으로 이동
            self.move(
                screen.width() + screen.x() - self.width() - 20,
                screen.height() + screen.y() - self.height() - 20
            )
            self.show() 
            self.is_mini_mode = True
            
        else:
            # 기본 모드 복구
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            
            # 🛠️ 카메라 최소 크기 복구
            self.image_label.setMinimumSize(500, 340)

            # 🛠️ 레이아웃 여백 원상 복구
            self.main_layout.setContentsMargins(15, 15, 15, 15)
            self.main_layout.setSpacing(20)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(15)
            self.middle_layout.setSpacing(15)
            self.timer_layout.setContentsMargins(15, 15, 15, 15)
            self.timer_layout.setSpacing(10)
            
            # 🛠️ 강제 고정 풀기
            self.setMinimumSize(1150, 750)
            self.setMaximumSize(16777215, 16777215)
            self.resize(1150, 750)
            
            center_x = screen.x() + (screen.width() - 1150) // 2
            center_y = screen.y() + (screen.height() - 750) // 2
            self.move(center_x, center_y)
            
            self.sidebar.show()
            self.cam_frame.show()
            self.status_frame.show()
            self.control_frame.show()
            self.header_frame.show()
            self.t_header_frame.show()
            
            self.timer_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 20px;")
            
            for i, w in enumerate(self.pot_wrappers):
                w.show()
                if self.selected_pot == (i + 1):
                    w.setStyleSheet("background-color: #FFFDF8; border: 2px solid #F39C12; border-radius: 16px;")
                else:
                    w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 16px;")
            
            self.show()
            self.is_mini_mode = False
            
        pyautogui.hotkey('alt', 'esc')

    # 타이머 로직들
    def select_pot(self, pot_num):
        if 1 <= pot_num <= 4: self.select_burner(pot_num)

    def start_selected_timer(self):
        if self.selected_pot is None: return
        idx = self.selected_pot - 1
        if self.pot_times[idx] == 0: self.pot_times[idx] = 300
        self.pot_states[idx] = "실행"
        self.timer_buttons[idx].setIcon(self.get_icon("22_pause.png"))
        # 🔥 여기서 까만색(#222) 대신 밝은 회색(#EAEAEA)으로 수정 완료!
        self.timer_buttons[idx].setStyleSheet("background-color: #EAEAEA; border-radius: 15px; border: none;")

    def pause_selected_timer(self):
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            self.pot_states[idx] = "정지"
            self.timer_buttons[idx].setIcon(self.get_icon("21_play.png"))
            self.timer_buttons[idx].setStyleSheet("background-color: #E2AD64; border-radius: 15px; border: none;")

    def reset_selected_timer(self):
        if self.selected_pot is not None:
            idx = self.selected_pot - 1
            self.pot_times[idx] = 0
            self.pot_states[idx] = "대기"
            self.refresh_pot_label(idx)
            self.timer_buttons[idx].setIcon(self.get_icon("21_play.png"))
            self.timer_buttons[idx].setStyleSheet("background-color: #E2AD64; border-radius: 15px; border: none;")

    def update_countdowns(self):
        for i in range(4):
            if self.pot_states[i] == "실행" and self.pot_times[i] > 0:
                self.pot_times[i] -= 1
                self.refresh_pot_label(i)
                if self.pot_times[i] == 0:
                    self.pot_states[i] = "대기"
                    self.timer_buttons[i].setIcon(self.get_icon("21_play.png"))
                    self.timer_buttons[i].setStyleSheet("background-color: #E2AD64; border-radius: 15px; border: none;")

    def refresh_pot_label(self, idx):
        t = self.pot_times[idx]
        self.pot_labels[idx].setText(f"{t//60:02d}:{t%60:02d}" if t > 0 else "--:--")

    # 웹캠 로직
    def start_webcam(self):
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        if not self.timer.isActive():
            self.timer.start(30)

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                try:
                    frame, gestures = self.gesture_controller.process(frame)
                    if gestures:
                        g_name = gestures[0]["gesture"]
                        self.lbl_gesture.setText(g_name.upper())
                        if g_name == "one": self.select_burner(1)
                        elif g_name == "two": self.select_burner(2)
                        elif g_name == "three": self.select_burner(3)
                        elif g_name == "four": self.select_burner(4)
                except Exception:
                    pass

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self.image_label.setPixmap(QPixmap.fromImage(qt_img).scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, event):
        if hasattr(self, 'timer'): self.timer.stop()
        if self.cap and self.cap.isOpened(): self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = kitchen_App()
    window.show()
    sys.exit(app.exec())
# <트러블 슈팅 보고서 (미니모드 레이아웃 깨짐 현상)
# 문제 현상: 미니모드(위젯 모드)로 전환 시, 창 크기가 줄어들지 않고 가로로 길게 찢어지며 UI가 텅 비어 보이는 현상 발생.

# 근본 원인 (Root Cause):

# PySide6(Qt)의 레이아웃 시스템은 자식 위젯들의 MinimumSize(최소 크기)를 기억하고 창 크기가 그 이하로 줄어드는 것을 강제로 막는 특성이 있습니다.

# 기존 풀 화면 모드에 있던 '웹캠 카메라 영역'에 MinimumSize(500, 340)이 설정되어 있었고, 레이아웃 자체의 기본 여백(Margin)이 남아있어 창이 작아지는 것을 거부했습니다.

# 해결 방안 (Solution):

# 크기 제약 해제: 미니모드 진입 시 카메라 위젯의 MinimumSize를 (0, 0)으로 강제 초기화.

# 여백(Margin) 압축: 안 보이는 투명 레이아웃들의 Margin과 Spacing을 모두 0으로 날림.

# 강제 크기 고정: 창 크기를 부탁하듯 줄이는 resize() 대신, 절대 크기가 변하지 못하도록 setFixedSize(280, 높이)로 묶어버려 완벽하게 제어함.