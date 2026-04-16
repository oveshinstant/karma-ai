import streamlit as st
import anthropic
import requests
import json
import os
from datetime import datetime

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Karma AI",
    page_icon="🚀",
    layout="wide"
)

# ─────────────────────────────────────────
# MEMORY FILE — disk pe save hota hai
# ─────────────────────────────────────────
MEMORY_FILE = "karma_memory.json"

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"sessions": [], "total_queries": 0}

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

def add_to_memory(query, goal_type, plan):
    memory = load_memory()
    session = {
        "id": len(memory["sessions"]) + 1,
        "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "query": query,
        "goal_type": goal_type,
        "plan": plan
    }
    memory["sessions"].append(session)
    memory["total_queries"] = len(memory["sessions"])
    save_memory(memory)

# ─────────────────────────────────────────
# SESSION STATE — conversation ke liye
# ─────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "current_plan" not in st.session_state:
    st.session_state.current_plan = None

if "current_query" not in st.session_state:
    st.session_state.current_query = None

if "workflow_stage" not in st.session_state:
    st.session_state.workflow_stage = "idle"

# ─────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚀 Karma AI")
    st.caption("Sirf jawab nahi — poora kaam")
    st.divider()

    st.markdown("### ⚙️ API Keys")
    claude_key = st.text_input(
        "Claude API Key *", type="password", placeholder="sk-ant-..."
    )
    perplexity_key = st.text_input(
        "Perplexity API Key", type="password", placeholder="pplx-... (optional)"
    )
    st.caption("Keys sirf tumhare browser me hain — safe hai")

    st.divider()

    # ── MEMORY HISTORY ──────────────────
    st.markdown("### 🧠 Purani Queries")
    memory = load_memory()

    if memory["sessions"]:
        st.caption(f"Total saved plans: {memory['total_queries']}")
        for session in reversed(memory["sessions"][-5:]):
            with st.expander(f"#{session['id']} — {session['timestamp'][:11]}"):
                st.markdown(f"**Goal:** {session['goal_type']}")
                st.markdown(f"**Sawaal:** {session['query'][:70]}...")
                if st.button("📂 Load Karo", key=f"load_{session['id']}"):
                    st.session_state.current_plan = session["plan"]
                    st.session_state.current_query = session["query"]
                    st.session_state.chat_history = []
                    st.rerun()

        if st.button("🗑️ Sab Memory Clear", type="secondary", use_container_width=True):
            save_memory({"sessions": [], "total_queries": 0})
            st.session_state.current_plan = None
            st.session_state.current_query = None
            st.session_state.chat_history = []
            st.rerun()
    else:
        st.caption("Abhi koi history nahi hai")

# ─────────────────────────────────────────
# MAIN AREA
# ─────────────────────────────────────────
col1, col2 = st.columns([1.2, 1], gap="large")

