"""Integrity checks for the pending-only Stage 8 remediation batch."""

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE8 = ROOT / "data" / "evaluation" / "stage8"
CANDIDATES = STAGE8 / "round2_candidates_171.jsonl"
MANIFEST = STAGE8 / "round2_remediation_manifest.json"
REVIEWED = STAGE8 / "review_queue_300_reviewed.jsonl"
FIELDS = [
    "queue_id", "origin", "question", "proposed_question_type",
    "proposed_difficulty", "proposed_knowledge_base_slugs",
    "proposed_relevant_article_ids", "proposed_should_abstain",
    "local_source_locator", "review_state", "reviewer", "reviewed_at",
    "review_note", "verified_record",
]
REJECTED_TEMPLATES = ("当事人同时遇到", "同时还需要判断", "若与相近规则混淆")
HARD_EXPECTATIONS = {'round2-adjacent-001': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-002': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-003': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-004': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-005': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-006': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-007': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-008': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-009': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-010': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第590条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第590条'}, 'round2-adjacent-011': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-012': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-013': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-014': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-015': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-016': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-017': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-018': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-019': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-020': {'articles': ['中华人民共和国民法典第585条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第585条；中华人民共和国民法典第584条'}, 'round2-adjacent-021': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-022': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-023': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-024': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-025': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-026': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-027': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-028': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-029': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-030': {'articles': ['中华人民共和国民法典第586条', '中华人民共和国民法典第587条'], 'locator': '中华人民共和国民法典第586条；中华人民共和国民法典第587条'}, 'round2-adjacent-031': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-032': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-033': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-034': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-035': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-036': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-037': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-038': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-039': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-adjacent-040': {'articles': ['中华人民共和国民法典第591条', '中华人民共和国民法典第584条'], 'locator': '中华人民共和国民法典第591条；中华人民共和国民法典第584条'}, 'round2-cross-001': {'articles': ['中华人民共和国劳动法第41条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第41条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-002': {'articles': ['中华人民共和国劳动法第17条', '中华人民共和国劳动合同法第35条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第17条；中华人民共和国劳动合同法第35条；中华人民共和国劳动合同法第87条'}, 'round2-cross-003': {'articles': ['中华人民共和国劳动法第72条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第72条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-004': {'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动法第41条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动法第41条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-005': {'articles': ['中华人民共和国劳动法第61条', '中华人民共和国劳动合同法第35条'], 'locator': '中华人民共和国劳动法第61条；中华人民共和国劳动合同法第35条'}, 'round2-cross-006': {'articles': ['中华人民共和国劳动法第25条', '中华人民共和国劳动合同法第19条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第25条；中华人民共和国劳动合同法第19条；中华人民共和国劳动合同法第39条'}, 'round2-cross-007': {'articles': ['中华人民共和国劳动法第27条', '中华人民共和国劳动合同法第41条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第27条；中华人民共和国劳动合同法第41条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-008': {'articles': ['中华人民共和国劳动法第38条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第38条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-009': {'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-010': {'articles': ['中华人民共和国劳动法第41条', '中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第38条'], 'locator': '中华人民共和国劳动法第41条；中华人民共和国劳动法第44条；中华人民共和国劳动合同法第38条'}, 'round2-cross-011': {'articles': ['中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第50条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-012': {'articles': ['中华人民共和国劳动法第16条', '中华人民共和国劳动合同法第14条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第82条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第16条；中华人民共和国劳动合同法第14条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第82条；中华人民共和国劳动合同法第87条'}, 'round2-cross-013': {'articles': ['中华人民共和国劳动法第62条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第62条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-014': {'articles': ['中华人民共和国劳动法第26条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第26条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-015': {'articles': ['中华人民共和国劳动法第61条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第61条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-016': {'articles': ['中华人民共和国劳动法第26条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第26条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-017': {'articles': ['中华人民共和国劳动法第41条', '中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第41条；中华人民共和国劳动法第44条；中华人民共和国劳动合同法第39条'}, 'round2-cross-018': {'articles': ['中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第50条'], 'locator': '中华人民共和国劳动法第50条；中华人民共和国劳动合同法第50条'}, 'round2-cross-019': {'articles': ['中华人民共和国劳动法第64条', '中华人民共和国劳动合同法第32条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第64条；中华人民共和国劳动合同法第32条；中华人民共和国劳动合同法第39条'}, 'round2-cross-020': {'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第87条'}, 'round2-cross-021': {'articles': ['中华人民共和国劳动法第48条', '中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条'], 'locator': '中华人民共和国劳动法第48条；中华人民共和国劳动法第50条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条'}, 'round2-cross-022': {'articles': ['中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第44条；中华人民共和国劳动合同法第39条'}, 'round2-cross-023': {'articles': ['中华人民共和国劳动法第48条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第48条；中华人民共和国劳动合同法第87条'}, 'round2-cross-024': {'articles': ['中华人民共和国劳动合同法第23条', '中华人民共和国劳动合同法第24条', '中华人民共和国民法典第509条'], 'locator': '中华人民共和国劳动合同法第23条；中华人民共和国劳动合同法第24条；中华人民共和国民法典第509条'}, 'round2-cross-025': {'articles': ['中华人民共和国劳动合同法第22条', '中华人民共和国民法典第509条'], 'locator': '中华人民共和国劳动合同法第22条；中华人民共和国民法典第509条'}, 'round2-cross-026': {'articles': ['中华人民共和国民法典第67条', '中华人民共和国劳动合同法第34条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国民法典第67条；中华人民共和国劳动合同法第34条；中华人民共和国劳动合同法第47条'}, 'round2-cross-027': {'articles': ['中华人民共和国劳动法第17条', '中华人民共和国劳动合同法第35条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第17条；中华人民共和国劳动合同法第35条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第87条'}, 'round2-cross-028': {'articles': ['中华人民共和国劳动法第63条', '中华人民共和国劳动法第41条', '中华人民共和国劳动合同法第4条'], 'locator': '中华人民共和国劳动法第63条；中华人民共和国劳动法第41条；中华人民共和国劳动合同法第4条'}, 'round2-cross-029': {'articles': ['中华人民共和国劳动法第26条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第26条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-030': {'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-031': {'articles': ['中华人民共和国劳动法第72条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第72条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-032': {'articles': ['中华人民共和国劳动法第27条', '中华人民共和国劳动合同法第41条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第27条；中华人民共和国劳动合同法第41条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-033': {'articles': ['中华人民共和国劳动法第54条', '中华人民共和国劳动合同法第32条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第54条；中华人民共和国劳动合同法第32条；中华人民共和国劳动合同法第39条'}, 'round2-cross-034': {'articles': ['中华人民共和国劳动法第20条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第20条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-035': {'articles': ['中华人民共和国劳动法第36条', '中华人民共和国劳动法第41条', '中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第36条；中华人民共和国劳动法第41条；中华人民共和国劳动法第44条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-036': {'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条；中华人民共和国劳动合同法第87条'}, 'round2-cross-037': {'articles': ['中华人民共和国劳动合同法第23条', '中华人民共和国劳动合同法第24条', '中华人民共和国劳动合同法第35条', '中华人民共和国民法典第509条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动合同法第23条；中华人民共和国劳动合同法第24条；中华人民共和国劳动合同法第35条；中华人民共和国民法典第509条；中华人民共和国劳动合同法第87条'}, 'round2-cross-038': {'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-039': {'articles': ['中华人民共和国劳动法第38条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第38条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-040': {'articles': ['中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第50条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-multihop-001': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-002': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-003': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-004': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-005': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-006': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-007': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-008': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-009': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-010': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-011': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-012': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-013': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-014': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-015': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-016': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-017': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-018': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-019': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条', '中华人民共和国民法典第563条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条；中华人民共和国民法典第563条'}, 'round2-multihop-020': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-021': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-022': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-023': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-024': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-025': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-026': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-027': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-028': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-029': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}, 'round2-multihop-030': {'articles': ['中华人民共和国民法典第577条', '中华人民共和国民法典第584条', '中华人民共和国民法典第591条'], 'locator': '中华人民共和国民法典第577条；中华人民共和国民法典第584条；中华人民共和国民法典第591条'}}


