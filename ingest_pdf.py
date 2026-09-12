# -*- coding: utf-8 -*-
"""
PDF/扫描件入库入口：PDF → 纯文本(txt) → law_parser 结构化解析（验证用，不写向量库）

演示「从只吃 txt 扩展到 PDF/扫描件」的完整链路：
    PDF 文件 → parse_pdf_to_txt（文本层 + RapidOCR 扫描页 OCR）→ LawParser 六层结构解析

用法：
    python ingest_pdf.py data/laws/民法典_扫描版.pdf
    python ingest_pdf.py 某判决书.pdf --out-txt out/判决书.txt --no-ocr

参数：
    pdf            PDF 文件路径
    --out-txt      导出合并纯文本的路径（可选）
    --no-ocr       关闭扫描页 OCR 兜底（只提取文本层）
"""
import argparse
import io
import os
import sys

# 兼容 Windows 控制台中文输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 保证以项目根目录导入 src 包（支持从任意目录执行）
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.ingestion.pdf_parser import parse_pdf, parse_pdf_to_txt
from src.ingestion.law_parser import LawParser


def main():
    parser = argparse.ArgumentParser(description="PDF/扫描件 → txt → 法条结构化解析（验证链路，不写库）")
    parser.add_argument("pdf", help="PDF 文件路径")
    parser.add_argument("--out-txt", default=None, help="导出合并纯文本的路径（可选）")
    parser.add_argument("--no-ocr", action="store_true", help="关闭扫描页 OCR 兜底")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"[错误] 文件不存在: {args.pdf}")
        sys.exit(1)

    # 1) 逐页解析（只跑一次 OCR，结果复用到 txt 导出）
    print(f"[1/3] 解析 PDF: {args.pdf}（OCR 兜底: {'关闭' if args.no_ocr else '开启'}）...")
    pages = parse_pdf(args.pdf, ocr_fallback=not args.no_ocr)

    stats = {"text": 0, "ocr": 0, "empty": 0}
    for p in pages:
        stats[p["source"]] += 1
    print(f"      共 {len(pages)} 页 | 文本层 {stats['text']} 页 | OCR {stats['ocr']} 页 | 空页(封面等) {stats['empty']} 页")

    # 2) 导出合并纯文本（跳过封面/空页）
    txt = parse_pdf_to_txt(args.pdf, out_txt=args.out_txt, pages=pages)
    print(f"[2/3] 提取纯文本 {len(txt)} 字符" + (f" → 已写入 {args.out_txt}" if args.out_txt else ""))

    # 3) 交给 law_parser 做 编→章→节→条 结构化解析（验证下游可衔接）
    parser = LawParser()
    law_name = parser._extract_law_name(txt)
    articles = parser.parse_law_content(txt, law_name=law_name)
    print(f"[3/3] law_parser 解析出 {len(articles)} 条法律条文（法律名: {law_name}）")
    if articles:
        print(f"      首条: {articles[0].article_id} | {articles[0].content[:40]}")
        print(f"      末条: {articles[-1].article_id} | {articles[-1].content[:40]}")


if __name__ == "__main__":
    main()
