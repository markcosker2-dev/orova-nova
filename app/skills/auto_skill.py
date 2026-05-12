# -*- coding: utf-8 -*-
"""
AutoSkillCreator - Self-improving skills system for OROVA (Hermes)

Detects complex patterns in user interactions, extracts skill templates,
stores skills to ~/.hermes/skills/user-created/, and continuously improves
them based on usage feedback.

Compatible with agentskills.io format.
"""
import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
from collections import Counter


class AutoSkillCreator:
    """
    Autonomous skill creation system that learns from user interactions
    and self-improves during use.
    """
    
    def __init__(self):
        self.skills_dir = Path.home() / ".hermes" / "skills" / "user-created"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.interaction_log = Path.home() / ".hermes" / "interaction_log.json"
        self._init_log()
    
    def _init_log(self):
        if not self.interaction_log.exists():
            self._save_json(self.interaction_log, {"interactions": [], "patterns": []})
    
    def _load_json(self, path: Path) -> Dict:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_json(self, path: Path, data: Dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _compute_pattern_hash(self, steps: List[str]) -> str:
        """Generate a unique hash for a sequence of steps."""
        steps_str = "|".join(str(s) for s in steps)
        return hashlib.sha256(steps_str.encode()).hexdigest()[:12]
    
    def _load_interaction_log(self) -> Dict:
        return self._load_json(self.interaction_log)
    
    def _save_interaction_log(self, data: Dict):
        self._save_json(self.interaction_log, data)
    
    def log_interaction(self, task: str, steps: List[str], outcome: str = "success"):
        """Log an interaction for pattern detection."""
        data = self._load_interaction_log()
        interaction = {
            "task": task,
            "steps": steps,
            "outcome": outcome,
            "timestamp": time.time()
        }
        data["interactions"].append(interaction)
        self._save_interaction_log(data)
        self._detect_and_store_pattern(task, steps)
    
    def _detect_and_store_pattern(self, task: str, steps: List[str]):
        """Detect and store recurring patterns."""
        data = self._load_interaction_log()
        pattern_key = self._compute_pattern_hash(steps)
        
        existing_pattern = None
        for p in data.get("patterns", []):
            if p.get("hash") == pattern_key:
                existing_pattern = p
                break
        
        if existing_pattern:
            existing_pattern["count"] = existing_pattern.get("count", 1) + 1
            existing_pattern["last_task"] = task
            existing_pattern["last_used"] = time.time()
        else:
            new_pattern = {
                "hash": pattern_key,
                "steps": steps,
                "task_type": task,
                "count": 1,
                "first_seen": time.time(),
                "last_used": time.time()
            }
            data.setdefault("patterns", []).append(new_pattern)
        
        self._save_interaction_log(data)
    
    def detect_pattern(self, interaction_steps: List[str]) -> Optional[Dict]:
        """
        Detect if steps form a reusable pattern.
        
        Looks for:
        - Minimum 3 steps (complex enough to be useful)
        - Recurrence in interaction history
        - Consistent outcome patterns
        
        Returns pattern metadata if detected, None otherwise.
        """
        if len(interaction_steps) < 3:
            return None
        
        pattern_hash = self._compute_pattern_hash(interaction_steps)
        data = self._load_interaction_log()
        
        for pattern in data.get("patterns", []):
            if pattern.get("hash") == pattern_hash:
                return {
                    "hash": pattern_hash,
                    "steps": interaction_steps,
                    "recurrence_count": pattern.get("count", 1),
                    "task_type": pattern.get("task_type", "unknown"),
                    "confidence": min(pattern.get("count", 1) / 10, 1.0),
                    "suggested_name": self._generate_skill_name(pattern.get("task_type", "task"))
                }
        
        if len(interaction_steps) >= 5:
            return {
                "hash": pattern_hash,
                "steps": interaction_steps,
                "recurrence_count": 1,
                "task_type": "detected",
                "confidence": 0.3,
                "suggested_name": self._generate_skill_name("complex")
            }
        
        return None
    
    def _generate_skill_name(self, task_type: str) -> str:
        """Generate a clean skill name from task type."""
        clean = "".join(c for c in task_type if c.isalnum() or c == "-").lower()
        return f"auto-{clean}-{int(time.time()) % 10000}"
    
    def create_skill(
        self,
        name: str,
        description: str,
        steps: List[Dict[str, Any]],
        trigger: Optional[str] = None,
        tags: Optional[List[str]] = None,
        improved_from: Optional[str] = None
    ) -> Dict:
        """
        Create a new skill from steps.
        
        Args:
            name: Skill identifier (kebab-case)
            description: Human-readable description
            steps: List of action steps
            trigger: Optional trigger pattern (e.g., /skill-name)
            tags: Optional categorization tags
            improved_from: Original skill name if this is an improvement
            
        Returns created skill metadata.
        """
        skill_file = self.skills_dir / f"{name}.json"
        
        skill_data = {
            "name": name,
            "trigger": trigger or f"/{name}",
            "steps": steps,
            "description": description,
            "tags": tags or [],
            "version": 1,
            "improved_from": improved_from,
            "created_at": time.time(),
            "last_used": None,
            "use_count": 0,
            "success_rate": 1.0,
            "improvement_history": []
        }
        
        self._save_json(skill_file, skill_data)
        
        metadata = {
            "name": name,
            "path": str(skill_file),
            "created": True,
            "version": 1
        }
        
        self._register_skill_in_index(name, description, tags or [])
        
        return metadata
    
    def _register_skill_in_index(self, name: str, description: str, tags: List[str]):
        """Register skill in the central index."""
        index_file = self.skills_dir / "index.json"
        index = self._load_json(index_file)
        
        index.setdefault("skills", {})[name] = {
            "description": description,
            "tags": tags,
            "added_at": time.time()
        }
        
        self._save_json(index_file, index)
    
    def improve_skill(self, skill_name: str, feedback: Dict) -> Dict:
        """
        Refine skill based on use feedback.
        
        Feedback format:
        {
            "success": bool,
            "steps_worked": [step_indices_that_worked],
            "steps_failed": [step_indices_that_failed],
            "suggestions": ["optional improvement suggestions"],
            "new_steps": [optional new steps to add]
        }
        
        Returns updated skill metadata.
        """
        skill_file = self.skills_dir / f"{skill_name}.json"
        
        if not skill_file.exists():
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self._load_json(skill_file)
        
        old_version = skill.get("version", 1)
        skill["version"] = old_version + 1
        skill["last_used"] = time.time()
        skill["use_count"] = skill.get("use_count", 0) + 1
        
        total_uses = skill["use_count"]
        successes = skill.get("success_count", 0) + (1 if feedback.get("success") else 0)
        skill["success_count"] = successes
        skill["success_rate"] = successes / total_uses if total_uses > 0 else 0.0
        
        improvement = {
            "version": old_version,
            "timestamp": time.time(),
            "feedback": feedback,
            "changes": []
        }
        
        if feedback.get("steps_failed"):
            failed_indices = feedback["steps_failed"]
            for idx in failed_indices:
                if idx < len(skill["steps"]):
                    skill["steps"][idx]["note"] = f"Flagged for review (success rate may vary)"
                    improvement["changes"].append(f"Flagged step {idx}")
        
        if feedback.get("new_steps"):
            skill["steps"].extend(feedback["new_steps"])
            improvement["changes"].append(f"Added {len(feedback['new_steps'])} new steps")
        
        if feedback.get("suggestions"):
            skill["description"] = feedback["suggestions"][0]
            improvement["changes"].append("Updated description based on feedback")
        
        skill.setdefault("improvement_history", []).append(improvement)
        
        self._save_json(skill_file, skill)
        
        return {
            "name": skill_name,
            "old_version": old_version,
            "new_version": skill["version"],
            "changes": improvement["changes"],
            "new_success_rate": skill["success_rate"]
        }
    
    def suggest_skills(self, task: str) -> List[Dict]:
        """
        Find relevant existing skills for a task.
        
        Searches by:
        - Task keywords matching skill names/descriptions
        - Tags
        - Historical usage patterns
        """
        task_lower = task.lower()
        index_file = self.skills_dir / "index.json"
        index = self._load_json(index_file)
        
        suggestions = []
        
        for name, info in index.get("skills", {}).items():
            score = 0
            matched_tags = []
            
            if name.lower() in task_lower:
                score += 10
            if info.get("description", "").lower() in task_lower:
                score += 5
            
            for tag in info.get("tags", []):
                if tag.lower() in task_lower:
                    score += 3
                    matched_tags.append(tag)
            
            if score > 0:
                skill_file = self.skills_dir / f"{name}.json"
                skill_data = self._load_json(skill_file)
                
                suggestions.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "match_score": score,
                    "matched_tags": matched_tags,
                    "trigger": skill_data.get("trigger", f"/{name}"),
                    "success_rate": skill_data.get("success_rate", 0.0),
                    "use_count": skill_data.get("use_count", 0)
                })
        
        suggestions.sort(key=lambda x: x["match_score"], reverse=True)
        
        return suggestions[:5]
    
    def search_skills_hub(self, query: str) -> List[Dict]:
        """
        Search the skills.io hub for relevant skills.
        
        Since actual hub access requires network, this provides
        a local cache of known skill templates that can be
        downloaded/adapted.
        
        Returns list of available skill templates.
        """
        known_templates = [
            {
                "name": "web-automation",
                "description": "Automated web interaction patterns",
                "source": "agentskills.io",
                "trigger": "/web-auto"
            },
            {
                "name": "data-processing",
                "description": "File and data transformation workflows",
                "source": "agentskills.io",
                "trigger": "/data-proc"
            },
            {
                "name": "api-integration",
                "description": "REST API call patterns and error handling",
                "source": "agentskills.io",
                "trigger": "/api-call"
            },
            {
                "name": "content-generation",
                "description": "AI-powered content creation workflows",
                "source": "agentskills.io",
                "trigger": "/generate"
            },
            {
                "name": "testing-automation",
                "description": "Automated testing and validation patterns",
                "source": "agentskills.io",
                "trigger": "/test-auto"
            }
        ]
        
        query_lower = query.lower()
        results = [
            t for t in known_templates
            if query_lower in t["name"].lower() or query_lower in t["description"].lower()
        ]
        
        return results if results else known_templates
    
    def get_skill(self, name: str) -> Optional[Dict]:
        """Load and return a specific skill."""
        skill_file = self.skills_dir / f"{name}.json"
        if skill_file.exists():
            return self._load_json(skill_file)
        return None
    
    def list_skills(self) -> List[Dict]:
        """List all available user-created skills."""
        index_file = self.skills_dir / "index.json"
        index = self._load_json(index_file)
        
        skills = []
        for name in index.get("skills", {}):
            skill = self.get_skill(name)
            if skill:
                skills.append({
                    "name": skill["name"],
                    "description": skill["description"],
                    "version": skill.get("version", 1),
                    "trigger": skill.get("trigger", f"/{name}"),
                    "use_count": skill.get("use_count", 0),
                    "success_rate": skill.get("success_rate", 0.0)
                })
        
        return skills
    
    def delete_skill(self, name: str) -> bool:
        """Delete a skill."""
        skill_file = self.skills_dir / f"{name}.json"
        if skill_file.exists():
            skill_file.unlink()
            
            index_file = self.skills_dir / "index.json"
            index = self._load_json(index_file)
            if name in index.get("skills", {}):
                del index["skills"][name]
                self._save_json(index_file, index)
            
            return True
        return False
    
    def export_skill_yaml(self, name: str) -> Optional[str]:
        """Export skill in agentskills.io compatible YAML format."""
        skill = self.get_skill(name)
        if not skill:
            return None
        
        yaml_output = f"""# Skill: {skill['name']}
# Version: {skill.get('version', 1)}
# Created: {time.ctime(skill.get('created_at', 0))}

name: {skill['name']}
trigger: {skill.get('trigger', f'/{name}')}
description: {skill['description']}
improved_from: {skill.get('improved_from', 'none')}

steps:
"""
        for i, step in enumerate(skill.get("steps", [])):
            yaml_output += f"  - step_{i + 1}: {json.dumps(step)}\n"
        
        yaml_output += f"""
metadata:
  use_count: {skill.get('use_count', 0)}
  success_rate: {skill.get('success_rate', 0.0)}
  tags: {skill.get('tags', [])}
"""
        return yaml_output


