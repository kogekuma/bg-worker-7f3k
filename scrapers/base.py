"""スクレイパー基底クラスと共通 HTTP 設定。"""

from abc import ABC, abstractmethod
import requests

CHROME_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
}


class BaseScraper(ABC):
    site_id:   str
    site_name: str

    def __init__(self):
        self.session = requests.Session()

    @abstractmethod
    def scrape(self) -> dict:
        pass

    def get(self, url: str, **kwargs):
        return self.session.get(url, headers=CHROME_HEADERS, timeout=15, **kwargs)

    def post(self, url: str, **kwargs):
        return self.session.post(url, headers=CHROME_HEADERS, timeout=15, **kwargs)
