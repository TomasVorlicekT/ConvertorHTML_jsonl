import json
import sys
import os

def extract_text_content(content_data):
    """
    Helper to extract text from the nested content list structure.
    Handles 'input_text', 'output_text', 'summary_text', and simple strings.
    """
    text_parts = []
    if isinstance(content_data, list):
        for item in content_data:
            if isinstance(item, dict):
                # Check for all known text keys found in Codex logs
                msg_type = item.get("type")
                if msg_type in ["input_text", "output_text", "summary_text", "text"]:
                    text_parts.append(item.get("text", ""))
    elif isinstance(content_data, str):
        return content_data
    return "".join(text_parts)

def convert_jsonl_to_md(input_path, output_path):
    print(f"Reading from: {input_path}")
    
    if not os.path.exists(input_path):
        print(f"Error: File '{input_path}' not found.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    markdown_output = []
    
    # We track seen messages to avoid duplications.
    # This is critical because 'agent_message' (event) and 'response_item' (history) 
    # often contain the exact same text.
    seen_hashes = set()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        try:
            data = json.loads(line)
            
            msg_type = data.get("type")
            payload = data.get("payload", {})
            
            # --- HANDLE EVENTS (Like agent_message) ---
            if msg_type == "event_msg":
                event_type = payload.get("type")
                
                # Check for the specific agent/user message events you pointed out
                if event_type in ["agent_message", "user_message"]:
                    # In events, the text is usually in a direct 'message' key
                    text = payload.get("message", "")
                    
                    if text:
                        # Deduplication
                        content_hash = hash(text)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)
                        
                        role = "Assistant" if event_type == "agent_message" else "User"
                        icon = "🤖" if role == "Assistant" else "👤"
                        
                        markdown_output.append(f"### {icon} {role}\n")
                        markdown_output.append(f"{text}\n")
                        markdown_output.append("---\n")
                continue

            # --- HANDLE RESPONSE ITEMS (Standard Chat History) ---
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

                        # Assign Icons
                        icon = "❓"
                        if role == "User": icon = "👤"
                        elif role in ["Assistant", "Model"]: icon = "🤖"
                        elif role in ["Developer", "System"]: icon = "⚙️"
                        
                        markdown_output.append(f"### {icon} {role}\n")
                        markdown_output.append(f"{text}\n")
                        markdown_output.append("---\n")

                # 2. Agent Reasoning (Thoughts)
                elif item_type == "reasoning":
                    summary = payload.get("summary", [])
                    text = extract_text_content(summary)
                    
                    if text:
                        # Deduplication for reasoning (rarely duplicated, but good practice)
                        content_hash = hash(text)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)

                        formatted_text = text.replace('\n', '\n> ')
                        markdown_output.append(f"> **🧠 Reasoning:**\n> {formatted_text}\n")
                        markdown_output.append("\n")

                # 3. Tool/Function Calls
                elif item_type == "function_call":
                    tool_name = payload.get("name", "unknown_tool")
                    args = payload.get("arguments", "{}")
                    
                    markdown_output.append(f"#### 🛠️ Tool Call: `{tool_name}`\n")
                    try:
                        if isinstance(args, str):
                            parsed_args = json.loads(args)
                            pretty_args = json.dumps(parsed_args, indent=2)
                        else:
                            pretty_args = json.dumps(args, indent=2)
                        markdown_output.append(f"```json\n{pretty_args}\n```\n")
                    except:
                        markdown_output.append(f"```text\n{args}\n```\n")

                # 4. Tool Outputs
                elif item_type == "function_call_output":
                    output = payload.get("output", "")
                    
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
        print("No readable messages found.")
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(markdown_output))
        print(f"Success! Markdown saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_codex.py <input.jsonl> [output.md]")
    else:
        input_file = sys.argv[1]
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
        else:
            output_file = input_file.rsplit('.', 1)[0] + ".md"
            
        convert_jsonl_to_md(input_file, output_file)