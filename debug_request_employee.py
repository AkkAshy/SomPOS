import os
import re
from pathlib import Path

project_root = Path(__file__).parent
print(f"🔍 ИЩУ request.Employee В ПРОЕКТЕ: {project_root}\n")

# Шаблоны поиска
patterns = [
    r'request\.Employee',  # Точное совпадение
    r"request\['Employee'\]",  # Через квадратные скобки
    r"getattr\(request, ['\"]Employee['\"]",  # Через getattr
    r"request\.employee",  # Маленькая буква (для сравнения)
    r"user\.Employee",  # В user (ошибка)
    r"self\.request\.Employee",  # В классах
]

results = {pattern: [] for pattern in patterns}

# Поиск по всем .py файлам
for py_file in project_root.rglob("*.py"):
    try:
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        results[pattern].append({
                            'file': str(py_file.relative_to(project_root)),
                            'line': i,
                            'code': line.strip()
                        })
    except Exception as e:
        print(f"❌ Не могу прочитать {py_file}: {e}")

# Вывод результатов
for pattern, matches in results.items():
    print(f"\n📄 '{pattern}' НАЙДЕНО ({len(matches)}):")
    if matches:
        for match in matches:
            print(f"  📍 {match['file']}:{match['line']}")
            print(f"     {match['code']}")
            print()
    else:
        print("  ✅ Не найдено!")

# Дополнительный поиск в inventory
print(f"\n🔍 В INVENTORY ПРИЛОЖЕНИИ:")
inventory_files = list(project_root.glob("inventory/*.py"))
for py_file in inventory_files:
    try:
        with open(py_file, 'r') as f:
            content = f.read()
            if 'Employee' in content and 'request' in content:
                print(f"  ⚠️  {py_file.name} — содержит Employee и request")
    except:
        pass

print("\n🔍 ДИАГНОСТИКА ЗАВЕРШЕНА")
