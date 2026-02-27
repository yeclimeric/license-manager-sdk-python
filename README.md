# License Manager SDK (Python)

`license-manager-sdk-python` 是 License Manager 授权管控中枢的官方 Python 客户端。它与后端的 SaaS 管控网络无缝集成，专门为各类软件、算法模型落地以及私有化部署提供从在线激活到离线授权、从机器指纹绑定到后台心跳管控的全套授权治理能力。

## 核心能力架构

本 SDK 提供多层防御机制和灵活的商业策略触点：

*   **强硬件指纹锁定**：全平台自动提取 `MAC`, `CPU`, `Hostname` 等特征生成唯一指纹，实现“一机一码”，有效防止未授权的设备滥用。
*   **数据强防篡改 (RSA-PSS + AES)**：网络传输与本地落地的 `license.lic` 均由不可逆的非对称 RSA 私钥重签名，本地持久化缓存以动态 Nonce + AES-GCM 加密，保障本地授权文件安全。
*   **混合鉴权 (Online First & Offline Fallback)**：
    *   **在线模式**：输入产品激活码，设备主动向管控端请求注册激活，后台验证后派发许可并建立心跳连接。
    *   **离线侧载**：针对无外网环境，支持用户将授权码与离线授权封套组合为 `AuthCode&Envelope` 格式输入 SDK，实现物理隔离环境下的离线激活验证。
*   **云端管控心跳系统**：底层常驻心跳守护线程。当在控制台执行“禁用”、“解绑”或当授权“过期”时，客户端的心跳请求会获取最新状态并触发回调，及时中止核心业务。

## 快速接入指南

### 1. 基础依赖

本 SDK 除标准库外，仅需依赖：
```bash
pip install requests cryptography
```

### 2. 初始化与使用

以下是如何在您的 Python 业务代码中集成授权验证的示例：

```python
import time
import logging
from license_manager.client import Client, ClientOptions, Callbacks
from license_manager.config import Config
from license_manager.models import LicensePayload

def main():
    # 1. 配置您的服务端网关与应用身份
    cfg = Config(
        server="http://127.0.0.1:18081",
        product="vision-vm-studio",     # 您在后台创建的产品标识
        version="1.0.0",                # 软件版本
        authorization_code="YOUR_AUTH_CODE", # 客户输入的授权码
        hardware_fields=["cpu", "hostname", "mac"],
        license_file_path="license.lic",     # 授权本地落地缓存
        public_key_pem=b"-----BEGIN PUBLIC KEY-----\n..." # 从后台获取的公钥PEM串
    )

    # 2. 注入业务状态同步回调钩子
    def on_license_updated(lic: LicensePayload):
        logging.info(f"-> 收到新证书！将于 {lic.expires_at} 过期")

    def on_heartbeat_error(err: Exception):
        logging.warning(f"-> 心跳预警/暂无法连接服务器: {err}")
        if "300006" in str(err):
            logging.error("业务提示：授权已被吊销或清理！")

    def on_activation_required(reason: str):
        logging.error(f"-> 授权失效: {reason}")
        # 在此处执行程序退出或中止核心业务

    # 3. 初始化客户端
    callbacks = Callbacks(
        on_license_updated=on_license_updated,
        on_heartbeat_error=on_heartbeat_error,
        on_activation_required=on_activation_required,
        on_heartbeat_ping=lambda: logging.info("Ping...")
    )
    
    try:
        # SDK 启动时会自动尝试：载入本地有效证书 -> 发起在线激活请求 -> 解析离线授权包 -> 启动轮询
        client = Client(cfg, ClientOptions(callbacks=callbacks))
    except Exception as e:
        logging.error(f"授权初始化失败: {e}")
        return

    # 4. 获取有效的授权凭证
    lic = client.current_license()
    logging.info(f"授权成功并生效，企业标识: {lic.license_key}")
    
    # +++ 以下为核心商业逻辑 +++
    # ...
    # 在执行核心计算前均可调用安全验证：
    client.validate() 
    
    # 优雅退出
    client.close()

if __name__ == "__main__":
    main()
```

## API 模块详述

- `license_manager.config.Config`: SDK 的配置模块，定义产品身份、硬件采样维度和公钥验签证书。
- `license_manager.client.Client`: 主控客户端实例。
- `license_manager.hardware.DefaultHardwareProvider`: 跨平台设备指纹提取器，支持 `mac`, `cpu`, `hostname`, `disk` 等硬件特征的提取与处理。
- `license_manager.heartbeat.HeartbeatManager`: 定时心跳管理器，按照配置间隔向服务端上报状态并同步最新授权配置。

## 示例应用 (Examples)

SDK 内置了两个参考案例：
- `examples/basic/main.py`: 无界面的终端 SDK 接入演示。
- `examples/客户案例1/client-demo/demo.py`: 基于 `Tkinter` 的 GUI 客户端 Demo，展示了离线载入、阻断日志以及动态修改服务端地址的完整交互体验。可以作为参考或者使用 PyInstaller 构建独立可执行程序。