# ══════════════════════════════════════════
# LEFT — INPUT + WORKFLOW STEPS
# ══════════════════════════════════════════
with col1:
    st.markdown("### 💬 Kya karna chahte ho?")

    query = st.text_area(
        "Sawaal",
        placeholder="Example: Mujhe YouTube channel start karna hai cooking ke liye, budget 20,000 rupaye hai...",
        height=110,
        label_visibility="collapsed"
    )

    goal_type = st.selectbox(
        "Goal Type:",
        [
            "Business Start Karna",
            "Content / YouTube / Social Media",
            "Paisa Invest / Bachana",
            "Job / Career / Freelancing",
            "Study / Skills Seekhna",
            "Kuch Aur"
        ]
    )

    # Workflow steps — visual progress
    st.markdown("#### ⚡ Workflow")
    step_col1, step_col2, step_col3 = st.columns(3)
    stage = st.session_state.workflow_stage

    with step_col1:
        if stage in ("researching",):
            st.info("🔍 **Research**\nHo raha hai...")
        elif stage in ("planning", "done"):
            st.success("🔍 **Research**\n✅ Done")
        else:
            st.markdown("🔍 **Research**\nPerplexity se")

    with step_col2:
        if stage == "planning":
            st.info("🧠 **Planning**\nHo raha hai...")
        elif stage == "done":
            st.success("🧠 **Planning**\n✅ Done")
        else:
            st.markdown("🧠 **Planning**\nClaude se")

    with step_col3:
        if stage == "done":
            st.success("💾 **Memory**\n✅ Saved")
        else:
            st.markdown("💾 **Memory**\nAuto save")

    st.markdown("")

    run_btn = st.button("🔥 Kaam Shuru Karo", type="primary", use_container_width=True)

    if run_btn:
        if not query.strip():
            st.error("Kuch toh poocho bhai! 😄")
            st.stop()
        if not claude_key.strip():
            st.error("Sidebar me Claude API Key daalo pehle!")
            st.stop()

        # Pichla context — agar pehle se plan hai
        previous_context = ""
        if st.session_state.current_plan:
            previous_context = (
                f"\n\nPIEHLA CONTEXT (yaad rakhna):\n"
                f"Pichla sawaal: {st.session_state.current_query}\n"
                f"Pichle plan ki summary: {st.session_state.current_plan[:400]}...\n"
                f"Naya sawaal is context se connect karo agar relevant ho.\n"
            )

        # ── STEP 1: RESEARCH ─────────────
        st.session_state.workflow_stage = "researching"
        research_result = ""

        with st.spinner("🔍 Step 1 — Research ho rahi hai..."):
            if perplexity_key.strip():
                try:
                    headers = {
                        "Authorization": f"Bearer {perplexity_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": "sonar",
                        "messages": [{
                            "role": "user",
                            "content": (
                                f"India ke context me research karo: {query}. "
                                "Latest data, trends, realistic costs, competition level, aur key insights do."
                            )
                        }]
                    }
                    resp = requests.post(
                        "https://api.perplexity.ai/chat/completions",
                        json=payload, headers=headers, timeout=30
                    )
                    resp.raise_for_status()
                    research_result = resp.json()["choices"][0]["message"]["content"]
                except Exception:
                    research_result = ""

        # ── STEP 2: CLAUDE PLAN ──────────
        st.session_state.workflow_stage = "planning"

        with st.spinner("🧠 Step 2 — Plan ban raha hai..."):
            try:
                client = anthropic.Anthropic(api_key=claude_key)

                research_block = (
                    f"\n\nLatest Research Data (Perplexity):\n{research_result}"
                    if research_result else ""
                )

                prompt = f"""Tu Karma AI hai — ek expert Indian advisor jo sirf kaam karta hai, bakwaas nahi.
{previous_context}
User ka Goal Type: {goal_type}
User ka Sawaal: {query}{research_block}

Ek complete, actionable plan do:

## 🔍 Situation Analysis
(3 lines — kya ho raha hai, kya opportunity hai)

## 💡 Top 3 Options
Option 1: [naam] — fayde: ___ / nuksan: ___
Option 2: [naam] — fayde: ___ / nuksan: ___
Option 3: [naam] — fayde: ___ / nuksan: ___

## ✅ Best Choice & Kyun
(Clear bolo — kaunsa choose karo aur kyun)

## 📅 7-Din Action Plan
Din 1-2: [specific action]
Din 3-4: [specific action]
Din 5-6: [specific action]
Din 7: [specific action + review]

## 💰 Budget Breakdown (Indian Context)
Minimum: ₹___
Comfortable: ₹___
Ideal: ₹___

## ⚠️ Top 3 Risks + Solutions
1. Risk: ___ → Solution: ___
2. Risk: ___ → Solution: ___
3. Risk: ___ → Solution: ___

## 🚀 Ek Line Me Summary
[Powerful one-liner]

Hinglish me. Actionable. India-specific. No vague advice."""

                message = client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}]
                )

                final_plan = message.content[0].text

            except anthropic.AuthenticationError:
                st.error("❌ Claude API Key galat hai! Check karo.")
                st.session_state.workflow_stage = "idle"
                st.stop()
            except Exception as e:
                st.error(f"❌ Error aaya: {e}")
                st.session_state.workflow_stage = "idle"
                st.stop()

        # ── STEP 3: MEMORY SAVE ──────────
        with st.spinner("💾 Step 3 — Memory me save ho raha hai..."):
            add_to_memory(query, goal_type, final_plan)
            st.session_state.current_plan = final_plan
            st.session_state.current_query = query
            st.session_state.chat_history = []
            st.session_state.workflow_stage = "done"

        st.rerun()