CROSS_EXPECTATIONS = {'round2-cross-001': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第41条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第41条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-002': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第17条', '中华人民共和国劳动合同法第35条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第17条；中华人民共和国劳动合同法第35条；中华人民共和国劳动合同法第87条'}, 'round2-cross-003': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第72条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第72条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-004': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动法第41条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动法第41条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-005': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第61条', '中华人民共和国劳动合同法第35条'], 'locator': '中华人民共和国劳动法第61条；中华人民共和国劳动合同法第35条'}, 'round2-cross-006': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第25条', '中华人民共和国劳动合同法第19条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第25条；中华人民共和国劳动合同法第19条；中华人民共和国劳动合同法第39条'}, 'round2-cross-007': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第27条', '中华人民共和国劳动合同法第41条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第27条；中华人民共和国劳动合同法第41条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-008': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第38条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第38条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-009': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-010': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第41条', '中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第38条'], 'locator': '中华人民共和国劳动法第41条；中华人民共和国劳动法第44条；中华人民共和国劳动合同法第38条'}, 'round2-cross-011': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第50条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-012': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第16条', '中华人民共和国劳动合同法第14条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第82条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第16条；中华人民共和国劳动合同法第14条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第82条；中华人民共和国劳动合同法第87条'}, 'round2-cross-013': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第62条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第62条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-014': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第26条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第26条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-015': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第61条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第61条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-016': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第26条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第26条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-017': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第41条', '中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第41条；中华人民共和国劳动法第44条；中华人民共和国劳动合同法第39条'}, 'round2-cross-018': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第50条'], 'locator': '中华人民共和国劳动法第50条；中华人民共和国劳动合同法第50条'}, 'round2-cross-019': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第64条', '中华人民共和国劳动合同法第32条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第64条；中华人民共和国劳动合同法第32条；中华人民共和国劳动合同法第39条'}, 'round2-cross-020': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第87条'}, 'round2-cross-021': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第48条', '中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条'], 'locator': '中华人民共和国劳动法第48条；中华人民共和国劳动法第50条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条'}, 'round2-cross-022': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第44条；中华人民共和国劳动合同法第39条'}, 'round2-cross-023': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第48条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第48条；中华人民共和国劳动合同法第87条'}, 'round2-cross-024': {'slugs': ['labor-contract-law', 'civil-code'], 'articles': ['中华人民共和国劳动合同法第23条', '中华人民共和国劳动合同法第24条', '中华人民共和国民法典第509条'], 'locator': '中华人民共和国劳动合同法第23条；中华人民共和国劳动合同法第24条；中华人民共和国民法典第509条'}, 'round2-cross-025': {'slugs': ['labor-contract-law', 'civil-code'], 'articles': ['中华人民共和国劳动合同法第22条', '中华人民共和国民法典第509条'], 'locator': '中华人民共和国劳动合同法第22条；中华人民共和国民法典第509条'}, 'round2-cross-026': {'slugs': ['civil-code', 'labor-contract-law'], 'articles': ['中华人民共和国民法典第67条', '中华人民共和国劳动合同法第34条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国民法典第67条；中华人民共和国劳动合同法第34条；中华人民共和国劳动合同法第47条'}, 'round2-cross-027': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第17条', '中华人民共和国劳动合同法第35条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第17条；中华人民共和国劳动合同法第35条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第87条'}, 'round2-cross-028': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第63条', '中华人民共和国劳动法第41条', '中华人民共和国劳动合同法第4条'], 'locator': '中华人民共和国劳动法第63条；中华人民共和国劳动法第41条；中华人民共和国劳动合同法第4条'}, 'round2-cross-029': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第26条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第42条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第26条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第42条；中华人民共和国劳动合同法第87条'}, 'round2-cross-030': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-031': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第72条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第72条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-032': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第27条', '中华人民共和国劳动合同法第41条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第27条；中华人民共和国劳动合同法第41条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-033': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第54条', '中华人民共和国劳动合同法第32条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第54条；中华人民共和国劳动合同法第32条；中华人民共和国劳动合同法第39条'}, 'round2-cross-034': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第20条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第20条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-035': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第36条', '中华人民共和国劳动法第41条', '中华人民共和国劳动法第44条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第36条；中华人民共和国劳动法第41条；中华人民共和国劳动法第44条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-036': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条；中华人民共和国劳动合同法第87条'}, 'round2-cross-037': {'slugs': ['labor-contract-law', 'civil-code'], 'articles': ['中华人民共和国劳动合同法第23条', '中华人民共和国劳动合同法第24条', '中华人民共和国劳动合同法第35条', '中华人民共和国民法典第509条', '中华人民共和国劳动合同法第87条'], 'locator': '中华人民共和国劳动合同法第23条；中华人民共和国劳动合同法第24条；中华人民共和国劳动合同法第35条；中华人民共和国民法典第509条；中华人民共和国劳动合同法第87条'}, 'round2-cross-038': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第4条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第40条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第4条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第40条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}, 'round2-cross-039': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第38条', '中华人民共和国劳动合同法第4条', '中华人民共和国劳动合同法第39条'], 'locator': '中华人民共和国劳动法第38条；中华人民共和国劳动合同法第4条；中华人民共和国劳动合同法第39条'}, 'round2-cross-040': {'slugs': ['labor-law', 'labor-contract-law'], 'articles': ['中华人民共和国劳动法第50条', '中华人民共和国劳动合同法第38条', '中华人民共和国劳动合同法第46条', '中华人民共和国劳动合同法第47条'], 'locator': '中华人民共和国劳动法第50条；中华人民共和国劳动合同法第38条；中华人民共和国劳动合同法第46条；中华人民共和国劳动合同法第47条'}}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def number_to_chinese(number):
    digits = "零一二三四五六七八九"
    units = ((1000, "千"), (100, "百"), (10, "十"), (1, ""))
    result, remaining, pending_zero = "", number, False
    for value, unit in units:
        digit, remaining = divmod(remaining, value)
        if digit:
            if pending_zero:
                result += "零"
            if not (value == 10 and digit == 1 and not result):
                result += digits[digit]
            result += unit
            pending_zero = False
        elif result and remaining:
            pending_zero = True
    return result or "零"


