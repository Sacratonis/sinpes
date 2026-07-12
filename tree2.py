import os
import sys

def generate_tree(dir_path, prefix=""):
    try:
        entries = sorted(os.listdir(dir_path))
    except PermissionError:
        print(prefix + "[Permission Denied]")
        return
    except FileNotFoundError:
        print(prefix + "[Not Found: " + dir_path + "]")
        return

    excludes = {'.git', 'node_modules', '__pycache__', 'dist', '.astro', 'systemd', 'venv', '.next', '.pytest_cache'}
    entries = [e for e in entries if e not in excludes and not e.endswith('.pyc') and not e.startswith('.')]
    
    for i, entry in enumerate(entries):
        path = os.path.join(dir_path, entry)
        is_last = (i == len(entries) - 1)
        pointer = "└── " if is_last else "├── "
        
        print(prefix + pointer + entry)
        
        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            generate_tree(path, prefix + extension)

for path in sys.argv[1:]:
    print(path)
    generate_tree(path)