def create_skill_from_interaction(
    name: str,
    description: str,
    steps: List[Dict[str, Any]]
) -> Dict:
    """
    Convenience function to create a skill from interaction data.
    """
    creator = AutoSkillCreator()
    return creator.create_skill(name, description, steps)


def find_skill_for_task(task: str) -> List[Dict]:
    """
    Convenience function to find relevant skills for a task.
    """
    creator = AutoSkillCreator()
    return creator.suggest_skills(task)


if __name__ == "__main__":
    creator = AutoSkillCreator()
    
    print("=== AutoSkillCreator Demo ===")
    print(f"Skills directory: {creator.skills_dir}")
    
    demo_steps = [
        {"action": "search", "query": "example"},
        {"action": "filter", "criteria": "relevance"},
        {"action": "process", "method": "transform"}
    ]
    
    pattern = creator.detect_pattern([str(s) for s in demo_steps])
    print(f"\nPattern detection: {pattern}")
    
    result = creator.create_skill(
        name="demo-pattern-skill",
        description="A demo skill created from pattern detection",
        steps=demo_steps,
        tags=["demo", "pattern"]
    )
    print(f"\nSkill creation: {result}")
    
    suggestions = creator.suggest_skills("demo task")
    print(f"\nSkill suggestions: {suggestions}")
    
    hub_results = creator.search_skills_hub("automation")
    print(f"\nHub search: {hub_results}")