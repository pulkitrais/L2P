#!/usr/bin/env python3
"""
ai_chat_to_pdf.py

Convert AI conversation markdown (Grok, ChatGPT, Gemini, Claude, Copilot,
Perplexity, etc.) into a clean PDF.

Quick examples:
    # 1) From markdown file
    python ai_chat_to_pdf.py conversation.md

    # 2) From clipboard (copy full chat first)
    python ai_chat_to_pdf.py --clipboard --model chatgpt --title "My ChatGPT Session"

    # 3) From direct multi-line text argument
    python ai_chat_to_pdf.py --text "# User\nWhat is quantum tunneling?\n\n# Assistant\nIt is..."

Install:
    pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Tuple

MODEL_LABELS = {
    "chatgpt": "🤖 ChatGPT",
    "grok": "⚡ Grok",
    "gemini": "✨ Gemini",
    "claude": "🧠 Claude",
    "copilot": "🛠️ Copilot",
    "perplexity": "🔎 Perplexity",
}

LIGHT_THEME = {
    "bg": "#f8fafc",
    "paper": "#ffffff",
    "text": "#0f172a",
    "muted": "#64748b",
    "border": "#dbe2ea",
    "user_bg": "#e0f2fe",
    "user_border": "#38bdf8",
    "assistant_bg": "#f8fafc",
    "assistant_border": "#94a3b8",
    "code_bg": "#0b1220",
}

DARK_THEME = {
    "bg": "#0b1220",
    "paper": "#111827",
    "text": "#e5e7eb",
    "muted": "#9ca3af",
    "border": "#374151",
    "user_bg": "#0f2a3f",
    "user_border": "#38bdf8",
    "assistant_bg": "#161f2f",
    "assistant_border": "#64748b",
    "code_bg": "#020617",
}

ROLE_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^#{1,6}\s*user\b[:\-]?", re.IGNORECASE), "user"),
    (re.compile(r"^#{1,6}\s*(assistant|ai|model|bot)\b[:\-]?", re.IGNORECASE), "assistant"),
    (re.compile(r"^\*\*\s*user\s*\*\*\s*[:\-]?", re.IGNORECASE), "user"),
    (re.compile(r"^\*\*\s*(assistant|ai|model|bot)\s*\*\*\s*[:\-]?", re.IGNORECASE), "assistant"),
    (re.compile(r"^\s*(user|human)\s*:\s*", re.IGNORECASE), "user"),
    (re.compile(r"^\s*(assistant|ai|model|bot)\s*:\s*", re.IGNORECASE), "assistant"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert AI chat markdown to a polished PDF")
    parser.add_argument("input", nargs="?", help="Path to markdown file")
    parser.add_argument("--text", help="Conversation markdown as direct text")
    parser.add_argument("--clipboard", action="store_true", help="Read markdown from clipboard")
    parser.add_argument("--output", "-o", help="Output PDF path (default: derived from input/title)")
    parser.add_argument("--title", default="AI Conversation Export", help="Document title")
    parser.add_argument("--model", default="", help="AI model name, e.g. grok/chatgpt/gemini/claude")
    parser.add_argument("--theme", choices=["light", "dark"], default="light", help="Visual theme")
    parser.add_argument(
        "--engine",
        choices=["auto", "weasyprint", "fpdf"],
        default="auto",
        help="PDF engine selection",
    )
    return parser.parse_args()


def read_input_markdown(args: argparse.Namespace) -> str:
    if args.text:
        return args.text.strip()

    if args.clipboard:
        try:
            import pyperclip  # type: ignore
        except Exception as exc:
            raise RuntimeError("pyperclip is required for --clipboard. Install dependencies first.") from exc
        value = pyperclip.paste() or ""
        if not value.strip():
            raise RuntimeError("Clipboard appears empty.")
        return value.strip()

    if args.input:
        path = Path(args.input)
        if not path.exists():
            raise RuntimeError(f"Input file not found: {path}")
        return path.read_text(encoding="utf-8")

    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            return piped.strip()

    raise RuntimeError("No input provided. Use a markdown file, --text, --clipboard, or pipe markdown to stdin.")


def role_for_line(line: str) -> str | None:
    for pattern, role in ROLE_PATTERNS:
        if pattern.match(line):
            return role
    return None


def split_conversation_blocks(markdown_text: str) -> List[Tuple[str, str]]:
    lines = markdown_text.splitlines()
    blocks: List[Tuple[str, List[str]]] = []
    current_role = "assistant"
    current_lines: List[str] = []

    def flush() -> None:
        if current_lines and "\n".join(current_lines).strip():
            blocks.append((current_role, current_lines.copy()))

    for line in lines:
        role = role_for_line(line)
        if role:
            flush()
            current_lines.clear()
            current_role = role
            cleaned = re.sub(r"^\s*(#{1,6}\s*)?(\*\*)?\s*(user|human|assistant|ai|model|bot)\s*(\*\*)?\s*[:\-]?\s*", "", line, flags=re.IGNORECASE)
            if cleaned.strip():
                current_lines.append(cleaned)
            continue
        current_lines.append(line)

    flush()

    if not blocks:
        return [("assistant", markdown_text)]

    return [(role, "\n".join(content).strip()) for role, content in blocks]


def image_available(url: str, timeout: int = 6) -> bool:
    if url.startswith("http://") or url.startswith("https://"):
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return int(getattr(resp, "status", 200)) < 400
        except Exception:
            return False
    return Path(url).exists()


def preprocess_images(markdown_text: str) -> str:
    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^\)]+)\)")

    def repl(match: re.Match[str]) -> str:
        alt, src = match.group(1).strip(), match.group(2).strip()
        if image_available(src):
            return match.group(0)
        safe_alt = alt or "Image"
        safe_src = html.escape(src)
        return f"> [Image unavailable] {safe_alt} could not be embedded. Source: `{safe_src}`"

    return image_pattern.sub(repl, markdown_text)


def preprocess_math(markdown_text: str) -> str:
    # Basic fallback style for LaTeX snippets in engines without JS math rendering.
    markdown_text = re.sub(r"\$\$([^$]+)\$\$", r"\n\n```math\n\1\n```\n\n", markdown_text, flags=re.DOTALL)
    markdown_text = re.sub(r"\$(.+?)\$", r"`\1`", markdown_text)
    return markdown_text


def markdown_to_html(md_text: str) -> str:
    try:
        import markdown  # type: ignore
    except Exception as exc:
        raise RuntimeError("markdown package is required. Install dependencies first.") from exc

    extensions = [
        "fenced_code",
        "tables",
        "toc",
        "sane_lists",
        "nl2br",
        "codehilite",
    ]
    extension_configs = {
        "codehilite": {
            "guess_lang": False,
            "linenums": False,
            "css_class": "codehilite",
            "noclasses": False,
        }
    }
    return markdown.markdown(md_text, extensions=extensions, extension_configs=extension_configs)


def get_code_css() -> str:
    try:
        from pygments.formatters import HtmlFormatter  # type: ignore
    except Exception as exc:
        raise RuntimeError("pygments is required for syntax highlighting.") from exc
    return HtmlFormatter(style="friendly").get_style_defs(".codehilite")


def conversation_html(markdown_text: str) -> str:
    blocks = split_conversation_blocks(markdown_text)
    html_blocks = []
    for role, content in blocks:
        content_html = markdown_to_html(content)
        label = "User" if role == "user" else "AI Assistant"
        html_blocks.append(
            f"""
            <section class=\"msg {role}\">
              <div class=\"msg-label\">{label}</div>
              <div class=\"msg-content\">{content_html}</div>
            </section>
            """
        )
    return "\n".join(html_blocks)


def build_full_html(title: str, model: str, body_html: str, theme_name: str) -> str:
    theme = LIGHT_THEME if theme_name == "light" else DARK_THEME
    date_text = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    model_key = (model or "").strip().lower()
    model_label = MODEL_LABELS.get(model_key, model.strip()) if model else ""
    model_line = f" • {html.escape(model_label)}" if model_label else ""
    code_css = get_code_css()

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    @page {{
      size: A4;
      margin: 20mm 14mm 18mm 14mm;
      @bottom-right {{
        content: "Page " counter(page) " / " counter(pages);
        color: {theme['muted']};
        font-size: 10px;
      }}
    }}

    :root {{
      color-scheme: {theme_name};
    }}

    body {{
      margin: 0;
      padding: 0;
      background: {theme['bg']};
      color: {theme['text']};
      font-family: "Inter", "Segoe UI", Roboto, Arial, sans-serif;
      font-size: 12pt;
      line-height: 1.5;
    }}

    .page {{
      background: {theme['paper']};
      border: 1px solid {theme['border']};
      border-radius: 12px;
      padding: 18px;
    }}

    .header {{
      border-bottom: 1px solid {theme['border']};
      margin-bottom: 14px;
      padding-bottom: 10px;
    }}

    .title {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
    }}

    .meta {{
      margin-top: 6px;
      color: {theme['muted']};
      font-size: 11px;
    }}

    .msg {{
      border: 1px solid {theme['border']};
      border-radius: 10px;
      margin: 12px 0;
      overflow: hidden;
      page-break-inside: avoid;
    }}

    .msg-label {{
      font-weight: 700;
      font-size: 11px;
      letter-spacing: .02em;
      text-transform: uppercase;
      padding: 8px 12px;
      border-bottom: 1px solid {theme['border']};
    }}

    .msg-content {{
      padding: 12px;
    }}

    .msg.user {{
      border-left: 6px solid {theme['user_border']};
      background: {theme['user_bg']};
    }}

    .msg.assistant {{
      border-left: 6px solid {theme['assistant_border']};
      background: {theme['assistant_bg']};
    }}

    h1, h2, h3 {{ margin: 0.7em 0 0.3em; }}
    p {{ margin: 0.5em 0; }}
    ul, ol {{ margin: 0.4em 0 0.6em 1.3em; }}

    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0.8em 0;
      font-size: 11px;
    }}

    th, td {{
      border: 1px solid {theme['border']};
      padding: 6px;
      vertical-align: top;
    }}

    pre {{
      overflow-x: auto;
      border-radius: 8px;
      padding: 10px;
      background: {theme['code_bg']};
    }}

    code {{
      font-family: "JetBrains Mono", Consolas, "Courier New", monospace;
      font-size: 90%;
    }}

    img {{
      max-width: 100%;
      border: 1px solid {theme['border']};
      border-radius: 8px;
      margin: 8px 0;
    }}

    blockquote {{
      margin: 0.7em 0;
      padding: 0.4em 0.8em;
      border-left: 4px solid {theme['border']};
      color: {theme['muted']};
    }}

    {code_css}
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <h1 class="title">{html.escape(title)}</h1>
      <div class="meta">{date_text}{model_line}</div>
    </header>
    {body_html}
  </main>
</body>
</html>
"""


