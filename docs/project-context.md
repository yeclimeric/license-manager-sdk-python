# 项目上下文 (Project Context)

## 架构概览 (Architecture Overview)
License Manager SDK (Python): 一个轻量级的 SDK，旨在完全迁移 Go 版本的架构和生命周期概念。

## 关键技术决策 (Key Technical Decisions)
- 使用 `taskloop` 工作流按 MPE (最小程序实体) 级别迭代和测试。
- 使用 Python 标准和常用组件：网络请求使用 `requests`，RSA/AES 验证加解密使用 `cryptography`。

## 当前状态 (Current State)
已通过 TaskLoop 的 DAG 结构完成开发计划的制定。所有 MPE 已识别且定义了验收标准。代码编写与执行尚未开始。

## 已知问题与风险 (Known Issues / Risks)
- 在暂停心跳 (heartbeat) 时需要优雅地处理后台线程的中断。

## 领域知识 (Domain Knowledge)
- 许可证生命周期：在线激活 (Activate) -> 本地加密存储 (Store Locally: AES-GCM) -> 验证签名与防篡改 (Validate: RSA) -> 保持在线心跳 (Heartbeat: Keep-Alive)。
