import base64
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext

# Ensure the SDK root is in PYTHONPATH to allow running demo.py standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from license_manager.client import Client, ClientOptions, Callbacks
from license_manager.config import Config
from license_manager.models import LicensePayload
from license_manager.hardware import DefaultHardwareProvider


class DemoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("License Manager SDK Demo")
        self.geometry("700x650")
        
        self.client = None
        
        # 提取当前设备指纹（仅做界面展示）
        hw = DefaultHardwareProvider(["mac", "cpu", "hostname"])
        try:
            self.fingerprint, _ = hw.fingerprint()
        except Exception:
            self.fingerprint = "Unknown"
            
        self._build_ui()
        self._log("系统初始化完毕，准备加载授权...")
        
        # 延迟100ms去试着加载本地授权
        self.after(100, self.init_sdk_offline)

    def _build_ui(self):
        # 区域一：设备识别与状态显示牌
        top_frame = tk.LabelFrame(self, text="设备指纹与当前授权状态", padx=10, pady=10)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(top_frame, text="设备指纹 (Hardware ID):").grid(row=0, column=0, sticky="w")
        
        self.entry_fp = tk.Entry(top_frame, width=35)
        self.entry_fp.insert(0, self.fingerprint)
        self.entry_fp.config(state="readonly")
        self.entry_fp.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Button(top_frame, text="复制", command=self._copy_fp).grid(row=0, column=2, padx=5)
        
        tk.Label(top_frame, text="授权状态:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.lbl_status = tk.Label(top_frame, text="未激活", fg="red", font=("Helvetica", 12, "bold"))
        self.lbl_status.grid(row=1, column=1, sticky="w", pady=(5, 0))
        
        tk.Label(top_frame, text="到期时间:").grid(row=2, column=0, sticky="w")
        self.lbl_expire = tk.Label(top_frame, text="-")
        self.lbl_expire.grid(row=2, column=1, sticky="w")

        # 区域二：授权码输入与操作区
        mid_frame = tk.LabelFrame(self, text="管控与激活设置", padx=10, pady=10)
        mid_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(mid_frame, text="SaaS 服务地址:").grid(row=0, column=0, sticky="w", pady=2)
        self.entry_server = tk.Entry(mid_frame, width=60)
        self.entry_server.insert(0, "http://43.136.177.43:18081")
        self.entry_server.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(mid_frame, text="RSA 公钥 (PEM):").grid(row=1, column=0, sticky="nw", pady=2)
        self.txt_pubkey = scrolledtext.ScrolledText(mid_frame, width=58, height=4, font=("Consolas", 9))
        self.txt_pubkey.insert("1.0", (
            "-----BEGIN PUBLIC KEY-----\n"
            "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5hGz3hws+L2MUW7CaRQI\n"
            "t7Vxk0KAdPBUuNdkJcs2kpgkDmiT/pHf+9WXfRVdKD/Eu/t7wckQfzziddXTbeCx\n"
            "gN/5bKSeLTPXT0VvvSkfB5FUUQABHFWO4fiBlfP/NdFy++qKgCUF1wGg+jSsrhAw\n"
            "6oMDI7MHVRfRZTe3rTM3T0qi3Ed6qaoIM9INQ87FcqPVMyQ/KXbe4Dz5yVkLY5iY\n"
            "j8ZJP7iU2vKYvWIG9TNv0FK/dXQk7syMGBSKmIncCe+UaflAajbDGXq52gIeTyhO\n"
            "BumOLXXBdlwgCVtejBTqDmlQpiJYADKiZLQfx0z1hYbbOPBPB3djXCJJmQk69sso\n"
            "ZQIDAQAB\n"
            "-----END PUBLIC KEY-----"
        ))
        self.txt_pubkey.grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(mid_frame, text="产品激活码:").grid(row=2, column=0, sticky="w", pady=2)
        self.entry_code = tk.Entry(mid_frame, width=60)
        self.entry_code.grid(row=2, column=1, padx=5, pady=2)
        
        btn_frame = tk.Frame(mid_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky="w")
        
        tk.Button(btn_frame, text="激活 / 验证", bg="#4CAF50", fg="white", width=15, command=self.on_activate_click).pack(side="left", padx=5)
        tk.Button(btn_frame, text="清理本地许可缓存", width=15, command=self.on_clear_click).pack(side="left", padx=5)

        # 区域三：业务模拟与底座运行日志
        bot_frame = tk.LabelFrame(self, text="机器视觉核心业务模拟与日志", padx=10, pady=10)
        bot_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.btn_run_ai = tk.Button(bot_frame, text="[业务] 开始 AI 模板检测", bg="#2196F3", fg="white", font=("Helvetica", 14), command=self.on_run_ai_click)
        self.btn_run_ai.pack(fill="x", pady=5)
        
        self.txt_log = scrolledtext.ScrolledText(bot_frame, height=10, bg="black", fg="white")
        self.txt_log.pack(fill="both", expand=True, pady=5)

    def _copy_fp(self):
        self.clipboard_clear()
        self.clipboard_append(self.fingerprint)
        messagebox.showinfo("复制成功", "机器指纹已复制")

    def _log(self, msg: str):
        now = time.strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"[{now}] {msg}\n")
        self.txt_log.see(tk.END)

    def _update_status(self, payload: LicensePayload):
        if payload and payload.license_key:
            self.lbl_status.config(text="验证通过 (合法)", fg="green")
            exp_str = payload.expires_at.strftime("%Y-%m-%d %H:%M:%S") if payload.expires_at else "永久"
            self.lbl_expire.config(text=exp_str)
        else:
            self.lbl_status.config(text="未激活 / 被锁定", fg="red")
            self.lbl_expire.config(text="-")

    def _safe_update_status(self, payload: LicensePayload):
        self.after(0, self._update_status, payload)

    def _safe_log(self, msg: str):
        self.after(0, self._log, msg)

    def _safe_alert(self, title, msg):
        self.after(0, lambda: messagebox.showwarning(title, msg))

    # --- SDK 钩子定义 ---
    def on_license_updated(self, lic: LicensePayload):
        self._safe_log(f"-> 钩子触发: [on_license_updated] 下发了有效的新证书！到期: {lic.expires_at}")
        self._safe_update_status(lic)

    def on_activation_required(self, reason: str):
        self._safe_log(f"-> 钩子触发: [on_activation_required] 授权已被驳回/封禁！原因: {reason}")
        self.after(0, lambda: self.lbl_status.config(text=f"锁定: {reason}", fg="red"))
        self._safe_alert("授权已失效", f"您的授权已被服务器拒绝或锁定，请联系管理员。\n底层原因: {reason}")
        
    def on_heartbeat_error(self, err: Exception):
        msg = str(err)
        self._safe_log(f"[后台轮询] 心跳无法连接服务器/遭遇异常: {msg}")
        # 如果后台返回了明确的 300006 (许可证不存在)，说明管理后台删除了授权或该机器被强制解绑
        if "300006" in msg:
            self._safe_log("[安全策略阻断] 服务端反馈许可不存在！您的授权已被撤销或转移。正在清理本地许可凭证...")
            # 因为错误回调是在独立的守护线程里执行的，我们需要借用 after 以 UI 线程安全的方式清理并阻断
            self.after(500, self.on_clear_click)

    def on_heartbeat_ping(self):
        self._safe_log(f"[后台轮询] 成功向服务器上报设备在线心跳！")

    # --- 核心业务连贯逻辑 ---
    def get_sdk_config(self, auth_code: str = "") -> Config:
        server_url = self.entry_server.get().strip()
        if not server_url:
            server_url = "http://43.136.177.43:18081"
            
        pub_key_str = self.txt_pubkey.get("1.0", tk.END).strip()
        pub_key_bytes = pub_key_str.encode('utf-8') if pub_key_str else b""
            
        return Config(
            server=server_url,
            product="vision-vm-studio",
            version="1.0.0",
            authorization_code=auth_code,
            license_file_path="license.lic",
            heartbeat_interval_seconds=10,  # 演示专用：10秒一次高频心跳
            public_key_pem=pub_key_bytes
        )

    def init_sdk_offline(self):
        """尝试不带激活码纯本地启动"""
        self._log("尝试加载本地 'license.lic' 验证授权...")
        cfg = self.get_sdk_config()
        
        # 对于真正从硬盘拉取历史授权记录的“冷启动”：
        # 我们不知道用户当时填的激活码是啥，只知道他本地有合法生成的证。
        # 为了不破坏联网心跳能力（不设置 cfg.offline），我们塞入一个占位激活码让 Config 通过验证，
        # 只要本地有合规授权，SDK Bootstrap 阶段就不会向服务器发起"空行"激活，而是直接拉起心跳。
        cfg.authorization_code = "LOADED_FROM_LOCAL_CACHE"
        
        def _boot():
            try:
                self._init_client_impl(cfg)
                self._safe_log("-> 历史本地授权自动加载且验证通过！无需重复输入激活码。")
            except Exception as e:
                # 初次启动时如果没有激活码和本地授权文件是正常的，这里静默处理
                msg = str(e)
                if "authorization code" not in msg and "missing" not in msg and "no loaded license" not in msg:
                    self._safe_log(f"-> 本地授权预加载检测未通过: {msg}")
                self.after(0, lambda: self._update_status(None))
                
        threading.Thread(target=_boot, daemon=True).start()

    def on_activate_click(self):
        user_input = self.entry_code.get().strip()
        if not user_input:
            messagebox.showwarning("错误", "请输入产品激活码")
            return
            
        self._log(f"用户发起激活请求，识别码长度: {len(user_input)}")
        cfg = self.get_sdk_config()
        
        envelope_b64 = None
        if "&" in user_input:
            auth_part, envelope_b64 = user_input.split("&", 1)
            cfg.authorization_code = auth_part
            self._log("-> 识别到产品激活码中包含脱机包验证参数。")
        else:
            cfg.authorization_code = user_input
            self._log("-> 识别为纯在线授权码。")

        # 异步启动防止卡死 UI
        threading.Thread(target=self._activate_logic_thread, args=(cfg, envelope_b64), daemon=True).start()

    def _activate_logic_thread(self, cfg: Config, envelope_b64: str):
        # 先清理本地遗留许可，强制优先走“在线激活”流程
        if os.path.exists(cfg.license_file_path):
            os.remove(cfg.license_file_path)
            
        self._safe_log("-> [策略] 优先尝试连接 SaaS 平台进行在线激活/绑定...")
        
        try:
            self._init_client_impl(cfg)
            self._safe_log("-> 在线激活成功！设备已绑定并在后台可见。")
            return
        except Exception as e:
            msg = str(e)
            self._safe_log(f"-> 在线激活遭遇异常/网络不通: {msg}")
            
            # 如果存在脱机包，则降级为离线侧载
            if envelope_b64:
                self._safe_log("-> [策略] 检测到网络无法完成激活，正在自动降级使用脱机包进行完全物理隔离验证...")
                try:
                    payload_bytes = base64.b64decode(envelope_b64)
                    with open(cfg.license_file_path, "wb") as f:
                        f.write(payload_bytes)
                    self._safe_log("-> 脱机包落地成功！正在二次验证...")
                    self._init_client_impl(cfg)
                    self._safe_log("-> 脱机验证成功！(系统此时完全离线运行)")
                except Exception as ex:
                    self._safe_log(f"-> 脱机包降级验证失败: {ex}")
                    self.after(0, lambda: self._update_status(None))
            else:
                self._safe_log("-> 致命错误：因为没有脱机包且当前无法在线激活，授权流程被阻断。")
                self.after(0, lambda: self._update_status(None))

    def _init_client_impl(self, cfg: Config):
        # 内部真实初始化 Client
        # 实战中不建议这么做，此处为了 Demo 演示快节奏，强行忽略后台 SaaS 返回的 600s/3600s 下发间隔限制
        from license_manager.models import HeartbeatResponse
        original_from_dict = HeartbeatResponse.from_dict
        
        def patched_from_dict(data: dict) -> HeartbeatResponse:
            resp = original_from_dict(data)
            resp.heartbeat_interval = 10 # 强制覆盖服务端配置
            return resp
            
        HeartbeatResponse.from_dict = staticmethod(patched_from_dict)
        
        # 若是外部调用跑进此函数发生异常，会向外抛出被 _activate_logic_thread 捕获
        if self.client:
            self.client.close()
            
        opts = ClientOptions(
            callbacks=Callbacks(
                on_license_updated=self.on_license_updated,
                on_activation_required=self.on_activation_required,
                on_heartbeat_error=self.on_heartbeat_error,
                on_heartbeat_ping=self.on_heartbeat_ping
            )
        )
        self.client = Client(cfg, opts=opts)
        lic = self.client.current_license()
        if lic:
            self._safe_log(">>> SDK 验证成功 <<<")
            self._safe_update_status(lic)
        else:
            self.after(0, lambda: self._update_status(None))

    def on_clear_click(self):
        if self.client:
            self.client.close()
            self.client = None
            
        if os.path.exists("license.lic"):
            os.remove("license.lic")
            self._log("已物理删除 'license.lic' 缓存文件。")
        else:
            self._log("未发现 'license.lic' 文件。")
            
        self._update_status(None)

    def on_run_ai_click(self):
        if not self.client:
            messagebox.showerror("阻断", "SDK 未初始化，请先提供激活码！")
            return
            
        # 实时验证
        try:
            self.client.validate()
            # 通过后模拟业务逻辑
            self._log("【业务端】实时合规性检测: 通过。")
            messagebox.showinfo("业务层", "授权正常！\nAI 模板匹配算法已成功启动，正在处理图像帧...")
        except Exception as e:
            self._log(f"【业务端】授权拦截: {e}")
            messagebox.showerror("越权阻断", f"由于未授权或授权已被封禁，算法引擎拒绝启动。\n\n原因: {e}")


if __name__ == "__main__":
    app = DemoApp()
    app.mainloop()
