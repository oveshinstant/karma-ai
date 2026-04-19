import streamlit as st
import anthropic
import requests
import json
import os
import hashlib
import uuid
from datetime import datetime, date

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Karma AI — Work Engine",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2rem; font-weight: 800;
        background: linear-gradient(90deg, #6C63FF, #FF6584);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .stButton > button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stExpander"] { border: 1px solid #333; border-radius: 8px; }
    .kit-box {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #6C63FF; border-radius: 12px; padding: 16px; margin: 8px 0;
    }
    .viral-badge {
        background: linear-gradient(90deg, #FF6584, #FF9A56);
        border-radius: 6px; padding: 4px 10px; font-size: 0.8rem; font-weight: 700; color: white;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# API KEYS
# ─────────────────────────────────────────
def get_secret(key):
    try:
        return st.secrets[key]
    except:
        return ""

CLAUDE_KEY     = get_secret("CLAUDE_API_KEY")
PERPLEXITY_KEY = get_secret("PERPLEXITY_API_KEY")
GEMINI_KEY     = get_secret("GEMINI_API_KEY")


# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────
FREE_DAILY_LIMIT = 5
DATA_FILE        = "karma_data.json"
BACKUP_FILE      = "karma_data_backup.json"
CACHE_FILE       = "karma_cache.json"

COMPLEX_KEYWORDS = [
    "business","plan","strategy","launch","startup","career","invest",
    "youtube","content","marketing","study","course","freelance","script",
    "brand","budget","project","app","website","channel","product","sales"
]

# ── NEW: keyword lists for new modes ──────
IMAGE_KEYWORDS  = ["logo","thumbnail","poster","design","image","banner","cover","visual","graphic","icon"]
VIRAL_KEYWORDS  = ["build in 7 days","full system","complete business","7 day","full plan",
                   "complete system","viral","grow fast","scale","full roadmap","zero to"]

# ─────────────────────────────────────────
# DB LAYER
# ─────────────────────────────────────────
def _empty_db():
    return {"users":{},"all_queries":[],"total_sessions":0,"popular_goals":{},"version":"1.0"}

def db_read():
    for path in [DATA_FILE, BACKUP_FILE]:
        if os.path.exists(path):
            try:
                with open(path,"r",encoding="utf-8") as f:
                    data = json.load(f)
                for k,v in _empty_db().items():
                    data.setdefault(k,v)
                return data
            except (json.JSONDecodeError, IOError):
                continue
    return _empty_db()

def db_write(data):
    try:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE,"r") as f: backup=f.read()
                with open(BACKUP_FILE,"w") as f: f.write(backup)
            except: pass
        with open(DATA_FILE,"w",encoding="utf-8") as f:
            json.dump(data,f,indent=2,ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Save error: {e}"); return False

def db_get_user(user_id):
    data  = db_read()
    today = str(date.today())
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "id":user_id,"is_premium":False,"sessions":[],"goals":[],
            "joined":today,"last_active":today,"total_queries":0,
            "daily":{"date":today,"count":0}
        }
        db_write(data)
    user = data["users"][user_id]
    if user.get("daily",{}).get("date") != today:
        user["daily"] = {"date":today,"count":0}
        data["users"][user_id] = user
        db_write(data)
    return user

def db_save_session(user_id, query, goal_type, plan, model_used):
    data  = db_read()
    today = str(date.today())
    user  = data["users"].get(user_id, db_get_user(user_id))
    session = {
        "id": len(user["sessions"])+1,
        "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "query": query, "goal_type": goal_type,
        "plan": plan,   "model_used": model_used
    }
    user["sessions"].append(session)
    user["total_queries"] = user.get("total_queries",0)+1
    user["last_active"]   = today
    if "daily" not in user or user["daily"].get("date") != today:
        user["daily"] = {"date":today,"count":0}
    user["daily"]["count"] += 1
    if goal_type not in user.get("goals",[]):
        user.setdefault("goals",[]).append(goal_type)
    data["users"][user_id] = user
    data["all_queries"].append({"date":today,"goal_type":goal_type,"model":model_used,"query_len":len(query)})
    data["total_sessions"] = data.get("total_sessions",0)+1
    data.setdefault("popular_goals",{})[goal_type] = data["popular_goals"].get(goal_type,0)+1
    db_write(data)
    return session["id"]

# ─────────────────────────────────────────
# PERSISTENT USER ID
# ─────────────────────────────────────────
def get_persistent_user_id():
    if "uid" in st.query_params:
        uid = st.query_params["uid"]
        st.session_state["_uid"] = uid
        return uid
    if "_uid" in st.session_state:
        uid = st.session_state["_uid"]
        st.query_params["uid"] = uid
        return uid
    uid = "u_" + uuid.uuid4().hex[:12]
    st.session_state["_uid"] = uid
    st.query_params["uid"]   = uid
    return uid

# ─────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────
def cache_get(query_hash):
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE,"r") as f: cache=json.load(f)
            entry = cache.get(query_hash)
            if entry and entry.get("date")==str(date.today()):
                return entry.get("plan")
    except: pass
    return None

def cache_set(query_hash, plan):
    try:
        cache = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE,"r") as f: cache=json.load(f)
        cache[query_hash] = {"plan":plan,"date":str(date.today())}
        if len(cache)>100: del cache[list(cache.keys())[0]]
        with open(CACHE_FILE,"w") as f: json.dump(cache,f,ensure_ascii=False)
    except: pass

