import json
import os
import subprocess

SUPPORTED = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.webm'}

with open('data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for project in data.get('projects', []):
    folder = project.get('folder')
    if not folder or not os.path.isdir(folder):
        continue

    # Get files in the order they were first committed (upload order)
    result = subprocess.run(
        ['git', 'log', '--diff-filter=A', '--name-only', '--format=', '--reverse', '--', f'{folder}/*'],
        capture_output=True, text=True
    )
    ordered = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]

    # Keep only supported formats that still exist
    images = [f for f in ordered if os.path.isfile(f) and os.path.splitext(f)[1].lower() in SUPPORTED]

    # Append any newly added files not yet in git log
    for fname in sorted(os.listdir(folder)):
        path = os.path.join(folder, fname).replace('\\', '/')
        if os.path.splitext(fname)[1].lower() in SUPPORTED and path not in images:
            images.append(path)

    project['images'] = images
    print(f"{project['name']}: {len(images)} file(s)")

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("data.json updated.")
