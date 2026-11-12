import argparse
import ctypes
from ctypes import wintypes
from functools import partial
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

from djvu_online import random_djvu_book_url, random_djvu_it_book_url, tag_catalog_url


APP_NAME = "RnxRutrRandomBook"
ATOM = "{http://www.w3.org/2005/Atom}"
FEED_URL = "https://feed.rutracker.cc/atom/f/{}.atom"
TOPIC_URL = re.compile(r"https://rutracker\.org/forum/viewtopic\.php\?t=[1-9][0-9]*")
MATH_FORUM = 2028
PHYSICS_FORUM = 2026
PHILOSOPHY_FORUM = 995
BOOK_FORUMS = (
    2043, 2042, 2041, 2044, 2039, 2045, 2080, 2047,  # Fiction and genres
    39, PHILOSOPHY_FORUM, MATH_FORUM, 1426, 2337,  # General, philosophy, math, programming, children's nonfiction
)
# RuTracker's Computer Literature forum and its book subforums.
COMPUTER_BOOK_FORUMS = (1418, 1422, 1423, 1424, 1445, 1425, 1426, 1428, 1429, 1430, 1431, 1433)
RND_KEYS = frozenset({0x13, 0x31, 0x20})  # Physical R, N, D keys
IT_KEYS = frozenset({0x17, 0x14})  # Physical I, T keys

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10
LLKHF_UP = 0x80
ERROR_ALREADY_EXISTS = 183
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
MODIFIER_KEYS = {
    VK_CONTROL: {0xA2, 0xA3},  # Left and right Ctrl
    VK_MENU: {0xA4, 0xA5},  # Left and right Alt
}
OTHER_MODIFIERS = (0x10, 0x5B, 0x5C)  # Shift, left/right Windows
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
VK_PACKET = 0xE7
MENU_MASK_KEY = 0xE8  # Unassigned key, used to keep Alt release from activating a menu.
REPLAY_MARKER = 0x524E5842
LOGGER = logging.getLogger(APP_NAME)


def read_book_links(data):
    root = ElementTree.fromstring(data)
    links = set()
    for link in root.iterfind(f"{ATOM}entry/{ATOM}link"):
        url = link.get("href", "")
        if link.get("rel", "alternate") == "alternate" and TOPIC_URL.fullmatch(url):
            links.add(url)
    return sorted(links)


def random_book_url(forums=BOOK_FORUMS):
    shuffled_forums = list(forums)
    random.shuffle(shuffled_forums)
    deadline = monotonic() + 10
    last_error = None
    for forum in shuffled_forums:
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


def prompt_djvu_tag_url():
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as error:
        raise RuntimeError("Для окна ввода тега требуется Python с Tcl/Tk.") from error

    try:
        window = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError("Не удалось открыть окно ввода тега.") from error

    try:
        window.withdraw()
        window.title("DjVu Online — книги по тегу")
        window.resizable(False, False)
        window.attributes("-topmost", True)

        content = ttk.Frame(window, padding=16)
        content.grid()
        ttk.Label(content, text="Введите тег").grid(sticky="w")
        entry = ttk.Entry(content, width=42)
        entry.grid(sticky="ew", pady=(6, 12))

        url = None

        def confirm(_event=None):
            nonlocal url
            tag = entry.get().strip()
            if tag:
                url = tag_catalog_url(tag)
                window.quit()

        ttk.Button(content, text="ОК", command=confirm).grid(sticky="e")
        window.bind("<Return>", confirm)
        window.bind("<Escape>", lambda _event: window.quit())
        window.protocol("WM_DELETE_WINDOW", window.quit)

        window.update_idletasks()
        x = (window.winfo_screenwidth() - window.winfo_reqwidth()) // 2
        y = (window.winfo_screenheight() - window.winfo_reqheight()) // 2
        window.geometry(f"+{max(0, x)}+{max(0, y)}")
        window.deiconify()
        window.after_idle(entry.focus_force)
        window.mainloop()
        return url
    except tk.TclError as error:
        raise RuntimeError("Не удалось показать окно ввода тега.") from error
    finally:
        window.destroy()