def make_cache_key(query, goal_type, language, mode="normal"):
    raw = f"{query.strip().lower()}|{goal_type}|{language}|{mode}"
    return hashlib.md5(raw.encode()).hexdigest()

# ─────────────────────────────────────────
# LIMIT CHECK
# ─────────────────────────────────────────
def check_limit(user):
    if user.get("is_premium"): return True, 999
    today = str(date.today())
    daily = user.get("daily",{})
    if daily.get("date") != today: return True, FREE_DAILY_LIMIT
    used = daily.get("count",0)
    return max(FREE_DAILY_LIMIT-used,0)>0, max(FREE_DAILY_LIMIT-used,0)

# ─────────────────────────────────────────
# SMART QUERY ROUTER  ← NEW modes added
# ─────────────────────────────────────────
def route_query(query, do_it_mode=False):
    """
    Returns: "image" | "viral" | "do_it" | "complex" | "simple"
    """
    q = query.lower()
    if do_it_mode:
        return "do_it"
    if any(kw in q for kw in IMAGE_KEYWORDS):
        return "image"
    if any(kw in q for kw in VIRAL_KEYWORDS):
        return "viral"
    if len(query.split())>8 or any(kw in q for kw in COMPLEX_KEYWORDS):
        return "complex"
    return "simple"

# ─────────────────────────────────────────
# RESEARCH ENGINE
# ─────────────────────────────────────────
def get_research(query):
    if not PERPLEXITY_KEY: return ""
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization":f"Bearer {PERPLEXITY_KEY}","Content-Type":"application/json"},
            json={"model":"sonar","messages":[{"role":"user",
                  "content":f"India context research: {query}. Latest data, costs, trends."}]},
            timeout=25
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except: return ""

# ─────────────────────────────────────────
# AI ENGINES
# ─────────────────────────────────────────

def run_gemini(prompt, max_tokens=800):
    """Pure REST API — no SDK needed"""
    if not GEMINI_KEY:
        return None
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}
        }
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def run_claude(prompt, max_tokens=2500):
    if not CLAUDE_KEY: return None,"no_key"
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_KEY)
        msg = client.messages.create(
            model="claude-opus-4-5", max_tokens=max_tokens,
            messages=[{"role":"user","content":prompt}]
        )
        return msg.content[0].text, "claude"
    except anthropic.AuthenticationError: return None,"auth_error"
    except Exception as e: return None,str(e)

