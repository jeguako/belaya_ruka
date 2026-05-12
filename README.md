# Telegram assistant bot

Simple personal bot that receives messages and stores them as tasks in a local inbox file.
It also supports two-way dialogue via local outbox queue.

## 1) Create bot token

1. Open Telegram and find `@BotFather`.
2. Run `/newbot`.
3. Copy API token.

## 2) Setup project

```bash
cd "/Users/temirkanseudzen/assistant-telegram-bot"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

- `TELEGRAM_BOT_TOKEN=...`
- Optional: `ALLOWED_CHAT_ID=...` to allow only your Telegram chat.
- Optional: `WEBAPP_URL=https://...` public HTTPS URL for Telegram Mini App.
- Optional: `AUTO_ACK=false` to disable simple auto-reply.
- Optional: `ENABLE_REMOTE_EXEC=false` to control shell execution from Telegram.
- Optional: `CMD_TIMEOUT_SEC=45` command timeout.
- Optional: `EXEC_ALLOWLIST=...` comma-separated allowed root commands for `!exec`.
- Optional: `LLM_PROVIDER=ollama` (`ollama` or `anthropic`).
- Optional: `OLLAMA_BASE_URL=http://127.0.0.1:11434`.
- Optional: `OLLAMA_MODEL=qwen2.5:7b-instruct`.
- Optional: `ANTHROPIC_API_KEY=...` for Claude `!ask`.
- Optional: `ANTHROPIC_MODEL=claude-3-5-sonnet-latest`.

## 3) Run bot

```bash
source .venv/bin/activate
python bot.py
```

## 4) Find your chat_id

1. Send `/start` to your bot.
2. Bot replies with your `chat_id`.
3. Put it into `.env` as `ALLOWED_CHAT_ID=...`.
4. Restart bot.

Extra commands:

- `/id` - show your chat_id
- `/last` - show last 5 saved tasks
- `/status` - show bot queue status
- `/shop` - open mini app for 19L water order
- `/b2b` - open B2B pre-application form
- `!ask <text>` - get autonomous LLM response in Telegram
- `!exec <command>` - execute allowed shell command on Mac

## 5) Where tasks are saved

All incoming messages are appended to:

- `inbox/tasks.md`
- `inbox/messages.jsonl`

## 6) Send reply from Mac to Telegram

With bot running, queue a message:

```bash
cd "/Users/temirkanseudzen/assistant-telegram-bot"
source .venv/bin/activate
python reply.py "Ассаляму алейкум"
```

Optional with explicit chat_id:

```bash
python reply.py "Статус по проекту обновил" 154912984
```

Bot checks `outbox/pending` every 2 seconds and sends queued replies to Telegram.

## Mini App (water order + B2B)

Static Mini App files are in `webapp/`:

- `webapp/index.html`
- `webapp/styles.css`
- `webapp/script.js`

Core behavior:

- mono product: 19L bottled water
- minimum quantity: 3 (cannot be reduced below 3)
- order comment
- delivery addresses:
  - first launch requires adding primary address
  - additional named addresses (`Дом`, `Работа`, `Дача`, custom)
- B2B pre-application with request/company/points/volume/contact fields
- partner banner for private users in B2B block

### Connect Mini App in Telegram

1. Deploy `webapp/` to any public HTTPS domain/subdomain.
2. Put this URL to `.env`:

```env
WEBAPP_URL=https://your-domain.tld
```

3. Restart bot.
4. In BotFather set domain for web app:

```text
/setdomain
@YourBot
https://your-domain.tld
```

5. In chat send `/shop` or `/b2b`.

### Timeweb quick setup (shared hosting, FTP)

1. In the Timeweb dashboard open **«Доступ по FTP»** and copy **host** (often `*.timeweb.ru`), **login**, and **password**. The FTP login is usually **not** the site subdomain (`cl254416.tw1.ru`); it is the hosting account login shown in that block. **On Timeweb shared hosting, the FTP password often matches your control-panel login password** for the primary account — use that value in `FTP_PASSWORD` when no separate FTP password is shown.
2. Put them into `.env`: `FTP_HOST`, **`FTP_USER`** (required), `FTP_PASSWORD`, optionally `FTP_TLS` (`0` = plain FTP; `1` if the panel says explicit FTP/TLS). Remote directory defaults to `/public_html`.
3. From the bot project directory run:

```bash
python3 upload_webapp_ftp.py
```

Or pass the login once without editing `.env`:

```bash
python3 upload_webapp_ftp.py --ftp-user YOUR_FTP_LOGIN_FROM_PANEL
```

4. Enable SSL (Let's Encrypt) so `WEBAPP_URL` opens over HTTPS.
5. Set `.env`:

```env
WEBAPP_URL=https://cl254416.tw1.ru
```

If custom domain is unavailable, use Timeweb free subdomain with HTTPS, e.g. `https://cl254416.tw1.ru`.

## 7) Instant remote execution from Telegram

Enable in `.env`:

```env
ENABLE_REMOTE_EXEC=true
```

Then send a message with this format:

```text
!exec ls -la ~/Desktop
```

Bot will execute the command on your Mac and return exit code + output.

Security notes:

- Only `ALLOWED_CHAT_ID` can execute commands.
- Root command must be in `EXEC_ALLOWLIST`.
- Dangerous patterns like `rm -rf /`, `shutdown`, `diskutil erase` are blocked.

## 8) Ollama assistant in Telegram (`!ask`)

Install Ollama app: [Ollama](https://ollama.com/download)

Pull model:

```bash
ollama pull qwen2.5:7b-instruct
```

Set in `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
```

Usage:

```text
!ask Составь план работ по проекту на сегодня
```

## 9) Claude assistant in Telegram (`!ask`)

Set in `.env`:

```env
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Usage:

```text
!ask Составь план работ по проекту на сегодня
```

## 10) Auto-start on macOS with launchd

Create and install LaunchAgent:

```bash
cd "/Users/temirkanseudzen/assistant-telegram-bot"
mkdir -p launchd scripts logs
```

Then use files from this repo:

- `scripts/start_bot.sh`
- `launchd/com.temirkan.assistant-bot.plist`

Install:

```bash
launchctl unload ~/Library/LaunchAgents/com.temirkan.assistant-bot.plist 2>/dev/null || true
cp launchd/com.temirkan.assistant-bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.temirkan.assistant-bot.plist
launchctl start com.temirkan.assistant-bot
```