# ══════════════════════════════════════════
# RIGHT — PLAN + FOLLOW-UP CHAT
# ══════════════════════════════════════════
with col2:

    if st.session_state.current_plan:

        tab1, tab2 = st.tabs(["📋 Tera Plan", "💬 Follow-up Chat"])

        # ── TAB 1: PLAN ──────────────────
        with tab1:
            if st.session_state.current_query:
                st.caption(f"**Sawaal:** {st.session_state.current_query}")
            st.markdown(st.session_state.current_plan)
            st.divider()

            download_text = (
                f"KARMA AI PLAN\n"
                f"{'='*40}\n"
                f"Sawaal: {st.session_state.current_query}\n"
                f"Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n"
                f"{'='*40}\n\n"
                f"{st.session_state.current_plan}"
            )
            st.download_button(
                "📥 Plan Download Karo (.txt)",
                data=download_text,
                file_name="karma-ai-plan.txt",
                mime="text/plain",
                use_container_width=True
            )

        # ── TAB 2: FOLLOW-UP CHAT ────────
        with tab2:
            st.caption("Plan ke baare me kuch bhi poocho — context yaad hai 🧠")

            # Chat history dikhao
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            follow_up = st.chat_input(
                "Koi sawal? Jaise: Budget kam ho toh kya karu? / Aur detail chahiye..."
            )

            if follow_up:
                if not claude_key.strip():
                    st.error("Sidebar me Claude API Key daalo!")
                    st.stop()

                with st.chat_message("user"):
                    st.markdown(follow_up)
                st.session_state.chat_history.append({"role": "user", "content": follow_up})

                with st.chat_message("assistant"):
                    with st.spinner("Soch raha hoon..."):
                        try:
                            client = anthropic.Anthropic(api_key=claude_key)

                            # Pura context — plan + chat history
                            messages = [
                                {
                                    "role": "user",
                                    "content": (
                                        f"Tu Karma AI hai. Yeh plan pehle bana tha:\n\n"
                                        f"{st.session_state.current_plan}\n\n"
                                        f"Ab follow-up questions aayenge. Context yaad rakh."
                                    )
                                },
                                {
                                    "role": "assistant",
                                    "content": "Haan, plan samajh gaya. Poocho kya jaanna hai!"
                                }
                            ]

                            # Purani chat add karo
                            for msg in st.session_state.chat_history[:-1]:
                                messages.append({
                                    "role": msg["role"],
                                    "content": msg["content"]
                                })

                            messages.append({"role": "user", "content": follow_up})

                            resp = client.messages.create(
                                model="claude-opus-4-5",
                                max_tokens=800,
                                messages=messages
                            )

                            reply = resp.content[0].text
                            st.markdown(reply)
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": reply
                            })

                        except Exception as e:
                            st.error(f"Error: {e}")

    else:
        # Empty state
        st.markdown("### 👈 Wahan se shuru karo")
        st.markdown("""
**Karma AI kya karta hai:**

🔍 **Step 1 — Research**
Perplexity se latest Indian market data laata hai

🧠 **Step 2 — Planning**  
Claude se complete action plan banata hai

💾 **Step 3 — Memory**
Teri query aur plan automatically save hoti hai

💬 **Follow-up Chat**
Plan ke baare me aur kuch poocho — context yaad rehta hai

📂 **History**
Purane plans sidebar se wapas load kar sakte ho
        """)

        memory = load_memory()
        if memory["sessions"]:
            st.info(f"💡 Tumhare {memory['total_queries']} purane plans hain — sidebar se load karo!")