# ─────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────
SIMPLE_PROMPT = """You are Karma AI — smart, concise assistant.
Language: {lang}
User asked: {query}
Give a clear, helpful, structured answer. Be concise."""

COMPLEX_PROMPT = """You are Karma AI — execution-focused AI assistant for India.
Language: {lang}
{prev}Goal Type: {goal}
Request: {query}{research}

Produce a COMPLETE EXECUTION PACKAGE:

## 🎯 Situation Analysis
(3 lines)

## 💡 Top 3 Options
**Option 1 — [Name]:** pros / cons / cost
**Option 2 — [Name]:** pros / cons / cost
**Option 3 — [Name]:** pros / cons / cost

## ✅ Best Choice & Why

## ⚡ EXECUTION KIT
### 📝 5 Ready-to-Use Names/Titles
### 🎬 2 Ready-to-Use Scripts/Content Pieces
### 📱 3 Captions + Hashtags
### 🎨 3 Visual/Design Ideas

## 📅 7-Day Action Plan
Day 1-2 / Day 3-4 / Day 5-6 / Day 7

## 💰 Budget Table (₹)
| Item | Min | Comfortable | Ideal |

## ⚠️ Top 3 Risks + Fixes

## 🚀 One-Line Summary"""

# ── NEW PROMPT: Do It For Me ──────────────
DO_IT_PROMPT = """You are Karma AI in EXECUTION MODE. Do not give plans — give COMPLETE READY OUTPUT.
Language: {lang}
{prev}Goal: {query}
Goal Type: {goal}{research}

Generate everything ready to copy-paste and use RIGHT NOW:

## 🚀 READY-TO-POST CONTENT (3 pieces)
[Full post/script for each — not outline, actual content]

## 📱 CAPTIONS + HASHTAGS (5 sets)
Caption 1: ...
Hashtags: #...

Caption 2: ...
Hashtags: #...

[Continue for all 5]

## 🎨 IMAGE PROMPTS (3 prompts ready for Midjourney/DALL-E)
Prompt 1: ...
Prompt 2: ...
Prompt 3: ...

## 🛠️ TOOLS TO USE RIGHT NOW
| Tool | Purpose | Free/Paid | Link |

## 📋 POSTING STEPS (exact sequence)
Step 1: ...
Step 2: ...
[Continue until done]

## 📊 EXPECTED RESULTS (realistic)
- Week 1: ...
- Week 2-4: ...
- Month 2-3: ..."""

# ── NEW PROMPT: Viral / System Mode ──────
VIRAL_PROMPT = """You are Karma AI in SYSTEM BUILD MODE. Build a complete 7-day system.
Language: {lang}
{prev}Goal: {query}
Goal Type: {goal}{research}

## 🔥 SYSTEM OVERVIEW
[What this system does, expected outcome]

## 📅 7-DAY FULL BREAKDOWN

### Day 1 — Foundation
- Tasks: ...
- Tools: ...
- Output: ...
- Time needed: ...

### Day 2 — Build
- Tasks: ...
- Tools: ...
- Output: ...

### Day 3 — Content
- Tasks: ...
- Tools: ...
- Output: ...

### Day 4 — Launch
- Tasks: ...
- Tools: ...
- Output: ...

### Day 5 — Promote
- Tasks: ...
- Tools: ...
- Output: ...

### Day 6 — Optimize
- Tasks: ...
- Tools: ...
- Output: ...

### Day 7 — Scale
- Tasks: ...
- Tools: ...
- Output: ...

## 🛠️ COMPLETE TOOL STACK
| Tool | Purpose | Cost |

## 📈 GROWTH STRATEGY (30-day)
Week 1: ...
Week 2: ...
Week 3-4: ...

## 💰 MONETIZATION ROADMAP
Phase 1 (Day 1-7): ...
Phase 2 (Day 8-30): ...
Phase 3 (Month 2+): ...

## ⚡ QUICK WINS (do these first)
1. ...
2. ...
3. ...

## 💰 FULL BUDGET BREAKDOWN
| Item | Cost | Priority |"""

