import json
import os
import sys
from typing import Any

def extract_text_content(content_data: Any) -> str:
    """Extract text from the nested content list structure.

    Args:
        content_data: Mixed content from the JSONL payload. Supported inputs are
            a list of dicts with "type"/"text" keys or a plain string.

    Returns:
        Concatenated text content extracted from the input data.
    """
    text_parts = []
    if isinstance(content_data, list):
        for item in content_data:
            if isinstance(item, dict):
                if item.get("type") == "input_text":
                    text_parts.append(item.get("text", ""))
                elif item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
    elif isinstance(content_data, str):
        return content_data
    return "".join(text_parts)

def convert_jsonl_to_md(input_path: str, output_path: str) -> None:
    """Convert a JSONL transcript into a readable Markdown transcript.

    Args:
        input_path: Path to the input JSONL file.
        output_path: Path where the Markdown output is written.
    """
    print(f"Reading from: {input_path}")
    
    if not os.path.exists(input_path):
        print(f"Error: File '{input_path}' not found.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    markdown_output = []
    
    # We track seen messages to avoid the duplications often present in these logs
    # (e.g., 'event_msg' vs 'response_item' often contain the same text)
    seen_hashes = set()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        try:
            data = json.loads(line)
            
            # Root type check
            msg_type = data.get("type")
            payload = data.get("payload", {})
            
            # We skip 'event_msg' because 'response_item' usually contains the same info 
            # plus tool outputs, making it the more complete source for a transcript.
            if msg_type != "response_item":
                continue

            item_type = payload.get("type")
            
            # 1. Standard Chat Messages (User / Developer / System)
            if item_type == "message":
                role = payload.get("role", "unknown").capitalize()
                content_raw = payload.get("content")
                text = extract_text_content(content_raw)
                
                if text:
                    # Deduplication check
                    content_hash = hash(text)
                    if content_hash in seen_hashes:
                        continue
                    seen_hashes.add(content_hash)

                    icon = "👤" if role == "User" else "🤖"
                    if role == "Developer": icon = "⚙️"
                    
                    markdown_output.append(f"### {icon} {role}\n")
                    markdown_output.append(f"{text}\n")
                    markdown_output.append("---\n")

            # 2. Agent Reasoning (Thoughts)
            elif item_type == "reasoning":
                summary = payload.get("summary", [])
                text = extract_text_content(summary) # Usually in summary for this format
                
                if text:
                    # Formatting blockquote properly
                    formatted_text = text.replace('\n', '\n> ')
                    markdown_output.append(f"> **🧠 Reasoning:**\n> {formatted_text}\n")
                    markdown_output.append("\n")

            # 3. Tool/Function Calls
            elif item_type == "function_call":
                tool_name = payload.get("name", "unknown_tool")
                args = payload.get("arguments", "{}")
                
                markdown_output.append(f"#### 🛠️ Tool Call: `{tool_name}`\n")
                try:
                    # Pretty print the arguments if they are valid JSON
                    if isinstance(args, str):
                        parsed_args = json.loads(args)
                        pretty_args = json.dumps(parsed_args, indent=2)
                    else:
                        pretty_args = json.dumps(args, indent=2)
                    markdown_output.append(f"```json\n{pretty_args}\n```\n")
                except:
                    markdown_output.append(f"```json\n{args}\n```\n")

            # 4. Tool Outputs
            elif item_type == "function_call_output":
                output = payload.get("output", "")
                
                # Truncate if massive (logs can contain huge data dumps)
                if output and len(output) > 2000:
                    display_output = output[:2000] + "\n... (truncated)"
                else:
                    display_output = output

                markdown_output.append(f"**Tool Output:**\n")
                markdown_output.append(f"```text\n{display_output}\n```\n")
                markdown_output.append("---\n")

        except json.JSONDecodeError:
            print(f"Skipping line {i+1}: Invalid JSON")
            continue

    if not markdown_output:
        print("No readable messages found. Ensure the file contains 'response_item' types.")
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(markdown_output))
        print(f"Success! Markdown saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_codex.py <input.jsonl> [output.md]")
    else:
        input_file = sys.argv[1]
        # Auto-generate output filename if not provided
        output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".jsonl", ".md")
        
        # Fallback if extension wasn't jsonl
        if output_file == input_file:
            output_file += ".md"
            
        convert_jsonl_to_md(input_file, output_file)
