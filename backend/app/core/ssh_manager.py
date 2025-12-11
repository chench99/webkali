import paramiko
import os
from app.core.config import settings


class SSHManager:
    def __init__(self):
        self.client = None
        self.sftp = None
        self.host = settings.KALI_HOST
        self.user = settings.KALI_USER
        self.password = settings.KALI_PASS

    def connect(self):
        """建立 SSH 连接 (带详细调试信息)"""
        # 如果已经连上了，先跳过
        if self.client and self.client.get_transport() and self.client.get_transport().is_active():
            return

        print(f"------------ SSH DEBUG START ------------")
        print(f"[*] Python 配置读取到的目标 IP: {self.host}")
        print(f"[*] Python 配置读取到的用户名: {self.user}")
        print(f"[*] 正在尝试建立连接...")

        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 强制设置超时时间为 10 秒
            self.client.connect(
                self.host,
                port=settings.KALI_PORT,
                username=self.user,
                password=self.password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=30
            )

            self.sftp = self.client.open_sftp()
            print(f"[+] 成功！SSH 连接已建立！")

        except Exception as e:
            print(f"❌ 连接失败！具体报错原因如下：")
            print(f"ERROR TYPE: {type(e)}")
            print(f"ERROR MSG: {e}")
            self.client = None
            # 不要在这里 raise，否则主程序会崩，我们让它打印出来就好

        print(f"------------ SSH DEBUG END ------------")
    def exec_command(self, cmd, background=False):
        """执行命令"""
        if not self.client: self.connect()

        # 加上 source /etc/profile 确保环境变量加载
        full_cmd = f"source /etc/profile; {cmd}"

        if background:
            # 后台执行，不等待结果 (如 nohup)
            full_cmd = f"nohup sh -c '{full_cmd}' > /dev/null 2>&1 &"

        stdin, stdout, stderr = self.client.exec_command(full_cmd)
        return stdin, stdout, stderr

    def upload_payload(self, local_path, remote_filename):
        """上传脚本到 Kali 的临时目录"""
        if not self.sftp: self.connect()
        remote_path = f"/tmp/{remote_filename}"
        try:
            self.sftp.put(local_path, remote_path)
            return remote_path
        except Exception as e:
            print(f"[!] Upload Failed: {e}")
            return None

    def download_file(self, remote_path, local_path):
        """从 Kali 下载文件 (如握手包)"""
        if not self.sftp: self.connect()
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self.sftp.get(remote_path, local_path)
            return True
        except Exception as e:
            print(f"[!] Download Failed: {e}")
            return False


# 单例模式导出
ssh_client = SSHManager()