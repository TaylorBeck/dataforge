"""
Prompt templating service using Jinja2 templates with few-shot learning support.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from dataclasses import dataclass
from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class FewShotExample:
    """Represents a few-shot learning example."""
    input_context: Dict[str, Any]
    expected_output: str
    description: Optional[str] = None


@dataclass 
class PromptConfig:
    """Configuration for prompt generation."""
    template_name: str
    context: Dict[str, Any]
    few_shot_examples: List[FewShotExample] = None
    sentiment_intensity: Optional[int] = None  # 1-5 scale
    tone: Optional[str] = None
    domain_constraints: List[str] = None
    max_length: Optional[int] = None
    min_length: Optional[int] = None


class PromptTemplateService:
    """Service for managing and rendering Jinja2 prompt templates."""
    
    def __init__(self, template_dir: str = None):
        """
        Initialize prompt template service.
        
        Args:
            template_dir: Directory containing template files
        """
        settings = get_settings()
        self.template_dir = Path(template_dir or settings.prompt_template_dir)
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False  # We don't need HTML escaping for prompts
        )
        
        # Cache for loaded templates
        self._template_cache: Dict[str, Template] = {}
        
    def list_templates(self) -> List[str]:
        """
        List all available template files.
        
        Returns:
            List of template filenames
        """
        try:
            return [
                f.name for f in self.template_dir.glob("*.j2") 
                if f.is_file()
            ]
        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            return []
    
    def get_template(self, template_name: str, use_cache: bool = True) -> Template:
        """
        Load a Jinja2 template.
        
        Args:
            template_name: Name of template file (e.g., "support_request.j2")
            use_cache: Whether to use cached template
            
        Returns:
            Jinja2 Template object
            
        Raises:
            TemplateNotFound: If template file doesn't exist
            Exception: On template loading errors
        """
        if use_cache and template_name in self._template_cache:
            return self._template_cache[template_name]
        
        try:
            template = self.env.get_template(template_name)
            if use_cache:
                self._template_cache[template_name] = template
            return template
        except TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            available = self.list_templates()
            raise TemplateNotFound(
                f"Template '{template_name}' not found. Available templates: {available}"
            )
        except Exception as e:
            logger.error(f"Failed to load template {template_name}: {e}")
            raise
    
    def render_template(
        self, 
        template_name: str, 
        context: Dict[str, Any],
        use_cache: bool = True
    ) -> str:
        """
        Render a template with given context.
        
        Args:
            template_name: Name of template file
            context: Template variables
            use_cache: Whether to use cached template
            
        Returns:
            Rendered template string
            
        Raises:
            TemplateNotFound: If template doesn't exist
            Exception: On rendering errors
        """
        try:
            template = self.get_template(template_name, use_cache)
            rendered = template.render(**context)
            return rendered.strip()
        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {e}")
            raise
    
    def validate_template(self, template_name: str) -> Dict[str, Any]:
        """
        Validate template syntax and extract variables.
        
        Args:
            template_name: Name of template file
            
        Returns:
            Validation results dictionary
        """
        results = {
            "valid": False,
            "variables": [],
            "error": None
        }
        
        try:
            from jinja2 import meta
            template = self.get_template(template_name, use_cache=False)
            
            # Extract template variables using Jinja2 meta API
            parsed_ast = self.env.parse(template.source)
            var_names = sorted(list(meta.find_undeclared_variables(parsed_ast)))
            
            results["valid"] = True
            results["variables"] = var_names
            
        except Exception as e:
            results["error"] = str(e)
            logger.error(f"Template validation failed for {template_name}: {e}")
        
        return results
    
    def create_template_from_string(self, template_string: str) -> Template:
        """
        Create template from string (for dynamic templates).
        
        Args:
            template_string: Template content as string
            
        Returns:
            Jinja2 Template object
        """
        return self.env.from_string(template_string)
    
    def clear_cache(self) -> None:
        """Clear template cache."""
        self._template_cache.clear()
        logger.info("Template cache cleared")
    
    def render_enhanced_prompt(self, config: PromptConfig) -> str:
        """
        Render prompt with few-shot examples and enhanced features.
        
        Args:
            config: Prompt configuration including few-shot examples
            
        Returns:
            Enhanced prompt string with examples and constraints
        """
        # Start with base template context
        enhanced_context = config.context.copy()
        
        # Add enhanced features to context
        if config.sentiment_intensity:
            enhanced_context['sentiment_intensity'] = config.sentiment_intensity
            enhanced_context['sentiment_scale'] = self._get_sentiment_description(config.sentiment_intensity)
        
        if config.tone:
            enhanced_context['tone'] = config.tone
            
        if config.domain_constraints:
            enhanced_context['constraints'] = config.domain_constraints
            
        if config.max_length or config.min_length:
            length_constraint = self._format_length_constraint(config.min_length, config.max_length)
            enhanced_context['length_constraint'] = length_constraint
        
        # Render base template
        base_prompt = self.render_template(config.template_name, enhanced_context)
        
        # Add few-shot examples if provided
        if config.few_shot_examples:
            examples_section = self._format_few_shot_examples(config.few_shot_examples)
            # Insert examples before the final instruction
            enhanced_prompt = f"{examples_section}\n\n{base_prompt}"
        else:
            enhanced_prompt = base_prompt
            
        return enhanced_prompt
    
    def _get_sentiment_description(self, intensity: int) -> str:
        """Get descriptive text for sentiment intensity scale."""
        intensity_map = {
            1: "Very Negative - Highly dissatisfied, angry, or frustrated",
            2: "Negative - Dissatisfied or disappointed", 
            3: "Neutral - Balanced or indifferent",
            4: "Positive - Satisfied or pleased",
            5: "Very Positive - Extremely satisfied, delighted, or enthusiastic"
        }
        return intensity_map.get(intensity, "Neutral")
    
    def _format_length_constraint(self, min_length: Optional[int], max_length: Optional[int]) -> str:
        """Format length constraint description."""
        if min_length and max_length:
            return f"between {min_length}-{max_length} words"
        elif min_length:
            return f"at least {min_length} words"
        elif max_length:
            return f"no more than {max_length} words"
        return ""
    
    def _format_few_shot_examples(self, examples: List[FewShotExample]) -> str:
        """Format few-shot examples for inclusion in prompt."""
        if not examples:
            return ""
            
        examples_text = "Here are some examples of the expected output:\n\n"
        
        for i, example in enumerate(examples, 1):
            examples_text += f"Example {i}:\n"
            
            # Format input context
            context_items = []
            for key, value in example.input_context.items():
                context_items.append(f"{key}: {value}")
            context_str = ", ".join(context_items)
            examples_text += f"Input: {context_str}\n"
            
            # Add expected output
            examples_text += f"Output: {example.expected_output}\n"
            
            # Add description if available
            if example.description:
                examples_text += f"Note: {example.description}\n"
                
            examples_text += "\n"
        
        examples_text += "Now generate your own response following the same pattern:"
        return examples_text
    
    def get_default_few_shot_examples(self, template_name: str, product: str) -> List[FewShotExample]:
        """Get default few-shot examples for a template type."""
        examples_map = {
            "support_request.j2": self._get_support_request_examples(product),
            "product_review.j2": self._get_product_review_examples(product),
            "feature_request.j2": self._get_feature_request_examples(product),
            "chatbot_conversation.j2": self._get_chatbot_examples(product)
        }
        
        return examples_map.get(template_name, [])
    
    def _get_support_request_examples(self, product: str) -> List[FewShotExample]:
        """Get few-shot examples for support requests."""
        return [
            FewShotExample(
                input_context={"product": product, "tone": "frustrated"},
                expected_output=f"I've been trying to use {product} for the past week, but I keep running into sync issues that are really impacting my workflow. The data doesn't update properly between devices, and I've already tried restarting the app multiple times. Could you please help me resolve this? I need this working for an important project deadline next week.",
                description="Frustrated but professional tone with specific issue details"
            ),
            FewShotExample(
                input_context={"product": product, "tone": "polite"},
                expected_output=f"Hi there! I'm having a small issue with {product} where the notifications seem to be delayed by several hours. It's not urgent, but I wanted to report it in case others are experiencing the same thing. The app works great otherwise! Could you let me know if there's a setting I might have missed or if this is a known issue? Thanks for your help!",
                description="Polite and helpful tone with minor issue"
            ),
            FewShotExample(
                input_context={"product": product, "tone": "urgent"},
                expected_output=f"URGENT: {product} completely crashed during our live demo with clients this morning and we lost all our presentation data. This is extremely embarrassing and unprofessional. We need immediate assistance to recover the data and ensure this doesn't happen again. Our reputation is on the line here. Please escalate this to your technical team immediately.",
                description="Urgent tone with business impact emphasis"
            )
        ]
    
    def _get_product_review_examples(self, product: str) -> List[FewShotExample]:
        """Get few-shot examples for product reviews."""
        return [
            FewShotExample(
                input_context={"product": product, "sentiment": "positive"},
                expected_output=f"I've been using {product} for about three months now and I'm really impressed. The interface is intuitive and the features work exactly as advertised. Customer support responded quickly when I had questions during setup. The price point is reasonable for what you get. My only minor complaint is that the mobile app could be a bit faster, but overall this is a solid product that I'd recommend to colleagues.",
                description="Balanced positive review with minor criticism"
            ),
            FewShotExample(
                input_context={"product": product, "sentiment": "negative"},
                expected_output=f"Unfortunately, {product} hasn't lived up to my expectations. The setup process was confusing and took much longer than promised. I've encountered several bugs that customer service says are 'known issues' but no timeline for fixes. For the price, I expected better reliability and support. The core functionality works sometimes, but the inconsistency makes it hard to rely on for important tasks.",
                description="Constructive negative review with specific issues"
            ),
            FewShotExample(
                input_context={"product": product, "sentiment": "neutral"},
                expected_output=f"{product} does what it's supposed to do, nothing more, nothing less. The features are basic but functional. Setup was straightforward. Price seems fair for a standard solution. It's not exciting or innovative, but it gets the job done reliably. If you need something simple and don't require advanced features, this could work for you.",
                description="Neutral review focusing on functionality"
            )
        ]
    
    def _get_feature_request_examples(self, product: str) -> List[FewShotExample]:
        """Get few-shot examples for feature requests."""
        return [
            FewShotExample(
                input_context={"product": product, "urgency": "high"},
                expected_output=f"I'd love to see {product} add bulk export functionality. Currently, I have to export files one by one, which takes hours for large projects. A bulk export feature would save enormous amounts of time for users like me who work with lots of data. This would significantly improve workflow efficiency and reduce the tedious manual work. Many competitors already offer this feature, so it would help {product} stay competitive.",
                description="High-value feature request with business justification"
            ),
            FewShotExample(
                input_context={"product": product, "urgency": "medium"},
                expected_output=f"It would be great if {product} could add dark mode support. I often work in low-light environments and the current bright interface can be straining. This is becoming a standard feature in most modern apps, and it would improve the user experience for many of us who prefer darker themes. Not critical, but would definitely be appreciated!",
                description="User experience improvement request"
            )
        ]
    
    def _get_chatbot_examples(self, product: str) -> List[FewShotExample]:
        """Get few-shot examples for chatbot conversations.""" 
        return [
            FewShotExample(
                input_context={"product": product, "user_type": "new_user"},
                expected_output=f"User: Hi, I just signed up for {product} and I'm not sure where to start.\nBot: Welcome to {product}! I'd be happy to help you get started. Let me walk you through the basics. First, have you completed your profile setup? That's usually the best place to begin.\nUser: No, I haven't done that yet. How do I access it?\nBot: Great question! You can find your profile settings by clicking the gear icon in the top right corner, then selecting 'Profile.' Would you like me to guide you through the key sections to fill out?",
                description="Helpful onboarding conversation for new users"
            )
        ]


# Global template service instance
_template_service: PromptTemplateService = None


def get_template_service() -> PromptTemplateService:
    """Get global template service instance."""
    global _template_service
    if _template_service is None:
        _template_service = PromptTemplateService()
    return _template_service


def render_prompt(
    template_name: str, 
    context: Dict[str, Any], 
    version: str = "v1"
) -> str:
    """
    Convenience function to render a prompt template.
    
    Args:
        template_name: Template file name
        context: Template variables
        version: Template version (for future versioning)
        
    Returns:
        Rendered prompt string
    """
    service = get_template_service()
    
    # Add version to context
    context_with_version = {**context, "version": version}
    
    return service.render_template(template_name, context_with_version)


def render_enhanced_prompt(
    template_name: str,
    context: Dict[str, Any],
    sentiment_intensity: Optional[int] = None,
    tone: Optional[str] = None,
    enable_few_shot: bool = True,
    domain_constraints: List[str] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None
) -> str:
    """
    Convenience function to render enhanced prompt with few-shot learning.
    
    Args:
        template_name: Template file name
        context: Template variables
        sentiment_intensity: Sentiment scale 1-5
        tone: Desired tone (frustrated, polite, urgent, etc.)
        enable_few_shot: Whether to include few-shot examples
        domain_constraints: List of domain-specific constraints
        min_length: Minimum output length in words
        max_length: Maximum output length in words
        
    Returns:
        Enhanced prompt string with examples and constraints
    """
    service = get_template_service()
    
    # Get few-shot examples if enabled
    few_shot_examples = None
    if enable_few_shot and context.get('product'):
        few_shot_examples = service.get_default_few_shot_examples(template_name, context['product'])
    
    # Create prompt configuration
    config = PromptConfig(
        template_name=template_name,
        context=context,
        few_shot_examples=few_shot_examples,
        sentiment_intensity=sentiment_intensity,
        tone=tone,
        domain_constraints=domain_constraints or [],
        min_length=min_length,
        max_length=max_length
    )
    
    return service.render_enhanced_prompt(config)


def get_default_template_context(product: str) -> Dict[str, Any]:
    """
    Get default context for prompt templates.
    
    Args:
        product: Product name/description
        
    Returns:
        Default template context
    """
    return {
        "product": product,
        "timestamp": "now",  # Can be enhanced with actual timestamps
    }