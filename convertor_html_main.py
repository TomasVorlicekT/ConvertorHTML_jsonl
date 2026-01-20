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
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import tkinter as tk

import traceback

from convertor_html_GUI import BatchConverterGUI

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

# A little robot icon for the window in tkinter
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
    app = BatchConverterGUI(convert_single_file, root)
    root.mainloop()


if __name__ == "__main__":
    create_gui()
