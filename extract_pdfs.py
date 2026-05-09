from pathlib import Path
from PyPDF2 import PdfReader

paths = [
    Path('7745-Article Text-11274-1-2-20201228.pdf'),
    Path('reproducibility_assignment.pdf'),
    Path('rubric.pdf')
]
for path in paths:
    print('FILE:', path.name, 'EXISTS:', path.exists())
    if not path.exists():
        continue
    reader = PdfReader(str(path))
    print('NUM PAGES:', len(reader.pages))
    for i, page in enumerate(reader.pages[:3], start=1):
        text = page.extract_text() or ''
        print('--- PAGE', i, '---')
        print(text[:2000])
        print('--- END PAGE ---')
        print()
