"""
Simple Qt browser window that shows Google Maps navigation.
Opens alongside the camera window.
"""
import sys
import threading
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, pyqtSignal, QObject

class _Signals(QObject):
    load_url = pyqtSignal(str)

class MapWindow:
    def __init__(self):
        self._signals = _Signals()
        self._win = None
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=5)

    def _run(self):
        app = QApplication.instance() or QApplication(sys.argv)
        self._win = QMainWindow()
        self._win.setWindowTitle("Navigation Map")
        self._win.resize(900, 700)
        self._view = QWebEngineView()
        self._view.load(QUrl("https://www.google.com/maps"))
        self._win.setCentralWidget(self._view)
        self._signals.load_url.connect(lambda u: self._view.load(QUrl(u)))
        self._win.show()
        self._ready.set()
        app.exec_()

    def load(self, url: str):
        self._signals.load_url.emit(url)
