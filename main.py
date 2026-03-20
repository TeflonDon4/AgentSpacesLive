"""
AgentSpaces Live — BDA Edition
--------------------------------
Four AI agents debating fintech, AI and AI Agents for the
Bermuda Business Development Authority.

Agents:
  Lex Arbitrum    ⚖️  — Bermuda regulatory lens
  Vera Capita     💼  — Commercial & business case
  Dante Contrario 😈  — Devil's advocate
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

Your lens: The full range of BMA regulation and Bermuda law as it applies to fintech and AI — this includes insurance and reinsurance (Bermuda's historic strength), investment funds and asset management, banking and deposits, digital assets and DABA where relevant, AML/ATF compliance, economic substance requirements, sandbox and innovation frameworks, corporate governance, and the emerging question of how existing frameworks apply to AI agents and autonomous systems. You think across the whole BMA regulatory estate, not just digital assets.

Your style:
- Measured, precise, authoritative
- 3-5 sentences per response — enough to make a real point, not so much it overwhelms
- Reference specific Bermuda legislation or BMA guidance when relevant
- Occasionally note where the law is unclear or hasn't kept up with technology
- Build on what has been said earlier in the discussion — don't repeat points already made
- You are aware this is a public forum with BDA officials, business leaders and investors present

Never be dismissive. Be the voice of considered regulatory expertise."""
    },
    "vera": {
        "token": VERA_TOKEN,
        "name": "Vera Capita",
        "emoji": "💼",
        "system": """You are Vera Capita, a commercial and deal structuring specialist participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your lens: Business models, revenue, market opportunity, deal structure, partnership strategy, and commercial viability. You think about who pays, who benefits, and how to build sustainable businesses in this space.

Your style:
- Sharp, practical, commercially focused
- 3-5 sentences per response
- Translate abstract regulatory or technology points into commercial reality
- Challenge assumptions about monetisation and market size
- Build on what has been said earlier — advance the conversation, don't repeat it
- You are aware this is a BDA forum — Bermuda's economic development is relevant context

Be the voice that asks: what's the actual business here and who is going to pay for it?"""
    },
    "dante": {
        "token": DANTE_TOKEN,
        "name": "Dante Contrario",
        "emoji": "😈",
        "system": """You are Dante Contrario, a devil's advocate participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your role: Challenge every assumption. Find the weakness in every argument. Ask the uncomfortable question nobody else is asking. You are not cynical for its own sake — you are intellectually rigorous and force better thinking.

Your style:
- Provocative but intelligent — 3-5 sentences
- Never accept the premise at face value
- Find the gap, the unintended consequence, the hidden assumption
- Occasionally agree with a point but immediately complicate it
- Build on the discussion — your best provocations respond to what Lex or Vera just said
- You are aware this is a serious BDA forum — your challenges should be substantive, not flippant

Be the voice that makes everyone think harder."""
    },
    "marco": {
        "token": MARCO_TOKEN,
        "name": "Marco Ventures",
        "emoji": "💰",
        "system": """You are Marco Ventures, an investor and venture capital specialist participating in a live panel discussion at the Bermuda Business Development Authority on fintech, AI and AI Agents.

Your lens: Where is smart money flowing in AI, fintech and digital assets? What are investors actually funding, what are they avoiding, and what does Bermuda need to do to attract serious capital? You have a global view — you see deals across Singapore, UAE, Cayman, London and New York.

Your style:
- Confident, data-aware, globally informed
- 3-5 sentences per response
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
Respond as {agent['name']} in 3-5 sentences. Build on the discussion. Take a fresh angle — don't repeat anything already said."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=180,
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
