import json
import sys
import os
import html
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --- LOGIC: TEXT EXTRACTION & FORMATTING ---

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
    if not text:
        return ""

    safe_text = html.escape(text)

    code_blocks = {}
    
    def store_code_block(match):
        key = f"__CODE_BLOCK_{len(code_blocks)}__"
        lang = match.group(1) if match.group(1) else "text"
        content = match.group(2)
        code_html = f'<pre><code class="language-{lang}">{content}</code></pre>'
        code_blocks[key] = code_html
        return key

    safe_text = re.sub(r'```(\w+)?\n?(.*?)```', store_code_block, safe_text, flags=re.DOTALL)
    safe_text = re.sub(r'\n{2,}(?=#)', '\n', safe_text)
    safe_text = re.sub(r'\n{3,}', '\n\n', safe_text)
    safe_text = re.sub(r'(?m)^#+ My request for Codex:', r'<h2>👤❓ My request for Codex:</h2>', safe_text)
    safe_text = re.sub(r'(?m)^# (.*?)$', r'<h2>\1</h2>', safe_text)
    safe_text = re.sub(r'(?m)^## (.*?)$', r'<h3>\1</h3>', safe_text)
    safe_text = re.sub(r'(?m)^### (.*?)$', r'<h4>\1</h4>', safe_text)
    safe_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', safe_text)
    safe_text = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', safe_text)

    for key, code_html in code_blocks.items():
        safe_text = safe_text.replace(key, code_html)

    return safe_text

# --- LOGIC: HTML GENERATION ---

