import os

def bundle_code():
    workspace = r"c:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\openclaw_instance"
    output_file = os.path.join(workspace, "Claude_Export.md")
    
    # We want to ignore cache, pycache, .git, etc.
    ignore_dirs = {".git", "__pycache__", "venv", ".env", "node_modules", "Client_Data"}
    ignore_files = {"Claude_Export.md", "bundle_code.py", ".env", "metrics.json", "metrics_history.json", "notifications.json", "agent_status.json", "leads.db"}
    
    with open(output_file, "w", encoding="utf-8") as outfile:
        outfile.write("# OROVA (Nova) Mission Control Codebase\n\n")
        outfile.write("This file contains the complete OpenClaw/Nova Mission Control application codebase, including the core engine, sub-agents, main server, and configuration files.\n\n")
        
        for root, dirs, files in os.walk(workspace):
            # Mutate dirs in place to skip hidden/ignored dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignore_dirs]
            
            for file in files:
                if file in ignore_files or file.endswith(".pyc") or file.endswith(".sqlite") or file.endswith(".db"):
                    continue
                
                # Only include relevant code extensions
                if not (file.endswith(".py") or file.endswith(".md") or file.endswith(".txt") or file.endswith(".json") or file == "Dockerfile" or file == ".env.example"):
                    continue
                
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, workspace)
                
                # Determine markdown code block language
                ext = file.split(".")[-1]
                if ext == "py": lang = "python"
                elif ext == "md": lang = "markdown"
                elif ext == "json": lang = "json"
                elif ext == "txt": lang = "text"
                elif file == "Dockerfile": lang = "dockerfile"
                else: lang = ""
                
                outfile.write(f"\n## File: `{rel_path}`\n\n")
                outfile.write(f"```{lang}\n")
                
                try:
                    with open(filepath, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"Error reading file: {e}")
                
                outfile.write(f"\n```\n")
                
    print(f"Codebase bundled successfully to: {output_file}")

if __name__ == "__main__":
    bundle_code()
