import psutil
from fastapi import APIRouter
from app.core.ssh_manager import ssh_client

router = APIRouter()


@router.get("/status")
def get_system_status():
    """获取 Windows (本机) 和 Kali (远程) 的状态"""

    # 1. 获取 Windows 状态
    win_stats = {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "gpu_temp": "N/A"
    }

    # 2. 获取 Kali 状态 (默认离线)
    kali_stats = {
        "online": False,
        "cpu": 0,
        "ram": 0
    }

    try:
        # 如果 SSH 没连，尝试连一下
        if not ssh_client.client or not ssh_client.client.get_transport() or not ssh_client.client.get_transport().is_active():
            # print("DEBUG: SSH 连接断开，正在重连...")
            ssh_client.connect()

        if ssh_client.client:
            # === 第一层检测：极简存活检测 ===
            # 只要能执行 echo，就说明在线
            try:
                stdin, stdout, stderr = ssh_client.exec_command("echo online")
                check_online = stdout.read().decode().strip()
                if "online" in check_online:
                    kali_stats["online"] = True
            except Exception as e:
                print(f"DEBUG: 存活检测失败 -> {e}")

            # === 第二层检测：只有在线才去获取详细数据 ===
            if kali_stats["online"]:
                try:
                    # 获取负载和内存
                    cmd = "cat /proc/loadavg && free -m"
                    stdin, stdout, stderr = ssh_client.exec_command(cmd)
                    output = stdout.read().decode().strip().split('\n')

                    # 打印 Kali 回复的内容，方便你看有没有数据
                    # print(f"DEBUG: Kali Output Lines -> {len(output)}")

                    if len(output) >= 2:
                        # 解析 CPU (Load Average)
                        load_avg = float(output[0].split()[0])
                        kali_stats["cpu"] = min(round(load_avg * 100 / 4, 1), 100)

                        # 解析内存 (查找包含 Mem: 的行)
                        for line in output:
                            if "Mem:" in line:
                                parts = line.split()
                                # parts[0]=Mem:, parts[1]=total, parts[2]=used
                                total = int(parts[1])
                                used = int(parts[2])
                                kali_stats["ram"] = round((used / total) * 100, 1)
                                break
                except Exception as e:
                    print(f"DEBUG: 获取详细资源数据失败 (但不影响在线状态) -> {e}")

    except Exception as e:
        print(f"❌ SSH 异常: {e}")
        ssh_client.client = None

    return {
        "host": win_stats,
        "kali": kali_stats
    }