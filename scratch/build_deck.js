const pptxgen = require("pptxgenjs");

const COL = {
  bg: "FFFFFF",
  ink: "1F2430",
  muted: "6B7280",
  line: "C7CCD6",
  orange: "D99A3E", orangeFill: "FDF0D5",
  blue: "5B84C4", blueFill: "E3ECFB",
  purple: "8862C9", purpleFill: "ECE3F8",
  green: "5FA96F", greenFill: "E2F3E5",
  gray: "9AA1B2", grayFill: "F1F2F5",
};

function box(slide, x, y, w, h, text, {fill, line, bold=true, size=12, sub, subSize=9.5, italic=false, align="ctr", rectRadius=0.08} = {}) {
  slide.addShape("roundRect", { x, y, w, h, rectRadius, fill: { color: fill }, line: { color: line, width: 1.25 } });
  if (sub) {
    slide.addText(
      [
        { text: text, options: { bold, fontSize: size, color: COL.ink, breakLine: true } },
        { text: sub, options: { fontSize: subSize, color: COL.muted, italic } },
      ],
      { x, y, w, h, align, valign: "middle", fontFace: "Calibri", margin: 4 }
    );
  } else {
    slide.addText(text, { x, y, w, h, align, valign: "middle", fontSize: size, bold, color: COL.ink, fontFace: "Calibri", margin: 4 });
  }
}

function noteBox(slide, x, y, w, h, text, sub) {
  slide.addShape("roundRect", { x, y, w, h, rectRadius: 0.06, fill: { color: COL.grayFill }, line: { color: COL.line, width: 1, dashType: "dash" } });
  slide.addText(
    [
      { text, options: { bold: true, fontSize: 10.5, color: COL.ink, breakLine: true } },
      { text: sub, options: { fontSize: 8.5, color: COL.muted } },
    ],
    { x, y, w, h, align: "ctr", valign: "middle", fontFace: "Calibri", margin: 3 }
  );
}

function arrow(slide, x1, y1, x2, y2, {color=COL.gray, dash=false, width=1.5} = {}) {
  slide.addShape("line", {
    x: Math.min(x1, x2), y: Math.min(y1, y2),
    w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color, width, dashType: dash ? "dash" : "solid", endArrowType: "triangle" },
  });
}

function arrowLabel(slide, cx, cy, text, color=COL.muted) {
  slide.addText(text, { x: cx - 1.1, y: cy - 0.14, w: 2.2, h: 0.28, align: "ctr", fontSize: 8.5, italic: true, color, fontFace: "Calibri", fill: { color: COL.bg } });
}

function laneHeader(slide, x, w, text, color) {
  slide.addText(text, { x, y: 0.9, w, h: 0.32, align: "ctr", fontSize: 12.5, bold: true, color, fontFace: "Calibri" });
}

function title(slide, kicker, main) {
  slide.addText(kicker, { x: 0.5, y: 0.22, w: 10, h: 0.3, fontSize: 12, bold: true, color: COL.muted, fontFace: "Calibri", charSpacing: 1 });
  slide.addText(main, { x: 0.5, y: 0.48, w: 11, h: 0.5, fontSize: 26, bold: true, color: COL.ink, fontFace: "Cambria" });
}

function footer(slide, text, y = 7.12) {
  slide.addText(text, { x: 0.5, y, w: 12.33, h: 0.3, fontSize: 9, italic: true, color: COL.muted, fontFace: "Calibri" });
}

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5

