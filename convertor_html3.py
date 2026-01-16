import json
import sys
import os
import html
import re

def extract_text_content(content_data):
    """Helper to extract text from nested content structures."""
    text_parts = []
    if isinstance(content_data, list):
        for item in content_data:
            if isinstance(item, dict):
                msg_type = item.get("type")
                if msg_type in ["input_text", "output_text", "summary_text", "text"]:
                    text_parts.append(item.get("text", ""))
    elif isinstance(content_data, str):
        return content_data
    return "".join(text_parts)

def format_content(text):
    """
    Parses Markdown (Headers, Bold, Code) into HTML.
    Uses a placeholder strategy to prevent Markdown syntax inside code blocks
    from being processed incorrectly.
    """
    if not text:
        return ""

    # 1. Escape HTML first (Security & Layout safety)
    safe_text = html.escape(text)

    # Dictionary to store code blocks temporarily
    code_blocks = {}
    
    def store_code_block(match):
        key = f"__CODE_BLOCK_{len(code_blocks)}__"
        lang = match.group(1) if match.group(1) else "text"
        content = match.group(2)
        # Create the final HTML for this block
        code_html = f'<pre><code class="language-{lang}">{content}</code></pre>'
        code_blocks[key] = code_html
        return key

    # 2. Extract Code Blocks and replace with placeholders
    # Regex captures: ```(optional_lang)\n(content)```
    safe_text = re.sub(r'```(\w+)?\n?(.*?)```', store_code_block, safe_text, flags=re.DOTALL)

    # 3. Process Markdown Headers (on the text outside code blocks)
    # H1 (# ) - Mapped to H2 visually to fit message context
    safe_text = re.sub(r'(?m)^# (.*?)$', r'<h2>\1</h2>', safe_text)
    # H2 (## )
    safe_text = re.sub(r'(?m)^## (.*?)$', r'<h3>\1</h3>', safe_text)
    # H3 (### )
    safe_text = re.sub(r'(?m)^### (.*?)$', r'<h4>\1</h4>', safe_text)

    # 4. Process Bold Text (**text**)
    safe_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', safe_text)

    # 5. Process Inline Code (`text`)
    safe_text = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', safe_text)

    # 6. Restore Code Blocks
    for key, code_html in code_blocks.items():
        safe_text = safe_text.replace(key, code_html)

    return safe_text

