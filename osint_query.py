#!/usr/bin/env python3
"""
OSINT 情报查询工具 - 统一入口
整合 MediaCrawler / bilibili-danmaku / bili2text / TrendRadar 四个工具，
实现一键多平台搜索 + 视频内容识别 + 弹幕分析 + 全网补充。

用法:
    python osint_query.py "DeepSeek vs Kimi 使用体验对比"
    python osint_query.py "GLM-5 评测" --days 7 --platforms zhihu,bilibili,weibo
    python osint_query.py "Qwen3 对比" --no-video --no-danmaku
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ============================================================
# 路径配置 - 各工具的安装位置
# ============================================================
WORKSPACE = Path(__file__).parent.resolve()
MEDIA_CRAWLER_DIR = WORKSPACE / "MediaCrawler"
DANMAKU_DIR = WORKSPACE / "bilibili-danmaku"
BILI2TEXT_DIR = WORKSPACE / "bili2text"
TREND_RADAR_DIR = WORKSPACE / "TrendRadar"

# 输出目录
OUTPUT_BASE = WORKSPACE / "osint_output"


class OSINTQuery:
    """统一情报查询引擎"""

    def __init__(
        self,
        keyword: str,
        days: int = 7,
        platforms: Optional[list[str]] = None,
        enable_video: bool = True,
        enable_danmaku: bool = True,
        enable_trendradar: bool = True,
        max_notes: int = 20,
        max_comments: int = 20,
    ):
        self.keyword = keyword
        self.days = days
        self.platforms = platforms or ["zhihu", "bilibili", "weibo", "tieba", "xhs", "douyin", "kuaishou"]
        self.enable_video = enable_video
        self.enable_danmaku = enable_danmaku
        self.enable_trendradar = enable_trendradar
        self.max_notes = max_notes
        self.max_comments = max_comments

        # 创建本次查询的输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_kw = "".join(c for c in keyword[:30] if c.isalnum() or c in "_ -").strip().replace(" ", "_")
        self.output_dir = OUTPUT_BASE / f"{timestamp}_{safe_kw}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 结果收集
        self.results = {
            "keyword": keyword,
            "query_time": datetime.now().isoformat(),
            "days_range": days,
            "platforms": self.platforms,
            "media_crawler": {"status": "pending", "data_path": None},
            "danmaku": {"status": "pending", "results": []},
            "video_transcript": {"status": "pending", "results": []},
            "trendradar": {"status": "pending", "data_path": None},
        }

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")

    # ============================================================
    # Step 1: MediaCrawler - 多平台搜索+评论采集
    # ============================================================
    def run_media_crawler(self):
        """运行 MediaCrawler 搜索各平台内容"""
        self.log("=" * 60)
        self.log("Step 1: MediaCrawler 多平台搜索+评论采集")
        self.log("=" * 60)

        platform_map = {
            "xhs": "xhs",
            "douyin": "dy",
            "kuaishou": "ks",
            "bilibili": "bili",
            "weibo": "wb",
            "tieba": "tieba",
            "zhihu": "zhihu",
        }

        all_results = {}

        for platform in self.platforms:
            platform_code = platform_map.get(platform)
            if not platform_code:
                self.log(f"  跳过不支持的平台: {platform}")
                continue

            self.log(f"  采集平台: {platform} ({platform_code})")

            # 修改 MediaCrawler 配置
            config_file = MEDIA_CRAWLER_DIR / "config" / "base_config.py"
            if config_file.exists():
                self._patch_media_crawler_config(platform_code, self.keyword)

            # 运行 MediaCrawler
            output_path = self.output_dir / f"mediacrawler_{platform_code}"
            output_path.mkdir(exist_ok=True)

            try:
                cmd = [
                    sys.executable, "-m", "media_crawler",
                    "--platform", platform_code,
                    "--lt", "qrcode",
                    "--type", "search",
                ]
                env = os.environ.copy()
                env["KEYWORDS"] = self.keyword
                env["SAVE_DATA_OPTION"] = "jsonl"
                env["SAVE_DATA_PATH"] = str(output_path)
                env["CRAWLER_MAX_NOTES_COUNT"] = str(self.max_notes)
                env["ENABLE_GET_COMMENTS"] = "True"
                env["CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES"] = str(self.max_comments)
                env["HEADLESS"] = "True"

                self.log(f"    执行: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    cwd=str(MEDIA_CRAWLER_DIR),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode == 0:
                    all_results[platform] = {
                        "status": "success",
                        "output_dir": str(output_path),
                    }
                    self.log(f"    ✓ {platform} 采集完成，数据保存至 {output_path}")
                else:
                    all_results[platform] = {
                        "status": "error",
                        "error": result.stderr[:500] if result.stderr else "unknown error",
                    }
                    self.log(f"    ✗ {platform} 采集失败: {result.stderr[:200] if result.stderr else 'unknown'}")

            except subprocess.TimeoutExpired:
                all_results[platform] = {"status": "timeout"}
                self.log(f"    ✗ {platform} 采集超时")
            except Exception as e:
                all_results[platform] = {"status": "error", "error": str(e)}
                self.log(f"    ✗ {platform} 采集异常: {e}")

        self.results["media_crawler"] = {
            "status": "completed",
            "platforms": all_results,
        }
        return all_results

    def _patch_media_crawler_config(self, platform_code: str, keyword: str):
        """临时修改 MediaCrawler 配置"""
        config_path = MEDIA_CRAWLER_DIR / "config" / "base_config.py"
        if not config_path.exists():
            return

        content = config_path.read_text(encoding="utf-8")
        # 修改平台
        content = self._replace_config(content, 'PLATFORM = "', platform_code, '"')
        # 修改关键词
        content = self._replace_config(content, 'KEYWORDS = "', keyword, '"')
        # 修改排序 - B站按最新
        if platform_code == "bili":
            bilibili_config = MEDIA_CRAWLER_DIR / "config" / "bilibili_config.py"
            if bilibili_config.exists():
                bi_content = bilibili_config.read_text(encoding="utf-8")
                bi_content = self._replace_config(bi_content, 'BILI_SEARCH_MODE = "', 'normal', '"')
                bilibili_config.write_text(bi_content, encoding="utf-8")

        config_path.write_text(content, encoding="utf-8")

    @staticmethod
    def _replace_config(content: str, prefix: str, value: str, suffix: str) -> str:
        """替换配置项的值"""
        import re
        pattern = re.escape(prefix) + r'[^"]*' + re.escape(suffix)
        replacement = prefix + value + suffix
        return re.sub(pattern, replacement, content, count=1)

    # ============================================================
    # Step 2: B站视频内容识别（bili2text）
    # ============================================================
    def run_video_transcription(self, video_urls: Optional[list[str]] = None):
        """将B站视频内容转为文字"""
        if not self.enable_video:
            self.log("跳过视频内容识别（--no-video）")
            return

        self.log("=" * 60)
        self.log("Step 2: B站视频内容识别（bili2text）")
        self.log("=" * 60)

        if not video_urls:
            # 从 MediaCrawler 的输出中提取B站视频链接
            video_urls = self._extract_bilibili_urls()

        if not video_urls:
            self.log("  未找到B站视频链接，跳过视频转文字")
            self.results["video_transcript"] = {
                "status": "skipped",
                "reason": "no_bilibili_urls_found",
            }
            return

        self.log(f"  找到 {len(video_urls)} 个B站视频，开始转文字...")

        transcript_results = []
        for i, url in enumerate(video_urls[:5]):  # 最多处理5个视频
            self.log(f"  处理视频 {i+1}/{min(len(video_urls), 5)}: {url}")
            try:
                output_path = self.output_dir / f"transcript_{i+1}"
                cmd = [
                    sys.executable, "-m", "b2t",
                    "transcribe",
                    url,
                    "--output", str(output_path),
                ]
                result = subprocess.run(
                    cmd,
                    cwd=str(BILI2TEXT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode == 0:
                    transcript_results.append({
                        "url": url,
                        "status": "success",
                        "output": str(output_path),
                    })
                    self.log(f"    ✓ 转文字完成")
                else:
                    transcript_results.append({
                        "url": url,
                        "status": "error",
                        "error": result.stderr[:300] if result.stderr else "unknown",
                    })
                    self.log(f"    ✗ 转文字失败: {result.stderr[:100] if result.stderr else ''}")
            except subprocess.TimeoutExpired:
                transcript_results.append({"url": url, "status": "timeout"})
                self.log(f"    ✗ 转文字超时")
            except Exception as e:
                transcript_results.append({"url": url, "status": "error", "error": str(e)})
                self.log(f"    ✗ 转文字异常: {e}")

        self.results["video_transcript"] = {
            "status": "completed",
            "results": transcript_results,
        }

    def _extract_bilibili_urls(self) -> list[str]:
        """从 MediaCrawler 输出中提取B站视频链接"""
        urls = []
        bili_output = self.output_dir / "mediacrawler_bili"
        if bili_output.exists():
            for f in bili_output.glob("*.jsonl"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        for line in fh:
                            if line.strip():
                                data = json.loads(line)
                                url = data.get("video_url") or data.get("url", "")
                                if "bilibili.com/video" in url:
                                    urls.append(url)
                except Exception:
                    pass
        return urls

    # ============================================================
    # Step 3: B站弹幕抓取+情感分析
    # ============================================================
    def run_danmaku_analysis(self, video_urls: Optional[list[str]] = None):
        """抓取B站弹幕并做情感分析"""
        if not self.enable_danmaku:
            self.log("跳过弹幕分析（--no-danmaku）")
            return

        self.log("=" * 60)
        self.log("Step 3: B站弹幕抓取+情感分析")
        self.log("=" * 60)

        if not video_urls:
            video_urls = self._extract_bilibili_urls()

        if not video_urls:
            self.log("  未找到B站视频链接，跳过弹幕分析")
            self.results["danmaku"] = {
                "status": "skipped",
                "reason": "no_bilibili_urls_found",
            }
            return

        self.log(f"  找到 {len(video_urls)} 个B站视频，开始弹幕分析...")

        danmaku_results = []
        for i, url in enumerate(video_urls[:5]):  # 最多处理5个视频
            self.log(f"  处理视频 {i+1}/{min(len(video_urls), 5)}: {url}")
            try:
                # Step 3a: 抓取弹幕
                danmaku_output = self.output_dir / "danmaku"
                danmaku_output.mkdir(exist_ok=True)

                fetch_script = DANMAKU_DIR / "scripts" / "fetch_danmaku.py"
                cmd_fetch = [
                    sys.executable, str(fetch_script),
                    "--url", url,
                    "--outdir", str(danmaku_output),
                ]
                result = subprocess.run(
                    cmd_fetch,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode != 0:
                    danmaku_results.append({
                        "url": url,
                        "status": "fetch_error",
                        "error": result.stderr[:300] if result.stderr else "unknown",
                    })
                    self.log(f"    ✗ 弹幕抓取失败")
                    continue

                # 找到输出的 CSV 文件
                csv_files = list(danmaku_output.glob("*_danmaku.csv"))
                meta_files = list(danmaku_output.glob("*_meta.json"))

                if not csv_files:
                    danmaku_results.append({
                        "url": url,
                        "status": "no_danmaku",
                    })
                    self.log(f"    ⚠ 未抓到弹幕")
                    continue

                csv_path = str(csv_files[-1])
                meta_path = str(meta_files[-1]) if meta_files else ""

                # Step 3b: 情感分析
                analyze_script = DANMAKU_DIR / "scripts" / "analyze_danmaku.py"
                analyze_output = self.output_dir / "danmaku_analysis"
                analyze_output.mkdir(exist_ok=True)

                bvid = Path(csv_path).stem.replace("_danmaku", "").split("_")[0]
                cmd_analyze = [
                    sys.executable, str(analyze_script),
                    "--csv", csv_path,
                    "--meta", meta_path,
                    "--outdir", str(analyze_output),
                    "--name", f"{bvid}_{self.keyword[:10]}",
                ]
                result = subprocess.run(
                    cmd_analyze,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                danmaku_results.append({
                    "url": url,
                    "status": "success",
                    "csv": csv_path,
                    "analysis_dir": str(analyze_output),
                })
                self.log(f"    ✓ 弹幕分析完成")

            except subprocess.TimeoutExpired:
                danmaku_results.append({"url": url, "status": "timeout"})
                self.log(f"    ✗ 弹幕分析超时")
            except Exception as e:
                danmaku_results.append({"url": url, "status": "error", "error": str(e)})
                self.log(f"    ✗ 弹幕分析异常: {e}")

        self.results["danmaku"] = {
            "status": "completed",
            "results": danmaku_results,
        }

    # ============================================================
    # Step 4: TrendRadar - 全网热点补充搜索
    # ============================================================
    def run_trendradar(self):
        """运行 TrendRadar 搜索全网最新内容"""
        if not self.enable_trendradar:
            self.log("跳过 TrendRadar（--no-trendradar）")
            return

        self.log("=" * 60)
        self.log("Step 4: TrendRadar 全网热点补充搜索")
        self.log("=" * 60)

        # 更新 TrendRadar 关键词配置
        self._patch_trendradar_config()

        trendradar_output = self.output_dir / "trendradar"
        trendradar_output.mkdir(exist_ok=True)

        try:
            # 运行 TrendRadar 单次抓取
            cmd = [
                sys.executable, "-m", "trendradar",
                "--once",
                "--output", str(trendradar_output),
            ]
            env = os.environ.copy()
            env["TRENDRADAR_CONFIG"] = str(TREND_RADAR_DIR / "config" / "config.yaml")

            result = subprocess.run(
                cmd,
                cwd=str(TREND_RADAR_DIR),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                self.results["trendradar"] = {
                    "status": "success",
                    "output_dir": str(trendradar_output),
                }
                self.log(f"  ✓ TrendRadar 搜索完成，数据保存至 {trendradar_output}")
            else:
                # 尝试直接用 Python 运行
                self.log(f"  尝试直接运行 TrendRadar...")
                cmd2 = [
                    sys.executable, str(TREND_RADAR_DIR / "trendradar" / "__main__.py"),
                ]
                result2 = subprocess.run(
                    cmd2,
                    cwd=str(TREND_RADAR_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.results["trendradar"] = {
                    "status": "partial" if result2.returncode == 0 else "error",
                    "output_dir": str(trendradar_output),
                    "note": "TrendRadar 通常作为定时任务运行，单次运行可能需要配置调度",
                }
                self.log(f"  ⚠ TrendRadar 已执行，建议配合定时任务使用")

        except subprocess.TimeoutExpired:
            self.results["trendradar"] = {"status": "timeout"}
            self.log(f"  ✗ TrendRadar 超时")
        except Exception as e:
            self.results["trendradar"] = {"status": "error", "error": str(e)}
            self.log(f"  ✗ TrendRadar 异常: {e}")

    def _patch_trendradar_config(self):
        """更新 TrendRadar 的关键词配置"""
        words_file = TREND_RADAR_DIR / "config" / "frequency_words.txt"
        if not words_file.exists():
            return

        content = words_file.read_text(encoding="utf-8")

        # 在 [WORD_GROUPS] 区域添加查询关键词
        # 先检查是否已存在
        if self.keyword not in content:
            # 在 [WORD_GROUPS] 后追加
            lines = content.split("\n")
            word_group_idx = None
            for i, line in enumerate(lines):
                if line.strip() == "[WORD_GROUPS]":
                    word_group_idx = i
                    break

            if word_group_idx is not None:
                # 在词组区域最前面插入
                insert_idx = word_group_idx + 1
                lines.insert(insert_idx, "")
                lines.insert(insert_idx + 1, f"[OSINT查询: {self.keyword}]")
                # 将关键词拆分并添加
                words = self.keyword.replace(" vs ", "\n").replace(" ", "\n").replace("、", "\n").split("\n")
                for w in words:
                    w = w.strip()
                    if w:
                        lines.insert(insert_idx + 2, w)

                words_file.write_text("\n".join(lines), encoding="utf-8")
                self.log(f"  已更新 TrendRadar 关键词配置")

    # ============================================================
    # 主流程
    # ============================================================
    def run(self):
        """执行完整查询流程"""
        self.log(f"开始情报查询: '{self.keyword}'")
        self.log(f"时间范围: 最近 {self.days} 天")
        self.log(f"目标平台: {', '.join(self.platforms)}")
        self.log(f"输出目录: {self.output_dir}")
        self.log("")

        # Step 1: MediaCrawler 多平台搜索
        self.run_media_crawler()

        # Step 2: B站视频内容识别
        self.run_video_transcription()

        # Step 3: B站弹幕分析
        self.run_danmaku_analysis()

        # Step 4: TrendRadar 全网补充
        self.run_trendradar()

        # 保存查询结果摘要
        self._save_summary()

        self.log("")
        self.log("=" * 60)
        self.log("查询完成！")
        self.log(f"结果保存至: {self.output_dir}")
        self.log("=" * 60)

        return self.results

    def _save_summary(self):
        """保存查询结果摘要"""
        summary_path = self.output_dir / "query_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        # 生成可读的 Markdown 摘要
        md_path = self.output_dir / "query_summary.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 情报查询报告: {self.keyword}\n\n")
            f.write(f"- 查询时间: {self.results['query_time']}\n")
            f.write(f"- 时间范围: 最近 {self.days} 天\n")
            f.write(f"- 目标平台: {', '.join(self.platforms)}\n\n")

            # MediaCrawler 结果
            mc = self.results.get("media_crawler", {})
            f.write("## 1. 多平台搜索结果（MediaCrawler）\n\n")
            platforms = mc.get("platforms", {})
            for plat, info in platforms.items():
                status = info.get("status", "unknown")
                icon = "✓" if status == "success" else "✗"
                f.write(f"- {icon} **{plat}**: {status}\n")
            f.write("\n")

            # 视频转文字结果
            vt = self.results.get("video_transcript", {})
            f.write("## 2. B站视频内容识别（bili2text）\n\n")
            f.write(f"- 状态: {vt.get('status', 'unknown')}\n")
            for r in vt.get("results", []):
                status = r.get("status", "unknown")
                icon = "✓" if status == "success" else "✗"
                f.write(f"  - {icon} {r.get('url', '')}: {status}\n")
            f.write("\n")

            # 弹幕分析结果
            dm = self.results.get("danmaku", {})
            f.write("## 3. B站弹幕分析（bilibili-danmaku）\n\n")
            f.write(f"- 状态: {dm.get('status', 'unknown')}\n")
            for r in dm.get("results", []):
                status = r.get("status", "unknown")
                icon = "✓" if status == "success" else "✗"
                f.write(f"  - {icon} {r.get('url', '')}: {status}\n")
                if status == "success" and r.get("analysis_dir"):
                    f.write(f"    - 分析报告: {r['analysis_dir']}\n")
            f.write("\n")

            # TrendRadar 结果
            tr = self.results.get("trendradar", {})
            f.write("## 4. 全网热点补充（TrendRadar）\n\n")
            f.write(f"- 状态: {tr.get('status', 'unknown')}\n")
            if tr.get("output_dir"):
                f.write(f"- 输出目录: {tr['output_dir']}\n")
            f.write("\n")

            f.write("---\n")
            f.write(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

        self.log(f"摘要报告: {md_path}")


# ============================================================
# 独立工具：B站弹幕快速分析（不依赖 MediaCrawler）
# ============================================================
def quick_danmaku_analysis(url: str, output_dir: str = "./osint_output/quick_danmaku"):
    """快速分析单个B站视频的弹幕"""
    print(f"快速弹幕分析: {url}")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # 抓取弹幕
    fetch_script = DANMAKU_DIR / "scripts" / "fetch_danmaku.py"
    subprocess.run([
        sys.executable, str(fetch_script),
        "--url", url,
        "--outdir", str(output),
    ], check=True)

    # 分析弹幕
    csv_files = list(output.glob("*_danmaku.csv"))
    meta_files = list(output.glob("*_meta.json"))

    if csv_files:
        analyze_script = DANMAKU_DIR / "scripts" / "analyze_danmaku.py"
        subprocess.run([
            sys.executable, str(analyze_script),
            "--csv", str(csv_files[-1]),
            "--meta", str(meta_files[-1]) if meta_files else "",
            "--outdir", str(output),
        ], check=True)

    print(f"分析完成，结果保存在: {output}")


# ============================================================
# 独立工具：B站视频快速转文字
# ============================================================
def quick_video_transcribe(url: str, output_dir: str = "./osint_output/quick_transcript"):
    """快速将B站视频转为文字"""
    print(f"视频转文字: {url}")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    subprocess.run([
        sys.executable, "-m", "b2t",
        "transcribe", url,
        "--output", str(output),
    ], cwd=str(BILI2TEXT_DIR), check=True)

    print(f"转文字完成，结果保存在: {output}")


# ============================================================
# CLI 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="OSINT 情报查询工具 - 多平台搜索+视频识别+弹幕分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 全平台搜索 DeepSeek 评测
  python osint_query.py "DeepSeek 评测"

  # 指定平台和时间范围
  python osint_query.py "Kimi vs GLM 对比" --days 7 --platforms zhihu,bilibili

  # 只搜索不分析视频和弹幕
  python osint_query.py "Qwen3 体验" --no-video --no-danmaku

  # 快速弹幕分析
  python osint_query.py --quick-danmaku "https://www.bilibili.com/video/BV1xxx"

  # 快速视频转文字
  python osint_query.py --quick-transcribe "https://www.bilibili.com/video/BV1xxx"
        """,
    )

    parser.add_argument("keyword", nargs="?", help="查询关键词")
    parser.add_argument("--days", type=int, default=7, help="时间范围（天），默认7天")
    parser.add_argument("--platforms", default=None, help="目标平台，逗号分隔: zhihu,bilibili,weibo,tieba,xhs,douyin,kuaishou")
    parser.add_argument("--no-video", action="store_true", help="跳过视频内容识别")
    parser.add_argument("--no-danmaku", action="store_true", help="跳过弹幕分析")
    parser.add_argument("--no-trendradar", action="store_true", help="跳过 TrendRadar")
    parser.add_argument("--max-notes", type=int, default=20, help="每个平台最大采集条数")
    parser.add_argument("--max-comments", type=int, default=20, help="每条内容最大评论数")

    # 快捷模式
    parser.add_argument("--quick-danmaku", metavar="URL", help="快速分析单个B站视频弹幕")
    parser.add_argument("--quick-transcribe", metavar="URL", help="快速将B站视频转文字")

    args = parser.parse_args()

    # 快捷模式
    if args.quick_danmaku:
        quick_danmaku_analysis(args.quick_danmaku)
        return

    if args.quick_transcribe:
        quick_video_transcribe(args.quick_transcribe)
        return

    # 标准模式
    if not args.keyword:
        parser.error("请提供查询关键词，或使用 --quick-danmaku / --quick-transcribe")

    platforms = None
    if args.platforms:
        platforms = [p.strip() for p in args.platforms.split(",")]

    query = OSINTQuery(
        keyword=args.keyword,
        days=args.days,
        platforms=platforms,
        enable_video=not args.no_video,
        enable_danmaku=not args.no_danmaku,
        enable_trendradar=not args.no_trendradar,
        max_notes=args.max_notes,
        max_comments=args.max_comments,
    )
    query.run()


if __name__ == "__main__":
    main()
