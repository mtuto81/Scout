import datetime

def get_time_date():
    """Returns the current time and date."""
    return str(datetime.datetime.now())


TOOLS = [
    {
        "name": "get_time_date",
        "description": "Return the current local date and time.",
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "handler": get_time_date,
    }
]
