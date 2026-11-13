from django import template
from ..models import SystemConfiguration

register = template.Library()

@register.simple_tag
def get_system_config():
    return SystemConfiguration.get_solo()
