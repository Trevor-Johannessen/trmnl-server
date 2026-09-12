"""Screen layout.

Zones split an abstract space into two smaller parts along a single line; a
zone has two children (zone_one, zone_two) and this continues downward until a
leaf, which holds a Window that renders HTML.

The original version emitted vw/vh/cqi units against no viewport, so nothing
had a size. The panel is a fixed 800x480 and never anything else, so the
document below pins that in absolute pixels and every zone is a percentage of
its parent.
"""
import html

from .config import HEIGHT, WIDTH

DIVIDER_PX = 2


class Window:
    """A leaf. Subclasses return an HTML fragment that fills their zone."""

    def render(self) -> str:
        raise NotImplementedError(f"{type(self).__name__} does not implement render()")


class Zone:
    def __init__(self, direction=None, percentage=None, zone_one=None, zone_two=None,
                 window=None, divider=True):
        if window is not None and (direction or percentage or zone_one or zone_two):
            raise ValueError("Zone cannot be given subzones and a Window")
        if window is None and not (direction and percentage):
            raise ValueError("A non-leaf Zone needs both direction and percentage")
        if direction not in (None, "row", "column"):
            raise ValueError(f"Invalid direction {direction!r}; use 'row' or 'column'")
        if percentage is not None and not 0 < percentage < 100:
            raise ValueError(f"percentage must be between 0 and 100, got {percentage}")

        self.direction = direction
        self.percentage = percentage
        self.zone_one = zone_one
        self.zone_two = zone_two
        self.window = window
        self.divider = divider

    def render(self) -> str:
        if self.window is not None:
            return self.window.render()
        one = self.zone_one.render() if self.zone_one else ""
        two = self.zone_two.render() if self.zone_two else ""
        rule = ""
        if self.divider:
            # A row splits left/right, so its divider is a vertical rule.
            size = ("width:%dpx;height:100%%" if self.direction == "row"
                    else "height:%dpx;width:100%%") % DIVIDER_PX
            rule = f'<div class="rule" style="{size}"></div>'
        return (
            f'<div class="zone" style="flex-direction:{self.direction}">'
            f'<div class="pane" style="flex:0 0 calc({self.percentage}% - {DIVIDER_PX}px)">{one}</div>'
            f"{rule}"
            f'<div class="pane" style="flex:1 1 0">{two}</div>'
            "</div>"
        )


def esc(value) -> str:
    """Everything rendered into a screen comes from another service. Escape it."""
    return html.escape("" if value is None else str(value), quote=True)


def document(body: str, css: str, *, title: str = "trmnl") -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{esc(title)}</title><style>{css}</style></head>"
        f'<body><div class="screen" style="width:{WIDTH}px;height:{HEIGHT}px">{body}</div>'
        "</body></html>"
    )
