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
    Escapes HTML and converts Markdown code blocks to HTML code blocks 
    compatible with Prism.js for syntax highlighting.
    """
    if not text:
        return ""

    # 1. First, escape HTML to prevent XSS and rendering issues
    safe_text = html.escape(text)

    # 2. Convert Triple Backticks (Block Code)
    # Pattern: ```language\n code \n```
    # We use a regex to transform these into <pre><code class="language-xyz">...</code></pre>
    def replace_code_block(match):
        lang = match.group(1) if match.group(1) else "text"
        code_content = match.group(2)
        return f'<pre><code class="language-{lang}">{code_content}</code></pre>'

    # Regex logic: 
    # ```(\w+)? -> Optional language identifier
    # \n? -> Optional newline after fence
    # (.*?) -> The code content (lazy match)
    # ``` -> Closing fence
    safe_text = re.sub(r'```(\w+)?\n?(.*?)```', replace_code_block, safe_text, flags=re.DOTALL)

    # 3. Convert Single Backticks (Inline Code)
    safe_text = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', safe_text)

    return safe_text

def get_html_header():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Log</title>
    <link href="[https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css](https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css)" rel="stylesheet" />
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f4f4f9; color: #333; }
        .container { background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .message { margin-bottom: 30px; padding-bottom: 30px; border-bottom: 1px solid #eee; }
        .message:last-child { border-bottom: none; }
        
        /* Headers */
        .role { font-weight: bold; margin-bottom: 10px; font-size: 1.1em; display: flex; align-items: center; gap: 8px; }
        .role.user { color: #007bff; }
        .role.assistant { color: #28a745; }
        .role.developer { color: #6c757d; }
        .role.tool { color: #d63384; }
        
        /* Content Styling */
        .content { white-space: pre-wrap; font-family: inherit; }
        
        /* Inline code styling */
        .inline-code { background: #eee; padding: 2px 5px; border-radius: 4px; font-family: "Consolas", monospace; color: #d63384; }
        
        /* Tool Output Blocks */
        .tool-block { background: #2d2d2d; color: #ccc; padding: 15px; border-radius: 6px; font-size: 0.9em; overflow-x: auto; margin-top: 5px; }
        
        /* Reasoning Block */
        .reasoning { background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 15px; margin: 15px 0; font-style: italic; color: #555; }
        .reasoning-title { font-weight: bold; margin-bottom: 5px; display: block; font-style: normal; text-transform: uppercase; font-size: 0.8em; color: #6c757d; }

        /* Truncation */
        .truncated { color: #dc3545; font-style: italic; font-size: 0.85em; margin-top: 5px; }
    </style>
</head>
<body>
<div class="container">
    <h1>Codex Session Transcript</h1>
    <hr>
"""

def get_html_footer():
    # We include PrismJS at the bottom to auto-highlight code blocks
    return """
</div>
<script src="[https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js](https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js)"></script>
<script src="[https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js](https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js)"></script>
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
                        
                        # Use format_content to parse Code Blocks
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
                        # Reasoning usually doesn't have code blocks, but we format it just in case
                        formatted_text = format_content(text)
                        html_parts.append(f"""
                        <div class="message">
                            <div class="reasoning">
                                <span class="reasoning-title">🧠 Reasoning</span>
                                {formatted_text}
                            </div>
                        </div>
                        """)

                # 3. Tool Calls (Force JSON highlighting)
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
                        <div class="role tool">🛠️ Tool Call: {html.escape(tool_name)}</div>
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
                    
                    # We treat tool output as generic text/log
                    html_parts.append(f"""
                    <div class="message">
                        <div class="role tool">Output</div>
                        <pre class="tool-block"><code class="language-text">{safe_output}</code></pre>
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
        print("Usage: python codex_to_html_v2.py <input.jsonl> [output.html]")
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.rsplit('.', 1)[0] + ".html"
        convert_jsonl_to_html(input_file, output_file)