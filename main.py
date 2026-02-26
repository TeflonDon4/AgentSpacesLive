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
        "system": """You are Lex Arbitrum, a regulatory and legal agent in a live meeting Telegram feed.

STRICT RULES:
- DEFAULT: 1 sentence only. Sharp and specific.
- OCCASIONALLY (when the point genuinely requires it): up to 3-5 sentences max.
- Never repeat a point already made in this conversation.
- Never echo what Vera or Dante just said.
- React ONLY to what was just said. Move on when the topic moves on.
- Reference DABA, BMA, or law only when directly relevant.""",
        "emoji": "⚖️"
    },
    "vera": {
        "token": VERA_TOKEN,
        "name": "Vera Capita",
        "system": """You are Vera Capita, a commercial agent in a live meeting Telegram feed.

STRICT RULES:
- DEFAULT: 1 sentence only. Punchy and practical.
- OCCASIONALLY (when the point genuinely requires it): up to 3-5 sentences max.
- Never repeat a point already made in this conversation.
- Never echo what Lex or Dante just said.
- React ONLY to what was just said. Move on when the topic moves on.
- Focus on deal structure, revenue, or market opportunity.""",
        "emoji": "💼"
    },
    "dante": {
        "token": DANTE_TOKEN,
        "name": "Dante Contrario",
        "system": """You are Dante Contrario, a devil's advocate in a live meeting Telegram feed.

STRICT RULES:
- DEFAULT: 1 sentence only. Provocative and intelligent.
- OCCASIONALLY (when the point genuinely requires it): up to 3-5 sentences max.
- Never repeat a point already made — especially your own previous points.
- Never echo what Lex or Vera just said.
- React ONLY to what was just said. Drop old topics completely.
- Find a fresh angle every time.""",
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

def get_agent_response(agent_key: str, new_segment: str, prior_responses: dict) -> str:
    """Ask Claude to respond as a given agent persona."""
    agent = AGENTS[agent_key]
    
    # Only use last 3 segments — keeps agents focused on NOW
    context = "\n".join([f"{s['speaker']}: {s['text']}" for s in transcript_buffer[-3:]])
    
    # Show what other agents already said so this agent doesn't repeat them
    other_responses = "\n".join([
        f"{AGENTS[k]['name']}: {v}"
        for k, v in prior_responses.items()
        if k != agent_key and v
    ])
    other_context = f"\nOther agents already said:\n{other_responses}\n" if other_responses else ""

    user_message = f"""Recent transcript:
{context}

Just said: {new_segment}
{other_context}
Respond as {agent['name']}. DEFAULT to 1 sentence. Take a fresh angle — don't repeat anything above."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=120,
            system=agent["system"],
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude API error for {agent_key}: {e}")
        return None

def agents_respond(segment_text: str, speaker: str):
    """Have all three agents respond with staggered timing, sharing prior responses."""
    
    delays = {"lex": 5, "vera": 18, "dante": 32}
    prior_responses = {}  # Accumulates as each agent responds
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

# ── Webhook endpoint ──────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def deepgram_webhook():
    """Receive real-time transcript segments from Deepgram via local listen.py."""
    data = request.json
    
    if not data:
        return jsonify({"status": "no data"}), 400
    
    print(f"Webhook received: {data}")
    
    # listen.py posts TranscriptSegment events
    event_type = data.get("eventType", "")
    
    # Handle real-time segment events from Deepgram
    if event_type in ["Transcription", "TranscriptSegment", "transcript_ready"]:
        
        # Extract transcript data (Deepgram format via listen.py)
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
