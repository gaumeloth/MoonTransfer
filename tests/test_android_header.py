from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.environ.get("MOONTRANSFER_KIVY_TOUCH_TESTS") == "1"
    and importlib.util.find_spec("kivy"),
    "Requires opt-in Kivy touch tests and an OpenGL context",
)
class AndroidHeaderTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "android" / "app"))
        sys.path.insert(0, str(ROOT / "src"))
        from kivy.base import EventLoop
        from kivy.clock import Clock
        from kivy.core.window import Window
        from kivy.input.motionevent import MotionEvent
        from moontransfer_android.application import MoonTransferAndroidApp

        class Touch(MotionEvent):
            def depack(self, args):
                self.sx, self.sy = args
                super().depack(args)

        self.Touch = Touch
        self.clock = Clock
        self.window = Window
        self.event_loop = EventLoop
        self.old_size = Window.size
        Window.size = (360, 640)
        self.app = MoonTransferAndroidApp()
        self.app.root = self.app.build()
        Window.add_widget(self.app.root)
        self.addCleanup(self.cleanup_app)
        self.settle()

    def cleanup_app(self):
        from kivy.animation import Animation
        from kivy.lang import Builder
        from moontransfer_android.application import KV_PATH

        self.app.on_stop()
        if self.app._snackbar_event is not None:
            self.app._snackbar_event.cancel()
        for widget in self.app.root.walk():
            Animation.cancel_all(widget)
        self.window.remove_widget(self.app.root)
        self.window.size = self.old_size
        Builder.unload_file(str(KV_PATH))

    def settle(self):
        for _ in range(20):
            self.clock.tick()

    def tap(self, button):
        x, y = button.to_window(*button.center)
        touch = self.Touch(
            "test", 1,
            (x / (self.window.width - 1), y / (self.window.height - 1)),
            is_touch=True, type_id="touch",
        )
        touch.profile = ["pos"]
        self.event_loop.post_dispatch_input("begin", touch)
        self.event_loop.post_dispatch_input("end", touch)
        self.settle()

    def assert_info_opens(self):
        self.tap(self.app.build_info_button)
        dialog = self.app._dialog_overlay
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.title, "Informazioni su MoonTransfer")
        self.assertTrue(dialog.details)
        dialog.invoke_primary()
        self.assertIsNone(self.app._dialog_overlay)

    def test_info_with_hidden_transport_panel_in_both_tabs(self):
        for mode in ("send", "receive"):
            with self.subTest(mode=mode):
                self.app._switch_mode(mode)
                self.settle()
                self.assert_info_opens()

    def test_info_with_visible_transport_panel(self):
        self.app._set_transport_panel_visible(True)
        self.settle()
        self.assert_info_opens()

    def test_info_after_transport_panel_is_hidden(self):
        self.app._set_transport_panel_visible(True)
        self.settle()
        self.app._set_transport_panel_visible(False)
        self.settle()
        self.assert_info_opens()

    def test_visible_retry_button_still_receives_taps(self):
        self.app._set_transport_panel_visible(True)
        button = self.app.probe_button
        button.unbind(on_release=self.app._start_transport_probe)
        callback = Mock()
        button.bind(on_release=callback)
        button.disabled = False
        self.settle()
        self.tap(button)
        callback.assert_called_once_with(button)
