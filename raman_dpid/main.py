import sys

from PyQt6.QtWidgets import QApplication

from raman_dpid.gui import MainApp


def main():
    app = QApplication(sys.argv)
    ex = MainApp()
    if ex.config.get('show_whats_new', False):
        ex.show_whats_new()
    ex.showFullScreen()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()