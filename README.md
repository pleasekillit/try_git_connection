# pyFastGithub

`FastGithub` 的 Python 重写版（方案 A：本地 HTTP 代理 + HTTPS 中间人，纯用户态，不依赖 WinDivert 驱动）。

面向 Windows，先把 CLI 跑通，界面后续再说。

## 特性

- 本地 HTTP 代理（默认 `127.0.0.1:38457`），自动设置/还原 Windows 系统代理
- HTTPS 中间人：自建 CA + 按域名动态签发证书
- 纯净 DNS 解析（DoH / TCP DNS）绕过污染
- 多 IP 并发 TCP 测速，选最快的 IP 作为上游
- 按域名规则定制上游 TLS 的 SNI（可关闭 SNI、可伪造 SNI、可忽略证书域名不匹配）
- 配置与代码分离：域名规则、DNS、超时等都放在 `data/` 目录的 JSON 中

## 目录结构

```
pyFastGithub/
├── docs/                需求文档 / 概要设计 / 详细设计
├── data/               配置数据（与代码分离）
│   ├── appsettings.json
│   └── appsettings/     按域名分组的规则
├── scripts/             源码
├── tests/               pytest 自测
├── cacert/              运行时生成的 CA 与域名证书
└── requirements.txt
```

## 快速开始

```powershell
# 1. 创建虚拟环境（已创建可跳过）
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 信任自签 CA（写入当前用户证书库，无需管理员，只需执行一次）
.\.venv\Scripts\python.exe -m scripts install-ca

# 3. 启动代理（自动设置系统代理）
.\.venv\Scripts\python.exe -m scripts run
```

停止：`Ctrl+C`，程序会自动还原系统代理设置。

## 常用命令

```powershell
.\.venv\Scripts\python.exe -m scripts run --port 38457 --no-system-proxy
.\.venv\Scripts\python.exe -m scripts install-ca
.\.venv\Scripts\python.exe -m pytest
```

## git 使用提示

若 git 提示 `SSL certificate problem`：

```powershell
git config --global http.sslverify false
```

## 免责声明

本工具不具备"翻墙"能力，仅用于改善对 GitHub 等域名的解析质量与连通性。