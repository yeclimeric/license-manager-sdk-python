import base64
import os
import sys
import threading
from typing import Optional
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

# Ensure the SDK root is in PYTHONPATH to allow running demo.py standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from license_manager.client import Client, ClientOptions, Callbacks
from license_manager.config import Config
from license_manager.models import LicensePayload

# 无激活码时仅加载本地 license.lic：满足 Config 校验且避免走空激活请求
LOCAL_AUTH_PLACEHOLDER = "LOADED_FROM_LOCAL_CACHE"


class DemoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("License Manager 客户端模拟器v1.0.5")
        self.geometry("700x650")

        self.client = None
        # 模拟断网：monkey-patch requests.Session.post；None 表示当前未拦截
        self._net_mock_orig_post = None

        # 用 Client 内部同样的逻辑获取指纹，确保 UI 显示的和激活发给系统的一样
        from license_manager.hardware import DefaultHardwareProvider
        hw = DefaultHardwareProvider(["cpu"])
        try:
            self.fingerprint, _ = hw.fingerprint()
        except Exception:
            self.fingerprint = "Unknown"

        self._build_ui()
        self._log("系统初始化完毕。激活码可留空：将仅验证本地 license.lic；填写后可在线激活或带脱机包降级。")
        self._log(f"当前设备指纹: {self.fingerprint}")

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
        self.entry_server.insert(0, "http://lm-e.cedar-v.com")
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

        tk.Label(mid_frame, text="授权码/产品激活码:").grid(row=2, column=0, sticky="w", pady=2)
        self.entry_code = tk.Entry(mid_frame, width=60)
        self.entry_code.grid(row=2, column=1, padx=5, pady=2)

        btn_frame = tk.Frame(mid_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky="w")

        tk.Button(btn_frame, text="激活 / 验证", bg="#4CAF50", fg="white", width=15, command=self.on_activate_click).pack(side="left", padx=5)
        tk.Button(btn_frame, text="清理本地许可缓存", width=15, command=self.on_clear_click).pack(side="left", padx=5)
        tk.Button(btn_frame, text="创建/修改许可证", width=15, command=self.on_edit_license_click).pack(side="left", padx=5)

        # 区域三：业务模拟与底座运行日志
        bot_frame = tk.LabelFrame(self, text="机器视觉核心业务模拟与日志", padx=10, pady=10)
        bot_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 业务按钮与网络模式开关同行排列
        ctrl_frame = tk.Frame(bot_frame)
        ctrl_frame.pack(fill="x", pady=5)

        # 网络模式开关区域
        switch_frame = tk.Frame(ctrl_frame)
        switch_frame.pack(side="left", padx=(0, 10))

        self.net_offline = tk.BooleanVar(value=False)

        tk.Label(switch_frame, text="模拟断网:").pack(side="left", padx=(0, 5))

        net_check = ttk.Checkbutton(
            switch_frame, text="开启",
            variable=self.net_offline,
            command=self._on_net_switch_changed
        )
        net_check.pack(side="left")

        self.net_mode_label = tk.Label(switch_frame, text="外网（联网）", fg="#4CAF50", font=("Helvetica", 10, "bold"))
        self.net_mode_label.pack(side="left", padx=(8, 0))

        # 业务主按钮
        self.btn_run_ai = tk.Button(
            ctrl_frame, text="[业务] AI 模板检测",
            bg="#2196F3", fg="white", font=("Helvetica", 14),
            command=self.on_run_ai_click
        )
        self.btn_run_ai.pack(side="left", fill="x", expand=True)

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
        if "300006" in msg:
            self._safe_log("[安全策略阻断] 服务端反馈许可不存在！您的授权已被撤销或转移。正在清理本地许可凭证...")
            self.after(500, self.on_clear_click)

    def on_heartbeat_ping(self):
        self._safe_log(f"[后台轮询] 成功向服务器上报设备在线心跳！")

    def on_public_key_updated(self, new_pub_key: str):
        self.after(0, lambda pk=new_pub_key: self._do_update_pubkey(pk))

    def _do_update_pubkey(self, new_pub_key: str):
        self.txt_pubkey.delete("1.0", tk.END)
        self.txt_pubkey.insert("1.0", new_pub_key)
        self._safe_log(f"[公钥更新] 已自动替换为服务端最新公钥，后续激活无需再手动填入。")

    # --- 核心业务连贯逻辑 ---
    def get_sdk_config(self, auth_code: str = "") -> Config:
        server_url = self.entry_server.get().strip()
        if not server_url:
            server_url = "http://lm-e.cedar-v.com/"

        pub_key_str = self.txt_pubkey.get("1.0", tk.END).strip()
        pub_key_bytes = pub_key_str.encode('utf-8') if pub_key_str else b""

        return Config(
            server=server_url,
            product="vision-vm-studio",
            version="1.0.0",
            authorization_code=auth_code,
            license_file_path="license.lic",
            heartbeat_interval_seconds=10,
            public_key_pem=pub_key_bytes,
            hardware_fields=["cpu"],
        )

    def on_activate_click(self):
        user_input = self.entry_code.get().strip()
        if not user_input:
            self._log("用户发起「激活 / 验证」：未填激活码，尝试仅加载本地 license.lic ...")
            threading.Thread(target=self._activate_local_only_thread, daemon=True).start()
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

        threading.Thread(target=self._activate_logic_thread, args=(cfg, envelope_b64), daemon=True).start()

    def _activate_local_only_thread(self):
        """激活码为空：不删本地文件，仅用占位码走 SDK 本地加载。"""
        cfg = self.get_sdk_config()
        cfg.authorization_code = LOCAL_AUTH_PLACEHOLDER
        path = cfg.license_file_path
        if not os.path.exists(path):
            self._safe_log("-> 未找到本地 license.lic，无法在无激活码时验证。")
            self._safe_update_status(None)
            self.after(0, lambda: messagebox.showwarning(
                "提示",
                "未填写授权码/产品激活码时，需要存在本地许可文件 license.lic。\n请先完成一次在线激活，或粘贴含脱机包的激活码。"
            ))
            return
        if self._net_simulates_disconnect():
            self._apply_network_disconnect_mock()
        else:
            self._restore_network_disconnect_mock()
        try:
            self._init_client_impl(cfg)
            self._safe_log("-> 本地许可验证通过（未使用激活码）。")
            if not self._net_simulates_disconnect():
                self._restore_network_disconnect_mock()
        except Exception as e:
            self._safe_log(f"-> 本地许可加载失败: {e}")
            self._safe_update_status(None)
            if not self._net_simulates_disconnect():
                self._restore_network_disconnect_mock()

    def _activate_logic_thread(self, cfg: Config, envelope_b64: str):
        offline = self._net_simulates_disconnect()
        if offline:
            self._apply_network_disconnect_mock()
        else:
            self._restore_network_disconnect_mock()

        # 断网：绝不先删本地 license.lic；优先用已有缓存验证
        if offline and os.path.exists(cfg.license_file_path):
            self._safe_log("-> [离线激活] 检测到本地 license.lic，断网模式下直接验证...")
            try:
                self._init_client_impl(cfg)
                self._safe_log("-> 本地缓存验证通过（断网激活/验证）。")
                if not self._net_simulates_disconnect():
                    self._restore_network_disconnect_mock()
                return
            except Exception as local_err:
                self._safe_log(f"-> [离线激活] 本地缓存验证失败: {local_err}")
                if not envelope_b64:
                    self._safe_log("-> 致命错误：断网且无脱机包，授权流程被阻断。（本地 license.lic 已保留）")
                    self._safe_update_status(None)
                    if not self._net_simulates_disconnect():
                        self._restore_network_disconnect_mock()
                    return

        # 联网：清理旧缓存后再走全新在线激活
        if not offline and os.path.exists(cfg.license_file_path):
            os.remove(cfg.license_file_path)

        self._safe_log("-> [策略] 优先尝试连接 SaaS 平台进行在线激活/绑定...")

        try:
            self._init_client_impl(cfg)
            self._safe_log("-> 在线激活成功！设备已绑定并在后台可见。")
            if not self._net_simulates_disconnect():
                self._restore_network_disconnect_mock()
            return
        except Exception as e:
            msg = str(e)
            self._safe_log(f"-> 在线激活遭遇异常/网络不通: {msg}")

            if envelope_b64:
                self._safe_log("-> [策略] 检测到网络无法完成激活，正在自动降级使用脱机包进行完全物理隔离验证...")
                try:
                    payload_bytes = base64.b64decode(envelope_b64)
                    with open(cfg.license_file_path, "wb") as f:
                        f.write(payload_bytes)
                    self._safe_log("-> 脱机包落地成功！正在二次验证...")
                    self._init_client_impl(cfg)
                    self._safe_log("-> 脱机验证成功！(系统此时完全离线运行)")
                    if not self._net_simulates_disconnect():
                        self._restore_network_disconnect_mock()
                except Exception as ex:
                    self._safe_log(f"-> 脱机包降级验证失败: {ex}")
                    self._safe_update_status(None)
                    if not self._net_simulates_disconnect():
                        self._restore_network_disconnect_mock()
            else:
                self._safe_log("-> 致命错误：因为没有脱机包且当前无法在线激活，授权流程被阻断。")
                self._safe_update_status(None)
                if not self._net_simulates_disconnect():
                    self._restore_network_disconnect_mock()

    def _init_client_impl(self, cfg: Config):
        from license_manager.models import HeartbeatResponse
        original_from_dict = HeartbeatResponse.from_dict

        def patched_from_dict(data: dict) -> HeartbeatResponse:
            resp = original_from_dict(data)
            resp.heartbeat_interval = 10
            return resp

        HeartbeatResponse.from_dict = staticmethod(patched_from_dict)

        if self.client:
            self.client.close()

        opts = ClientOptions(
            callbacks=Callbacks(
                on_license_updated=self.on_license_updated,
                on_activation_required=self.on_activation_required,
                on_heartbeat_error=self.on_heartbeat_error,
                on_heartbeat_ping=self.on_heartbeat_ping,
                on_public_key_updated=self.on_public_key_updated
            )
        )
        self.client = Client(cfg, opts=opts)
        lic = self.client.current_license()
        if lic:
            self._safe_log(">>> SDK 验证成功 <<<")
            self._safe_update_status(lic)
        else:
            self._safe_update_status(None)

    def _license_pubkey_path(self, lic_path: str) -> str:
        return lic_path.rsplit('.', 1)[0] + ".pubkey"

    def on_clear_click(self):
        if self.client:
            self.client.close()
            self.client = None
        cfg = self.get_sdk_config()
        for path in [cfg.license_file_path, self._license_pubkey_path(cfg.license_file_path)]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    self._log(f"已删除: {path}")
                except Exception as e:
                    self._log(f"删除失败 {path}: {e}")
        self.txt_pubkey.delete("1.0", tk.END)
        self._safe_update_status(None)

    def on_edit_license_click(self):
        """弹窗：读取/修改/新建本地 license.lic，不校验内容格式，直接保存用户输入。"""
        path = self.get_sdk_config().license_file_path

        win = tk.Toplevel(self)
        win.title("创建 / 修改本地许可证")
        win.geometry("700x500")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="请输入或粘贴许可证内容（可以是任意格式）：").pack(anchor="w", padx=10, pady=(10, 2))

        txt = scrolledtext.ScrolledText(win, width=90, height=22, font=("Consolas", 9))
        txt.pack(fill="both", expand=True, padx=10, pady=5)

        # 本地已有文件则加载内容，无文件则空文本框
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    txt.insert("1.0", f.read())
            except Exception:
                pass

        btn_row = tk.Frame(win)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        def _do_save():
            raw = txt.get("1.0", tk.END).rstrip("\n")
            if not raw:
                messagebox.showerror("错误", "内容不能为空。", parent=win)
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(raw)
                self._log(f"-> [许可证] 已保存至 {path}")
                messagebox.showinfo("保存成功", f"已保存至 {path}", parent=win)
                win.destroy()
            except Exception as e:
                messagebox.showerror("保存失败", str(e), parent=win)

        tk.Button(btn_row, text="保存到本地 license.lic", bg="#4CAF50", fg="white",
                  width=22, command=_do_save).pack(side="left", padx=5)
        tk.Button(btn_row, text="取消", width=15, command=win.destroy).pack(side="right", padx=5)

        self._restore_network_disconnect_mock()

        if os.path.exists("license.lic"):
            os.remove("license.lic")
            self._log("已物理删除 'license.lic' 缓存文件。")
        else:
            self._log("未发现 'license.lic' 文件。")

        self._update_status(None)

    def _net_simulates_disconnect(self) -> bool:
        return bool(self.net_offline.get())

    def _apply_network_disconnect_mock(self) -> None:
        """拦截 Session.post，模拟断网（激活、心跳同一套 HTTP 路径）。"""
        import requests

        if self._net_mock_orig_post is None:
            self._net_mock_orig_post = requests.Session.post

        def _failing_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("模拟断网：网络不可用")

        requests.Session.post = _failing_post

    def _restore_network_disconnect_mock(self) -> None:
        """恢复真实 HTTP，供「联网」或业务线程结束时使用。"""
        import requests

        if self._net_mock_orig_post is not None:
            requests.Session.post = self._net_mock_orig_post
            self._net_mock_orig_post = None

    def _on_net_switch_changed(self):
        """开关状态变化时更新标签；切回联网时立即恢复 HTTP，心跳即可上报。"""
        if self.net_offline.get():
            self.net_mode_label.config(text="内网（断网）", fg="#FF9800")
            self.btn_run_ai.config(bg="#FF9800")
        else:
            self.net_mode_label.config(text="外网（联网）", fg="#4CAF50")
            self.btn_run_ai.config(bg="#2196F3")
            self._restore_network_disconnect_mock()
            self._log("-> [模拟断网] 已关闭，HTTP 已恢复，后续心跳将尝试真实上报。")

    def on_run_ai_click(self):
        user_input = self.entry_code.get().strip()
        offline_fallback = self.net_offline.get()

        if not user_input:
            cfg = self.get_sdk_config()
            cfg.authorization_code = LOCAL_AUTH_PLACEHOLDER
            self._log("=" * 50)
            offline_desc = "（模拟断网：心跳持续尝试，网络恢复即上报）" if offline_fallback else "（联网心跳）"
            self._log(f"[业务开始] 未填激活码：仅验证本地 license.lic{offline_desc}")
            if offline_fallback:
                self._log("-> [模拟断网] 业务逻辑不变，心跳持续尝试，网络恢复立即上报。")
            threading.Thread(
                target=self._biz_thread,
                args=(cfg, None, offline_fallback, True),
                daemon=True,
            ).start()
            return

        cfg = self.get_sdk_config()
        envelope_b64 = None
        if "&" in user_input:
            auth_part, envelope_b64 = user_input.split("&", 1)
            cfg.authorization_code = auth_part
        else:
            cfg.authorization_code = user_input

        mode = "内网（离线降级）" if offline_fallback else "外网（在线）"
        self._log("=" * 50)
        self._log(f"[业务开始] 模式: {mode}，激活码长度: {len(user_input)}")

        if offline_fallback:
            self._log("-> [内网模式] 正在模拟断网，强制降级使用脱机包验证...")
        threading.Thread(
            target=self._biz_thread,
            args=(cfg, envelope_b64, offline_fallback, False),
            daemon=True,
        ).start()

    def _biz_thread(self, cfg: Config, envelope_b64: Optional[str], force_offline: bool, local_only: bool = False):
        """统一的业务执行线程。local_only=True 时不删除本地 license，仅加载后校验。"""
        self.after(0, self._close_client_unsafe)

        if force_offline:
            self._apply_network_disconnect_mock()
        else:
            self._restore_network_disconnect_mock()

        # ── 新增逻辑 ── 本地缓存优先：断网时直接用已有 license.lic 验证，跳过在线激活
        if force_offline and not local_only and os.path.exists(cfg.license_file_path):
            self._safe_log("-> [离线缓存] 检测到本地 license.lic，断网模式下直接验证...")
            try:
                self._init_client_impl(cfg)
                self.client.validate()
                self._safe_log("【业务端】离线缓存验证: 通过。")
                self._safe_log("=" * 50)
                self._safe_update_status(self.client.current)
                self.after(0, lambda: messagebox.showinfo("业务层", "授权正常（离线缓存）！\nAI 模板匹配算法已成功启动，正在处理图像帧..."))
                return
            except Exception as local_err:
                self._safe_log(f"-> [离线缓存] 验证失败: {local_err}")
                self._safe_log("-> [阻断] 断网且本地许可证无效，无法继续（请联网后重试）。")
                self._safe_update_status(None)
                self.after(0, lambda: messagebox.showerror(
                    "越权阻断",
                    f"断网环境下本地许可证验证失败：{local_err}\n\n请恢复网络连接后重新运行业务。"
                ))
                return

        if local_only:
            if not os.path.exists(cfg.license_file_path):
                self._safe_log("-> [阻断] 未填写激活码但未找到本地 license.lic。")
                self._safe_update_status(None)
                self.after(0, lambda: messagebox.showwarning(
                    "提示",
                    "未填写激活码时，需要存在本地许可文件 license.lic。\n请先激活或粘贴含脱机包的激活码。"
                ))
                return
        else:
            if os.path.exists(cfg.license_file_path):
                os.remove(cfg.license_file_path)

        online_ok = False
        try:
            self._init_client_impl(cfg)
            online_ok = True
            if local_only:
                self._safe_log("-> [本地许可] 加载并验证成功。")
            else:
                self._safe_log("-> [在线激活] 成功！设备已绑定。")
        except Exception as e:
            if local_only:
                self._safe_log(f"-> [本地许可] 失败: {e}")
            else:
                self._safe_log(f"-> [在线激活] 失败: {e}")

        # Step 5: 在线失败时降级离线
        if not online_ok and envelope_b64:
            self._safe_log("-> [降级] 网络不可达，正在使用脱机包进行离线验证...")
            try:
                payload_bytes = base64.b64decode(envelope_b64)
                with open(cfg.license_file_path, "wb") as f:
                    f.write(payload_bytes)
                self._safe_log("-> [脱机包] 落地成功，重新初始化 SDK...")
                self._init_client_impl(cfg)
                self._safe_log("-> [离线验证] 成功！系统完全离线运行中。")
                online_ok = True
            except Exception as ex:
                self._safe_log(f"-> [离线验证] 失败: {ex}")
                self._safe_update_status(None)
                if not self._net_simulates_disconnect():
                    self._restore_network_disconnect_mock()
                return
        elif not online_ok:
            if local_only:
                self._safe_log("-> [阻断] 本地许可无效或无法加载。")
            else:
                self._safe_log("-> [阻断] 在线激活失败且无脱机包，授权流程无法继续。")
            if not self._net_simulates_disconnect():
                self._restore_network_disconnect_mock()
            return

        # 仅「联网」时恢复 HTTP；断网时保持拦截，心跳才会持续失败直至关闭开关
        if not self._net_simulates_disconnect():
            self._restore_network_disconnect_mock()
        else:
            self._safe_log("-> [模拟断网] 保持 HTTP 拦截，心跳将持续失败直至关闭「模拟断网」。")

        # Step 7: 执行业务校验
        try:
            self.client.validate()
            self._safe_log("【业务端】实时合规性检测: 通过。")
            self._safe_log("=" * 50)
            self.after(0, lambda: messagebox.showinfo("业务层", "授权正常！\nAI 模板匹配算法已成功启动，正在处理图像帧..."))
        except Exception as e:
            self._safe_log(f"【业务端】授权拦截: {e}")
            self.after(0, lambda: messagebox.showerror("越权阻断", f"由于未授权或授权已被封禁，算法引擎拒绝启动。\n\n原因: {e}"))

    def _close_client_unsafe(self):
        """关闭 client（须在 UI 线程中调用，或通过 after 异步调用）。"""
        if self.client:
            self.client.close()
            self.client = None


if __name__ == "__main__":
    app = DemoApp()
    app.mainloop()
