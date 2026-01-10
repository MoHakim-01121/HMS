"""
Secure environment configuration handler
"""
import os
from pathlib import Path


def get_env_variable(var_name, default=None):
    """
    Get environment variable or return default
    
    Args:
        var_name (str): Environment variable name
        default: Default value if not found
        
    Returns:
        str: Environment variable value or default
    """
    return os.environ.get(var_name, default)


def get_bool_env(var_name, default=False):
    """
    Get boolean environment variable
    
    Args:
        var_name (str): Environment variable name
        default (bool): Default value
        
    Returns:
        bool: Boolean value
    """
    value = os.environ.get(var_name, str(default))
    return value.lower() in ('true', '1', 'yes', 'on')


def get_list_env(var_name, default=None):
    """
    Get list from comma-separated environment variable
    
    Args:
        var_name (str): Environment variable name
        default (list): Default list
        
    Returns:
        list: List of values
    """
    if default is None:
        default = []
    value = os.environ.get(var_name)
    if value:
        return [item.strip() for item in value.split(',')]
    return default
