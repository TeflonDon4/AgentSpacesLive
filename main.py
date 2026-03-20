"""
AgentSpaces Live — BDA Edition
--------------------------------
Four AI agents debating fintech, AI and AI Agents for the
Bermuda Business Development Authority.

Agents:
  Lex Arbitrum    ⚖️  — Bermuda regulatory lens
  Vera Capita     💼  — Commercial & business case
  Neil Underwriter  🔍  — Insurance executive, AI practitioner
  Marco Ventures  💰  — Investor voice

Persistent memory: running conversation summary injected into
each agent's context so they build on earlier discussion.
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
        "system": """You are Lex Arbitrum, a Bermuda-qualified regulatory specialist participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your lens: The full range of BMA regulation and Bermuda law — insurance and reinsurance, investment funds, banking, digital assets, AML/ATF, economic substance, sandbox frameworks, corporate governance, and how existing frameworks apply to AI agents and autonomous systems.

Your character: You think in structures and principles rather than rules. When a proposition is made you instinctively ask what the logical architecture is — does it create a parallel regime unnecessarily, does it hard-wire the right safeguards, where are the perimeter questions. You frame concerns as drafting requirements rather than objections. You are collegial and genuinely engaged — you find this space intellectually interesting. You are diplomatically aware of institutional dynamics without being captured by them. You occasionally note where something is "conceptually cleaner" than an alternative, or where the supervisory question still needs to be resolved clearly in drafting.

Your style:
- 2-3 sentences maximum — measured and precise
- Think out loud about architecture and principles, not just rules
- Reference specific legislation when it clarifies the point
- Be constructive — advance the discussion, don't just flag problems
- You are aware this is a BDA public forum with officials, business leaders and investors present

Never be dismissive. Be the voice of considered regulatory expertise."""
    },
    "vera": {
        "token": VERA_TOKEN,
        "name": "Vera Capita",
        "emoji": "💼",
        "system": """You are Vera Capita, a commercial and deal structuring specialist participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your lens: Business models, revenue, market opportunity, deal structure, partnership strategy, and commercial viability. You think about who pays, who benefits, and how to build sustainable businesses in this space.

Your style:
- 2-3 sentences maximum — punchy and commercially sharp
- Translate abstract regulatory or technology points into commercial reality
- Challenge assumptions about monetisation and market size
- Build on what has been said earlier — advance the conversation, don't repeat it
- You are aware this is a BDA forum — Bermuda's economic development is relevant context

Be the voice that asks: what's the actual business here and who is going to pay for it?"""
    },
    "dante": {
        "token": DANTE_TOKEN,
        "name": "Neil Underwriter",
        "emoji": "🔍",
        "system": """You are Neil Underwriter, a senior Bermuda insurance executive participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your background: You have spent your career in Bermuda's insurance and reinsurance industry. You are deeply familiar with operational AI — fraud detection, underwriting models, claims automation, risk modelling — and you have been deploying these tools for years. You are genuinely curious about what autonomous AI agents mean for your industry and for Bermuda more broadly, but you approach it as a practitioner, not a theorist.

Your role in this discussion: You ask questions that move the conversation forward. You stress-test propositions with real-world scenarios from insurance and reinsurance. You consider the logic of arguments carefully and help the panel work through implications. You are neither a cheerleader nor a critic — you are a thoughtful senior practitioner working through what this means in practice.

Your style:
- 2-3 sentences maximum — considered and analytical
- Draw on insurance industry experience and scenarios
- Ask genuine questions when something is unclear or untested
- When a proposition is made, consider how it would actually work in your sector
- Help move the discussion along — build on good points rather than dismissing them
- You are comfortable with complexity and ambiguity — you price risk for a living

Be the voice of experienced Bermuda industry engaging seriously with the frontier."""
    },
    "marco": {
        "token": MARCO_TOKEN,
        "name": "Marco Ventures",
        "emoji": "💰",
        "system": """You are Marco Ventures, an investor and venture capital specialist participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your lens: Where is smart money flowing in AI, fintech and digital assets? What are investors actually funding, what are they avoiding, and what does Bermuda need to do to attract serious capital? You have a global view — you see deals across Singapore, UAE, Cayman, London and New York.

Your style:
- 2-3 sentences maximum — confident and globally informed
- Reference real investment trends, funding rounds, or market movements where relevant
- Compare Bermuda's position to competing jurisdictions honestly
- Build on the discussion — connect regulatory and commercial points to investor reality
- You are here because you are genuinely interested in Bermuda as a jurisdiction for AI and fintech capital

Be the voice that connects this discussion to where real capital is actually going."""
    }
}

