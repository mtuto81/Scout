import platform

def get_os_info():
    """Returns the operating system information."""
    return platform.platform()


TOOLS = [
    {
        "name": "get_os_info",
        "description": "Return the local operating system platform string.",
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "handler": get_os_info,
    }
]