HOTKEY_ACTIONS = {
    VK_CONTROL: {
        RND_KEYS: random_book_url,
        IT_KEYS: partial(random_book_url, COMPUTER_BOOK_FORUMS),
        frozenset({0x32, 0x1E, 0x14}): partial(random_book_url, (MATH_FORUM,)),  # M, A, T
        frozenset({0x21, 0x17, 0x2C}): partial(random_book_url, (PHYSICS_FORUM,)),  # F, I, Z
        frozenset({0x21, 0x17, 0x26}): partial(random_book_url, (PHILOSOPHY_FORUM,)),  # F, I, L
    },
    VK_MENU: {
        RND_KEYS: random_djvu_book_url,
        IT_KEYS: random_djvu_it_book_url,
        frozenset({0x14, 0x1E, 0x22}): prompt_djvu_tag_url,  # T, A, G
    },
}
HOTKEY_SCAN_CODES = frozenset().union(*(chord for actions in HOTKEY_ACTIONS.values() for chord in actions))


def find_yandex_browser():
    import winreg

    registration = r"Software\Clients\StartMenuInternet\Yandex\shell\open\command"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, registration, 0, winreg.KEY_READ | view) as key:
                    command, _ = winreg.QueryValueEx(key, None)
            except OSError:
                continue
            if not isinstance(command, str):
                continue
            match = re.match(
                r'\s*(?:"([^"\r\n]+\.exe)"|([^"\r\n]+?\.exe))(?=\s|$)', command, re.IGNORECASE
            )
            if match:
                path = Path(os.path.expandvars(match.group(1) or match.group(2)))
                if path.is_absolute() and path.is_file():
                    return path

    for variable in ("LOCALAPPDATA", "ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            path = Path(root) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe"
            if path.is_file():
                return path
    raise FileNotFoundError("Не удалось найти установленный Яндекс Браузер.")


def open_in_yandex(url):
    os.startfile(find_yandex_browser(), arguments=url)


class KeyboardEvent(ctypes.Structure):
    _fields_ = [
        ("vk_code", wintypes.DWORD),
        ("scan_code", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("vk_code", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]

    @classmethod
    def from_event(cls, event):
        vk, scan = event.vk_code, event.scan_code
        flags = KEYEVENTF_KEYUP if event.flags & LLKHF_UP else 0
        if vk == VK_PACKET:
            vk = 0
            flags |= KEYEVENTF_UNICODE
        elif scan:
            vk = 0
            flags |= KEYEVENTF_SCANCODE
            if event.flags & LLKHF_EXTENDED:
                flags |= KEYEVENTF_EXTENDEDKEY
        return cls(vk, scan, flags, 0, REPLAY_MARKER)


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
        ("data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class InputData(ctypes.Union):
    # The mouse member sets the Win32 union's full size, even for keyboard input.
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", InputData)]


class BookHotkey:
    def __init__(self, user32, on_press):
        self.user32 = user32
        self.on_press = on_press
        self.held = set()
        self.pending = {}
        self.pending_modifier = None
        # Keep the completed modifier and chord for each swallowed key.
        self.consumed = {}
        self.pending_window = None

    def key_down(self, vk):
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def active_modifier(self):
        ctrl = self.key_down(VK_CONTROL)
        alt = self.key_down(VK_MENU)
        if ctrl == alt or any(self.key_down(vk) for vk in OTHER_MODIFIERS):
            return None
        return VK_CONTROL if ctrl else VK_MENU

    def send_keys(self, keys):
        inputs = (Input * len(keys))(
            *(Input(INPUT_KEYBOARD, InputData(keyboard=key)) for key in keys)
        )
        sent = self.user32.SendInput(len(inputs), inputs, ctypes.sizeof(Input))
        return sent == len(inputs)

    def replay(self, event):
        keys = [*self.pending.values(), KeyboardInput.from_event(event)]
        self.pending.clear()
        return self.send_keys(keys)

    def defer_press(self, scan, event, modifier):
        completed = next(
            (chord for chord in self.consumed.values() if chord and chord[0] == modifier and scan in chord[1]),
            None,
        )
        if completed is not None:
            self.consumed[scan] = completed
            return True

        if self.pending and modifier != self.pending_modifier:
            return False

        actions = HOTKEY_ACTIONS[modifier]
        candidate = frozenset(self.pending) | {scan}
        if not any(candidate <= chord for chord in actions):
            return False

        if not self.pending:
            self.pending_window = self.user32.GetForegroundWindow()
            self.pending_modifier = modifier
        self.pending[scan] = KeyboardInput.from_event(event)
        action = actions.get(candidate)
        if action:
            self.consumed.update(dict.fromkeys(candidate, (modifier, candidate)))
            self.pending.clear()
            if modifier == VK_MENU:
                self.send_keys([
                    KeyboardInput(MENU_MASK_KEY, 0, flags, 0, REPLAY_MARKER)
                    for flags in (0, KEYEVENTF_KEYUP)
                ])
            self.on_press(action)
        return True

    def handle(self, event):
        released = bool(event.flags & LLKHF_UP)
        scan = event.scan_code
        if self.pending and self.pending_window != self.user32.GetForegroundWindow():
            self.consumed.update(dict.fromkeys(self.pending))
            self.pending.clear()

        if scan in HOTKEY_SCAN_CODES and event.vk_code != VK_PACKET and not event.flags & LLKHF_EXTENDED:
            was_held = scan in self.held
            if released:
                self.held.discard(scan)
                if scan in self.consumed:
                    del self.consumed[scan]
                    return True
            else:
                self.held.add(scan)
                if scan in self.pending or scan in self.consumed:
                    return True
                if not was_held and (modifier := self.active_modifier()) is not None:
                    if self.defer_press(scan, event, modifier):
                        return True

        if not self.pending:
            return False
        modifier_keys = MODIFIER_KEYS[self.pending_modifier]
        if event.vk_code in modifier_keys:
            if not released or any(self.key_down(vk) for vk in modifier_keys - {event.vk_code}):
                return False
        # Replay the event after the deferred keys, preserving the modifier until the shortcut is sent.
        return self.replay(event)


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
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    hotkey = BookHotkey(user32, on_press)

    @callback_type
    def keyboard_hook(code, message, event_address):
        if code == HC_ACTION:
            event = KeyboardEvent.from_address(event_address)
            own_replay = event.flags & LLKHF_INJECTED and event.extra_info == REPLAY_MARKER
            if not own_replay and hotkey.handle(event):
                return 1
        return user32.CallNextHookEx(None, code, message, event_address)

    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_hook, kernel32.GetModuleHandleW(None), 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())

    LOGGER.info(
        "Активны Ctrl+R+N+D, Ctrl+I+T, Ctrl+M+A+T, Ctrl+F+I+Z, Ctrl+F+I+L, "
        "Alt+R+N+D, Alt+I+T и Alt+T+A+G."
    )
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

        def enqueue_request(pick_url):
            try:
                requests.put_nowait(pick_url)
            except Full:
                pass

        def open_books():
            while True:
                pick_url = requests.get()
                try:
                    url = pick_url()
                    if url is None:
                        continue
                    open_in_yandex(url)
                    LOGGER.info("Открыта страница %s", url)
                except (OSError, RuntimeError):
                    LOGGER.exception("Не удалось открыть книгу.")
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        Thread(target=open_books, daemon=True).start()
        listen_for_hotkey(enqueue_request)
    finally:
        kernel32.CloseHandle(mutex)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Открывает случайную книгу RuTracker по Ctrl+R+N+D, Ctrl+I+T, "
            "Ctrl+M+A+T, Ctrl+F+I+Z или Ctrl+F+I+L, книгу DjVu Online по Alt+R+N+D или Alt+I+T "
            "и каталог по тегу по Alt+T+A+G."
        )
    )
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
