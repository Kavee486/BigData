from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

styles = getSampleStyleSheet()

navy   = colors.HexColor("#1E2761")
ice    = colors.HexColor("#EEF2FB")
green  = colors.HexColor("#2C6B4F")
red    = colors.HexColor("#A8433A")
gray   = colors.HexColor("#5B6270")
lightg = colors.HexColor("#F4F5F7")

title_style = ParagraphStyle("TitleX", parent=styles["Title"], textColor=navy, fontSize=20, spaceAfter=2)
sub_style   = ParagraphStyle("SubX", parent=styles["Normal"], textColor=gray, fontSize=10, spaceAfter=14)
h2_style    = ParagraphStyle("H2X", parent=styles["Heading2"], textColor=navy, fontSize=13, spaceBefore=16, spaceAfter=6)
body_style  = ParagraphStyle("BodyX", parent=styles["Normal"], fontSize=9.5, leading=13.5)
cell_style  = ParagraphStyle("CellX", parent=styles["Normal"], fontSize=8.7, leading=11.5)
cell_b_style= ParagraphStyle("CellBX", parent=styles["Normal"], fontSize=8.7, leading=11.5, fontName="Helvetica-Bold")
mono_style  = ParagraphStyle("MonoX", parent=styles["Normal"], fontName="Courier", fontSize=8.5, leading=12, textColor=navy)
caption_style = ParagraphStyle("CapX", parent=styles["Normal"], fontSize=8, textColor=gray, spaceAfter=10)

def P(text, style=cell_style):
    return Paragraph(text, style)

doc = SimpleDocTemplate(
    "Learning_Pace_7_Signal_Votes.pdf", pagesize=A4,
    topMargin=18*mm, bottomMargin=16*mm, leftMargin=18*mm, rightMargin=18*mm,
)

story = []

story.append(Paragraph("The 7 Signal-Vote Learning Pace Predictor", title_style))
story.append(Paragraph(
    "Real-Time AI Evaluation Engine &mdash; Learning Pace Analysis module &nbsp;|&nbsp; "
    "Source: <font face='Courier'>app/ml/pace_predictor.py</font>",
    sub_style
))
story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#D7DBE3"), spaceAfter=10))

story.append(Paragraph(
    "Every student interaction history is scored by seven independent, rule-based signals &mdash; "
    "no machine-learning training required. Each signal casts exactly one vote: "
    "<b>+1</b> (evidence of a fast learner), <b>&minus;1</b> (evidence of a slow learner), or "
    "<b>0</b> (inconclusive / not enough evidence). The seven votes are summed into one score "
    "from &minus;7 to +7, which is then mapped to a FAST / MEDIUM / SLOW pace label.",
    body_style
))

story.append(Paragraph("1&nbsp;&nbsp;The Seven Signals", h2_style))

header = [P("#", cell_b_style), P("Signal", cell_b_style), P("What it measures", cell_b_style),
          P("+1&nbsp;FAST if&hellip;", cell_b_style), P("&minus;1&nbsp;SLOW if&hellip;", cell_b_style),
          P("0&nbsp;neutral", cell_b_style)]

rows_data = [
    ("1", "Overall accuracy", "Fraction of all attempts answered correctly",
     "&gt; 75%", "&lt; 45%", "45&ndash;75%"),
    ("2", "Average response time", "Mean seconds taken per answer",
     "&lt; 25s", "&gt; 80s", "25&ndash;80s"),
    ("3", "Accuracy trend*", "Recent accuracy vs. earlier accuracy (needs &ge;12 interactions)",
     "improved &ge; +10&nbsp;pp", "dropped &ge; &minus;10&nbsp;pp", "stable / not enough data"),
    ("4", "Response-time trend*", "Recent avg. time vs. earlier avg. time",
     "&ge;10s faster", "&ge;10s slower", "stable / not enough data"),
    ("5", "Max correct streak", "Longest run of consecutive correct answers, ever",
     "&ge; 5 in a row", "0 (never once streaked)", "1&ndash;4 in a row"),
    ("6", "Recent wrong streak", "Wrong answers within the last 5 attempts",
     "0 wrong in last 5", "&ge; 4 wrong in last 5", "1&ndash;3 wrong"),
    ("7", "Experience depth", "Total number of interactions logged so far",
     "&ge; 30 interactions", "&lt; 5 interactions", "5&ndash;30 interactions"),
]

table_rows = [header]
for r in rows_data:
    table_rows.append([
        P(r[0], cell_b_style), P(r[1], cell_b_style), P(r[2]), P(r[3]), P(r[4]), P(r[5]),
    ])

col_widths = [9*mm, 30*mm, 46*mm, 32*mm, 32*mm, 25*mm]
t = Table(table_rows, colWidths=col_widths, repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), navy),
    ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ALIGN", (0,0), (0,-1), "CENTER"),
    ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#D7DBE3")),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, lightg]),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING", (0,0), (-1,-1), 5),
    ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(t)
story.append(Paragraph(
    "* trend signals compare the most recent slice of interactions against the earlier ones; "
    "they stay at 0 until the student has at least 12 logged interactions.",
    caption_style
))

