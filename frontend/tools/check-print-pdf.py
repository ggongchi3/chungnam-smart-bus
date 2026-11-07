"""브라우저 검사에서 만든 80mm PDF의 실제 페이지 크기와 텍스트를 확인한다."""
import json
from pathlib import Path

from pypdf import PdfReader

reports = []
for name in ("direct", "transfer"):
    path = Path("qa.local") / f"paper-{name}-80mm.pdf"
    reader = PdfReader(path)
    assert len(reader.pages) == 1, f"{name}: 내용이 여러 장으로 잘렸습니다."
    page = reader.pages[0]
    width = float(page.mediabox.width) * 25.4 / 72
    height = float(page.mediabox.height) * 25.4 / 72
    assert abs(width - 80) < 0.2, (name, width)
    assert height >= 180, (name, height)
    text = " ".join((page.extract_text() or "").split())
    assert "시연 데이터" in text and "안내표 생성 시각" in text, (name, text)
    reports.append({"name": name, "pages": 1, "widthMm": round(width, 2), "heightMm": round(height, 2)})

Path("qa.local/pdf-results.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(reports, ensure_ascii=False))