// ---------------------------------------------------------------
// SLIDE 1 — Part 1: Client (frontend-robot-)
// ---------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COL.bg };
  title(s, "SYSTEM ARCHITECTURE · PART 1 OF 2", "Client — Robot & Web Frontend");

  const laneAx = 0.5, laneW = 5.55;
  const laneBx = 7.28;

  laneHeader(s, laneAx, laneW, "Learning Buddy — Robot, Multi-Subject", COL.orange);
  laneHeader(s, laneBx, laneW, "Atlas — Web Tutor / Voice", COL.blue);

  // Row 1 — five subject chips instead of a single "chess" box
  let y = 1.32, h = 0.62;
  const chips = ["Chess", "Math Quest", "Sentence Building", "Puzzle Park", "Learn Anything"];
  const chipGap = 0.14, chipW = (laneW - chipGap * (chips.length - 1)) / chips.length;
  chips.forEach((label, i) => {
    box(s, laneAx + i * (chipW + chipGap), y, chipW, h, label, { fill: COL.orangeFill, line: COL.orange, size: 8.5 });
  });
  box(s, laneBx, y, laneW, h, "Student asks a question", { fill: COL.blueFill, line: COL.blue, sub: "typed, spoken, or via camera/mic engagement signal" });

  // arrow 1
  let ay1 = y + h, ay2 = ay1 + 0.28;
  arrow(s, laneAx + laneW/2, ay1, laneAx + laneW/2, ay2);
  arrow(s, laneBx + laneW/2, ay1, laneBx + laneW/2, ay2);

  // Row 2
  y = ay2;
  box(s, laneAx, y, laneW, h, "Subject Adapter Layer", { fill: COL.orangeFill, line: COL.orange, sub: "shared query/reply for every activity (chess is the evaluated case)", subSize: 9 });
  box(s, laneBx, y, laneW, h, "POST /tutor/ask", { fill: COL.blueFill, line: COL.blue, sub: "or WebSocket /tutor/ask/stream" });

  ay1 = y + h; ay2 = ay1 + 0.28;
  arrow(s, laneAx + laneW/2, ay1, laneAx + laneW/2, ay2);
  arrow(s, laneBx + laneW/2, ay1, laneBx + laneW/2, ay2);
  arrowLabel(s, laneAx + laneW/2, (ay1+ay2)/2, "to Backend →", COL.orange);
  arrowLabel(s, laneBx + laneW/2, (ay1+ay2)/2, "to Backend →", COL.blue);

  // Row 3 - gateway
  y = ay2; h = 0.5;
  noteBox(s, laneAx, y, laneW, h, "⇄  Backend  ·  Part 2", "network boundary — see next slide");
  noteBox(s, laneBx, y, laneW, h, "⇄  Backend  ·  Part 2", "network boundary — see next slide");

  ay1 = y + h; ay2 = ay1 + 0.28;
  arrow(s, laneAx + laneW/2, ay1, laneAx + laneW/2, ay2);
  arrow(s, laneBx + laneW/2, ay1, laneBx + laneW/2, ay2);
  arrowLabel(s, laneAx + laneW/2, (ay1+ay2)/2, "← response", COL.orange);
  arrowLabel(s, laneBx + laneW/2, (ay1+ay2)/2, "← response", COL.blue);

  // Row 4
  y = ay2; h = 0.62;
  box(s, laneAx, y, laneW, h, "Graded feedback + engine reply", { fill: COL.orangeFill, line: COL.orange, sub: "e.g. good / mistake / blunder for chess — TTS audio, per activity" });
  box(s, laneBx, y, laneW, h, "Streamed tutor tokens", { fill: COL.blueFill, line: COL.blue, sub: "shown live in the browser / tutor UI" });

  ay1 = y + h; ay2 = ay1 + 0.26;
  arrow(s, laneAx + laneW/2, ay1, laneAx + laneW/2, ay2);
  arrow(s, laneBx + laneW/2, ay1, laneBx + laneW/2, ay2);

  // Row 5
  y = ay2; h = 0.6;
  box(s, laneAx, y, laneW, h, "Touchscreen + Speaker", { fill: COL.orangeFill, line: COL.orange, sub: "servo gestures accompany playback" });
  box(s, laneBx, y, laneW, h, "Tutor UI renders answer", { fill: COL.blueFill, line: COL.blue, sub: "text + optional voice playback" });

  // Only Atlas (tutor) connects onward to the teacher dashboard —
  // Learning Buddy sessions stay on-device and are not shown there.
  const dy = y + h + 0.32, dh = 0.6;
  arrow(s, laneBx + laneW/2, y + h, laneBx + laneW/2, dy, { color: COL.green });
  box(s, laneBx, dy, laneW, dh, "Teacher Dashboard", { fill: COL.greenFill, line: COL.green, sub: "Atlas class analytics — reads Backend API (Part 2)" });
  s.addText("stays on-device — not shown on\nthe teacher dashboard", {
    x: laneAx, y: dy, w: laneW, h: dh, align: "ctr", valign: "middle",
    fontSize: 9.5, italic: true, color: COL.muted, fontFace: "Calibri",
  });

  footer(s, "Repo: frontend-robot- (Next.js pages/dashboard) + touchscreen/speaker/servo hardware. No grading or reasoning logic lives on this side.");
}

