import json
import sys
import os
import html
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from datetime import datetime

# ==========================================
# PART 1: THE CORE CONVERTER ENGINE (Logic)
# ==========================================

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

def format_timestamp(iso_str):
    """Converts ISO 8601 timestamp to European format DD.MM.YYYY HH:MM:SS"""
    try:
        # Handle 'Z' for UTC and ensure compatibility with older Python versions
        if iso_str.endswith('Z'):
            iso_str = iso_str[:-1]
        # Truncate fractional seconds for cleaner display if present
        if '.' in iso_str:
            iso_str = iso_str.split('.')[0]
            
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return iso_str # Return original if parsing fails

def format_content(text):
    if not text: return ""
    safe_text = html.escape(text)

    # 1. Hide Code Blocks
    code_blocks = {}
    def store_code_block(match):
        key = f"__CODE_BLOCK_{len(code_blocks)}__"
        lang = match.group(1) if match.group(1) else "text"
        content = match.group(2)
        code_html = f'<pre><code class="language-{lang}">{content}</code></pre>'
        code_blocks[key] = code_html
        return key

    safe_text = re.sub(r'```(\w+)?\n?(.*?)```', store_code_block, safe_text, flags=re.DOTALL)

    # 2. COLLAPSIBLE CONTEXT LOGIC
    # Looks for "Context from my IDE setup" and captures everything until "My request for Codex"
    # Wraps it in <details> tags.
    # regex flags: DOTALL (dot matches newline) | MULTILINE (^ matches start of line)
    safe_text = re.sub(
        r'(?ms)(^#+\s*Context from my IDE setup:)\s*(.*?)(?=^#+\s*My request for Codex:)',
        r'<details><summary>Context from my IDE setup</summary>\n\2\n</details>\n',
        safe_text,
        flags=re.DOTALL | re.MULTILINE
    )

    # 3. Compact Mode & Overrides
    safe_text = re.sub(r'\n{2,}(?=#)', '\n', safe_text)
    safe_text = re.sub(r'\n{3,}', '\n\n', safe_text)
    safe_text = re.sub(r'(?m)^#+ My request for Codex:', r'<h2>👤❓ My request for Codex:</h2>', safe_text)
    
    # 4. Headers & Formatting
    safe_text = re.sub(r'(?m)^# (.*?)$', r'<h2>\1</h2>', safe_text)
    safe_text = re.sub(r'(?m)^## (.*?)$', r'<h3>\1</h3>', safe_text)
    safe_text = re.sub(r'(?m)^### (.*?)$', r'<h4>\1</h4>', safe_text)
    safe_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', safe_text)
    safe_text = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', safe_text)

    # 5. Restore Code
    for key, code_html in code_blocks.items():
        safe_text = safe_text.replace(key, code_html)

    return safe_text

