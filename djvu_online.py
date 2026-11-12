from html.parser import HTMLParser
import random
import re
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


SITE = "https://djvu.online"
CATALOG_URL = f"{SITE}/latest"
BOOK_LINK = re.compile(r"(?:https://djvu\.online)?(/file/[A-Za-z0-9_-]+)")
PAGE_QUERY = re.compile(r"page=([1-9][0-9]{0,7})")
IT_TAGS = (
    "информационные технологии", "вычислительная техника", "компьютерные технологии",
    "программирование", "компьютерные сети", "интернет", "искусственный интеллект",
    "машинное обучение",
)

# Book pages from the public catalog, used when it requires browser verification.
# Sources: https://djvu.online/latest and pages 6232, 9583 and 9993.
FALLBACK_BOOK_IDS = (
    "WsoWL6MhbSqwQ", "r6kaNPMN2ls0G", "CR1BKzjBWzyah",
    "PkTjcPBSbuDgG", "TE73fCdSIa883", "Vb4qWYFkxBe9I", "5bpT0WPbzZx9G",
    "sn4JG9l057ukf", "yV0X1e3fW6Vsm", "Plta0x1QflUXD", "RHLKxInYegfN5",
    "9zFeIVzLU4USd", "UvO0MSne6fvRO", "qnu05hJumlEna", "jCz91f5PZb02m",
    "BLsdpllJrkLPm", "r6g3IkjkegxGK", "LrT4yKjJEhlSV", "dWNaayGcbWhFD",
    "tDfYfLF4u7fa0", "YIVsksPFYgjbd", "rv0A8al622IBd", "MRGf2WPR60kPV",
    "DMOlilBOzADhi", "9MEv4aKTdDN6r", "NJHOoPXGo4nie", "Ew7d7N1lTAT4t",
    "Xs6aRvjxNRSgk", "PRfK5JTRaoxc0", "Vu7f3nFw8Vm2W", "ZKXBzvzKDxD1J",
    "3V4tgRMxIATXr", "umlTRKDQVNTRx",
)
# Verified DjVu Online book pages, grouped by topic for catalog verification failures.
IT_FALLBACK_BOOK_IDS = (
    "laThe9dxacpfZ", "EJXHuSs1h0CX7", "gp1NxKthr0o5i", "vmsAMiz3BleCe",  # IT and hardware
    "sdBKJkwVqFpnc", "a1H7SBDEW8mcV",
    "LGsWXd6OVv1KI", "SvW2eUAV54bTF", "U5hLAPAXN9tvr", "9IrlcU1pc0sf5", "wDR26EaabIkCJ",  # Programming
    "5AU2QHAb8aX4s", "WY3fG0mi4cfOO", "qeEgLpmeTVkWr", "OUWAlu99hWbto",  # Networks
    "85pOR3pnBYWht", "0UsJ7iPfFpbhh", "NwpmvkU7LS5Op", "gR5r0TrnQzDG3", "8JbWI9toBY0rB",  # Internet and web
    "cWR9f1ywBkIab", "7pc1ZwWyiyDnT", "YE9zvRaytTHUd", "3mzYvS8pDYFIl",  # AI and machine learning
)


class CatalogPage(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.path = unquote(urlsplit(url).path)
        self.books = set()
        self.last_page = 1

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        book = BOOK_LINK.fullmatch(href)
        if book:
            self.books.add(f"{SITE}{book.group(1)}")
            return

        path, _, query = href.removeprefix(SITE).partition("?")
        if path and unquote(path) != self.path:
            return
        if page := PAGE_QUERY.fullmatch(query):
            self.last_page = max(self.last_page, int(page.group(1)))


def read_catalog(url):
    request = Request(url, headers={"Accept": "text/html", "User-Agent": "RnxRutrRandomBook/1.0"})
    catalog = CatalogPage(url)
    with urlopen(request, timeout=3) as response:
        catalog.feed(response.read(1024 * 1024).decode("utf-8", errors="replace"))
    catalog.close()
    return catalog


def random_catalog_book_url(url, fallback_ids):
    books = set()
    try:
        catalog = read_catalog(url)
        books = catalog.books
        if books and (page := random.randint(1, catalog.last_page)) > 1:
            books = read_catalog(f"{url}?page={page}").books or books
    except OSError:
        pass

    if books:
        return random.choice(sorted(books))
    return f"{SITE}/file/{random.choice(fallback_ids)}"


def random_djvu_book_url():
    return random_catalog_book_url(CATALOG_URL, FALLBACK_BOOK_IDS)


def tag_catalog_url(tag):
    encoded_tag = quote("+".join(tag.split()), safe="")
    return f"{SITE}/tag/{encoded_tag}"


def random_djvu_it_book_url():
    return random_catalog_book_url(tag_catalog_url(random.choice(IT_TAGS)), IT_FALLBACK_BOOK_IDS)
