import sys
import os

class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log_file = open("logs.log", "w", encoding='utf-8')

    def write(self, message):
        # Write to log file
        self.log_file.write(message)
        self.log_file.flush()
        # Do NOT write to terminal (as requested)
        # self.terminal.write(message)

    def flush(self):
        self.log_file.flush()
        pass

def setup_logging():
    # Only redirect if not already redirected
    if not isinstance(sys.stdout, Logger):
        sys.stdout = Logger()
        sys.stderr = Logger() # Redirect stderr too
        print("Logging started. Terminal output silenced.")