# ── NEW PROMPT: Image Mode ────────────────
IMAGE_PROMPT = """You are Karma AI — visual content specialist.
Language: {lang}
User needs visual/design help for: {query}
Goal Type: {goal}

Generate:

## 🎨 IMAGE PROMPTS (5 ready-to-use prompts)

### For Midjourney / DALL-E / Stable Diffusion:
**Prompt 1 (Main):**
[Detailed, specific prompt with style, colors, mood, composition]

**Prompt 2 (Alternative Style):**
[Different aesthetic approach]

**Prompt 3 (Minimalist):**
[Clean, simple version]

**Prompt 4 (Bold/Viral):**
[High-impact, attention-grabbing]

**Prompt 5 (Professional):**
[Corporate/clean style]

## 💡 VISUAL CONCEPT IDEAS (5 concepts)
1. **Concept Name:** [Description, colors, fonts, mood]
2. **Concept Name:** [Description]
3. **Concept Name:** [Description]
4. **Concept Name:** [Description]
5. **Concept Name:** [Description]

## 🎨 COLOR PALETTE SUGGESTIONS
Primary: #___  Secondary: #___  Accent: #___
[Explain why these colors work for this brand/purpose]

## 📐 SIZE & FORMAT GUIDE
| Platform | Size | Format |
|----------|------|--------|
| Instagram Post | 1080x1080 | JPG/PNG |
| YouTube Thumbnail | 1280x720 | JPG |
| Logo | SVG/PNG | Transparent BG |

## 🛠️ FREE TOOLS TO CREATE THIS
1. Canva — [template suggestion]
2. Adobe Express — [template suggestion]
3. Figma — [approach]

## 📝 TEXT/COPY FOR THE DESIGN
[Headline, subtext, CTA ready to use]"""

# ─────────────────────────────────────────
# MAIN GENERATION FUNCTION
# ─────────────────────────────────────────
def generate_plan(query, goal_type, query_type, research, prev_ctx, language):
    """
    Routes to correct prompt + model based on query_type.
    simple  → Gemini (fallback Claude)
    complex → Claude (fallback Gemini)
    image   → Claude (fallback Gemini)  [NEW]
    do_it   → Claude (fallback Gemini)  [NEW]
    viral   → Claude (fallback Gemini)  [NEW]
    """
    lang_note      = f"Respond in {language}." if language != "English" else "Respond in clear English."
    prev_block     = f"Previous context:\n{prev_ctx}\n" if prev_ctx else ""
    research_block = f"\nResearch Data:\n{research}" if research else ""

    # ── Select prompt template ────────────
    if query_type == "simple":
        prompt = SIMPLE_PROMPT.format(lang=lang_note, query=query)
        result = run_gemini(prompt, max_tokens=600)
        if result: return result, "gemini"
        result, err = run_claude(prompt, max_tokens=600)
        return (result, "claude-fallback") if result else (None, err)

    elif query_type == "image":                                    # NEW
        prompt = IMAGE_PROMPT.format(lang=lang_note, query=query, goal=goal_type)
        result, err = run_claude(prompt, max_tokens=2000)
        if result: return result, "claude"
        result = run_gemini(prompt, max_tokens=1500)
        return (result, "gemini-fallback") if result else (None, err)

    elif query_type == "do_it":                                    # NEW
        prompt = DO_IT_PROMPT.format(
            lang=lang_note, prev=prev_block,
            query=query, goal=goal_type, research=research_block
        )
        result, err = run_claude(prompt, max_tokens=3000)
        if result: return result, "claude"
        result = run_gemini(prompt, max_tokens=2000)
        return (result, "gemini-fallback") if result else (None, err)

    elif query_type == "viral":                                    # NEW
        prompt = VIRAL_PROMPT.format(
            lang=lang_note, prev=prev_block,
            query=query, goal=goal_type, research=research_block
        )
        result, err = run_claude(prompt, max_tokens=3500)
        if result: return result, "claude"
        result = run_gemini(prompt, max_tokens=2500)
        return (result, "gemini-fallback") if result else (None, err)

    else:  # complex
        prompt = COMPLEX_PROMPT.format(
            lang=lang_note, prev=prev_block,
            goal=goal_type, query=query, research=research_block
        )
        result, err = run_claude(prompt, max_tokens=2500)
        if result: return result, "claude"
        result = run_gemini(prompt, max_tokens=1500)
        return (result, "gemini-fallback") if result else (None, err)

