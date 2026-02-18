import os
import ast

project_dir = r"C:\Users\pc\Desktop\Thesis_final"
all_imports = set()

for root, _, files in os.walk(project_dir):
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8") as file:
                    tree = ast.parse(file.read(), filename=f)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for n in node.names:
                            all_imports.add(n.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            all_imports.add(node.module.split('.')[0])
            except Exception as e:
                print(f"Skipped {path} due to {e}")

print("\nDetected imports:")
for lib in sorted(all_imports):
    print(lib)
