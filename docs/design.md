# License Manager Python SDK 设计

## 1. 设计目标
- 提供统一、低侵入的 Python SDK 以封装激活、校验、心跳、许可证管理流程。
- 兼容现有 License Manager 服务端接口，在线/离线模式对业务透明。
- 高可扩展与可测试性：硬件指纹、存储、网络协议处理器等核心可替换（duck typing 理念）。

## 2. 交付范围
- 符合 PEP 标准的 Python 包源码。
- 依赖描述文件（`requirements.txt` / `setup.py`）。
- 示例：最小化直接调用的基础示例 `examples/basic/main.py`。
- 面向 Python 的技术文档。

## 3. 核心模块设计说明
- **client.Client (门面模式)**
  - 组合各模块，提供 `__init__`, `validate`, `current_license`, `close` 等方法。
  - 维护内部状态，并通过 `threading.Lock` 等保证线程安全访问当前 License 版本。
- **config (配置与数据校验)**
  - 定义明确具有 Type hints 的类或 `dataclasses`，支持将环境及文件属性覆盖。
  - 静态检查：在线模式验证服务端必须 URL / 密码文件；离线模式检验证书位置。
- **activation (激活)**
  - 基于标准的 `requests`（带连接池和自动超时重试策略）发起网络激活通信。
  - 接收加密串后调用 validator 核验，成功后通过 storage 保存。
- **validator (强安全验证)**
  - 依托强大的 `cryptography` 包处理 RSA (建议为 PSS padding 等现代方法，具体匹配服务端实现)。
  - 对解包出的许可证时间 `ExpiresAt`、硬件指纹进行 CPU 负载级的精确比较并验证未发生人为修改。
- **heartbeat (心跳维护)**
  - 取代 Go 的 goroutine 使用，改用由 `threading.Thread` 的轮询服务。设置 `daemon=True` 防止卡顿主进程。
  - 设计线程安全的 `threading.Event()` 实现如 `pause`, `resume`, `stop` 这些外部调度接口。
  - 对于网络闪断具有一定指数回退 (Exponential backoff) 容量。
- **hardware (多态指纹搜集)**
  - 抽象采集策略，利用系统底层命令及 `uuid`、`platform` 以避免绑定复杂的原生编译依赖（如果在 CPython 环境可引入 psutil 或仅靠 standard libs 执行降级采集策略）。
- **storage (凭证安全落地)**
  - 文件加解密适配 `cryptography` 在 AES-GCM 算法下使用 256bit 动态密钥做密文打包，防本地脱机逆向嗅探。
- **logger & exceptions (日志体系监控)**
  - 使用标准的 `logging` 获取当前全局记录器。
  - 设计带有分类标记的 `LicenseManagerError`, `NetworkError`, `ValidationError` 提供可分辨的控制流分支。

## 4. 关键生命周期总结
1. **实例化**：加载配置 → 初始化硬件信息/日志/存储机制 → 调用 validator 验算本地既有证书 → 按需挂起并调用 activation 发在线网路激活申请。
2. **后台伴生**：启动 heartbeat daemon → 在给定 `interval` 进行上游 pinging → 若上游发来更新证，回调主线程数据结构；若请求重新激活，则触发 callback 进入阻塞警报。
3. **断网本地态**：应用随时拉起 `client.validate()`。验证不通过抛出 SDK 特有 `Exception`，应用层捕获异常并决定关停自身业务。

## 5. 对比补充与潜在风险
- **包依赖风险**：为降低部署繁杂度，若系统有条件应考虑避免引用含有大量 C 扩展的包，优先利用 Python 3 自带库封装；必须时则明确说明并列在依赖清单首位 (如 `cryptography`)。
- **定时锁和 GIL 干扰**：心跳网络收发本质是 I/O 阻塞型操作，采用线程天然适合，且不易阻断业务代码，但在多线程中覆盖验证缓存 `current_license` 必须添加明确锁保护（`threading.RLock()`），确保不产生竞争读写现象。
