# L2P

## AI chat to PDF exporter

This repository includes `ai_chat_to_pdf.py`, a standalone script to convert AI conversations (Grok, ChatGPT, Gemini, Claude, Copilot, Perplexity, etc.) from Markdown into a professional PDF.

### Install

```bash
pip install -r requirements.txt
```

### Quick usage

```bash
# From markdown file
python ai_chat_to_pdf.py conversation.md

# From clipboard (copy full chat first)
python ai_chat_to_pdf.py --clipboard --model chatgpt --title "My ChatGPT Session"

# From direct markdown text
python ai_chat_to_pdf.py --text "# User\nHello\n\n# Assistant\nHi there" --model grok

# Force fallback renderer
python ai_chat_to_pdf.py conversation.md --engine fpdf
```

### Tips for Grok/ChatGPT/Gemini/Claude/Copilot/Perplexity

1. Copy the full conversation from the platform UI.
2. Paste into a `.md` file, or keep it in clipboard and use `--clipboard`.
3. Set `--model` (for example: `grok`, `chatgpt`, `gemini`, `claude`, `copilot`, `perplexity`) to label the export header.
4. Optional: use `--theme dark` for dark-style output.
