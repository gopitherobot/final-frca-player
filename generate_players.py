#!/usr/bin/env python3
"""Generate Final FRCA interactive player HTML files from transcript JSON cache."""

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / "_transcripts_cache"
OUT_DIR   = BASE_DIR / "players"
OUT_DIR.mkdir(exist_ok=True)

# ── Category metadata ──────────────────────────────────────────────────────────
CATEGORIES = {
    "Cardiac_Anaesthesia":       {"label": "Cardiac Anaesthesia",        "color": "#ef4444", "cls": "cat-cardiac"},
    "Day_Stay":                  {"label": "Day Stay",                   "color": "#6b7280", "cls": "cat-daystay"},
    "ENT":                       {"label": "ENT",                        "color": "#f59e0b", "cls": "cat-ent"},
    "Emergency_Medicine":        {"label": "Emergency Medicine",         "color": "#dc2626", "cls": "cat-em"},
    "Endocrinology":             {"label": "Endocrinology",              "color": "#8b5cf6", "cls": "cat-endo"},
    "Gastrointestinal_Tract":    {"label": "Gastrointestinal Tract",     "color": "#f97316", "cls": "cat-git"},
    "Haematological":            {"label": "Haematological",             "color": "#ec4899", "cls": "cat-haem"},
    "Hepatology":                {"label": "Hepatology",                 "color": "#b45309", "cls": "cat-hep"},
    "Intensive_Care_Medicine":   {"label": "Intensive Care Medicine",    "color": "#0ea5e9", "cls": "cat-icm"},
    "Metabolism":                {"label": "Metabolism",                 "color": "#10b981", "cls": "cat-meta"},
    "Neurosurgical_Anaesthesia": {"label": "Neurosurgical Anaesthesia",  "color": "#6366f1", "cls": "cat-neuro"},
    "Obstetrics":                {"label": "Obstetrics",                 "color": "#db2777", "cls": "cat-obs"},
    "Ophthalmic":                {"label": "Ophthalmic",                 "color": "#059669", "cls": "cat-ophth"},
    "Orthopaedics":              {"label": "Orthopaedics",               "color": "#64748b", "cls": "cat-ortho"},
    "Paediatric_and_Neonatal":   {"label": "Paediatric & Neonatal",      "color": "#fbbf24", "cls": "cat-paeds"},
    "Pain":                      {"label": "Pain",                       "color": "#a855f7", "cls": "cat-pain"},
    "Regional_Anaesthesia":      {"label": "Regional Anaesthesia",       "color": "#2563eb", "cls": "cat-reg"},
    "Renal":                     {"label": "Renal",                      "color": "#0891b2", "cls": "cat-renal"},
    "Thoracics":                 {"label": "Thoracics",                  "color": "#7c3aed", "cls": "cat-thor"},
    "Vascular":                  {"label": "Vascular",                   "color": "#ea580c", "cls": "cat-vasc"},
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_time(secs):
    """Convert seconds to M:SS string."""
    m = int(secs) // 60
    s = int(secs) % 60
    return f"{m}:{s:02d}"

def parse_filename(stem):
    """
    Stem like: FinalFRCACardiac_Anaesthesia_Hypertension
    Returns (category_key, topic_label, mp3_name)
    """
    # Strip leading FinalFRCA
    rest = stem[len("FinalFRCA"):]
    # Match category
    matched_cat = None
    for cat_key in sorted(CATEGORIES.keys(), key=len, reverse=True):
        if rest.startswith(cat_key + "_"):
            matched_cat = cat_key
            topic_raw = rest[len(cat_key) + 1:]
            break
    if matched_cat is None:
        # Fallback: first segment before second underscore group
        parts = rest.split("_", 1)
        matched_cat = parts[0]
        topic_raw = parts[1] if len(parts) > 1 else rest
    topic_label = topic_raw.replace("_", " ")
    mp3_name = stem + ".mp3"
    return matched_cat, topic_label, mp3_name

def group_segments(segments, group_size=6):
    """Group flat segments list into blocks of ~group_size."""
    groups = []
    for i in range(0, len(segments), group_size):
        groups.append(segments[i:i + group_size])
    return groups

def is_question_seg(text):
    """Heuristic: segment likely contains/ends a question."""
    t = text.strip()
    return t.endswith("?") or "?" in t[-30:]

# ── Player HTML generator ──────────────────────────────────────────────────────
CSS = """
  :root {
    --accent:    %(accent)s;
    --body-bg:   #f1f5f9;
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
  .header-sub {
    font-size: 0.72rem;
    color: #94a3b8;
    font-style: italic;
  }
  audio {
    height: 36px;
    accent-color: var(--accent);
    flex-shrink: 0;
  }
  .back-link {
    font-size: 0.8rem;
    color: #94a3b8;
    text-decoration: none;
    white-space: nowrap;
  }
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
    flex: 1;
    max-width: 380px;
    padding: 5px 11px;
    border: 1px solid #475569;
    border-radius: 6px;
    background: #0f172a;
    color: #e2e8f0;
    font-size: 0.83rem;
    outline: none;
  }
  .toolbar input:focus { border-color: var(--accent); }
  .toolbar input::placeholder { color: #64748b; }
  .stats {
    font-size: 0.72rem;
    color: #64748b;
    white-space: nowrap;
  }

  /* ── Scroll area ── */
  .scroll-area {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }
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
  .subtitle-text {
    font-size: 0.9rem;
    color: #e2e8f0;
    line-height: 1.5;
    font-style: italic;
  }
  .subtitle-text.empty { color: #475569; }

  /* ── Transcript blocks ── */
  .t-block {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    margin-bottom: 14px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    display: flex;
  }
  .t-block.block-active {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(37,99,235,0.15);
  }
  .t-gutter {
    background: #0f172a;
    width: 52px;
    flex-shrink: 0;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 14px;
    cursor: pointer;
  }
  .t-gutter:hover { background: #1e293b; }
  .t-timestamp {
    font-size: 0.7rem;
    color: #64748b;
    font-family: monospace;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .t-gutter.gutter-active .t-timestamp { color: var(--accent); }
  .t-body {
    flex: 1;
    padding: 12px 16px;
    line-height: 1.75;
    font-size: 0.92rem;
    color: #1e293b;
  }

  /* ── Segments ── */
  .segment {
    cursor: pointer;
    border-radius: 3px;
    transition: background 0.1s;
  }
  .segment:hover { background: #eff6ff; }
  .segment.active {
    background: #bfdbfe;
    outline: 2px solid #3b82f6;
    outline-offset: 1px;
    border-radius: 3px;
  }
  .segment.search-match  { background: #fef9c3; }
  .segment.search-current { background: #fde047; outline: 2px solid #ca8a04; }
"""

JS = """
const audio    = document.getElementById('audio');
const allSegs  = Array.from(document.querySelectorAll('.segment'));
const allBlocks = Array.from(document.querySelectorAll('.t-block'));
const subtitleEl = document.getElementById('subtitle-text');
let activeSegEl   = null;
let activeBlockEl = null;
let searchMatches = [];
let searchIdx     = 0;

// Duration display
audio.addEventListener('loadedmetadata', () => {
  const m = Math.floor(audio.duration / 60);
  const s = Math.floor(audio.duration %% 60).toString().padStart(2,'0');
  document.getElementById('dur').textContent = m + ':' + s;
});

// Seek helper
function seekTo(t) {
  audio.currentTime = t;
  audio.play();
}

// Block gutter click
document.querySelectorAll('.t-gutter').forEach(g => {
  g.addEventListener('click', () => seekTo(parseFloat(g.dataset.start)));
});

// Segment click
allSegs.forEach(s => {
  s.addEventListener('click', e => {
    e.stopPropagation();
    seekTo(parseFloat(s.dataset.start));
  });
});

// Real-time tracking
audio.addEventListener('timeupdate', () => {
  const t = audio.currentTime;

  // Find active segment (last one whose start <= t)
  let found = null;
  for (let i = allSegs.length - 1; i >= 0; i--) {
    if (parseFloat(allSegs[i].dataset.start) <= t) { found = allSegs[i]; break; }
  }

  if (found && found !== activeSegEl) {
    // Clear previous
    if (activeSegEl) activeSegEl.classList.remove('active');
    if (activeBlockEl) {
      activeBlockEl.classList.remove('block-active');
      const pg = activeBlockEl.querySelector('.t-gutter');
      if (pg) pg.classList.remove('gutter-active');
    }
    // Set new
    found.classList.add('active');
    const block = found.closest('.t-block');
    if (block) {
      block.classList.add('block-active');
      const g = block.querySelector('.t-gutter');
      if (g) g.classList.add('gutter-active');
      activeBlockEl = block;
    }
    activeSegEl = found;

    // Update subtitle
    subtitleEl.textContent = found.textContent.trim();
    subtitleEl.classList.remove('empty');

    // Auto-scroll (only when not searching)
    if (!document.getElementById('search').value) {
      found.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
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
    if (s.textContent.toLowerCase().includes(q)) {
      s.classList.add('search-match');
      searchMatches.push(s);
    }
  });
  if (!searchMatches.length) return;
  searchIdx = 0;
  searchMatches[0].classList.add('search-current');
  searchMatches[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
}
"""

def generate_player(stem, cat_key, topic_label, mp3_name, segments, accent):
    cat_info = CATEGORIES.get(cat_key, {"label": cat_key.replace("_", " "), "color": "#2563eb"})
    cat_label = cat_info["label"]
    n_segs = len(segments)
    groups = group_segments(segments, group_size=6)

    # Build transcript HTML
    blocks_html = []
    for grp in groups:
        if not grp:
            continue
        block_start = grp[0]["start"]
        ts = fmt_time(block_start)
        segs_html = []
        for seg in grp:
            txt = seg["text"].strip()
            if not txt:
                continue
            s_start = round(seg["start"], 3)
            s_end   = round(seg["end"], 3)
            title   = fmt_time(s_start)
            segs_html.append(
                f'<span class="segment" data-start="{s_start}" data-end="{s_end}" title="{title}">{txt} </span>'
            )
        if not segs_html:
            continue
        blocks_html.append(f"""<div class="t-block">
  <div class="t-gutter" data-start="{round(block_start,3)}"><span class="t-timestamp">{ts}</span></div>
  <div class="t-body">{''.join(segs_html)}</div>
</div>""")

    css = CSS % {"accent": accent}

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{cat_label} — {topic_label}</title>
<style>
{css}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>{cat_label} — {topic_label}</h1>
    <div class="header-sub">Final FRCA &mdash; Exam Viva Simulation &mdash; Click any phrase to seek</div>
  </div>
  <audio id="audio" src="../{mp3_name}" controls preload="metadata"></audio>
  <a class="back-link" href="index.html">&#8592; All Topics</a>
</div>

<div class="toolbar">
  <input type="text" id="search" placeholder="Search transcript&#8230; (Enter = next match)">
  <span class="stats" id="stats">{n_segs} segments &nbsp;|&nbsp; <span id="dur">loading&#8230;</span></span>
</div>

<div class="scroll-area" id="scroll-area">
{''.join(blocks_html)}
</div>

<div class="subtitle-bar">
  <span class="subtitle-text empty" id="subtitle-text">Play audio to see live subtitles&#8230;</span>
</div>

<script>
{JS}
</script>
</body>
</html>
"""
    return html

# ── Index HTML generator ───────────────────────────────────────────────────────
def generate_index(entries_by_cat):
    """entries_by_cat: {cat_key: [(html_filename, topic_label), ...]}"""
    cat_sections = []
    for cat_key, entries in sorted(entries_by_cat.items(), key=lambda x: CATEGORIES.get(x[0], {}).get("label", x[0])):
        info = CATEGORIES.get(cat_key, {"label": cat_key.replace("_", " "), "color": "#2563eb", "cls": "cat-" + cat_key.lower()})
        color = info["color"]
        label = info["label"]
        cls   = info["cls"]
        cards = "\n".join(
            f'<a class="card {cls}" href="{fn}"><div class="card-prefix" style="color:{color}">{label}</div>{tl}</a>'
            for fn, tl in sorted(entries, key=lambda x: x[1])
        )
        section = f"""<div class="category">
<div class="cat-header">
  <div class="cat-dot" style="background:{color}"></div>
  <h2>{label}</h2>
  <div class="cat-line"></div>
</div>
<div class="grid">
{cards}
</div>
</div>"""
        cat_sections.append(section)

    css_vars = "\n".join(
        f"  .{info['cls']} .cat-dot {{ background: {info['color']}; }}"
        for info in CATEGORIES.values()
    )

    html = f"""<!DOCTYPE html>
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
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    padding: 32px 24px;
  }}
  .top-header {{
    text-align: center;
    margin-bottom: 36px;
  }}
  .top-header h1 {{
    font-size: 1.6rem;
    color: #f1f5f9;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin-bottom: 6px;
  }}
  .top-header p {{
    font-size: 0.85rem;
    color: #64748b;
  }}
  .filter-wrap {{
    max-width: 480px;
    margin: 0 auto 32px;
  }}
  .filter-wrap input {{
    width: 100%;
    padding: 10px 16px;
    border: 1px solid #334155;
    border-radius: 8px;
    background: #1e293b;
    color: #e2e8f0;
    font-size: 0.9rem;
    outline: none;
  }}
  .filter-wrap input:focus {{ border-color: var(--accent); }}
  .filter-wrap input::placeholder {{ color: #475569; }}
  .category {{ margin-bottom: 36px; }}
  .cat-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }}
  .cat-header h2 {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 700;
    color: #94a3b8;
  }}
  .cat-line {{
    flex: 1;
    height: 1px;
    background: #1e293b;
  }}
  .cat-dot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
{css_vars}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 10px;
  }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px 16px;
    text-decoration: none;
    color: #cbd5e1;
    font-size: 0.85rem;
    line-height: 1.4;
    display: block;
    transition: border-color 0.15s, color 0.15s, transform 0.1s;
  }}
  .card:hover {{
    border-color: var(--accent);
    color: #93c5fd;
    transform: translateY(-1px);
  }}
  .card.hidden {{ display: none; }}
  .card-prefix {{
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 4px;
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

{''.join(cat_sections)}

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
    return html

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    json_files = sorted(CACHE_DIR.glob("*.json"))
    entries_by_cat = {}
    generated = 0

    for jf in json_files:
        stem = jf.stem  # e.g. FinalFRCACardiac_Anaesthesia_Hypertension
        cat_key, topic_label, mp3_name = parse_filename(stem)
        cat_info = CATEGORIES.get(cat_key, {"label": cat_key, "color": "#2563eb", "cls": "cat-other"})
        accent = cat_info["color"]

        with open(jf, encoding="utf-8") as f:
            data = json.load(f)

        segments = data.get("segments", [])
        if not segments:
            print(f"  SKIP (no segments): {stem}")
            continue

        html_filename = stem + ".html"
        out_path = OUT_DIR / html_filename

        html = generate_player(stem, cat_key, topic_label, mp3_name, segments, accent)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        if cat_key not in entries_by_cat:
            entries_by_cat[cat_key] = []
        entries_by_cat[cat_key].append((html_filename, topic_label))
        generated += 1
        print(f"  OK  [{cat_info['label']}] {topic_label}")

    # Write index
    index_html = generate_index(entries_by_cat)
    with open(OUT_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"\nDone. Generated {generated} player files + index.html → {OUT_DIR}")

if __name__ == "__main__":
    main()
