"""
Convert Codex JSONL logs to a styled HTML transcript.

This script provides a core conversion engine and a Tkinter GUI that supports
batch conversion of JSONL log files into a readable HTML format.
The script preserves the original JSONL order.

Log structure notes:
- "event_msg" entries in the log are what the user sees as chat-style messages (user/assistant), 
    ("token_count" message is ignored, and "agent_reasoning" is dealth with in the section "response_item"

- "response_item" entries seem to represent the actual history passed back and forth to the LLM. Below are its subcategories:
    
    "type":"message": Chat messages with extra context (compared to event_msg).

        "role":"user": Input into AI from user's side.

        "role":"assistant": Output from LLM.

        "role":"developer": System instructions that define how the AI behaves.

    "type":"function_call": The model deciding to use a tool (e.g., shell_command, or our list_mcp_resources). It shows the arguments the AI generated.

    "function_call_output": The result returned by the tool (e.g., the result of a shell command or database query).

    "type":"reasoning": The internal "Chain of Thought" summary used by the model.

- ("token_count" tell us the tokens statistics) => IGNORED

"""

import html
import json
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback

from convertor_html_rendering import (
    ICON_ASSISTANT,
    ICON_GEAR,
    ICON_USER,
    _build_event_message,
    _build_index_html,
    _build_response_item,
    get_html_footer,
    get_html_header,
)

DATE_FORMAT = "%d.%m.%Y %H:%M:%S"
APP_ICON_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAYElEQVR4nGNgwAMCTpz4D8"
    "L41OAFJBng5ub2nxSM1YClq9YThYk2AOYFggbAnEWKC1AMgQnCFIiIiIAxLj5MLU4DiHEB"
    "dQ2gOAzQYwHEtrGxQcHo8vRJByQbQFFSHjAAABG9kLrPW+PgAAAAAElFTkSuQmCC"
)

REQUEST_SECTION_PATTERN = re.compile(
    r"(?ms)^#+\s*My request for Codex:?\s*(.*?)(?=^#+\s|\Z)"
)

# ==========================================
# PART 1: THE CORE CONVERTER ENGINE (Logic)
# ==========================================


def _normalize_iso_timestamp(iso_str: str) -> str:
    """Normalize ISO timestamps by removing UTC suffix and fractional seconds."""
    if not isinstance(iso_str, str):
        return ""
    normalized = iso_str.rstrip("Z")                # Getting rid of the 'Zulu' = 'UTC' designation
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]    # Getting rid of miliseconds - no value for the user
    return normalized


def _parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    """Parse an ISO timestamp string into a datetime object."""
    normalized = _normalize_iso_timestamp(iso_str)
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)  # Converts str into a Python object that represents a specific point in time
    except ValueError:
        return None


def format_timestamp(iso_str: Any) -> Any:
    """Convert an ISO 8601 timestamp to DD.MM.YYYY HH:MM:SS.

    Args:
        iso_str: Timestamp string, optionally with a trailing "Z" or
            fractional seconds.

    Returns:
        Formatted timestamp, or the original string on parse errors.
    """
    if not isinstance(iso_str, str):
        return iso_str
    dt = _parse_iso_datetime(iso_str)
    return dt.strftime(DATE_FORMAT) if dt else iso_str


def get_session_date(lines: Iterable[str]) -> str:
    """Extract the first available timestamp from JSONL lines.

    Args:
        lines: Iterable of JSONL strings.

    Returns:
        Formatted timestamp string or an empty string if none is found.
    """
    for line in lines:
        data = _parse_json_line(line)
        if not data:
            continue
        if "timestamp" in data:
            return format_timestamp(data["timestamp"])
        payload = data.get("payload", {})
        if isinstance(payload, dict) and "timestamp" in payload:
            return format_timestamp(payload["timestamp"])
    return ""


