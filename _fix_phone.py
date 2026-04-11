path = 'server/input_guard.py'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '0[1-9][0-9]?' in line and 'phone' not in line.lower() and '[-.\\' in line:
        lines[i] = '            r"\\b(02|01[016789]|0[3-9][0-9])[-\\s]?[0-9]{3,4}[-\\s]?[0-9]{4}\\b"\n'
        print(f"Fixed line {i+1}: {lines[i].strip()}")
        break

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Done")
