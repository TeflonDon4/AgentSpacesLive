"""
AgentSpaces Live — BDA Edition
--------------------------------
Four AI agents debating fintech, AI and AI Agents for the
Bermuda Business Development Authority.

Agents:
  Lex Arbitrum    ⚖️  — Bermuda regulatory lens + moderator
  Vera Capita     💼  — Commercial & business case
  Neil Underwriter  🔍  — Insurance executive, AI practitioner
  Marco Ventures  💰  — Investor voice

Fixes in this version:
  - Substantive content filter before firing agents
  - Much shorter responses (1 sentence default, 2-3 max)
  - Agents respond TO each other, not just the transcript
  - Lex understands moderating function and can see the thread
  - Marco varies data points, no repetition
  - agent_points memory tracks what's been said to avoid parroting
"""

import os
import time
import threading
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)
client = Anthropic()

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_GROUP_ID = os.environ["TELEGRAM_GROUP_ID"]
LEX_TOKEN         = os.environ["LEX_TOKEN"]
VERA_TOKEN        = os.environ["VERA_TOKEN"]
DANTE_TOKEN       = os.environ["DANTE_TOKEN"]
MARCO_TOKEN       = os.environ["MARCO_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# ── Agent Personas ─────────────────────────────────────────────────────────────
AGENTS = {
    "lex": {
        "token": LEX_TOKEN,
        "name": "Lex Arbitrum",
        "emoji": "⚖️",
        "system": """You are Lex Arbitrum, a Bermuda-qualified regulatory specialist on a live panel at the Bermuda Business Development Authority discussing fintech, AI and AI Agents.

Your lens: The full BMA regulatory estate — insurance, investment funds, banking, digital assets, AML/ATF, economic substance, sandbox frameworks, and how existing frameworks apply to AI agents.

Your character: You think in structures and principles. You ask what the logical architecture is — does it create parallel regimes unnecessarily, where are the perimeter questions, does it hard-wire the right safeguards. You frame concerns as drafting requirements. You are collegial, genuinely engaged, and diplomatically aware. You occasionally note when something is "conceptually cleaner" or where a supervisory question still needs resolving.

MODERATING ROLE: You are also the panel moderator. You can see the full Telegram thread — all agent messages appear there and you have read them. When asked to summarise, do so based on what the agents have said in the thread. When directing questions, name the agent. When the discussion needs steering, do it naturally.

RESPONSE RULES — CRITICAL:
- DEFAULT: 1 sentence only. Sharp and specific.
- OCCASIONALLY (when a point genuinely needs more): 2 sentences maximum.
- Directly respond to what another agent just said when you can.
- Never repeat a point already made in this session.
- Never use filler openers like "Good morning", "Thank you", "I'd be happy to".
- If asked to summarise, summarise what's actually in the thread — never say you can't see it."""
    },
    "vera": {
        "token": VERA_TOKEN,
        "name": "Vera Capita",
        "emoji": "💼",
        "system": """You are Vera Capita, a commercial deal structuring specialist on a live panel at the Bermuda Business Development Authority discussing fintech, AI and AI Agents.

Your lens: Business models, revenue, market opportunity, deal structure, who pays, who benefits.

RESPONSE RULES — CRITICAL:
- DEFAULT: 1 sentence only. Punchy and commercial.
- OCCASIONALLY (when a point genuinely needs more): 2 sentences maximum.
- Directly respond to what Lex, Neil or Marco just said — agree, push back, or build on it.
- Vary your arguments — do not repeat the same point twice in a session.
- Never use filler openers.
- Advance the conversation every time you speak."""
    },
    "dante": {
        "token": DANTE_TOKEN,
        "name": "Neil Underwriter",
        "emoji": "🔍",
        "system": """You are Neil Underwriter, a senior Bermuda insurance and reinsurance executive on a live panel at the Bermuda Business Development Authority discussing fintech, AI and AI Agents.

Your background: You've deployed operational AI for years — fraud detection, underwriting models, catastrophe modelling, claims automation. You're curious about autonomous AI agents but approach it as a practitioner. You price risk for a living.

Your role: Ask questions that move the discussion forward. Stress-test propositions with real insurance scenarios. Help the panel work through implications.

RESPONSE RULES — CRITICAL:
- DEFAULT: 1 sentence only — a question or a sharp practical observation.
- OCCASIONALLY (when a scenario needs unpacking): 2 sentences maximum.
- Respond directly to what other panellists say — name them if helpful.
- Draw on specific insurance scenarios: treaty negotiation, cat modelling, claims decisions, E&O exposure.
- Never use filler openers.
- Never repeat a point already made."""
    },
    "marco": {
        "token": MARCO_TOKEN,
        "name": "Marco Ventures",
        "emoji": "💰",
        "system": """You are Marco Ventures, an investor and VC specialist on a live panel at the Bermuda Business Development Authority discussing fintech, AI and AI Agents.

Your lens: Where is smart money flowing? What are investors funding and avoiding? What does Bermuda need to attract serious capital? You have a global view — Singapore, UAE, Cayman, London, New York.

RESPONSE RULES — CRITICAL:
- DEFAULT: 1 sentence only. Confident and specific.
- OCCASIONALLY (when a capital flow point needs context): 2 sentences maximum.
- NEVER repeat the same statistic or data point in the same session — vary your evidence every time.
- Respond directly to what other panellists say — connect their point to investor reality.
- Never use filler openers.
- Vary your angles: deal terms, LP appetite, fund structures, exit multiples, specific sectors, regulatory risk pricing, specific jurisdictions with specific details."""
    }
}

# ── Persistent conversation memory ────────────────────────────────────────────
conversation_memory = {
    "summary": "",
    "key_points": [],
    "agent_points": [],   # Tracks what agents have said to prevent repetition
    "segment_count": 0
}

transcript_buffer = []
MAX_BUFFER = 30

def update_memory(new_segment: str, speaker: str):
    conversation_memory["segment_count"] += 1
    conversation_memory["key_points"].append(f"{speaker}: {new_segment}")
    if len(conversation_memory["key_points"]) > 15:
        conversation_memory["key_points"] = conversation_memory["key_points"][-15:]
    if conversation_memory["segment_count"] % 5 == 0:
        threading.Thread(target=regenerate_summary, daemon=True).start()

def record_agent_point(agent_name: str, response: str):
    conversation_memory["agent_points"].append(f"{agent_name}: {response}")
    if len(conversation_memory["agent_points"]) > 20:
        conversation_memory["agent_points"] = conversation_memory["agent_points"][-20:]

def regenerate_summary():
    if not conversation_memory["key_points"]:
        return
    try:
        points = "\n".join(conversation_memory["key_points"])
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": f"""Summarise the key themes from this discussion in 2-3 sentences. Be specific — capture actual arguments made.

Discussion:
{points}

Summary:"""
            }]
        )
        conversation_memory["summary"] = response.content[0].text
        print(f"  [Memory: {conversation_memory['summary'][:80]}...]")
    except Exception as e:
        print(f"  Memory error: {e}")

def get_memory_context() -> str:
    context = ""
    if conversation_memory["summary"]:
        context += f"\n--- DISCUSSION SUMMARY ---\n{conversation_memory['summary']}\n"
    if conversation_memory["agent_points"]:
        recent = conversation_memory["agent_points"][-8:]
        context += "\nRecent agent contributions (DO NOT repeat these points):\n"
        context += "\n".join(recent) + "\n--- END CONTEXT ---\n"
    return context

# ── Substantive content filter ─────────────────────────────────────────────────
def is_substantive(text: str) -> bool:
    """Filter out procedural/admin speech before firing agents."""
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": f"""Is this statement substantive enough for a panel of experts to comment on?
It should contain an actual idea, claim, question or argument about fintech, AI, regulation, or business.
It should NOT be: very short procedural phrases ("let's start", "thank you", "moving on"), greetings, or requests for someone to speak. Questions about AI, regulation, fintech, or Bermuda policy ARE substantive even if they are phrased as questions.

Statement: "{text}"

Reply with only YES or NO."""
            }]
        )
        answer = response.content[0].text.strip().upper()
        print(f"  [Filter: {answer} — {text[:60]}]")
        return answer.startswith("YES")
    except Exception:
        return True  # Default to firing if filter fails

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(token: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": TELEGRAM_GROUP_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Telegram error: {e}")

# ── Agent responses ────────────────────────────────────────────────────────────
def get_agent_response(agent_key: str, new_segment: str, prior_responses: dict) -> str:
    agent = AGENTS[agent_key]

    # Recent transcript
    context = "\n".join([f"{s['speaker']}: {s['text']}" for s in transcript_buffer[-4:]])

    # What other agents said THIS round
    other_responses = "\n".join([
        f"{AGENTS[k]['name']}: {v}"
        for k, v in prior_responses.items()
        if k != agent_key and v
    ])
    other_context = (
        f"\nOther panellists just said:\n{other_responses}\n\n"
        "Prioritise responding directly to one of these points rather than just the transcript."
    ) if other_responses else ""

    memory_context = get_memory_context()

    user_message = f"""{memory_context}
Live transcript:
{context}

Just said: {new_segment}
{other_context}
IMPORTANT: Default to 1 sentence. Only use 2 sentences if genuinely necessary. Be direct. Do not repeat points already made."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=80,
            system=agent["system"],
            messages=[{"role": "user", "content": user_message}]
        )
        text = response.content[0].text
        record_agent_point(agent["name"], text)
        return text
    except Exception as e:
        print(f"Claude API error for {agent_key}: {e}")
        return None

