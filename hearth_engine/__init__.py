"""Hearth engine (skeleton for process-model probe)."""
import os, threading
STATE = {"llm": None, "registered_pid": None, "api_pid": None}
