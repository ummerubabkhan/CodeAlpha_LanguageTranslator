"""
Language Translation Tool (v2)
Desktop app (Tkinter) that translates text between languages.

Translation services, tried in this order:
    1. Google Cloud Translation API   (official, only if you add an API key)
    2. Microsoft Translator API       (official, only if you add a key)
    3. MyMemory Translation API       (free REST API, NO key needed)  <- main service
    4. Google Translate via deep-translator (free backup, may hit limits)
Services without a key are skipped automatically.

Install:
    python -m pip install deep-translator requests

Run:
    python "Language Translation Tool.py"  
      
Features:
    - Side-by-side input / translation panels
    - Source (or Auto Detect) and target language selection
    - Translate button (also Ctrl+Enter), Swap, Clear, Copy
    - Right-to-left display for Urdu, Arabic, Persian and Sindhi
    - Live character counter and coloured status messages
"""

import html
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import requests
from deep_translator import GoogleTranslator

# ------------------------------------------------------------ API KEYS
# Paste your keys between the quotes, OR set them as environment variables.
# IMPORTANT: delete your keys from this file before sharing the code with anyone.
GOOGLE_API_KEY = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")
MICROSOFT_API_KEY = os.environ.get("MS_TRANSLATOR_KEY", "")
MICROSOFT_REGION = os.environ.get("MS_TRANSLATOR_REGION", "")  # e.g. "eastus"
# Optional: your email. MyMemory gives a larger free daily limit when it is sent.
MYMEMORY_EMAIL = os.environ.get("MYMEMORY_EMAIL", "")

MAX_CHARS = 5000  # Google Translate limit per request

LANGUAGES = {
    "Auto Detect": "auto",
    "Arabic": "ar",
    "Bengali": "bn",
    "Chinese (Simplified)": "zh-CN",
    "Dutch": "nl",
    "English": "en",
    "French": "fr",
    "German": "de",
    "Greek": "el",
    "Hindi": "hi",
    "Indonesian": "id",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Persian": "fa",
    "Polish": "pl",
    "Portuguese": "pt",
    "Punjabi": "pa",
    "Russian": "ru",
    "Sindhi": "sd",
    "Spanish": "es",
    "Swedish": "sv",
    "Turkish": "tr",
    "Urdu": "ur",
    "Vietnamese": "vi",
}

RTL_LANGUAGES = {"ar", "fa", "ur", "sd"}  # written right-to-left

# MyMemory (backup service) needs regional codes, e.g. Urdu = "ur-PK"
MYMEMORY_CODES = {
    "ar": "ar-SA", "bn": "bn-IN", "zh-CN": "zh-CN", "nl": "nl-NL",
    "en": "en-GB", "fr": "fr-FR", "de": "de-DE", "el": "el-GR",
    "hi": "hi-IN", "id": "id-ID", "it": "it-IT", "ja": "ja-JP",
    "ko": "ko-KR", "fa": "fa-IR", "pl": "pl-PL", "pt": "pt-PT",
    "pa": "pa-IN", "ru": "ru-RU", "sd": "sd-PK", "es": "es-ES",
    "sv": "sv-SE", "tr": "tr-TR", "ur": "ur-PK", "vi": "vi-VN",
}

# Colour palette
BG = "#EEF2F7"
HEADER = "#1F3A5F"
CARD = "#FFFFFF"
ACCENT = "#2F80ED"
ACCENT_HOVER = "#1C66C9"
GREY_BTN = "#E3E8EF"
GREY_BTN_HOVER = "#D2D9E3"
TEXT = "#1B2733"
MUTED = "#6B7A8C"
BORDER = "#D5DDE6"
OK = "#1E8E4E"
ERR = "#C62828"

FONT = "Segoe UI"


# ------------------------------------------------------------ translation
def split_text(text, limit=450):
    """Split text into small pieces. MyMemory accepts at most ~500 BYTES per
    request, and Urdu/Arabic/Chinese letters use 2-3 bytes each."""
    def size(t):
        return len(t.encode("utf-8"))

    pieces, current = [], ""
    for part in re.split(r"(?<=[.!?\n۔؟])\s+", text):
        while size(part) > limit:  # very long sentence: cut it
            cut = len(part)
            while size(part[:cut]) > limit:
                cut -= 1
            if current:
                pieces.append(current)
                current = ""
            pieces.append(part[:cut])
            part = part[cut:]
        if current and size(current) + size(part) + 1 > limit:
            pieces.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        pieces.append(current)
    return pieces


