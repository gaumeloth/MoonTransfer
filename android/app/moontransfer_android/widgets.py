from __future__ import annotations

from collections.abc import Callable

from kivy.metrics import dp
from kivy.properties import (
    AliasProperty,
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    OptionProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.textinput import TextInput

from moontransfer_android import theme


BUTTON_BACKGROUNDS = {
    "primary": theme.PRIMARY,
    "secondary": theme.SURFACE_STRONG,
    "quiet": theme.TRANSPARENT,
    "danger": theme.ERROR_SOFT,
    "success": theme.SUCCESS_SOFT,
}
BUTTON_PRESSED_BACKGROUNDS = {
    "primary": theme.PRIMARY_PRESSED,
    "secondary": theme.BORDER_STRONG,
    "quiet": theme.SURFACE_ALT,
    "danger": (0.30, 0.11, 0.14, 1.0),
    "success": (0.08, 0.27, 0.18, 1.0),
}
BUTTON_FOREGROUNDS = {
    "primary": theme.PRIMARY_TEXT,
    "secondary": theme.TEXT,
    "quiet": theme.TEXT_MUTED,
    "danger": theme.ERROR,
    "success": theme.SUCCESS,
}
BUTTON_BORDERS = {
    "primary": theme.PRIMARY,
    "secondary": theme.BORDER,
    "quiet": theme.TRANSPARENT,
    "danger": (0.45, 0.18, 0.21, 1.0),
    "success": (0.12, 0.38, 0.25, 1.0),
}


class MoonTransferRoot(FloatLayout):
    pass


class MoonWrappedLabel(Label):
    minimum_height = NumericProperty(dp(28))
    label_color = ListProperty(theme.TEXT_MUTED)


class MoonTitleLabel(MoonWrappedLabel):
    pass


class MoonSurface(BoxLayout):
    surface_color = ListProperty(theme.SURFACE)
    border_color = ListProperty(theme.BORDER)
    radius = NumericProperty(dp(8))


class MoonActionBar(MoonSurface):
    pass


class MoonMetric(BoxLayout):
    title = StringProperty("")
    value = StringProperty("-")


class MoonAdaptiveBox(BoxLayout):
    breakpoint = NumericProperty(dp(720))

    def on_width(self, *_args: object) -> None:
        self.orientation = "horizontal" if self.width >= self.breakpoint else "vertical"


class _ButtonPalette:
    variant = OptionProperty(
        "primary",
        options=("primary", "secondary", "quiet", "danger", "success"),
    )

    def _background(self) -> tuple[float, float, float, float]:
        if self.disabled:
            return (
                theme.TRANSPARENT
                if self.variant == "quiet"
                else theme.SURFACE_DISABLED
            )
        if self.state == "down":
            return BUTTON_PRESSED_BACKGROUNDS[self.variant]
        return BUTTON_BACKGROUNDS[self.variant]

    resolved_background = AliasProperty(
        _background,
        bind=("disabled", "state", "variant"),
        cache=True,
    )

    def _foreground(self) -> tuple[float, float, float, float]:
        if self.disabled:
            return theme.TEXT_DISABLED
        return BUTTON_FOREGROUNDS[self.variant]

    resolved_foreground = AliasProperty(
        _foreground,
        bind=("disabled", "variant"),
        cache=True,
    )

    def _border(self) -> tuple[float, float, float, float]:
        if self.disabled:
            return theme.BORDER
        return BUTTON_BORDERS[self.variant]

    resolved_border = AliasProperty(
        _border,
        bind=("disabled", "variant"),
        cache=True,
    )


class MoonButton(_ButtonPalette, ButtonBehavior, BoxLayout):
    text = StringProperty("")
    icon_source = StringProperty("")
    radius = NumericProperty(dp(8))


class MoonIconButton(_ButtonPalette, ButtonBehavior, FloatLayout):
    icon_source = StringProperty("")
    radius = NumericProperty(dp(8))


class MoonNavButton(ButtonBehavior, BoxLayout):
    text = StringProperty("")
    icon_source = StringProperty("")
    selected = BooleanProperty(False)


class MoonTextInput(TextInput):
    radius = NumericProperty(dp(8))

    def _border(self) -> tuple[float, float, float, float]:
        if self.disabled:
            return theme.BORDER
        return theme.PRIMARY if self.focus else theme.BORDER_STRONG

    resolved_border = AliasProperty(
        _border,
        bind=("disabled", "focus"),
        cache=True,
    )


class MoonProgressBar(ProgressBar):
    track_color = ListProperty(theme.SURFACE_STRONG)
    progress_color = ListProperty(theme.PRIMARY)
    radius = NumericProperty(dp(4))

    def _normalized(self) -> float:
        if self.max <= 0:
            return 0.0
        return max(0.0, min(1.0, self.value / self.max))

    normalized_value = AliasProperty(
        _normalized,
        bind=("max", "value"),
        cache=True,
    )


class MoonSelectionRow(RecycleDataViewBehavior, BoxLayout):
    item_index = NumericProperty(-1)
    title = StringProperty("")
    detail = StringProperty("")
    icon_source = StringProperty("")
    remove_callback = ObjectProperty(None, allownone=True)

    def request_remove(self) -> None:
        callback = self.remove_callback
        if callback is not None and self.item_index >= 0:
            callback(int(self.item_index))


class MoonResultPanel(MoonSurface):
    title = StringProperty("")
    message = StringProperty("")
    icon_source = StringProperty("")
    tone = OptionProperty(
        "neutral",
        options=("success", "neutral", "error"),
    )

    def _tone_color(self) -> tuple[float, float, float, float]:
        return {
            "success": theme.SUCCESS,
            "neutral": theme.TEXT_MUTED,
            "error": theme.ERROR,
        }[self.tone]

    tone_color = AliasProperty(_tone_color, bind=("tone",), cache=True)


class MoonSnackbar(MoonSurface):
    text = StringProperty("")


class MoonDialogOverlay(FloatLayout):
    title = StringProperty("")
    message = StringProperty("")
    details = StringProperty("")
    primary_text = StringProperty("Chiudi")
    secondary_text = StringProperty("")
    primary_callback = ObjectProperty(None, allownone=True)
    secondary_callback = ObjectProperty(None, allownone=True)

    def invoke_primary(self) -> None:
        callback: Callable[[], None] | None = self.primary_callback
        if callback is not None:
            callback()

    def invoke_secondary(self) -> None:
        callback: Callable[[], None] | None = self.secondary_callback
        if callback is not None:
            callback()
