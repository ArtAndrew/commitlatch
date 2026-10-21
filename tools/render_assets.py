"""Render paced evidence frames and a social preview; requires Pillow.

Usage: python tools/render_assets.py path/to/http-output/results.json
This is a visualization of measured counts, not a screen recording.
"""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size, bold=False):
    choices = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else
               ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf"])
    for path in choices:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install DejaVu Sans or Arial to render the assets")


BG, PANEL, FG, MUTED = "#101820", "#192731", "#edf3f7", "#aabec9"
GREEN, RED, AMBER = "#64e2c2", "#ff8b98", "#f2c46e"


def evidence_frame(data, revealed):
    canvas = Image.new("RGB", (1080, 640), BG)
    d = ImageDraw.Draw(canvas)
    d.text((42, 25), "CommitLatch", font=font(23, True), fill=GREEN)
    d.text((770, 30), "EXPERIMENTAL ALPHA", font=font(15), fill=MUTED)
    d.text((42, 77), "The action happened. The response vanished.", font=font(34, True), fill=FG)
    d.rounded_rectangle((42, 137, 1038, 184), radius=8, fill=PANEL)
    d.text((60, 149), "POST /operations  >  effect committed  >  TCP connection closed", font=font(21), fill=MUTED)
    d.text((58, 211), "RECOVERY STRATEGY", font=font(14, True), fill=MUTED)
    d.text((526, 211), "EFFECTS", font=font(14, True), fill=MUTED)
    d.text((650, 211), "POSTS", font=font(14, True), fill=MUTED)
    d.text((790, 211), "OUTCOME", font=font(14, True), fill=MUTED)
    titles = {"blind_retry": "Blind retry", "native_idempotency": "Native idempotency key",
              "reconciled": "CommitLatch + receipt", "opaque": "CommitLatch + no lookup"}
    for index, case in enumerate(data["scenarios"]):
        y = 245 + index * 64
        d.rounded_rectangle((42, y, 1038, y + 55), radius=8, fill=PANEL)
        d.text((58, y + 15), titles[case["scenario"]], font=font(21), fill=FG)
        if index < revealed:
            color = RED if case["state"] == "DUPLICATED" else AMBER if case["state"] == "UNKNOWN" else GREEN
            d.text((551, y + 10), str(case["effects"]), font=font(28, True), fill=color)
            d.text((672, y + 10), str(case["post_requests"]), font=font(28, True), fill=FG)
            d.text((790, y + 17), case["state"], font=font(18, True), fill=color)
        else:
            d.text((551, y + 12), "—", font=font(24), fill=MUTED)
    d.text((42, 524), "Reconcile a known result. Stop when the outcome is unknown.", font=font(23, True), fill=GREEN)
    d.text((42, 574), "Synthetic loopback HTTP · measured counts · paced animation, not latency", font=font(17), fill=MUTED)
    d.text((42, 601), "Reproduce: PYTHONPATH=src python3 -m commitlatch http-demo", font=font(17), fill=MUTED)
    return canvas


def social_preview():
    canvas = Image.new("RGB", (1280, 640), BG)
    d = ImageDraw.Draw(canvas)
    d.text((64, 42), "CommitLatch", font=font(30, True), fill=GREEN)
    d.text((64, 142), "Your agent lost", font=font(62, True), fill=FG)
    d.text((64, 215), "the response.", font=font(62, True), fill=FG)
    d.text((64, 316), "Should it repeat", font=font(47, True), fill=GREEN)
    d.text((64, 374), "the action?", font=font(47, True), fill=GREEN)
    labels = [("01", "Record the intent"), ("02", "Reconcile the receipt"),
              ("03", "Stop on UNKNOWN")]
    for index, (number, label) in enumerate(labels):
        y = 155 + index * 95
        d.rounded_rectangle((750, y, 1216, y + 76), radius=12, fill=PANEL)
        d.text((773, y + 25), number, font=font(21, True), fill=GREEN)
        d.text((825, y + 24), label, font=font(24), fill=FG)
    d.line((64, 514, 1216, 514), fill="#354b57", width=2)
    d.text((64, 549), "Python SDK · Apache-2.0 · Experimental alpha", font=font(23), fill=MUTED)
    d.text((64, 589), "github.com/ArtAndrew/commitlatch", font=font(19), fill=MUTED)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, default=Path("assets"))
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    if data.get("test_only") is not True or len(data["scenarios"]) != 4:
        raise ValueError("Expected the four measured loopback HTTP scenarios")
    args.output.mkdir(parents=True, exist_ok=True)
    frames = [evidence_frame(data, i) for i in range(5)]
    frames[0].save(args.output / "recovery-demo.gif", save_all=True,
                   append_images=frames[1:], duration=[1700, 1700, 1700, 1700, 4200], loop=0)
    frames[-1].save(args.output / "recovery-results.png", optimize=True)
    social_preview().save(args.output / "social-preview.png", optimize=True)
    (args.output / "http-results.json").write_text(json.dumps(data, indent=2) + "\n")
    print("Rendered GIF, static results, social preview and measured JSON")


if __name__ == "__main__":
    main()
