"""远程文件系统支持模块"""
import os
import logging
from abc import ABC, abstractmethod
from ftplib import FTP
from typing import Iterator, List, Tuple, Optional
from urllib.parse import urlparse

__all__ = ['get_filesystem', 'RemoteFileSystem', 'LocalFileSystem', 'FTPFileSystem', 'SMBFileSystem']

from javsp.config import Cfg

logger = logging.getLogger(__name__)


class RemoteFileSystem(ABC):
    """远程文件系统抽象基类"""
    
    @abstractmethod
    def walk(self, path: str) -> Iterator[Tuple[str, List[str], List[str]]]:
        """遍历目录，返回 (dirpath, dirnames, filenames) 元组"""
        pass
    
    @abstractmethod
    def get_size(self, path: str) -> int:
        """获取文件大小（字节）"""
        pass
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查路径是否存在"""
        pass
    
    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """检查路径是否为目录"""
        pass
    
    def join(self, *paths) -> str:
        """连接路径"""
        return '/'.join(p.strip('/') for p in paths if p)


class LocalFileSystem(RemoteFileSystem):
    """本地文件系统实现"""
    
    def walk(self, path: str) -> Iterator[Tuple[str, List[str], List[str]]]:
        yield from os.walk(path)
    
    def get_size(self, path: str) -> int:
        return os.path.getsize(path)
    
    def exists(self, path: str) -> bool:
        return os.path.exists(path)
    
    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)
    
    def join(self, *paths) -> str:
        return os.path.join(*paths)


class FTPFileSystem(RemoteFileSystem):
    """FTP文件系统实现"""
    
    def __init__(self, host: str, port: int = 21, username: str = "anonymous", 
                 password: str = "", encoding: str = "utf-8"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.encoding = encoding
        self._ftp: Optional[FTP] = None
    
    def _connect(self) -> FTP:
        """获取或创建FTP连接"""
        if self._ftp is None:
            logger.info(f"连接FTP服务器: {self.host}:{self.port}")
            self._ftp = FTP()
            self._ftp.encoding = self.encoding
            self._ftp.connect(self.host, self.port)
            self._ftp.login(self.username, self.password)
            logger.info(f"FTP登录成功: {self.username}@{self.host}")
        return self._ftp
    
    def walk(self, path: str) -> Iterator[Tuple[str, List[str], List[str]]]:
        """递归遍历FTP目录"""
        ftp = self._connect()
        dirs_to_visit = [path]
        
        while dirs_to_visit:
            current_dir = dirs_to_visit.pop(0)
            try:
                ftp.cwd(current_dir)
            except Exception as e:
                logger.error(f"无法进入FTP目录 {current_dir}: {e}")
                continue
            
            dirnames = []
            filenames = []
            
            # 获取目录列表
            items = []
            try:
                ftp.retrlines('MLSD', lambda x: items.append(x))
            except:
                # 如果MLSD不支持，使用NLST
                try:
                    names = ftp.nlst()
                    for name in names:
                        if name in ('.', '..'):
                            continue
                        try:
                            ftp.cwd(name)
                            ftp.cwd('..')
                            dirnames.append(name)
                        except:
                            filenames.append(name)
                    yield (current_dir, dirnames, filenames)
                    for dirname in dirnames:
                        dirs_to_visit.append(self.join(current_dir, dirname))
                    continue
                except Exception as e:
                    logger.error(f"无法列出FTP目录 {current_dir}: {e}")
                    continue
            
            for item in items:
                parts = item.split(';')
                name = parts[-1].strip()
                if name in ('.', '..'):
                    continue
                
                item_type = 'file'
                for part in parts[:-1]:
                    if part.lower().startswith('type='):
                        item_type = part.split('=')[1].lower()
                        break
                
                if item_type == 'dir':
                    dirnames.append(name)
                elif item_type == 'file':
                    filenames.append(name)
            
            yield (current_dir, dirnames, filenames)
            
            for dirname in dirnames:
                dirs_to_visit.append(self.join(current_dir, dirname))
    
    def get_size(self, path: str) -> int:
        """获取FTP文件大小"""
        ftp = self._connect()
        try:
            return ftp.size(path) or 0
        except:
            return 0
    
    def exists(self, path: str) -> bool:
        """检查FTP路径是否存在"""
        ftp = self._connect()
        try:
            ftp.cwd(path)
            ftp.cwd('/')
            return True
        except:
            try:
                ftp.size(path)
                return True
            except:
                return False
    
    def is_dir(self, path: str) -> bool:
        """检查FTP路径是否为目录"""
        ftp = self._connect()
        try:
            current = ftp.pwd()
            ftp.cwd(path)
            ftp.cwd(current)
            return True
        except:
            return False
    
    def close(self):
        """关闭FTP连接"""
        if self._ftp:
            try:
                self._ftp.quit()
            except:
                pass
            self._ftp = None


class SMBFileSystem(RemoteFileSystem):
    """SMB文件系统实现"""
    
    def __init__(self, host: str, share: str, path: str = "/",
                 username: str = None, password: str = None, port: int = 445):
        self.host = host
        self.share = share
        self.base_path = path
        self.username = username
        self.password = password
        self.port = port
        self._session = None
        self._tree = None
    
    def _connect(self):
        """获取或创建SMB连接"""
        if self._session is None:
            try:
                from smbprotocol.session import Session
                from smbprotocol.tree import TreeConnect
                from smbprotocol.connection import Connection
                
                logger.info(f"连接SMB服务器: {self.host}:{self.port}")
                
                conn = Connection(uuid=None, server=self.host, port=self.port)
                conn.connect()
                
                self._session = Session(conn, username=self.username or "", 
                                        password=self.password or "")
                self._session.connect()
                
                share_path = f"\\\\{self.host}\\{self.share}"
                self._tree = TreeConnect(self._session, share_path)
                self._tree.connect()
                
                logger.info(f"SMB连接成功: {self.host}/{self.share}")
            except ImportError:
                raise ImportError("请安装smbprotocol库: pip install smbprotocol")
        return self._tree
    
    def walk(self, path: str) -> Iterator[Tuple[str, List[str], List[str]]]:
        """递归遍历SMB目录"""
        try:
            from smbclient import scandir, stat as smb_stat
            import smbclient
            
            # 注册会话
            if self.username and self.password:
                smbclient.register_session(
                    self.host, 
                    username=self.username, 
                    password=self.password,
                    port=self.port
                )
            
            smb_path_suffix = path.replace('/', '\\')
            smb_path = f"\\\\{self.host}\\{self.share}{smb_path_suffix}"
            
            dirs_to_visit = [smb_path]
            
            while dirs_to_visit:
                current_dir = dirs_to_visit.pop(0)
                dirnames = []
                filenames = []
                
                try:
                    for entry in scandir(current_dir):
                        if entry.is_dir():
                            dirnames.append(entry.name)
                            dirs_to_visit.append(f"{current_dir}\\{entry.name}")
                        else:
                            filenames.append(entry.name)
                except Exception as e:
                    logger.error(f"无法遍历SMB目录 {current_dir}: {e}")
                    continue
                
                # 转换回Unix风格路径
                unix_path = current_dir.replace('\\\\', '/').replace('\\', '/')
                yield (unix_path, dirnames, filenames)
                
        except ImportError:
            raise ImportError("请安装smbclient库: pip install smbprotocol")
    
    def get_size(self, path: str) -> int:
        """获取SMB文件大小"""
        try:
            from smbclient import stat as smb_stat
            smb_path_suffix = path.replace('/', '\\')
            smb_path = f"\\\\{self.host}\\{self.share}{smb_path_suffix}"
            return smb_stat(smb_path).st_size
        except:
            return 0
    
    def exists(self, path: str) -> bool:
        """检查SMB路径是否存在"""
        try:
            from smbclient import stat as smb_stat
            smb_path_suffix = path.replace('/', '\\')
            smb_path = f"\\\\{self.host}\\{self.share}{smb_path_suffix}"
            smb_stat(smb_path)
            return True
        except:
            return False
    
    def is_dir(self, path: str) -> bool:
        """检查SMB路径是否为目录"""
        try:
            from smbclient import stat as smb_stat
            import stat
            smb_path_suffix = path.replace('/', '\\')
            smb_path = f"\\\\{self.host}\\{self.share}{smb_path_suffix}"
            return stat.S_ISDIR(smb_stat(smb_path).st_mode)
        except:
            return False


def get_filesystem() -> RemoteFileSystem:
    """根据配置返回对应的文件系统实例"""
    cfg = Cfg()
    remote_fs = cfg.scanner.remote_fs
    
    if remote_fs is None or remote_fs.type == 'local':
        return LocalFileSystem()
    
    if remote_fs.type == 'ftp':
        if remote_fs.ftp is None:
            raise ValueError("FTP配置缺失，请在config.yml中配置scanner.remote_fs.ftp")
        return FTPFileSystem(
            host=remote_fs.ftp.host,
            port=remote_fs.ftp.port,
            username=remote_fs.ftp.username,
            password=remote_fs.ftp.password,
            encoding=remote_fs.ftp.encoding
        )
    
    if remote_fs.type == 'smb':
        if remote_fs.smb is None:
            raise ValueError("SMB配置缺失，请在config.yml中配置scanner.remote_fs.smb")
        return SMBFileSystem(
            host=remote_fs.smb.host,
            share=remote_fs.smb.share,
            path=remote_fs.smb.path,
            username=remote_fs.smb.username,
            password=remote_fs.smb.password,
            port=remote_fs.smb.port
        )
    
    raise ValueError(f"不支持的远程文件系统类型: {remote_fs.type}")


def parse_remote_url(url: str) -> Tuple[str, dict]:
    """解析远程URL，返回 (类型, 配置字典)
    
    支持格式:
    - ftp://user:pass@host:port/path
    - smb://user:pass@host/share/path
    """
    parsed = urlparse(url)
    
    if parsed.scheme == 'ftp':
        return 'ftp', {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 21,
            'username': parsed.username or 'anonymous',
            'password': parsed.password or '',
            'path': parsed.path or '/'
        }
    elif parsed.scheme in ('smb', 'cifs'):
        # SMB路径格式: smb://host/share/path
        path_parts = parsed.path.strip('/').split('/', 1)
        share = path_parts[0] if path_parts else ''
        path = '/' + path_parts[1] if len(path_parts) > 1 else '/'
        return 'smb', {
            'host': parsed.hostname or 'localhost',
            'share': share,
            'path': path,
            'username': parsed.username,
            'password': parsed.password,
            'port': parsed.port or 445
        }
    else:
        return 'local', {'path': url}