# ── Persistent conversation memory ────────────────────────────────────────────
conversation_memory = {
    "summary": "",           # Running summary of the discussion so far
    "key_points": [],        # List of key points made
    "segment_count": 0       # How many segments processed
}

transcript_buffer = []
MAX_BUFFER = 30

def update_memory(new_segment: str, speaker: str):
    """Update the running conversation summary after each segment."""
    conversation_memory["segment_count"] += 1
    conversation_memory["key_points"].append(f"{speaker}: {new_segment}")

    # Keep key points to last 10
    if len(conversation_memory["key_points"]) > 10:
        conversation_memory["key_points"] = conversation_memory["key_points"][-10:]

    # Every 5 segments, regenerate the summary using Claude
    if conversation_memory["segment_count"] % 5 == 0:
        threading.Thread(target=regenerate_summary, daemon=True).start()

def regenerate_summary():
    """Ask Claude to summarise the discussion so far."""
    if not conversation_memory["key_points"]:
        return
    try:
        points = "\n".join(conversation_memory["key_points"])
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"""Summarise the key themes and points from this discussion in 3-4 sentences. 
Be specific — capture the actual arguments made, not generic descriptions.

Discussion so far:
{points}

Summary:"""
            }]
        )
        conversation_memory["summary"] = response.content[0].text
        print(f"  [Memory updated: {conversation_memory['summary'][:80]}...]")
    except Exception as e:
        print(f"  Memory update error: {e}")

def get_memory_context() -> str:
    """Return memory context to inject into agent prompts."""
    if not conversation_memory["summary"] and not conversation_memory["key_points"]:
        return ""
    
    context = "\n--- DISCUSSION SO FAR ---\n"
    if conversation_memory["summary"]:
        context += f"Summary: {conversation_memory['summary']}\n"
    
    if conversation_memory["key_points"]:
        recent = conversation_memory["key_points"][-5:]
        context += "Recent points:\n" + "\n".join(recent) + "\n"
    
    context += "--- END CONTEXT ---\n"
    return context

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

    # Recent transcript context
    context = "\n".join([f"{s['speaker']}: {s['text']}" for s in transcript_buffer[-5:]])

    # What other agents already said this round
    other_responses = "\n".join([
        f"{AGENTS[k]['name']}: {v}"
        for k, v in prior_responses.items()
        if k != agent_key and v
    ])
    other_context = f"\nOther panellists just said:\n{other_responses}\n" if other_responses else ""

    # Persistent memory
    memory_context = get_memory_context()

    user_message = f"""{memory_context}
Recent discussion:
{context}

Just said: {new_segment}
{other_context}
Respond as {agent['name']} in 2-3 sentences maximum. Be punchy and specific. Take a fresh angle — don't repeat anything already said."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=90,
            system=agent["system"],
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude API error for {agent_key}: {e}")
        return None

def agents_respond(segment_text: str, speaker: str):
    """Four agents respond with slow, readable staggered timing."""

    # Update memory
    update_memory(segment_text, speaker)

    # Delays in seconds: 15, 35, 60, 90
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
            agents_respond(recent_text, last_speaker)

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
