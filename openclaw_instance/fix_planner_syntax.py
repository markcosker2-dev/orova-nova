import os

file_path = r'c:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\openclaw_instance\app\core\planner.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix initialization (ensure it hasn't been added yet)
old_init = '        """\n        Execute the goal using the ReAct loop with memory.\n        """'
new_init = '        """\n        Execute the goal using the ReAct loop with memory.\n        """\n        if status_callback:\n            await status_callback("🧠 Nova is initializing...")'

if old_init in content and 'await status_callback("🧠 Nova is initializing...")' not in content:
    content = content.replace(old_init, new_init)

# 2. Fix step start
old_step = '            logger.info(f"Planner Step {i+1}/{max_steps}")'
new_step = '            logger.info(f"Planner Step {i+1}/{max_steps}")\n            if status_callback:\n                await status_callback(f"⚡ Step {i+1}/{max_steps}: Thinking...")'

if old_step in content and 'Thinking..."' not in content:
    content = content.replace(old_step, new_step)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed planner.py status callbacks")
