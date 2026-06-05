async def get_sysinfo():
    import platform, psutil, socket
    info = {
        "os": platform.system(),
        "version": platform.version(),
        "hostname": socket.gethostname(),
        "cpu": platform.processor(),
        "cores": psutil.cpu_count(logical=False),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 2),
    }
    return info


TOOLS = [
    {
        "name": "get_sysinfo",
        "description": "Return basic local system information such as OS, hostname, CPU, cores, and RAM.",
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "handler": get_sysinfo,
    }
]