# ─────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────
for k, v in {
    "chat_history":  [],
    "current_plan":  None,
    "current_query": None,
    "workflow_stage":"idle",
    "user_language": "English",
    "last_mode":     "normal",          # NEW — track which mode was used
    "image_result":  None,              # NEW — store image mode result separately
}.items():
    st.session_state.setdefault(k, v)

user_id   = get_persistent_user_id()
user_prof = db_get_user(user_id)
can_q, remaining = check_limit(user_prof)

# ─────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚀 Karma AI")
    st.caption("Work Engine — not just answers")
    st.divider()

    today_used = user_prof.get("daily",{}).get("count",0)
    c1, c2 = st.columns(2)
    c1.metric("Today", f"{today_used}/{FREE_DAILY_LIMIT}")
    c2.metric("Total", user_prof.get("total_queries",0))
    if not user_prof.get("is_premium"):
        st.progress(min(today_used/FREE_DAILY_LIMIT,1.0), text=f"{remaining} queries left today")
        st.caption("🔄 Resets every day at midnight")

    st.divider()
    st.markdown("### 🌐 Language")
    lang = st.selectbox(
        "Language",["English","Hinglish","Hindi","Tamil","Telugu","Marathi","Bengali"],
        label_visibility="collapsed"
    )
    st.session_state.user_language = lang

    st.divider()
    st.markdown("### 🧠 Memory")
    sessions = user_prof.get("sessions",[])
    if sessions:
        st.caption(f"{len(sessions)} sessions saved")
        for s in reversed(sessions[-5:]):
            with st.expander(f"#{s['id']} — {s['timestamp'][:11]}"):
                st.markdown(f"**Goal:** {s['goal_type']}")
                st.markdown(f"**Query:** {s['query'][:60]}...")
                badge = "⚡ Gemini" if "gemini" in s.get("model_used","") else "🧠 Claude"
                st.caption(badge)
                if st.button("📂 Load", key=f"load_{s['id']}"):
                    st.session_state.current_plan  = s["plan"]
                    st.session_state.current_query = s["query"]
                    st.session_state.chat_history  = []
                    st.rerun()
        if st.button("🗑️ Clear History", use_container_width=True):
            data = db_read()
            if user_id in data["users"]:
                data["users"][user_id]["sessions"] = []
                db_write(data)
            st.session_state.update({"current_plan":None,"current_query":None,"chat_history":[]})
            st.rerun()
    else:
        st.caption("No history yet")

# ─────────────────────────────────────────
# MAIN LAYOUT
# ─────────────────────────────────────────
col1, col2 = st.columns([1.2, 1], gap="large")

