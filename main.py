import sys
import os

# 현재 프로젝트 최상대 폴더 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Qt DPI 경고 차단
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window.warning=false"

try:
    from PySide6.QtWidgets import QApplication
    from src.kitchen_ui_overlay import KitchenApp
except Exception as e:
    print(f"❌ 파일 불러오기(Import) 중 에러 발생: {e}")
    sys.exit(1)


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        
    try:
        print(">> 🚀 메인 앱을 실행합니다...")
        window = KitchenApp()
        window.show()
        print(">> ✨ UI 창이 정상적으로 열렸습니다!")
        sys.exit(app.exec())
    except Exception as e:
        print(f"❌ 실행 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()