import threading
import speech_recognition as sr
import pyttsx3

# 화구 번호별로 인식할 음성 키워드
_HOB_KEYWORDS = {
    1: ("1번", "일번", "첫 번째", "첫번째"),
    2: ("2번", "이번", "두 번째", "두번째"),
    3: ("3번", "삼번", "세 번째", "세번째"),
    4: ("4번", "사번", "네 번째", "네번째"),
}


class VoiceAssistant(threading.Thread):
    def __init__(self, timer_system):
        super().__init__()
        # timer_system은 get_remaining_time(hob_id) -> 남은 초(int)를 제공해야 함
        self.timer_system = timer_system
        self.daemon = True  # 메인 프로그램 종료 시 같이 종료
        self._stop_flag = threading.Event()

        # 💡 TTS 엔진(pyttsx3)은 여기서 만들지 않음.
        # VoiceAssistant는 QTimer.singleShot으로 메인 스레드에서 생성되는데, 여기서 엔진을
        # 만들면 SAPI5(COM) 엔진이 메인 스레드에 귀속됨. 정작 speak()는 run()이 도는
        # 별도 스레드에서 호출되는데, Windows COM은 생성한 스레드가 아닌 다른 스레드에서
        # 건드리면 예외 없이 조용히 무시돼서 콘솔에 텍스트만 찍히고 소리가 안 나는 원인이 됨.
        # 그래서 실제로 speak()를 호출할 run() 스레드 안에서 초기화함.
        self.engine = None

        # 음성 인식기 초기화
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300  # 마이크 민감도 (조절 가능)

    def speak(self, text):
        """텍스트를 음성으로 읽어주기"""
        print(f"[Voice Assistant] : {text}")
        if self.engine is None:
            return
        self.engine.say(text)
        self.engine.runAndWait()

    def stop(self):
        """음성 인식 루프 종료 요청"""
        self._stop_flag.set()

    def run(self):
        """음성 인식 루프"""
        # speak()를 호출할 이 스레드 안에서 TTS 엔진을 초기화해야 Windows COM 문제가 없음
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 160)  # 말하는 속도
        except Exception as e:
            print(f"[Voice Assistant] TTS 엔진 초기화 실패 (음성 안내 없이 텍스트만 출력됨): {e}")
            self.engine = None

        try:
            mic = sr.Microphone()
        except Exception as e:
            print(f"[Voice Assistant] 마이크를 열 수 없어 음성 인식을 시작할 수 없습니다: {e}")
            return

        with mic as source:
            print(">> 음성 인식 준비 완료. ('1번' ~ '4번' 등을 말씀하세요)")
            while not self._stop_flag.is_set():
                try:
                    # 마이크 입력 대기 (배경 소음 적응)
                    audio = self.recognizer.listen(source, timeout=None, phrase_time_limit=3)

                    # Google Web Speech API로 한국어 인식 (무료, 인터넷 필요)
                    text = self.recognizer.recognize_google(audio, language='ko-KR')
                    print(f"[인식된 음성]: {text}")

                    self.process_command(text)

                except sr.UnknownValueError:
                    pass  # 소리가 들렸으나 무슨 말인지 모를 때 무시
                except sr.RequestError as e:
                    print(f"음성 인식 서비스 에러: {e}")
                except Exception as e:
                    print(f"음성 처리 중 오류: {e}")

    def process_command(self, text):
        """'1번'~'4번' 등 화구 번호 키워드를 인식해서 해당 화구의 남은 타이머 시간을 안내"""
        for hob_id, keywords in _HOB_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                self._announce_remaining_time(hob_id)
                return

    def _announce_remaining_time(self, hob_id):
        """화구 번호를 받아 남은 시간을 조회하고 음성으로 안내"""
        time_left = self.timer_system.get_remaining_time(hob_id=hob_id)
        if time_left > 0:
            min_val = time_left // 60
            sec_val = time_left % 60
            self.speak(f"{hob_id}번 화구 남은 시간은 {min_val}분 {sec_val}초입니다.")
        else:
            self.speak(f"{hob_id}번 화구에 작동 중인 타이머가 없습니다.")