def agents_respond(segment_text: str, speaker: str):
    """Four agents respond with staggered timing."""
    update_memory(segment_text, speaker)

    delays = {"lex": 15, "vera": 35, "dante": 60, "marco": 90}
    prior_responses = {}
    lock = threading.Lock()

    def respond(agent_key, delay):
        time.sleep(delay)
        with lock:
            snapshot = dict(prior_responses)
        response = get_agent_response(agent_key, segment_text, snapshot)
        if response:
            with lock:
                prior_responses[agent_key] = response
            agent = AGENTS[agent_key]
            message = f"{agent['emoji']} *{agent['name']}*\n{response}"
            send_telegram(agent["token"], message)

    for agent_key, delay in delays.items():
        t = threading.Thread(target=respond, args=(agent_key, delay))
        t.daemon = True
        t.start()

# ── Webhook ───────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"status": "no data"}), 400

    event_type = data.get("eventType", "")

    if event_type in ["Transcription", "TranscriptSegment", "transcript_ready"]:
        transcript = data.get("transcript", {})
        sentences = transcript.get("sentences", [])

        if sentences:
            for sentence in sentences:
                speaker = sentence.get("speaker_name", "Speaker")
                text = sentence.get("text", "")
                if text:
                    transcript_buffer.append({"speaker": speaker, "text": text})
                    if len(transcript_buffer) > MAX_BUFFER:
                        transcript_buffer.pop(0)

            recent_text = " ".join([s["text"] for s in transcript_buffer[-3:]])
            last_speaker = transcript_buffer[-1]["speaker"] if transcript_buffer else "Speaker"

            snippet = f"🎙️ *{last_speaker}:* {transcript_buffer[-1]['text']}"
            send_telegram(LEX_TOKEN, snippet)

            if is_substantive(recent_text):
                print(f"  [Substantive — firing agents]")
                agents_respond(recent_text, last_speaker)
            else:
                print(f"  [Procedural — skipping]")

    return jsonify({"status": "ok"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "AgentSpaces Live is running",
        "memory_segments": conversation_memory["segment_count"],
        "memory_summary": conversation_memory["summary"][:100] if conversation_memory["summary"] else "none"
    }), 200

@app.route("/memory", methods=["GET"])
def memory():
    return jsonify(conversation_memory), 200

@app.route("/memory/reset", methods=["POST"])
def reset_memory():
    conversation_memory["summary"] = ""
    conversation_memory["key_points"] = []
    conversation_memory["agent_points"] = []
    conversation_memory["segment_count"] = 0
    transcript_buffer.clear()
    return jsonify({"status": "memory reset"}), 200

@app.route("/test", methods=["POST"])
def test_agents():
    data = request.json or {}
    text = data.get("text", "Bermuda has a unique opportunity to become the global hub for AI agent incorporation — but only if the regulatory framework keeps pace with the technology.")
    speaker = data.get("speaker", "BC")

    transcript_buffer.append({"speaker": speaker, "text": text})
    update_memory(text, speaker)
    send_telegram(LEX_TOKEN, f"🎙️ *{speaker}:* {text}")
    agents_respond(text, speaker)

    return jsonify({"status": "test fired", "text": text}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
