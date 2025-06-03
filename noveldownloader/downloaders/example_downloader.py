from .base_downloader import BaseDownloader
from ..parsers.example_parser import ExampleParser # 假设我们有一个对应的解析器
from ..cache_manager.file_cache import FileCache # 引入缓存管理器
import os
import time
import re
from typing import Optional, List, Tuple
import logging
from ebooklib import epub
import glob
from datetime import datetime

logger = logging.getLogger(__name__)

class ExampleDownloader(BaseDownloader):
    """
    示例网站下载器，用于演示如何实现特定网站的下载逻辑。
    """
    def __init__(self, site_config, cache_dir="cache"):
        super().__init__(headers=site_config.get("headers"), proxies=site_config.get("proxies"))
        self.site_name = site_config.get("site_name", "example_site")
        self.parser = ExampleParser(site_config) # Parser needs full site_config for its selectors

        cache_settings = site_config.get("cache_settings", {})
        self._cache_enabled = cache_settings.get("enabled", True) # Check if caching is globally enabled for this site
        cache_expires = cache_settings.get("expires_in_seconds")

        # cache_dir is the specific directory for this site's cache, passed from main.py
        self.cache = FileCache(cache_dir=cache_dir, expires_in_seconds=cache_expires)
        
        self.download_delay = site_config.get("download_delay", 1) # 下载延迟，单位秒

        # 新增：加载标题清理正则表达式
        title_patterns = site_config.get("title_patterns", {})
        self.title_remove_regex_str = title_patterns.get("remove_regex")
        self.title_remove_regex = None
        if self.title_remove_regex_str:
            try:
                self.title_remove_regex = re.compile(self.title_remove_regex_str)
            except re.error as e:
                print(f"警告: 标题移除正则表达式编译失败: {self.title_remove_regex_str}, 错误: {e}")

        # 新增：内容内章节分割配置
        in_content_splitting_config = site_config.get("in_content_splitting", {})
        self.in_content_splitting_enabled = in_content_splitting_config.get("enabled", False)
        self.in_content_header_regex_str = in_content_splitting_config.get("header_regex")
        self.in_content_header_regex = None
        if self.in_content_splitting_enabled and self.in_content_header_regex_str:
            try:
                # 必须使用 re.MULTILINE 使 ^ 匹配每行的开头
                self.in_content_header_regex = re.compile(self.in_content_header_regex_str, re.MULTILINE)
                logger.info(f"内容内章节分割已启用，正则表达式: {self.in_content_header_regex_str}")
            except re.error as e:
                logger.error(f"内容内章节分割正则表达式编译失败: {self.in_content_header_regex_str}, 错误: {e}")
                self.in_content_splitting_enabled = False

        # 新增：用于跨章节内容合并的缓存
        self._last_chapter_info = {
            'index': None,  # 上一章的序号
            'title': None,  # 上一章的标题
            'path': None,   # 上一章的文件路径
            'pending_content': None  # 待处理的内容（可能属于上一章）
        }

    def _get_cleaned_title(self, raw_title: Optional[str]) -> str:
        """清理原始章节标题，移除不需要的模式。"""
        if not raw_title:
            return "未命名章节"
        
        cleaned_title = raw_title.strip()
        if self.title_remove_regex:
            cleaned_title = self.title_remove_regex.sub("", cleaned_title).strip()
        
        # 移除"第x章"格式
        chapter_pattern = re.compile(r'^第[一二三四五六七八九十百千零〇\d]+章[_\s]*')
        cleaned_title = chapter_pattern.sub("", cleaned_title).strip()
        
        # 确保标题不为空
        return cleaned_title if cleaned_title else "未命名章节"

    def _save_chapter_content(self, title: Optional[str], content: str, output_path: str) -> bool:
        """辅助方法，用于保存单个（子）章节的内容。"""
        if not content:
            print(f"警告: 内容为空，不保存文件: {output_path}")
            return False
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            # 使用清理后的标题写入文件内容
            display_title = self._get_cleaned_title(title)
            full_text = f"{display_title}\n\n{content.strip()}" if display_title != "untitled_chapter" else content.strip()
            
            # 如果有待处理的内容需要合并到这一章
            if self._last_chapter_info['pending_content'] and title == self._last_chapter_info['title']:
                full_text = f"{full_text}\n\n{self._last_chapter_info['pending_content'].strip()}"
                self._last_chapter_info['pending_content'] = None  # 清除已合并的待处理内容
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            print(f"内容已保存到: {output_path}")
            return True
        except IOError as e:
            print(f"保存文件失败: {output_path}, 错误: {e}")
            return False

    def download_chapter(self, chapter_url: str, base_output_path: str, chapter_index: int, original_chapter_title_from_toc: str) -> bool:
        """
        下载并处理单个目录条目对应的章节内容。
        如果启用了章节切分，可能会将一个网页内容分割成多个文件。

        Args:
            chapter_url: 章节的 URL。
            base_output_path: 该章节的基础输出路径 (不包含文件名，但可能包含小说标题目录)。
            chapter_index: 该章节在目录中的序号 (从1开始)。
            original_chapter_title_from_toc: 从目录页解析得到的原始章节标题。

        Returns:
            处理成功（至少保存了一个文件）返回 True，否则返回 False。
        """
        print(f"\n开始处理章节 {chapter_index}: {self._get_cleaned_title(original_chapter_title_from_toc)} ({chapter_url})")
        
        html_content = None
        # 对于章节切分，我们总是缓存原始HTML，而不是解析后的或切分后的内容
        # 因为切分规则可能改变，重新从原始HTML执行切分更可靠
        if self._cache_enabled:
            cached_html = self.cache.get(chapter_url)
            if cached_html:
                print(f"从缓存加载原始HTML: {chapter_url}")
                html_content = cached_html
            # else: we will fetch and then cache it
        
        if not html_content:
            html_content = self.get_html(chapter_url)
            if not html_content:
                print(f"获取章节HTML失败: {chapter_url}")
                return False
            if self._cache_enabled:
                self.cache.set(chapter_url, html_content) # Cache the raw HTML

        # 解析HTML获取主要章节标题和完整内容块
        main_html_title, full_content_block = self.parser.parse_chapter(html_content)

        if not full_content_block:
            print(f"解析章节内容块失败: {chapter_url}")
            return False

        # 清理来自HTML的标题和来自目录的标题
        cleaned_main_html_title = self._get_cleaned_title(main_html_title)
        cleaned_toc_title = self._get_cleaned_title(original_chapter_title_from_toc)
        
        # 决定有效的显示/保存用主标题
        effective_main_display_title = cleaned_main_html_title if cleaned_main_html_title != "untitled_chapter" else cleaned_toc_title

        saved_any_file = False
        processed_by_in_content_splitting = False

        # 1. 优先尝试内容内分割 (in-content splitting)
        if self.in_content_splitting_enabled and self.in_content_header_regex:
            logger.debug(f"章节 {chapter_index} - 尝试内容内分割，使用正则: {self.in_content_header_regex_str}")
            
            # 找到所有匹配的标题
            matches = list(self.in_content_header_regex.finditer(full_content_block))
            
            # 如果没有找到任何标题，整个内容应该合并到前一章
            if not matches:
                logger.debug("未找到任何匹配的标题，尝试合并到前一章")
                if self._last_chapter_info['title'] and self._last_chapter_info['path']:
                    # 将整个内容追加到上一章
                    with open(self._last_chapter_info['path'], 'a', encoding='utf-8') as f:
                        f.write(f"\n\n{full_content_block.strip()}")
                    logger.info(f"将无标题内容合并到上一章: {self._last_chapter_info['title']}")
                    saved_any_file = True
                    processed_by_in_content_splitting = True
                else:
                    logger.warning("没有前一章的信息，无法合并内容")
            else:
                logger.debug(f"找到 {len(matches)} 个匹配的标题")
                
                ics_sub_chapter_counter = 0
                
                # 处理第一个标题之前的内容
                first_part_content = full_content_block[:matches[0].start()].strip()
                if first_part_content:
                    # 如果这部分内容没有标题，它应该属于上一章
                    if self._last_chapter_info['title'] and self._last_chapter_info['path']:
                        # 将内容追加到上一章
                        with open(self._last_chapter_info['path'], 'a', encoding='utf-8') as f:
                            f.write(f"\n\n{first_part_content}")
                        logger.info(f"将无标题内容合并到上一章: {self._last_chapter_info['title']}")
                        saved_any_file = True
                    else:
                        # 如果没有上一章的信息，作为当前章节的一部分处理
                        ics_sub_chapter_counter += 1
                        main_part_title = effective_main_display_title 
                        main_part_filename_title = self._clean_filename(f"{main_part_title}_p0")
                        
                        output_filename_main_part = f"{chapter_index:04d}_ics_{ics_sub_chapter_counter:03d}_{main_part_filename_title}.txt"
                        output_filepath_main_part = os.path.join(base_output_path, output_filename_main_part)
                        
                        if self._save_chapter_content(main_part_title, first_part_content, output_filepath_main_part):
                            saved_any_file = True
                            processed_by_in_content_splitting = True

                # 处理每个标题和其后的内容
                for i in range(len(matches)):
                    current_match = matches[i]
                    next_match = matches[i + 1] if i + 1 < len(matches) else None
                    
                    # 使用匹配的标题作为章节标题
                    raw_ics_title = current_match.group(0).strip()
                    cleaned_ics_title = self._get_cleaned_title(raw_ics_title)
                    
                    # 获取内容（从当前标题后到下一个标题前）
                    content_start = current_match.end()
                    content_end = next_match.start() if next_match else len(full_content_block)
                    content = full_content_block[content_start:content_end].strip()
                    
                    if cleaned_ics_title and content:
                        ics_sub_chapter_counter += 1
                        clean_title_for_file = self._clean_filename(cleaned_ics_title)
                        output_filename = f"{chapter_index:04d}_ics_{ics_sub_chapter_counter:03d}_{clean_title_for_file}.txt"
                        output_filepath = os.path.join(base_output_path, output_filename)
                        
                        if self._save_chapter_content(cleaned_ics_title, content, output_filepath):
                            saved_any_file = True
                            processed_by_in_content_splitting = True
                            # 更新最后处理的章节信息
                            self._last_chapter_info.update({
                                'index': chapter_index,
                                'title': cleaned_ics_title,
                                'path': output_filepath,
                                'pending_content': None
                            })
                    elif content:  # 如果只有内容没有标题
                        if self._last_chapter_info['title'] and self._last_chapter_info['path']:
                            # 将内容追加到上一章
                            with open(self._last_chapter_info['path'], 'a', encoding='utf-8') as f:
                                f.write(f"\n\n{content}")
                            logger.info(f"将无标题内容合并到上一章: {self._last_chapter_info['title']}")
                            saved_any_file = True

                if processed_by_in_content_splitting:
                    logger.info(f"章节 {chapter_index} - 内容内分割处理完成，共处理 {ics_sub_chapter_counter} 个子章节")
                else:
                    logger.warning(f"章节 {chapter_index} - 内容内分割未产生任何有效的子章节")
                    
        # 2. 如果内容内分割未处理或未启用，则尝试解析器级别的章节切分
        if not processed_by_in_content_splitting and self.parser.splitting_enabled and self.parser.splitting_regex:
            logger.info(f"章节 {chapter_index} - 内容内分割未处理，尝试解析器级别切分，正则: {self.parser.splitting_regex_str}")
            
            parts = self.parser.splitting_regex.split(full_content_block)
            parser_sub_chapter_counter = 0

            if parts and parts[0].strip(): # 处理第一个分隔符前的内容
                parser_sub_chapter_counter += 1
                # 使用主章节的有效显示标题作为这部分的标题
                # 或者可以创建一个如 "cleaned_toc_title_part1" 的标题
                title_for_first_part = effective_main_display_title + (f"_part{parser_sub_chapter_counter}" if len(parts) > 1 else "")
                clean_title_for_file = self._clean_filename(title_for_first_part)

                output_filename = f"{chapter_index:04d}_psr_{parser_sub_chapter_counter:03d}_{clean_title_for_file}.txt"
                output_filepath = os.path.join(base_output_path, output_filename)
                logger.info(f"章节 {chapter_index} - 解析器切分：保存前导部分 {parser_sub_chapter_counter} - '{title_for_first_part}'")
                if self._save_chapter_content(title_for_first_part, parts[0], output_filepath):
                    saved_any_file = True
            
            for i in range(1, len(parts), 2): # 处理正则匹配到的子章节标题和它们的内容
                raw_sub_title = self._clean_text(parts[i])
                cleaned_sub_title = self._get_cleaned_title(raw_sub_title)
                sub_chapter_content = parts[i+1].strip() if (i+1) < len(parts) else ""

                if not cleaned_sub_title or not sub_chapter_content:
                    logger.warning(f"章节 {chapter_index} - 解析器切分：跳过空的子标题或内容。标题: '{cleaned_sub_title}'")
                    continue
                
                parser_sub_chapter_counter += 1
                clean_sub_title_for_file = self._clean_filename(cleaned_sub_title)
                
                output_filename = f"{chapter_index:04d}_psr_{parser_sub_chapter_counter:03d}_{clean_sub_title_for_file}.txt"
                output_filepath = os.path.join(base_output_path, output_filename)
                
                logger.info(f"章节 {chapter_index} - 解析器切分：保存子章节 {parser_sub_chapter_counter} - '{cleaned_sub_title}'")
                if self._save_chapter_content(cleaned_sub_title, sub_chapter_content, output_filepath):
                    saved_any_file = True
            
            if not saved_any_file and (not parts[0].strip() and len(parts) <= 1):
                logger.warning(f"章节 {chapter_index} - 解析器切分正则未切分出任何子章节，且前导内容为空。")
                # 不要在这里回退到保存整个块，让最后的统一回退逻辑处理

        # 3. 如果以上两种分割方式都没有成功保存任何文件，则保存整个内容块
        if not saved_any_file:
            logger.info(f"章节 {chapter_index} - 未进行任何分割，或分割未产生文件。将保存整个内容块。")
            # 使用清理后的目录标题或HTML标题作为文件名
            title_for_file = self._clean_filename(effective_main_display_title)
            if not title_for_file: title_for_file = f"chapter_{chapter_index}"

            output_filename = f"{chapter_index:04d}_{title_for_file}.txt"
            output_filepath = os.path.join(base_output_path, output_filename)
            # 保存时使用有效的显示标题 (cleaned_main_html_title 或 cleaned_toc_title)
            if self._save_chapter_content(effective_main_display_title, full_content_block, output_filepath):
                saved_any_file = True

        if saved_any_file:
            time.sleep(self.download_delay) # 只有在成功保存至少一个文件后才延迟
        return saved_any_file

    def _clean_text(self, text: str) -> str:
        if text is None: return ""
        return re.sub(r'\s+', ' ', text).strip()

    def _clean_filename(self, filename: str) -> str:
        if not filename: return "未命名章节"
        # 移除非法字符，并将空格替换为下划线
        filename = re.sub(r'[\\/:*?"<>|]', '', filename)
        filename = re.sub(r'\s+', '_', filename)
        return filename[:100] #限制文件名长度

    def _merge_to_txt(self, novel_output_dir: str, novel_title: str) -> str:
        """
        将所有章节合并为单个txt文件。
        
        Args:
            novel_output_dir: 小说章节文件所在目录
            novel_title: 小说标题
        
        Returns:
            合并后的txt文件路径
        """
        txt_path = os.path.join(novel_output_dir, f"{novel_title}.txt")
        chapter_files = sorted(glob.glob(os.path.join(novel_output_dir, "*.txt")))
        
        with open(txt_path, 'w', encoding='utf-8') as outfile:
            outfile.write(f"{novel_title}\n\n")
            for chapter_file in chapter_files:
                if os.path.basename(chapter_file) != os.path.basename(txt_path):  # 避免包含合并后的文件
                    with open(chapter_file, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(f"{content}\n\n")
        
        return txt_path

    def _merge_to_epub(self, novel_output_dir: str, novel_title: str) -> str:
        """
        将所有章节合并为epub文件。
        
        Args:
            novel_output_dir: 小说章节文件所在目录
            novel_title: 小说标题
        
        Returns:
            合并后的epub文件路径
        """
        book = epub.EpubBook()
        
        # 设置书籍元数据
        book.set_identifier(f'novel_{datetime.now().strftime("%Y%m%d%H%M%S")}')
        book.set_title(novel_title)
        book.set_language('zh-CN')
        
        # 添加CSS样式
        style = '''
        @namespace epub "http://www.idpf.org/2007/ops";
        body {
            font-family: SimSun, serif;
            padding: 5%;
        }
        h1 {
            text-align: center;
            padding: 10px;
        }
        '''
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        book.add_item(nav_css)
        
        # 添加章节
        chapter_files = sorted(glob.glob(os.path.join(novel_output_dir, "*.txt")))
        chapters = []
        toc = []
        spine = ['nav']
        
        for i, chapter_file in enumerate(chapter_files):
            if os.path.basename(chapter_file).endswith('.txt'):
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    # 分离标题和内容
                    lines = content.split('\n', 1)
                    title = lines[0].strip()
                    chapter_content = lines[1].strip() if len(lines) > 1 else ""
                    
                    # 创建章节
                    chapter = epub.EpubHtml(title=title,
                                          file_name=f'chapter_{i+1}.xhtml',
                                          lang='zh-CN')
                    chapter.content = f'<h1>{title}</h1>\n{chapter_content}'
                    chapter.add_item(nav_css)
                    
                    book.add_item(chapter)
                    chapters.append(chapter)
                    toc.append(chapter)
                    spine.append(chapter)
        
        # 添加目录
        book.toc = toc
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 生成epub文件
        epub_path = os.path.join(novel_output_dir, f"{novel_title}.epub")
        epub.write_epub(epub_path, book, {})
        
        return epub_path

    def download_novel(self, novel_url: str, output_dir: str, selected_chapters: Optional[List[int]] = None):
        """
        下载整本小说的内容。
        如果提供了 selected_chapters，则只下载指定序号的章节。
        下载完成后会自动合并为epub和txt格式。
        """
        print(f"开始下载小说: {novel_url}")
        if selected_chapters:
            print(f"指定下载章节序号: {selected_chapters}")
        
        # 获取小说目录页的HTML
        toc_html_content = self.get_html(novel_url)
        if not toc_html_content:
            print(f"获取小说目录页失败: {novel_url}")
            return

        # 解析目录页，获取小说标题和章节列表
        novel_title_from_parser, chapters = self.parser.parse_novel_toc(toc_html_content, self.session, novel_url)
        
        if not chapters:
            print(f"未能从目录页解析到任何章节: {novel_url}")
            return

        # 使用从解析器获取的小说标题
        if novel_title_from_parser:
            cleaned_novel_title = self._clean_filename(self._get_cleaned_title(novel_title_from_parser))
        else:
            print("警告: 未能从目录页解析到小说主标题，将尝试使用站点名或URL部分作为目录名。")
            try:
                meaningful_part = novel_url.strip("/").split("/")[-1]
                if '.html' in meaningful_part or '.htm' in meaningful_part:
                    meaningful_part = meaningful_part.split('.')[0]
                cleaned_novel_title = self._clean_filename(meaningful_part)
                if not cleaned_novel_title:
                    cleaned_novel_title = self._clean_filename(self.site_name)
            except Exception:
                cleaned_novel_title = self._clean_filename(self.site_name)
        
        if not cleaned_novel_title:
            cleaned_novel_title = "untitled_novel"

        novel_output_dir = os.path.join(output_dir, cleaned_novel_title)
        os.makedirs(novel_output_dir, exist_ok=True)
        print(f"小说将保存到目录: {novel_output_dir}")

        # 初始化计数器和章节列表
        downloaded_count = 0
        failed_count = 0
        original_total_chapters = len(chapters)
        chapters_to_download = []

        if selected_chapters:
            # 筛选章节
            for i, (raw_chapter_title, chapter_url) in enumerate(chapters):
                chapter_num_1_based = i + 1
                if chapter_num_1_based in selected_chapters:
                    chapters_to_download.append(((raw_chapter_title, chapter_url), chapter_num_1_based))
            if not chapters_to_download:
                print(f"指定的章节序号 {selected_chapters} 在解析到的 {original_total_chapters} 个章节中均未找到。未下载任何章节。")
                return
            print(f"将从 {original_total_chapters} 个总章节中下载 {len(chapters_to_download)} 个选定章节。")
        else:
            # 下载所有章节
            for i, (raw_chapter_title, chapter_url) in enumerate(chapters):
                chapters_to_download.append(((raw_chapter_title, chapter_url), i + 1))

        effective_total_chapters_to_process = len(chapters_to_download)

        # 下载章节
        for current_processing_index, ((raw_chapter_title_from_toc, chapter_url), original_chapter_index) in enumerate(chapters_to_download):
            progress_index = current_processing_index + 1 
            print(f"处理选定列表中的第 {progress_index}/{effective_total_chapters_to_process} 项 (原目录序号 {original_chapter_index}): '{raw_chapter_title_from_toc}' ({chapter_url})", end='')
            
            if self.download_chapter(chapter_url, novel_output_dir, original_chapter_index, raw_chapter_title_from_toc):
                downloaded_count += 1
            else:
                failed_count += 1
                print(f"下载或处理章节失败: {raw_chapter_title_from_toc} ({chapter_url}) (原序号 {original_chapter_index})")

        print(f"\n小说下载完成: {novel_title_from_parser if novel_title_from_parser else novel_url}")
        if selected_chapters:
            print(f"原总章节数: {original_total_chapters}")
            print(f"请求下载章节数: {len(selected_chapters)} (实际匹配并尝试下载: {effective_total_chapters_to_process})")
        else:
            print(f"总章节数: {original_total_chapters}")
        print(f"成功下载/处理章节数: {downloaded_count}")
        
        # 合并为epub和txt
        try:
            print("\n开始合并文件...")
            txt_path = self._merge_to_txt(novel_output_dir, cleaned_novel_title)
            print(f"已生成txt文件: {txt_path}")
            
            epub_path = self._merge_to_epub(novel_output_dir, cleaned_novel_title)
            print(f"已生成epub文件: {epub_path}")
        except Exception as e:
            print(f"合并文件时发生错误: {e}")
        
        if failed_count > 0:
            print("部分章节下载失败，请检查日志。")

    def list_chapters(self, novel_url: str) -> None:
        """
        获取并打印小说目录（包括所有分页）。
        """
        print(f"开始获取小说目录: {novel_url}")
        logger.info(f"调用 list_chapters 获取目录: {novel_url}")

        toc_html_content = self.get_html(novel_url)
        if not toc_html_content:
            logger.error(f"获取小说目录页失败: {novel_url}")
            print(f"获取小说目录页失败: {novel_url}")
            return

        # parse_novel_toc 负责处理所有分页逻辑
        logger.debug(f"准备调用 self.parser.parse_novel_toc for {novel_url}")
        novel_title, chapters = self.parser.parse_novel_toc(toc_html_content, self.session, novel_url)
        logger.debug(f"self.parser.parse_novel_toc 调用完毕. 获取到标题: '{novel_title}', 章节数: {len(chapters) if chapters else 0}")

        if novel_title:
            print(f"\n小说标题: {novel_title}")
        else:
            print("\n未能解析到小说标题。")

        if chapters:
            print(f"共找到 {len(chapters)} 章：")
            for i, (title, url) in enumerate(chapters):
                print(f"  {i+1:04d}: {title} ({url})")
        else:
            print("未能解析到任何章节。")
        
        logger.info(f"目录列表示例完成。共找到 {len(chapters) if chapters else 0} 章。")

# 示例用法
if __name__ == '__main__':
    # 假设的网站配置
    mock_site_config = {
        "site_name": "my_example_site",
        "base_url": "http://www.examplefakedomain.com", # 示例，需要替换为真实网站
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        },
        "proxies": None, # 例如: {"http": "http://10.10.1.10:3128", "https": "http://10.10.1.10:1080"}
        "download_delay": 1.5, # 下载每章节后的延迟时间（秒）
        # 解析规则 (这些会被 ExampleParser 使用)
        "novel_toc_url_pattern": "/book/{book_id}/", # 小说目录页 URL 模式 (示例)
        "chapter_url_pattern": "/book/{book_id}/{chapter_id}.html", # 章节页 URL 模式 (示例)
        "novel_title_selector": "h1.title", # 小说标题 CSS 选择器 (示例)
        "chapter_list_selector": "div.chapter-list ul li a", # 章节列表项 CSS 选择器 (示例)
        "chapter_title_selector": "h2.chapter-title", # 章节标题 CSS 选择器 (示例)
        "chapter_content_selector": "div.content", # 章节内容 CSS 选择器 (示例)
        "cache_settings": {"enabled": False},
        "title_patterns": {
            "remove_regex": "\\s*-\\s*[Pp]art\\.\\s*\\d+\\s*$" # 示例：移除 " - Part. X"
        },
        "chapter_splitting_enabled": True,
        "chapter_splitting_regex": "^(Section\\s+\\d+.*)$", # 示例：按 "Section X" 切分
        "in_content_splitting": {
            "enabled": True,
            "header_regex": "^(Section\\s+\\d+.*)$"
        }
    }

    # downloader = ExampleDownloader(site_config=mock_site_config, cache_dir="../cache_test")
    
    # 示例：下载一本小说 (需要提供真实的小说目录页 URL)
    # test_novel_url = "http://www.examplefakedomain.com/book/12345/" # 需要替换
    # downloader.download_novel(test_novel_url, "../output_test")

    # 示例：下载单个章节 (需要提供真实的章节 URL 和输出路径)
    # test_chapter_url = "http://www.examplefakedomain.com/book/12345/chapter1.html" # 需要替换
    # downloader.download_chapter(test_chapter_url, "../output_test/example_novel/0001_example_chapter.txt")
    print("ExampleDownloader 模块已加载。取消注释并修改上述示例代码以进行测试。") 