def get_html_header():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Log</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; margin: 0; padding: 0; background-color: #e9ecef; color: #333; }
        
        .wrapper { display: flex; justify-content: center; padding: 20px; }
        .container { background: #fff; padding: 50px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); width: 100%; max-width: 900px; margin-left: 0; }
        
        /* SIDEBAR (Draggable) */
        .sidebar {
            position: fixed;
            top: 20px;
            left: 20px;
            width: 200px;
            background: #fff;
            padding: 0; /* Padding moved to inner elements */
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            z-index: 1000;
            overflow: hidden; /* Keeps border-radius clean */
        }
        
        /* The Drag Handle (Header) */
        .sidebar-header {
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            cursor: move; /* Shows the 'move' cursor */
            user-select: none; /* Prevents text highlighting while dragging */
        }
        .sidebar-header h3 { margin: 0; font-size: 1.1em; color: #333; }
        
        .sidebar-content { padding: 15px 20px; }
        
        .filter-group { display: flex; align-items: center; margin-bottom: 10px; cursor: pointer; }
        .filter-group input { margin-right: 10px; cursor: pointer; transform: scale(1.2); }
        .filter-group label { cursor: pointer; font-size: 0.95em; }

        /* Responsive: On small screens, reset to static */
        @media (max-width: 1300px) {
            .sidebar { position: static; width: 100%; margin-bottom: 20px; box-shadow: none; border: 1px solid #ddd; }
            .sidebar-header { cursor: default; }
            .wrapper { flex-direction: column; align-items: center; }
        }

        /* MESSAGES & ROLES */
        .message { margin-bottom: 30px; padding: 30px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.05); }
        .hidden { display: none !important; }

        .message.role-user { background-color: #f8f9fa; border-left: 6px solid #007bff; }
        .message.role-assistant { background-color: #f0f7ff; border-left: 6px solid #28a745; }
        .message.role-developer { background-color: #fff4f4; border-left: 6px solid #dc3545; border: 1px dashed #eec; }
        .message.type-tool-call { background-color: #fff; border-left: 6px solid #d63384; }
        .message.type-tool-output { background-color: #2d2d2d; color: #ccc; border-left: 6px solid #6c757d; padding: 15px; }
        .message.type-reasoning { background-color: #fff; border-left: 6px solid #6c757d; }

        .role { font-size: 1.4em; font-weight: 700; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid rgba(0,0,0,0.1); display: flex; align-items: center; gap: 10px; }
        .role-user .role { color: #0056b3; }
        .role-assistant .role { color: #1e7e34; }
        
        .content { white-space: pre-wrap; font-family: inherit; font-size: 1.05em; }
        .content h2 { margin-top: 25px; margin-bottom: 15px; font-size: 1.3em; font-weight: 700; color: #222; }
        .content h3 { margin-top: 15px; margin-bottom: 8px; font-size: 1.1em; font-weight: 600; color: #555; background: rgba(0,0,0,0.05); padding: 5px 12px; border-radius: 6px; display: inline-block; }
        .content h4 { margin-top: 10px; font-size: 1em; font-weight: 600; color: #666; }
        
        pre { background: #1e1e1e !important; color: #d4d4d4; padding: 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); overflow-x: auto; margin: 20px 0; font-size: 0.95em; }
        code { font-family: "Consolas", "Monaco", "Courier New", monospace; }
        .inline-code { background: #eef1f6; padding: 2px 6px; border-radius: 4px; color: #c7254e; font-size: 0.9em; border: 1px solid #dce2ea; }
        
        .reasoning-content { font-style: italic; color: #555; }
        .reasoning-title { font-weight: bold; margin-bottom: 5px; display: block; font-style: normal; text-transform: uppercase; font-size: 0.8em; color: #6c757d; }
        
        .tool-header { font-size: 0.9em; color: #d63384; font-weight: bold; margin-bottom: 5px; }
        .truncated { color: #dc3545; font-style: italic; font-size: 0.85em; margin-top: 5px; }
    </style>
</head>
<body>

<div class="sidebar" id="draggable-sidebar">
    <div class="sidebar-header" id="sidebar-handle">
        <h3>🔍 Filters</h3>
    </div>
    <div class="sidebar-content">
        <div class="filter-group"><input type="checkbox" id="check-user" checked><label for="check-user">User</label></div>
        <div class="filter-group"><input type="checkbox" id="check-assistant" checked><label for="check-assistant">Assistant</label></div>
        <div class="filter-group"><input type="checkbox" id="check-reasoning" checked><label for="check-reasoning">Reasoning</label></div>
        <div class="filter-group"><input type="checkbox" id="check-tools" checked><label for="check-tools">Tool Calls</label></div>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <div class="filter-group"><input type="checkbox" id="check-developer"><label for="check-developer">Developer / System</label></div>
        <div class="filter-group"><input type="checkbox" id="check-tool-output"><label for="check-tool-output">Tool Outputs</label></div>
    </div>
</div>

<div class="wrapper">
<div class="container">
    <h1 style="text-align: center; color: #333; margin-bottom: 40px;">Codex Session Transcript</h1>
"""

def get_html_footer():
    return """
</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>

<script>
    // --- 1. FILTER LOGIC ---
    const filters = {
        'check-user': 'role-user',
        'check-assistant': 'role-assistant',
        'check-developer': 'role-developer',
        'check-reasoning': 'type-reasoning',
        'check-tools': 'type-tool-call',
        'check-tool-output': 'type-tool-output'
    };

    function applyFilters() {
        for (const [id, className] of Object.entries(filters)) {
            const checkbox = document.getElementById(id);
            const elements = document.getElementsByClassName(className);
            for (let el of elements) {
                if (checkbox.checked) {
                    el.classList.remove('hidden');
                } else {
                    el.classList.add('hidden');
                }
            }
        }
    }

    for (const id in filters) {
        document.getElementById(id).addEventListener('change', applyFilters);
    }
    applyFilters();

    // --- 2. DRAG & DROP LOGIC ---
    const sidebar = document.getElementById('draggable-sidebar');
    const handle = document.getElementById('sidebar-handle');
    let isDragging = false;
    let startX, startY, initialLeft, initialTop;

    handle.addEventListener('mousedown', (e) => {
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        
        const rect = sidebar.getBoundingClientRect();
        initialLeft = rect.left;
        initialTop = rect.top;
        
        // Prevent selection issues
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        
        sidebar.style.left = `${initialLeft + dx}px`;
        sidebar.style.top = `${initialTop + dy}px`;
    });

    document.addEventListener('mouseup', () => {
        isDragging = false;
    });
</script>
</body>
</html>
"""

def convert_jsonl_to_html(input_path, output_path):
    if not os.path.exists(input_path):
        return False, "Input file not found."

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    html_parts = [get_html_header()]
    seen_hashes = set()
    message_count = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if not line: continue
            
        try:
            data = json.loads(line)
            msg_type = data.get("type")
            payload = data.get("payload", {})
            
            html_block = ""
            css_class = ""

            # EVENTS
            if msg_type == "event_msg":
                event_type = payload.get("type")
                if event_type in ["agent_message", "user_message"]:
                    text = payload.get("message", "")
                    if text:
                        if hash(text) in seen_hashes: continue
                        seen_hashes.add(hash(text))
                        
                        role = "Assistant" if event_type == "agent_message" else "User"
                        css_class = "role-assistant" if role == "Assistant" else "role-user"
                        icon = "🤖" if role == "Assistant" else "👤"
                        
                        formatted = format_content(text)
                        html_block = f"""
                        <div class="message {css_class}">
                            <div class="role">{icon} {role}</div>
                            <div class="content">{formatted}</div>
                        </div>"""

            # RESPONSE ITEMS
            elif msg_type == "response_item":
                item_type = payload.get("type")
                
                if item_type == "message":
                    role = payload.get("role", "unknown").capitalize()
                    text = extract_text_content(payload.get("content"))
                    if text:
                        if hash(text) in seen_hashes: continue
                        seen_hashes.add(hash(text))
                        role_lower = role.lower()
                        if role_lower == "user": css_class, icon = "role-user", "👤"
                        elif role_lower in ["assistant", "model"]: css_class, icon = "role-assistant", "🤖"
                        else: css_class, icon = "role-developer", "⚙️"
                        formatted = format_content(text)
                        html_block = f"""
                        <div class="message {css_class}">
                            <div class="role">{icon} {role}</div>
                            <div class="content">{formatted}</div>
                        </div>"""

                elif item_type == "reasoning":
                    text = extract_text_content(payload.get("summary", []))
                    if text:
                        formatted = format_content(text)
                        html_block = f"""
                        <div class="message type-reasoning">
                            <span class="reasoning-title">🧠 Reasoning</span>
                            <div class="reasoning-content">{formatted}</div>
                        </div>"""

                elif item_type == "function_call":
                    tool_name = payload.get("name", "unknown")
                    args = payload.get("arguments", "{}")
                    try: pretty = json.dumps(json.loads(args) if isinstance(args, str) else args, indent=2)
                    except: pretty = str(args)
                    html_block = f"""
                    <div class="message type-tool-call">
                        <div class="tool-header">🛠️ Tool Call: {html.escape(tool_name)}</div>
                        <pre><code class="language-json">{html.escape(pretty)}</code></pre>
                    </div>"""

                elif item_type == "function_call_output":
                    output = payload.get("output", "")
                    trunc_msg = ""
                    if output and len(output) > 2000:
                        output = output[:2000]
                        trunc_msg = '<div class="truncated">... (truncated)</div>'
                    html_block = f"""
                    <div class="message type-tool-output">
                        <div class="tool-header">Output</div>
                        <pre><code class="language-text">{html.escape(output)}</code></pre>
                        {trunc_msg}
                    </div>"""

            if html_block:
                html_parts.append(html_block)
                message_count += 1

        except json.JSONDecodeError:
            continue

    html_parts.append(get_html_footer())
    
    if message_count == 0:
        return False, "No readable messages found in file."
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("".join(html_parts))
        return True, f"Success! HTML saved to:\n{output_path}"
    except Exception as e:
        return False, str(e)

# --- GUI SECTION ---

def create_gui():
    root = tk.Tk()
    root.title("Codex Log Converter")
    root.geometry("500x250")
    root.resizable(False, False)

    style = ttk.Style()
    style.configure("TButton", padding=6, font=('Helvetica', 10))
    style.configure("TLabel", font=('Helvetica', 10))

    input_path_var = tk.StringVar()
    output_path_var = tk.StringVar()

    def select_input():
        path = filedialog.askopenfilename(filetypes=[("JSONL Files", "*.jsonl"), ("All Files", "*.*")])
        if path:
            input_path_var.set(path)
            if not output_path_var.get():
                output_path_var.set(os.path.splitext(path)[0] + ".html")

    def select_output():
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML Files", "*.html")])
        if path:
            output_path_var.set(path)

    def run_conversion():
        inp = input_path_var.get()
        out = output_path_var.get()
        
        if not inp or not out:
            messagebox.showwarning("Missing Info", "Please select both input and output files.")
            return
            
        success, msg = convert_jsonl_to_html(inp, out)
        if success:
            messagebox.showinfo("Done", msg)
        else:
            messagebox.showerror("Error", msg)

    frame = ttk.Frame(root, padding="20")
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text="Input Log (.jsonl):").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=input_path_var, width=40).grid(row=1, column=0, padx=5)
    ttk.Button(frame, text="Browse...", command=select_input).grid(row=1, column=1)

    ttk.Label(frame, text="Output HTML:").grid(row=2, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=output_path_var, width=40).grid(row=3, column=0, padx=5)
    ttk.Button(frame, text="Browse...", command=select_output).grid(row=3, column=1)

    ttk.Button(frame, text="CONVERT TO HTML", command=run_conversion).grid(row=4, column=0, columnspan=2, pady=30, sticky="ew")

    root.mainloop()

if __name__ == "__main__":
    create_gui()