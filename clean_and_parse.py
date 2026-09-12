# -*- coding: utf-8 -*-
"""清洗v2：保留PDF行结构（解析器自带续行拼接），只去目录/附录/页码"""
import io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = r"E:/python/LLM/Legal_RAG_Agent/data/laws/民法典全文.txt"
DST = r"E:/python/LLM/Legal_RAG_Agent/data/laws/民法典_清洗.txt"

with io.open(SRC, "r", encoding="utf-8") as fp:
    lines = fp.read().splitlines()

# 正文范围：行161（第一编总则）~ 行5563（第一千二百六十条内容结束）
body = lines[161:5564]
cleaned = []
for l in body:
    s = l.strip()
    if re.fullmatch(r"\d+", s):          # 去页码行
        continue
    cleaned.append(l)

text = "中华人民共和国民法典\n" + "\n".join(cleaned)
with io.open(DST, "w", encoding="utf-8") as fp:
    fp.write(text)
print("清洗v2 完成，行数:", len(cleaned), "字符:", len(text))

sys.path.insert(0, r"E:/python/LLM/Legal_RAG_Agent")
from src.ingestion.law_parser import LawParser
parser = LawParser()
arts = parser.parse_law_file(DST)
print("解析出法条数:", len(arts))
if arts:
    print("首条:", arts[0].article_id, "|", arts[0].content[:50])
    print("末条:", arts[-1].article_id, "|", arts[-1].content[:50])
    nums = [int(a.article_number) for a in arts if a.article_number.isdigit()]
    have = set(nums)
    missing = sorted(set(range(1, 1261)) - have)
    extra = sorted(have - set(range(1, 1261)))
    print("条号范围:", min(nums), "~", max(nums), "| 总数:", len(nums))
    print("缺失条号:", missing, "| 超范围:", extra)
