import paramiko
import os
import time
from app.core.config import settings

class SSHManager:
    def __init__(self):
        self.client = None
        self.sftp = None
        self.host = settings.KALI_HOST
        self.user = settings.KALI_USER
        self.password = settings.KALI_PASS

    def connect(self):
        """建立 SSH 连接"""
        if self.client:
            try:
                if self.client.get_transport().is_active():
                    return
            except:
                pass

        print(f"[*] SSH Connecting to {self.host}...")
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                self.host,
                port=settings.KALI_PORT,
                username=self.user,
                password=self.password,
                timeout=10,
                banner_timeout=60, # 稍微调大防止由于Kali卡顿导致的连接失败
                allow_agent=False,
                look_for_keys=False
            )
            # 开启 KeepAlive 防止长时间抓包断连
            self.client.get_transport().set_keepalive(30)
            self.sftp = self.client.open_sftp()
            print(f"[+] SSH Connected!")
        except Exception as e:
            print(f"❌ SSH Connection Failed: {e}")
            self.client = None
            raise e

    def exec_command(self, cmd, background=False, timeout=None, get_pty=False):
        """
        :param get_pty: 关键参数！
            - 扫描WiFi时设为 False (否则会卡住)
            - 抓握手包时设为 True (否则后端收不到 print 输出)
        """
        try:
            self.connect()
        except:
            return None, None, None

        full_cmd = f"source /etc/profile; {cmd}"
        if background:
            full_cmd = f"nohup sh -c '{full_cmd}' > /dev/null 2>&1 &"

        try:
            # 传递 get_pty 参数
            stdin, stdout, stderr = self.client.exec_command(
                full_cmd, 
                timeout=timeout, 
                get_pty=get_pty 
            )
            return stdin, stdout, stderr
        except Exception as e:
            print(f"[!] Command Exec Error: {e}, Retrying...")
            self.client = None
            try:
                self.connect()
                stdin, stdout, stderr = self.client.exec_command(
                    full_cmd, 
                    timeout=timeout, 
                    get_pty=get_pty
                )
                return stdin, stdout, stderr
            except Exception as final_e:
                raise final_e

    def upload_payload(self, local_path, remote_filename):
        try:
            self.connect()
            remote_path = f"/tmp/{remote_filename}"
            self.sftp.put(str(local_path), remote_path)
            self.client.exec_command(f"chmod +x {remote_path}")
            return remote_path
        except Exception as e:
            print(f"[!] Upload Failed: {e}")
            return None

    def download_file(self, remote_path, local_path):
        try:
            self.connect()
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            try:
                self.sftp.stat(remote_path) # 检查文件是否存在
            except IOError:
                return False
            self.sftp.get(remote_path, str(local_path))
            return True
        except Exception:
            return False

ssh_client = SSHManager()