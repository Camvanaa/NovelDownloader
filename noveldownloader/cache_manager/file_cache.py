import os
import hashlib
import json
import time

class FileCache:
    """
    一个简单的基于文件的缓存系统。
    它将数据存储在指定目录下的文件中，文件名是基于缓存键的哈希值。
    可以设置缓存的过期时间。
    """
    def __init__(self, cache_dir="cache", expires_in_seconds=None):
        """
        初始化文件缓存。

        Args:
            cache_dir (str): 缓存文件存储的目录。
            expires_in_seconds (int, optional): 缓存的默认过期时间（秒）。
                                                None 表示永不过期。
        """
        self.cache_dir = cache_dir
        self.expires_in_seconds = expires_in_seconds
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except OSError as e:
                print(f"创建缓存目录失败: {self.cache_dir}, 错误: {e}")
                # 可以考虑抛出异常或使用一个备用目录
                self.cache_dir = ".cache_fallback" # 示例性的备用方案
                os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_filepath(self, key: str) -> str:
        """根据键生成缓存文件的完整路径。"""
        # 使用 SHA256 哈希作为文件名以避免非法字符和过长文件名
        # 同时保留部分原始 key 以增加可读性 (如果 key 是 URL)
        safe_key_part = re.sub(r'[^a-zA-Z0-9_.-]', '_', key)[:50] # 取前50个安全字符
        hashed_key = hashlib.sha256(key.encode('utf-8')).hexdigest()
        # 文件名可以包含部分原始信息和哈希，例如：url_xxxxx_hash.json
        # 这里为了简单，仅使用哈希
        # filename = f"{safe_key_part}_{hashed_key}.cache"
        filename = f"{hashed_key}.cache.json" # 假设我们缓存json或文本
        return os.path.join(self.cache_dir, filename)

    def get(self, key: str) -> any:
        """
        从缓存中获取数据。

        Args:
            key (str): 缓存键。

        Returns:
            any: 缓存的数据，如果缓存不存在、已过期或读取失败，则返回 None。
        """
        filepath = self._get_cache_filepath(key)
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data_wrapper = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"读取或解析缓存文件失败: {filepath}, 错误: {e}")
            # 可以选择删除损坏的缓存文件
            # os.remove(filepath)
            return None

        # 检查缓存是否已过期
        if self.expires_in_seconds is not None:
            created_at = data_wrapper.get("created_at", 0)
            if time.time() - created_at > self.expires_in_seconds:
                print(f"缓存已过期: {key}")
                self.delete(key) # 删除过期的缓存
                return None
        
        # print(f"从缓存加载: {key}")
        return data_wrapper.get("payload")

    def set(self, key: str, value: any, expires_in_seconds: int = None) -> bool:
        """
        将数据存入缓存。

        Args:
            key (str): 缓存键。
            value (any): 要缓存的数据 (应可被 JSON 序列化)。
            expires_in_seconds (int, optional): 特定于此条目的过期时间（秒）。
                                                如果为 None，则使用实例的默认过期时间。
                                                如果为 0，表示永不过期 (覆盖实例默认)。
        Returns:
            bool: 存储成功返回 True，否则返回 False。
        """
        filepath = self._get_cache_filepath(key)
        
        current_time = time.time()
        
        # 决定此条目的过期设置
        entry_expires_in = self.expires_in_seconds
        if expires_in_seconds is not None:
            entry_expires_in = expires_in_seconds if expires_in_seconds > 0 else None

        data_wrapper = {
            "payload": value,
            "created_at": current_time,
            "key_hint": key[:200] # 存储部分原始 key 用于调试
        }

        try:
            # 确保缓存目录存在，以防在init后被删除
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_wrapper, f, ensure_ascii=False, indent=4)
            # print(f"缓存已保存: {key} -> {filepath}")
            return True
        except (IOError, TypeError, json.JSONDecodeError) as e: # TypeError for non-serializable
            print(f"写入缓存文件失败: {filepath}, 错误: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        从缓存中删除数据。

        Args:
            key (str): 缓存键。
        Returns:
            bool: 删除成功或文件不存在返回 True，否则返回 False。
        """
        filepath = self._get_cache_filepath(key)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                # print(f"缓存已删除: {key}")
                return True
            except OSError as e:
                print(f"删除缓存文件失败: {filepath}, 错误: {e}")
                return False
        return True # 文件不存在也视为删除成功

    def clear(self) -> bool:
        """
        清空所有缓存。
        Returns:
            bool: 操作成功返回 True，否则返回 False。
        """
        all_cleared = True
        if not os.path.exists(self.cache_dir):
            print("缓存目录不存在，无需清空。")
            return True
            
        print(f"正在清空缓存目录: {self.cache_dir}")
        for filename in os.listdir(self.cache_dir):
            if filename.endswith(".cache.json"): # 只删除我们创建的缓存文件
                filepath = os.path.join(self.cache_dir, filename)
                try:
                    os.remove(filepath)
                except OSError as e:
                    print(f"删除缓存文件失败: {filepath}, 错误: {e}")
                    all_cleared = False
        if all_cleared:
            print("缓存已清空。")
        else:
            print("部分缓存文件未能清空。")
        return all_cleared

import re # 需要在_get_cache_filepath中使用

# 示例用法
if __name__ == '__main__':
    # 创建一个缓存实例，缓存有效期为 1 小时 (3600 秒)
    # cache = FileCache(cache_dir="../my_app_cache", expires_in_seconds=3600)
    cache = FileCache(cache_dir="./test_cache_dir", expires_in_seconds=5) # 短过期时间用于测试

    cache.clear() # 清理之前的测试缓存

    key1 = "https://api.example.com/data/1"
    data1 = {"name": "示例数据1", "value": 123, "nested": {"id": "a"}}

    key2 = "some_plain_text_key"
    data2 = "这是一段纯文本缓存内容。"
    
    key3 = "https://api.example.com/data/3?param=你好世界"
    data3 = [1, 2, "你好", True, None]

    # 存储数据
    print(f"设置缓存 for {key1}: {cache.set(key1, data1)}")
    print(f"设置缓存 for {key2}: {cache.set(key2, data2, expires_in_seconds=0)}") # 永不过期
    print(f"设置缓存 for {key3}: {cache.set(key3, data3, expires_in_seconds=10)}") 

    # 获取数据
    retrieved_data1 = cache.get(key1)
    print(f"获取缓存 for {key1}: {retrieved_data1}")
    assert retrieved_data1 == data1

    retrieved_data2 = cache.get(key2)
    print(f"获取缓存 for {key2}: {retrieved_data2}")
    assert retrieved_data2 == data2
    
    retrieved_data3 = cache.get(key3)
    print(f"获取缓存 for {key3}: {retrieved_data3}")
    assert retrieved_data3 == data3

    print("\n等待6秒测试过期...")
    time.sleep(6)

    retrieved_data1_after_expiry = cache.get(key1)
    print(f"再次获取缓存 for {key1} (应已过期): {retrieved_data1_after_expiry}")
    assert retrieved_data1_after_expiry is None

    retrieved_data2_after_expiry = cache.get(key2) # key2 设置为永不过期
    print(f"再次获取缓存 for {key2} (应未过期): {retrieved_data2_after_expiry}")
    assert retrieved_data2_after_expiry == data2
    
    retrieved_data3_still_valid = cache.get(key3) # key3 10秒过期，此时应还存在
    print(f"再次获取缓存 for {key3} (应未过期): {retrieved_data3_still_valid}")
    assert retrieved_data3_still_valid == data3
    
    print("\n等待5秒让key3也过期...")
    time.sleep(5)
    retrieved_data3_after_expiry = cache.get(key3)
    print(f"再次获取缓存 for {key3} (应已过期): {retrieved_data3_after_expiry}")
    assert retrieved_data3_after_expiry is None

    # 删除数据
    print(f"删除缓存 for {key2}: {cache.delete(key2)}")
    retrieved_data2_after_delete = cache.get(key2)
    print(f"再次获取缓存 for {key2} (应已删除): {retrieved_data2_after_delete}")
    assert retrieved_data2_after_delete is None

    # 清空所有缓存
    # cache.clear()
    # print("缓存已清空。测试当前目录下是否有 test_cache_dir")

    print("\nFileCache 模块测试完成。手动检查 'test_cache_dir' 目录下的文件。")
    # 可以手动删除 test_cache_dir 以清理测试 