// ---------------------------------------------------------------
// SLIDE 2 — Part 2: Backend (personalized-robot-/code/Backend)
// ---------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: COL.bg };
  title(s, "SYSTEM ARCHITECTURE · PART 2 OF 2", "Backend — Learning Buddy Adapter, Agent Pipeline & Data");

  const laneAx = 0.5, laneW = 4.35;
  const laneBx = 5.35, laneBw = 4.35;
  const noteX = 10.2, noteW = 2.63;

  laneHeader(s, laneAx, laneW, "Learning Buddy Adapter · Chess example", COL.orange);
  laneHeader(s, laneBx, laneBw, "SupervisorAgent Pipeline", COL.purple);

  let y = 1.32, h = 0.56;
  box(s, laneAx, y, laneW, h, "Validity check", { fill: COL.orangeFill, line: COL.orange, sub: "chess: legal move? · others: their own check", size: 11.5, subSize: 8.5 });
  box(s, laneBx, y, laneBw, h, "1 · Perception Agent", { fill: COL.purpleFill, line: COL.purple, sub: "clean the raw input", size: 11.5 });

  let ay1 = y + h, ay2 = ay1 + 0.2;
  arrow(s, laneAx + laneW/2, ay1, laneAx + laneW/2, ay2);
  arrow(s, laneBx + laneBw/2, ay1, laneBx + laneBw/2, ay2);

  y = ay2; h = 0.56;
  box(s, laneAx, y, laneW, h, "Activity scoring", { fill: COL.orangeFill, line: COL.orange, sub: "chess: Stockfish depth 12 · others: own scorer", size: 11.5, subSize: 8.5 });
  box(s, laneBx, y, laneBw, h, "2 · Diagnostic Agent", { fill: COL.purpleFill, line: COL.purple, sub: "read the learner's mastery state", size: 11.5 });

  ay1 = y + h; ay2 = ay1 + 0.2;
  arrow(s, laneAx + laneW/2, ay1, laneAx + laneW/2, ay2);
  arrow(s, laneBx + laneBw/2, ay1, laneBx + laneBw/2, ay2);

  y = ay2; h = 0.56;
  box(s, laneAx, y, laneW, h, "Grade + detect concept", { fill: COL.orangeFill, line: COL.orange, sub: "good / mistake / blunder → skill_id", size: 11.5 });
  box(s, laneBx, y, laneBw, h, "3 · Pedagogical Agent", { fill: COL.purpleFill, line: COL.purple, sub: "choose the teaching action", size: 11.5 });

  ay1 = y + h; ay2 = ay1 + 0.2;
  arrow(s, laneBx + laneBw/2, ay1, laneBx + laneBw/2, ay2);

  y = ay2; h = 0.56;
  box(s, laneBx, y, laneBw, h, "4 · Content Agent", { fill: COL.purpleFill, line: COL.purple, sub: "retrieve context + build the prompt", size: 11.5 });
  noteBox(s, noteX, y - 0.36, noteW, 0.46, "ChromaDB", "curriculum vectors — teacher PDF, top-4 chunks");
  noteBox(s, noteX, y + 0.42, noteW, 0.46, "PostgreSQL", "mastery + interaction history");
  arrow(s, laneBx + laneBw, y + 0.12, noteX, y - 0.13, { color: COL.green, dash: true });
  arrow(s, laneBx + laneBw, y + 0.44, noteX, y + 0.65, { color: COL.green, dash: true });

  ay1 = y + h; ay2 = ay1 + 0.2;
  arrow(s, laneBx + laneBw/2, ay1, laneBx + laneBw/2, ay2);

  y = ay2; h = 0.56;
  box(s, laneBx, y, laneBw, h, "Ollama LLM", { fill: COL.purpleFill, line: COL.purple, sub: "generate the response", size: 11.5 });

  // converge both lanes down to Validate
  const vY = y + h + 0.34, vH = 0.56;
  arrow(s, laneAx + laneW/2, 1.32 + h*3 + 0.4, laneAx + laneW - 0.3, vY, { color: COL.gray });
  arrow(s, laneBx + laneBw/2, y + h, laneBx + laneBw/2, vY, { color: COL.gray });
  box(s, 2.2, vY, 7.6, vH, "Validate the output — five safety checks", { fill: COL.orangeFill, line: COL.orange, sub: "fails once → corrective retry with the LLM · fails again → deterministic fallback template", size: 12 });

  // split to two outcomes
  const oY = vY + vH + 0.22, oH = 0.85;
  arrow(s, 2.2 + 7.6*0.27, vY + vH, 2.2 + 7.6*0.02 + 1.9, oY, { color: COL.blue });
  arrow(s, 2.2 + 7.6*0.73, vY + vH, 2.2 + 7.6*0.98 - 1.9, oY, { color: COL.green });
  box(s, 0.5, oY, 6.1, oH, "Response returned to Part 1", { fill: COL.blueFill, line: COL.blue, sub: "JSON reply + TTS audio (Learning Buddy)  ·  tokens over WebSocket (Atlas)", size: 12, subSize: 9.5 });
  box(s, 6.9, oY, 5.93, oH, "Log interaction · update BKT mastery", { fill: COL.greenFill, line: COL.green, sub: "Atlas tutor sessions notify Teacher Dashboard; Learning Buddy sessions do not.", size: 12, subSize: 9.5 });

  footer(s, "Repo: personalized-robot-/code/Backend — FastAPI (app/api/v1/*) + app/ml/agents/*. Owns all grading, reasoning, retrieval, safety-checking and persistence.", 7.18);
}

pres.writeFile({ fileName: "Robot_Architecture_Split.pptx" }).then(() => console.log("written"));
