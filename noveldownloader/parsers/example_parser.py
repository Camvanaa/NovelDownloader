from bs4 import BeautifulSoup
from .base_parser import BaseParser
from typing import List, Tuple, Optional
import re
from urllib.parse import urljoin, urlencode # 用于拼接相对 URL 和编码 POST 数据
import json # 用于解析 AJAX 返回的 JSON
import time # 用于分页请求间的延时
import logging # <--- 添加 logging 导入

# Forward reference for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import requests

logger = logging.getLogger(__name__) # <--- 获取 logger 实例

class ExampleParser(BaseParser):
    """
    示例网站解析器，演示如何使用 BeautifulSoup 解析 HTML。
    具体的 CSS 选择器等规则应通过 site_config 传入。
    """
    def __init__(self, site_config: dict):
        super().__init__(site_config)
        self.base_url = site_config.get("base_url", "")
        # 从配置中获取 CSS 选择器等规则
        self.novel_title_selector = site_config.get("novel_title_selector")
        self.chapter_list_selector = site_config.get("chapter_list_selector")
        self.chapter_title_selector = site_config.get("chapter_title_selector")
        self.chapter_content_selector = site_config.get("chapter_content_selector")
        # self.next_page_selector = site_config.get("next_page_selector") # 内容分页，暂时不使用

        # 章节切分相关配置
        self.splitting_enabled = site_config.get("chapter_splitting_enabled", False)
        self.splitting_regex_str = site_config.get("chapter_splitting_regex")
        self.splitting_regex = None
        if self.splitting_enabled and self.splitting_regex_str:
            try:
                self.splitting_regex = re.compile(self.splitting_regex_str, re.MULTILINE)
            except re.error as e:
                print(f"警告: 章节切分正则表达式编译失败: {self.splitting_regex_str}, 错误: {e}")
                self.splitting_enabled = False

        # 目录分页相关配置
        self.pagination_config = site_config.get("pagination_config", {})
        self.ajax_url = self.pagination_config.get("ajax_url")
        self.ajax_method = self.pagination_config.get("ajax_method", "POST").upper()
        self.id_from_url_regex_str = self.pagination_config.get("id_from_url_regex")
        self.id_from_url_regex = None
        if self.id_from_url_regex_str:
            try:
                self.id_from_url_regex = re.compile(self.id_from_url_regex_str)
            except re.error as e:
                print(f"警告: 小说ID提取正则表达式编译失败: {self.id_from_url_regex_str}, 错误: {e}")
        
        self.pagination_select_selector = self.pagination_config.get("pagination_select_selector", "select.select") # CSS selector for the <select> element
        self.pagination_option_selector = self.pagination_config.get("pagination_option_selector", "option") # CSS selector for <option> elements

        self.download_delay = site_config.get("download_delay_seconds", 1) # 用于分页请求间的延时

    def _clean_text(self, text: str) -> str:
        """ 清理文本中的多余空白和特定字符。 """
        if text is None:
            return ""
        text = text.strip()
        text = re.sub(r'\\s+', ' ', text)
        return text

    def parse_novel_toc(self, html_content: str, session: 'requests.Session', novel_url: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
        """
        解析小说目录页，提取小说标题和所有章节的标题及 URL。
        如果目录是分页的，此方法会尝试通过 AJAX 请求获取所有分页的内容。
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        novel_title = None
        all_chapters = []

        # 1. 提取小说标题 (只从第一页提取)
        if self.novel_title_selector:
            title_element = soup.select_one(self.novel_title_selector)
            if title_element:
                novel_title = self._clean_text(title_element.get_text())

        # 2. 提取第一页的章节列表
        if self.chapter_list_selector:
            chapter_elements = soup.select(self.chapter_list_selector)
            for element in chapter_elements:
                try:
                    chapter_text = self._clean_text(element.get_text())
                    raw_chapter_url = element.get('href')
                    if chapter_text and raw_chapter_url:
                        absolute_chapter_url = urljoin(self.base_url or novel_url, raw_chapter_url)
                        all_chapters.append((chapter_text, absolute_chapter_url))
                except Exception as e:
                    print(f"解析第一页章节链接失败: {element}, 错误: {e}")
                    continue
        
        print(f"从第一页解析到 {len(all_chapters)} 章。")

        # 3. 处理分页目录
        logger.debug(f"进入分页处理逻辑。ajax_url: {self.ajax_url}, id_from_url_regex: {self.id_from_url_regex}")
        if self.ajax_url and self.id_from_url_regex:
            logger.debug("ajax_url 和 id_from_url_regex 均有效。")
            novel_id_match = self.id_from_url_regex.search(novel_url)
            if not novel_id_match:
                print(f"警告: 无法从小说URL {novel_url} 中使用正则 {self.id_from_url_regex_str} 提取小说ID，无法进行分页加载。")
                logger.warning(f"小说ID提取失败，URL: {novel_url}, Regex: {self.id_from_url_regex_str}")
                return novel_title, all_chapters
            
            novel_id = novel_id_match.group(1)
            print(f"提取到小说ID: {novel_id}，准备处理分页。")
            logger.info(f"小说ID: {novel_id}，准备处理分页。")

            total_pages = 1
            pagination_select = soup.select_one(self.pagination_select_selector)
            if pagination_select:
                page_options = pagination_select.select(self.pagination_option_selector)
                if page_options:
                    total_pages = len(page_options)
                    print(f"通过分页选择器找到 {total_pages} 个页面选项。")
                    logger.info(f"通过选择器 {self.pagination_select_selector} 找到 {total_pages} 个页面选项 ({self.pagination_option_selector})。")
                else:
                    print(f"警告: 找到分页选择框 {self.pagination_select_selector} 但未找到选项 {self.pagination_option_selector}。假设只有1页。")
                    logger.warning(f"分页选择框 {self.pagination_select_selector} 中未找到选项 {self.pagination_option_selector}。total_pages=1")
            else:
                print(f"未找到分页选择框 {self.pagination_select_selector}。将尝试从 page=2 开始请求。")
                total_pages = self.pagination_config.get("max_ajax_pages", 10)
                logger.info(f"未找到分页选择框 {self.pagination_select_selector}。将使用 max_ajax_pages: {total_pages}。")

            current_page = 2
            logger.debug(f"开始分页循环: current_page={current_page}, total_pages={total_pages}")
            while current_page <= total_pages:
                print(f"尝试获取第 {current_page} 页的章节...")
                logger.info(f"循环中：尝试获取第 {current_page}/{total_pages} 页的章节...")
                
                payload = {'id': novel_id, 'page': str(current_page)}
                
                # 构造 AJAX 请求头
                # 1. 首先复制一份来自 site_config 的通用请求头
                final_ajax_headers = self.site_config.get("headers", {}).copy()
                
                # 2. 然后定义 AJAX 特定的请求头
                ajax_specific_headers = {
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': novel_url, # 关键：AJAX 请求使用具体的小说 URL 作为 Referer
                    'Origin': self.base_url, # AJAX 请求的 Origin，通常是网站的基础 URL
                    'Cookie': 'zh_choose=s' # 显式添加 cURL 中的 Cookie
                }
                
                # 3. 用 AJAX 特定的请求头更新（并覆盖）通用请求头中的相应项
                final_ajax_headers.update(ajax_specific_headers)

                # 如果是 POST，数据在 data 参数；如果是 GET，数据在 params 参数
                try:
                    if self.ajax_method == "POST":
                        response = session.post(self.ajax_url, data=payload, headers=final_ajax_headers)
                    elif self.ajax_method == "GET":
                        response = session.get(self.ajax_url, params=payload, headers=final_ajax_headers)
                    else:
                        print(f"错误: 不支持的 AJAX 请求方法: {self.ajax_method}")
                        break
                    
                    response.raise_for_status() # 如果请求失败 (4xx or 5xx)，则抛出异常
                    
                    # 根据 cURL 的 'accept' 头，期望是 JSON
                    # 有些网站可能在 JSON 里嵌套 HTML，或者直接返回 HTML 片段
                    content_type = response.headers.get('Content-Type', '').lower()

                    page_chapters_html = "" # 重置，因为我们可能不会用它
                    if 'application/json' in content_type:
                        try:
                            data = response.json()
                            logger.debug(f"第 {current_page} 页 ({self.ajax_url}) - AJAX 响应为 JSON。数据 (前500字符): {str(data)[:500]}")
                            
                            # 新的逻辑：直接从 JSON 的 'data' 字段 (如果存在且为列表) 提取章节信息
                            if 'data' in data and isinstance(data['data'], list):
                                logger.info(f"第 {current_page} 页 - 找到 'data' 列表，包含 {len(data['data'])} 个条目。")
                                new_chapters_on_page_from_json = 0
                                for item in data['data']:
                                    if isinstance(item, dict):
                                        chapter_name = item.get('chaptername')
                                        chapter_url_relative = item.get('chapterurl')
                                        
                                        if chapter_name and chapter_url_relative:
                                            cleaned_chapter_name = self._clean_text(chapter_name)
                                            absolute_chapter_url = urljoin(self.base_url or novel_url, chapter_url_relative)
                                            all_chapters.append((cleaned_chapter_name, absolute_chapter_url))
                                            new_chapters_on_page_from_json += 1
                                        else:
                                            logger.warning(f"第 {current_page} 页 - JSON 'data' 列表中的项目缺少 'chaptername' 或 'chapterurl': {item}")
                                    else:
                                        logger.warning(f"第 {current_page} 页 - JSON 'data' 列表中的项目不是字典: {item}")
                                
                                print(f"从 AJAX 第 {current_page} 页的 JSON 'data' 字段解析到 {new_chapters_on_page_from_json} 章。")
                                logger.info(f"从 AJAX 第 {current_page} 页的 JSON 'data' 字段解析到 {new_chapters_on_page_from_json} 章。")
                                
                                # 如果从此JSON的'data'字段没有解析到章节，并且我们不是通过select循环，则停止
                                if new_chapters_on_page_from_json == 0 and not pagination_select:
                                    print(f"AJAX 第 {current_page} 页的 JSON 'data' 未解析到新章节，且未找到分页选择器，停止分页。")
                                    logger.info(f"第 {current_page} 页 ({self.ajax_url}) JSON 'data' 未解析到新章节，且无分页选择器，将 break 分页循环。")
                                    break 
                                # 如果成功解析，则跳过后续的 HTML 解析逻辑，直接进入下一次循环
                                time.sleep(self.download_delay) 
                                current_page += 1
                                continue # <--- 直接进入下一页的循环
                            else: # 如果没有 'data' 列表，回退到尝试从 HTML 字符串解析
                                logger.warning(f"AJAX JSON 响应 ({self.ajax_url}, page {current_page}) 中未找到 'data' 列表。将尝试按旧方式查找 HTML 字符串。")
                                json_html_key_from_config = self.pagination_config.get("json_response_chapters_html_key")
                                found_key = None
                                if 'list' in data and isinstance(data['list'], str):
                                    page_chapters_html = data['list']
                                    found_key = 'list'
                                elif 'info' in data and isinstance(data['info'], str):
                                    page_chapters_html = data['info']
                                    found_key = 'info'
                                elif json_html_key_from_config and json_html_key_from_config in data and isinstance(data[json_html_key_from_config], str):
                                    page_chapters_html = data[json_html_key_from_config]
                                    found_key = json_html_key_from_config
                                
                                if found_key:
                                    logger.debug(f"第 {current_page} 页 - 从JSON字段 '{found_key}' 成功提取HTML。长度: {len(page_chapters_html)}")
                                else:
                                    # (日志记录和 break 的逻辑保持，以防将来遇到这种格式)
                                    attempted_keys = ["'list'", "'info'"]
                                    if json_html_key_from_config:
                                        attempted_keys.append(f"'{json_html_key_from_config}' (from config)")
                                    unique_keys_str = ", ".join(list(set(attempted_keys)))
                                    logger.warning(f"AJAX JSON 响应 ({self.ajax_url}, page {current_page}) 中未找到预期的章节 HTML 字段 (尝试了: {unique_keys_str}, 且没有 'data' 列表). 响应数据 (前200字符): {str(data)[:200]}")
                                    if pagination_select: 
                                         print(f"由于总页数 ({total_pages}) 是根据 select 元素确定的，且未在JSON响应中找到章节HTML或'data'列表，提前结束分页请求。")
                                         logger.warning(f"第 {current_page} 页 - 未在JSON中找到章节HTML或'data'列表，但有分页选择器指示更多页面。提前终止分页。")
                                         break 
                        except json.JSONDecodeError:
                            # (JSON解析错误处理逻辑保持不变)
                            print(f"错误: 解析第 {current_page} 页的 AJAX 响应 JSON 失败。响应文本 (前500字符): {response.text[:500]}...")
                            logger.error(f"解析第 {current_page} 页 ({self.ajax_url}) 的 AJAX 响应 JSON 失败。响应文本 (前200字符): {response.text[:200]}")
                            if not pagination_select: 
                                print("由于JSON解析失败且未找到分页选择器，停止分页尝试。")
                                logger.warning("JSON解析失败且未找到分页选择器，将 break 分页循环。")
                                break 
                    elif 'text/html' in content_type: 
                        page_chapters_html = response.text
                        logger.info(f"第 {current_page} 页 ({self.ajax_url}) - AJAX 响应为 text/html。长度: {len(page_chapters_html)}")
                    else:
                        logger.warning(f"警告: 未知的 AJAX 响应 Content-Type: {content_type}。响应文本 (前200字符): {response.text[:200]}...")
                        if not pagination_select:
                            print("由于未知响应类型且未找到分页选择器，停止分页尝试。")
                            logger.warning(f"未知响应类型 {content_type} 且未找到分页选择器，将 break 分页循环。")
                            break

                    # 如果 page_chapters_html 有内容 (例如来自 text/html 或旧的 JSON->HTML 逻辑)
                    # 并且我们没有通过新的 JSON 'data' 列表逻辑成功并 continue
                    if page_chapters_html: 
                        logger.debug(f"第 {current_page} 页 ({self.ajax_url}) - 将使用 page_chapters_html (长度: {len(page_chapters_html)}) 进行HTML解析。")
                        page_soup = BeautifulSoup(page_chapters_html, 'html.parser')
                        new_chapters_on_page = 0
                        if self.chapter_list_selector: 
                            chapter_elements = page_soup.select(self.chapter_list_selector)
                            logger.debug(f"第 {current_page} 页 ({self.ajax_url}) - HTML片段已用BeautifulSoup解析。用选择器 '{self.chapter_list_selector}' 找到 {len(chapter_elements)} 个章节元素。")
                            for element in chapter_elements:
                                try:
                                    chapter_text = self._clean_text(element.get_text())
                                    raw_chapter_url = element.get('href')
                                    if chapter_text and raw_chapter_url:
                                        absolute_chapter_url = urljoin(self.base_url or novel_url, raw_chapter_url)
                                        all_chapters.append((chapter_text, absolute_chapter_url))
                                        new_chapters_on_page += 1
                                except Exception as e:
                                    print(f"解析第 {current_page} 页 AJAX 章节链接失败: {element}, 错误: {e}")
                                    logger.error(f"解析第 {current_page} 页 AJAX HTML章节链接失败: {element}, 错误: {e}")
                                    continue
                            print(f"从 AJAX 第 {current_page} 页的 HTML 内容解析到 {new_chapters_on_page} 章。")
                            logger.info(f"从 AJAX 第 {current_page} 页的 HTML 内容解析到 {new_chapters_on_page} 章。")
                            if new_chapters_on_page == 0 and not pagination_select:
                                print(f"AJAX 第 {current_page} 页的 HTML 未解析到新章节，且未找到分页选择器，停止分页。")
                                logger.info(f"第 {current_page} 页 ({self.ajax_url}) HTML 未解析到新章节，且无分页选择器，将 break 分页循环。")
                                break 
                        # 如果通过HTML解析，则在此处继续循环
                    elif not ('data' in data and isinstance(data.get('data'), list)): # 如果既没有 page_chapters_html，也不是新JSON格式
                        logger.warning(f"第 {current_page} 页 ({self.ajax_url}) AJAX 响应中既没有可解析的 HTML，也没有 'data' 列表。")
                        if not pagination_select: # 如果不是通过select确定的总页数
                             print(f"在第 {current_page} 页未获取到任何有效章节数据，且未找到分页选择器，停止分页。")
                             logger.info(f"第 {current_page} 页 ({self.ajax_url}) 未获取到任何有效章节数据，且无分页选择器，将 break 分页循环。")
                             break 
                         # 如果有分页选择器，我们已经处理过在JSON中找不到数据的情况，这里可能意味着其他错误，但循环会基于 total_pages 继续

                except requests.exceptions.RequestException as e:
                    # (请求错误处理逻辑保持不变)
                    print(f"请求第 {current_page} 页的 AJAX 目录失败: {e}")
                    logger.error(f"请求第 {current_page} 页 ({self.ajax_url}) 的 AJAX 目录失败: {e}")
                    if not pagination_select:
                        print("由于请求错误且未找到分页选择器，停止分页尝试。")
                        logger.warning(f"请求第 {current_page} 页 ({self.ajax_url}) 失败，且无分页选择器，将 break 分页循环。")
                        break
                
                # 只有在没有通过新的 JSON 'data' 逻辑 continue 的情况下，才执行这里的 time.sleep 和 current_page++
                # 如果已经 continue，这两个操作会在下一次循环前由 continue 语句跳过
                # 但如果新的 JSON 'data' 逻辑成功处理并 continue，它内部已经有 time.sleep 和 current_page++
                # 所以，这里只为旧的HTML解析路径或失败路径服务
                # **修正：移除了这里的 time.sleep 和 current_page++，因为它们要么在新的JSON逻辑中处理，要么在循环末尾统一处理**

                # 统一在循环末尾处理延时和页码增加，除非前面已经 break 或 continue
                time.sleep(self.download_delay) 
                current_page += 1
        else:
            logger.debug("未进入分页处理逻辑。ajax_url 或 id_from_url_regex 未配置或无效。")

        if not novel_title and all_chapters:
            print("警告: 未能解析到小说标题，但解析到了章节列表。")
        elif not all_chapters:
            print("警告: 未能解析到任何章节。请检查 chapter_list_selector 配置和分页逻辑。")
            if novel_title:
                print(f"小说标题为: {novel_title}")

        print(f"总共解析到 {len(all_chapters)} 章。")
        return novel_title, all_chapters

    def parse_chapter(self, html_content: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解析小说章节页，提取章节标题和【完整的、未分割的】内容。
        章节切分逻辑将由 Downloader 根据配置处理。
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        chapter_title = None
        chapter_content_parts = [] # Used if chapter content is paginated, not fully implemented yet

        # 提取章节标题
        if self.chapter_title_selector:
            title_element = soup.select_one(self.chapter_title_selector)
            if title_element:
                chapter_title = self._clean_text(title_element.get_text())

        # 提取章节内容
        if self.chapter_content_selector:
            content_element = soup.select_one(self.chapter_content_selector)
            if content_element:
                # Process each text string from stripped_strings, clean it, then join with double newlines for paragraph effect.
                cleaned_paragraph_strings = [self._clean_text(s) for s in content_element.stripped_strings if s.strip()] # Apply _clean_text to each part and filter empty ones
                current_page_content = '\n\n'.join(cleaned_paragraph_strings) # Join with double newline
                chapter_content_parts.append(current_page_content) # No _clean_text needed here as parts are already cleaned
            else:
                print(f"警告: 未找到章节内容元素，CSS选择器为: {self.chapter_content_selector}")
                return chapter_title, None
        else:
            print("警告: 未配置章节内容选择器 (chapter_content_selector)。")
            return chapter_title, None
        
        # Pagination logic placeholder (currently next_page_selector is not deeply integrated)
        # if self.next_page_selector:
        #     next_page_link = soup.select_one(self.next_page_selector)
        #     if next_page_link and next_page_link.get('href'):
        #         # Recursive call or loop to fetch and append next page content
        #         pass 

        if not chapter_content_parts:
            print(f"警告: 未能解析到章节内容。HTML内容长度: {len(html_content)}")
            if chapter_title: 
                print(f"章节标题为: {chapter_title}")
            return chapter_title, None

        # Join content from multiple (paginated) pages with double newlines
        final_content = "\n\n".join(chapter_content_parts)
        return chapter_title, final_content

# 示例用法 (通常由下载器调用)
if __name__ == '__main__':
    # 假设的网站配置
    mock_site_config = {
        "site_name": "my_example_site",
        "base_url": "http://www.examplefakedomain.com",
        "novel_title_selector": "h1.novel-title",
        "chapter_list_selector": "ul.chapter-list li a", # 匹配所有章节链接
        "chapter_title_selector": "h2.chapter-name",
        "chapter_content_selector": "div#chapter-content-container",
        "next_page_selector": "a.next-page-button" # 假设的分页按钮
    }
    parser = ExampleParser(site_config=mock_site_config)

    # 1. 测试解析小说目录 (TOC)
    mock_toc_html = """
    <html><head><title>Test Novel</title></head><body>
        <h1 class='novel-title'>  My Awesome Novel  </h1>
        <ul class='chapter-list'>
            <li><a href='/novel/1/chap1.html'>Chapter 1: The Beginning</a></li>
            <li><a href='/novel/1/chap2.html'>Chapter 2: The Journey </a></li>
            <li><a href='chap3.html'>Chapter 3: The Climax  </a></li> 
        </ul>
    </body></html>
    """
    title, chapters = parser.parse_novel_toc(mock_toc_html)
    print(f"解析到的小说标题: {title}")
    print("解析到的章节:")
    for ch_title, ch_url in chapters:
        print(f"  - {ch_title} ({ch_url})")
    print("-" * 20)

    # 2. 测试解析章节内容
    mock_chapter_html = """
    <html><head><title>Chapter 1</title></head><body>
        <h2 class='chapter-name'> Chapter 1: The Beginning </h2>
        <div id='chapter-content-container'>
            <p>This is the first paragraph of the story.</p>
            <p>This is the second paragraph, with some  extra   spaces. </p>
            Some text outside paragraph.
            <br/>
            <div>Another nested div with text.</div>
            <!-- Some comment -->
            <script>alert('ads');</script>
            <p>Final paragraph.</p>
        </div>
        <a href='chap2.html' class='next-page-button'>Next Page</a>
    </body></html>
    """
    ch_title, ch_content = parser.parse_chapter(mock_chapter_html)
    print(f"解析到的章节标题: {ch_title}")
    print(f"解析到的章节内容:\n{ch_content}")
    print("-" * 20)

    mock_chapter_html_no_content_selector = """
    <html><head><title>Chapter X</title></head><body>
        <h2 class='chapter-name'> Chapter X </h2>
        <div>No specific content container here. Just random divs.</div>
    </body></html>
    """
    ch_title_err, ch_content_err = parser.parse_chapter(mock_chapter_html_no_content_selector)
    print(f"测试未匹配内容选择器 - 标题: {ch_title_err}, 内容是否为None: {ch_content_err is None}")

    print("\nExampleParser 模块已加载并执行了示例测试。") 