"""
AgentSpaces Live
----------------
Receives Fireflies transcript webhooks and routes them to
Lex, Vera, and Dante — three AI agents debating in a Telegram group.
"""

import os
import time
import threading
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)
client = Anthropic()

# ── Config from environment variables ────────────────────────────────────────
TELEGRAM_GROUP_ID   = os.environ["TELEGRAM_GROUP_ID"]
LEX_TOKEN           = os.environ["LEX_TOKEN"]
VERA_TOKEN          = os.environ["VERA_TOKEN"]
DANTE_TOKEN         = os.environ["DANTE_TOKEN"]
FIREFLIES_API_KEY   = os.environ["FIREFLIES_API_KEY"]   # for verification
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]

# ── Agent Personas ────────────────────────────────────────────────────────────
AGENTS = {
    "lex": {
        "token": LEX_TOKEN,
        "name": "Lex Arbitrum",
        "system": """You are Lex Arbitrum, a sharp regulatory and legal agent participating in a live meeting via Telegram.

Your role: Analyse what is being said through the lens of regulation, law, governance, and compliance — particularly Bermuda's Digital Asset Business Act (DABA), BMA requirements, and broader financial services regulation.

Your style:
- Concise and precise — 2-4 sentences maximum per response
- Flag regulatory risks, obligations, or opportunities immediately
- Reference specific legislation or frameworks when relevant
- Use plain language — no unnecessary jargon
- Occasionally push back on commercial or contrarian views with legal reality

You are commenting in real time on a live meeting transcript. Stay sharp and relevant.""",
        "emoji": "⚖️"
    },
    "vera": {
        "token": VERA_TOKEN,
        "name": "Vera Capita",
        "system": """You are Vera Capita, a commercial and deal structure agent participating in a live meeting via Telegram.

Your role: Analyse what is being said through a commercial lens — deal structure, revenue models, market opportunity, partnerships, and financial viability.

Your style:
- Pragmatic and deal-focused — 2-4 sentences maximum per response
- Identify commercial opportunities or risks quickly
- Think about incentives, economics, and who benefits
- Challenge assumptions that don't stack up commercially
- Occasionally push back on regulatory or contrarian views with market reality

You are commenting in real time on a live meeting transcript. Stay sharp and relevant.""",
        "emoji": "💼"
    },
    "dante": {
        "token": DANTE_TOKEN,
        "name": "Dante Contrario",
        "system": """You are Dante Contrario, a devil's advocate agent participating in a live meeting via Telegram.

Your role: Challenge every assumption. Find the weakness in every argument. Ask the uncomfortable question nobody else is asking.

Your style:
- Provocative but intelligent — 2-4 sentences maximum per response
- Never accept the premise at face value
- Find the flaw, the gap, the unintended consequence
- Play contrarian even when you might privately agree
- Occasionally wind up Lex and Vera with pointed observations

You are commenting in real time on a live meeting transcript. Stay sharp and contrarian.""",
        "emoji": "😈"
    }
}

# ── Transcript buffer (stores recent transcript for context) ──────────────────
transcript_buffer = []
MAX_BUFFER = 20  # keep last 20 segments for context

def send_telegram(token: str, text: str):
    """Send a message to the Telegram group."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_GROUP_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Telegram send error: {e}")

def get_agent_response(agent_key: str, new_segment: str) -> str:
    """Ask Claude to respond as a given agent persona."""
    agent = AGENTS[agent_key]
    
    # Build context from buffer
    context = "\n".join([f"{s['speaker']}: {s['text']}" for s in transcript_buffer[-10:]])
    
    user_message = f"""Live meeting transcript context (last few exchanges):
{context}

Latest segment just spoken:
{new_segment}

Respond as {agent['name']} in 2-4 sentences. Be sharp and relevant to what was just said."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system=agent["system"],
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude API error for {agent_key}: {e}")
        return None

def agents_respond(segment_text: str, speaker: str):
    """Have all three agents respond with staggered timing."""
    
    # Stagger agent responses so it feels like a natural conversation
    delays = {"lex": 3, "vera": 8, "dante": 14}
    
    def respond(agent_key, delay):
        time.sleep(delay)
        response = get_agent_response(agent_key, segment_text)
        if response:
            agent = AGENTS[agent_key]
            message = f"{agent['emoji']} *{agent['name']}*\n{response}"
            send_telegram(agent["token"], message)
    
    for agent_key, delay in delays.items():
        t = threading.Thread(target=respond, args=(agent_key, delay))
        t.daemon = True
        t.start()

# ── Webhook endpoint ──────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def fireflies_webhook():
    """Receive transcript segments from Fireflies."""
    data = request.json
    
    if not data:
        return jsonify({"status": "no data"}), 400
    
    print(f"Webhook received: {data}")
    
    # Fireflies sends different event types
    event_type = data.get("eventType", "")
    
    # Handle transcript_ready or real-time segment events
    if event_type in ["Transcription", "TranscriptSegment", "transcript_ready"]:
        
        # Extract transcript data (Fireflies format)
        transcript = data.get("transcript", {})
        sentences = transcript.get("sentences", [])
        
        if sentences:
            # Process new sentences
            for sentence in sentences:
                speaker = sentence.get("speaker_name", "Speaker")
                text = sentence.get("text", "")
                
                if text:
                    segment = {"speaker": speaker, "text": text}
                    transcript_buffer.append(segment)
                    
                    # Keep buffer manageable
                    if len(transcript_buffer) > MAX_BUFFER:
                        transcript_buffer.pop(0)
            
            # Take the last meaningful chunk and have agents respond
            recent_text = " ".join([s["text"] for s in transcript_buffer[-3:]])
            last_speaker = transcript_buffer[-1]["speaker"] if transcript_buffer else "Speaker"
            
            # Post transcript snippet to group first
            snippet = f"🎙️ *{last_speaker}:* {transcript_buffer[-1]['text']}"
            # Use Lex's token just to post the transcript (neutral poster)
            send_telegram(LEX_TOKEN, snippet)
            
            # Then have agents respond
            agents_respond(recent_text, last_speaker)
    
    return jsonify({"status": "ok"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "AgentSpaces Live is running"}), 200

@app.route("/test", methods=["POST"])
def test_agents():
    """Test endpoint — fire a sample transcript segment to see agents respond."""
    data = request.json or {}
    text = data.get("text", "We need to decide whether to register this token offering under DABA or structure it as an exemption. The timeline is tight — client wants to launch in 60 days.")
    speaker = data.get("speaker", "BC")
    
    segment = {"speaker": speaker, "text": text}
    transcript_buffer.append(segment)
    
    send_telegram(LEX_TOKEN, f"🎙️ *{speaker}:* {text}")
    agents_respond(text, speaker)
    
    return jsonify({"status": "test fired", "text": text}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
