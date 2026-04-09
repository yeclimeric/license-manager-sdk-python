# License Manager 客户端模拟器（LMClientSimulator）

这是一个基于 Tkinter GUI 的**授权管理客户端模拟工具**，用于演示和测试 ThingsPanel License Manager SDK 的完整授权流程。工具模拟了机器视觉核心业务的激活、心跳、离线降级等真实场景。

---

## 功能概览

- **设备指纹识别**：自动读取本机 MAC / CPU / 主机名作为硬件唯一标识
- **在线激活**：通过 SaaS 服务端激活授权，支持产品激活码 + 脱机包降级
- **本地缓存验证**：无网络时使用本地 `license.lic` 文件验证授权
- **断网模拟**：一键开启断网模式，测试离线降级与心跳失败场景
- **业务模拟**：演示 AI 模板检测算法在授权通过后才启动的业务流程
- **许可证编辑**：内置编辑器可直接创建 / 修改本地 `license.lic`

---

## 前提条件

- Python 3.7 或更高版本
- `pip` 包管理器

安装 SDK 依赖：

```bash
pip install requests cryptography
```

---

## 使用方式

### 方式一：直接运行 Python 脚本（开发调试用）

```bash
cd LMClientSimulator
python demo.py
```

> 不需要激活码也可以运行，此时工具会读取同目录下的 `license.lic` 文件进行本地验证。

### 方式二：打包为 Windows 可执行文件（exe）

#### 1. 安装 PyInstaller

```bash
pip install pyinstaller
```

#### 2. 执行打包命令

```bash
cd LMClientSimulator
pyinstaller --noconfirm LMClientSimulator-win64.spec
```

> **说明**：打包时工作目录必须为 `LMClientSimulator/` 目录，因为 `demo.py` 内部使用相对路径 `license.lic` 来定位许可证文件。如果在其他目录执行打包，需要同步修改 spec 文件中的 `pathex` 路径。

#### 3. 输出产物

打包完成后，可执行文件位于：

```
LMClientSimulator/dist/LMClientSimulator-win64.exe
```

#### 4. 部署到其他机器

将 `dist/` 目录下的以下文件一起分发即可：

| 文件 | 说明 |
|------|------|
| `LMClientSimulator-win64.exe` | 主程序 |
| `license.lic` | 可选，本地许可证文件（首次运行后会自动生成） |

---

## ico 图标文件位置

如果需要为 exe 添加自定义图标，请在 `LMClientSimulator/` 目录下放置一个名为 **`app.ico`** 的文件：

```
LMClientSimulator/
├── app.ico          ← 放置你的图标文件（必须命名为 app.ico）
├── demo.py
├���─ demo.spec
├── LMClientSimulator-win64.spec
├── license.lic
└── README.md
```

然后在打包命令中指定图标文件：

```bash
pyinstaller --noconfirm --icon=app.ico LMClientSimulator-win64.spec
```

> **关于 ico 文件**：Windows exe 图标必须使用 `.ico` 格式（多分辨率图标集合）。如果您只有 PNG / JPG 等普通图片格式，可以使用在线工具（如 [cloudconvert](https://cloudconvert.com/png-to-ico)）转换为 `.ico` 文件。

---

## 目录结构说明

```
LMClientSimulator/
├── dist/                          # 打包输出目录（最终发布的 exe 在此）
│   ├── LMClientSimulator-win64.exe
│   └── license.lic
├── build/                         # 打包中间产物（可删除）
├── docs/                          # 文档目录
├── app.ico                        # ← exe 图标文件（可选，请命名为 app.ico）
├── demo.py                        # 主程序入口
├── demo.spec                      # PyInstaller 旧版配置（可忽略）
├── LMClientSimulator-win64.spec   # 当前使用的打包配置
├── license.lic                    # 本地许可证文件（首次激活后生成）
└── README.md                      # 本文档
```

---

## 常见问题

**Q: 运行后提示"授权失败"怎么办？**

A: 确保 `LMClientSimulator/` 目录下存在有效的 `license.lic` 文件，或者填写产品激活码（包含脱机包）后重新点击「激活 / 验证」。

**Q: 打包后 exe 在其他机器上无法运行？**

A: 目标机器需要安装对应架构的 Visual C++ Redistributable。也可使用 PyInstaller 的 `--onedir` 模式替代单文件模式以减少依赖。

**Q: 如何获取 app.ico 图标？**

A: 推荐使用以下工具生成 .ico 文件：
- 在线工具：[cloudconvert](https://cloudconvert.com/png-to-ico)
- 桌面工具：GIMP、Photoshop、Affinity Designer 等都支持导出 ico 格式
- 推荐分辨率：256×256 或 512×512 的 PNG 图片

---

## 更多信息

如需了解 SDK 内部的授权机制，请参考项目根目录下的 SDK 文档。