def _parse_json_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a JSONL line into a dict; return None on errors."""
    try:
        return json.loads(line)
    except Exception:
        return None


def _path_to_href(path: str) -> str:
    """
    Convert a file system path into a relative URL.
    
    On Windows, os.sep is \\. On Linux/Mac, it is /.
    We need to ensure everything is a forward slash for HTML.
    """
    return path.replace(os.sep, "/")


def _get_session_timestamp(lines: Iterable[str]) -> Optional[datetime]:
    """Return the first valid timestamp parsed from JSONL lines."""
    for line in lines:
        data = _parse_json_line(line)
        if not data:
            continue
        if "timestamp" in data:
            ts = _parse_iso_datetime(data["timestamp"])
            if ts:
                return ts
        payload = data.get("payload", {})
        if isinstance(payload, dict) and "timestamp" in payload:
            ts = _parse_iso_datetime(payload["timestamp"])
            if ts:
                return ts
    return None


def _get_first_prompt(lines: Iterable[str]) -> str:
    """Extract the first user prompt from the JSONL stream."""
    for line in lines:
        data = _parse_json_line(line)
        if not data:
            continue
        msg_type = data.get("type")
        payload = data.get("payload", {})

        if msg_type == "event_msg" and payload.get("type") == "user_message":
            text = payload.get("message", "")
            if text:
                return _extract_user_request_from_context(text)
    return ""


def _extract_user_request_from_context(text: str) -> str:
    """Strip IDE context blocks and return the user's request text."""
    if "Context from my IDE setup" not in text:
        return text
    match = REQUEST_SECTION_PATTERN.search(text)
    if not match:
        return text
    return match.group(1).strip()

def _collect_index_entries(input_folder: str, output_folder: str) -> List[Dict[str, Any]]:
    """Collect index entries for converted sessions under the output folder."""
    entries = []
    for dirpath, _, filenames in os.walk(input_folder):
        for filename in filenames:
            if not filename.lower().endswith(".jsonl"):
                continue
            input_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(input_path, input_folder)
            rel_base, _ = os.path.splitext(rel_path)
            output_path = os.path.join(output_folder, "converted_sessions", rel_base + ".html")
            if not os.path.exists(output_path):
                continue
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                continue

            date_display = get_session_date(lines)
            timestamp = _get_session_timestamp(lines)
            prompt = _get_first_prompt(lines)
            href = _path_to_href(os.path.relpath(output_path, output_folder))
            entries.append({
                "date": date_display or "Unknown",
                "prompt": prompt,
                "href": href,
                "timestamp": timestamp,
                "file": rel_path,
                "rel_path": rel_path,
            })

    entries.sort(key=lambda e: e["rel_path"])
    entries.sort(key=lambda e: e["timestamp"] or datetime.min, reverse=True)
    return entries

def write_index_html_for_folder(input_folder: str, output_folder: str) -> str:
    """Write the overview HTML file for a folder and return its path."""

    os.makedirs(output_folder, exist_ok=True)
    entries = _collect_index_entries(input_folder, output_folder)
    html_content = _build_index_html(entries)
    output_path = os.path.join(output_folder, "codex_sessions_overview.html")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return output_path

