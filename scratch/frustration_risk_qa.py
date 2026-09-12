from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

styles = getSampleStyleSheet()

navy   = colors.HexColor("#1E2761")
green  = colors.HexColor("#2C6B4F")
red    = colors.HexColor("#A8433A")
gray   = colors.HexColor("#5B6270")
lightg = colors.HexColor("#F4F5F7")
line_c = colors.HexColor("#D7DBE3")

title_style = ParagraphStyle("TitleX", parent=styles["Title"], textColor=navy, fontSize=19, spaceAfter=2)
sub_style   = ParagraphStyle("SubX", parent=styles["Normal"], textColor=gray, fontSize=10, spaceAfter=14)
q_style     = ParagraphStyle("QX", parent=styles["Heading2"], textColor=colors.white, fontSize=11.5,
                              spaceBefore=0, spaceAfter=0, leading=15)
a_style     = ParagraphStyle("AX", parent=styles["Normal"], fontSize=9.7, leading=14, spaceAfter=4)
cell_style  = ParagraphStyle("CellX", parent=styles["Normal"], fontSize=8.6, leading=11.5)
cell_b_style= ParagraphStyle("CellBX", parent=styles["Normal"], fontSize=8.6, leading=11.5, fontName="Helvetica-Bold")
mono_style  = ParagraphStyle("MonoX", parent=styles["Normal"], fontName="Courier", fontSize=8.3, leading=11.5, textColor=navy)
quote_style = ParagraphStyle("QuoteX", parent=styles["Normal"], fontSize=8.8, leading=12.5,
                              leftIndent=10, textColor=colors.HexColor("#333333"),
                              borderColor=line_c, borderWidth=0.6, borderPadding=8,
                              backColor=lightg)
caption_style = ParagraphStyle("CapX", parent=styles["Normal"], fontSize=7.8, textColor=gray, spaceAfter=10)

def P(text, style=cell_style):
    return Paragraph(text, style)

def q_block(number, question):
    """Return a Table acting as a dark question banner."""
    t = Table([[Paragraph(f"Q{number}.  {question}", q_style)]], colWidths=[172*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), navy),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING", (0,0), (-1,-1), 9),
        ("RIGHTPADDING", (0,0), (-1,-1), 9),
    ]))
    return t

doc = SimpleDocTemplate(
    "Frustration_Risk_QA.pdf", pagesize=A4,
    topMargin=16*mm, bottomMargin=15*mm, leftMargin=19*mm, rightMargin=19*mm,
)

story = []

story.append(Paragraph("Frustration-Risk Score &mdash; Q&amp;A", title_style))
story.append(Paragraph(
    "How it's calculated, where its inputs come from, and what the tutor actually does with it. "
    "Source: <font face='Courier'>app/ml/multimodal_fusion.py</font>, "
    "<font face='Courier'>app/ml/agents/pedagogical_agent.py</font>, "
    "<font face='Courier'>app/ml/agents/content_agent.py</font>, "
    "<font face='Courier'>app/ml/agents/diagnostic_agent.py</font>",
    sub_style
))
story.append(HRFlowable(width="100%", thickness=0.8, color=line_c, spaceAfter=12))

# ── Q1 ──────────────────────────────────────────────────────────────────────
story.append(q_block(1, "What is frustration risk?"))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "A single number from 0 to 1, computed fresh on every tutoring turn, estimating "
    "<b>“is this student about to give up”</b> — not “is this student unhappy.” "
    "It is a rule-based proxy built from evidence of struggle (bad performance, low mastery, "
    "uncertain speech, and optionally facial emotion), not a direct measurement of feelings.",
    a_style
))
story.append(Spacer(1, 10))

# ── Q2 ──────────────────────────────────────────────────────────────────────
story.append(q_block(2, "What signals go into it — where does it get its data from?"))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Three independent modalities are combined by <font face='Courier'>MultimodalFusion.fuse()</font>, "
    "each with a fixed reliability weight used elsewhere in the fusion (BKT is always available, "
    "camera/mic only when active):",
    a_style
))
sig_rows = [
    [P("Signal", cell_b_style), P("Source", cell_b_style), P("Availability", cell_b_style)],
    [P("BKT mastery"), P("Bayesian Knowledge Tracing — specifically <font face='Courier'>bkt_min</font>, "
                          "the learner's <i>weakest</i> skill, not the average"), P("Always available")],
    [P("Recent accuracy"), P("Fraction correct over the last ~10 questions answered"), P("Always available")],
    [P("Audio confidence"), P("Speech-to-text analysis confidence from the microphone"), P("Only when mic is used")],
    [P("Facial emotion"), P("DeepFace CNN classification of webcam frames — blended in separately, "
                             "see Q4"), P("Only when camera is on")],
]
t = Table(sig_rows, colWidths=[30*mm, 100*mm, 42*mm])
t.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), navy), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("GRID", (0,0), (-1,-1), 0.5, line_c), ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, lightg]),
    ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(t)
story.append(Spacer(1, 10))

