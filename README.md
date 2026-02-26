# AgentSpaces Live 🚀

Real-time AI agents that listen to your meetings and debate in Telegram.

**Lex Arbitrum** ⚖️ — Regulatory & Legal  
**Vera Capita** 💼 — Commercial & Deal Structure  
**Dante Contrario** 😈 — Devil's Advocate  

---

## How it works

1. Fireflies joins your call and transcribes in real time
2. Fireflies sends transcript segments to this server via webhook
3. Server posts the transcript to your AgentSpacesLive Telegram group
4. All three agents respond with staggered timing (3s, 8s, 14s) creating a natural debate

---

## Setup

### Environment Variables (set in Railway)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_GROUP_ID` | Your AgentSpacesLive group chat ID (see below) |
| `LEX_TOKEN` | Telegram bot token for Lex |
| `VERA_TOKEN` | Telegram bot token for Vera |
| `DANTE_TOKEN` | Telegram bot token for Dante |
| `FIREFLIES_API_KEY` | Your Fireflies API key |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

### Getting your Telegram Group ID

1. Add `@userinfobot` to your AgentSpacesLive group temporarily
2. It will post the group's chat ID (a negative number like `-1001234567890`)
3. Copy that number — that's your `TELEGRAM_GROUP_ID`
4. Remove `@userinfobot` from the group

### Fireflies Webhook Setup

Once deployed to Railway, you'll get a public URL like:
`https://agentspaces-live.up.railway.app`

In Fireflies → Settings → Webhooks, add:
`https://your-railway-url.up.railway.app/webhook`

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | Fireflies sends transcript data here |
| `/health` | GET | Check server is running |
| `/test` | POST | Fire a test transcript to see agents respond |

### Test it manually

```bash
curl -X POST https://your-railway-url.up.railway.app/test \
  -H "Content-Type: application/json" \
  -d '{"text": "Should we register under DABA or seek an exemption?", "speaker": "BC"}'
```

---

## Deploy to Railway

1. Push this repo to GitHub
2. In Railway → New Project → Deploy from GitHub repo
3. Add all environment variables
4. Deploy — Railway auto-builds and gives you a public URL