def get_html_header(date_str=""):
    date_html = ""
    if date_str:
        date_html = f'<div style="text-align: center; color: #888; margin-bottom: 30px; font-size: 2.0em; font-weight: 500;">{date_str}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Codex Session Log</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; margin: 0; padding: 0; background-color: #e9ecef; color: #333; }}
        .wrapper {{ display: flex; justify-content: center; padding: 20px; }}
        .container {{ background: #fff; padding: 50px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); width: 100%; max-width: 900px; margin-left: 0; }}
        
        /* SIDEBAR */
        .sidebar {{ position: fixed; top: 20px; left: 20px; width: 200px; background: #fff; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); z-index: 1000; overflow: hidden; }}
        .sidebar-header {{ background: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #eee; cursor: move; user-select: none; }}
        .sidebar-header h3 {{ margin: 0; font-size: 1.1em; color: #333; }}
        .sidebar-content {{ padding: 15px 20px; }}
        .filter-group {{ display: flex; align-items: center; margin-bottom: 10px; cursor: pointer; }}
        .filter-group input {{ margin-right: 10px; transform: scale(1.2); cursor: pointer; }}
        
        @media (max-width: 1300px) {{
            .sidebar {{ position: static; width: 100%; margin-bottom: 20px; box-shadow: none; border: 1px solid #ddd; }}
            .sidebar-header {{ cursor: default; }}
            .wrapper {{ flex-direction: column; align-items: center; }}
        }}

        /* MESSAGES */
        .message {{ margin-bottom: 30px; padding: 30px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.05); }}
        .hidden {{ display: none !important; }}
        .message.role-user {{ background-color: #f8f9fa; border-left: 6px solid #007bff; }}
        .message.role-assistant {{ background-color: #f0f7ff; border-left: 6px solid #28a745; }}
        .message.role-developer {{ background-color: #fff4f4; border-left: 6px solid #dc3545; border: 1px dashed #eec; }}
        .message.type-tool-call {{ background-color: #fff; border-left: 6px solid #d63384; }}
        .message.type-tool-output {{ background-color: #2d2d2d; color: #ccc; border-left: 6px solid #6c757d; padding: 15px; }}
        .message.type-reasoning {{ background-color: #fff; border-left: 6px solid #6c757d; }}

        .role {{ font-size: 1.4em; font-weight: 700; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid rgba(0,0,0,0.1); display: flex; align-items: center; gap: 10px; }}
        .role-user .role {{ color: #0056b3; }}
        .role-assistant .role {{ color: #1e7e34; }}
        
        .content {{ white-space: pre-wrap; font-family: inherit; font-size: 1.05em; }}
        
        details {{
            background-color: #fff;
            border: 1px solid #dce2ea;
            border-radius: 8px;
            padding: 10px 15px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        summary {{
            cursor: pointer;
            font-weight: 600;
            color: #6c757d;
            font-size: 0.95em;
            outline: none;
            user-select: none;
        }}
        summary:hover {{ color: #333; }}
        details[open] {{ border-color: #b1b7c1; }}
        details[open] summary {{ margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 5px; color: #333; }}
        
        .content h2 {{ margin-top: 25px; margin-bottom: 15px; font-size: 1.3em; font-weight: 700; color: #222; }}
        .content h3 {{ margin-top: 15px; margin-bottom: 8px; font-size: 1.1em; font-weight: 600; color: #555; background: rgba(0,0,0,0.05); padding: 5px 12px; border-radius: 6px; display: inline-block; }}
        
        pre {{ background: #1e1e1e !important; color: #d4d4d4; padding: 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); overflow-x: auto; margin: 20px 0; font-size: 0.95em; }}
        .inline-code {{ background: #eef1f6; padding: 2px 6px; border-radius: 4px; color: #c7254e; font-size: 0.9em; border: 1px solid #dce2ea; }}
        
        .reasoning-content {{ font-style: italic; color: #555; }}
        .reasoning-title {{ font-weight: bold; margin-bottom: 5px; display: block; font-style: normal; text-transform: uppercase; font-size: 0.8em; color: #6c757d; }}
        .tool-header {{ font-size: 0.9em; color: #d63384; font-weight: bold; margin-bottom: 5px; }}
        .truncated {{ color: #dc3545; font-style: italic; font-size: 0.85em; margin-top: 5px; }}
    </style>
</head>
<body>

<div class="sidebar" id="draggable-sidebar">
    <div class="sidebar-header" id="sidebar-handle"><h3>🔍 Filters</h3></div>
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
    <h1 style="text-align: center; color: #333; margin-bottom: 10px;">Codex Session Transcript</h1>
    {date_html}
"""

def get_html_footer():
    return """
</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
<script>
    const filters = {'check-user':'role-user','check-assistant':'role-assistant','check-developer':'role-developer','check-reasoning':'type-reasoning','check-tools':'type-tool-call','check-tool-output':'type-tool-output'};
    function applyFilters(){ for(const[id,cls] of Object.entries(filters)){ const cb=document.getElementById(id); const els=document.getElementsByClassName(cls); for(let el of els){ if(cb.checked) el.classList.remove('hidden'); else el.classList.add('hidden'); } } }
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

def get_session_date(lines):
    """Finds the first valid timestamp in the lines."""
    for line in lines:
        try:
            data = json.loads(line)
            # Check root timestamp
            if "timestamp" in data:
                return format_timestamp(data["timestamp"])
            # Check payload timestamp if root is missing
            if "payload" in data and "timestamp" in data["payload"]:
                return format_timestamp(data["payload"]["timestamp"])
        except:
            continue
    return ""

def convert_single_file(input_path):
    output_path = os.path.splitext(input_path)[0] + ".html"
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Extract Date
        session_date = get_session_date(lines)
        html_parts = [get_html_header(session_date)]
        seen_hashes = set()
        count = 0

        for line in lines:
            line = line.strip()
            if not line: continue
            try:
                data = json.loads(line)
                msg_type = data.get("type")
                payload = data.get("payload", {})
                
                html_block = ""
                css_class = ""

                # --- 1. EVENTS ---
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
                            html_block = f'<div class="message {css_class}"><div class="role">{icon} {role}</div><div class="content">{format_content(text)}</div></div>'

                # --- 2. RESPONSE ITEMS ---
                elif msg_type == "response_item":
                    item_type = payload.get("type")
                    if item_type == "message":
                        role = payload.get("role", "unknown").capitalize()
                        text = extract_text_content(payload.get("content"))
                        if text:
                            if hash(text) in seen_hashes: continue
                            seen_hashes.add(hash(text))
                            role_l = role.lower()
                            if role_l == "user": css, ic = "role-user", "👤"
                            elif role_l in ["assistant","model"]: css, ic = "role-assistant", "🤖"
                            else: css, ic = "role-developer", "⚙️"
                            html_block = f'<div class="message {css}"><div class="role">{ic} {role}</div><div class="content">{format_content(text)}</div></div>'
                    
                    elif item_type == "reasoning":
                        text = extract_text_content(payload.get("summary", []))
                        if text:
                            html_block = f'<div class="message type-reasoning"><span class="reasoning-title">🧠 Reasoning</span><div class="reasoning-content">{format_content(text)}</div></div>'

                    # STANDARD TOOL CALL
                    elif item_type == "function_call":
                        tool = payload.get("name", "unknown")
                        args = payload.get("arguments", "{}")
                        try: pretty = json.dumps(json.loads(args) if isinstance(args, str) else args, indent=2)
                        except: pretty = str(args)
                        html_block = f'<div class="message type-tool-call"><div class="tool-header">🛠️ Tool Call: {html.escape(tool)}</div><pre><code class="language-json">{html.escape(pretty)}</code></pre></div>'

                    # CUSTOM TOOL CALL (e.g. PATCH)
                    elif item_type == "custom_tool_call":
                        tool = payload.get("name", "unknown")
                        inp = payload.get("input", "")
                        html_block = f'<div class="message type-tool-call"><div class="tool-header">🛠️ Tool Call: {html.escape(tool)}</div><pre><code class="language-diff">{html.escape(inp)}</code></pre></div>'

                    elif item_type == "function_call_output":
                        out = payload.get("output", "")
                        trun = ""
                        if out and len(out) > 2000:
                            out = out[:2000]
                            trun = '<div class="truncated">... (truncated)</div>'
                        html_block = f'<div class="message type-tool-output"><div class="tool-header">Output</div><pre><code class="language-text">{html.escape(out)}</code></pre>{trun}</div>'

                if html_block:
                    html_parts.append(html_block)
                    count += 1
            except: continue

        html_parts.append(get_html_footer())
        
        if count == 0:
            return False, "Empty/Invalid Log"
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("".join(html_parts))
        return True, "Done"
        
    except Exception as e:
        return False, str(e)


# ==========================================
# PART 2: THE GUI (BATCH PROCESSING)
# ==========================================

class BatchConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Codex Batch Converter")
        self.root.geometry("700x500")
        
        # Variables
        self.folder_path = tk.StringVar()
        self.file_items = []  # Stores (filename, fullpath, item_id)

        # Top Section
        top_frame = ttk.Frame(root, padding="10")
        top_frame.pack(fill=tk.X)
        ttk.Label(top_frame, text="Log Folder:").pack(side=tk.LEFT)
        ttk.Entry(top_frame, textvariable=self.folder_path, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(top_frame, text="Browse...", command=self.browse_folder).pack(side=tk.LEFT)

        # Middle Section (List)
        list_frame = ttk.Frame(root, padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)
        # Treeview setup
        columns = ("filename", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        # Headers
        self.tree.heading("filename", text="File Name", anchor="w")
        self.tree.heading("status", text="Status", anchor="w")
        # Column Config
        self.tree.column("filename", width=400)
        self.tree.column("status", width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double click to toggle check
        self.tree.bind("<Double-1>", self.toggle_check)
        self.tree.bind("<space>", self.toggle_check)

        # Bottom Section
        btn_frame = ttk.Frame(root, padding="10")
        btn_frame.pack(fill=tk.X)
        self.chk_all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_frame, text="Select All", variable=self.chk_all_var, command=self.toggle_all).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Start Conversion", command=self.start_batch).pack(side=tk.RIGHT)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.load_files(folder)

    def load_files(self, folder):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.file_items = []
        if not os.path.exists(folder): return

        for f in os.listdir(folder):
            if f.lower().endswith(".jsonl"):
                full_path = os.path.join(folder, f)
                item_id = self.tree.insert("", "end", values=(f"☑  {f}", "Waiting..."))
                self.file_items.append({"checked": True, "name": f, "path": full_path, "id": item_id})

    def toggle_check(self, event=None):
        selected_id = self.tree.focus()
        if not selected_id: return
        item_data = next((x for x in self.file_items if x["id"] == selected_id), None)
        if item_data:
            item_data["checked"] = not item_data["checked"]
            icon = "☑" if item_data["checked"] else "☐"
            name = item_data["name"]
            current_status = self.tree.item(selected_id, "values")[1]
            self.tree.item(selected_id, values=(f"{icon}  {name}", current_status))

    def toggle_all(self):
        state = self.chk_all_var.get()
        icon = "☑" if state else "☐"
        for item in self.file_items:
            item["checked"] = state
            current_status = self.tree.item(item["id"], "values")[1]
            self.tree.item(item["id"], values=(f"{icon}  {item['name']}", current_status))

    def start_batch(self):
        to_process = [x for x in self.file_items if x["checked"]]
        if not to_process:
            messagebox.showwarning("No Files", "No files selected for conversion.")
            return
        threading.Thread(target=self.process_files, args=(to_process,)).start()

    def process_files(self, files):
        for item in files:
            self.update_status(item["id"], "Converting...")
            success, msg = convert_single_file(item["path"])
            final_status = "✅ Done" if success else "❌ Error"
            self.update_status(item["id"], final_status)
        messagebox.showinfo("Batch Complete", f"Finished processing {len(files)} files.")

    def update_status(self, item_id, status_text):
        try:
            current_vals = self.tree.item(item_id, "values")
            self.tree.item(item_id, values=(current_vals[0], status_text))
        except: pass

def create_gui():
    root = tk.Tk()
    app = BatchConverterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    create_gui()