story.append(Paragraph("2&nbsp;&nbsp;Turning Seven Votes Into One Label", h2_style))
story.append(Paragraph(
    "The seven +1 / &minus;1 / 0 votes are summed into a single integer <b>score</b> "
    "(range &minus;7 to +7). No single signal can decide the outcome alone &mdash; a real "
    "cluster of agreeing evidence is required before the system commits to FAST or SLOW.",
    body_style
))

score_header = [P("Total score", cell_b_style), P("Label", cell_b_style), P("Confidence formula", cell_b_style)]
score_rows = [
    score_header,
    [P("&ge; +3"), P("<font color='#2C6B4F'><b>FAST</b></font>", cell_style),
     Paragraph("0.60 + 0.08 &times; min(score &minus; 2, 5), capped at 0.98", mono_style)],
    [P("&minus;2 to +2"), P("<b>MEDIUM</b>", cell_style),
     Paragraph("0.55 + 0.05 &times; (2 &minus; |score|)", mono_style)],
    [P("&le; &minus;3"), P("<font color='#A8433A'><b>SLOW</b></font>", cell_style),
     Paragraph("0.60 + 0.08 &times; min(|score| &minus; 2, 5), capped at 0.98", mono_style)],
]
t2 = Table(score_rows, colWidths=[28*mm, 22*mm, 124*mm])
t2.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), navy),
    ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("ALIGN", (0,0), (1,-1), "CENTER"),
    ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#D7DBE3")),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, lightg]),
    ("TOPPADDING", (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("LEFTPADDING", (0,0), (-1,-1), 5),
    ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(t2)

story.append(Paragraph(
    "<b>Worked example:</b> a student with 82% accuracy (+1), 18s average response time (+1), "
    "only 8 logged interactions so trend signals 3 &amp; 4 stay inconclusive (0, 0), "
    "a 6-answer correct streak (+1), 0 wrong in the last 5 (+1), and 8 total interactions "
    "which is neither &ge;30 nor &lt;5 (0) &mdash; sums to a score of <b>+4</b>, which is "
    "&ge; the FAST threshold of +3, giving pace = <b>FAST</b> with confidence "
    "0.60&nbsp;+&nbsp;0.08&times;min(4&minus;2,5)&nbsp;=&nbsp;<b>0.76</b>.",
    body_style
))

story.append(Paragraph("3&nbsp;&nbsp;What the Pace Label Actually Changes", h2_style))
story.append(Paragraph(
    "The resulting FAST / MEDIUM / SLOW label is translated by "
    "<font face='Courier'>AdaptiveContentDelivery</font> into concrete instructions injected "
    "into the tutor LLM's system prompt for every response &mdash; not just a label shown on a "
    "dashboard.",
    body_style
))

deliv_header = [P("Pace", cell_b_style), P("Explanation depth", cell_b_style),
                P("Examples", cell_b_style), P("Hints", cell_b_style), P("Pacing", cell_b_style)]
deliv_rows = [
    deliv_header,
    [P("<font color='#2C6B4F'><b>FAST</b></font>"),
     P("Brief &mdash; skip unrequested basics"),
     P("1, tight, no elaboration unless asked"),
     P("Minimal &mdash; only if explicitly requested"),
     P("Move quickly; introduce next concept proactively")],
    [P("<b>MEDIUM</b>"),
     P("Moderate &mdash; key steps, no over-detail"),
     P("2 (one standard, one variation)"),
     P("On-demand &mdash; only when visibly stuck"),
     P("Steady; check understanding before moving on")],
    [P("<font color='#A8433A'><b>SLOW</b></font>"),
     P("Detailed &mdash; define every term, smallest possible steps"),
     P("2&ndash;3 worked examples, increasing complexity"),
     P("Proactive &mdash; offered before the student asks"),
     P("Go slowly; confirm each sub-concept before continuing")],
]
t3 = Table(deliv_rows, colWidths=[16*mm, 40*mm, 38*mm, 38*mm, 42*mm])
t3.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), navy),
    ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#D7DBE3")),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, lightg]),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING", (0,0), (-1,-1), 5),
    ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(t3)

story.append(Spacer(1, 14))
story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#D7DBE3")))
story.append(Paragraph(
    "Why this design works from session one: every threshold above (0.75 accuracy, 25s response "
    "time, 5-answer streak, etc.) is a fixed constant &mdash; nothing is learned from a training "
    "dataset. Signal 7 (experience depth) is what keeps a brand-new student from breaking the "
    "system: with 0 interactions, signals 3 &amp; 4 automatically stay at 0 (they require &ge;12 "
    "data points), and signal 7 itself casts a &minus;1 vote for having fewer than 5 interactions "
    "&mdash; so a first-time student is naturally scored toward SLOW/MEDIUM rather than the "
    "predictor failing or needing history to exist first.",
    caption_style
))
story.append(Paragraph(
    "Source: personalized-robot- / code / Backend / app / ml / pace_predictor.py",
    caption_style
))

doc.build(story)
print("PDF written.")
