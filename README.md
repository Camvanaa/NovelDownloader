# 小说下载器 (Novel Downloader)

一个用Python编写的小说下载工具，支持多个小说网站，具有缓存功能和灵活的配置选项。
前排提醒：用ai瞎几把乱写的

## 特性

- 支持多个小说网站
- 灵活的配置系统
- 文件缓存功能
- 自动生成epub和txt格式
- 支持选择性下载章节
- 自定义请求头和代理设置
- 内容分章功能
- 日志记录系统

## 安装

1. 克隆仓库：
```bash
git clone [repository-url]
cd noveldownloader
```

2. 创建并激活虚拟环境（可选但推荐）：
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

## 使用方法

### 基本使用

```python
from noveldownloader.downloaders.example_downloader import ExampleDownloader

# 配置示例
site_config = {
    "site_name": "example_site",
    "headers": {
        "User-Agent": "Mozilla/5.0 ..."
    },
    "cache_settings": {
        "enabled": True,
        "expires_in_seconds": 3600
    }
}

# 创建下载器实例
downloader = ExampleDownloader(site_config)

# 下载小说
downloader.download_novel("https://example.com/book/123", "output")
```

### 选择性下载章节

```python
# 只下载第1、3、5章
downloader.download_novel("https://example.com/book/123", "output", selected_chapters=[1, 3, 5])
```

### 查看目录

```python
# 列出小说所有章节
downloader.list_chapters("https://example.com/book/123")
```

## 配置说明

配置文件支持以下选项：

```python
{
    "site_name": "站点名称",
    "headers": {
        "User-Agent": "浏览器标识",
        # 其他请求头...
    },
    "proxies": {
        "http": "http代理地址",
        "https": "https代理地址"
    },
    "cache_settings": {
        "enabled": True,  # 是否启用缓存
        "expires_in_seconds": 3600  # 缓存过期时间
    },
    "download_delay": 1.0  # 下载延迟（秒）
}
```

## 输出格式

下载完成后会在输出目录生成：
- 单独的章节txt文件
- 完整的txt合集文件
- epub格式电子书（带目录）

## 注意事项

1. 请遵守网站的使用条款和robots.txt规则
2. 建议设置适当的下载延迟，避免对目标网站造成压力
3. 下载的内容仅供个人学习使用

## 许可证

MIT License 