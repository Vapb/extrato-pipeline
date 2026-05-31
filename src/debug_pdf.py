import sys
import pdfplumber

path = sys.argv[1]
with pdfplumber.open(path) as pdf:
    for i, page in enumerate(pdf.pages[1:], 2):
        words = page.extract_words()
        print(f"\n=== PAGINA {i} | {len(words)} palavras ===")
        for w in words:
            print(f"  x0={w['x0']:6.1f}  top={w['top']:6.1f}  text={w['text']}")
