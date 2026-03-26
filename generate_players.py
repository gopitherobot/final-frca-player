#!/usr/bin/env python3
"""Generate Final FRCA interactive Q&A player HTML files from transcript JSON cache."""

import json, re, os
from pathlib import Path

BASE_DIR  = Path(__file__).parent
CACHE_DIR = BASE_DIR / "_transcripts_cache"
OUT_DIR   = BASE_DIR / "players"
OUT_DIR.mkdir(exist_ok=True)

# ── Category metadata ──────────────────────────────────────────────────────────
CATEGORIES = {
    "Cardiac_Anaesthesia":       {"label": "Cardiac Anaesthesia",       "color": "#ef4444", "cls": "cat-cardiac"},
    "Day_Stay":                  {"label": "Day Stay",                  "color": "#6b7280", "cls": "cat-daystay"},
    "ENT":                       {"label": "ENT",                       "color": "#f59e0b", "cls": "cat-ent"},
    "Emergency_Medicine":        {"label": "Emergency Medicine",        "color": "#dc2626", "cls": "cat-em"},
    "Endocrinology":             {"label": "Endocrinology",             "color": "#8b5cf6", "cls": "cat-endo"},
    "Gastrointestinal_Tract":    {"label": "Gastrointestinal Tract",    "color": "#f97316", "cls": "cat-git"},
    "Haematological":            {"label": "Haematological",            "color": "#ec4899", "cls": "cat-haem"},
    "Hepatology":                {"label": "Hepatology",                "color": "#b45309", "cls": "cat-hep"},
    "Intensive_Care_Medicine":   {"label": "Intensive Care Medicine",   "color": "#0ea5e9", "cls": "cat-icm"},
    "Metabolism":                {"label": "Metabolism",                "color": "#10b981", "cls": "cat-meta"},
    "Neurosurgical_Anaesthesia": {"label": "Neurosurgical Anaesthesia", "color": "#6366f1", "cls": "cat-neuro"},
    "Obstetrics":                {"label": "Obstetrics",                "color": "#db2777", "cls": "cat-obs"},
    "Ophthalmic":                {"label": "Ophthalmic",                "color": "#059669", "cls": "cat-ophth"},
    "Orthopaedics":              {"label": "Orthopaedics",              "color": "#64748b", "cls": "cat-ortho"},
    "Paediatric_and_Neonatal":   {"label": "Paediatric & Neonatal",     "color": "#fbbf24", "cls": "cat-paeds"},
    "Pain":                      {"label": "Pain",                      "color": "#a855f7", "cls": "cat-pain"},
    "Regional_Anaesthesia":      {"label": "Regional Anaesthesia",      "color": "#2563eb", "cls": "cat-reg"},
    "Renal":                     {"label": "Renal",                     "color": "#0891b2", "cls": "cat-renal"},
    "Thoracics":                 {"label": "Thoracics",                 "color": "#7c3aed", "cls": "cat-thor"},
    "Vascular":                  {"label": "Vascular",                  "color": "#ea580c", "cls": "cat-vasc"},
}

# Interrogative openers that signal a question even without '?'
Q_OPENERS = re.compile(
    r'^(what|how|why|when|where|who|which|can you|could you|tell me|describe|explain|define|'
    r'compare|contrast|classify|outline|give me|list|name|discuss|elaborate|would you)',
    re.IGNORECASE
)

def fmt_time(secs):
    m = int(secs) // 60
    s = int(secs) % 60
    return f"{m}:{s:02d}"

def parse_filename(stem):
    rest = stem[len("FinalFRCA"):]
    for cat_key in sorted(CATEGORIES.keys(), key=len, reverse=True):
        if rest.startswith(cat_key + "_"):
            topic_raw = rest[len(cat_key) + 1:]
            return cat_key, topic_raw.replace("_", " "), stem + ".mp3"
    parts = rest.split("_", 1)
    return parts[0], (parts[1].replace("_", " ") if len(parts) > 1 else rest), stem + ".mp3"

