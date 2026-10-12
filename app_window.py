import sys
import threading
import time
import os
import signal
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2, GLib

def main(port=8765):
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    url = f"http://127.0.0.1:{port}"

    Gtk.init()
    win = Gtk.Window(title="UltraViewer Linux")
    win.set_default_size(1100, 800)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.connect("destroy", Gtk.main_quit)

    icon_path = Path(__file__).with_name("ultraviewer-linux.png")
    if not icon_path.exists():
        icon_path = Path("/home/phuc/Documents/Codex/2026-10-12/new-chat/work/build-appimage/AppDir/ultraviewer-linux.png")
    if icon_path.exists():
        try:
            win.set_icon_from_file(str(icon_path))
        except Exception:
            pass

    webview = WebKit2.WebView()
    settings = webview.get_settings()
    settings.set_enable_javascript(True)
    settings.set_enable_webgl(True)
    
    webview.load_uri(url)
    win.add(webview)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