def write_pdf_with_weasyprint(html_text: str, output_path: Path) -> None:
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:
        raise RuntimeError("WeasyPrint is not available.") from exc

    HTML(string=html_text, base_url=str(Path.cwd())).write_pdf(str(output_path))


def write_pdf_with_fpdf(markdown_text: str, title: str, model: str, output_path: Path) -> None:
    try:
        from fpdf import FPDF  # type: ignore
    except Exception as exc:
        raise RuntimeError("fpdf2 is required for fallback PDF generation.") from exc

    def latin1_safe(value: str) -> str:
        return value.encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_title(title)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, latin1_safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    meta = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if model:
        meta += f" | {MODEL_LABELS.get(model.lower(), model)}"
    pdf.cell(0, 8, latin1_safe(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    content_html = markdown_to_html(latin1_safe(markdown_text))
    pdf.write_html(f"<div>{content_html}</div>")
    pdf.output(str(output_path))


def derive_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        out = Path(args.output)
        if out.suffix.lower() != ".pdf":
            out = out.with_suffix(".pdf")
        return out

    if args.input:
        in_path = Path(args.input)
        return in_path.with_suffix(".pdf")

    slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-") or "conversation"
    return Path(f"{slug}.pdf")


def main() -> int:
    args = parse_args()
    print("[1/4] Reading input...", flush=True)

    try:
        markdown_text = read_input_markdown(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("[2/4] Preparing markdown (images/math/conversation blocks)...", flush=True)
    markdown_text = preprocess_math(preprocess_images(markdown_text))

    output_path = derive_output_path(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.engine in {"auto", "weasyprint"}:
        print("[3/4] Rendering PDF with WeasyPrint...", flush=True)
        try:
            body = conversation_html(markdown_text)
            full_html = build_full_html(args.title, args.model, body, args.theme)
            with tempfile.TemporaryDirectory(prefix="ai-chat-pdf-") as _:
                write_pdf_with_weasyprint(full_html, output_path)
            print(f"[4/4] Done: {output_path}")
            return 0
        except Exception as exc:
            if args.engine == "weasyprint":
                print(f"Error: Failed with WeasyPrint: {exc}", file=sys.stderr)
                return 1
            print(f"[3/4] WeasyPrint unavailable ({exc}). Falling back to fpdf2...", flush=True)

    print("[3/4] Rendering PDF with fpdf2 fallback...", flush=True)
    try:
        write_pdf_with_fpdf(markdown_text, args.title, args.model, output_path)
    except Exception as exc:
        print(f"Error: Fallback rendering failed: {exc}", file=sys.stderr)
        return 1

    print(f"[4/4] Done: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
