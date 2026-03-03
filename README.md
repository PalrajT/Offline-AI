# BoltLite for Windows (OpenRouter)

BoltLite is a lightweight desktop app inspired by Bolt.DIY workflows:
- task prompt input
- model selection
- fast response streaming
- code-first output panel
- one-click save to local files

It uses the OpenRouter Chat Completions API and is built with Python + Tkinter so it runs fast on Windows without heavy frameworks.

## Why it is fast

- **No browser runtime**: native Tkinter UI keeps startup time low.
- **Streaming responses**: shows tokens immediately instead of waiting for full output.
- **Persistent HTTP session**: reuses TCP/TLS connections via `requests.Session`.
- **Background worker thread**: UI stays responsive while a request is in flight.
- **Small context mode**: optional context trimming to reduce latency.

## Quick start

1. Install Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your OpenRouter API key:
   - PowerShell:
     ```powershell
     setx OPENROUTER_API_KEY "your_key_here"
     ```
   - Restart terminal after setting.
4. Run:
   ```bash
   python app.py
   ```

## Build a Windows executable (optional)

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name boltlite app.py
```

The executable will be created under `dist/boltlite.exe`.

## Recommended low-latency models

Use smaller/fast models from OpenRouter for sub-minute coding starts, for example:
- `openai/gpt-4o-mini`
- `anthropic/claude-3.5-haiku`
- `meta-llama/llama-3.1-8b-instruct`

## Notes

- You can set `Max output tokens` lower for faster first response.
- For fastest turnaround, keep prompts concise and enable compact context.
