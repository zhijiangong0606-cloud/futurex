# Security Notes

Futurex is designed to keep secrets out of source control.

## What Is Not Committed

- `.env`
- Real Binance API keys or secrets
- Real Anthropic API keys
- Telegram bot tokens or chat IDs
- Mainnet credential configuration
- Local databases
- Historical data downloads
- Logs
- Virtual environments and caches

## Safe Configuration Pattern

Use `.env.example` as the template:

```bash
cp .env.example .env
```

Then fill real secrets in `.env`, which is ignored by Git.

## Exchange Safety Recommendation

For Binance API keys:

- Enable futures trading only when needed.
- Never enable withdrawals.
- Prefer testnet during development.
- Use IP restrictions when available.
- Rotate keys after public demos or screen recordings.

## AI API Safety

The AI filter only receives compact technical indicator summaries and signal metadata. It does not receive exchange secrets, Telegram tokens, or account credentials.
