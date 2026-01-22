"""
HTML rendering helpers for Codex JSONL conversion.

Most AI generated part, regexes untouched, html/css/JS only lightly modified.

"""

import html
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

TOOL_OUTPUT_TRUNCATE_LIMIT = 4000   # Tool Output can be large, 4000 chosen as a reasonable middle-ground
PROMPT_TRUNCATE_LIMIT = 300         # Limit used in the Overview table

TEXT_BLOCK_TYPES = {"input_text", "output_text", "summary_text", "text"}

CONTEXT_PLACEHOLDER = "__CONTEXT_PROTECTED__"
CODE_BLOCK_PLACEHOLDER_PREFIX = "__CODE_BLOCK_"

ICON_USER           = "\N{BUST IN SILHOUETTE}"
ICON_QUESTION       = "\N{BLACK QUESTION MARK ORNAMENT}"
ICON_USER_REQUEST   = f"{ICON_QUESTION}"
ICON_ASSISTANT      = "\N{ROBOT FACE}"
ICON_REASONING      = "\N{BRAIN}"
ICON_TOOL           = "\N{HAMMER AND WRENCH}"
ICON_GEAR           = "\N{GEAR}"
ICON_FILTERS        = "\N{LEFT-POINTING MAGNIFYING GLASS}"

CONTEXT_SECTION_PATTERN = re.compile(
    r"(?ms)(^#+\s*Context from my IDE setup:)"
    r"(.*?)(?=^#+\s*My request for Codex:|\Z)"
)
CODE_BLOCK_PATTERN = re.compile(r"```(\w+)?\n?(.*?)```", re.DOTALL)
NEWLINES_BEFORE_HEADER_PATTERN = re.compile(r"\n{2,}(?=#)")
NEWLINES_PATTERN = re.compile(r"\n{3,}")
MY_REQUEST_HEADER_PATTERN = re.compile(r"(?m)^#+\s+My request for Codex:?")
HEADER_PATTERNS = [
    (re.compile(r"(?m)^# (.*?)$"), r"<h1>\1</h2>"),
    (re.compile(r"(?m)^## (.*?)$"), r"<h2>\1</h3>"),
    (re.compile(r"(?m)^### (.*?)$"), r"<h3>\1</h4>"),
    (re.compile(r"(?m)^#### (.*?)$"), r"<h4>\1</h4>"),
]
STRONG_PATTERN = re.compile(r"\*\*(.*?)\*\*")
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
REL_PATH_SPLIT_PATTERN = re.compile(r"[\\\\/]+")

MY_REQUEST_HEADER_REPLACEMENT = f"<h2>{ICON_USER_REQUEST} My request for Codex:</h2>"


def extract_text_content(content_data: Any) -> str:
    """Extract textual content from nested message structures.

    Args:
        content_data: Either a string or a list of content blocks (dicts).

    Returns:
        Concatenated text for supported block types, or an empty string.
    """
    if isinstance(content_data, str):
        return content_data
    if not isinstance(content_data, list):
        return ""

    text_parts = []
    for item in content_data:
        if isinstance(item, dict) and item.get("type") in TEXT_BLOCK_TYPES:
            text_parts.append(item.get("text", ""))
    return "".join(text_parts)


def _extract_context_block(text: str) -> Tuple[str, Optional[str]]:
    """Extract and replace the IDE context section with a placeholder."""
    match = CONTEXT_SECTION_PATTERN.search(text)
    if not match:
        return text, None
    context_content = match.group(2)
    replaced_text = text[:match.start()] + CONTEXT_PLACEHOLDER + "\n" + text[match.end():]
    return replaced_text, context_content


def _extract_code_blocks(text: str) -> Tuple[str, Dict[str, str]]:
    """Replace fenced code blocks with placeholders and collect their HTML."""
    code_blocks = {}

    def store_code_block(match):
        key = f"{CODE_BLOCK_PLACEHOLDER_PREFIX}{len(code_blocks)}__"
        lang = match.group(1) or "text"
        content = match.group(2)
        code_blocks[key] = f'<pre><code class="language-{lang}">{content}</code></pre>'
        return key

    return CODE_BLOCK_PATTERN.sub(store_code_block, text), code_blocks


