from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


# Run with MOONTRANSFER_KIVY_TOUCH_TESTS=1 in the Android environment.
# On headless Linux, SDL_VIDEODRIVER=offscreen provides the OpenGL context.
@unittest.skipUnless(
    os.environ.get("MOONTRANSFER_KIVY_TOUCH_TESTS") == "1"
    and importlib.util.find_spec("kivy"),
    "Requires opt-in Kivy touch tests and an OpenGL context",
)
class AndroidScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "android" / "app"))
        sys.path.insert(0, str(ROOT / "src"))
        from kivy.base import EventLoop
        from kivy.clock import Clock
        from kivy.core.window import Window
        from kivy.input.motionevent import MotionEvent
        from kivy.uix.scrollview import ScrollView
        from moontransfer_android.application import MoonTransferAndroidApp

        class Touch(MotionEvent):
            def depack(self, args):
                self.sx, self.sy = args
                super().depack(args)

        cls.Touch = Touch
        cls.clock = Clock
        cls.window = Window
        cls.event_loop = EventLoop
        cls.app = MoonTransferAndroidApp()
        Window.size = (360, 640)
        cls.root = cls.app.build()
        Window.add_widget(cls.root)
        cls.selection = cls.root.ids.selection_list
        cls.page = cls.selection.parent
        while not isinstance(cls.page, ScrollView):
            cls.page = cls.page.parent
        cls.settle()

    @classmethod
    def tearDownClass(cls):
        cls.window.remove_widget(cls.root)

    @classmethod
    def settle(cls):
        for _ in range(12):
            cls.clock.tick()

    def prepare(self, count):
        for view in (self.page, self.selection):
            view.effect_y.velocity = 0
        self.selection.disabled = False
        self.selection.data = [
            {"title": f"File {i}", "detail": "1 KiB", "item_index": i}
            for i in range(count)
        ]
        self.settle()
        self.page.scroll_y = 0.5
        self.selection.scroll_y = 0.5
        self.settle()

    def swipe(self, dy, start=None):
        x, y = self.selection.to_window(*self.selection.center)
        y = max(self.page.y + 70, min(y, self.page.top - 70))
        if start is not None:
            x, y = start

        def args(py):
            return x / (self.window.width - 1), py / (self.window.height - 1)

        touch = self.Touch("test", 1, args(y), is_touch=True, type_id="touch")
        touch.profile = ["pos"]
        self.event_loop.post_dispatch_input("begin", touch)
        for step in range(1, 5):
            touch.move(args(y + dy * step / 4))
            self.event_loop.post_dispatch_input("update", touch)
        self.event_loop.post_dispatch_input("end", touch)

    def test_page_scrolls_from_empty_and_short_selection_in_both_directions(self):
        for count in (0, 1, 3):
            for dy in (-60, 60):
                with self.subTest(count=count, dy=dy):
                    self.prepare(count)
                    before = self.page.scroll_y
                    self.swipe(dy)
                    self.assertLess((self.page.scroll_y - before) * dy, 0)

    def test_long_selection_still_scrolls(self):
        self.prepare(30)
        before = self.selection.scroll_y
        self.swipe(60)
        self.assertLess(self.selection.scroll_y, before)

    def test_disabled_selection_does_not_block_page_swipes(self):
        self.prepare(30)
        self.selection.disabled = True
        before = self.page.scroll_y
        self.swipe(60)
        self.assertLess(self.page.scroll_y, before)

    def test_visible_and_hidden_snackbar_allow_page_swipes(self):
        snackbar = self.root.ids.snackbar
        for visible in (True, False):
            with self.subTest(visible=visible):
                self.prepare(0)
                snackbar.disabled = not visible
                snackbar.opacity = int(visible)
                before = self.page.scroll_y
                self.swipe(60, start=snackbar.center)
                self.assertLess(self.page.scroll_y, before)

    def test_short_selection_remove_button_still_receives_taps(self):
        from moontransfer_android.widgets import MoonIconButton

        self.prepare(1)
        removed = []
        self.selection.data = [{
            "title": "File", "item_index": 0, "remove_callback": removed.append,
        }]
        self.settle()
        row = self.selection.layout_manager.children[0]
        button = next(child for child in row.children if isinstance(child, MoonIconButton))
        self.swipe(0, start=button.to_window(*button.center))
        self.settle()
        self.settle()
        self.assertEqual(removed, [0])


if __name__ == "__main__":
    unittest.main()
