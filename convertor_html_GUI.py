import os
import threading
from typing import Any, Dict, List, Optional, Callable
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class BatchConverterGUI:
    """Tkinter GUI for batch conversion of JSONL log files."""
    def __init__(self, converter_callback: Callable, root: tk.Tk) -> None:
        """Initialize the main window, layout, and widgets."""
 
        self.converter_callback = converter_callback

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
            self.update_status(item["id"], "Converting...")

            success, _msg = self.converter_callback(item["path"], output_folder, input_root)
            final_status = "Done" if success else "Error"

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
