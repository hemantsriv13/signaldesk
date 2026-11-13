"""Dark mode must define every colour the last light palette defines. A variable missing from the
later .dark block silently keeps its light value in dark mode (the white-on-beige bug)."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "web" / "src" / "index.css").read_text(encoding="utf-8")


def block(selector: str) -> dict[str, str]:
    """Variables of the LAST block whose selector is exactly `selector`."""
    found = list(re.finditer(rf"(?m)^{re.escape(selector)}\s*\{{(.*?)^\}}", CSS, re.S))
    assert found, selector
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", found[-1].group(1)))


def test_last_dark_palette_covers_every_light_colour():
    light, dark = block(":root"), block(".dark")
    colours = {k for k, v in light.items() if re.match(r"#|oklch|rgb|hsl", v.strip())}
    assert not colours - dark.keys(), f"set these in .dark too: {sorted(colours - dark.keys())}"


def test_native_controls_follow_the_theme():
    assert re.search(r":root\s*\{\s*color-scheme:\s*light", CSS)
    assert re.search(r":root\.dark\s*\{\s*color-scheme:\s*dark", CSS)
    assert re.search(r"select option[^{]*\{[^}]*background-color:\s*var\(--popover\)[^}]*color:\s*var\(--popover-foreground\)", CSS)


def _lum(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_paired_tokens_reach_aa_contrast_in_both_themes():
    for name in (":root", ".dark"):
        t = block(name)
        pairs = [("background", "foreground"), ("card", "card-foreground"), ("popover", "popover-foreground"), ("muted", "foreground"),
                 ("muted", "muted-foreground"), ("row-selected", "row-selected-foreground"), ("row-hover", "foreground"),
                 ("quote", "quote-foreground"), ("chip", "chip-foreground"), ("secondary", "secondary-foreground"), ("primary", "primary-foreground"),
                 ("card", "muted-foreground"), ("card", "primary-text")]
        for bg, fg in pairs:
            assert ratio(t[f"--{bg}"], t[f"--{fg}"]) >= 4.5, (name, bg, fg, round(ratio(t[f"--{bg}"], t[f"--{fg}"]), 2))