def article_exists(article_id):
    law, article = article_id.split("第", 1)
    number = article.removesuffix("条")
    files = {
        "中华人民共和国民法典": ["中华人民共和国民法典.txt"],
        "中华人民共和国刑法": ["criminal-law.txt"],
        "中华人民共和国劳动法": ["labor-law.txt"],
        "中华人民共和国劳动合同法": ["labor-contract-law.txt"],
    }.get(law)
    if files is None:
        return False
    markers = (number, number_to_chinese(int(number)))
    return any(
        any(f"第{marker}条" in (ROOT / "data" / "laws" / filename).read_text(encoding="utf-8") for marker in markers)
        for filename in files
    )


def test_round2_candidates_are_a_pending_data_only_remediation_batch():
    rows = read_jsonl(CANDIDATES)
    assert len(rows) == 171
    assert len({row["queue_id"] for row in rows}) == 171
    assert all(list(row) == FIELDS for row in rows)
    assert all(row["origin"] == "round2_remediation" for row in rows)
    assert all(
        row["review_state"] == "pending"
        and row["reviewer"] == ""
        and row["reviewed_at"] is None
        and row["review_note"] == ""
        and row["verified_record"] is None
        for row in rows
    )
    counts = Counter(row["proposed_question_type"] for row in rows)
    assert counts == {
        "oral_without_law_name": 50,
        "insufficient_facts_abstention": 10,
        "baseline_direct_lookup": 1,
        "adjacent_or_confusable": 40,
        "cross_law": 40,
        "multi_hop": 30,
    }
    assert "version_or_time" not in counts
    assert all(not any(phrase in row["question"] for phrase in REJECTED_TEMPLATES) for row in rows)


