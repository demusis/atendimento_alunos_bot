import asyncio
import threading
from typing import Coroutine, Any, Optional
from PyQt6.QtCore import QThread, QObject

class AsyncBridgeWorker(QThread):
    """
    Worker thread to host the asyncio event loop.
    Isolates asyncio execution from the main PyQt thread to ensure GUI responsiveness.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Initialize the worker.

        Parameters
        ----------
        parent : QObject, optional
            The parent QObject.
        """
        super().__init__(parent)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()

    def run(self) -> None:
        """
        Entry point for the thread. Creates and runs the asyncio event loop.
        """
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._loop_ready.set()
            self.loop.run_forever()
        except Exception as e:
            print(f"AsyncBridgeWorker failure: {e}")
        finally:
            self._loop_ready.clear()
            if self.loop:
                try:
                    tasks = asyncio.all_tasks(self.loop)
                    for task in tasks:
                        task.cancel()
                    
                    # Run loop briefly to allow task cancellation
                    if not self.loop.is_closed():
                        self.loop.run_until_complete(
                            asyncio.gather(*tasks, return_exceptions=True)
                        )
                    self.loop.close()
                except Exception as e:
                    print(f"Error closing loop: {e}")

    def submit(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Future:
        """
        Submit a coroutine to be executed in the thread's event loop.
        Thread-safe method called from the main thread.

        Parameters
        ----------
        coro : Coroutine
            The coroutine to execute.

        Returns
        -------
        asyncio.Future
            A concurrent.futures.Future object (wrapped by asyncio) representing the execution.
        
        Raises
        ------
        RuntimeError
            If the event loop is not running within timeout.
        """
        if not self._loop_ready.wait(timeout=2.0):
             raise RuntimeError("Async event loop did not start in time.")
        
        if self.loop is None or not self.loop.is_running():
            raise RuntimeError("Async event loop is not running.")
        
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self) -> None:
        """
        Stop the asyncio event loop and the thread.
        """
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.quit()
        self.wait()
