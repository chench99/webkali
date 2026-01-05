from fastapi import APIRouter
from app.core.ssh_manager import ssh_client
import psutil

router = APIRouter()


# ==========================================
# 1. 系统状态监控 (原功能)
# ==========================================
@router.get("/status")
async def get_system_status():
    """获取宿主机状态和 Kali 连接状态"""
    # 获取本机资源
    cpu_usage = psutil.cpu_percent(interval=None)
    ram_usage = psutil.virtual_memory().percent

    # 检查 SSH 连接是否存活
    kali_online = False
    if ssh_client.client:
        if ssh_client.client.get_transport() and ssh_client.client.get_transport().is_active():
            kali_online = True
        else:
            ssh_client.client = None  # 连接已断开

    # 如果在线，尝试获取 Kali 的负载 (可选)
    kali_cpu = 0
    kali_ram = 0
    if kali_online:
        try:
            # 简单的获取 Kali 负载命令
            stdin, stdout, stderr = ssh_client.exec_command(
                "grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}'")
            k_cpu = stdout.read().decode().strip()
            kali_cpu = int(float(k_cpu)) if k_cpu else 0

            stdin, stdout, stderr = ssh_client.exec_command("free | grep Mem | awk '{print $3/$2 * 100.0}'")
            k_ram = stdout.read().decode().strip()
            kali_ram = int(float(k_ram)) if k_ram else 0
        except:
            pass

    return {
        "host": {
            "cpu": cpu_usage,
            "ram": ram_usage
        },
        "kali": {
            "online": kali_online,
            "cpu": kali_cpu,
            "ram": kali_ram
        }
    }


# ==========================================
# 2. 网卡详情获取 (Evil Twin 增强功能)
# ==========================================
@router.get("/interfaces")
async def get_kali_interfaces():
    """
    执行 'airmon-ng' 获取网卡列表和芯片信息
    返回格式: [{"name": "wlan0", "driver": "mt7601u", "chipset": "MediaTek...", "label": "..."}]
    """
    if not ssh_client.client:
        try:
            ssh_client.connect()
        except:
            return {"status": "error", "data": []}

    try:
        # airmon-ng 的输出包含 PHY, Interface, Driver, Chipset
        # 使用 airmon-ng 命令比 iwconfig 能看到更详细的芯片信息
        stdin, stdout, stderr = ssh_client.exec_command("airmon-ng")
        output = stdout.read().decode()

        interfaces = []
        lines = output.splitlines()

        # 解析输出
        for line in lines:
            # 跳过空行和标题行
            if not line or "PHY" in line or "Interface" in line: continue

            # airmon-ng 输出是用 tab 分隔的
            parts = line.split('\t')
            # 过滤掉空字符串元素
            parts = [p for p in parts if p]

            # 确保解析正确 (通常至少有 Interface, Driver, Chipset)
            if len(parts) >= 3:
                # 某些版本格式: [PHY, Interface, Driver, Chipset]
                # 有些版本可能只有 [Interface, Driver, Chipset]
                # 我们主要找 Interface 名称 (wlanX, monX)

                iface_name = ""
                driver = ""
                chipset = ""

                # 简单的启发式查找
                for part in parts:
                    if part.startswith("wlan") or part.startswith("mon"):
                        iface_name = part
                        break

                # 如果没找到网卡名，尝试按位置取
                if not iface_name and len(parts) > 1:
                    iface_name = parts[1]  # 假设第二列是接口名

                if len(parts) > 2: driver = parts[2]
                if len(parts) > 3: chipset = parts[3]

                # 排除非无线网卡
                if iface_name and "eth" not in iface_name and "lo" not in iface_name:
                    interfaces.append({
                        "name": iface_name,
                        "driver": driver,
                        "chipset": chipset,
                        # 前端下拉框显示的标签
                        "label": f"{iface_name}: {chipset} ({driver})"
                    })

        return {"status": "success", "data": interfaces}
    except Exception as e:
        return {"status": "error", "msg": str(e), "data": []}