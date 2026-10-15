import psutil
import threading
import os
import time
from colorama import Fore, Style

from . import JobBot
from . import debug

def monitor_memory_footprint(stop_event:threading.Event, interval:int):
    main_process = psutil.Process(os.getpid())
    while not stop_event.is_set():
        try:
            total_ram_bytes = main_process.memory_info().rss
            for child in main_process.children(True):
                try:
                    total_ram_bytes += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            total_ram_mb = total_ram_bytes/ (1024 * 1024)
            print(f"{Fore.LIGHTGREEN_EX}TOTAL MEMORY FOOTPRINT(Python + Browser): {total_ram_mb}mb{Style.RESET_ALL}")
        except psutil.NoSuchProcess as e:
            print(f"{Fore.LIGHTGREEN_EX}No such process ...exiting profiler: {Fore.RED}{e}{Style.RESET_ALL}")
            break
        print(f"{Fore.LIGHTGREEN_EX}Sleeping for {interval}s{Style.RESET_ALL}")
        time.sleep(interval)

stop_event:threading.Event
monitor_thread:threading.Thread

def start_profiling():
    global stop_event
    global monitor_thread
    try:
        stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=monitor_memory_footprint,args=(stop_event,2),daemon= True
        )
        monitor_thread.start()
    except Exception as e:
        debug.log(f"Error: Couldn't start profiling - {Fore.RED}{e}{Style.RESET_ALL}")

def end_profiling():
    global stop_event
    global monitor_thread
    try:
        if stop_event is not None:
            stop_event.set()
        if monitor_thread is not None:
            monitor_thread.join(2)
    except Exception as e:
        debug.log(f"Error: couldn't end profiling - {Fore.RED}{e}{Style.RESET_ALL}")
