from typing import Dict, Optional, Any
import yaml
from pathlib import Path
import logging
from dataclasses import dataclass
import re
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class InterviewContext:
    role: str = "" 
    company: str = "" 
    years_experience: int = 0
    skills: list[str] = None 
    preferred_style: str = "detailed"  #
    
    def __post_init__(self):
        if self.skills is None:
            self.skills = []

class PromptBuilder:
    def __init__(self, templates_dir: Optional[Path] = None):

        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent / "config" / "prompts"
        self.templates_dir = templates_dir
        self.templates = self._load_templates()
        
        self.question_patterns = {
            "behavioral": r"(?i)(tell me about a time|describe a situation|give an example of|how do you handle)",
            "technical": r"(?i)(how would you implement|explain how|what is the difference between|how does|what are|write a|solve this|design a)",
            "experience": r"(?i)(what experience do you have|have you worked with|are you familiar with)",
            "scenario": r"(?i)(what would you do if|how would you handle|imagine that|suppose that)",
            "strength_weakness": r"(?i)(what are your strengths|what is your greatest strength|what are your weaknesses|what is your greatest weakness)",
            "motivation": r"(?i)(why do you want|what interests you|why should we hire|where do you see yourself)",
        }

    def _load_templates(self) -> Dict[str, str]:
        templates = {}
        
        # Create default templates if directory doesn't exist
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Default templates if none exist
        default_templates = {
            "behavioral.yaml": """
format: |
    Given your experience as a {role}, provide a STAR-formatted response about {topic}.
    Focus on demonstrating skills relevant to {company}.
    Keep the response {style}.

example: |
    Situation: Briefly describe the context and challenge
    Task: What was required of you
    Action: What you specifically did, emphasizing relevant skills
    Result: Quantifiable outcomes and learnings
""",
            "technical.yaml": """
format: |
    As a {role} candidate for {company}, explain the technical concept or solution.
    Include practical examples and best practices.
    Structure the response to be {style}.
    Focus on demonstrating expertise in: {skills}.

example: |
    - High-level explanation
    - Key technical details
    - Practical example or implementation
    - Best practices and considerations
""",
            "general.yaml": """
format: |
    Provide a clear and professional response as a {role} candidate interviewing at {company}.
    Demonstrate relevant experience and skills.
    Keep the response {style} and focused.

example: |
    - Direct answer to the question
    - Supporting examples or reasoning
    - Connection to role and company
    - Professional conclusion
"""
        }
        
        for filename, content in default_templates.items():
            template_file = self.templates_dir / filename
            if not template_file.exists():
                template_file.write_text(content)
                logger.info(f"Created default template: {filename}")
        
        # Load all template files
        for template_file in self.templates_dir.glob("*.yaml"):
            try:
                with open(template_file) as f:
                    template_data = yaml.safe_load(f)
                templates[template_file.stem] = template_data
                logger.debug(f"Loaded template: {template_file.name}")
            except Exception as e:
                logger.error(f"Error loading template {template_file}: {e}")
        
        return templates

    def _detect_question_type(self, question: str) -> str:
        """Detect the type of interview question based on patterns."""
        for q_type, pattern in self.question_patterns.items():
            if re.search(pattern, question):
                return q_type
        return "general"

    def _format_skills(self, skills: list[str]) -> str:
        """Format skills list for template insertion."""
        if not skills:
            return "general technical skills"
        return ", ".join(skills)

    def build_prompt(self, question: str, context: InterviewContext) -> str:
        """Build a prompt for the given question and context.
        
        Args:
            question: The interview question
            context: Interview context including role, company, etc.
            
        Returns:
            Formatted prompt for the LLM
        """
        # Detect question type
        q_type = self._detect_question_type(question)
        
        # Get appropriate template
        template_data = self.templates.get(q_type, self.templates["general"])
        
        # Format template with context
        format_vars = {
            "role": context.role or "Software Engineer",
            "company": context.company or "the company",
            "skills": self._format_skills(context.skills),
            "style": context.preferred_style,
            "topic": question
        }
        
        # Build the complete prompt
        prompt = f"""Question: {question}

{template_data['format'].format(**format_vars)}

Remember:
1. Answer ONLY the main question asked, ignore any other unrelated content
2. Keep the answer short, specific, brief, and natural
3. Focus on relevant experience and skills
4. Keep responses professional and well-structured
5. No elaboration unless specifically requested
6. answer within 200 words
"""
        return prompt

    def save_template(self, name: str, template_data: Dict[str, Any]) -> None:
        """Save a new template to the templates directory.
        
        Args:
            name: Template name (without .yaml extension)
            template_data: Template content
        """
        template_file = self.templates_dir / f"{name}.yaml"
        try:
            with open(template_file, 'w') as f:
                yaml.dump(template_data, f)
            self.templates[name] = template_data
            logger.info(f"Saved template: {name}")
        except Exception as e:
            logger.error(f"Error saving template {name}: {e}")
