"""RustStdoutReader — protocol parser for Rust voice bridge."""
import subprocess
import queue
import threading
from typing import Optional, Tuple
from serin.config.logger import logger

