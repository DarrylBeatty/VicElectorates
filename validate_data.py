import json
content = open('data.js').read()
data = json.loads(content.replace('window.electorates = ', '').rstrip(';'))
print(f'✓ Valid JSON with {len(data)} electorates')
print(f'Sample 1: {data[0]["name"]} ({data[0]["slug"]})')
print(f'Sample 2: {data[5]["name"]} ({data[5]["slug"]})')
