import argparse
import ctypes
from ctypes import wintypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from queue import Full, Queue
import random
import re
from threading import Thread
from time import monotonic
from urllib.request import Request, urlopen
from xml.etree import ElementTree


APP_NAME = "RnxRutrRandomBook"
ATOM = "{http://www.w3.org/2005/Atom}"
FEED_URL = "https://feed.rutracker.cc/atom/f/{}.atom"
TOPIC_URL = re.compile(r"https://rutracker\.org/forum/viewtopic\.php\?t=[1-9][0-9]*")
BOOK_FORUMS = (
    2043, 2042, 2041, 2044, 2039, 2045, 2080, 2047,  # Fiction and genres
    39, 995, 2028, 1426, 2337,  # General, philosophy, math, programming, children's nonfiction
)

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LLKHF_EXTENDED = 0x01
LLKHF_UP = 0x80
ERROR_ALREADY_EXISTS = 183
CTRL_KEYS = {0xA2, 0xA3}  # VK_LCONTROL, VK_RCONTROL
BOOK_KEYS = {0x13, 0x31, 0x20}  # Physical R, N, D keys (scan code set 1)
LOGGER = logging.getLogger(APP_NAME)


def read_book_links(data):
    root = ElementTree.fromstring(data)
    links = set()
    for link in root.iterfind(f"{ATOM}entry/{ATOM}link"):
        url = link.get("href", "")
        if link.get("rel", "alternate") == "alternate" and TOPIC_URL.fullmatch(url):
            links.add(url)
    return sorted(links)


def random_book_url():
    forums = list(BOOK_FORUMS)
    random.shuffle(forums)
    deadline = monotonic() + 10
    last_error = None
    for forum in forums:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        try:
            request = Request(
                FEED_URL.format(forum),
                headers={"Accept": "application/atom+xml", "User-Agent": f"{APP_NAME}/1.0"},
            )
            with urlopen(request, timeout=min(3, remaining)) as response:
                links = read_book_links(response.read(1024 * 1024))
        except (OSError, ElementTree.ParseError) as error:
            last_error = error
            continue
        if links:
            return random.choice(links)
    raise RuntimeError("Не удалось получить книги из лент RuTracker.") from last_error


class KeyboardEvent(ctypes.Structure):
    _fields_ = [
        ("vk_code", wintypes.DWORD),
        ("scan_code", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


def listen_for_hotkey(on_press):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    )
    user32.SetWindowsHookExW.argtypes = (
        ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD
    )
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = (
        wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    )
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
    )
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    held = set()
    chord_down = False

    @callback_type
    def keyboard_hook(code, message, event_address):
        nonlocal chord_down
        if code == HC_ACTION:
            event = KeyboardEvent.from_address(event_address)
            key = event.vk_code if event.vk_code in CTRL_KEYS else event.scan_code
            if key in CTRL_KEYS or (key in BOOK_KEYS and not event.flags & LLKHF_EXTENDED):
                if event.flags & LLKHF_UP:
                    held.discard(key)
                else:
                    held.add(key)
                active = BOOK_KEYS <= held and not CTRL_KEYS.isdisjoint(held)
                if active and not chord_down:
                    on_press()
                chord_down = active
        return user32.CallNextHookEx(None, code, message, event_address)

    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_hook, kernel32.GetModuleHandleW(None), 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())

    LOGGER.info("Сочетание Ctrl+R+N+D активно.")
    msg = wintypes.MSG()
    try:
        while (status := user32.GetMessageW(ctypes.byref(msg), None, 0, 0)) > 0:
            user32.DispatchMessageW(ctypes.byref(msg))
        if status == -1:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        user32.UnhookWindowsHookEx(hook)


def run_background():
    import winsound

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    mutex = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            return

        requests = Queue(maxsize=1)

        def enqueue_request():
            try:
                requests.put_nowait(None)
            except Full:
                pass

        def open_books():
            while True:
                requests.get()
                try:
                    url = random_book_url()
                    os.startfile(url)
                    LOGGER.info("Открыта тема %s", url)
                except (OSError, RuntimeError):
                    LOGGER.exception("Не удалось открыть книгу.")
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        Thread(target=open_books, daemon=True).start()
        listen_for_hotkey(enqueue_request)
    finally:
        kernel32.CloseHandle(mutex)


def main():
    parser = argparse.ArgumentParser(description="Открывает случайную книгу RuTracker по Ctrl+R+N+D.")
    parser.add_argument("--url", action="store_true", help="вывести случайную ссылку для проверки")
    args = parser.parse_args()
    if args.url:
        try:
            print(random_book_url())
        except RuntimeError as error:
            parser.exit(1, f"{error}\n")
        return

    if os.name != "nt":
        parser.exit(1, "Фоновое приложение работает в Windows.\n")
    log_directory = Path(os.environ["LOCALAPPDATA"]) / APP_NAME
    log_directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            RotatingFileHandler(
                log_directory / "service.log", maxBytes=256 * 1024, backupCount=1, encoding="utf-8"
            )
        ],
    )
    try:
        run_background()
    except KeyboardInterrupt:
        pass
    except Exception:
        LOGGER.exception("Фоновое приложение остановлено.")
        raise


if __name__ == "__main__":
    main()