# ══════════ LEFT — INPUT ══════════════════
with col1:
    st.markdown('<p class="main-header">Karma AI ⚡</p>', unsafe_allow_html=True)
    st.caption("Tell me what you want — I'll do the work")

    if not can_q and not user_prof.get("is_premium"):
        st.error("🔒 **Daily limit reached!** Come back tomorrow — resets at midnight.")
        st.stop()

    if remaining <= 2 and not user_prof.get("is_premium"):
        st.warning(f"⚠️ Only **{remaining} queries** left today.")

    if st.session_state.current_plan:
        st.info(f"🧠 Context: *'{st.session_state.current_query[:50]}...'*")

    st.markdown("### 💬 What do you want to do?")
    query = st.text_area(
        "Goal", height=120, label_visibility="collapsed",
        placeholder="E.g. Create a YouTube cooking channel thumbnail / Build a business in 7 days..."
    )
    goal_type = st.selectbox("Category:", [
        "🚀 Business Launch","🎬 Content / YouTube / Social Media",
        "💰 Investment / Savings","💼 Career / Freelancing",
        "📚 Study / Skills / Students","📱 App / Tech Project",
        "🏪 Small Business / Shop","🔧 Something Else"
    ])

    # ── NEW: Mode detection preview ───────
    if query.strip():
        detected = route_query(query)
        mode_labels = {
            "image":   "🎨 Image & Visual Mode",
            "viral":   "🔥 System Build Mode (7-Day)",
            "do_it":   "⚡ Do It For Me Mode",
            "complex": "🧠 Deep Execution Mode",
            "simple":  "💬 Quick Answer Mode"
        }
        st.caption(f"**Detected mode:** {mode_labels.get(detected, 'Normal')}")

    # Workflow status
    st.markdown("#### ⚡ Workflow")
    w1,w2,w3,w4 = st.columns(4)
    stage = st.session_state.workflow_stage
    stages_order = ["researching","planning","executing","done"]
    labels_wf    = ["🔍 Research","🧠 Plan","⚡ Build","💾 Save"]
    for i,(col,lbl) in enumerate(zip([w1,w2,w3,w4],labels_wf)):
        idx = stages_order.index(stage) if stage in stages_order else -1
        with col:
            if stage == stages_order[i]: st.info(f"{lbl}\nRunning...")
            elif idx > i: st.success(f"{lbl}\n✅")
            else: st.markdown(f"{lbl}\nReady")

    st.markdown("")

    # ── Action buttons row ────────────────
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        run_btn    = st.button("🔥 Start Working", type="primary", use_container_width=True)

    with btn_col2:
        do_it_btn  = st.button("⚡ Do It For Me", use_container_width=True)   # NEW

    # ── RUN LOGIC ─────────────────────────
    triggered    = run_btn or do_it_btn
    do_it_mode   = do_it_btn

    if triggered:
        if not query.strip():
            st.error("Please tell me what you want!"); st.stop()
        if not CLAUDE_KEY and not GEMINI_KEY:
            st.error("System not configured — contact admin."); st.stop()
        if not can_q:
            st.error("🔒 Daily limit reached!"); st.stop()

        query_type = route_query(query, do_it_mode=do_it_mode)
        st.session_state.last_mode = query_type

        cache_key = make_cache_key(query, goal_type, st.session_state.user_language, query_type)
        cached    = cache_get(cache_key)

        if cached:
            st.session_state.current_plan  = cached
            st.session_state.current_query = query
            st.session_state.chat_history  = []
            st.session_state.workflow_stage = "done"
            st.session_state.image_result  = None
            db_save_session(user_id, query, goal_type, cached, "cache")
            st.rerun()

        prev_ctx = ""
        if st.session_state.current_plan:
            prev_ctx = (f"Previous query: {st.session_state.current_query}\n"
                        f"Previous plan: {st.session_state.current_plan[:400]}...")

        # Research only for complex/viral/do_it
        st.session_state.workflow_stage = "researching"
        research = ""
        with st.spinner("🔍 Researching..."):
            if query_type in ("complex","viral","do_it"):
                research = get_research(query)

        st.session_state.workflow_stage = "planning"
        with st.spinner("🧠 Building your kit..."):
            st.session_state.workflow_stage = "executing"
            plan, model_used = generate_plan(
                query, goal_type, query_type,
                research, prev_ctx, st.session_state.user_language
            )

        if plan is None:
            st.error("❌ AI error — try again."); st.session_state.workflow_stage="idle"; st.stop()

        with st.spinner("💾 Saving..."):
            cache_set(cache_key, plan)
            db_save_session(user_id, query, goal_type, plan, model_used)
            st.session_state.update({
                "current_plan":  plan,
                "current_query": query,
                "chat_history":  [],
                "workflow_stage":"done",
                "image_result":  None
            })

        user_prof = db_get_user(user_id)
        can_q, remaining = check_limit(user_prof)
        st.rerun()

