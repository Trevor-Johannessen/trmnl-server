"""Windows for the House screen -- shown only when something is actually wrong."""
from ..layout import Window, esc

MAX_ROWS = 6


class Findings(Window):
    def __init__(self, findings):
        self.findings = findings

    def render(self):
        if not self.findings:
            return '<div class="w"><div class="empty">All clear</div></div>'
        rows = []
        for finding in self.findings[:MAX_ROWS]:
            severity = (finding.get("severity") or "").upper()
            badge = "badge" if severity == "CRIT" else "badge hollow"
            where = " / ".join(x for x in (finding.get("machine"), finding.get("component")) if x)
            rows.append(
                "<li>"
                f'<span class="{badge}">{esc(severity)}</span>'
                '<span style="min-width:0;flex:1">'
                f'<span class="sm clip" style="display:block;font-weight:600">{esc(where)}</span>'
                f'<span class="xs clip" style="display:block">{esc(finding.get("message"))}</span>'
                "</span></li>")
        more = len(self.findings) - MAX_ROWS
        extra = f'<div class="xs" style="margin-top:6px">+{more} more</div>' if more > 0 else ""
        return f'<div class="w tight"><ul class="items">{"".join(rows)}</ul>{extra}</div>'


class Minecraft(Window):
    def __init__(self, reading):
        self.reading = reading

    def render(self):
        if not self.reading.ok:
            return '<div class="w tight"><div class="caps">Minecraft</div></div>'
        data = self.reading.data
        names = ", ".join(data.get("online") or []) or "nobody online"
        return ('<div class="w tight">'
                '<div class="caps">Minecraft</div>'
                f'<div class="sm clip">{esc(names)}</div></div>')
