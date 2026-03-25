"""
frontend/app.py
---------------
Streamlit UI — works with any uploaded PDF, any subject.

Pages:
    1. Upload PDF   — drag-and-drop any PDF, triggers ingestion
    2. Generate     — flashcard-only view with shuffle indicator
    3. Review Cards — spaced repetition card-flip mode
    4. Take Quiz    — answer quiz + post-submit breakdown review
    5. My Library   — browse uploaded documents

Run:
    streamlit run frontend/app.py
"""

import streamlit as st
import requests

API_BASE = "http://localhost:8000"
USER_ID  = "demo_user"

st.set_page_config(
    page_title="Flashcard AI",
    page_icon="🧠",
    layout="centered",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(160deg, #0d0d0d 0%, #111827 100%);
    border-right: 1px solid #1f2937;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 2rem; }

.brand-header {
    text-align: center; padding: 0 1.2rem 2rem;
    border-bottom: 1px solid #1f2937; margin-bottom: 1.5rem;
}
.brand-icon {
    font-size: 2.8rem; display: block; margin-bottom: 0.3rem;
    filter: drop-shadow(0 0 12px rgba(139,92,246,0.6));
}
.brand-name {
    font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.4rem;
    color: #fff; letter-spacing: -0.02em; display: block;
}
.brand-tagline {
    font-size: 0.7rem; color: #6b7280; letter-spacing: 0.12em;
    text-transform: uppercase; display: block; margin-top: 0.2rem;
}
div[data-testid="stSidebar"] .stButton > button {
    width: 100%; text-align: left; background: transparent; border: none;
    color: #9ca3af; font-family: 'DM Sans', sans-serif; font-size: 0.875rem;
    font-weight: 400; padding: 0.65rem 1.2rem; border-radius: 8px;
    margin-bottom: 2px; transition: all 0.15s ease; cursor: pointer;
}
div[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(139,92,246,0.12); color: #e5e7eb; transform: translateX(2px);
}
.nav-active > button {
    background: linear-gradient(90deg,rgba(139,92,246,0.2),rgba(139,92,246,0.06)) !important;
    color: #a78bfa !important; font-weight: 500 !important;
    border-left: 2px solid #8b5cf6 !important;
    padding-left: calc(1.2rem - 2px) !important;
}
.nav-section-label {
    font-size: 0.65rem; font-weight: 500; letter-spacing: 0.1em;
    text-transform: uppercase; color: #4b5563;
    padding: 0 1.2rem 0.4rem; margin-top: 0.5rem;
}
.sidebar-footer {
    margin-top: 2rem; padding: 1rem 1.2rem 0.5rem;
    border-top: 1px solid #1f2937; text-align: center;
}
.sidebar-footer span {
    font-size: 0.65rem; color: #374151; letter-spacing: 0.05em;
    display: block; line-height: 1.6;
}

/* ── Page headings ── */
h1 {
    font-family: 'Syne', sans-serif !important; font-weight: 800 !important;
    letter-spacing: -0.03em !important; color: #111827 !important;
}

/* ── Shuffle banner ── */
.shuffle-banner {
    display: flex; align-items: center; gap: 0.6rem;
    background: linear-gradient(90deg, #f5f3ff, #ede9fe);
    border: 1px solid #ddd6fe; border-radius: 10px;
    padding: 0.65rem 1rem; margin-bottom: 1.25rem;
    font-size: 0.8rem; color: #6d28d9; font-weight: 500;
}

/* ── Stats row ── */
.stats-row {
    display: flex; gap: 0.75rem; margin-bottom: 1.2rem; flex-wrap: wrap;
}
.stat-pill {
    background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 0.4rem 0.85rem; font-size: 0.78rem; color: #374151;
    font-weight: 500; white-space: nowrap;
}
.stat-pill span { color: #7c3aed; font-weight: 700; }

/* ── Flashcard grid ── */
.fc-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem; margin-top: 1rem;
}
.fc-card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 14px;
    padding: 1.1rem 1.2rem 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: box-shadow 0.15s ease, transform 0.15s ease;
    position: relative;
}
.fc-card:hover { box-shadow: 0 4px 16px rgba(109,40,217,0.12); transform: translateY(-2px); }
.fc-diff-bar {
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    border-radius: 14px 14px 0 0;
}
.fc-diff-easy   { background: #10b981; }
.fc-diff-medium { background: #f59e0b; }
.fc-diff-hard   { background: #ef4444; }
.fc-topic {
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #8b5cf6;
    margin-bottom: 0.4rem; margin-top: 0.2rem;
}
.fc-question {
    font-family: 'Syne', sans-serif; font-weight: 700; font-size: 0.92rem;
    color: #111827; line-height: 1.4; margin-bottom: 0.7rem;
}
.fc-answer {
    font-size: 0.82rem; color: #374151; line-height: 1.5;
    border-top: 1px solid #f3f4f6; padding-top: 0.6rem;
}
.fc-footer {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 0.6rem;
}
.fc-diff-label {
    font-size: 0.68rem; font-weight: 600; text-transform: capitalize;
    padding: 0.18rem 0.55rem; border-radius: 20px;
}
.diff-easy   { background: #d1fae5; color: #065f46; }
.diff-medium { background: #fef3c7; color: #92400e; }
.diff-hard   { background: #fee2e2; color: #991b1b; }
.fc-page { font-size: 0.68rem; color: #9ca3af; }

/* ── Quiz question block ── */
.quiz-q-block {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 1.2rem 1.3rem; margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.quiz-q-num {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #8b5cf6; margin-bottom: 0.4rem;
}
.quiz-q-text {
    font-family: 'Syne', sans-serif; font-weight: 700; font-size: 0.96rem;
    color: #111827; line-height: 1.45;
}

/* ── Score hero ── */
.score-hero {
    text-align: center; padding: 1.5rem;
    background: #f9fafb; border-radius: 16px;
    border: 1px solid #e5e7eb; margin-bottom: 1.5rem;
}
.score-number {
    font-family: 'Syne', sans-serif; font-size: 3rem;
    font-weight: 800; color: #111827; line-height: 1;
}
.score-pct { font-size: 1.1rem; color: #6b7280; margin-top: 0.2rem; }

/* ── Result cards ── */
.result-card {
    border-radius: 12px; padding: 1rem 1.2rem;
    margin-bottom: 0.75rem; border: 1px solid;
}
.result-correct   { background: #f0fdf4; border-color: #bbf7d0; }
.result-incorrect { background: #fff1f2; border-color: #fecdd3; }
.result-q   { font-weight: 600; font-size: 0.9rem; color: #111827; margin-bottom: 0.4rem; }
.result-row { font-size: 0.82rem; margin-top: 0.2rem; }
.result-your { color: #374151; }
.result-correct-ans { color: #065f46; font-weight: 600; }
.result-explanation { color: #6b7280; font-style: italic; margin-top: 0.4rem; }

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #f9fafb; border: 1px solid #e5e7eb;
    border-radius: 10px; padding: 1rem;
}

/* ── Doc cards ── */
.doc-card {
    background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px;
    padding: 0.9rem 1.1rem; margin-bottom: 0.6rem;
    display: flex; justify-content: space-between; align-items: center;
}
.doc-card-name {
    font-family: 'Syne', sans-serif; font-weight: 600;
    font-size: 0.9rem; color: #111827;
}
.doc-card-meta { font-size: 0.75rem; color: #6b7280; margin-top: 0.15rem; }
.doc-badge {
    background: #ede9fe; color: #7c3aed; font-size: 0.7rem; font-weight: 600;
    padding: 0.25rem 0.6rem; border-radius: 20px; white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────

if "page" not in st.session_state:
    st.session_state["page"] = "Upload PDF"


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div class="brand-header">
        <span class="brand-icon">🧠</span>
        <span class="brand-name">Flashcard AI</span>
        <span class="brand-tagline">Study smarter, not harder</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="nav-section-label">Main</div>', unsafe_allow_html=True)

    nav_items = [
        ("📄", "Upload PDF",   "Add a new document"),
        ("⚡", "Generate",     "Create flashcards"),
        ("🔁", "Review Cards", "Spaced repetition session"),
        ("✏️", "Take Quiz",    "Test your knowledge"),
        ("📚", "My Library",   "Browse uploaded documents"),
    ]

    for icon, label, _ in nav_items:
        is_active = st.session_state["page"] == label
        with st.container():
            if is_active:
                st.markdown('<div class="nav-active">', unsafe_allow_html=True)
            clicked = st.button(f"{icon}  {label}", key=f"nav_{label}")
            if is_active:
                st.markdown("</div>", unsafe_allow_html=True)
            if clicked:
                st.session_state["page"] = label
                st.rerun()

    st.markdown("""
    <div class="sidebar-footer">
        <span>SM-2 spaced repetition scheduling</span>
    </div>
    """, unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

page = st.session_state["page"]


def fetch_documents() -> list[dict]:
    try:
        resp = requests.get(f"{API_BASE}/documents", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("documents", [])
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the API. Make sure uvicorn is running on port 8000.")
    return []


def document_selector(label: str = "Select your uploaded document") -> dict | None:
    docs = fetch_documents()
    if not docs:
        st.warning("No documents uploaded yet. Go to **Upload PDF** first.")
        return None
    options = {f"{d['filename']}  ({d['chunk_count']} chunks)": d for d in docs}
    choice  = st.selectbox(label, list(options.keys()))
    return options[choice]


def render_fc_grid(cards: list[dict]) -> None:
    """Renders the flashcard CSS grid."""
    dc_map = {"easy": "easy", "medium": "medium", "hard": "hard"}
    st.markdown('<div class="fc-grid">', unsafe_allow_html=True)
    for card in cards:
        diff = card.get("difficulty", "medium")
        dc   = dc_map.get(diff, "medium")
        st.markdown(f"""
        <div class="fc-card">
            <div class="fc-diff-bar fc-diff-{dc}"></div>
            <div class="fc-topic">{card.get('topic', '')}</div>
            <div class="fc-question">{card['question']}</div>
            <div class="fc-answer">{card['answer']}</div>
            <div class="fc-footer">
                <span class="fc-diff-label diff-{dc}">{diff}</span>
                <span class="fc-page">p. {card.get('source_page', '?')}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_stats_row(cards: list[dict], extra: str = "") -> None:
    easy   = sum(1 for c in cards if c.get("difficulty") == "easy")
    medium = sum(1 for c in cards if c.get("difficulty") == "medium")
    hard   = sum(1 for c in cards if c.get("difficulty") == "hard")
    extra_pill = f'<div class="stat-pill">{extra}</div>' if extra else ""
    st.markdown(f"""
    <div class="stats-row">
        <div class="stat-pill">Total <span>{len(cards)}</span></div>
        <div class="stat-pill">🟢 Easy <span>{easy}</span></div>
        <div class="stat-pill">🟡 Medium <span>{medium}</span></div>
        <div class="stat-pill">🔴 Hard <span>{hard}</span></div>
        {extra_pill}
    </div>
    """, unsafe_allow_html=True)


# ── Page 1: Upload ────────────────────────────────────────────────────────────

if page == "Upload PDF":
    st.title("Upload a document")
    st.caption("Upload any PDF — textbook, lecture notes, research paper, etc.")

    uploaded = st.file_uploader(
        "Choose a PDF file", type="pdf",
        help="Any PDF works. The system automatically parses and indexes it.",
    )

    if uploaded:
        st.info(f"Ready to ingest: **{uploaded.name}**")
        if st.button("Ingest PDF", type="primary"):
            with st.spinner(f"Parsing and indexing **{uploaded.name}**… this may take a minute."):
                resp = requests.post(
                    f"{API_BASE}/ingest",
                    data={"user_id": USER_ID},
                    files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                )
            if resp.status_code == 200:
                data = resp.json()
                st.success(
                    f"Done! Indexed **{data['chunk_count']} chunks** "
                    f"from **{data['page_count']} pages**."
                )
                st.session_state["document_id"] = data["document_id"]
                col1, col2, col3 = st.columns(3)
                col1.metric("Pages",  data["page_count"])
                col2.metric("Chunks", data["chunk_count"])
                col3.metric("File",   data["filename"])
                st.caption(f"Document ID: `{data['document_id']}`")
                st.info("Head to **Generate** to create flashcards from this document.")
            else:
                st.error(f"Ingestion failed: {resp.text}")


# ── Page 2: Generate (flashcards only) ───────────────────────────────────────

elif page == "Generate":
    st.title("Generate flashcards")

    doc = document_selector()

    if doc:
        st.caption(f"Source: **{doc['filename']}** · {doc['chunk_count']} indexed chunks")

        col_a, col_b = st.columns([3, 1])
        topic     = col_a.text_input(
            "Topic or keyword",
            placeholder="e.g. mitosis, supply and demand, World War I…",
            help="Any topic, chapter name, or concept from your PDF.",
        )
        num_cards = col_b.number_input("Cards", min_value=1, max_value=20, value=10, step=1)

        with st.expander("⚙️  Quiz settings (used on Take Quiz)", expanded=False):
            cq1, cq2 = st.columns(2)
            num_quiz  = cq1.slider("Quiz questions", 1, 15, 5)
            quiz_type = cq2.selectbox("Quiz type", ["mcq", "truefalse", "short"])
            st.caption("These settings apply when you head to **Take Quiz**.")

        generate_clicked = st.button(
            "🔀  Shuffle & Generate",
            disabled=not topic,
            type="primary",
            help="Generates a fresh, randomly ordered set every time — no repeats!",
        )

        if generate_clicked:
            with st.spinner(
                f"Shuffling the deck and generating **{int(num_cards)} cards** on **{topic}**…"
            ):
                resp = requests.post(
                    f"{API_BASE}/generate",
                    json={
                        "topic":       topic,
                        "document_id": doc["id"],
                        "num_cards":   int(num_cards),
                        "num_quiz":    num_quiz,
                        "quiz_type":   quiz_type,
                    },
                )

            if resp.status_code == 200:
                data = resp.json()
                st.session_state["last_generate"]   = data
                st.session_state["generate_topic"]  = topic
                # Reset quiz state so Take Quiz starts fresh
                st.session_state["quiz_state"]      = "answering"
                st.session_state["quiz_answers"]    = {}
                st.session_state["quiz_results"]    = []

                cards = data["flashcards"]

                st.markdown(f"""
                <div class="shuffle-banner">
                    🔀&nbsp;&nbsp;Fresh shuffle complete — <strong>{len(cards)} unique cards</strong>
                    generated for <em>{topic}</em>.
                    Questions are randomised every time so you never see the same set twice.
                </div>
                """, unsafe_allow_html=True)

                render_stats_row(cards, extra=f"📄 {doc['filename'].split('.')[0][:20]}")
                render_fc_grid(cards)

                st.markdown("")
                st.success(
                    f"✅ {len(cards)} cards ready! "
                    "Head to **Review Cards** for spaced repetition or **Take Quiz** to test yourself."
                )

            else:
                st.error(f"Generation failed: {resp.text}")

        # Show persisted cards from last run
        elif st.session_state.get("last_generate"):
            cards = st.session_state["last_generate"].get("flashcards", [])
            prev_topic = st.session_state.get("generate_topic", "")
            if cards:
                st.markdown(
                    f"*Showing last generated set — topic: **{prev_topic}**. "
                    "Enter a topic above and hit Generate to reshuffle.*"
                )
                render_stats_row(cards)
                render_fc_grid(cards)


# ── Page 3: Review cards ──────────────────────────────────────────────────────

elif page == "Review Cards":
    st.title("Review due cards")
    st.caption("Cards are scheduled using SM-2 spaced repetition.")

    if st.button("Load due cards", type="primary"):
        resp = requests.get(f"{API_BASE}/review/{USER_ID}")
        if resp.status_code == 200:
            data = resp.json()
            st.session_state["due_cards"]  = data["cards"]
            st.session_state["review_idx"] = 0
            if data["due_count"] == 0:
                st.info("No cards due today. Generate some flashcards first!")
            else:
                st.success(f"{data['due_count']} cards due for review today.")

    cards = st.session_state.get("due_cards", [])
    idx   = st.session_state.get("review_idx", 0)

    if cards and idx < len(cards):
        card = cards[idx]
        st.progress(idx / len(cards), text=f"Card {idx + 1} of {len(cards)}")
        st.markdown("---")

        diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(
            card.get("difficulty", ""), "⚪"
        )
        st.caption(f"{diff_icon} {card.get('difficulty', '').capitalize()}")
        st.markdown(f"### {card['question']}")
        if card.get("topic"):
            st.caption(f"Topic: {card['topic']}")

        st.markdown("---")
        show = st.toggle("Reveal answer")

        if show:
            st.success(card["answer"])
            st.write("How well did you recall this?")
            cols    = st.columns(4)
            ratings = [
                ("Again", 0, "Forgot completely"),
                ("Hard",  3, "Got it, but tough"),
                ("Good",  4, "Recalled with effort"),
                ("Easy",  5, "Instant recall"),
            ]
            for col, (label, rating, tooltip) in zip(cols, ratings):
                if col.button(label, key=f"rate_{rating}", help=tooltip):
                    requests.post(
                        f"{API_BASE}/review/submit",
                        json={"flashcard_id": card["id"], "user_id": USER_ID, "rating": rating},
                    )
                    st.session_state["review_idx"] = idx + 1
                    st.rerun()

    elif cards and idx >= len(cards):
        st.balloons()
        st.success("All cards reviewed for today! Come back tomorrow for more.")
        st.session_state["due_cards"] = []


# ── Page 4: Take Quiz + post-submit review breakdown ─────────────────────────

elif page == "Take Quiz":
    st.title("Take Quiz")

    data = st.session_state.get("last_generate")
    if not data or not data.get("quiz"):
        st.info("Go to **Generate** first to create a quiz from your document.")
        st.stop()

    questions = data["quiz"]
    doc_id    = data["document_id"]

    # Init quiz state machine
    if "quiz_state" not in st.session_state:
        st.session_state["quiz_state"]   = "answering"
        st.session_state["quiz_answers"] = {}
        st.session_state["quiz_results"] = []

    # ─── STATE A: answering ───────────────────────────────────────────────────
    if st.session_state["quiz_state"] == "answering":

        topic_label = st.session_state.get("generate_topic", "")
        st.caption(
            f"{len(questions)} questions · "
            f"{questions[0]['quiz_type'].upper()} format"
            + (f" · {topic_label}" if topic_label else "")
        )

        for i, q in enumerate(questions):
            qtype = q["quiz_type"]
            st.markdown(f"""
            <div class="quiz-q-block">
                <div class="quiz-q-num">Question {i+1} of {len(questions)}</div>
                <div class="quiz-q-text">{q['question']}</div>
            </div>
            """, unsafe_allow_html=True)

            if qtype == "mcq" and q.get("options"):
                opts   = [f"{o['label']}.  {o['text']}" for o in q["options"]]
                answer = st.radio(
                    "", opts, key=f"q_{i}", index=None,
                    label_visibility="collapsed",
                )
                if answer:
                    st.session_state["quiz_answers"][i] = answer.split(".")[0].strip()

            elif qtype == "truefalse":
                answer = st.radio(
                    "", ["True", "False"], key=f"q_{i}", index=None,
                    label_visibility="collapsed",
                )
                if answer:
                    st.session_state["quiz_answers"][i] = answer

            elif qtype == "short":
                answer = st.text_input(
                    "", key=f"q_{i}",
                    placeholder="Type your answer…",
                    label_visibility="collapsed",
                )
                if answer:
                    st.session_state["quiz_answers"][i] = answer

        answered = len(st.session_state["quiz_answers"])
        st.markdown("")
        submitted = st.button(
            f"Submit Quiz  ({answered}/{len(questions)} answered)",
            type="primary",
            disabled=(answered == 0),
        )

        if submitted:
            correct = 0
            results = []
            for i, q in enumerate(questions):
                user_ans   = st.session_state["quiz_answers"].get(i, "")
                is_correct = False
                if q["quiz_type"] == "mcq":
                    is_correct = (user_ans.upper() == str(q["answer"]).upper())
                elif q["quiz_type"] == "truefalse":
                    is_correct = (user_ans.lower() == str(q["answer"]).lower())
                correct += int(is_correct)
                results.append({
                    "question":       q["question"],
                    "your_answer":    user_ans,
                    "correct_answer": q.get("answer", ""),
                    "explanation":    q.get("explanation", ""),
                    "is_correct":     is_correct,
                    "quiz_type":      q["quiz_type"],
                })

            score = correct / len(questions)
            requests.post(
                f"{API_BASE}/quiz/submit",
                data={
                    "user_id":     USER_ID,
                    "document_id": doc_id,
                    "score":       score,
                    "total":       len(questions),
                    "correct":     correct,
                    "quiz_type":   questions[0]["quiz_type"],
                },
            )
            st.session_state["quiz_state"]   = "submitted"
            st.session_state["quiz_results"] = results
            st.session_state["quiz_score"]   = (correct, len(questions), score)
            st.rerun()

    # ─── STATE B: results + question breakdown ────────────────────────────────
    elif st.session_state["quiz_state"] == "submitted":
        correct, total, score = st.session_state["quiz_score"]
        results = st.session_state["quiz_results"]

        pct = f"{score * 100:.0f}%"
        if score >= 0.8:
            verdict       = "🎉 Excellent work!"
            verdict_color = "#065f46"
        elif score >= 0.5:
            verdict       = "👍 Good effort — review the topics you missed"
            verdict_color = "#92400e"
        else:
            verdict       = "📖 Keep studying — try Review Cards first"
            verdict_color = "#991b1b"

        st.markdown(f"""
        <div class="score-hero">
            <div class="score-number">{correct}<span style="color:#9ca3af;font-size:1.8rem">/{total}</span></div>
            <div class="score-pct">{pct} correct</div>
            <div style="margin-top:0.5rem;font-weight:600;color:{verdict_color}">{verdict}</div>
        </div>
        """, unsafe_allow_html=True)

        wrong = total - correct
        st.markdown(f"""
        <div class="stats-row" style="justify-content:center">
            <div class="stat-pill">✅ Correct <span>{correct}</span></div>
            <div class="stat-pill">❌ Wrong <span>{wrong}</span></div>
            <div class="stat-pill">📊 Score <span>{pct}</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### Question breakdown")

        for i, r in enumerate(results, 1):
            css   = "result-correct" if r["is_correct"] else "result-incorrect"
            icon  = "✅" if r["is_correct"] else "❌"

            correct_row = ""
            if not r["is_correct"] and r["correct_answer"]:
                correct_row = (
                    f'<div class="result-row result-correct-ans">'
                    f'✔ Correct answer: {r["correct_answer"]}</div>'
                )

            exp_row = ""
            if r.get("explanation") and not r["is_correct"]:
                exp_row = (
                    f'<div class="result-row result-explanation">'
                    f'💡 {r["explanation"]}</div>'
                )

            st.markdown(f"""
            <div class="result-card {css}">
                <div class="result-q">{icon} Q{i}. {r['question']}</div>
                <div class="result-row result-your">
                    Your answer: <strong>{r['your_answer'] or '(no answer)'}</strong>
                </div>
                {correct_row}
                {exp_row}
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")
        col1, col2 = st.columns(2)
        if col1.button("🔄  Retake quiz", type="primary"):
            st.session_state["quiz_state"]   = "answering"
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_results"] = []
            st.rerun()
        if col2.button("⚡  Generate new quiz"):
            st.session_state["page"]         = "Generate"
            st.session_state["quiz_state"]   = "answering"
            st.session_state["quiz_answers"] = {}
            st.rerun()


# ── Page 5: My Library ────────────────────────────────────────────────────────

elif page == "My Library":
    st.title("My Library")
    st.caption("Browse and manage your uploaded documents.")

    with st.expander("🔽  Filter & sort options", expanded=False):
        col1, col2 = st.columns(2)
        sort_by    = col1.selectbox("Sort by", ["Newest first", "Oldest first", "Name A–Z", "Most chunks"])
        filter_kw  = col2.text_input("Search by filename", placeholder="e.g. biology…")

    st.divider()
    docs = fetch_documents()

    if not docs:
        st.info("No documents yet. Head to **Upload PDF** to get started.")
    else:
        if filter_kw:
            docs = [d for d in docs if filter_kw.lower() in d["filename"].lower()]
        if sort_by == "Oldest first":
            docs = sorted(docs, key=lambda d: d["ingested_at"])
        elif sort_by == "Name A–Z":
            docs = sorted(docs, key=lambda d: d["filename"].lower())
        elif sort_by == "Most chunks":
            docs = sorted(docs, key=lambda d: d["chunk_count"], reverse=True)
        else:
            docs = sorted(docs, key=lambda d: d["ingested_at"], reverse=True)

        st.caption(f"Showing **{len(docs)}** document{'s' if len(docs) != 1 else ''}")

        for d in docs:
            st.markdown(f"""
            <div class="doc-card">
                <div>
                    <div class="doc-card-name">📄 {d['filename']}</div>
                    <div class="doc-card-meta">
                        {d['page_count']} pages · uploaded {d['ingested_at'][:10]}
                    </div>
                </div>
                <div class="doc-badge">{d['chunk_count']} chunks</div>
            </div>
            """, unsafe_allow_html=True)