import sys
import logging
from typing import Optional, TextIO
from PyQt6.QtCore import QObject, pyqtSignal

class LogObserver(QObject):
    """
    Observer class to capture sys.stdout and logging events.
    Emits intercepted messages via a Qt signal for GUI display.
    """
    
    # Signal to emit log messages to the GUI (thread-safe)
    log_signal = pyqtSignal(str)
    
    _instance: Optional['LogObserver'] = None

    def __init__(self) -> None:
        """
        Initialize the LogObserver. 
        Sets up stdout redirection and logging handler.
        """
        super().__init__()
        if LogObserver._instance is not None:
             # Just a warning or strict singleton enforcement. 
             # Here we allow re-init but usually it's unique.
             pass
        LogObserver._instance = self
        
        # Setup Logger Interception
        self._setup_logging()
        
        # Setup Stdout Interception
        self._setup_stdout()

    def _setup_logging(self) -> None:
        """
        Configure a custom logging handler to emit records via log_signal.
        """
        class PyQtSignalHandler(logging.Handler):
            def __init__(self, observer: 'LogObserver'):
                super().__init__()
                self.observer = observer

            def emit(self, record: logging.LogRecord) -> None:
                msg = self.format(record)
                self.observer.log_signal.emit(msg)

        handler = PyQtSignalHandler(self)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Add to root logger
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def _setup_stdout(self) -> None:
        """
        Redirect sys.stdout to a custom writer that emits via log_signal.
        Keeps reference to original stdout to avoid blocking/loops and allow terminal output.
        """
        class StdoutRedirector:
            def __init__(self, observer: 'LogObserver', original_stdout: TextIO):
                self.observer = observer
                self.original_stdout = original_stdout

            def write(self, message: str) -> None:
                # Write to original stdout first
                if self.original_stdout:
                     self.original_stdout.write(message)

                # Emit signal for GUI (filter empty newlines if desired, 
                # but better to send all for exact representation or strip for cleaner logs)
                if message and message.strip():
                    self.observer.log_signal.emit(message.strip())

            def flush(self) -> None:
                if self.original_stdout:
                    self.original_stdout.flush()

            def isatty(self) -> bool:
                 # Mimic terminal behavior if needed
                 return getattr(self.original_stdout, 'isatty', lambda: False)()

        # Save original stdout usually only once
        if not isinstance(sys.stdout, StdoutRedirector):
            sys.stdout = StdoutRedirector(self, sys.stdout)

    @classmethod
    def get_instance(cls) -> Optional['LogObserver']:
        """
        Get the current instance of LogObserver.
        
        Returns
        -------
        LogObserver
            The active instance.
        """
        return cls._instance
