"""Export a plan as a ZIP of HTML and PDF files, one folder per audience: hitters/, pitchers/, coaches/.

Each plan section is first turned into a small document of blocks (headings, paragraphs, bullets, tables);
the same blocks are rendered to HTML and to PDF, so the two always match. Which sections go in which folder
comes from the fixed PACKETS allowlist in backend/agents/team.py, never from an agent.
"""

from __future__ import annotations

import html
import io
import unicodedata
import zipfile
from typing import Any

from fpdf import FPDF

from backend.team_colors import colors

Block = tuple  # ("h", text) | ("p", text) | ("bullets", [..]) | ("table", headers, rows)

TITLES = {
    "lineup_card": "Lineup Card", "pitching_plan": "Pitching Plan",
    "opposing_pitchers_report": "Scouting Report: Their Pitchers", "opposing_hitters_report": "Scouting Report: Their Hitters",
    "medical_report": "Medical and Availability Report", "manager_review": "Manager's Game Plan",
    "hitters_briefing": "Hitters' Briefing", "pitchers_briefing": "Pitchers' Briefing", "coaches_briefing": "Coaches' Briefing",
}
ROLE_ORDER = ["closer", "setup", "middle", "lefty_specialist", "long", "mop_up", "unavailable"]


def _f(x: Any, places: int = 3) -> str:
    if x is None:
        return "-"
    if isinstance(x, float) and x < 1 and places == 3:
        return f"{x:.3f}".lstrip("0")
    return f"{x:g}" if isinstance(x, float) else str(x)


# ---------------------------------------------------------------------------
# Sections -> blocks
# ---------------------------------------------------------------------------

def blocks_for(name: str, plan: dict) -> list[Block]:
    s = plan["sections"][name]
    if name == "lineup_card":
        b: list[Block] = [("p", f"Opposing starter: {s['opposing_starter_assumed']['name']}"),
                          ("table", ["#", "Player", "Pos", "Bats", "Why"],
                           [[x["slot"], x["name"], x["position"], x["bats"], x["reason"]]
                            for x in sorted(s["lineup"], key=lambda x: x["slot"])]),
                          ("h", "Bench"), ("table", ["Player", "Role", "Note"],
                                           [[x["name"], x["role"].replace("_", " "), x["note"]] for x in s["bench"]])]
        if s["substitutions"]:
            names = {x["player_id"]: x["name"] for x in s["lineup"] + s["bench"]}
            b += [("h", "Planned moves"), ("table", ["Move", "When", "In", "Out", "Why"],
                                           [[x["kind"].replace("_", " "), x["situation"], names.get(x["bench_player_id"], "?"),
                                             names.get(x["replaces_player_id"], "?"), x["reason"]] for x in s["substitutions"]])]
        return b + [("p", s["summary"])]
    if name == "pitching_plan":
        st = s["starter"]
        names = {x["player_id"]: x["name"] for x in s["bullpen"]}
        b = [("h", f"Starter: {st['name']} ({st['throws']}HP)"), ("p", st["reason"]),
             ("p", f"Target: about {_f(st['expected_innings'])} innings, pitch-count limit {st['pitch_count_limit']}.")]
        if st.get("plan_written_for"):
            b.append(("p", f"Note: the starter was changed by the manager; the pitch mix below was written for "
                           f"{st['plan_written_for']}."))
        b += [("table", ["Pitch", "% vs LHB", "% vs RHB", "Purpose"],
               [[m["pitch"], _f(m["vs_lhb_pct"], 1), _f(m["vs_rhb_pct"], 1), m["purpose"]] for m in st["pitch_mix"]]),
              ("bullets", st["keys"]), ("h", "Bullpen roles"),
              ("table", ["Pitcher", "Throws", "Role", "Note"],
               [[x["name"], x["throws"], x["role"].replace("_", " "), x["note"]]
                for x in sorted(s["bullpen"], key=lambda x: ROLE_ORDER.index(x["role"]))]),
              ("h", "Game scenarios"),
              ("table", ["Situation", "Plan", "Relievers in order"],
               [[x["scenario"].replace("_", " "), x["plan"], ", ".join(names.get(p, str(p)) for p in x["pitcher_ids"])]
                for x in s["scenarios"]]),
              ("p", s["summary"])]
        return b
    if name == "opposing_pitchers_report":
        sp = s["opposing_starter"]
        alt = f" Alternatives: {', '.join(sp['alternatives'])}." if sp.get("alternatives") else ""
        mrow = lambda m: [m["name"], _f(m["expected_xwoba"]), m["edge"], m["note"]]  # noqa: E731
        return [("h", f"Expected starter: {sp['name']} ({sp['throws']}HP), confidence: {sp['confidence']}"),
                ("p", alt.strip()) if alt else ("p", ""),
                ("table", ["Pitch", "Usage %", "Velo", "Whiff %", "Note"],
                 [[a["pitch"], _f(a["usage_pct"], 1), _f(a["velo"], 1), _f(a["whiff_pct"], 1), a["note"]] for a in s["arsenal"]]),
                ("h", "How to attack him"), ("bullets", s["how_to_attack"]),
                ("h", "Best matchups"), ("table", ["Hitter", "Exp. xwOBA", "Edge", "Note"], [mrow(m) for m in s["best_matchups"]]),
                ("h", "Toughest matchups"), ("table", ["Hitter", "Exp. xwOBA", "Edge", "Note"], [mrow(m) for m in s["toughest_matchups"]]),
                ("h", "Their bullpen to watch"), ("table", ["Reliever", "Throws", "Note"],
                                                   [[r["name"], r["throws"], r["note"]] for r in s["bullpen_to_watch"]]),
                ("p", s["summary"])]
    if name == "opposing_hitters_report":
        lu = lambda rows: [[e["slot"], e["name"], e["position"], e["bats"]] for e in sorted(rows, key=lambda e: e["slot"])]  # noqa: E731
        return [("h", "Their lineup if we start a right-hander"), ("table", ["#", "Hitter", "Pos", "Bats"], lu(s["lineup_vs_rhp"])),
                ("h", "Their lineup if we start a left-hander"), ("table", ["#", "Hitter", "Pos", "Bats"], lu(s["lineup_vs_lhp"])),
                ("h", "How to pitch them"),
                ("table", ["Hitter", "Bats", "Threat", "xwOBA", "Weakness", "How to pitch him"],
                 [[h["name"], h["bats"], h["threat"], _f(h.get("xwoba")), h["weakness"], h["how_to_pitch"]]
                  for h in sorted(s["hitters"], key=lambda h: ["high", "medium", "low"].index(h["threat"]))]),
                ("p", s["summary"])]
    if name == "medical_report":
        return [("table", ["Player", "Status", "Reason"],
                 [[x["name"], x["status"].replace("_", " "), x["reason"]] for x in s["statuses"]]
                 or [["Everyone available", "", ""]]), ("p", s["summary"])]
    if name == "manager_review":
        b = [("p", s["summary"]), ("h", "Keys to the game"), ("bullets", s["keys_to_the_game"]),
             ("h", "Key decisions"), ("bullets", s["key_decisions"])]
        if plan.get("staff_notes"):
            b += [("h", "Staff notes"), ("p", plan["staff_notes"])]
        if plan.get("edit_log"):
            b += [("h", "Changes made by the manager"), ("bullets", [c for e in plan["edit_log"] for c in e["changes"]])]
        return b
    # briefings
    return [("h", s["headline"]), ("p", s["message"]), ("bullets", s["reminders"])]


