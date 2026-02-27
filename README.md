# License Manager SDK (Python)

`license-manager-sdk-python` 是 ThingsPanel License Manager 系列授权管控中枢的官方 Python 客户端。它与后端的 SaaS 管控网络无缝集成，专门为 B端/G端 软件、算法模型落地以及各种私有化部署提供**从在线激活到离线侧载、从机器指纹绑定到后台心跳封禁**的全套授权治理能力。

## 🌟 核心能力架构

本 SDK 提供多层防御机制和灵活的商业策略触点：

*   **🛡️ 强硬件指纹锁定**：全平台自动抓取 `MAC`, `CPU`, `Hostname` 甚至自定义特征生成唯一指纹，实现真正的“一机一码”，阻断跨设备白嫖。
*   **🔒 数据强防篡改 (RSA-PSS + AES)**：网络传输与本地落地的 `license.lic` 均由不可逆的非对称 RSA 私钥重签名，本地持久化缓存以动态 Nonce + AES-GCM 加密，彻底杜绝本地抓包与反汇编篡改证书。
*   **🔌 混合鉴权 (Online First & Offline Fallback)**：
    *   **在线模式**：输入一串极简的产品激活码，设备主动向 SaaS 面板请求注册激活，后台自动派发许可并建立心跳档案。
    *   **离线侧载 (`&` 魔法)**：对于军工/内网纯断网环境，支持用户将授权码与被网闸外的终端代签的 `Base64` 离线封套组合为 `AuthCode&Envelope` 格式喂给 SDK，自动实现物理隔离区的脱机秒激活验证。
*   **💓 云端“遥控”心跳系统**：底层常驻心跳守护线程。无论何时在 SaaS 控制台点击“禁用”、“退款解绑”或“过期”，客户端下一秒的 `Heartbeat` 立即获取并触发死亡回调，瞬时阻断正在运行的业务。

## 📦 快速接入指南

### 1. 基础依赖

本 SDK 坚持最小极简原则，除标准库外，仅需依赖：
```bash
pip install requests cryptography
```

### 2. 初始化与使用

以下是如何在您的 Python 业务代码中无侵入式植入防线的示例：

```python
import time
import logging
from license_manager.client import Client, ClientOptions, Callbacks
from license_manager.config import Config
from license_manager.models import LicensePayload

def main():
    # 1. 配置您的 SaaS 网关与应用身份
    cfg = Config(
        server="http://43.136.177.43:18081",
        product="vision-vm-studio",     # 您在 SaaS 后台创建的产品标识
        version="1.0.0",                # 软件版本(可作升级校验控制)
        authorization_code="YOUR_AUTH_CODE", # 客户输入的授权码(可带&脱机包)
        hardware_fields=["cpu", "hostname", "mac"],
        license_file_path="license.lic",     # 授权本地落地缓存
        public_key_pem=b"-----BEGIN PUBLIC KEY-----\n..." # 从后台获取的公钥PEM串
    )

    # 2. 注入业务阻断/状态同步回调钩子
    def on_license_updated(lic: LicensePayload):
        logging.info(f"-> 收到新证书！将于 {lic.expires_at} 过期")

    def on_heartbeat_error(err: Exception):
        logging.warning(f"-> 心跳预警/暂无法连接服务器: {err}")
        # 如果 err 中包含 300006，意味着不仅是断网，而是您在后台强行吊销了该证
        if "300006" in str(err):
            logging.error("业务级致盲：授权已被吊销或清理！")

    def on_activation_required(reason: str):
        logging.error(f"-> 致命剥权: {reason}")
        # 在此处调用 sys.exit() 或者杀除核心算法句柄

    # 3. 拉起防线
    callbacks = Callbacks(
        on_license_updated=on_license_updated,
        on_heartbeat_error=on_heartbeat_error,
        on_activation_required=on_activation_required,
        on_heartbeat_ping=lambda: logging.info("Ping...")
    )
    
    try:
        # SDK 启动时会自动根据情况：尝试载入本地有效证 -> 发起在线激活请求 -> 降级解密离线包套 -> 启动轮询
        client = Client(cfg, ClientOptions(callbacks=callbacks))
    except Exception as e:
        logging.error(f"授权初始化崩溃: {e}")
        return

    # 4. 经过上一步的洗礼，此时必定有合规的证
    lic = client.current_license()
    logging.info(f"授权成功并生效，企业标识: {lic.license_key}")
    
    # +++ 以下为您的核心商业逻辑 +++
    # ...
    # 每次跑巨幅算力前均可调用安全验证：
    client.validate() 
    
    # 优雅退出
    client.close()

if __name__ == "__main__":
    main()
```

## 🛠️ API 模块详述

- `license_manager.config.Config`: SDK 的基石配置，负责定义产品身份、硬件采样维度和公钥验签证书。
- `license_manager.client.Client`: 主控 Facade。您只需持有它的实例即可。
- `license_manager.hardware.DefaultHardwareProvider`: 跨平台设备指纹提取器，默认支持 `mac`, `cpu`, `hostname`, `disk` 等硬件特征的稳定提取与加密散列化。
- `license_manager.heartbeat.HeartbeatManager`: 藏在底层的定时器，会按照 `Config` 或服务端下发的动态间隔，不断向后台上报指纹请求对齐 `LicensePayload` 履历。

## 💡 示例应用 (Examples)

SDK 内置了两个详尽的参考案例：
- `examples/basic/main.py`: 无依赖的纯终端 SDK 接入演示。
- `examples/客户案例1/client-demo/demo.py`: **基于 `Tkinter` 的高度还原 GUI 客户端 Demo**，展示了极其直观的离线载入、在线阻断日志以及动态修改 SaaS 地址的商业端防线体验。您可以直接运行或使用 PyInstaller 打包为 `exe`。
