import time

import pyautogui


class YoutubeController:
    """제스처 -> 유튜브 화면 제어(재생/일시정지, 볼륨 등) 매핑"""

    def __init__(self, cooldown_sec: float = 0.3):
        self.cooldown_sec = cooldown_sec
        self.last_action_time = 0

    def handle_vertical_motion(self, direction: str):
        """GestureController.hand_move_detected 시그널("up"/"down")을 받아 시스템 볼륨을 조절"""
        now = time.time()
        if now - self.last_action_time < self.cooldown_sec:
            return

        try:
            if direction == 'up':
                pyautogui.press('volumeup')
                print("[YoutubeController] 볼륨 업")
            elif direction == 'down':
                pyautogui.press('volumedown')
                print("[YoutubeController] 볼륨 다운")
        except Exception as e:
            print(f"[YoutubeController] 볼륨 조정 중 오류 발생: {e}")
        finally:
            self.last_action_time = now
