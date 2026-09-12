from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

styles = getSampleStyleSheet()

navy   = colors.HexColor("#1E2761")
gray   = colors.HexColor("#5B6270")
lightg = colors.HexColor("#F4F5F7")
line_c = colors.HexColor("#D7DBE3")

title_style = ParagraphStyle("TitleX", parent=styles["Title"], textColor=navy, fontSize=20, spaceAfter=2)
sub_style   = ParagraphStyle("SubX", parent=styles["Normal"], textColor=gray, fontSize=10, spaceAfter=16)
body_style  = ParagraphStyle("BodyX", parent=styles["Normal"], fontSize=10.5, leading=16, spaceAfter=10)
cell_b_style= ParagraphStyle("CellBX", parent=styles["Normal"], fontSize=9.5, leading=13, fontName="Helvetica-Bold")
cell_style  = ParagraphStyle("CellX", parent=styles["Normal"], fontSize=9.5, leading=13)
caption_style = ParagraphStyle("CapX", parent=styles["Normal"], fontSize=8, textColor=gray, spaceAfter=6)

def P(text, style=cell_style):
    return Paragraph(text, style)

doc = SimpleDocTemplate(
    "Error_Clustering_Explained.pdf", pagesize=A4,
    topMargin=20*mm, bottomMargin=18*mm, leftMargin=20*mm, rightMargin=20*mm,
)

story = []

story.append(Paragraph("Error Clustering — Plain-Language Explainer", title_style))
story.append(Paragraph(
    "Real-Time AI Evaluation Engine &mdash; Weak Area Detection module",
    sub_style
))
story.append(HRFlowable(width="100%", thickness=0.8, color=line_c, spaceAfter=14))

story.append(Paragraph(
    "It's the system's way of asking &ldquo;<i>is there a pattern in how this student gets things "
    "wrong, not just how often?</i>&rdquo; &mdash; instead of just counting wrong answers, it looks "
    "at <b>how</b> each wrong answer happened (how fast, how many tries, how hard the question was) "
    "and groups similar mistakes together to figure out the <b>type</b> of struggle, not just the "
    "fact of it.",
    body_style
))

story.append(Paragraph(
    "Every wrong answer gets tagged with 4 details &mdash; skill, answer time, number of attempts, "
    "and question difficulty &mdash; and a clustering algorithm (KMeans) groups the student's recent "
    "wrong answers into one of five behaviour types:",
    body_style
))

rows = [
    [P("Pattern", cell_b_style), P("What it looks like", cell_b_style)],
    [P("Impulsive"), P("Answering wrong, fast &mdash; guessing without really reading")],
    [P("Systematic"), P("Same type of mistake, repeatedly &mdash; a genuine misconception")],
    [P("Struggling"), P("Slow <i>and</i> wrong, repeatedly, on the same skill &mdash; a real knowledge gap")],
    [P("Difficulty spike"), P("Only wrong on the hardest questions &mdash; actually knows the basics fine")],
    [P("Careless"), P("One-off wrong answer, inconsistent with otherwise-good performance &mdash; just a slip")],
]
t = Table(rows, colWidths=[42*mm, 128*mm])
t.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), navy),
    ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("GRID", (0,0), (-1,-1), 0.5, line_c),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, lightg]),
    ("TOPPADDING", (0,0), (-1,-1), 7),
    ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ("LEFTPADDING", (0,0), (-1,-1), 7),
    ("RIGHTPADDING", (0,0), (-1,-1), 7),
]))
story.append(t)
story.append(Spacer(1, 14))

story.append(Paragraph(
    "<b>The point:</b> two students can both be &ldquo;at 40% accuracy,&rdquo; but one is guessing "
    "carelessly and the other has a real gap &mdash; this tells the tutor <i>which one</i> it's "
    "dealing with, so it can react differently (slow down and ask them to read carefully vs. "
    "actually re-teach the concept).",
    body_style
))

story.append(Spacer(1, 10))
story.append(HRFlowable(width="100%", thickness=0.6, color=line_c, spaceAfter=8))
story.append(Paragraph(
    "Source: personalized-robot- / code / Backend / app / ml / error_clustering.py",
    caption_style
))

doc.build(story)
print("PDF written.")
