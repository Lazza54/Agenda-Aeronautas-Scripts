import sys, pdfplumber
with pdfplumber.open(sys.argv[1]) as pdf:
    page = pdf.pages[0]
    rects = sorted([r for r in page.rects if r['x0'] < 10], key=lambda x: x['top'])
    crop = page.crop((0, rects[21]['top'], page.width, rects[21]['bottom']))
    for w in crop.extract_words(keep_blank_chars=False):
        t = w['text'].encode('ascii', 'ignore').decode('ascii').strip()
        if t in ('DO', 'ASB', 'HSB', 'DR', 'CMA'):
            print(f"{t}: top={w['top']}, bottom={w['bottom']}, x0={w['x0']}")
