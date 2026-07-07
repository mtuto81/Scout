from html import escape
import re

try:
    import markdown
except Exception:
    markdown = None

CHAT_CSS = """
    body {
        margin: 0;
        width: 100%;
        background: #414B56;
        color: #F4F4F5;
        font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
        padding: 0 12px;
    }
    .messageRow {
        clear: both;
        display: block;
        margin: 14px 0;
        width: 100%;
    }
    .userRow {
        text-align: right;
    }
    .assistantRow {
        text-align: center;
    }
    .message {
        padding: 12px;
        border-radius: 14px;
        display: inline-block;
    }
    .userMessage {
        background: #272c30;
        border: 1px solid #687684;
        border-radius: 16px;
        max-width: 62%;
        text-align: right;
        margin-left: auto;
    }
    .agentMessage {
        background: transparent;
        border: 0;
        display: block;
        max-width: 100%;
        text-align: left;
    }
    .messageText {
        color: #F4F4F5;
        line-height: 1.35;
    }
    .messageText p {
        margin: 0 0 12px 0;
    }
    .messageText p:last-child {
        margin-bottom: 0;
    }
    .messageText pre {
        background: #12171C;
        border: 1px solid #56616D;
        border-radius: 8px;
        overflow-x: auto;
        padding: 12px;
        white-space: pre-wrap;
    }
    .messageText code {
        background: #12171C;
        border-radius: 4px;
        color: #FFD2C2;
        font-family: "JetBrains Mono", "Fira Code", monospace;
        padding: 2px 4px;
    }
    .messageText pre code {
        background: transparent;
        padding: 0;
    }
    .messageText h1, .messageText h2, .messageText h3 {
        color: #FFFFFF;
        margin: 12px 0 8px 0;
    }
    .messageText ul, .messageText ol {
        margin: 8px 0 12px 24px;
    }
    .messageText blockquote {
        border-left: 3px solid #FF4D00;
        color: #DADDE1;
        margin: 10px 0;
        padding-left: 12px;
    }
    .agentMessage .messageText {
        font-size: 20px;
        line-height: 1.5;
    }
    .userMessage .messageText {
        font-size: 20px;
    }
    .systemNote {
        color: #C9D0D7;
        font-size: 12px;
        font-style: italic;
        margin: 8px 0;
        text-align: center;
    }
"""


def message_html(role: str, content: str) -> str:
    content_html = message_content_html(role, content)
    if role == "user":
        return (
            "<table align='right' width='62%' cellspacing='0' cellpadding='0' "
            "style='margin-top:14px; margin-bottom:14px;'>"
            "<tr><td align='right'>"
            "<div style='background-color:#2D353D; color:#F4F4F5; "
            "border:1px solid #687684; border-radius:14px; "
            "padding:10px 12px; font-size:16px; line-height:1.35; "
            "text-align:left;'>"
            f"{content_html}"
            "</div>"
            "</td></tr></table>"
        )

    return (
        "<table width='100%' cellspacing='0' cellpadding='0' "
        "style='margin-top:18px; margin-bottom:18px;'>"
        "<tr><td align='center'>"
        "<div style='color:#F4F4F5; font-size:20px; line-height:1.5; "
        "text-align:left;'>"
        f"{content_html}"
        "</div>"
        "</td></tr></table>"
    )


def system_note_html(content: str) -> str:
    content_html = escape(content).replace("\n", "<br>")
    return (
        "<table width='100%' cellspacing='0' cellpadding='0' "
        "style='margin-top:6px; margin-bottom:6px;'>"
        "<tr><td align='center'>"
        "<span style='color:#D7DCE1; background-color:#333C46; "
        "font-size:12px; font-style:italic; padding:3px 8px; "
        "border-radius:8px;'>"
        f"{content_html}"
        "</span>"
        "</td></tr></table>"
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