def describe(error):
    """Readable error text (some library errors have an empty message)."""
    return str(error).strip() or error.__class__.__name__


def mymemory_request(chunk, source_code, target_code):
    """One call to the MyMemory Translation API (https://mymemory.translated.net)."""
    params = {"q": chunk, "langpair": f"{source_code}|{target_code}"}
    if MYMEMORY_EMAIL:
        params["de"] = MYMEMORY_EMAIL
    response = requests.get("https://api.mymemory.translated.net/get",
                            params=params, timeout=15)
    data = response.json()
    status = int(data.get("responseStatus", response.status_code))
    if status != 200:
        raise RuntimeError(f"HTTP {status}: {data.get('responseDetails', 'request failed')}")
    if data.get("quotaFinished"):
        raise RuntimeError("the free daily limit is used up (try again tomorrow)")
    translated = html.unescape(data["responseData"]["translatedText"] or "").strip()
    if not translated:
        raise RuntimeError("the service returned an empty answer")
    if "MYMEMORY WARNING" in translated.upper():
        raise RuntimeError("the free daily limit is used up (try again tomorrow)")
    return translated


def mymemory_translate(text, source, target):
    """Translate with the MyMemory API (no key needed)."""
    # With Auto Detect, try the service's own detection first, then assume English.
    attempts = ["Autodetect", "en-GB"] if source == "auto" else [MYMEMORY_CODES[source]]
    last_error = None
    for src in attempts:
        try:
            parts = [mymemory_request(chunk, src, MYMEMORY_CODES[target])
                     for chunk in split_text(text)]
            return " ".join(parts)
        except Exception as exc:
            last_error = exc
    raise last_error


def google_cloud_translate(text, source, target):
    """Official Google Cloud Translation API (v2, API-key access)."""
    body = {"q": text, "target": target, "format": "text"}
    if source != "auto":
        body["source"] = source
    response = requests.post(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": GOOGLE_API_KEY}, json=body, timeout=15,
    )
    data = response.json()
    if response.status_code != 200:
        message = data.get("error", {}).get("message", response.text)
        raise RuntimeError(f"HTTP {response.status_code}: {message}")
    return data["data"]["translations"][0]["translatedText"]


def microsoft_translate(text, source, target):
    """Official Microsoft Translator API (Azure, version 3.0)."""
    code = {"zh-CN": "zh-Hans"}  # Microsoft uses a different code for Chinese
    params = {"api-version": "3.0", "to": code.get(target, target)}
    if source != "auto":
        params["from"] = code.get(source, source)
    headers = {
        "Ocp-Apim-Subscription-Key": MICROSOFT_API_KEY,
        "Content-Type": "application/json",
    }
    if MICROSOFT_REGION:
        headers["Ocp-Apim-Subscription-Region"] = MICROSOFT_REGION
    response = requests.post(
        "https://api.cognitive.microsofttranslator.com/translate",
        params=params, headers=headers, json=[{"Text": text}], timeout=15,
    )
    data = response.json()
    if response.status_code != 200:
        message = data.get("error", {}).get("message", response.text)
        raise RuntimeError(f"HTTP {response.status_code}: {message}")
    return data[0]["translations"][0]["text"]


def free_google_translate(text, source, target):
    return GoogleTranslator(source=source, target=target).translate(text)

def translate_text(text, source, target):
    """Try each service in order and return (translated_text, service_name)."""
    services = []
    if GOOGLE_API_KEY:
        services.append(("Google Cloud Translation API", google_cloud_translate))
    if MICROSOFT_API_KEY:
        services.append(("Microsoft Translator API", microsoft_translate))
    services.append(("MyMemory Translation API", mymemory_translate))
    services.append(("Google Translate (free backup)", free_google_translate))

    errors = []
    for name, function in services:
        try:
            result = function(text, source, target)
            if result and result.strip():
                return result, name
            raise RuntimeError("empty answer")
        except Exception as exc:
            errors.append(f"{name}: {describe(exc)}")

    hint = ""
    if source == "auto":
        hint = "\n\nTip: choose the 'From' language yourself instead of Auto Detect."
    raise RuntimeError("All translation services failed.\n\n" + "\n\n".join(errors) + hint)


