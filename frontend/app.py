"""
frontend/app.py
---------------
Streamlit UI — works with any uploaded PDF, any subject.

Pages:
    1. Upload     — drag-and-drop any PDF, triggers ingestion
    2. Generate   — select uploaded doc, enter any topic, generate
    3. Review     — spaced repetition card-flip mode
    4. Take Quiz  — answer the generated quiz

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

# ── Sidebar ───────────────────────────────────────────────────────────────────

page = st.sidebar.radio(
    "Navigate",
    ["Upload PDF", "Generate", "Review Cards", "Take Quiz"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Page 1: Upload ────────────────────────────────────────────────────────────

if page == "Upload PDF":
    st.title("Upload your document")
    st.caption("Upload any PDF — textbook, lecture notes, research paper, etc.")

    uploaded = st.file_uploader(
        "Choose a PDF file",
        type="pdf",
        help="Any PDF works. The system automatically parses and indexes it.",
    )

    if uploaded:
        st.info(f"Ready to ingest: **{uploaded.name}**")

        if st.button("Ingest PDF", type="primary"):
            with st.spinner(
                f"Parsing and indexing **{uploaded.name}**... "
                "This takes 1-2 minutes for a full textbook."
            ):
                resp = requests.post(
                    f"{API_BASE}/ingest",
                    data={"user_id": USER_ID},
                    files={
                        "file": (uploaded.name, uploaded.getvalue(), "application/pdf")
                    },
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

    st.divider()
    st.subheader("Previously uploaded documents")
    docs = fetch_documents()
    if docs:
        for d in docs:
            st.markdown(
                f"- **{d['filename']}** — "
                f"{d['page_count']} pages · {d['chunk_count']} chunks · "
                f"uploaded {d['ingested_at'][:10]}"
            )
    else:
        st.caption("No documents yet.")


# ── Page 2: Generate ──────────────────────────────────────────────────────────

elif page == "Generate":
    st.title("Generate flashcards + quiz")

    doc = document_selector()

    if doc:
        st.caption(
            f"Source: **{doc['filename']}** "
            f"({doc['chunk_count']} indexed chunks)"
        )

        topic = st.text_input(
            "Topic or keyword",
            placeholder="Enter any topic from your document...",
            help="Type any topic, chapter name, or concept from your PDF.",
        )

        col1, col2, col3 = st.columns(3)
        num_cards = col1.slider("Flashcards", 1, 20, 10)
        num_quiz  = col2.slider("Quiz questions", 1, 15, 5)
        quiz_type = col3.selectbox("Quiz type", ["mcq", "truefalse", "short"])

        if st.button("Generate", disabled=not topic, type="primary"):
            with st.spinner(
                f"Generating {num_cards} flashcards and {num_quiz} "
                f"{quiz_type} questions about **{topic}**..."
            ):
                resp = requests.post(
                    f"{API_BASE}/generate",
                    json={
                        "topic":       topic,
                        "document_id": doc["id"],
                        "num_cards":   num_cards,
                        "num_quiz":    num_quiz,
                        "quiz_type":   quiz_type,
                    },
                )

            if resp.status_code == 200:
                data = resp.json()
                st.session_state["last_generate"] = data

                st.subheader(f"Flashcards ({len(data['flashcards'])})")
                for i, card in enumerate(data["flashcards"], 1):
                    diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(
                        card["difficulty"], "⚪"
                    )
                    with st.expander(
                        f"{diff_icon} Card {i} — {card.get('topic', card['question'][:50])}"
                    ):
                        st.markdown(f"**Q:** {card['question']}")
                        st.markdown(f"**A:** {card['answer']}")
                        st.caption(
                            f"Difficulty: {card['difficulty']} · "
                            f"Page: {card.get('source_page', 'N/A')}"
                        )

                st.subheader(f"Quiz preview ({len(data['quiz'])})")
                for i, q in enumerate(data["quiz"], 1):
                    with st.expander(f"Q{i}: {q['question'][:70]}..."):
                        if q.get("options"):
                            for opt in q["options"]:
                                marker = "✅" if opt["is_correct"] else "○"
                                st.write(f"{marker} **{opt['label']}.** {opt['text']}")
                        else:
                            st.markdown(f"**Answer:** {q['answer']}")
                        if q.get("explanation"):
                            st.caption(f"Explanation: {q['explanation']}")

                st.success(
                    "Ready! Go to **Take Quiz** to test yourself "
                    "or **Review Cards** for spaced repetition."
                )
            else:
                st.error(f"Generation failed: {resp.text}")


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
                        json={
                            "flashcard_id": card["id"],
                            "user_id":      USER_ID,
                            "rating":       rating,
                        },
                    )
                    st.session_state["review_idx"] = idx + 1
                    st.rerun()

    elif cards and idx >= len(cards):
        st.balloons()
        st.success("All cards reviewed for today! Come back tomorrow for more.")
        st.session_state["due_cards"] = []


# ── Page 4: Quiz ──────────────────────────────────────────────────────────────

elif page == "Take Quiz":
    st.title("Quiz mode")

    data = st.session_state.get("last_generate")
    if not data or not data.get("quiz"):
        st.info("Go to **Generate** first to create a quiz from your document.")
        st.stop()

    questions = data["quiz"]
    doc_id    = data["document_id"]

    st.caption(f"{len(questions)} questions · {questions[0]['quiz_type']} format")

    if "quiz_answers" not in st.session_state:
        st.session_state["quiz_answers"] = {}

    for i, q in enumerate(questions):
        st.markdown(f"**Q{i+1}. {q['question']}**")

        if q["quiz_type"] == "mcq" and q.get("options"):
            opts   = [f"{o['label']}. {o['text']}" for o in q["options"]]
            answer = st.radio(
                "", opts, key=f"q_{i}", index=None,
                label_visibility="collapsed",
            )
            if answer:
                st.session_state["quiz_answers"][i] = answer[0]

        elif q["quiz_type"] == "truefalse":
            answer = st.radio(
                "", ["True", "False"], key=f"q_{i}", index=None,
                label_visibility="collapsed",
            )
            if answer:
                st.session_state["quiz_answers"][i] = answer

        elif q["quiz_type"] == "short":
            answer = st.text_input(
                "", key=f"q_{i}",
                placeholder="Type your answer...",
                label_visibility="collapsed",
            )
            if answer:
                st.session_state["quiz_answers"][i] = answer

        st.divider()

    answered  = len(st.session_state["quiz_answers"])
    submitted = st.button(
        f"Submit quiz ({answered}/{len(questions)} answered)",
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
                is_correct = (user_ans == q["answer"])
            elif q["quiz_type"] == "truefalse":
                is_correct = (user_ans.lower() == q["answer"].lower())

            correct += int(is_correct)
            results.append({
                "question":       q["question"],
                "your_answer":    user_ans,
                "correct_answer": q["answer"],
                "is_correct":     is_correct,
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

        st.metric("Your score", f"{correct}/{len(questions)}", f"{score*100:.0f}%")

        if score >= 0.8:
            st.success("Excellent! Great understanding of the material.")
        elif score >= 0.5:
            st.warning("Good effort — review the flashcards for the topics you missed.")
        else:
            st.error("Keep studying — go through Review Cards first, then retry.")

        st.subheader("Question breakdown")
        for i, r in enumerate(results, 1):
            icon = "✅" if r["is_correct"] else "❌"
            with st.expander(f"{icon} Q{i}: {r['question'][:60]}..."):
                st.write(f"**Your answer:** {r['your_answer'] or '(no answer)'}")
                if not r["is_correct"]:
                    st.write(f"**Correct answer:** {r['correct_answer']}")

        st.session_state.pop("quiz_answers", None)