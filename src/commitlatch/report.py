"""Self-contained, offline report. All dynamic content is escaped."""

import html
import json


def render_demo(data):
    titles = {"naive": "01 / Blind retry", "reconciled": "02 / Receipt reconciliation",
              "opaque": "03 / Unknown outcome"}
    descriptions = {
        "naive": "The request was repeated after the crash. The test service performed two operations.",
        "reconciled": "CommitLatch found the provider receipt and recovered the result without another dispatch.",
        "opaque": "No authoritative receipt is available. CommitLatch keeps UNKNOWN and blocks another dispatch.",
    }
    cards = []
    for case in data["scenarios"]:
        scenario = case["scenario"]
        events = "".join(
            "<li><strong>%s</strong><pre>%s</pre></li>" % (
                html.escape(event["kind"]),
                html.escape(json.dumps(event["detail"], ensure_ascii=False, indent=2)))
            for event in case["events"])
        cards.append("""<article class="card %s"><p class="eyebrow">%s</p>
            <span class="badge">%s</span><div class="number">%d<span>external effects</span></div>
            <p class="description">%s</p><div class="meta">Attempts: %d · Worker exit code: %d</div>
            <details><summary>Show event log</summary><ol>%s</ol></details></article>""" % (
                html.escape(scenario), html.escape(titles[scenario]), html.escape(case["state"]),
                case["effects"], html.escape(descriptions[scenario]), case["attempts"],
                case["worker_exit"], events))
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
    <title>CommitLatch — crash recovery demo</title><style>
    *{box-sizing:border-box}body{margin:0;background:#101820;color:#edf3f7;font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
    main{max-width:1240px;margin:auto;padding:48px 32px 56px}.brand{color:#61dfc6;font-weight:750;letter-spacing:.02em}
    .tag{float:right;color:#acbbc7;font-size:13px;border:1px solid #40505d;border-radius:20px;padding:4px 12px}
    .eyebrow{font-size:12px;letter-spacing:.1em;color:#acbbc7;text-transform:uppercase}h1{font-size:clamp(30px,4vw,50px);line-height:1.15;max-width:850px;letter-spacing:-.035em;margin:36px 0 20px}
    .intro{color:#bac9d3;max-width:850px;font-size:18px}.flow{margin:28px 0 32px;padding:16px 22px;background:#192731;border:1px solid #304753;border-radius:12px;color:#bbded7}
    .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#19242e;border:1px solid #364650;border-radius:16px;padding:24px;min-width:0}
    .badge{display:inline-block;border-radius:6px;font-size:12px;letter-spacing:.05em;padding:4px 9px;background:#3e222c;color:#ff9daa}
    .reconciled .badge{background:#173d35;color:#75efd2}.opaque .badge{background:#40341e;color:#f3cd7c}
    .number{font-size:64px;font-weight:700;line-height:1.1;margin:24px 0 16px;letter-spacing:-.04em}.number span{display:block;font-size:14px;font-weight:400;color:#acbbc7;letter-spacing:0;margin-top:9px}
    .description{min-height:104px}.meta{color:#acbbc7;font-size:12px;border-top:1px solid #364650;padding-top:16px}details{margin-top:16px;font-size:13px}summary{cursor:pointer;color:#75dfcd}
    ol{padding-left:20px}li{padding:8px 0}li strong{font-size:11px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#acbbc7;font-size:11px}
    .note{margin-top:28px;color:#adbeca;font-size:14px;border-left:3px solid #61dfc6;padding-left:18px}.note strong{color:#edf3f7}footer{margin-top:32px;color:#7f929f;font-size:12px}
    @media(max-width:850px){.grid{grid-template-columns:1fr}.description{min-height:0}main{padding:28px 20px}.tag{float:none;display:inline-block;margin-left:12px}}
    </style></head><body><main><div class="brand">CommitLatch <span class="tag">ALPHA · 0.1.0a1</span></div>
    <h1>The action happened.<br>The response vanished. Now what?</h1>
    <p class="intro">Observed results after terminating a real child process between the external effect and the local acknowledgement. All operations use synthetic test data.</p>
    <div class="flow">External effect committed → worker terminated with os._exit(42) → recovery</div>
    <section class="grid">""" + "".join(cards) + """</section>
    <div class="note"><strong>What this test demonstrates.</strong> Reconciliation can recover a confirmed result without repeating the action. When the outcome cannot be established, the library blocks another dispatch. UNKNOWN is a valid unresolved state, never an implicit success.<br><br>
    The test service uses an independent SQLite database and deliberately allows duplicates. This models the effect/acknowledgement gap locally; it does not test a remote API, PostgreSQL or Stripe.</div>
    <footer>Source: results.json beside this report. No external assets, telemetry or JavaScript. Expand a card to inspect its recorded events.</footer>
    </main></body></html>"""
