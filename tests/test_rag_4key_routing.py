import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.rag import RAGStore


class RAG4KeyRoutingTests(unittest.TestCase):
    def test_key_nao_question_selects_4key_rule_doc(self):
        rag = object.__new__(RAGStore)
        titles = [
            "Cau hoi ve gia cua ma.txt",
            "Cau hoi ve danh gia 4 key co phieu.txt",
            "Cau hoi ve suc manh dong tien, smdt nganh, ma.txt",
        ]

        doc = RAGStore._pick_explicit_rule_doc(rag, "GEX dang thuoc key nao?", titles)

        self.assertEqual(doc, "Cau hoi ve danh gia 4 key co phieu.txt")


if __name__ == "__main__":
    unittest.main()
