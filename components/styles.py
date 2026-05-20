"""
UI styles injected via st.markdown for premium look-and-feel.
"""

GLOBAL_CSS = """
<style>
/* ── Google Fonts ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Root Variables ───────────────────────────────────────── */
:root {
    --bg-primary:       #0D0D1A;
    --bg-secondary:     #13132A;
    --bg-card:          #1A1A35;
    --bg-hover:         #22224A;
    --accent-purple:    #7C3AED;
    --accent-violet:    #8B5CF6;
    --accent-indigo:    #6366F1;
    --accent-cyan:      #06B6D4;
    --accent-green:     #10B981;
    --accent-amber:     #F59E0B;
    --accent-rose:      #F43F5E;
    --text-primary:     #E2E8F0;
    --text-secondary:   #94A3B8;
    --text-muted:       #475569;
    --border:           rgba(124, 58, 237, 0.25);
    --border-hover:     rgba(124, 58, 237, 0.6);
    --glow:             rgba(124, 58, 237, 0.15);
    --glow-strong:      rgba(124, 58, 237, 0.35);
    --radius:           12px;
    --radius-lg:        18px;
    --transition:       all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Global Reset ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg-primary) !important;
    font-family: 'Inter', sans-serif !important;
    color: var(--text-primary) !important;
}

[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

/* ── Scrollbar ────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb {
    background: var(--accent-purple);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: var(--accent-violet); }

/* ── Hero Banner ──────────────────────────────────────────── */
.tracex-hero {
    background: linear-gradient(135deg, #1A0A35 0%, #0D0D1A 40%, #0A1628 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 2.5rem 2rem 2rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
    text-align: center;
}
.tracex-hero::before {
    content: '';
    position: absolute;
    top: -60px; left: 50%;
    transform: translateX(-50%);
    width: 400px; height: 200px;
    background: radial-gradient(ellipse, rgba(124,58,237,0.25) 0%, transparent 70%);
    pointer-events: none;
}
.tracex-hero h1 {
    font-size: 2.8rem !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #A78BFA 0%, #7C3AED 40%, #06B6D4 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -1px;
    margin: 0 0 0.5rem !important;
    line-height: 1.1 !important;
}
.tracex-hero .subtitle {
    color: var(--text-secondary);
    font-size: 1rem;
    font-weight: 400;
    letter-spacing: 0.5px;
}
.tracex-hero .badge-row {
    display: flex;
    gap: 0.6rem;
    justify-content: center;
    flex-wrap: wrap;
    margin-top: 1rem;
}
.badge {
    background: rgba(124,58,237,0.15);
    border: 1px solid rgba(124,58,237,0.3);
    color: #A78BFA;
    padding: 0.2rem 0.75rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Section Labels ───────────────────────────────────────── */
.section-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
}

/* ── Language Cards ───────────────────────────────────────── */
.lang-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.6rem;
    margin-bottom: 1rem;
}
.lang-card {
    background: var(--bg-card);
    border: 2px solid transparent;
    border-radius: var(--radius);
    padding: 0.75rem 0.5rem;
    text-align: center;
    cursor: pointer;
    transition: var(--transition);
    position: relative;
    overflow: hidden;
}
.lang-card:hover {
    border-color: var(--border-hover);
    background: var(--bg-hover);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px var(--glow);
}
.lang-card.active {
    border-color: var(--accent-purple);
    background: linear-gradient(135deg, rgba(124,58,237,0.2) 0%, rgba(99,102,241,0.1) 100%);
    box-shadow: 0 0 20px var(--glow-strong), inset 0 0 20px rgba(124,58,237,0.05);
}
.lang-card .lang-icon { font-size: 1.5rem; margin-bottom: 0.25rem; }
.lang-card .lang-name {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
}
.lang-card.active .lang-name { color: #A78BFA; }

/* ── Mode Selector ────────────────────────────────────────── */
.mode-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 1rem;
}
.mode-card {
    background: var(--bg-card);
    border: 2px solid transparent;
    border-radius: var(--radius);
    padding: 1.1rem 1rem;
    cursor: pointer;
    transition: var(--transition);
    position: relative;
    overflow: hidden;
}
.mode-card::before {
    content: '';
    position: absolute;
    inset: 0;
    opacity: 0;
    transition: opacity 0.25s;
}
.mode-card:hover { border-color: var(--border-hover); transform: translateY(-2px); }
.mode-card.active-full {
    border-color: var(--accent-green);
    background: linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(6,182,212,0.05) 100%);
    box-shadow: 0 0 20px rgba(16,185,129,0.2);
}
.mode-card.active-leet {
    border-color: var(--accent-amber);
    background: linear-gradient(135deg, rgba(245,158,11,0.12) 0%, rgba(239,68,68,0.05) 100%);
    box-shadow: 0 0 20px rgba(245,158,11,0.2);
}
.mode-card .mode-icon { font-size: 1.6rem; margin-bottom: 0.4rem; }
.mode-card .mode-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 0.2rem;
}
.mode-card .mode-desc {
    font-size: 0.72rem;
    color: var(--text-muted);
    line-height: 1.4;
}
.mode-card.active-full .mode-title { color: #10B981; }
.mode-card.active-leet .mode-title { color: #F59E0B; }

/* ── Code Editor Wrapper ──────────────────────────────────── */
.editor-wrapper {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: 0 4px 30px rgba(0,0,0,0.4);
    transition: var(--transition);
}
.editor-wrapper:focus-within {
    border-color: var(--accent-purple);
    box-shadow: 0 4px 30px rgba(0,0,0,0.4), 0 0 0 3px rgba(124,58,237,0.15);
}
.editor-topbar {
    background: #0F0F22;
    padding: 0.65rem 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
}
.editor-dots { display: flex; gap: 6px; align-items: center; }
.dot {
    width: 12px; height: 12px; border-radius: 50%;
    animation: pulse-dot 3s ease-in-out infinite;
}
.dot-red   { background: #FF5F57; animation-delay: 0s; }
.dot-amber { background: #FEBC2E; animation-delay: 0.3s; }
.dot-green { background: #28C840; animation-delay: 0.6s; }
@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.editor-filename {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    letter-spacing: 0.5px;
}
.editor-lang-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    background: rgba(124,58,237,0.2);
    color: #A78BFA;
    border: 1px solid rgba(124,58,237,0.3);
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Textarea Styling ─────────────────────────────────────── */
.editor-wrapper textarea {
    background: var(--bg-card) !important;
    color: #E2E8F0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.875rem !important;
    line-height: 1.7 !important;
    border: none !important;
    outline: none !important;
    resize: vertical !important;
    padding: 1rem 1.25rem !important;
    min-height: 360px !important;
}
.stTextArea > label { display: none !important; }
.stTextArea > div > div { border: none !important; background: transparent !important; }

/* ── Info Bar ─────────────────────────────────────────────── */
.info-bar {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-top: 0.75rem;
}
.info-pill {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.3rem 0.85rem;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--text-secondary);
}
.info-pill .dot-indicator {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent-green);
    box-shadow: 0 0 6px rgba(16,185,129,0.6);
}

/* ── Action Button ────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #7C3AED 0%, #6366F1 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--radius) !important;
    padding: 0.75rem 2rem !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    transition: var(--transition) !important;
    box-shadow: 0 4px 15px rgba(124,58,237,0.3) !important;
    width: 100% !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #6D28D9 0%, #4F46E5 100%) !important;
    box-shadow: 0 6px 25px rgba(124,58,237,0.5) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active {
    transform: translateY(0px) !important;
}

/* ── Success / Warning banners ────────────────────────────── */
.stSuccess, .stWarning, .stError, .stInfo {
    border-radius: var(--radius) !important;
    border-left-width: 4px !important;
}

/* ── Sidebar Tweaks ───────────────────────────────────────── */
[data-testid="stSidebarContent"] { padding: 1.5rem 1rem; }
.sidebar-logo {
    font-size: 1.4rem;
    font-weight: 800;
    background: linear-gradient(135deg, #A78BFA, #06B6D4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.25rem;
}
.sidebar-divider {
    height: 1px;
    background: var(--border);
    margin: 1rem 0;
}

/* ── Stat Card ────────────────────────────────────────────── */
.stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; margin-top: 0.5rem; }
.stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.75rem;
    text-align: center;
}
.stat-value {
    font-size: 1.4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #A78BFA, #06B6D4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.stat-label {
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 0.15rem;
}

/* ── Tooltip Card ─────────────────────────────────────────── */
.tooltip-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent-purple);
    border-radius: var(--radius);
    padding: 0.85rem 1rem;
    margin-top: 0.6rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.6;
}
.tooltip-card strong { color: var(--accent-violet); }
</style>
"""
