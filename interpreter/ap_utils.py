"""
APTwitchInterpreter
Created by Jade (TheLovenityJade) - 2025

Utility helpers for message splitting and sending.
"""

import math

def split_text(text: str, max_len: int = 480):
    """Split text into chunks not exceeding max_len, trying to cut on newlines or spaces."""
    parts = []
    current = ""
    for line in text.splitlines(keepends=True):
        # If single line already too long, we split on spaces
        if len(line) > max_len:
            for word in line.split(" "):
                if len(current) + len(word) + 1 > max_len:
                    if current:
                        parts.append(current.rstrip("\n"))
                    current = word + " "
                else:
                    current += word + " "
            continue
        # If adding this line would overflow, flush current
        if len(current) + len(line) > max_len:
            parts.append(current.rstrip("\n"))
            current = line
        else:
            current += line
    if current:
        parts.append(current.rstrip("\n"))
    return parts

async def send_long_message(target, text: str, max_len: int = 480):
    """Send a possibly long message to ctx or channel, splitting if necessary.

    `target` is expected to have an async `send(str)` method (ctx or channel).
    """
    for chunk in split_text(text, max_len=max_len):
        await target.send(chunk)
