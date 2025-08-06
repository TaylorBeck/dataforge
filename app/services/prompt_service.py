"""
Prompt templating service using Jinja2 templates.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from app.config import get_settings

logger = logging.getLogger(__name__)


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
            template = self.get_template(template_name, use_cache=False)
            
            # Extract template variables
            ast = self.env.parse(template.source)
            variables = list(ast.find_all(self.env.nodes.Name))
            var_names = list(set(var.name for var in variables if var.ctx == 'load'))
            
            results["valid"] = True
            results["variables"] = sorted(var_names)
            
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