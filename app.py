import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_SYSTEM = (
    "You are a fast coding copilot. Start with a concise implementation plan and then "
    "produce code quickly."
)


class OpenRouterClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/boltlite",
                "X-Title": "BoltLite",
            }
        )

    def stream_chat(self, payload: dict):
        with self.session.post(
            OPENROUTER_URL,
            data=json.dumps(payload),
            stream=True,
            timeout=(8, 120),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                    delta = event["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (KeyError, json.JSONDecodeError):
                    continue


class BoltLiteApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BoltLite - OpenRouter")
        self.geometry("1120x760")
        self.minsize(900, 620)

        self.queue = queue.Queue()
        self.worker_thread = None

        self.history = []
        self.last_response = ""

        self._build_ui()
        self.after(50, self._drain_queue)

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="API Key").grid(row=0, column=0, sticky="w")
        self.key_var = tk.StringVar(value=os.getenv("OPENROUTER_API_KEY", ""))
        ttk.Entry(top, textvariable=self.key_var, show="*", width=44).grid(
            row=0, column=1, sticky="ew", padx=6
        )

        ttk.Label(top, text="Model").grid(row=0, column=2, sticky="w")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        model_combo = ttk.Combobox(
            top,
            textvariable=self.model_var,
            values=[
                "openai/gpt-4o-mini",
                "anthropic/claude-3.5-haiku",
                "meta-llama/llama-3.1-8b-instruct",
                "qwen/qwen-2.5-coder-7b-instruct",
            ],
            width=34,
        )
        model_combo.grid(row=0, column=3, sticky="ew", padx=6)

        self.compact_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="Compact context (faster)",
            variable=self.compact_var,
        ).grid(row=0, column=4, sticky="w")

        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        middle = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        middle.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(middle, padding=8)
        right = ttk.Frame(middle, padding=8)
        middle.add(left, weight=2)
        middle.add(right, weight=3)

        ttk.Label(left, text="System Prompt").pack(anchor="w")
        self.system_text = tk.Text(left, height=6, wrap="word")
        self.system_text.insert("1.0", DEFAULT_SYSTEM)
        self.system_text.pack(fill=tk.X, pady=(2, 8))

        ttk.Label(left, text="Task Prompt").pack(anchor="w")
        self.prompt_text = tk.Text(left, height=16, wrap="word")
        self.prompt_text.pack(fill=tk.BOTH, expand=True, pady=(2, 8))

        controls = ttk.Frame(left)
        controls.pack(fill=tk.X)
        self.max_tokens_var = tk.IntVar(value=600)
        ttk.Label(controls, text="Max output tokens").pack(side=tk.LEFT)
        ttk.Spinbox(controls, from_=100, to=4096, textvariable=self.max_tokens_var, width=8).pack(
            side=tk.LEFT, padx=(6, 10)
        )

        self.send_btn = ttk.Button(controls, text="Generate", command=self.on_generate)
        self.send_btn.pack(side=tk.LEFT)
        ttk.Button(controls, text="Clear", command=self.on_clear).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Save Output", command=self.on_save).pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(left, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

        ttk.Label(right, text="Response (Streaming)").pack(anchor="w")
        self.output_text = tk.Text(right, wrap="word", font=("Consolas", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(2, 8))

    def on_generate(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Request running", "Please wait for the current response.")
            return

        key = self.key_var.get().strip()
        if not key:
            messagebox.showerror("Missing key", "Set OPENROUTER_API_KEY or paste key in API Key field.")
            return

        user_prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not user_prompt:
            messagebox.showerror("Missing prompt", "Please enter a task prompt.")
            return

        system_prompt = self.system_text.get("1.0", tk.END).strip() or DEFAULT_SYSTEM

        messages = [{"role": "system", "content": system_prompt}]
        if self.compact_var.get():
            messages.extend(self.history[-4:])
        else:
            messages.extend(self.history[-10:])
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model_var.get().strip() or DEFAULT_MODEL,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
            "max_tokens": int(self.max_tokens_var.get()),
        }

        self.output_text.delete("1.0", tk.END)
        self.last_response = ""
        self.send_btn.configure(state=tk.DISABLED)
        self.status_var.set("Connecting to OpenRouter...")

        self.worker_thread = threading.Thread(
            target=self._run_request,
            args=(key, payload, user_prompt),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_request(self, api_key: str, payload: dict, user_prompt: str):
        start = time.time()
        try:
            client = OpenRouterClient(api_key)
            first_token_time = None
            for chunk in client.stream_chat(payload):
                if first_token_time is None:
                    first_token_time = time.time() - start
                    self.queue.put(("status", f"First token in {first_token_time:.2f}s"))
                self.queue.put(("chunk", chunk))

            total = time.time() - start
            self.queue.put(("done", (user_prompt, total)))
        except requests.HTTPError as err:
            msg = f"HTTP error: {err}"
            if err.response is not None:
                msg += f"\n{err.response.text[:1000]}"
            self.queue.put(("error", msg))
        except requests.RequestException as err:
            self.queue.put(("error", f"Network error: {err}"))
        except Exception as err:
            self.queue.put(("error", f"Unexpected error: {err}"))

    def _drain_queue(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == "chunk":
                    self.last_response += data
                    self.output_text.insert(tk.END, data)
                    self.output_text.see(tk.END)
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "done":
                    prompt, total = data
                    self.history.append({"role": "user", "content": prompt})
                    self.history.append({"role": "assistant", "content": self.last_response})
                    self.status_var.set(f"Done in {total:.2f}s")
                    self.send_btn.configure(state=tk.NORMAL)
                elif kind == "error":
                    self.status_var.set("Failed")
                    messagebox.showerror("Request failed", data)
                    self.send_btn.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.after(50, self._drain_queue)

    def on_clear(self):
        self.prompt_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)
        self.status_var.set("Ready")

    def on_save(self):
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("Nothing to save", "Generate output first.")
            return

        default_name = self._suggest_filename(content)
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[
                ("Code or Text", "*.txt *.py *.js *.ts *.tsx *.json *.md"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.status_var.set(f"Saved: {os.path.basename(path)}")

    @staticmethod
    def _suggest_filename(content: str) -> str:
        m = re.search(r"(?:file|filename)\s*[:=]\s*([\w.-]+)", content, re.IGNORECASE)
        if m:
            return m.group(1)
        if "def " in content:
            return "generated.py"
        if "function " in content or "const " in content:
            return "generated.js"
        return "output.txt"


if __name__ == "__main__":
    app = BoltLiteApp()
    app.mainloop()
