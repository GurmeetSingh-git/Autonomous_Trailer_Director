"""FFmpeg drawtext filter construction from composable card attributes."""

from pathlib import Path

_EMPHASIS_PARAMS = {
    "subtle":   {"fontsize": 42, "fontcolor": "white@0.9"},
    "bold":     {"fontsize": 60, "fontcolor": "white"},
    "dramatic": {"fontsize": 78, "fontcolor": "white"},
}
_POSITION_Y = {
    "center": "(h-text_h)/2",
    "lower_third": "h*0.75-text_h/2",
}

MIN_CARD_DURATION = 1.2
MAX_CARD_DURATION = 3.5
_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def clamp_card_duration(duration: float) -> float:
    return max(MIN_CARD_DURATION, min(MAX_CARD_DURATION, duration))



def escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,").replace("'", "\\x27")


def _font_file() -> str | None:
    for candidate in _FONT_CANDIDATES:
        if candidate.is_file():
            return escape_drawtext(candidate.as_posix())
    return None


def build_drawtext_filter(content: str, emphasis: str, position: str, case: str, duration: float) -> str:
    text = content.upper() if case == "upper" else content
    params = _EMPHASIS_PARAMS.get(emphasis, _EMPHASIS_PARAMS["bold"])
    y = _POSITION_Y.get(position, _POSITION_Y["center"])
    safe_text = escape_drawtext(text)
    fade_in, fade_out = 0.4, 0.4
    alpha_expr = (
        f"if(lt(t,{fade_in}),t/{fade_in},"
        f"if(lt(t,{max(duration - fade_out, fade_in)}),1,"
        f"if(lt(t,{duration}),({duration}-t)/{fade_out},0)))"
    ).replace(",", "\\,")
    font_file = _font_file()
    font_option = f":fontfile='{font_file}'" if font_file else ""
    return (
        f"drawtext=text='{safe_text}'{font_option}:fontsize={params['fontsize']}:"
        f"fontcolor={params['fontcolor']}:x=(w-text_w)/2:y={y}:alpha='{alpha_expr}'"
    )