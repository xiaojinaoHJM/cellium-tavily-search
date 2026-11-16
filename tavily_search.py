# -*- coding: utf-8 -*-
"""
Tavily AI 搜索工具 — Cellium 组件

创建时间: 2026-05-20
更新时间: 2026-11-16

────────────────────────────────────────
命令说明
────────────────────────────────────────

【search】AI 增强搜索
  用法: tavily_search command=search args="关键词"
  参数:
    - args: 搜索关键词（纯文本）或 JSON 字符串
    - kwargs: 额外参数 JSON（可选）

  JSON 参数说明:
    - query: 搜索关键词（必填）
    - max_results: 结果数量，默认 3，最大 5
    - search_depth: "basic"(快) 或 "advanced"(深)
    - include_answer: 是否返回 AI 总结答案，默认 False
    - topic: "general"(通用) 或 "news"(新闻)

  示例:
    args=掌阅科技涨停
    args={"query":"AI短剧","max_results":5,"include_answer":true}

【search_news】新闻搜索
  用法: tavily_search command=search_news args="关键词"
  参数:
    - args: 搜索关键词
    - kwargs: 额外参数 JSON（可选）

  JSON 参数:
    - query: 搜索关键词
    - max_results: 结果数量，默认 3，最大 5
    - days: 搜索天数范围，默认 3

【extract】提取网页内容
  用法: tavily_search command=extract args="URL"
  参数:
    - args: URL 或 JSON 字符串
    - kwargs: 额外参数 JSON（可选）

  JSON 参数:
    - urls: URL 列表，最多 3 个

  示例:
    args=https://example.com
    args={"urls":["https://a.com","https://b.com"]}

【crawl】爬取网站多页
  用法: tavily_search command=crawl args='{"url":"https://..."}'
  参数:
    - args: JSON 参数
    - kwargs: 额外参数 JSON（可选）

  JSON 参数:
    - url: 网站 URL（必填）
    - max_depth: 爬取深度，默认 1，最大 2
    - limit: 页面数量，默认 5，最大 10

【config】配置 API Key
  用法: tavily_search command=config args="tvly-xxxx"
  说明: 写入 config/tavily.yaml，也可用环境变量 TAVILY_API_KEY

【help】查看帮助
  用法: tavily_search command=help topic="search"

────────────────────────────────────────
安全限制
────────────────────────────────────────
- search: max_results <= 5, content <= 500字符/条
- search_news: max_results <= 5, days <= 7
- extract: urls <= 3, 每页 <= 8000字符, 总计 <= 20000字符
- crawl: max_depth <= 2, limit <= 10, 每页 <= 5000字符, 总计 <= 30000字符
────────────────────────────────────────
"""
import json
import os
from typing import Any, Dict, List, Optional

from app.core.interface.base_cell import BaseCell


