import json

# Read the data.js file
with open('data.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Try to parse just the JSON part
json_str = content[len('window.electorates = '):].rstrip(';\n')
print(f"JSON string length: {len(json_str)}")
print(f"Last 100 chars: {repr(json_str[-100:])}")
print(f"First 100 chars: {repr(json_str[:100])}")

# Try to parse it
try:
    data = json.loads(json_str)
    print(f"✓ Valid JSON with {len(data)} items")
except json.JSONDecodeError as e:
    print(f"Error: {e}")
    print(f"Error position: {e.pos}")
    print(f"Error line: {e.lineno}")
    print(f"Context: {repr(json_str[max(0, e.pos-50):min(len(json_str), e.pos+50)])}")