def convert_single_file(
    input_path: str,
    output_folder: Optional[str] = None,
    input_root: Optional[str] = None,
) -> Tuple[bool, str]:
    """Convert a single JSONL log file into an HTML transcript.

    Args:
        input_path: Path to the JSONL input file.
        output_folder: Destination folder for output files. Defaults to the input file's folder.
        input_root: Root folder used to mirror input structure. Defaults to the input file's folder.

    Returns:
        Tuple (success, message). On success, the output HTML is written under the output folder in the converted_sessions subfolder.
    """
    # 1. Path Setup
    output_folder = output_folder or os.path.dirname(input_path)
    input_root = input_root or os.path.dirname(input_path)
    
    rel_path = os.path.relpath(input_path, input_root)
    rel_base, _ = os.path.splitext(rel_path)
    
    output_path = os.path.join(output_folder, "converted_sessions", rel_base + ".html")
    output_dir = os.path.dirname(output_path)

    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Performance Note: readlines() loads the whole file into RAM, but the logs are not that large that it should cause problem
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        session_date = get_session_date(lines)
        
        overview_rel_path = os.path.relpath(
            os.path.join(output_folder, "codex_sessions_overview.html"), 
            output_dir
        )
        index_href = _path_to_href(overview_rel_path)  # Create hypertext reference back to Overview file

        # 3. Initialize State
        html_parts = [get_html_header(session_date, index_href=index_href)]
        
        processed_user_messages: Set[int]      = set()  # hashes of user chat text messages
        processed_user_events: Set[int]        = set()  # hashes of user chat events (contains additional context apart from the user's prompt)
        processed_assistant_messages: Set[int] = set()  # hashes of all assistant text
        processed_events_other: Set[int]       = set()  # hashes of Tool/Dev

        # 4. Configuration Map
        # Structure: Key -> (Display Name, CSS Class, Icon, Hash Set)
        processing_map: Dict[str, Tuple[str, str, str, Set[int]]] = {
            # --- Event Messages (Key = 'type') ---
            "user_message":  ("User",      "role-user-chat", ICON_USER,      processed_user_messages),
            "agent_message": ("Assistant", "role-assistant", ICON_ASSISTANT, processed_assistant_messages),

            # --- Response Items (Key = 'role') ---
            "user":          ("User",      "role-user-log",  ICON_USER,      processed_user_events),
            "assistant":     ("Assistant", "role-assistant", ICON_ASSISTANT, processed_assistant_messages),
            
            # --- Fallbacks ---
            "developer":     ("Developer", "role-developer", ICON_GEAR,      processed_events_other),
            "default":       ("Developer", "role-developer", ICON_GEAR,      processed_events_other),
        }

        rendered_message_count = 0

        # 5. Main Loop
        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                data = _parse_json_line(line)
                if data is None:
                    continue
                
                msg_type = data.get("type")
                payload = data.get("payload", {})
                html_block = ""

                # Dispatch logic
                if msg_type == "event_msg":
                    html_block = _build_event_message(payload, processing_map)
                elif msg_type == "response_item":
                    html_block = _build_response_item(payload, processing_map)

                if html_block:
                    html_parts.append(html_block)
                    rendered_message_count += 1

            except Exception as e:
                # 6. Error Handling: Log to console AND inject into HTML
                print(f"Error on line: {line[:100]}...")
                traceback.print_exc()
                
                error_html = (
                    f'<div style="border: 2px solid #ef4444; background: #fef2f2; color: #b91c1c; '
                    f'padding: 12px; margin: 16px 0; border-radius: 8px; font-family: monospace;">'
                    f'<strong>Conversion Error:</strong> {html.escape(str(e))}'
                    f'</div>'
                )
                html_parts.append(error_html)
                continue

        # 7. Finalization
        html_parts.append(get_html_footer())

        if rendered_message_count == 0:
            return False, "Empty/Invalid Log"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("".join(html_parts))

        write_index_html_for_folder(input_root, output_folder)
        return True, "Done"

    except Exception as e:
        return False, str(e)


# =================
# PART 2: THE GUI
# =================


