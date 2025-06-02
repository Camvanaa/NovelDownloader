from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
# Forward reference for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import requests

class BaseParser(ABC):
    """
    解析器基类，定义了从 HTML 内容中提取小说信息的接口。
    """
    def __init__(self, site_config: dict):
        """
        初始化解析器。

        Args:
            site_config: 包含特定网站解析规则的配置字典。
                         例如：{"novel_title_selector": "css_selector_for_title", ...}
        """
        self.site_config = site_config

    @abstractmethod
    def parse_novel_toc(self, html_content: str, session: 'requests.Session', novel_url: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
        """
        解析小说目录页的 HTML 内容，提取小说标题和所有章节的标题及 URL。
        如果目录是分页的，此方法应负责获取所有分页的内容。

        Args:
            html_content: 小说目录页的第一页 HTML 文本内容。
            session: requests.Session 对象，用于发送后续的 AJAX 请求（如果需要）。
            novel_url: 小说目录页的原始 URL，用于提取小说 ID 或作为 Referer。

        Returns:
            一个元组，包含：
            - novel_title (str | None): 小说的标题，如果未找到则为 None。
            - chapters (List[Tuple[str, str]]): 章节列表，每个元素是一个 (章节标题, 章节URL) 的元组。
                                                如果未找到章节，则为空列表。
        """
        pass

    @abstractmethod
    def parse_chapter(self, html_content: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解析小说章节页的 HTML 内容，提取章节标题和正文。

        Args:
            html_content: 小说章节页的 HTML 文本内容。

        Returns:
            一个元组，包含：
            - chapter_title (str | None): 章节的标题，如果未找到则为 None。
            - chapter_content (str | None): 章节的正文内容，如果未找到则为 None。
        """
        pass

if __name__ == '__main__':
    # 这个基类不能直接实例化和使用，因为它包含抽象方法。
    # 它的用途是为特定的网站解析器提供一个统一的接口规范。
    # class MySiteParser(BaseParser):
    #     def parse_novel_toc(self, html_content: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    #         # 实现针对 MySite 的目录解析逻辑
    #         pass
    #     def parse_chapter(self, html_content: str) -> Tuple[Optional[str], Optional[str]]:
    #         # 实现针对 MySite 的章节解析逻辑
    #         pass
    # config = {"novel_title_selector": "h1.title"} # 示例配置
    # parser = MySiteParser(config)
    print("BaseParser 模块已加载。这是一个抽象基类，请在子类中实现其方法。")
    pass 