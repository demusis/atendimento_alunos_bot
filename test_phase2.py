import sys
import asyncio
import time
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from async_worker import AsyncBridgeWorker
from log_observer import LogObserver

async def dummy_task(duration: int):
    logging.info(f"Starting async task for {duration}s")
    print(f"Print from async task: Sleeping {duration}s")
    await asyncio.sleep(duration)
    logging.info("Async task finished")
    return "Done"

def run_test():
    app = QApplication(sys.argv)
    
    # Setup observer
    observer = LogObserver()
    observer.log_signal.connect(lambda msg: print(f"[GUI CAPTURE]: {msg}"))

    # Setup worker
    worker = AsyncBridgeWorker()
    worker.start()
    
    # Wait for loop to start (naive sleep for test)
    time.sleep(1) 
    
    print("Submitting task...")
    future = worker.submit(dummy_task(2))
    
    def check_future():
        if future.done():
            print(f"Task Result: {future.result()}")
            worker.stop()
            app.quit()
    
    timer = QTimer()
    timer.timeout.connect(check_future)
    timer.start(500)
    
    print("Running PyQt event loop...")
    app.exec()

if __name__ == "__main__":
    run_test()
