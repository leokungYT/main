import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
js = open('_automation.js', encoding='utf-8').read()
# Preview / jobs / servers context
for pat in ['/preview', '/jobs', '/servers', '/delete', '/member-presets']:
    for m in re.finditer(r'`' + re.escape(pat) + r'`[\s\S]{0,400}', js):
        print(f'=== {pat} ===')
        print(m.group(0)[:500])
        print()
        break
# accept="..."
for m in re.finditer(r'accept[^"\`]{0,5}["\`][^"\`]{1,60}["\`]', js):
    print('accept:', m.group(0))