def get_html_header():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Log</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f0f2f5; color: #333; }
        .container { background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
        
        .message { margin-bottom: 30px; padding-bottom: 30px; border-bottom: 1px solid #eee; }
        .message:last-child { border-bottom: none; }
        
        /* Roles */
        .role { font-weight: 700; margin-bottom: 10px; font-size: 1.1em; display: flex; align-items: center; gap: 8px; }
        .role.user { color: #007bff; }
        .role.assistant { color: #28a745; }
        .role.developer { color: #6c757d; }
        
        /* Content & Headers */
        .content { white-space: pre-wrap; font-family: inherit; }
        .content h2 { margin-top: 20px; margin-bottom: 10px; font-size: 1.4em; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; color: #222; }
        .content h3 { margin-top: 15px; margin-bottom: 8px; font-size: 1.2em; font-weight: 600; color: #444; }
        .content h4 { margin-top: 15px; font-size: 1.1em; font-weight: 600; color: #555; }
        
        /* Code Envelope - The "Card" Look */
        pre {
            background: #1e1e1e !important; /* Force dark background */
            color: #d4d4d4;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #333;
            overflow-x: auto;
            margin: 20px 0;
            font-size: 0.95em;
        }
        
        code { font-family: "Consolas", "Monaco", "Courier New", monospace; }
        .inline-code { background: #eef1f6; padding: 2px 6px; border-radius: 4px; color: #c7254e; font-size: 0.9em; border: 1px solid #dce2ea; }
        
        /* Reasoning */
        .reasoning { background-color: #f8f9fa; border-left: 5px solid #6c757d; padding: 15px 20px; margin: 15px 0; font-style: italic; color: #555; border-radius: 0 8px 8px 0; }
        .reasoning-title { font-weight: bold; margin-bottom: 5px; display: block; font-style: normal; text-transform: uppercase; font-size: 0.8em; color: #6c757d; }
        
        /* Truncation & Tools */
        .tool-header { font-size: 0.9em; color: #d63384; font-weight: bold; margin-bottom: 5px; }
        .truncated { color: #dc3545; font-style: italic; font-size: 0.85em; margin-top: 5px; }
    </style>
</head>
<body>
<div class="container">
    <h1 style="text-align: center; color: #333; margin-bottom: 30px;">Codex Session Transcript</h1>
    <hr style="border: 0; border-top: 1px solid #eee; margin-bottom: 30px;">
"""

def get_html_footer():
    return """
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
</body>
</html>
"""

def convert_jsonl_to_html(input_path, output_path):
    print(f"Reading from: {input_path}")
    
    if not os.path.exists(input_path):
        print(f"Error: File '{input_path}' not found.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    html_parts = [get_html_header()]
    seen_hashes = set()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        try:
            data = json.loads(line)
            msg_type = data.get("type")
            payload = data.get("payload", {})
            
            # --- HANDLE EVENTS ---
            if msg_type == "event_msg":
                event_type = payload.get("type")
                if event_type in ["agent_message", "user_message"]:
                    text = payload.get("message", "")
                    if text:
                        content_hash = hash(text)
                        if content_hash in seen_hashes: continue
                        seen_hashes.add(content_hash)
                        
                        role_class = "assistant" if event_type == "agent_message" else "user"
                        role_name = "Assistant" if event_type == "agent_message" else "User"
                        icon = "🤖" if role_class == "assistant" else "👤"
                        
                        formatted_text = format_content(text)
                        
                        html_parts.append(f"""
                        <div class="message">
                            <div class="role {role_class}">{icon} {role_name}</div>
                            <div class="content">{formatted_text}</div>
                        </div>
                        """)
                continue

            # --- HANDLE RESPONSE ITEMS ---
            if msg_type == "response_item":
                item_type = payload.get("type")
                
                # 1. Chat Messages
                if item_type == "message":
                    role = payload.get("role", "unknown").capitalize()
                    content_raw = payload.get("content")
                    text = extract_text_content(content_raw)
                    
                    if text:
                        content_hash = hash(text)
                        if content_hash in seen_hashes: continue
                        seen_hashes.add(content_hash)

                        role_lower = role.lower()
                        icon, role_cls = "❓", "unknown"
                        if role_lower == "user": icon, role_cls = "👤", "user"
                        elif role_lower in ["assistant", "model"]: icon, role_cls = "🤖", "assistant"
                        elif role_lower in ["developer", "system"]: icon, role_cls = "⚙️", "developer"

                        formatted_text = format_content(text)

                        html_parts.append(f"""
                        <div class="message">
                            <div class="role {role_cls}">{icon} {role}</div>
                            <div class="content">{formatted_text}</div>
                        </div>
                        """)

                # 2. Reasoning
                elif item_type == "reasoning":
                    summary = payload.get("summary", [])
                    text = extract_text_content(summary)
                    if text:
                        formatted_text = format_content(text)
                        html_parts.append(f"""
                        <div class="message">
                            <div class="reasoning">
                                <span class="reasoning-title">🧠 Reasoning</span>
                                {formatted_text}
                            </div>
                        </div>
                        """)

                # 3. Tool Calls
                elif item_type == "function_call":
                    tool_name = payload.get("name", "unknown_tool")
                    args = payload.get("arguments", "{}")
                    pretty_args = args
                    try:
                        if isinstance(args, str):
                            parsed = json.loads(args)
                            pretty_args = json.dumps(parsed, indent=2)
                        else:
                            pretty_args = json.dumps(args, indent=2)
                    except: pass
                    
                    safe_args = html.escape(pretty_args)

                    html_parts.append(f"""
                    <div class="message">
                        <div class="tool-header">🛠️ Tool Call: {html.escape(tool_name)}</div>
                        <pre><code class="language-json">{safe_args}</code></pre>
                    </div>
                    """)

                # 4. Tool Outputs
                elif item_type == "function_call_output":
                    output = payload.get("output", "")
                    truncated_msg = ""
                    if output and len(output) > 2000:
                        display_output = output[:2000]
                        truncated_msg = '<div class="truncated">... (output truncated)</div>'
                    else:
                        display_output = output

                    safe_output = html.escape(display_output)
                    
                    html_parts.append(f"""
                    <div class="message">
                        <div class="tool-header">Output</div>
                        <pre><code class="language-text">{safe_output}</code></pre>
                        {truncated_msg}
                    </div>
                    """)

        except json.JSONDecodeError:
            continue

    html_parts.append(get_html_footer())
    
    if len(html_parts) <= 2:
        print("No readable messages found.")
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("".join(html_parts))
        print(f"Success! HTML saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python codex_to_html_v3.py <input.jsonl> [output.html]")
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.rsplit('.', 1)[0] + ".html"
        convert_jsonl_to_html(input_file, output_file)