def test_hard_replacements_have_unique_substantive_questions_and_declared_mappings():
    rows = read_jsonl(CANDIDATES)
    hard_rows = [
        row for row in rows
        if row["proposed_question_type"] in {"adjacent_or_confusable", "cross_law", "multi_hop"}
    ]
    normalized = [re.sub(r"（(?:情境|案件|链路)\d+）$", "", row["question"]) for row in hard_rows]
    assert len(normalized) == len(set(normalized))
    assert set(HARD_EXPECTATIONS) == {row["queue_id"] for row in hard_rows}
    for row in hard_rows:
        assert HARD_EXPECTATIONS[row["queue_id"]] == {
            "articles": row["proposed_relevant_article_ids"],
            "locator": row["local_source_locator"],
        }


def test_cross_law_rows_span_two_statutes_with_exact_declared_mappings():
    rows = read_jsonl(CANDIDATES)
    cross_rows = [row for row in rows if row["proposed_question_type"] == "cross_law"]
    assert len(cross_rows) == 40
    assert set(CROSS_EXPECTATIONS) == {row["queue_id"] for row in cross_rows}
    for row in cross_rows:
        expected = CROSS_EXPECTATIONS[row["queue_id"]]
        assert row["proposed_knowledge_base_slugs"] == expected["slugs"]
        assert row["proposed_relevant_article_ids"] == expected["articles"]
        assert row["local_source_locator"] == expected["locator"]
        assert len(row["proposed_knowledge_base_slugs"]) >= 2
        laws = {article.split("第", 1)[0] for article in row["proposed_relevant_article_ids"]}
        assert len(laws) >= 2
        assert {slug_to_law(slug) for slug in row["proposed_knowledge_base_slugs"]} <= laws