class TavilySearch(BaseCell):
    """Tavily AI 搜索工具，专为 AI 设计的搜索 API"""

    # 不内置任何 API Key（避免私人凭据随组件分发）
    # 请通过环境变量 TAVILY_API_KEY 或 config/tavily.yaml 的 api_key 配置
    DEFAULT_API_KEY = ""

    @property
    def cell_name(self) -> str:
        return "tavily_search"

    def _load_config(self) -> Dict[str, Any]:
        """读取 config/tavily.yaml（可选）"""
        try:
            import yaml
            from pathlib import Path
            cfg_file = Path(__file__).resolve().parent.parent / "config" / "tavily.yaml"
            if cfg_file.exists():
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {}

    def _get_client(self):
        """获取 Tavily 客户端（懒加载）"""
        try:
            from tavily import TavilyClient
        except ImportError:
            raise ImportError("tavily-python 未安装，请运行: pip install tavily-python")
        cfg = self._load_config()
        api_key = (
            cfg.get("api_key")
            or os.environ.get("TAVILY_API_KEY")
            or self.DEFAULT_API_KEY
        )
        if not api_key:
            raise RuntimeError(
                "未配置 Tavily API Key：请设置环境变量 TAVILY_API_KEY，"
                "或在 config/tavily.yaml 中写入 api_key: tvly-xxxx"
            )
        return TavilyClient(api_key=api_key)

    def _parse_params(self, args: str = "", kwargs: str = "") -> Dict[str, Any]:
        """解析参数（支持 JSON 字符串或纯文本）"""
        params = {}
        if args:
            try:
                parsed = json.loads(args)
                if isinstance(parsed, dict):
                    params = parsed
                else:
                    params = {"query": str(args)}
            except json.JSONDecodeError:
                params = {"query": args}
        if kwargs:
            try:
                kw = json.loads(kwargs)
                if isinstance(kw, dict):
                    params.update(kw)
            except json.JSONDecodeError:
                pass
        return params

    def _cmd_search(self, args: str = "", kwargs: str = "", **extra) -> Dict[str, Any]:
        """
        AI 增强搜索，返回结构化结果（Token 安全版）

        Args:
            args: 搜索关键词或 JSON: {"query": "词", "max_results": 3}
            kwargs: 额外参数 JSON

        安全限制（强制）：
            - max_results: 默认 3，最大 5（限制结果数）
            - include_answer: 默认 False（避免额外 token 消耗）
            - 每条 content 截断至 500 字符

        Returns:
            {"success": bool, "answer": str, "results": [...]}
        """
        params = self._parse_params(args, kwargs)
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "搜索关键词不能为空"}

        # 安全限制：强制上限
        max_results = min(int(params.get("max_results", 3)), 5)  # 默认3，最大5
        search_depth = params.get("search_depth", "basic")
        include_answer = params.get("include_answer", False)  # 默认关闭，节省 token
        topic = params.get("topic", "general")
        max_content_chars = 500  # 每条结果最多500字符

        try:
            client = self._get_client()
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_answer=include_answer,
                topic=topic,
            )

            # 截断 answer（如果开启）- 防止 None 值
            answer = response.get("answer") or ""
            if len(answer) > 800:
                answer = answer[:800] + "...[答案已截断]"

            results = []
            for r in response.get("results", []):
                content = r.get("content") or ""
                if len(content) > max_content_chars:
                    content = content[:max_content_chars] + "...[内容已截断]"
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": content,
                    "score": r.get("score", 0),
                })

            return {
                "success": True,
                "query": query,
                "answer": answer,
                "results": results,
                "count": len(results),
                "search_config": {
                    "max_results": max_results,
                    "include_answer": include_answer,
                    "content_truncated": any(len(r.get("content", "")) > max_content_chars for r in response.get("results", []))
                },
            }
        except Exception as e:
            return {"success": False, "error": f"搜索失败: {str(e)}"}

    def _cmd_search_news(self, args: str = "", kwargs: str = "", **extra) -> Dict[str, Any]:
        """
        新闻搜索（Token 安全版）

        Args:
            args: 搜索关键词或 JSON: {"query": "词", "max_results": 3, "days": 3}
            kwargs: 额外参数 JSON

        安全限制（强制）：
            - max_results: 默认 3，最大 5
            - 每条 content 截断至 500 字符

        Returns:
            {"success": bool, "results": [...]}
        """
        params = self._parse_params(args, kwargs)
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "搜索关键词不能为空"}

        # 安全限制
        max_results = min(int(params.get("max_results", 3)), 5)  # 默认3，最大5
        days = int(params.get("days", 3))
        max_content_chars = 500

        try:
            client = self._get_client()
            response = client.search(
                query=query,
                max_results=max_results,
                topic="news",
                days=days,
            )

            results = []
            for r in response.get("results", []):
                content = r.get("content", "")
                if len(content) > max_content_chars:
                    content = content[:max_content_chars] + "...[已截断]"
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": content,
                    "published_date": r.get("published_date", ""),
                    "score": r.get("score", 0),
                })

            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {"success": False, "error": f"新闻搜索失败: {str(e)}"}

    def _cmd_extract(self, args: str = "", kwargs: str = "", **extra) -> Dict[str, Any]:
        """
        提取网页原始内容（Token 安全版）

        Args:
            args: URL 或 JSON: {"urls": ["https://..."]}
            kwargs: 额外参数 JSON

        安全限制（强制）：
            - urls: 最多 3 个（防止批量抓取）
            - 每页内容截断至 8000 字符（单页上限）
            - 总内容不超过 20000 字符（防止撑爆上下文）

        Returns:
            {"success": bool, "results": [...], "truncated": bool}
        """
        params = self._parse_params(args, kwargs)
        urls = params.get("urls", [])

        # 如果 args 是纯文本 URL
        if not urls and args and not args.strip().startswith("{"):
            urls = [args.strip()]

        if not urls:
            return {"success": False, "error": "请提供 URL"}

        # 安全限制：最多 3 个 URL
        urls = urls[:3]

        # 配置
        max_chars_per_page = 8000  # 单页最多 8000 字符
        max_total_chars = 20000   # 总内容最多 20000 字符

        try:
            client = self._get_client()
            response = client.extract(urls=urls)

            results = []
            total_chars = 0
            truncated_pages = []

            for r in response.get("results", []):
                content = r.get("raw_content", "")
                url = r.get("url", "")

                # 截断过长的单页内容
                if len(content) > max_chars_per_page:
                    content = content[:max_chars_per_page] + "\n\n...[内容已截断，原长度: {} 字符]".format(len(r.get("raw_content", "")))
                    truncated_pages.append(url)

                # 检查总内容长度
                if total_chars + len(content) > max_total_chars:
                    # 达到上限，停止添加更多内容
                    remaining = max_total_chars - total_chars
                    if remaining > 0:
                        content = content[:remaining] + "\n\n...[总内容已达上限，停止抓取]"
                        results.append({
                            "url": url,
                            "raw_content": content,
                            "truncated": True,
                        })
                    break

                results.append({
                    "url": url,
                    "raw_content": content,
                    "truncated": url in truncated_pages,
                })
                total_chars += len(content)

            failed_urls = response.get("failed_results", [])

            return {
                "success": True,
                "results": results,
                "failed_urls": failed_urls,
                "count": len(results),
                "total_chars": total_chars,
                "estimated_tokens": total_chars // 4,
                "truncated": len(truncated_pages) > 0 or total_chars >= max_total_chars,
                "safety_note": f"已限制为 {len(urls)} 个 URL，每页最多 {max_chars_per_page} 字符",
            }
        except Exception as e:
            return {"success": False, "error": f"提取失败: {str(e)}"}

    def _cmd_crawl(self, args: str = "", kwargs: str = "", **extra) -> Dict[str, Any]:
        """
        爬取网站多个页面（Token 安全版 - 主动截断）

        Args:
            args: JSON: {"url": "https://...", "max_depth": 1, "limit": 5}
            kwargs: 额外参数 JSON

        安全限制（强制）：
            - max_depth: 默认 1，最大 2（防止 Token 爆炸）
            - limit: 默认 5，最大 10（限制页面数）
            - 每页内容截断至 5000 字符
            - 总内容上限 30000 字符（超过则主动停止抓取）

        Returns:
            {"success": bool, "results": [...], "safety_info": {...}}
        """
        params = self._parse_params(args, kwargs)
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "请提供 URL"}

        # 安全限制：强制上限
        max_depth = min(int(params.get("max_depth", 1)), 2)  # 默认1，最大2
        limit = min(int(params.get("limit", 5)), 10)  # 默认5，最大10
        max_chars_per_page = 5000  # 每页最多5000字符
        max_total_chars = 30000   # 总内容最多30000字符（约7500 tokens）

        try:
            client = self._get_client()
            response = client.crawl(
                url=url,
                max_depth=max_depth,
                limit=limit,
            )

            results = []
            total_chars = 0
            stopped_early = False

            for r in response.get("results", []):
                content = r.get("raw_content", "")
                page_url = r.get("url", "")

                # 截断过长的单页内容
                original_len = len(content)
                if len(content) > max_chars_per_page:
                    content = content[:max_chars_per_page] + "\n...[内容已截断，原长度: {} 字符]".format(original_len)

                # 检查总内容长度 - 主动停止抓取
                if total_chars + len(content) > max_total_chars:
                    stopped_early = True
                    remaining = max_total_chars - total_chars
                    if remaining > 100:  # 至少保留100字符才有意义
                        content = content[:remaining] + "\n\n...[已达到安全上限，停止抓取]"
                        results.append({
                            "url": page_url,
                            "raw_content": content,
                            "chars": len(content),
                            "truncated": True,
                        })
                    break

                results.append({
                    "url": page_url,
                    "raw_content": content,
                    "chars": len(content),
                    "truncated": original_len > max_chars_per_page,
                })
                total_chars += len(content)

            # Token 估算
            estimated_tokens = total_chars // 4

            return {
                "success": True,
                "url": url,
                "results": results,
                "count": len(results),
                "total_chars": total_chars,
                "estimated_tokens": estimated_tokens,
                "stopped_early": stopped_early,
                "safety_info": {
                    "max_depth_used": max_depth,
                    "limit_used": limit,
                    "max_chars_per_page": max_chars_per_page,
                    "max_total_chars": max_total_chars,
                    "message": "已启用 Token 安全保护，内容已截断至安全范围" if stopped_early or total_chars > 10000 else "内容在安全范围内"
                },
            }
        except Exception as e:
            return {"success": False, "error": f"爬取失败: {str(e)}"}

    def _cmd_config(self, args: str = "", kwargs: str = "", **extra) -> Dict[str, Any]:
        """查看或设置 Tavily 配置（api_key 写入 config/tavily.yaml）

        Args:
            args: 直接传 api_key（如 tvly-xxxx）；留空则查看当前配置（脱敏）
            kwargs: 额外参数 JSON，如 {"api_key": "tvly-xxxx"}

        Returns:
            当前配置来源与脱敏后的 key，或写入结果
        """
        from pathlib import Path

        params: Dict[str, Any] = {}
        if args and args.strip():
            s = args.strip()
            if s.startswith("{"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, dict):
                        params.update(parsed)
                except Exception:
                    pass
            else:
                params["api_key"] = s
        if kwargs:
            try:
                parsed = json.loads(kwargs) if isinstance(kwargs, str) else kwargs
                if isinstance(parsed, dict):
                    params.update(parsed)
            except Exception:
                pass
        params.update({k: v for k, v in extra.items() if v})

        cfg_path = Path(__file__).resolve().parent.parent / "config" / "tavily.yaml"
        cfg = self._load_config()
        new_key = str(params.get("api_key") or "").strip()

        if not new_key:
            cur = cfg.get("api_key") or os.environ.get("TAVILY_API_KEY") or self.DEFAULT_API_KEY or ""
            masked = ("%s...%s" % (cur[:8], cur[-4:])) if len(cur) > 12 else ("***" if cur else "(未配置)")
            src = ("config/tavily.yaml" if cfg.get("api_key")
                   else ("环境变量 TAVILY_API_KEY" if os.environ.get("TAVILY_API_KEY") else "无"))
            return {
                "success": True,
                "config_file": str(cfg_path),
                "has_key": bool(cur),
                "api_key": masked,
                "source": src,
                "usage": '设置 key: tavily_search command=config args="tvly-xxxx"',
            }

        cfg["api_key"] = new_key
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            import yaml
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write("# 本机私有配置（不随组件分发）\n")
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
            try:
                os.chmod(cfg_path, 0o600)
            except Exception:
                pass
        except Exception as e:
            return {"success": False, "error": "写入失败: %s" % (e,)}
        return {
            "success": True,
            "config_file": str(cfg_path),
            "message": "api_key 已保存并立即生效",
            "api_key": ("%s...%s" % (new_key[:8], new_key[-4:])) if len(new_key) > 12 else "***",
        }

    def _cmd_help(self, topic: str = "", **kwargs) -> Dict[str, Any]:
        """查看帮助"""
        return {
            "component": "tavily_search",
            "description": "Tavily AI 搜索工具，专为 AI 设计的搜索 API",
            "commands": {
                "search": {
                    "desc": "AI 增强搜索",
                    "input_data": "搜索关键词或 JSON: {\"query\": \"词\", \"max_results\": 5, \"search_depth\": \"basic\", \"include_answer\": true}",
                    "note": "search_depth: basic(快) / advanced(深); topic: general / news",
                },
                "search_news": {
                    "desc": "新闻搜索",
                    "input_data": "搜索关键词或 JSON: {\"query\": \"词\", \"max_results\": 5, \"days\": 3}",
                },
                "extract": {
                    "desc": "提取网页原始内容",
                    "input_data": "URL 或 JSON: {\"urls\": [\"https://...\"]}",
                },
                "crawl": {
                    "desc": "爬取网站多个页面",
                    "input_data": "JSON: {\"url\": \"https://...\", \"max_depth\": 2, \"limit\": 10}",
                },
                "config": {
                    "desc": "查看或设置配置（api_key 写入 config/tavily.yaml）",
                    "input_data": "留空查看（脱敏）；args=\"tvly-xxxx\" 或 JSON {\"api_key\": \"tvly-xxxx\"} 写入",
                },
            },
            "api_key_source": "config/tavily.yaml 的 api_key，或环境变量 TAVILY_API_KEY（组件不内置任何 key）",
        }