def _apply_markdown_formatting(text: str) -> str:
    """Convert a subset of markdown-style formatting into HTML tags."""
    text = NEWLINES_BEFORE_HEADER_PATTERN.sub("\n", text)
    text = NEWLINES_PATTERN.sub("\n\n", text)
    text = MY_REQUEST_HEADER_PATTERN.sub(MY_REQUEST_HEADER_REPLACEMENT, text)
    for pattern, replacement in HEADER_PATTERNS:
        text = pattern.sub(replacement, text)
    text = STRONG_PATTERN.sub(r"<strong>\1</strong>", text)
    text = INLINE_CODE_PATTERN.sub(r'<code class="inline-code">\1</code>', text)
    return text


def _wrap_context_block(context_content: str) -> str:
    """Wrap the IDE context section in a collapsible <details> block."""
    return (
        "<details><summary>Context from my IDE setup</summary>\n"
        f"<div class=\"context-content\">{context_content}</div>\n"
        "</details>\n"
    )


def format_content(text: str) -> str:
    """Render message content as safe, styled HTML.

    This function escapes raw text, protects the IDE context block, converts
    Markdown-like headers and code blocks to HTML, and restores the protected
    content at the end.

    Args:
        text: Raw message content.

    Returns:
        HTML string safe for embedding inside the transcript.
    """
    if not text:
        return ""

    escaped_text = html.escape(text)
    escaped_text, context_content = _extract_context_block(escaped_text)
    escaped_text, code_blocks = _extract_code_blocks(escaped_text)
    escaped_text = _apply_markdown_formatting(escaped_text)

    for key, code_html in code_blocks.items():
        escaped_text = escaped_text.replace(key, code_html)

    if context_content is not None:
        escaped_text = escaped_text.replace(
            CONTEXT_PLACEHOLDER,
            _wrap_context_block(context_content),
        )

    return escaped_text