def slug_to_law(slug):
    return {
        "labor-law": "中华人民共和国劳动法",
        "labor-contract-law": "中华人民共和国劳动合同法",
        "civil-code": "中华人民共和国民法典",
        "criminal-law": "中华人民共和国刑法",
    }[slug]


def test_cross_content_regressions_pin_statutory_triggers_and_distinct_trial_issues():
    rows = {row["queue_id"]: row for row in read_jsonl(CANDIDATES)}
    assert "怀孕已满七个月" in rows["round2-cross-005"]["question"]
    assert "中华人民共和国劳动法第61条" in rows["round2-cross-005"]["proposed_relevant_article_ids"]
    assert "中华人民共和国劳动合同法第35条" in rows["round2-cross-005"]["proposed_relevant_article_ids"]
    assert "中华人民共和国劳动法第61条" not in rows["round2-cross-013"]["proposed_relevant_article_ids"]
    assert "中华人民共和国劳动法第64条" in rows["round2-cross-019"]["proposed_relevant_article_ids"]
    assert "未成年工" in rows["round2-cross-019"]["question"]
    assert "夜班" not in rows["round2-cross-019"]["question"]
    assert "中华人民共和国劳动合同法第32条" in rows["round2-cross-033"]["proposed_relevant_article_ids"]
    assert "中华人民共和国劳动合同法第35条" in rows["round2-cross-037"]["proposed_relevant_article_ids"]
    trial_006 = re.sub(r"[，；。]", "", rows["round2-cross-006"]["question"])
    trial_025 = re.sub(r"[，；。]", "", rows["round2-cross-025"]["question"])
    assert trial_006 != trial_025
    assert "第19条" not in rows["round2-cross-025"]["question"]


