# Task 1: Language Translation Tool

## What it does
A desktop app (Tkinter) that translates text between languages.
The user types text, chooses the source and target language, and clicks Translate.

## Features
- Side-by-side input and translation panels
- 24 languages plus Auto Detect
- Translate button (or Ctrl+Enter), Swap, Clear and Copy buttons
- Right-to-left display for Urdu, Arabic, Persian and Sindhi
- Live character counter (limit 5000) and coloured status messages
- Window stays responsive while translating

## Translation services
The app tries these in order and uses the first one that works:
1. Google Cloud Translation API (only if you add a key)
2. Microsoft Translator API (only if you add a key)
3. MyMemory Translation API (free, no key needed) - main service
4. Google Translate through deep-translator (free backup)

Services without a key are skipped automatically, so the app works
without any API key.

## How to run
1. Install Python 3.
2. Install libraries: `pip install -r requirements.txt`
3. Run: `python "Language Translation Tool.py"`
4. Internet is needed for translation.

## Optional: API keys
Set them as environment variables (do not write keys inside the code):
- GOOGLE_TRANSLATE_API_KEY
- MS_TRANSLATOR_KEY and MS_TRANSLATOR_REGION
- MYMEMORY_EMAIL (gives a bigger free daily limit)

## Files
- Language Translation Tool.py : main code
- Testing_LanguageTranslationTool.png : screenshot of the app working
- requirements.txt : libraries needed

## Author
Umm e Rubab