def get_html_header(date_str: str = "", index_href: str = "codex_sessions_overview.html") -> str:
    """Build the HTML document header and top-of-page layout.

    Args:
        date_str: Optional session date string shown under the title.
        index_href: Relative link to the overview index.

    Returns:
        The HTML header portion including CSS and the filter sidebar.
    """
    date_html = ""
    if date_str:
        # Reduced bottom margin here because the separator adds its own spacing
        date_html = f'<div style="text-align: center; color: #888; margin-bottom: 10px; font-size: 0.9em; font-weight: 500;">{date_str}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Log</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #f4f6f8;
            --panel: #ffffff;
            --panel-muted: #f7f9fb;
            --ink: #1f2937;
            --muted: #6b7280;
            --accent: #1f9d8e;
            --accent-2: #e07a5f;
            --line: #e5e7eb;
            --shadow: 0 10px 28px rgba(31, 41, 55, 0.12);
            --shadow-soft: 0 2px 10px rgba(31, 41, 55, 0.08);
            --radius-lg: 18px;
            --radius-md: 12px;
        }}

        * {{ box-sizing: border-box; }}

        body {{
            font-family: "IBM Plex Sans", "Space Grotesk", sans-serif;
            line-height: 1.55;
            margin: 0;
            padding: 0;
            color: var(--ink);
            background: var(--bg);
        }}

        body::before {{
            content: "";
            position: fixed;
            inset: 0;
            background:
                radial-gradient(1200px 600px at -10% -10%, rgba(31, 157, 142, 0.12), transparent 60%),
                radial-gradient(900px 500px at 110% 10%, rgba(224, 122, 95, 0.12), transparent 60%),
                linear-gradient(180deg, #f8fafc 0%, #eef2f6 100%);
            z-index: -1;
            pointer-events: none;
        }}

        h1, h2, h3, h4 {{
            font-family: "Space Grotesk", sans-serif;
            letter-spacing: -0.01em;
        }}

        /* --- LAYOUT --- */
        .wrapper {{ padding: 40px 24px 60px; }}
        .container {{ width: 100%; max-width: 1200px; margin: 0 auto; }}

        /* HEADER SEPARATOR */
        .header-separator {{
            border: 0;
            height: 1px;
            background-image: linear-gradient(to right, rgba(31, 41, 55, 0), rgba(31, 41, 55, 0.2), rgba(31, 41, 55, 0));
            margin: 18px auto 40px auto;
            width: 80%;
        }}

        /* SIDEBAR */
        .sidebar {{
            position: fixed;
            top: 20px;
            left: 20px;
            width: 230px;
            background: var(--panel);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow);
            border: 1px solid rgba(31, 41, 55, 0.08);
            z-index: 1000;
            overflow: hidden;
        }}
        .sidebar-header {{
            background: linear-gradient(135deg, rgba(31, 157, 142, 0.12), rgba(31, 157, 142, 0.02));
            padding: 16px 20px;
            border-bottom: 1px solid var(--line);
            cursor: move;
            user-select: none;
        }}
        .sidebar-header h3 {{
            margin: 0;
            font-size: 1.05em;
            color: var(--ink);
            font-family: "Space Grotesk", sans-serif;
        }}
        .sidebar-content {{ padding: 14px 20px; }}
        .filter-group {{ display: flex; align-items: center; margin-bottom: 10px; cursor: pointer; }}
        .filter-group input {{ margin-right: 10px; transform: scale(1.1); cursor: pointer; }}
        .filter-group label {{ cursor: pointer; font-size: 0.95em; color: var(--muted); }}
        .filter-group:hover label {{ color: var(--ink); }}
        .index-link {{ text-decoration: none; color: var(--ink); font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }}
        .index-link:hover {{ color: var(--accent); }}

        @media (max-width: 1500px) {{
            .sidebar {{ position: static; width: 100%; margin-bottom: 20px; box-shadow: none; border: 1px solid var(--line); }}
            .sidebar-header {{ cursor: default; }}
        }}

        /* --- MESSAGES (Chat Bubbles) --- */
        .message {{
            margin-bottom: 25px;
            padding: 24px;
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-soft);
            background: var(--panel);
            border: 1px solid rgba(31, 41, 55, 0.08);
            position: relative;
            box-sizing: border-box;
            animation: rise 0.35s ease both;
        }}
        .hidden {{ display: none !important; }}

        /* RIGHT ALIGNMENT */
        .message.role-user-chat,
        .message.role-user-log {{
            width: 85%;
            margin-left: auto;
            margin-right: 0;
            border-top-right-radius: 6px;
        }}

        .message.role-user-chat {{ background-color: #f1f7ff; border-right: 6px solid #4d9de0; }}
        .message.role-user-log {{ background-color: #f7f9fb; border-right: 6px dashed #7aa7d8; color: #4b5563; }}
        .message.role-assistant {{ background-color: #f0fbf9; border-left: 6px solid var(--accent); }}
        .message.role-developer {{ background-color: #fff6f0; border-left: 6px solid var(--accent-2); border: 1px dashed rgba(224, 122, 95, 0.4); }}
        .message.role-model-info {{ background-color: #e9e9f5; border-left: 6px solid var(--accent-2); border: 1px dashed rgba(224, 122, 95, 0.4); }}
        .message.type-tool-call {{ background-color: #f0fafa; border-left: 6px solid #2aa198; }}
        .message.type-tool-output {{ background-color: #1f2937; color: #e5e7eb; border-left: 6px solid #6b7280; padding: 18px; border-radius: var(--radius-md); border-top-left-radius: 6px; }}
        .message.type-reasoning {{ background-color: #f8fafb; border-left: 6px solid #9ca3af; }}

        .role {{
            font-size: 1.1em;
            font-weight: 700;
            margin-bottom: 14px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(31, 41, 55, 0.12);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .role-user-chat .role {{ color: #1f4b99; }}
        .role-user-log .role {{ color: #4b6a87; }}
        .role-assistant .role {{ color: #0f766e; }}

        details {{ background-color: #ffffff; border: 1px solid var(--line); border-radius: var(--radius-md); padding: 10px 14px; margin-bottom: 18px; box-shadow: 0 2px 6px rgba(31, 41, 55, 0.06); }}
        summary {{ cursor: pointer; font-weight: 600; color: var(--muted); font-size: 0.95em; outline: none; user-select: none; }}
        summary:hover {{ color: var(--ink); }}
        details[open] {{ border-color: #cbd5e1; }}
        details[open] summary {{ margin-bottom: 10px; border-bottom: 1px solid var(--line); padding-bottom: 6px; color: var(--ink); }}
        .context-content {{ font-family: "IBM Plex Mono", monospace; font-size: 0.92em; color: #4b5563; white-space: pre-wrap; }}
        .content {{ white-space: pre-wrap; font-family: inherit; font-size: 1.02em; }}
        .content h2 {{ margin-top: 24px; margin-bottom: 14px; font-size: 1.25em; font-weight: 700; color: #111827; }}
        .content h3 {{ margin-top: 14px; margin-bottom: 8px; font-size: 1.05em; font-weight: 600; color: #374151; background: rgba(31, 41, 55, 0.05); padding: 6px 12px; border-radius: 8px; display: inline-block; }}
        .content h4 {{ margin-top: 10px; font-size: 0.98em; font-weight: 600; color: #4b5563; }}
        pre {{ background: #0f172a !important; color: #dbeafe; padding: 18px; border-radius: 10px; box-shadow: 0 6px 16px rgba(15, 23, 42, 0.18); overflow-x: auto; margin: 18px 0; font-size: 0.92em; font-family: "IBM Plex Mono", monospace; }}
        .inline-code {{ background: #eef2f7; padding: 2px 6px; border-radius: 4px; color: #b45309; font-size: 0.9em; border: 1px solid #e2e8f0; font-family: "IBM Plex Mono", monospace; }}
        .reasoning-content {{ font-style: italic; color: #4b5563; }}
        .reasoning-title {{ font-weight: 700; margin-bottom: 6px; display: block; font-style: normal; text-transform: uppercase; font-size: 0.75em; color: #6b7280; letter-spacing: 0.08em; }}
        .tool-header {{ font-size: 0.85em; color: #0f766e; font-weight: 700; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.06em; }}
        .message.type-tool-output .tool-header {{ color: #e5e7eb; }}
        .truncated {{ color: #fca5a5; font-style: italic; font-size: 0.85em; margin-top: 6px; }}

        @keyframes rise {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
    </style>
</head>
<body>

<div class="sidebar" id="draggable-sidebar">
    <div class="sidebar-header" id="sidebar-handle"><h3>{ICON_FILTERS} Filters</h3></div>
    <div class="sidebar-content">
        <div class="filter-group"><input type="checkbox" id="check-user-chat" checked><label for="check-user-chat">User (Chat Messages)</label></div>
        <div class="filter-group"><input type="checkbox" id="check-user-log"><label for="check-user-log">User (Stream Logs)</label></div>
        <div class="filter-group"><input type="checkbox" id="check-assistant" checked><label for="check-assistant">Assistant</label></div>
        <div class="filter-group"><input type="checkbox" id="check-reasoning" checked><label for="check-reasoning">Reasoning</label></div>
        <div class="filter-group"><input type="checkbox" id="check-tools"><label for="check-tools">Tool Calls</label></div>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <div class="filter-group"><input type="checkbox" id="check-developer"><label for="check-developer">Developer / System</label></div>
        <div class="filter-group"><input type="checkbox" id="check-tool-output"><label for="check-tool-output">Tool Outputs</label></div>
        <div class="filter-group"><input type="checkbox" id="check-used-model"><label for="check-used-model">Model Info</label></div>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <div class="filter-group"><a class="index-link" href="{index_href}">&#127968; Overview</a></div>
    </div>
</div>

<div class="wrapper">
<div class="container">
    <h1 style="text-align: center; color: #333; margin-bottom: 10px;">Codex Session Transcript</h1>
    {date_html}
    <div class="header-separator"></div>
"""


def get_html_footer() -> str:
    """Return the HTML footer and JavaScript for UI interactivity."""
    return """
</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
<script>
    const filters = {
        'check-user-chat': 'role-user-chat',
        'check-user-log': 'role-user-log',
        'check-assistant': 'role-assistant',
        'check-developer': 'role-developer',
        'check-reasoning': 'type-reasoning',
        'check-tools': 'type-tool-call',
        'check-tool-output': 'type-tool-output',
        'check-used-model': 'role-model-info'
    };
    function applyFilters(){ 
        for(const[id,cls] of Object.entries(filters)){ 
            const cb=document.getElementById(id); 
            const els=document.getElementsByClassName(cls); 
            for(let el of els){ 
                if(cb.checked) el.classList.remove('hidden'); 
                else el.classList.add('hidden'); 
            } 
        } 
    }
    for(const id in filters) document.getElementById(id).addEventListener('change',applyFilters);
    applyFilters();

    const sb=document.getElementById('draggable-sidebar'), h=document.getElementById('sidebar-handle');
    let isD=false,sX,sY,iL,iT;
    h.addEventListener('mousedown',(e)=>{isD=true;sX=e.clientX;sY=e.clientY;const r=sb.getBoundingClientRect();iL=r.left;iT=r.top;e.preventDefault();});
    document.addEventListener('mousemove',(e)=>{if(!isD)return;sb.style.left=`${iL+e.clientX-sX}px`;sb.style.top=`${iT+e.clientY-sY}px`;});
    document.addEventListener('mouseup',()=>isD=false);
</script>
</body>
</html>
"""


def _should_emit_text(text: str, seen_set: Set[int]) -> bool:
    """Determine if text is unique and should be included in the html output.

    This function filters out empty strings and exact duplicates. It uses
    hashing to track seen content.

    Args:
        text (str): The string content to check.
        seen_set (set): A set of integer hashes representing previously
            processed messages. This set is modified in-place if the text is new.

    Returns:
        bool: True if the text is non-empty and has not been seen before and False otherwise.
    """
    if not text:
        return False
    text_hash = hash(text)
    if text_hash in seen_set:
        return False
    seen_set.add(text_hash)
    return True


def _build_message_html(role: str, css_class: str, icon: str, text: str) -> str:
    """Render a chat bubble for a single message."""
    return (
        f'<div class="message {css_class}">'
        f'<div class="role">{icon} {role.capitalize()}</div>'
        f'<div class="content">{format_content(text)}</div>'
        f'</div>'
    )


def _build_reasoning_html(text: str) -> str:
    """Render a styled reasoning block."""
    return (
        '<div class="message type-reasoning">'
        f'<span class="reasoning-title">{ICON_REASONING} Reasoning</span>'
        f'<div class="reasoning-content">{format_content(text)}</div>'
        '</div>'
    )


def _format_tool_args(args: Any) -> str:
    """Pretty-print tool arguments as JSON when possible."""
    try:
        parsed = json.loads(args) if isinstance(args, str) else args
        return json.dumps(parsed, indent=2)
    except Exception:
        return str(args)


def _build_tool_call_html(tool: str, args: Any, lang: str = "json") -> str:
    """Render a tool call message with formatted arguments."""
    pretty = _format_tool_args(args)
    return (
        '<div class="message type-tool-call">'
        f'<div class="tool-header">{ICON_TOOL} Tool Call: {html.escape(tool)}</div>'
        f'<pre><code class="language-{lang}">{html.escape(pretty)}</code></pre>'
        '</div>'
    )


def _build_custom_tool_call_html(tool: str, inp: str) -> str:
    """Render a custom tool call message."""
    return (
        '<div class="message type-tool-call">'
        f'<div class="tool-header">{ICON_TOOL} Tool Call: {html.escape(tool)}</div>'
        f'<pre><code class="language-diff">{html.escape(inp)}</code></pre>'
        '</div>'
    )


def _build_tool_output_html(output: str) -> str:
    """Render tool output with truncation when needed."""
    truncated_note = ""
    if output and len(output) > TOOL_OUTPUT_TRUNCATE_LIMIT:
        output = output[:TOOL_OUTPUT_TRUNCATE_LIMIT]
        truncated_note = '<div class="truncated">... (truncated)</div>'
    return (
        '<div class="message type-tool-output">'
        f'<div class="tool-header">{ICON_TOOL} Tool Call Output</div>'
        f'<pre><code class="language-text">{html.escape(output)}</code></pre>'
        f'{truncated_note}'
        '</div>'
    )


def _build_event_message(payload: Dict[str, Any], processing_map: Dict[str, tuple]) -> str:
    """Convert an event_msg payload into a rendered HTML block."""

    msg_type = payload.get("type")
    text = payload.get("message", "")

    config = processing_map.get(msg_type)  # Either user_message or agent_message

    if not config or not text:
        return ""
    
    display_name, css_class, icon, seen_set = config

    if not _should_emit_text(text, seen_set):
        return ""

    return _build_message_html(display_name, css_class, icon, text)


def _build_response_message(payload: Dict[str, Any], processing_map: Dict[str, tuple]) -> str:
    """Convert a response message payload into HTML."""
    
    role = payload.get("role", "unknown")
    text = extract_text_content(payload.get("content"))

    config = processing_map.get(role.lower(), processing_map.get("default"))

    if not config or not text:
        return ""

    display_name, css_class, icon, seen_set = config

    if not _should_emit_text(text, seen_set):
        return ""

    return _build_message_html(display_name, css_class, icon, text)


def _build_turn_context_message(payload: Dict[str, Any], processing_map: Dict[str, tuple]) -> str:
    """Convert a turn context message with model/reasoning payload into a rendered HTML block."""
    
    # Log example: "model":"gpt-5.2-codex","effort":"medium"
    model_type = payload.get("model")
    effort_type = payload.get("effort", "")

    if not model_type:
        return ""

    text = f"**Used model:** {model_type} \n**Reasoning Effort:** {effort_type}"

    config = processing_map.get("turn_context")
    display_name, css_class, icon, _ = config
    
    return _build_message_html(display_name, css_class, icon, text)


def _build_response_item(payload: Dict[str, Any], processing_map: Dict[str, tuple]) -> str:
    """Render response_item records into message HTML."""
    item_type = payload.get("type")
    if item_type == "message":
        return _build_response_message(payload, processing_map)
    if item_type == "reasoning":
        text = extract_text_content(payload.get("summary", []))
        return _build_reasoning_html(text) if text else ""
    if item_type == "function_call":
        tool = payload.get("name", "unknown")
        args = payload.get("arguments", "{}")
        return _build_tool_call_html(tool, args, lang="json")
    if item_type == "custom_tool_call":
        tool = payload.get("name", "unknown")
        inp = payload.get("input", "")
        return _build_custom_tool_call_html(tool, inp)
    if item_type == "function_call_output":
        out = payload.get("output", "")
        return _build_tool_output_html(out)
    return ""


def _truncate_prompt(prompt: str, limit: int = PROMPT_TRUNCATE_LIMIT) -> str:
    """Trim long prompts for the overview table."""
    if not prompt:
        return ""
    return prompt[:limit]


def _split_rel_path(rel_path: str) -> List[str]:
    """Split a relative path into folder parts."""
    parts = REL_PATH_SPLIT_PATTERN.split(rel_path)
    return [part for part in parts if part]


def _build_index_tree(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a nested folder tree structure for index rendering."""
    root = {"name": "", "children": {}, "items": []}
    for entry in entries:
        parts = _split_rel_path(entry["rel_path"])
        if not parts:
            root["items"].append(entry)
            continue
        dir_parts = parts[:-1]
        node = root
        for part in dir_parts:
            if part not in node["children"]:
                node["children"][part] = {"name": part, "children": {}, "items": []}
            node = node["children"][part]
        node["items"].append(entry)
    return root


def _sort_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort entries by timestamp descending."""
    return sorted(
        entries,
        key=lambda e: e["timestamp"] or datetime.min,
        reverse=False,
    )


def _render_entries_table(entries: List[Dict[str, Any]]) -> str:
    """Render a table of session entries for a single folder."""
    if not entries:
        return ""
    rows = []
    for entry in _sort_entries(entries):
        date_text = html.escape(entry["date"])
        full_prompt = entry["prompt"] or ""
        prompt_preview = _truncate_prompt(full_prompt)
        prompt_preview_text = html.escape(prompt_preview)
        prompt_full_text = html.escape(full_prompt)
        href = html.escape(entry["href"])
        prompt_data = html.escape(full_prompt, quote=True)
        if full_prompt and prompt_preview != full_prompt:
            prompt_html = (
                '<details class="prompt-details">'
                f'<summary><span class="prompt-preview">{prompt_preview_text + "..."}</span>'
                '<span class="prompt-show-more">Show more</span></summary>'
                f'<div class="prompt-full">{prompt_full_text + "\n"}'
                '<span class="prompt-show-less" onclick="this.closest(\'details\').removeAttribute(\'open\')"> Show less</span></div>'
                '</details>'
            )
        else:
            prompt_html = prompt_preview_text
        rows.append(
            f"<tr class=\"entry-row\" data-prompt=\"{prompt_data}\"><td><a href=\"{href}\">{date_text}</a></td><td class=\"prompt\">{prompt_html}</td></tr>"
        )
    return (
        "<table class=\"entries\">"
        "<thead><tr><th>Date</th><th>Initial prompt</th></tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_folder_sections(node: Dict[str, Any], level: int = 0) -> str:
    """Render nested <details> sections for folder trees."""
    sections = []
    for name in sorted(node["children"]):
        child = node["children"][name]
        child_html = _render_folder_sections(child, level + 1)
        table_html = _render_entries_table(child["items"])
        content = table_html + child_html
        if not content:
            continue
        summary = html.escape(name)
        sections.append(
            f'<details class="folder level-{level + 1}"><summary>{summary}</summary>{content}</details>'
        )
    return "".join(sections)


def _build_index_html(entries: List[Dict[str, Any]]) -> str:
    """Generate the HTML overview page for all sessions."""
    if not entries:
        body = "<p>No converted sessions found.</p>"
    else:
        tree = _build_index_tree(entries)
        root_table = _render_entries_table(tree["items"])
        body = root_table + _render_folder_sections(tree)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Overview</title>
    <style>
        :root {{
            --bg: #f4f6f8;
            --panel: #ffffff;
            --panel-muted: #f7f9fb;
            --ink: #1f2937;
            --muted: #6b7280;
            --accent: #1f9d8e;
            --line: #e5e7eb;
            --shadow: 0 8px 22px rgba(31, 41, 55, 0.12);
        }}

        body {{ font-family: "IBM Plex Sans", "Space Grotesk", sans-serif; line-height: 1.5; margin: 0; padding: 0; background: var(--bg); color: var(--ink); }}
        .wrapper {{ padding: 40px 20px 60px; }}
        .container {{ width: 100%; max-width: 1100px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 8px; font-family: "Space Grotesk", sans-serif; }}
        p {{ text-align: center; color: var(--muted); margin-top: 0; }}
        .search-bar {{ display: flex; justify-content: center; margin: 18px auto 28px; }}
        .search-field {{ position: relative; width: min(620px, 100%); }}
        .search-icon {{
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--muted);
            font-size: 1em;
            pointer-events: none;
        }}
        .search-bar input {{
            width: 100%;
            padding: 12px 14px;
            padding-left: 40px;
            border-radius: 10px;
            border: 1px solid var(--line);
            background: var(--panel);
            box-shadow: 0 2px 8px rgba(31, 41, 55, 0.08);
            font-size: 0.98em;
        }}
        .search-bar input:focus {{ outline: 2px solid rgba(31, 157, 142, 0.25); border-color: rgba(31, 157, 142, 0.6); }}
        .hidden {{ display: none !important; }}
        .no-results {{
            text-align: center;
            color: var(--muted);
            margin: 12px 0 0;
            font-size: 0.95em;
            display: none;
        }}
        .no-results.visible {{ display: block; }}

        mark.highlight {{
            background-color: #fde047; /* Yellow */
            color: #374151;
            padding: 0;
            margin: 0;
            border-radius: 2px;
        }}

        table.entries {{ 
            width: 100%;
            border-collapse: collapse;
            background: var(--panel);
            box-shadow: var(--shadow);
            border-radius: 12px;
            overflow: hidden;
            table-layout: fixed;
        }}
        th, td {{ text-align: left; padding: 14px 16px; border-bottom: 1px solid var(--line); vertical-align: top; }}
        th {{ background: var(--panel-muted); font-weight: 700; }}
        th:nth-child(1) {{
            width: 120px;
        }}
        tr:nth-child(even) td {{ background: #fafbfc; }}
        tr.entry-row:hover td {{ background: #eef6f5; }}
        a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
        a:hover {{ text-decoration: underline; }}
        td.prompt {{ white-space: pre-wrap; }}
        td.prompt details.prompt-details {{ display: block; width: 100%; }}
        td.prompt details.prompt-details > summary {{ 
            cursor: pointer; 
            list-style: none;
            display: block;
            box-sizing: border-box;
            padding: 8px 12px;
            border-radius: 8px;
            white-space: pre-wrap;
        }}
        td.prompt details.prompt-details > summary::-webkit-details-marker {{ display: none; }}
        td.prompt details.prompt-details[open] > summary {{ background: transparent; padding: 0; margin-bottom: 0;}}
        td.prompt .prompt-show-more,
        td.prompt .prompt-show-less {{ 
                display: block;       /* Makes the button take up its own full-width line */
                text-align: right;    /* Aligns the text to the right side of that line */
                margin-top: 8px;      /* Adds a little space above the button */
                font-size: 0.85em; 
                color: var(--accent); 
                font-weight: 600; 
                cursor: pointer;
        }}

        td.prompt details.prompt-details[open] .prompt-preview {{ display: none; }}
        td.prompt details.prompt-details[open] .prompt-show-more {{ display: none; }}
        td.prompt .prompt-full {{box-sizing: border-box; padding: 8px 12px; background: var(--panel-muted); border-radius: 8px; white-space: pre-wrap; }}

        details.folder {{
            margin: 12px 0;
            padding: 10px 12px 12px;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(31, 41, 55, 0.08);
        }}
        details.folder > summary {{
            cursor: pointer;
            font-weight: 700;
            color: var(--ink);
            list-style: none;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        details.folder > summary::before {{
            content: "";
            width: 8px;
            height: 8px;
            border-right: 2px solid var(--muted);
            border-bottom: 2px solid var(--muted);
            transform: rotate(-45deg);
            transition: transform 0.2s ease;
        }}
        details.folder[open] > summary::before {{
            transform: rotate(45deg);
        }}
        details.folder[open] > summary {{ margin-bottom: 10px; }}
        details.folder details.folder {{ margin-left: 16px; border-left: 2px solid rgba(31, 41, 55, 0.08); }}
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <h1>Codex Session Overview</h1>
            <p>Click a date to open the full transcript.</p>
            <div class="search-bar">
                <div class="search-field">
                    <span class="search-icon">&#128269;</span>
                    <input id="search-box" type="search" placeholder="Search by date or prompt text...">
                </div>
            </div>
            <div id="no-results" class="no-results">No sessions match your search.</div>
            {body}
        </div>
    </div>
    <script>
        const searchBox = document.getElementById('search-box');
        const rows = Array.from(document.querySelectorAll('tr.entry-row'));
        const folders = Array.from(document.querySelectorAll('details.folder'));
        const noResults = document.getElementById('no-results');

        // --- NEW: Helper to remove existing highlights ---
        function clearHighlights(root) {{
            // Find all marks and replace them with their text content
            const marks = root.querySelectorAll('mark.highlight');
            for (const mark of marks) {{
                const parent = mark.parentNode;
                parent.replaceChild(document.createTextNode(mark.textContent), mark);
                parent.normalize(); // Merge adjacent text nodes
            }}
        }}

        // --- NEW: Helper to add highlights safely ---
        function highlightText(root, query) {{
            if (!query) return;
            
            // Escape special regex characters in the query
            const escapedQuery = query.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
            const regex = new RegExp('(' + escapedQuery + ')', 'gi');

            // TreeWalker traverses only Text Nodes, avoiding HTML tags
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
            const nodesToProcess = [];

            while (walker.nextNode()) {{
                const node = walker.currentNode;
                // Skip if parent is script/style
                if (node.parentNode.tagName === 'SCRIPT' || node.parentNode.tagName === 'STYLE') continue;
                
                if (node.nodeValue.toLowerCase().includes(query)) {{
                    nodesToProcess.push(node);
                }}
            }}

            // Replace matched text nodes with fragments containing <mark>
            for (const node of nodesToProcess) {{
                const val = node.nodeValue;
                const parent = node.parentNode;
                
                // Double check match still exists (in case of overlaps)
                if (regex.test(val)) {{
                    const fragment = document.createDocumentFragment();
                    let lastIdx = 0;
                    
                    val.replace(regex, (match, p1, offset) => {{
                        // Append text before match
                        if (offset > lastIdx) {{
                            fragment.appendChild(document.createTextNode(val.substring(lastIdx, offset)));
                        }}
                        // Append highlighted match
                        const mark = document.createElement('mark');
                        mark.className = 'highlight';
                        mark.textContent = match;
                        fragment.appendChild(mark);
                        
                        lastIdx = offset + match.length;
                        return match; // Return value not strictly needed for replace loop
                    }});
                    
                    // Append text after last match
                    if (lastIdx < val.length) {{
                        fragment.appendChild(document.createTextNode(val.substring(lastIdx)));
                    }}
                    
                    parent.replaceChild(fragment, node);
                }}
            }}
        }}

        function updateFolderVisibility(query) {{
            for (const folder of folders) {{
                folder.classList.add('hidden');
            }}

            for (const folder of [...folders].reverse()) {{
                const hasVisibleRow = folder.querySelector('tr.entry-row:not(.hidden)');
                const hasVisibleChild = folder.querySelector('details.folder:not(.hidden)');
                if (hasVisibleRow || hasVisibleChild) {{
                    folder.classList.remove('hidden');
                    if (query) {{
                        folder.open = true;
                    }}
                }}
            }}
        }}

        function applyFilter() {{
            const query = searchBox.value.trim().toLowerCase();
            
            for (const row of rows) {{
                // 1. Clean up previous highlights first
                clearHighlights(row);

                // 2. Check visibility - even the hidden full text is searched
                const text = (row.textContent + " " + (row.dataset.prompt || "")).toLowerCase();
                
                if (!query || text.includes(query)) {{
                    row.classList.remove('hidden');
                    // 3. Apply new highlights if query exists
                    if (query) {{
                        highlightText(row, query);
                    }}
                }} else {{
                    row.classList.add('hidden');
                }}
            }}
            
            updateFolderVisibility(query);
            const hasVisibleRows = document.querySelector('tr.entry-row:not(.hidden)');
            if (hasVisibleRows) {{
                noResults.classList.remove('visible');
            }} else {{
                noResults.classList.add('visible');
            }}
        }}

        searchBox.addEventListener('input', applyFilter);
    </script>
</body>
</html>
"""