def test_cross_regressions_pin_medical_social_insurance_and_overtime_triggers():
    rows = {row["queue_id"]: row for row in read_jsonl(CANDIDATES)}
    assert "非因工患病" in rows["round2-cross-029"]["question"]
    assert "医疗期" in rows["round2-cross-029"]["question"]
    assert "中华人民共和国劳动合同法第42条" in rows["round2-cross-029"]["proposed_relevant_article_ids"]
    assert "员工书面通知解除" in rows["round2-cross-031"]["question"]
    assert "中华人民共和国劳动合同法第38条" in rows["round2-cross-031"]["proposed_relevant_article_ids"]
    assert "每天工作十小时" in rows["round2-cross-035"]["question"]
    assert "每周六天" in rows["round2-cross-035"]["question"]
    assert "中华人民共和国劳动法第41条" in rows["round2-cross-035"]["proposed_relevant_article_ids"]
    assert "中华人民共和国劳动法第44条" in rows["round2-cross-035"]["proposed_relevant_article_ids"]


def test_oral_and_abstention_remediations_keep_required_boundaries():
    rows = read_jsonl(CANDIDATES)
    reviewed = {row["queue_id"]: row for row in read_jsonl(REVIEWED)}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lineage = {entry["source_queue_id"]: entry for entry in manifest["lineage"]}
    oral = [row for row in rows if row["proposed_question_type"] == "oral_without_law_name"]
    banned = re.compile(r"法典|刑法|劳动法|第\s*[一二三四五六七八九十百千万\d]+\s*条")
    for row in oral:
        source = reviewed[lineage_for_candidate(manifest, row["queue_id"])]
        assert row["question"] != source["question"]
        assert not banned.search(row["question"])
    expected_abstention_slugs = {
        "hard-abstain-002": ["labor-contract-law"],
        "hard-abstain-006": ["labor-law"],
        "hard-abstain-007": ["trademark-law"],
        "hard-abstain-008": ["patent-law"],
        "hard-abstain-009": ["copyright-law"],
        "hard-abstain-011": ["labor-contract-law"],
        "hard-abstain-012": ["labor-contract-law"],
        "hard-abstain-013": ["company-law"],
        "hard-abstain-016": ["criminal-law"],
        "hard-abstain-018": ["copyright-law"],
    }
    for source_id, entry in lineage.items():
        if entry.get("replacement_candidate_id", "").startswith("round2-abstain-"):
            candidate = next(row for row in rows if row["queue_id"] == entry["replacement_candidate_id"])
            assert candidate["proposed_should_abstain"] is True
            assert candidate["proposed_relevant_article_ids"] == []
            assert candidate["proposed_knowledge_base_slugs"] == expected_abstention_slugs[source_id]
    civil = next(row for row in rows if row["queue_id"] == "round2-civil-correction-001")
    assert civil["proposed_relevant_article_ids"] == ["中华人民共和国民法典第628条"]
    assert lineage["civil-027"]["replacement_candidate_id"] == civil["queue_id"]


def lineage_for_candidate(manifest, candidate_id):
    return next(
        entry["source_queue_id"]
        for entry in manifest["lineage"]
        if entry.get("replacement_candidate_id") == candidate_id
    )


def test_round2_lineage_covers_every_nonapproved_item_and_local_sources_exist():
    rows = read_jsonl(CANDIDATES)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    reviewed = read_jsonl(REVIEWED)
    nonapproved = {row["queue_id"] for row in reviewed if row["review_state"] != "approved"}
    entries = manifest["lineage"]
    assert {entry["source_queue_id"] for entry in entries} == nonapproved
    assert len(entries) == 191
    replacements = [entry for entry in entries if "replacement_candidate_id" in entry]
    blocked = [entry for entry in entries if entry.get("status") == "blocked"]
    assert len(replacements) == 171
    assert len(blocked) == 20
    assert all("version" in entry["reason"].lower() and "corpus" in entry["reason"].lower() for entry in blocked)
    assert {entry["source_queue_id"] for entry in blocked} == {
        f"hard-version-{number:03d}" for number in range(1, 21)
    }
    assert {entry["replacement_candidate_id"] for entry in replacements} == {row["queue_id"] for row in rows}
    for row in rows:
        if not row["proposed_should_abstain"]:
            assert row["proposed_relevant_article_ids"]
            assert all(article_exists(article) for article in row["proposed_relevant_article_ids"])
            assert all(article in row["local_source_locator"] for article in row["proposed_relevant_article_ids"])
