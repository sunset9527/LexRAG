# -*- coding: utf-8 -*-
"""
PDF 解析器测试：用真实生成的 PDF 验证「文本层 + RapidOCR 扫描页 OCR」双通道

可直接运行:  python tests/test_pdf_parser.py
或 pytest:   python -m pytest tests/test_pdf_parser.py -v

测试 PDF 生成在 tests/fixtures/（首次运行时自动生成）：
- sample_text_law.pdf     文本型：fitz 内置中文字体写入文本层
- sample_scanned_law.pdf  扫描型：PIL 渲染中文图片插入整页（无文本层）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import fitz
import pytest

from src.ingestion.pdf_parser import parse_pdf, parse_pdf_to_txt

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TEXT_PDF = os.path.join(FIXTURES_DIR, "sample_text_law.pdf")
SCANNED_PDF = os.path.join(FIXTURES_DIR, "sample_scanned_law.pdf")

# 法律样本文本（文本型 PDF 用，结构对齐 law_parser 可解析的格式）
LAW_SAMPLE = (
    "中华人民共和国民法典\n"
    "第一条 为了保护民事主体的合法权益，调整民事关系，维护社会和经济秩序，"
    "适应中国特色社会主义发展要求，根据宪法，制定本法。\n"
    "第二条 民法调整平等主体的自然人、法人和非法人组织之间的人身关系和财产关系。"
)


def _find_cjk_font():
    """查找 Windows 中文字体，保证 PIL 渲染的图片能被 RapidOCR 识别"""
    for cand in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
                 r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\Deng.ttf"]:
        if os.path.exists(cand):
            return cand
    return None


def _ensure_fixtures():
    """生成测试 PDF（仅首次）：文本型 + 扫描型，存到 tests/fixtures/"""
    os.makedirs(FIXTURES_DIR, exist_ok=True)

    # 1) 文本型 PDF：fitz 内置中文字体 china-s 写入文本层（无任何图片）
    if not os.path.exists(TEXT_PDF):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), LAW_SAMPLE, fontname="china-s", fontsize=14)
        doc.save(TEXT_PDF)
        doc.close()
        print(f"[fixture] 已生成文本型 PDF: {TEXT_PDF}")

    # 2) 扫描型 PDF：PIL 把中文渲染成图片 → 插入为整页图片（无文本层）
    if not os.path.exists(SCANNED_PDF):
        from PIL import Image, ImageDraw, ImageFont
        font_path = _find_cjk_font()
        assert font_path, "未找到 Windows 中文字体，无法生成扫描测试件"
        img = Image.new("RGB", (1100, 320), "white")
        d = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, 44)
        d.text((60, 130), "中华人民共和国非物质文化遗产法（扫描件样张）", font=font, fill="black")
        tmp_png = os.path.join(FIXTURES_DIR, "_scanned_tmp.png")
        img.save(tmp_png)
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, filename=tmp_png)  # 整页图片 → 文本层为空
        doc.save(SCANNED_PDF)
        doc.close()
        os.remove(tmp_png)
        print(f"[fixture] 已生成扫描型 PDF: {SCANNED_PDF}")


def test_text_pdf_uses_text_layer():
    """文本型 PDF：全部走文本层，不触发 OCR"""
    _ensure_fixtures()
    pages = parse_pdf(TEXT_PDF)
    assert len(pages) == 1
    p = pages[0]
    assert p["source"] == "text"
    assert p["char_count"] > 0
    assert "民法典" in p["text"] and "第一条" in p["text"]


def test_scanned_pdf_uses_ocr():
    """扫描型 PDF：无文本层 → 触发 RapidOCR，识别出中文"""
    _ensure_fixtures()
    pages = parse_pdf(SCANNED_PDF)
    assert len(pages) == 1
    p = pages[0]
    assert p["source"] == "ocr"
    assert p["char_count"] > 0
    assert "非物质文化遗产" in p["text"]


def test_parse_pdf_to_txt_merges_and_skips_empty():
    """导出合并文本：文本型 PDF 直接得到纯文本；关闭 OCR 时扫描页为空 → 被跳过"""
    _ensure_fixtures()
    txt = parse_pdf_to_txt(TEXT_PDF)
    assert "第一条" in txt

    # 关闭 OCR 时，扫描页是空文本层 → 合并结果为空
    txt_no_ocr = parse_pdf_to_txt(SCANNED_PDF, ocr_fallback=False)
    assert txt_no_ocr.strip() == ""


if __name__ == "__main__":
    # 支持直接运行: python tests/test_pdf_parser.py
    test_text_pdf_uses_text_layer()
    print("[PASS] 文本型 PDF 全部走文本层，source=text")
    test_scanned_pdf_uses_ocr()
    print("[PASS] 扫描型 PDF 走 RapidOCR，source=ocr 且识别出中文")
    test_parse_pdf_to_txt_merges_and_skips_empty()
    print("[PASS] parse_pdf_to_txt 合并/跳过逻辑正确")
    print("全部测试通过 ✔")
