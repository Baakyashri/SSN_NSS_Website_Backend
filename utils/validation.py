import re
import html
from typing import Dict, Any, Tuple

def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format"""
    if not email:
        return False, "Email is required"
    
    # Basic email regex pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    
    # Check length
    if len(email) > 254:  # RFC 5321 limit
        return False, "Email too long"
    
    return True, "Valid"

def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password too long"
    
    # Check for at least one letter and one number
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    return True, "Valid"

def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input to prevent XSS and other attacks"""
    if not text:
        return ""
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length]
    
    # HTML escape to prevent XSS
    text = html.escape(text)
    
    # Remove any remaining potentially dangerous characters
    text = re.sub(r'[<>"\']', '', text)
    
    return text.strip()

def validate_required_fields(data: Dict[str, Any], required_fields: list) -> Tuple[bool, str]:
    """Validate that all required fields are present and not empty"""
    for field in required_fields:
        if field not in data or not data[field]:
            return False, f"{field} is required"
    
    return True, "Valid"

def validate_role(role: str) -> Tuple[bool, str]:
    """Validate user role"""
    allowed_roles = ['admin', 'verticalhead', 'volunteer']
    if role not in allowed_roles:
        return False, f"Invalid role. Must be one of: {', '.join(allowed_roles)}"
    
    return True, "Valid"

def validate_vertical(vertical: str) -> Tuple[bool, str]:
    """Validate vertical name"""
    if not vertical:
        return False, "Vertical name is required"
    
    # Sanitize vertical name
    vertical = sanitize_input(vertical, 50)
    
    # Check length
    if len(vertical) < 2:
        return False, "Vertical name too short"
    
    if len(vertical) > 50:
        return False, "Vertical name too long"
    
    # Only allow alphanumeric characters and spaces
    if not re.match(r'^[a-zA-Z0-9\s]+$', vertical):
        return False, "Vertical name can only contain letters, numbers, and spaces"
    
    return True, "Valid"

def validate_activity_data(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate activity data"""
    required_fields = ['title', 'description', 'date']
    
    # Check required fields
    is_valid, error = validate_required_fields(data, required_fields)
    if not is_valid:
        return False, error
    
    # Validate title
    title = sanitize_input(data['title'], 200)
    if len(title) < 3:
        return False, "Title must be at least 3 characters long"
    
    # Validate description
    description = sanitize_input(data['description'], 2000)
    if len(description) < 10:
        return False, "Description must be at least 10 characters long"
    
    # Validate date format (basic check)
    date = data['date']
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        return False, "Invalid date format. Use YYYY-MM-DD"
    
    return True, "Valid"

def validate_contact_data(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate contact form data"""
    required_fields = ['name', 'email', 'message']
    
    # Check required fields
    is_valid, error = validate_required_fields(data, required_fields)
    if not is_valid:
        return False, error
    
    # Validate email
    is_valid, error = validate_email(data['email'])
    if not is_valid:
        return False, error
    
    # Validate name
    name = sanitize_input(data['name'], 100)
    if len(name) < 2:
        return False, "Name must be at least 2 characters long"
    
    # Validate message
    message = sanitize_input(data['message'], 2000)
    if len(message) < 10:
        return False, "Message must be at least 10 characters long"
    
    return True, "Valid"