# ── Q&A parser ─────────────────────────────────────────────────────────────────
def expand_segments(segments):
    """
    Split segments at '?' boundaries so each chunk is either:
      is_q=True  (ends with ?)
      is_q=False (plain answer/preamble text)
    Also detect interrogative openers without '?'.
    """
    expanded = []
    for seg in segments:
        raw = seg["text"].strip()
        if not raw:
            continue
        if "?" not in raw:
            # Check if whole segment is a question via opener
            is_q = bool(Q_OPENERS.match(raw))
            expanded.append({"text": raw, "start": round(seg["start"], 3),
                              "end": round(seg["end"], 3), "is_q": is_q})
            continue

        # Split the segment text at every '?'
        parts = re.split(r"(\?)", raw)
        chunks = []
        buf = ""
        for p in parts:
            if p == "?":
                buf += "?"
                if buf.strip():
                    chunks.append((buf.strip(), True))
                buf = ""
            else:
                buf = p
        if buf.strip():
            # Trailing text after last ? → check opener
            is_q = bool(Q_OPENERS.match(buf.strip()))
            chunks.append((buf.strip(), is_q))

        # Distribute timestamps proportionally
        total_words = max(sum(len(c[0].split()) for c in chunks), 1)
        dur = seg["end"] - seg["start"]
        cur = seg["start"]
        for txt, is_q in chunks:
            if not txt:
                continue
            w = max(len(txt.split()), 1)
            end = round(cur + dur * w / total_words, 3)
            expanded.append({"text": txt, "start": round(cur, 3),
                              "end": end, "is_q": is_q})
            cur = end

    return expanded


def build_qa_blocks(segments):
    """
    Returns list of blocks:
      {"type": "preamble", "segs": [...]}
      {"type": "qa",  "q_segs": [...], "a_segs": [...]}
    """
    expanded = expand_segments(segments)
    blocks = []
    i, n = 0, len(expanded)

    # Preamble: non-question segments before the first question
    preamble = []
    while i < n and not expanded[i]["is_q"]:
        preamble.append(expanded[i])
        i += 1
    if preamble:
        blocks.append({"type": "preamble", "segs": preamble})

    # Q/A pairs
    while i < n:
        if expanded[i]["is_q"]:
            q_segs = []
            while i < n and expanded[i]["is_q"]:
                q_segs.append(expanded[i])
                i += 1
            a_segs = []
            while i < n and not expanded[i]["is_q"]:
                a_segs.append(expanded[i])
                i += 1
            blocks.append({"type": "qa", "q_segs": q_segs, "a_segs": a_segs})
        else:
            # Stray non-question segment — attach to previous answer
            if blocks and blocks[-1]["type"] == "qa":
                blocks[-1]["a_segs"].append(expanded[i])
            else:
                blocks.append({"type": "preamble", "segs": [expanded[i]]})
            i += 1

    return blocks