def header_lines(plan: dict) -> tuple[str, str]:
    g = plan["game"]
    where = "vs" if g["home_away"] == "home" else "at"
    return (f"{g['team']} {where} {g['opponent']}",
            f"{g['game_date']} | {g['venue']} | Stats: {g['stats_basis']}")


# ---------------------------------------------------------------------------
# Blocks -> HTML
# ---------------------------------------------------------------------------

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1b1f24;margin:0;background:#f6f4ef}
header{background:var(--p);color:#fff;padding:18px 28px;border-bottom:6px solid var(--s)}
header h1{margin:0;font-size:22px;letter-spacing:.5px}header .t{font-size:13px;opacity:.9;margin-top:4px}
header .doc{font-size:12px;text-transform:uppercase;letter-spacing:2px;opacity:.8}
main{max-width:980px;margin:0 auto;padding:18px 28px 40px}
h2{color:var(--p);font-size:17px;margin:22px 0 8px;border-bottom:2px solid var(--s);padding-bottom:4px}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff;margin:6px 0}
th{background:var(--p);color:#fff;text-align:left;padding:6px 8px;font-weight:600}
td{padding:6px 8px;border-bottom:1px solid #e3e0d8;vertical-align:top}tr:nth-child(even) td{background:#fbfaf7}
p{line-height:1.5;font-size:14px}li{margin:3px 0;font-size:14px}
footer{font-size:11px;color:#777;text-align:center;padding:16px}
@media print{body{background:#fff}header{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def to_html(title: str, plan: dict, blocks: list[Block]) -> str:
    c = colors(plan["game"]["team_id"])
    head, sub = header_lines(plan)
    e = html.escape
    parts = []
    for b in blocks:
        if b[0] == "h":
            parts.append(f"<h2>{e(b[1])}</h2>")
        elif b[0] == "p" and b[1]:
            parts.append(f"<p>{e(b[1])}</p>")
        elif b[0] == "bullets":
            parts.append("<ul>" + "".join(f"<li>{e(str(x))}</li>" for x in b[1]) + "</ul>")
        elif b[0] == "table":
            th = "".join(f"<th>{e(h)}</th>" for h in b[1])
            rows = "".join("<tr>" + "".join(f"<td>{e(str(v))}</td>" for v in r) + "</tr>" for r in b[2])
            parts.append(f"<table><tr>{th}</tr>{rows}</table>")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{e(title)}</title>"
            f"<style>:root{{--p:{c['primary']};--s:{c['secondary']}}}{CSS}</style></head><body>"
            f"<header><div class='doc'>{e(title)}</div><h1>{e(head)}</h1><div class='t'>{e(sub)}</div></header>"
            f"<main>{''.join(parts)}</main><footer>MLB Virtual Manager | plan {e(plan['run_id'])} | "
            "every number comes from the app's data tools; review before sharing</footer></body></html>")


# ---------------------------------------------------------------------------
# Blocks -> PDF (fpdf2, pure Python)
# ---------------------------------------------------------------------------

def _latin(text: Any) -> str:
    """The built-in PDF fonts cover Latin-1 (José, Muñoz, Sánchez); anything else is simplified."""
    t = str(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-").replace("…", "...")
    try:
        t.encode("latin-1")
        return t
    except UnicodeEncodeError:
        return unicodedata.normalize("NFKD", t).encode("latin-1", "ignore").decode("latin-1")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class _PacketPDF(FPDF):
    footer_text = ""

    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, self.footer_text + f" | page {self.page_no()}", align="C")


def to_pdf(title: str, plan: dict, blocks: list[Block]) -> bytes:
    c = colors(plan["game"]["team_id"])
    head, sub = header_lines(plan)
    pdf = _PacketPDF(orientation="P", unit="mm", format="Letter")
    pdf.footer_text = _latin(f"MLB Virtual Manager | plan {plan['run_id']}")
    pdf.set_auto_page_break(True, margin=14)
    pdf.add_page()
    pdf.set_fill_color(*_rgb(c["primary"]))
    pdf.rect(0, 0, pdf.w, 30, "F")
    pdf.set_fill_color(*_rgb(c["secondary"]))
    pdf.rect(0, 30, pdf.w, 2, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(12, 6)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 4, _latin(title.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(12)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _latin(head), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(12)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.multi_cell(pdf.w - 24, 3.6, _latin(sub))
    pdf.set_text_color(27, 31, 36)
    pdf.set_y(36)
    for b in blocks:
        if b[0] == "h":
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*_rgb(c["primary"]))
            pdf.cell(0, 6, _latin(b[1]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(27, 31, 36)
        elif b[0] == "p" and b[1]:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(0, 4.6, _latin(b[1]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif b[0] == "bullets":
            pdf.set_font("Helvetica", "", 9.5)
            for x in b[1]:
                pdf.multi_cell(0, 4.6, _latin(f"- {x}"), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif b[0] == "table" and b[2]:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_fill_color(247, 245, 240)
            pdf.set_draw_color(215, 211, 202)
            widths = _widths(b[1], b[2])
            with pdf.table(col_widths=widths, line_height=4.2, padding=1.2, cell_fill_color=(247, 245, 240),
                           cell_fill_mode="ROWS", headings_style=_heading_style(c["primary"])) as table:
                for row in [b[1], *b[2]]:
                    r = table.row()
                    for v in row:
                        r.cell(_latin(v))
            pdf.ln(2)
    return bytes(pdf.output())


def _heading_style(primary: str):
    from fpdf.fonts import FontFace
    return FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=_rgb(primary))


def _widths(headers: list[str], rows: list[list[Any]]) -> tuple[float, ...]:
    """Column widths proportional to content, with long text columns capped."""
    lengths = [max([len(str(r[i])) for r in rows] or [0]) for i in range(len(headers))]
    return tuple(min(max(n, len(h) + 3, 4), 60) for n, h in zip(lengths, headers))


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------

def export_zip(plan: dict, packets: dict[str, list[str]]) -> bytes:
    buf = io.BytesIO()
    g = plan["game"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for audience, names in packets.items():
            for i, name in enumerate(names, 1):
                if not plan["sections"].get(name):
                    continue
                title = TITLES[name]
                blocks = blocks_for(name, plan)
                base = f"{audience}/{i:02d}_{name}"
                z.writestr(f"{base}.html", to_html(title, plan, blocks))
                z.writestr(f"{base}.pdf", to_pdf(title, plan, blocks))
        z.writestr("README.txt", (
            f"MLB Virtual Manager game plan: {g['team']} vs {g['opponent']}, {g['game_date']}\n\n"
            "hitters/   for position players: lineup card, scouting report on their pitchers, hitters' briefing\n"
            "pitchers/  for pitchers: pitching plan, scouting report on their hitters, pitchers' briefing\n"
            "coaches/   for the coaching staff: everything, including the medical report and manager's game plan\n\n"
            "Each document comes as HTML (open in any browser) and PDF (print or share).\n"))
    return buf.getvalue()