# ══════════ RIGHT — OUTPUT ════════════════
with col2:
    if st.session_state.current_plan:
        last_mode = st.session_state.get("last_mode","normal")

        # ── Mode badge ────────────────────
        badge_map = {
            "image":   "🎨 Image & Visual Mode",
            "viral":   "🔥 System Build Mode",
            "do_it":   "⚡ Do It For Me Mode",
            "complex": "🧠 Execution Mode",
            "simple":  "💬 Quick Answer"
        }
        if last_mode in badge_map:
            st.markdown(f"**Mode:** `{badge_map[last_mode]}`")

        # ── Tabs ──────────────────────────
        # NEW: Image mode gets its own tab
        if last_mode == "image":
            tab1, tab2, tab3 = st.tabs(["🎨 Visual Kit", "⚡ Execution", "💬 Follow-up"])
        elif last_mode in ("viral","do_it"):
            tab1, tab2, tab3 = st.tabs(["⚡ Full Kit", "📋 Summary", "💬 Follow-up"])
        else:
            tab1, tab2, tab3 = st.tabs(["⚡ Execution Kit", "📋 Details", "💬 Follow-up"])

        with tab1:
            if st.session_state.current_query:
                st.caption(f"**Query:** {st.session_state.current_query[:80]}...")

            # ── NEW: Viral mode banner ─────
            if last_mode == "viral":
                st.markdown("🔥 **7-Day System Build** — Complete roadmap below")

            # ── NEW: Do It mode banner ─────
            if last_mode == "do_it":
                st.markdown("⚡ **Do It For Me** — Everything ready to copy-paste")

            st.markdown(st.session_state.current_plan)
            st.divider()

            b1, b2, b3 = st.columns(3)
            with b1:
                st.download_button(
                    "📥 Download", use_container_width=True,
                    data=(f"KARMA AI — {badge_map.get(last_mode,'Kit').upper()}\n{'='*50}\n"
                          f"Query: {st.session_state.current_query}\n"
                          f"Date: {datetime.now().strftime('%d %b %Y')}\n"
                          f"Mode: {badge_map.get(last_mode,'Normal')}\n"
                          f"{'='*50}\n\n{st.session_state.current_plan}"),
                    file_name=f"karma-ai-{last_mode}-kit.txt", mime="text/plain"
                )
            with b2:
                if st.button("📋 Copy", use_container_width=True):
                    st.code(st.session_state.current_plan[:400]+"...", language=None)
            with b3:
                if st.button("🔁 Regenerate", use_container_width=True):
                    st.session_state.current_plan=None; st.rerun()

        with tab2:
            # ── NEW: Quick summary / different view ──
            st.caption("Quick overview of your kit")
            if last_mode == "viral":
                st.markdown("""
**Your 7-Day System includes:**
- ✅ Daily task breakdown
- ✅ Tools & platforms
- ✅ Growth strategy
- ✅ Monetization roadmap
- ✅ Quick wins list
- ✅ Budget breakdown
                """)
            elif last_mode == "do_it":
                st.markdown("""
**Your Do-It Kit includes:**
- ✅ Ready-to-post content
- ✅ Captions + hashtags
- ✅ Image prompts
- ✅ Tools list
- ✅ Posting steps
- ✅ Expected results
                """)
            elif last_mode == "image":
                st.markdown("""
**Your Visual Kit includes:**
- ✅ 5 AI image prompts
- ✅ Visual concept ideas
- ✅ Color palette
- ✅ Size/format guide
- ✅ Free tools list
- ✅ Copy/text for design
                """)
            else:
                st.markdown("""
**Your Execution Kit includes:**
- ✅ Situation analysis
- ✅ Top 3 options
- ✅ Best choice recommendation
- ✅ Scripts & captions
- ✅ 7-day action plan
- ✅ Budget breakdown
                """)

            # ── NEW: Do It For Me button in output ──
            if last_mode not in ("do_it","viral") and st.session_state.current_query:
                st.divider()
                st.caption("Want everything done for you?")
                if st.button("⚡ Upgrade to Do It For Me", use_container_width=True):
                    if not can_q:
                        st.error("🔒 Daily limit reached!")
                    else:
                        query_type = "do_it"
                        st.session_state.last_mode = "do_it"
                        with st.spinner("⚡ Building complete ready kit..."):
                            plan, model_used = generate_plan(
                                st.session_state.current_query, goal_type,
                                "do_it", "", "", st.session_state.user_language
                            )
                        if plan:
                            cache_key = make_cache_key(
                                st.session_state.current_query, goal_type,
                                st.session_state.user_language, "do_it"
                            )
                            cache_set(cache_key, plan)
                            db_save_session(user_id, st.session_state.current_query, goal_type, plan, model_used)
                            st.session_state.current_plan = plan
                            st.rerun()

        # ── FOLLOW-UP CHAT ─────────────────
        with tab3:
            st.caption("Ask anything about your kit — full context remembered 🧠")
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            fu = st.chat_input("Ask follow-up...")
            if fu:
                with st.chat_message("user"):
                    st.markdown(fu)
                st.session_state.chat_history.append({"role":"user","content":fu})

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        lang_note  = f"Respond in {st.session_state.user_language}."
                        ctx_prompt = (f"You are Karma AI. The kit/plan generated:\n\n"
                                      f"{st.session_state.current_plan}\n\n"
                                      f"Answer follow-ups based on this. {lang_note}")
                        messages_h = [
                            {"role":"user","content":ctx_prompt},
                            {"role":"assistant","content":"Got it! Ask me anything."}
                        ]
                        for m in st.session_state.chat_history[:-1]:
                            messages_h.append({"role":m["role"],"content":m["content"]})
                        messages_h.append({"role":"user","content":fu})

                        reply = None
                        if GEMINI_KEY:
                            full_p = "\n".join([m["content"] for m in messages_h])
                            reply  = run_gemini(full_p, max_tokens=600)
                        if not reply and CLAUDE_KEY:
                            client = anthropic.Anthropic(api_key=CLAUDE_KEY)
                            resp   = client.messages.create(
                                model="claude-opus-4-5", max_tokens=600, messages=messages_h
                            )
                            reply = resp.content[0].text

                        if reply:
                            st.markdown(reply)
                            st.session_state.chat_history.append({"role":"assistant","content":reply})
                        else:
                            st.error("Could not generate reply.")

    else:
        # ── Empty state ───────────────────
        st.markdown("### 👈 Start from there")
        st.markdown("""
**What Karma AI does:**

⚡ **Execution Kit** — Scripts, captions, names, budgets ready to use

🎨 **Image Mode** — AI image prompts + visual concepts *(say "logo", "thumbnail", "poster")*

🔥 **System Mode** — Full 7-day system *(say "build in 7 days", "full system")*

⚡ **Do It For Me** — Complete ready-to-post content *(click the button)*

🔍 **Research** — Latest India data included

🧠 **Memory** — All sessions remembered

🌐 **Any Language** — English, Hindi, Hinglish & more

🤖 **Smart Routing** — Simple → Gemini | Complex → Claude
        """)
        data = db_read()
        if data.get("popular_goals"):
            st.divider()
            st.caption("🔥 Popular today:")
            for g,c in sorted(data["popular_goals"].items(), key=lambda x:-x[1])[:3]:
                st.caption(f"• {g}: {c} queries")
