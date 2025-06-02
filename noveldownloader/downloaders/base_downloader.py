import requests
from abc import ABC, abstractmethod
from typing import List, Optional

class BaseDownloader(ABC):
    """
    下载器基类，定义了下载器的基本接口。
    """
    def __init__(self, headers=None, proxies=None):
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)
        if proxies:
            self.session.proxies.update(proxies)

    def get_html(self, url: str, params=None, **kwargs) -> str | None:
        """
        获取指定 URL 的 HTML 内容。

        Args:
            url: 目标网页的 URL。
            params: URL 参数。
            **kwargs: 其他 requests.get 的参数。

        Returns:
            网页的 HTML 文本内容，如果请求失败则返回 None。
        """
        try:
            response = self.session.get(url, params=params, **kwargs)
            response.raise_for_status()  # 如果请求失败 (状态码 4xx 或 5xx)，则抛出 HTTPError 异常
            response.encoding = response.apparent_encoding # 自动检测并设置编码
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {url}, 错误: {e}")
            # 在这里可以加入日志记录
            return None

    @abstractmethod
    def download_chapter(self, chapter_url: str, output_path: str):
        """
        下载单个章节的内容。
        这是一个抽象方法，需要在子类中实现。

        Args:
            chapter_url: 章节的 URL。
            output_path: 章节内容的保存路径。
        """
        pass

    @abstractmethod
    def download_novel(self, novel_url: str, output_dir: str, selected_chapters: Optional[List[int]] = None):
        """
        下载整本小说的内容。
        这是一个抽象方法，需要在子类中实现。

        Args:
            novel_url: 小说目录页的 URL。
            output_dir: 小说保存的目录。
            selected_chapters: 可选参数，一个包含用户希望下载的章节序号（1-based）的列表。
                               如果为 None 或空列表，则下载所有章节。
        """
        pass

    @abstractmethod
    def list_chapters(self, novel_url: str) -> None:
        """
        获取并打印小说目录。
        这是一个抽象方法，需要在子类中实现。

        Args:
            novel_url: 小说目录页的 URL。
        """
        pass

if __name__ == '__main__':
    # 这是一个简单的使用示例，实际使用时会由具体的下载器子类来执行
    # downloader = BaseDownloader()
    # html_content = downloader.get_html("https://www.example.com")
    # if html_content:
    #     print(html_content[:200]) # 打印前200个字符
    pass 