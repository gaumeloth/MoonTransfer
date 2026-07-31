from __future__ import annotations

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label

from moontransfer.protocol import PROTOCOL_VERSION
from moontransfer.resources import APP_ICON_PATH


class MoonTransferAndroidApp(App):
    title = "MoonTransfer"
    icon = str(APP_ICON_PATH)

    def build(self) -> AnchorLayout:
        Window.clearcolor = (0.055, 0.059, 0.071, 1)

        root = AnchorLayout(padding=dp(24))
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint=(1, None),
            height=dp(220),
        )
        content.add_widget(
            Image(
                source=str(APP_ICON_PATH),
                size_hint=(1, None),
                height=dp(104),
                fit_mode="contain",
            )
        )
        content.add_widget(
            Label(
                text="MoonTransfer",
                color=(0.96, 0.96, 0.97, 1),
                font_size=sp(28),
                bold=True,
                size_hint=(1, None),
                height=dp(42),
            )
        )
        content.add_widget(
            Label(
                text=f"Android  |  Protocollo {PROTOCOL_VERSION}",
                color=(0.71, 0.73, 0.78, 1),
                font_size=sp(15),
                size_hint=(1, None),
                height=dp(30),
            )
        )
        root.add_widget(content)
        return root


def main() -> None:
    MoonTransferAndroidApp().run()