# ── Q3 ──────────────────────────────────────────────────────────────────────
story.append(q_block(3, "How exactly is it calculated — the formula?"))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "It's a points system, not a weighted average. Four rules each independently add a fixed "
    "amount to a running total (capped at 1.0), from <font face='Courier'>multimodal_fusion.py</font>:",
    a_style
))
story.append(Paragraph(
    "frustration_risk = 0.0<br/>"
    "if recent_accuracy &lt; 0.4:&nbsp;&nbsp;&nbsp; frustration_risk += 0.3<br/>"
    "if bkt_min &lt; 0.3:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; frustration_risk += 0.3<br/>"
    "if audio_confidence &lt; 0.3:&nbsp; frustration_risk += 0.2&nbsp; (only if mic is on)<br/>"
    "if attempts &gt; 5 and recent_accuracy &lt; 0.3:&nbsp; frustration_risk += 0.2<br/>"
    "frustration_risk = min(1.0, frustration_risk)",
    mono_style
))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "<b>Why 0.3 / 0.3 / 0.2 / 0.2?</b> The four weights sum to exactly 1.0 by design: if every "
    "warning sign fires at once, the score lands exactly at the ceiling. The two <b>0.3</b> weights "
    "go to the most direct, always-available, hardware-independent signals (current accuracy and the "
    "weakest-skill BKT mastery). The two <b>0.2</b> weights go to weaker or more conditional evidence: "
    "audio confidence is only a <i>proxy</i> for uncertainty (could just be a quiet mic), and the "
    "“persistence” rule is largely redundant with the accuracy rule already firing — "
    "so it adds less new information. <b>Why the minimum skill, not the average?</b> A student with five "
    "skills at 90% and one stuck at 10% would look fine on average (~75%) — using the minimum "
    "catches the one skill actually causing frustration instead of smoothing it away.",
    a_style
))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Note: these exact weights are a hand-tuned heuristic in the code, not a value derived from a "
    "study or trained on data.",
    caption_style
))
story.append(Spacer(1, 8))

# ── Q4 (own page start naturally) ────────────────────────────────────────────
story.append(q_block(4, "Is that the whole calculation, or does anything else feed into it?"))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "One more step happens afterward, in <font face='Courier'>diagnostic_agent.py</font>: if the "
    "camera is on and DeepFace produced a real facial-emotion frustration score, it gets blended "
    "into the number above at a fixed ratio:",
    a_style
))
story.append(Paragraph(
    "if emotion_frustration_score &gt; 0:<br/>"
    "&nbsp;&nbsp;&nbsp; frustration_risk = frustration_risk &times; 0.6 + emotion_frustration_score &times; 0.4",
    mono_style
))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "So the behavioural/performance score (accuracy + mastery + voice) always carries the majority "
    "weight (60%), with facial emotion capped at a 40% influence — camera data adjusts the "
    "score, it never fully overrides it on its own at this stage.",
    a_style
))
story.append(Spacer(1, 10))

# ── Q5 ──────────────────────────────────────────────────────────────────────
story.append(q_block(5, "What is it used for — what does the system actually do with it?"))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Three concrete, escalating uses — not just a number shown on a dashboard:",
    a_style
))
use_rows = [
    [P("Trigger", cell_b_style), P("What fires", cell_b_style), P("Effect", cell_b_style)],
    [P("frustration_risk &ge; 0.75"), P("<font face='Courier'>PedagogicalAgent</font> forces "
        "<font face='Courier'>TeachingAction.ENCOURAGE</font>, overriding whatever the normal "
        "mastery/ZPD logic would have picked"),
        P("Hard override — runs before any other teaching decision")],
    [P("frustration_risk 0.40–0.75<br/>(with a real camera/mic signal)"),
        P("An “IMPORTANT” alert line is inserted into the LLM's system prompt"),
        P("Softer nudge — tells the model the student seems to be struggling, "
          "without forcing a specific action")],
    [P("frustration_risk &lt; 0.40"), P("No override, no alert"),
        P("Normal teaching action proceeds (explain / hint / advance / remediate as usual)")],
]
t2 = Table(use_rows, colWidths=[35*mm, 68*mm, 69*mm])
t2.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), navy), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("GRID", (0,0), (-1,-1), 0.5, line_c), ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, lightg]),
    ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
]))
story.append(t2)
story.append(Spacer(1, 10))

# ── Q6 ──────────────────────────────────────────────────────────────────────
story.append(q_block(6, "When it overrides the tutor, what does the student actually see change?"))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "The exact instruction injected into the LLM's system prompt when ENCOURAGE fires "
    "(from <font face='Courier'>pedagogical_agent.py</font>):",
    a_style
))
story.append(Paragraph(
    "“ENGAGEMENT ALERT: frustration risk 82%, overall engagement 31%&hellip; The student is "
    "showing signs of frustration or disengagement. <b>DO NOT ask a new question or add complexity.</b> "
    "Acknowledge their effort warmly, normalise the difficulty, and offer ONE tiny, achievable next "
    "step. Use encouraging language. Keep it short and supportive.”",
    quote_style
))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Three concrete behaviour changes result: <b>(1) pacing freezes</b> — no new questions or "
    "harder material, regardless of what mastery/ZPD would otherwise recommend; "
    "<b>(2) scope shrinks</b> — the response is limited to one small, achievable step instead "
    "of a full explanation; <b>(3) tone shifts</b> — the model is directed to validate the "
    "student emotionally before anything academic, and to keep it brief.",
    a_style
))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "There is also a stronger tier, used only when the <i>camera</i> directly detects real "
    "distress (angry / disgust / fear / sad &ge; 70% via DeepFace), which is even more restrictive: "
    "“<b>DO NOT continue with new content.</b> Acknowledge the difficulty with empathy, "
    "validate their feelings&hellip;” — this blocks new academic content entirely, "
    "not just new questions.",
    a_style
))

doc.build(story)
print("PDF written.")
