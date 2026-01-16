import json
import sys
import os
import html

def extract_text_content(content_data):
    """
    Helper to extract text from the nested content list structure.
    Handles 'input_text', 'output_text', 'summary_text', and simple strings.
    """
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

def get_html_header():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Log</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max_width: 800px; margin: 0 auto; padding: 20px; background-color: #f4f4f9; color: #333; }
        .container { background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .message { margin-bottom: 25px; padding-bottom: 25px; border-bottom: 1px solid #eee; }
        .message:last-child { border-bottom: none; }
        
        /* Headers & Roles */
        .role { font-weight: bold; margin-bottom: 8px; font-size: 1.1em; display: flex; align-items: center; gap: 8px; }
        .role.user { color: #007bff; }
        .role.assistant { color: #28a745; }
        .role.developer { color: #6c757d; }
        .role.tool { color: #d63384; }
        
        /* Content Blocks */
        .content { white-space: pre-wrap; font-family: inherit; }
        
        /* Reasoning */
        .reasoning { background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 10px 15px; margin: 10px 0; font-style: italic; color: #555; }
        .reasoning-title { font-weight: bold; margin-bottom: 5px; display: block; font-style: normal; }
        
        /* Code Blocks (Tool Calls/Outputs) */
        pre { background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 0.9em; }
        code { font-family: "Consolas", "Monaco", "Courier New", monospace; }
        
        /* Truncation warning */
        .truncated { color: #dc3545; font-style: italic; font-size: 0.9em; }
    </style>
</head>
<body>
<div class="container">
    <h1>Codex Session Transcript</h1>
    <hr>
"""

def get_html_footer():
    return """
</div>
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
            
            # --- HANDLE EVENTS (Like agent_message/user_message) ---
            if msg_type == "event_msg":
                event_type = payload.get("type")
                
                if event_type in ["agent_message", "user_message"]:
                    text = payload.get("message", "")
                    
                    if text:
                        content_hash = hash(text)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)
                        
                        role_class = "assistant" if event_type == "agent_message" else "user"
                        role_name = "Assistant" if event_type == "agent_message" else "User"
                        icon = "🤖" if role_class == "assistant" else "👤"
                        
                        safe_text = html.escape(text)
                        
                        html_parts.append(f"""
                        <div class="message">
                            <div class="role {role_class}">{icon} {role_name}</div>
                            <div class="content">{safe_text}</div>
                        </div>
                        """)
                continue

            # --- HANDLE RESPONSE ITEMS ---
            if msg_type == "response_item":
                item_type = payload.get("type")
                
                # 1. Standard Chat Messages
                if item_type == "message":
                    role = payload.get("role", "unknown").capitalize()
                    content_raw = payload.get("content")
                    text = extract_text_content(content_raw)
                    
                    if text:
                        content_hash = hash(text)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)

                        # Determine styles
                        role_lower = role.lower()
                        icon = "❓"
                        if role_lower == "user": icon, role_cls = "👤", "user"
                        elif role_lower in ["assistant", "model"]: icon, role_cls = "🤖", "assistant"
                        elif role_lower in ["developer", "system"]: icon, role_cls = "⚙️", "developer"
                        else: role_cls = "unknown"

                        safe_text = html.escape(text)

                        html_parts.append(f"""
                        <div class="message">
                            <div class="role {role_cls}">{icon} {role}</div>
                            <div class="content">{safe_text}</div>
                        </div>
                        """)

                # 2. Agent Reasoning
                elif item_type == "reasoning":
                    summary = payload.get("summary", [])
                    text = extract_text_content(summary)
                    
                    if text:
                        content_hash = hash(text)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)

                        safe_text = html.escape(text)
                        
                        html_parts.append(f"""
                        <div class="message">
                            <div class="reasoning">
                                <span class="reasoning-title">🧠 Reasoning:</span>
                                {safe_text}
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
                    except:
                        pass
                    
                    safe_args = html.escape(pretty_args)

                    html_parts.append(f"""
                    <div class="message">
                        <div class="role tool">🛠️ Tool Call: {html.escape(tool_name)}</div>
                        <pre><code>{safe_args}</code></pre>
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
                        <div class="role tool">Output</div>
                        <pre><code>{safe_output}</code></pre>
                        {truncated_msg}
                    </div>
                    """)

        except json.JSONDecodeError:
            print(f"Skipping line {i+1}: Invalid JSON")
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
        print("Usage: python codex_to_html.py <input.jsonl> [output.html]")
    else:
        input_file = sys.argv[1]
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
        else:
            output_file = input_file.rsplit('.', 1)[0] + ".html"
            
        convert_jsonl_to_html(input_file, output_file)