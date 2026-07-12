import glob
files = glob.glob('apps/api/app/**/*.py', recursive=True)
for f in files:
    with open(f, 'r') as file:
        content = file.read()
    if '[cite: 1]' in content:
        content = content.replace('[cite: 1]', '')
        with open(f, 'w') as file:
            file.write(content)
