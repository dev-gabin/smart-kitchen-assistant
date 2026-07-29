import sys

from PySide6.QtWidgets import QApplication

from src.kitchen_ui_overlay import kitchen_App


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    window = kitchen_App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()