# ── HTML builder ───────────────────────────────────────────────────────────────
CSS = """\
  :root {
    --q-bg:       #1e3a5f;
    --q-text:     #ffffff;
    --q-label:    #60a5fa;
    --a-bg:       #ffffff;
    --a-border:   #e2e8f0;
    --a-label:    #059669;
    --active-q:   %(accent)s;
    --active-a:   #dbeafe;
    --accent:     %(accent)s;
    --body-bg:    #f1f5f9;
    --pre-bg:     #fef9c3;
    --pre-border: #fcd34d;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--body-bg);
    color: #1e293b;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Header ── */
  .header {
    background: #0f172a;
    border-bottom: 3px solid var(--accent);
    padding: 12px 20px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  .header-left { flex: 1; min-width: 200px; }
  .header h1 {
    font-size: 1rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 4px;
    letter-spacing: 0.01em;
  }
  .header-sub { font-size: 0.72rem; color: #94a3b8; font-style: italic; }
  audio { height: 36px; accent-color: var(--accent); flex-shrink: 0; }
  .back-link { font-size: 0.8rem; color: #94a3b8; text-decoration: none; white-space: nowrap; }
  .back-link:hover { color: #60a5fa; }

  /* ── Toolbar ── */
  .toolbar {
    background: #1e293b;
    padding: 7px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
    border-bottom: 1px solid #334155;
  }
  .toolbar input {
    flex: 1; max-width: 380px;
    padding: 5px 11px;
    border: 1px solid #475569; border-radius: 6px;
    background: #0f172a; color: #e2e8f0; font-size: 0.83rem; outline: none;
  }
  .toolbar input:focus { border-color: var(--accent); }
  .toolbar input::placeholder { color: #64748b; }
  .stats { font-size: 0.72rem; color: #64748b; white-space: nowrap; }

  /* ── Scroll area ── */
  .scroll-area { flex: 1; overflow-y: auto; padding: 20px; }
  .scroll-area::-webkit-scrollbar { width: 6px; }
  .scroll-area::-webkit-scrollbar-track { background: transparent; }
  .scroll-area::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }

  /* ── Subtitle bar ── */
  .subtitle-bar {
    background: #0f172a;
    border-top: 2px solid var(--accent);
    padding: 8px 20px;
    flex-shrink: 0;
    min-height: 42px;
    display: flex;
    align-items: center;
  }
  #subtitle-text { font-size: 0.88rem; color: #e2e8f0; line-height: 1.5; font-style: italic; }
  #subtitle-text.empty { color: #475569; }

  /* ── Preamble ── */
  .preamble-block {
    background: var(--pre-bg);
    border-left: 4px solid var(--pre-border);
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 0.88rem;
    color: #78350f;
    font-style: italic;
    line-height: 1.7;
  }

  /* ── Q&A pair ── */
  .qa-pair { margin-bottom: 20px; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }

  /* Question block */
  .q-block {
    background: var(--q-bg);
    padding: 14px 18px;
    display: flex; gap: 14px; align-items: flex-start;
    cursor: pointer;
    transition: background 0.15s;
  }
  .q-block:hover { background: #1d4ed8; }
  .q-block.q-active { background: var(--active-q); }
  .q-label {
    font-size: 0.7rem; font-weight: 700;
    color: var(--q-label);
    background: rgba(96,165,250,0.15);
    border: 1px solid rgba(96,165,250,0.3);
    border-radius: 5px; padding: 3px 7px;
    white-space: nowrap; margin-top: 2px; letter-spacing: 0.05em;
    flex-shrink: 0;
  }
  .q-body { flex: 1; font-size: 0.97rem; font-weight: 600; color: var(--q-text); line-height: 1.55; }

  /* Answer block */
  .a-block {
    background: var(--a-bg);
    border: 1px solid var(--a-border); border-top: none;
    padding: 14px 18px;
    display: flex; gap: 14px; align-items: flex-start;
  }
  .a-label {
    font-size: 0.7rem; font-weight: 700;
    color: var(--a-label);
    background: #d1fae5; border: 1px solid #6ee7b7;
    border-radius: 5px; padding: 3px 9px;
    white-space: nowrap; margin-top: 2px; letter-spacing: 0.05em;
    flex-shrink: 0;
  }
  .a-body { flex: 1; list-style: none; padding: 0; }
  .a-body li {
    padding: 4px 0 4px 14px;
    border-left: 3px solid transparent;
    line-height: 1.7; font-size: 0.92rem; color: #1e293b;
    border-radius: 0 4px 4px 0;
    transition: background 0.15s;
  }
  .a-body li:not(:last-child) { border-bottom: 1px solid #f1f5f9; }

  /* ── Segments (clickable) ── */
  .segment { cursor: pointer; border-radius: 3px; }
  .q-seg:hover { background: rgba(255,255,255,0.18); }
  .a-seg:hover { background: #eff6ff; }
  .segment.active { background: #bfdbfe; outline: 2px solid #3b82f6; outline-offset: 1px; }
  .a-body li.li-active { background: var(--active-a); border-left-color: var(--accent); }
  .segment.search-match  { background: #fef9c3; }
  .segment.search-current { background: #fde047; outline: 2px solid #ca8a04; }
"""

