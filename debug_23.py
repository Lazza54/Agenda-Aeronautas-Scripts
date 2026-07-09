import sys, pdfplumber, re
with pdfplumber.open(sys.argv[1]) as pdf:
    page = pdf.pages[0]
    rects = sorted([r for r in page.rects if r['x0'] < 10], key=lambda x: x['top'])
    for i in range(21, 25):
        crop = page.crop((0, rects[i]['top'], page.width, rects[i]['bottom']))
        words = crop.extract_words(keep_blank_chars=False)
        for w in words:
            m = re.search(r'^(LA\s*\d{4}|OFT_J|LOFT_J|DO|ASB|HSB|OFF|DOF|DR|CMA)$', w['text'].encode('ascii', 'ignore').decode('ascii').strip())
            if m:
                box = [o for o in words if w['top']-5 < o['top'] < w['bottom']+15 and w['x1'] < o['x0'] < w['x1']+100]
                box = sorted(box, key=lambda x: x['top'])
                groups = []
                for b in box:
                    if not groups: groups.append([b])
                    elif b['top'] - groups[-1][0]['top'] < 8: groups[-1].append(b)
                    else: groups.append([b])
                print(f'Day {i+1}: {[ [x["text"] for x in g] for g in groups ]}')
