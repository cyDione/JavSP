"""AI辅助提取番号"""
import logging
from typing import Optional

import requests
from pydantic_core import Url


__all__ = ['extract_avid_by_ai', 'check_ai_connection']


from javsp.config import Cfg


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个日本AV番号识别专家。请从以下文件名中提取番号（DVD ID）。

番号的常见格式：
1. 标准格式：字母+数字，如 "ABC-123"、"MIDV-001"
2. FC2格式：如 "FC2-123456"、"FC2PPV-123456"
3. 无码格式：纯数字，如 "123456-789"、"010120_001"
4. Heydouga格式：如 "heydouga-4017-123"
5. 特殊格式：如 "T28-123"、"259LUXU-123"、"GETCHU-123456"

规则：
- 只返回番号本身，不要包含任何其他文字或解释
- 如果番号缺少连字符，请添加（如 "ABC123" -> "ABC-123"）
- 如果无法识别，返回空字符串
- 优先匹配最明显的番号"""


def extract_avid_by_ai(filepath_str: str) -> str:
    """使用AI从文件名中提取番号
    
    Args:
        filepath_str: 文件路径或文件名
        
    Returns:
        str: 提取的番号，如果无法识别则返回空字符串
    """
    cfg = Cfg()
    if not cfg.ai_extractor.enabled or cfg.ai_extractor.engine is None:
        return ''
    
    engine = cfg.ai_extractor.engine
    
    # 只使用文件名，不使用完整路径
    import os
    filename = os.path.basename(filepath_str)
    
    try:
        result = _call_openai_api(filename, engine.url, engine.api_key, engine.model)
        if result:
            # 清理结果：去除空白字符和引号
            result = result.strip().strip('"\'')
            # 验证结果格式（简单检查是否看起来像番号）
            if _is_valid_avid(result):
                logger.info(f"AI成功识别番号: '{filename}' -> '{result}'")
                return result
            else:
                logger.debug(f"AI返回的结果不是有效番号: '{result}'")
    except Exception as e:
        logger.error(f"AI提取番号时出错: {e}")
    
    return ''


def check_ai_connection() -> bool:
    """检查AI API连接是否正常"""
    cfg = Cfg()
    if not cfg.ai_extractor.enabled:
        return True
    
    if cfg.ai_extractor.engine is None:
        logger.warning("AI功能已启用但未配置引擎")
        return False
        
    engine = cfg.ai_extractor.engine
    logger.info(f"正在测试AI连接 ({engine.model})...")
    
    try:
        # 使用简单的测试消息
        result = _call_openai_api("Test Connection", engine.url, engine.api_key, engine.model)
        if result is not None:
            logger.info("AI连接测试成功")
            return True
        else:
            logger.warning("AI连接测试失败: 无响应")
            return False
    except Exception as e:
        logger.warning(f"AI连接测试失败: {e}")
        return False


def _call_openai_api(filename: str, url: Url, api_key: str, model: str) -> Optional[str]:
    """调用OpenAI兼容API提取番号"""
    # 简单的速率限制
    import time
    rpm = Cfg().ai_extractor.request_per_minute
    if rpm > 0:
        interval = 60.0 / rpm
        last_req_time = getattr(_call_openai_api, 'last_req_time', 0)
        now = time.time()
        wait_time = interval - (now - last_req_time)
        if wait_time > 0:
            logger.debug(f"AI速率限制: 等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)
        _call_openai_api.last_req_time = time.time()

    api_url = str(url)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"文件名: {filename}"
            }
        ],
        "model": model,
        "temperature": 0,
        "max_tokens": 50,  # 番号很短，不需要太多token
    }
    
    r = requests.post(api_url, headers=headers, json=data, timeout=30)
    
    if r.status_code == 200:
        try:
            response = r.json()
        except requests.exceptions.JSONDecodeError:
            logger.error(f"AI API返回了非JSON格式的数据: {r.text[:200]}...")  # 只打印前200个字符避免太长
            return None
            
        if 'error' in response:
            logger.error(f"AI API返回错误: {response['error']}")
            return None
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip()
    else:
        logger.error(f"AI API请求失败: {r.status_code} - {r.reason} - {r.text[:200]}")
        return None


def _is_valid_avid(avid: str) -> bool:
    """简单验证番号格式是否有效"""
    import re
    
    if not avid or len(avid) < 3 or len(avid) > 30:
        return False
    
    # 常见的番号模式
    patterns = [
        r'^[A-Z]{2,10}[-_]\d{2,5}[A-Z]?$',      # ABC-123, ABW-123z
        r'^FC2[-_]?\d{5,7}$',                     # FC2-123456
        r'^\d{6}[-_]\d{2,3}$',                    # 123456-789
        r'^[A-Z]+\d{2,5}$',                       # ABC123 (缺少连字符)
        r'^HEYDOUGA[-_]\d{4}[-_]\d{3,5}$',       # heydouga-4017-123
        r'^GETCHU[-_]\d+$',                       # GETCHU-123456
        r'^GYUTTO[-_]\d+$',                       # GYUTTO-123456
        r'^T[23]8[-_]\d{3}$',                     # T28-123
        r'^\d{3}LUXU[-_]\d+$',                    # 259LUXU-123
        r'^[NK]\d{4}$',                           # N1234, K1234
    ]
    
    avid_upper = avid.upper()
    for pattern in patterns:
        if re.match(pattern, avid_upper, re.I):
            return True
    
    return False