JS = """\
const audio      = document.getElementById('audio');
const allSegs    = Array.from(document.querySelectorAll('.segment'));
const subtitleEl = document.getElementById('subtitle-text');
let activeSegEl  = null;
let searchMatches = [], searchIdx = 0;

audio.addEventListener('loadedmetadata', () => {
  const m = Math.floor(audio.duration / 60);
  const s = Math.floor(audio.duration %% 60).toString().padStart(2,'0');
  document.getElementById('dur').textContent = m + ':' + s;
});

function seekTo(t) { audio.currentTime = t; audio.play(); }

// Q-block header click
document.querySelectorAll('.q-block').forEach(q => {
  q.addEventListener('click', e => {
    if (!e.target.classList.contains('segment')) seekTo(parseFloat(q.dataset.start));
  });
});

// Individual segment click
allSegs.forEach(s => {
  s.addEventListener('click', e => { e.stopPropagation(); seekTo(parseFloat(s.dataset.start)); });
});

// Real-time tracking
audio.addEventListener('timeupdate', () => {
  const t = audio.currentTime;
  let found = null;
  for (let i = allSegs.length - 1; i >= 0; i--) {
    if (parseFloat(allSegs[i].dataset.start) <= t) { found = allSegs[i]; break; }
  }
  if (found && found !== activeSegEl) {
    if (activeSegEl) {
      activeSegEl.classList.remove('active');
      const pli = activeSegEl.closest('li');
      if (pli) pli.classList.remove('li-active');
      const pq = activeSegEl.closest('.q-block');
      if (pq) pq.classList.remove('q-active');
    }
    found.classList.add('active');
    const li = found.closest('li');
    if (li) li.classList.add('li-active');
    const qb = found.closest('.q-block');
    if (qb) qb.classList.add('q-active');
    activeSegEl = found;

    subtitleEl.textContent = found.textContent.trim();
    subtitleEl.classList.remove('empty');

    if (!document.getElementById('search').value)
      found.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
});

// Search
const searchInput = document.getElementById('search');
searchInput.addEventListener('input', runSearch);
searchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && searchMatches.length) {
    searchMatches[searchIdx].classList.remove('search-current');
    searchIdx = (searchIdx + 1) %% searchMatches.length;
    const el = searchMatches[searchIdx];
    el.classList.add('search-current');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
});
function runSearch() {
  const q = searchInput.value.trim().toLowerCase();
  allSegs.forEach(s => s.classList.remove('search-match','search-current'));
  searchMatches = [];
  if (!q) return;
  allSegs.forEach(s => {
    if (s.textContent.toLowerCase().includes(q)) { s.classList.add('search-match'); searchMatches.push(s); }
  });
  if (!searchMatches.length) return;
  searchIdx = 0;
  searchMatches[0].classList.add('search-current');
  searchMatches[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
}
"""


def seg_span(seg, cls):
    t = seg["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (f'<span class="segment {cls}" data-start="{seg["start"]}" '
            f'data-end="{seg["end"]}" title="{fmt_time(seg["start"])}">{t} </span>')


def generate_player(stem, cat_key, topic_label, mp3_name, segments, accent):
    cat_info  = CATEGORIES.get(cat_key, {"label": cat_key.replace("_"," "), "color": accent})
    cat_label = cat_info["label"]
    blocks    = build_qa_blocks(segments)

    n_questions = sum(1 for b in blocks if b["type"] == "qa")
    n_segs      = len(segments)

    body_parts = []
    q_num = 0

    for block in blocks:
        if block["type"] == "preamble":
            spans = "".join(seg_span(s, "a-seg") for s in block["segs"])
            body_parts.append(f'<div class="preamble-block">{spans}</div>\n')

        elif block["type"] == "qa":
            q_num += 1
            q_segs = block["q_segs"]
            a_segs = block["a_segs"]

            # Q block
            first_start = q_segs[0]["start"] if q_segs else 0
            q_spans = "".join(seg_span(s, "q-seg") for s in q_segs)
            q_html = (f'<div class="q-block" data-start="{first_start}">\n'
                      f'  <div class="q-label">Q{q_num}</div>\n'
                      f'  <div class="q-body">{q_spans}</div>\n'
                      f'</div>\n')

            # A block
            li_items = "".join(
                f'<li>{seg_span(s, "a-seg")}</li>\n' for s in a_segs
            )
            a_html = (f'<div class="a-block">\n'
                      f'  <div class="a-label">A</div>\n'
                      f'  <ul class="a-body">\n{li_items}  </ul>\n'
                      f'</div>\n')

            body_parts.append(f'<div class="qa-pair">\n{q_html}{a_html}</div>\n')

    css = CSS % {"accent": accent}

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{cat_label} \u2014 {topic_label}</title>
<style>
{css}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>{cat_label} \u2014 {topic_label}</h1>
    <div class="header-sub">Final FRCA &mdash; Exam Viva Simulation &mdash; Click any phrase to seek</div>
  </div>
  <audio id="audio" src="../{mp3_name}" controls preload="metadata"></audio>
  <a class="back-link" href="index.html">&#8592; All Topics</a>
</div>

<div class="toolbar">
  <input type="text" id="search" placeholder="Search transcript&#8230; (Enter = next match)">
  <span class="stats" id="stats">{n_questions} questions &nbsp;|&nbsp; {n_segs} segments &nbsp;|&nbsp; <span id="dur">loading&#8230;</span></span>
</div>

<div class="scroll-area" id="scroll-area">
{"".join(body_parts)}
</div>

<div class="subtitle-bar">
  <span id="subtitle-text" class="empty">Play audio to see live subtitles&#8230;</span>
</div>

