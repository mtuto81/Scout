from html import escape
import re

try:
    import markdown
except Exception:
    markdown = None

CHAT_CSS = """
:root {
    color-scheme: dark;
}
* {
    box-sizing: border-box;
}
html,
body {
    margin: 0;
    min-height: 100%;
    background: #414B56;
    color: #F4F4F5;
    font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
}
body {
    overflow-y: auto;
}
#transcript {
    min-height: 100vh;
    padding: 18px 22px 32px;
}
.messageRow,
.systemRow {
    display: flex;
    width: 100%;
    margin: 14px 0;
}
.userRow {
    justify-content: flex-end;
}
.assistantRow {
    justify-content: center;
}
.systemRow {
    justify-content: center;
    margin: 8px 0;
}
.message {
    color: #F4F4F5;
    line-height: 1.45;
    overflow-wrap: anywhere;
}
.userMessage {
    max-width: min(62%, 760px);
    background: #2D353D;
    border: 1px solid #687684;
    border-radius: 16px;
    padding: 10px 13px;
    font-size: 16px;
    text-align: left;
}
.agentMessage {
    width: min(900px, 100%);
    background: transparent;
    border: 0;
    padding: 4px 0;
    font-size: 20px;
    line-height: 1.55;
    text-align: left;
}
.streamMessage {
    opacity: 0.72;
}
.systemNote {
    display: inline-block;
    max-width: min(760px, 90%);
    color: #D7DCE1;
    background: #333C46;
    border: 1px solid #56616D;
    border-radius: 8px;
    padding: 4px 9px;
    font-size: 12px;
    font-style: italic;
    line-height: 1.3;
}
.message p {
    margin: 0 0 12px;
}
.message p:last-child {
    margin-bottom: 0;
}
.message pre {
    background: #12171C;
    border: 1px solid #56616D;
    border-radius: 8px;
    overflow-x: auto;
    padding: 12px;
    white-space: pre-wrap;
}
.message code {
    background: #12171C;
    border-radius: 4px;
    color: #FFD2C2;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    padding: 2px 4px;
}
.message pre code {
    background: transparent;
    padding: 0;
}
.message h1,
.message h2,
.message h3 {
    color: #FFFFFF;
    margin: 12px 0 8px;
}
.message ul,
.message ol {
    margin: 8px 0 12px 24px;
}
.message blockquote {
    border-left: 3px solid #FF4D00;
    color: #DADDE1;
    margin: 10px 0;
    padding-left: 12px;
}
::-webkit-scrollbar {
    width: 10px;
}
::-webkit-scrollbar-track {
    background: #414B56;
}
::-webkit-scrollbar-thumb {
    background: #687684;
    border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover {
    background: #7B8794;
}
"""


def transcript_document_html() -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<style>{CHAT_CSS}</style>
</head>
<body>
<main id=\"transcript\"></main>
<script>
(() => {{
    const transcript = document.getElementById("transcript");

    function fragmentFromHtml(html) {{
        const template = document.createElement("template");
        template.innerHTML = html;
        return template.content.cloneNode(true);
    }}

    window.scoutTranscript = {{
        append(html) {{
            transcript.appendChild(fragmentFromHtml(html));
            window.scrollTo(0, document.body.scrollHeight);
        }},
        upsert(id, html) {{
            const existing = document.getElementById(id);
            const fragment = fragmentFromHtml(html);
            if (existing) {{
                existing.replaceWith(fragment);
            }} else {{
                transcript.appendChild(fragment);
            }}
            window.scrollTo(0, document.body.scrollHeight);
        }},
        remove(id) {{
            const existing = document.getElementById(id);
            if (existing) {{
                existing.remove();
            }}
        }},
        clear() {{
            transcript.replaceChildren();
            window.scrollTo(0, 0);
        }}
    }};
}})();
</script>
</body>
</html>"""


def message_html(role: str, content: str) -> str:
    content_html = message_content_html(role, content)
    if role == "user":
        return (
            "<section class='messageRow userRow'>"
            "<article class='message userMessage'>"
            f"{content_html}"
            "</article>"
            "</section>"
        )

    return (
        "<section class='messageRow assistantRow'>"
        "<article class='message agentMessage'>"
        f"{content_html}"
        "</article>"
        "</section>"
    )


def transient_message_html(element_id: str, content: str) -> str:
    content_html = markdown_to_html(content)
    safe_id = escape(element_id, quote=True)
    return (
        f"<section id='{safe_id}' class='messageRow assistantRow'>"
        "<article class='message agentMessage streamMessage'>"
        f"{content_html}"
        "</article>"
        "</section>"
    )


def system_note_html(content: str) -> str:
    content_html = escape(content).replace("\n", "<br>")
    return (
        "<section class='systemRow'>"
        "<span class='systemNote'>"
        f"{content_html}"
        "</span>"
        "</section>"
    )


def message_content_html(role: str, content: str) -> str:
    if role == "assistant":
        return markdown_to_html(content)
    return escape(content).replace("\n", "<br>")


def markdown_to_html(content: str) -> str:
    if markdown:
        return markdown.markdown(
            content,
            extensions=["fenced_code", "tables", "nl2br"],
            output_format="html5",
        )
    return basic_markdown_to_html(content)


def basic_markdown_to_html(content: str) -> str:
    escaped = escape(content)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?m)^### (.+)$", r"<h3>\1</h3>", escaped)
    escaped = re.sub(r"(?m)^## (.+)$", r"<h2>\1</h2>", escaped)
    escaped = re.sub(r"(?m)^# (.+)$", r"<h1>\1</h1>", escaped)
    return escaped.replace("\n", "<br>")
