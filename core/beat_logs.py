"""Discard dependency output and logging while a CLI handles credentials."""
import contextlib
import logging
import os


@contextlib.contextmanager
def quiet_dependencies():
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous)