<script>
{JS}
</script>
</body>
</html>
"""


# ── Index HTML ─────────────────────────────────────────────────────────────────
def generate_index(entries_by_cat):
    cat_sections = []
    for cat_key, entries in sorted(entries_by_cat.items(),
                                    key=lambda x: CATEGORIES.get(x[0], {}).get("label", x[0])):
        info  = CATEGORIES.get(cat_key, {"label": cat_key, "color": "#2563eb", "cls": "cat-other"})
        color = info["color"]
        label = info["label"]
        cls   = info["cls"]
        cards = "\n".join(
            f'<a class="card {cls}" href="{fn}">'
            f'<div class="card-prefix" style="color:{color}">{label}</div>{tl}</a>'
            for fn, tl in sorted(entries, key=lambda x: x[1])
        )
        cat_sections.append(f"""<div class="category">
<div class="cat-header">
  <div class="cat-dot" style="background:{color}"></div>
  <h2>{label}</h2>
  <div class="cat-line"></div>
</div>
<div class="grid">
{cards}
</div>
</div>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Final FRCA &mdash; Viva Exam Player</title>
<style>
  :root {{ --accent: #2563eb; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 32px 24px;
  }}
  .top-header {{ text-align: center; margin-bottom: 36px; }}
  .top-header h1 {{
    font-size: 1.6rem; color: #f1f5f9; font-weight: 800;
    letter-spacing: -0.02em; margin-bottom: 6px;
  }}
  .top-header p {{ font-size: 0.85rem; color: #64748b; }}
  .filter-wrap {{ max-width: 480px; margin: 0 auto 32px; }}
  .filter-wrap input {{
    width: 100%; padding: 10px 16px;
    border: 1px solid #334155; border-radius: 8px;
    background: #1e293b; color: #e2e8f0; font-size: 0.9rem; outline: none;
  }}
  .filter-wrap input:focus {{ border-color: var(--accent); }}
  .filter-wrap input::placeholder {{ color: #475569; }}
  .category {{ margin-bottom: 36px; }}
  .cat-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }}
  .cat-header h2 {{
    font-size: 0.7rem; text-transform: uppercase;
    letter-spacing: 0.12em; font-weight: 700; color: #94a3b8;
  }}
  .cat-line {{ flex: 1; height: 1px; background: #1e293b; }}
  .cat-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }}
  .card {{
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    padding: 12px 16px; text-decoration: none; color: #cbd5e1;
    font-size: 0.85rem; line-height: 1.4; display: block;
    transition: border-color 0.15s, color 0.15s, transform 0.1s;
  }}
  .card:hover {{ border-color: var(--accent); color: #93c5fd; transform: translateY(-1px); }}
  .card.hidden {{ display: none; }}
  .card-prefix {{
    font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 4px;
  }}
</style>
</head>
<body>
<div class="top-header">
  <h1>Final FRCA &mdash; Viva Exam Player</h1>
  <p>Interactive audio + transcript. Click any phrase to jump to that moment in the recording.</p>
</div>
<div class="filter-wrap">
  <input type="text" id="filter" placeholder="Filter topics&#8230;" oninput="filterCards(this.value)">
</div>
{"".join(cat_sections)}
<script>
function filterCards(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('.card').forEach(c => {{
    c.classList.toggle('hidden', q && !c.textContent.toLowerCase().includes(q));
  }});
}}
</script>
</body>
</html>
"""


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    json_files   = sorted(CACHE_DIR.glob("*.json"))
    entries_by_cat = {}
    generated    = 0

    for jf in json_files:
        stem = jf.stem
        cat_key, topic_label, mp3_name = parse_filename(stem)
        cat_info = CATEGORIES.get(cat_key, {"label": cat_key, "color": "#2563eb", "cls": "cat-other"})
        accent   = cat_info["color"]

        with open(jf, encoding="utf-8") as f:
            data = json.load(f)

        segments = data.get("segments", [])
        if not segments:
            print(f"  SKIP (no segments): {stem}")
            continue

        html      = generate_player(stem, cat_key, topic_label, mp3_name, segments, accent)
        out_path  = OUT_DIR / (stem + ".html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Count questions for reporting
        blocks    = build_qa_blocks(segments)
        n_q       = sum(1 for b in blocks if b["type"] == "qa")
        entries_by_cat.setdefault(cat_key, []).append((stem + ".html", topic_label))
        generated += 1
        print(f"  OK  [{cat_info['label']}] {topic_label}  ({n_q} Qs, {len(segments)} segs)")

    index_html = generate_index(entries_by_cat)
    with open(OUT_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"\nDone. {generated} player files + index.html written to {OUT_DIR}")


if __name__ == "__main__":
    main()
