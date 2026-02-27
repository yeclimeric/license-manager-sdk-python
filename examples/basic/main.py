import time
import logging
from license_manager.client import Client, ClientOptions, Callbacks
from license_manager.config import Config
from license_manager.models import LicensePayload

def main():
    logging.basicConfig(level=logging.INFO)
    
    cfg = Config(
        server="https://license.example.com",
        product="edge-gateway",
        version="2.3.1",
        authorization_code_path="license_code/authorization_code.txt",
        public_key_path="license_code/rsa_public_key.pem",
        hardware_fields=["cpu", "memory", "mac"],
        heartbeat_interval_seconds=10,
        offline=False,
    )

    def on_license_updated(lic: LicensePayload):
        logging.info(f"许可证更新，将于 {lic.expires_at} 过期")

    def on_heartbeat_error(err: Exception):
        logging.error(f"心跳异常: {err}")

    def on_activation_required(reason: str):
        logging.warning(f"需要重新激活: {reason}")

    callbacks = Callbacks(
        on_license_updated=on_license_updated,
        on_heartbeat_error=on_heartbeat_error,
        on_activation_required=on_activation_required
    )
    
    opts = ClientOptions(callbacks=callbacks)

    try:
        # Client initialization validates configuration, gathers hardware fingerprint,
        # performs offline local validation or online activation, and spins up heartbeat threads
        client = Client(cfg, opts)
    except Exception as e:
        logging.error(f"初始化 SDK 失败: {e}")
        return

    lic = client.current_license()
    if lic:
        logging.info(f"状态={lic.status} 过期={lic.expires_at}")
        logging.info(f"最大激活={lic.max_activations} key={lic.license_key}")
        
    logging.info("主线程执行日常业务任务中...")
    try:
        time.sleep(35)
    except KeyboardInterrupt:
        pass
    finally:
        logging.info("关闭 SDK 客户端以终止后台心跳.")
        client.close()

if __name__ == "__main__":
    main()