class BatchConverterGUI:
    """Tkinter GUI for batch conversion of JSONL log files."""
    def __init__(self, root: tk.Tk) -> None:
        """Initialize the main window, layout, and widgets."""
        self.root = root
        self.root.title("Codex Batch Converter")
        self.root.geometry("700x500")
        self.root.minsize(600, 400)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        self.folder_path = tk.StringVar()
        self.output_folder_path = tk.StringVar()
        self.output_folder_custom = False
        self.tree_items: Dict[str, Dict[str, Any]] = {}

        top_frame = ttk.Frame(root, padding="10")
        top_frame.grid(row=0, column=0, sticky="ew")
        ttk.Label(top_frame, text="Log Folder:", width=15, anchor="w").pack(side=tk.LEFT)
        self.folder_entry = ttk.Entry(top_frame, textvariable=self.folder_path, width=50)
        self.folder_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.folder_entry.bind("<FocusOut>", self.on_log_folder_change)
        self.folder_entry.bind("<Return>", self.on_log_folder_change)
        ttk.Button(top_frame, text="Browse...", command=self.browse_folder).pack(side=tk.LEFT)

        output_frame = ttk.Frame(root, padding="10")
        output_frame.grid(row=1, column=0, sticky="ew")
        ttk.Label(output_frame, text="Output Folder:", width=15, anchor="w").pack(side=tk.LEFT)
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_folder_path, width=50)
        self.output_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.output_entry.bind("<FocusOut>", self.on_output_folder_change)
        self.output_entry.bind("<Return>", self.on_output_folder_change)
        ttk.Button(output_frame, text="Browse...", command=self.browse_output_folder).pack(side=tk.LEFT)

        list_frame = ttk.Frame(root, padding="10")
        list_frame.grid(row=2, column=0, sticky="nsew")
        columns = ("status",)
        self.tree = ttk.Treeview(list_frame, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Name", anchor="w")
        self.tree.heading("status", text="Status", anchor="w")
        self.tree.column("#0", width=400)
        self.tree.column("status", width=120, anchor="w", stretch=False)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self.toggle_check)
        self.tree.bind("<space>", self.toggle_check)

        btn_frame = ttk.Frame(root, padding="10")
        btn_frame.grid(row=3, column=0, sticky="ew")
        self.chk_all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_frame, text="Select All", variable=self.chk_all_var, command=self.toggle_all).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Start Conversion", command=self.start_batch).pack(side=tk.RIGHT)

    def browse_folder(self) -> None:
        """Prompt for a folder and load its JSONL files into the list."""
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            if not self.output_folder_custom:
                self.output_folder_path.set(folder)
            self.load_files(folder)

    def on_log_folder_change(self, event: Optional[tk.Event] = None) -> None:
        """Handle manual edits to the log folder entry."""
        folder = self.folder_path.get().strip()
        if not folder or not os.path.exists(folder):
            return
        if not self.output_folder_custom:
            self.output_folder_path.set(folder)
        self.load_files(folder)

    def browse_output_folder(self) -> None:
        """Prompt for an output folder."""
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder_path.set(folder)
            self.output_folder_custom = True

    def on_output_folder_change(self, event: Optional[tk.Event] = None) -> None:
        """Handle manual edits to the output folder entry."""
        folder = self.output_folder_path.get().strip()
        if folder:
            self.output_folder_custom = True

    def _find_jsonl_files(self, folder: str) -> List[str]:
        """Find JSONL files under a folder (recursive)."""
        results = []
        for dirpath, _, filenames in os.walk(folder):
            for filename in filenames:
                if filename.lower().endswith(".jsonl"):
                    results.append(os.path.join(dirpath, filename))
        return sorted(results)

    def _format_item_label(self, name: str, state: str) -> str:
        """Format a tree label with a selection checkbox marker."""
        if state == "checked":
            box = "[x]"
        elif state == "partial":
            box = "[-]"
        else:
            box = "[ ]"
        return f"{box}  {name}"

    def _update_item_label(self, item_id: str) -> None:
        """Refresh the label and status for a tree item."""
        item = self.tree_items[item_id]
        current_values = self.tree.item(item_id, "values")
        current_status = current_values[0] if current_values else ""
        self.tree.item(
            item_id,
            text=self._format_item_label(item["name"], item["state"]),
            values=(current_status,),
        )

    def _set_item_state(self, item_id: str, state: str, cascade: bool = False) -> None:
        """Set an item's selection state, optionally cascading to children."""
        item = self.tree_items.get(item_id)
        if not item:
            return
        item["state"] = state
        self._update_item_label(item_id)
        if cascade and item["is_dir"]:
            for child_id in self.tree.get_children(item_id):
                self._set_item_state(child_id, state, cascade=True)

    def _update_parent_states(self, item_id: str) -> None:
        """Update parent items to reflect aggregated child state."""
        parent_id = self.tree.parent(item_id)
        while parent_id:
            child_ids = self.tree.get_children(parent_id)
            if not child_ids:
                break
            states = [self.tree_items[child_id]["state"] for child_id in child_ids]
            if all(state == "checked" for state in states):
                new_state = "checked"
            elif all(state == "unchecked" for state in states):
                new_state = "unchecked"
            else:
                new_state = "partial"
            if self.tree_items[parent_id]["state"] != new_state:
                self.tree_items[parent_id]["state"] = new_state
                self._update_item_label(parent_id)
            parent_id = self.tree.parent(parent_id)

    def _sync_select_all_state(self) -> None:
        """Sync the 'Select All' checkbox with current file states."""
        file_states = [
            item["state"]
            for item in self.tree_items.values()
            if not item["is_dir"]
        ]
        all_checked = bool(file_states) and all(state == "checked" for state in file_states)
        if self.chk_all_var.get() != all_checked:
            self.chk_all_var.set(all_checked)

    def load_files(self, folder: str) -> None:
        """Populate the tree with JSONL files found in the selected folder."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items = {}
        if not os.path.exists(folder):
            return

        jsonl_files = self._find_jsonl_files(folder)
        if not jsonl_files:
            return

        dir_items = {}
        for file_path in jsonl_files:
            rel_dir = os.path.relpath(os.path.dirname(file_path), folder)
            parent_id = self._ensure_dir_item(dir_items, folder, rel_dir)
            self._add_file_item(parent_id, file_path)

    def _ensure_dir_item(self, dir_items: Dict[str, str], folder: str, rel_dir: str) -> str:
        """Ensure directory nodes exist in the tree and return the parent id."""
        if rel_dir == ".":
            return ""
        current_rel = ""
        parent_id = ""
        for part in rel_dir.split(os.sep):
            current_rel = part if not current_rel else os.path.join(current_rel, part)
            if current_rel not in dir_items:
                dir_id = self.tree.insert(
                    parent_id,
                    "end",
                    text=self._format_item_label(part, "checked"),
                    values=("",),
                    open=True,
                )
                dir_items[current_rel] = dir_id
                self.tree_items[dir_id] = {
                    "id": dir_id,
                    "name": part,
                    "path": os.path.join(folder, current_rel),
                    "is_dir": True,
                    "state": "checked",
                }
            parent_id = dir_items[current_rel]
        return parent_id

    def _add_file_item(self, parent_id: str, file_path: str) -> None:
        """Add a JSONL file row to the tree view."""
        file_name = os.path.basename(file_path)
        file_id = self.tree.insert(
            parent_id,
            "end",
            text=self._format_item_label(file_name, "checked"),
            values=("Waiting...",),
        )
        self.tree_items[file_id] = {
            "id": file_id,
            "name": file_name,
            "path": file_path,
            "is_dir": False,
            "state": "checked",
        }

    def toggle_check(self, event: Optional[tk.Event] = None) -> None:
        """Toggle selection state for the currently focused row."""
        selected_id = self.tree.focus()
        if not selected_id:
            return
        item = self.tree_items.get(selected_id)
        if not item:
            return
        new_state = "checked" if item["state"] != "checked" else "unchecked"
        self._set_item_state(selected_id, new_state, cascade=True)
        self._update_parent_states(selected_id)
        self._sync_select_all_state()

    def toggle_all(self) -> None:
        """Select or deselect all items based on the header checkbox."""
        state = "checked" if self.chk_all_var.get() else "unchecked"
        for item_id in self.tree.get_children(""):
            self._set_item_state(item_id, state, cascade=True)

    def start_batch(self) -> None:
        """Start background conversion for the selected files."""
        to_process = [
            item for item in self.tree_items.values()
            if not item["is_dir"] and item["state"] == "checked"
        ]
        if not to_process:
            messagebox.showwarning("No Files", "No files selected for conversion.")
            return
        threading.Thread(target=self.process_files, args=(to_process,)).start()

    def process_files(self, files: List[Dict[str, Any]]) -> None:
        """Convert each file and update status in the UI."""
        input_root = self.folder_path.get().strip()
        output_folder = self.output_folder_path.get().strip() or input_root

        for item in files:
            # Safe call to update status
            self.update_status(item["id"], "Converting...")

            # Logic remains same, runs in thread
            success, msg = convert_single_file(item["path"], output_folder, input_root)
            final_status = "Done" if success else "Error"

            # Safe call to update status
            self.update_status(item["id"], final_status)

        # Safe call to show final messagebox on main thread
        self.root.after(0, lambda: messagebox.showinfo("Batch Complete", f"Finished processing {len(files)} files."))

    def update_status(self, item_id: str, status_text: str) -> None:
        """Safely update the status column for a given tree row using the main thread."""
        self.root.after(0, lambda: self._internal_update_status(item_id, status_text))

    def _internal_update_status(self, item_id: str, status_text: str) -> None:
        """Internal method called by the main thread to modify the widget."""
        try:
            self.tree.item(item_id, values=(status_text,))
        except tk.TclError:
            pass


def _set_window_icon(root: tk.Tk) -> None:
    """Apply the embedded app icon to the Tk root window."""
    try:
        icon = tk.PhotoImage(data=APP_ICON_PNG_BASE64)
        root.iconphoto(True, icon)
        root._app_icon = icon
    except tk.TclError:
        pass


def create_gui() -> None:
    """Launch the Tkinter GUI application."""
    root = tk.Tk()
    _set_window_icon(root)
    app = BatchConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    create_gui()