# --------------------------------------------------------------------- UI
def make_button(parent, text, command, bg, fg, hover, size=10, bold=False, padx=16, pady=7):
    """A flat coloured button with a hover effect."""
    btn = tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground=hover, activeforeground=fg,
        relief="flat", bd=0, cursor="hand2", padx=padx, pady=pady,
        font=(FONT, size, "bold" if bold else "normal"),
    )
    btn.bind("<Enter>", lambda e: btn.config(bg=hover) if str(btn["state"]) == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


class TranslatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Language Translation Tool")
        self.root.geometry("960x640")
        self.root.minsize(760, 540)
        self.root.configure(bg=BG)

        self.source_var = tk.StringVar(value="Auto Detect")
        self.target_var = tk.StringVar(value="Urdu")
        self.status_var = tk.StringVar(value="Ready")
        self.count_var = tk.StringVar(value=f"0 / {MAX_CHARS}")

        self._setup_styles()
        self._build_ui()
        self.input_text.focus_set()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox", fieldbackground=CARD, background=CARD,
            foreground=TEXT, bordercolor=BORDER, arrowsize=14, padding=6,
        )
        style.map("TCombobox", fieldbackground=[("readonly", CARD)],
                  foreground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def _build_ui(self):
        # ---- Header banner
        header = tk.Frame(self.root, bg=HEADER)
        header.pack(fill="x")
        tk.Label(header, text="🌐  Language Translation Tool", bg=HEADER, fg="white",
                 font=(FONT, 18, "bold")).pack(anchor="w", padx=24, pady=(14, 0))
        tk.Label(header, text="Translate text between 24 languages instantly",
                 bg=HEADER, fg="#B8C7DB", font=(FONT, 10)).pack(anchor="w", padx=24, pady=(0, 14))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ---- Language selection card
        lang_card = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        lang_card.pack(fill="x")
        inner = tk.Frame(lang_card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(2, weight=1)

        self._lang_picker(inner, "FROM", self.source_var, list(LANGUAGES), 0)
        make_button(inner, "⇄", self.swap_languages, GREY_BTN, TEXT, GREY_BTN_HOVER,
                    size=14, bold=True, padx=14, pady=4).grid(row=0, column=1, padx=16, pady=(16, 0))
        self._lang_picker(inner, "TO", self.target_var,
                          [n for n in LANGUAGES if n != "Auto Detect"], 2)

        # ---- Text panels
        panels = tk.Frame(body, bg=BG)
        panels.pack(fill="both", expand=True, pady=14)
        panels.columnconfigure(0, weight=1, uniform="panel")
        panels.columnconfigure(1, weight=1, uniform="panel")
        panels.rowconfigure(0, weight=1)

        # Input panel
        in_card = self._card(panels, 0, "Enter text")
        self.input_text = self._text_box(in_card)
        self.input_text.bind("<KeyRelease>", self._update_count)
        self.input_text.bind("<Control-Return>", lambda e: self.translate() or "break")
        in_footer = tk.Frame(in_card, bg=CARD)
        in_footer.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(in_footer, textvariable=self.count_var, bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side="left")
        make_button(in_footer, "Clear", self.clear, GREY_BTN, TEXT, GREY_BTN_HOVER,
                    size=9, padx=12, pady=3).pack(side="right")

        # Output panel
        out_card = self._card(panels, 1, "Translation")
        self.output_text = self._text_box(out_card, readonly=True, bg="#F7F9FC")
        self.output_text.tag_configure("rtl", justify="right")
        self.output_text.tag_configure("ltr", justify="left")
        out_footer = tk.Frame(out_card, bg=CARD)
        out_footer.pack(fill="x", padx=12, pady=(0, 10))
        self.copy_btn = make_button(out_footer, "📋 Copy", self.copy_output, GREY_BTN, TEXT,
                                    GREY_BTN_HOVER, size=9, padx=12, pady=3)
        self.copy_btn.pack(side="right")

        # ---- Translate button
        self.translate_btn = make_button(
            body, "Translate  ➜", self.translate, ACCENT, "white", ACCENT_HOVER,
            size=12, bold=True, padx=40, pady=10)
        self.translate_btn.pack()
        tk.Label(body, text="Tip: press Ctrl + Enter to translate", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(pady=(6, 0))

        # ---- Status bar
        status = tk.Frame(self.root, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        status.pack(fill="x", side="bottom")
        self.status_label = tk.Label(status, textvariable=self.status_var, bg=CARD, fg=MUTED,
                                     font=(FONT, 9), anchor="w")
        self.status_label.pack(fill="x", padx=24, pady=6)

    # ------------------------------------------------------- UI builders
    def _lang_picker(self, parent, label, variable, values, column):
        box = tk.Frame(parent, bg=CARD)
        box.grid(row=0, column=column, sticky="ew")
        tk.Label(box, text=label, bg=CARD, fg=MUTED, font=(FONT, 8, "bold")).pack(anchor="w")
        ttk.Combobox(box, textvariable=variable, values=values, state="readonly",
                     font=(FONT, 11)).pack(fill="x", pady=(2, 0))

    def _card(self, parent, column, title):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        tk.Label(card, text=title, bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).pack(
            anchor="w", padx=14, pady=(10, 4))
        return card

    def _text_box(self, parent, readonly=False, bg=CARD):
        box = tk.Text(
            parent, wrap="word", font=(FONT, 12), bg=bg, fg=TEXT, relief="flat",
            padx=12, pady=8, height=8, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            insertbackground=TEXT, undo=True,
        )
        box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        if readonly:
            box.config(state="disabled")
        return box

    # ----------------------------------------------------------- helpers
    def _set_status(self, message, kind="info"):
        colour = {"info": MUTED, "ok": OK, "error": ERR}[kind]
        self.status_var.set(message)
        self.status_label.config(fg=colour)

    def _update_count(self, _event=None):
        n = len(self.input_text.get("1.0", "end-1c"))
        self.count_var.set(f"{n} / {MAX_CHARS}")

    def _set_output(self, text, lang_code="en"):
        direction = "rtl" if lang_code in RTL_LANGUAGES else "ltr"
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text, direction)
        self.output_text.config(state="disabled")

    def _get_output(self) -> str:
        return self.output_text.get("1.0", "end-1c").strip()

    # ----------------------------------------------------------- actions
    def swap_languages(self):
        src, tgt = self.source_var.get(), self.target_var.get()
        if src == "Auto Detect":
            self._set_status("Choose a specific 'From' language to swap.", "error")
            return
        self.source_var.set(tgt)
        self.target_var.set(src)

        # Move the translation into the input box for a quick back-translation
        translated = self._get_output()
        if translated:
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", translated)
            self._set_output("")
            self._update_count()
        self._set_status("Languages swapped.")

    def clear(self):
        self.input_text.delete("1.0", "end")
        self._set_output("")
        self._update_count()
        self._set_status("Ready")
        self.input_text.focus_set()

    def translate(self):
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            self._set_status("Please enter some text to translate.", "error")
            return
        if len(text) > MAX_CHARS:
            self._set_status(f"Text is too long (limit {MAX_CHARS} characters).", "error")
            return

        source = LANGUAGES[self.source_var.get()]
        target = LANGUAGES[self.target_var.get()]
        if source == target:
            self._set_output(text, target)
            self._set_status("Source and target are the same language.")
            return

        self.translate_btn.config(state="disabled", text="Translating...")
        self._set_status("Translating...")

        # Run the network call in a thread so the window doesn't freeze
        threading.Thread(
            target=self._translate_worker, args=(text, source, target), daemon=True
        ).start()

    def _translate_worker(self, text, source, target):
        try:
            result, service = translate_text(text, source, target)
            self.root.after(0, self._on_success, result, service, target)
        except Exception as exc:  # no internet, bad language codes, etc.
            self.root.after(0, self._on_error, f"Translation failed: {exc}")

    def _on_success(self, result, service, target):
        self._set_output(result or "", target)
        self._set_status(f"Done  •  translated by {service}", "ok")
        self.translate_btn.config(state="normal", text="Translate  ➜")

    def _on_error(self, message):
        self._set_status("Translation failed. See the message.", "error")
        self.translate_btn.config(state="normal", text="Translate  ➜")
        messagebox.showerror("Error", message)

    def copy_output(self):
        text = self._get_output()
        if not text:
            self._set_status("Nothing to copy yet.", "error")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("Translation copied to clipboard.", "ok")
        self.copy_btn.config(text="✔ Copied")
        self.root.after(1500, lambda: self.copy_btn.config(text="📋 Copy"))


if __name__ == "__main__":
    root = tk.Tk()
    TranslatorApp(root)
    root.mainloop()