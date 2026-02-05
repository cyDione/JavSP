"""AI辅助提取番号"""
import logging
from typing import Optional

import requests
from pydantic_core import Url


__all__ = ['extract_avid_by_ai', 'check_ai_connection', 'batch_extract_avid']


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


    return ''


def batch_extract_avid(filepaths: list[str]) -> dict[str, str]:
    """批量使用AI从文件路径中提取番号
    
    Args:
        filepaths: 文件路径列表
        
    Returns:
        dict: 文件路径 -> 提取的番号
    """
    cfg = Cfg()
    if not cfg.ai_extractor.enabled or cfg.ai_extractor.engine is None or not filepaths:
        return {}
    
    # 过滤掉非视频文件（可选，暂时全部提交因为调用方已经过滤过一次）
    # 分批处理，避免Prompt过长
    BATCH_SIZE = 20
    results = {}
    
    import math
    total_batches = math.ceil(len(filepaths) / BATCH_SIZE)
    
    for i in range(total_batches):
        batch = filepaths[i*BATCH_SIZE : (i+1)*BATCH_SIZE]
        try:
            batch_result = _call_openai_api_batch(batch, cfg.ai_extractor.engine)
            if batch_result:
                results.update(batch_result)
        except Exception as e:
            logger.error(f"批量提取番号失败 (Batch {i+1}/{total_batches}): {e}")
            
    return results


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
    """调用OpenAI兼容API提取番号（单条）"""
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
        "max_tokens": 50,
    }
    
    try:
        r = requests.post(api_url, headers=headers, json=data, timeout=30)
        if r.status_code == 200:
            try:
                response = r.json()
            except requests.exceptions.JSONDecodeError:
                logger.error(f"AI API返回了非JSON格式的数据: {r.text[:200]}...")
                return None
                
            if 'error' in response:
                logger.error(f"AI API返回错误: {response['error']}")
                return None
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip()
        else:
            logger.error(f"AI API请求失败: {r.status_code} - {r.reason}")
            return None
    except Exception as e:
        logger.error(f"请求AI API时发生异常: {e}")
        return None

def _call_openai_api_batch(filepaths: list[str], engine) -> dict[str, str]:
    """批量调用API"""
    import json
    import time
    
    # 速率限制复用单条调用的逻辑，或者单独计算
    rpm = Cfg().ai_extractor.request_per_minute
    if rpm > 0:
        interval = 60.0 / rpm
        # 这里把一次批量请求算作一次API调用，或者根据需要调整
        last_req_time = getattr(_call_openai_api, 'last_req_time', 0)
        now = time.time()
        wait_time = interval - (now - last_req_time)
        if wait_time > 0:
            logger.debug(f"AI速率限制: 等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)
        _call_openai_api.last_req_time = time.time()

    api_url = str(engine.url)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {engine.api_key}",
    }
    
    files_str = "\n".join(filepaths)
    
    batch_system_prompt = """你是一个日本AV番号识别专家。请从以下文件路径列表中提取番号（DVD ID）。

请严格遵循以下规则：
1. 分析每个文件路径，提取其中包含的番号。
2. 忽略路径中的目录部分，主要关注文件名，但如果有用的信息在父目录中也可以参考。
3. 返回一个标准的 JSON 对象。
   - Key (键): 文件路径 (必须与输入完全一致)
   - Value (值): 提取到的番号 (字符串)。如果无法识别，这通常是空字符串或者 null。
4. 番号格式示例: "ABC-123", "FC2-123456", "123456-789"。如果原文件名中缺少连字符，请补全。
5. 不要返回 JSON 以外的任何内容。不要使用Markdown代码块格式。直接返回原始 JSON 字符串。
"""

    data = {
        "messages": [
            {
                "role": "system",
                "content": batch_system_prompt
            },
            {
                "role": "user",
                "content": files_str
            }
        ],
        "model": engine.model,
        "temperature": 0,
        "response_format": { "type": "json_object" }, # 尝试强制 JSON 模式，部分模型支持
    }
    
    try:
        r = requests.post(api_url, headers=headers, json=data, timeout=60) # 批量处理超时时间长一点
        if r.status_code == 200:
            try:
                response = r.json()
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                # 清理可能存在的 markdown 代码块标记
                content = content.replace('```json', '').replace('```', '').strip()
                result_dict = json.loads(content)
                
                # 简单验证和清理
                validated_results = {}
                for fpath, avid in result_dict.items():
                    if avid and _is_valid_avid(avid):
                        validated_results[fpath] = avid
                    elif fpath in filepaths: # 确保路径存在于请求中
                        validated_results[fpath] = "" # 无法识别
                return validated_results
            except json.JSONDecodeError:
                logger.error(f"AI返回的不是有效的JSON: {content[:200]}...")
                return {}
            except Exception as e:
                logger.error(f"解析批量响应时出错: {e}")
                return {}
        else:
            logger.error(f"AI API批量请求失败: {r.status_code} - {r.reason}")
            return {}
    except Exception as e:
        logger.error(f"请求AI API时发生异常: {e}")
        return {}


def _is_valid_avid(avid: str) -> bool:
    """简单验证番号格式是否有效"""
    import re
    if not isinstance(avid, str): return False
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
