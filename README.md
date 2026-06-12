# OSINT Toolkit / 开源信息情报工具

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个模块化的开源信息情报（OSINT）工具集，用于从公开来源收集、整理与分析信息。

A modular Open Source Intelligence (OSINT) toolkit for collecting, organizing, and analyzing information from public sources.

## 功能规划 / Roadmap

- [ ] 域名与 DNS 信息收集
- [ ] IP 地址与 ASN 查询
- [ ] 社交媒体公开资料检索
- [ ] 元数据提取（图片、文档）
- [ ] 报告导出（JSON / Markdown / HTML）

## 项目结构 / Project Structure

```
osint-toolkit/
├── src/osint_toolkit/     # 核心代码
│   ├── collectors/        # 信息采集模块
│   ├── analyzers/         # 数据分析模块
│   ├── exporters/         # 报告导出模块
│   └── utils/             # 通用工具
├── config/                # 配置文件
├── tests/                 # 测试
└── docs/                  # 文档
```

## 快速开始 / Quick Start

### 环境要求

- Python 3.10+

### 安装

```bash
# 克隆仓库
git clone https://github.com/guoedge/gochj.git
cd gochj

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"
```

### 使用

```bash
# 查看帮助
osint --help

# 示例：查询域名信息
osint domain example.com
```

## 配置 / Configuration

复制示例配置并按需修改：

```bash
cp config/config.example.yaml config/config.yaml
```

## 开发 / Development

```bash
# 运行测试
pytest

# 代码格式化
ruff check src tests
ruff format src tests
```

## 免责声明 / Disclaimer

本工具仅用于合法的安全研究、授权渗透测试与学术研究。使用者须遵守当地法律法规，作者不对任何滥用行为负责。

This tool is intended for lawful security research, authorized penetration testing, and academic study only. Users must comply with applicable laws. The authors are not responsible for misuse.

## 许可证 / License

[MIT](LICENSE)
