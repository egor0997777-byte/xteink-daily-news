#!/usr/bin/env python3
"""Проверка пересказов: каждое число и каждое имя из пересказа должны встречаться в
исходном тексте. Пересказ в part-файле сопоставляется с harvest.json по url.

Запуск:  python3 editor/check_numbers.py chatgpt/parts/<дата>-01.json
Выводит подозрительные места. Это подсказка для ручной проверки, а не вердикт:
числа с единицами (мили/км, фунты/кг) и русская запись дат дают ложные срабатывания.
"""
import json
import re
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent / "work"


def nums(s):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,\.]*\d|\d", s) if len(n) > 1 or n.isdigit()}


def main(path):
    src = {r["url"]: r for r in json.load(open(WORK / "harvest.json", encoding="utf-8"))}
    arts = json.load(open(path, encoding="utf-8"))["articles"]
    bad = 0
    for a in arts:
        r = src.get(a["url"])
        if not r:
            print("НЕТ ИСТОЧНИКА В harvest.json:", a["url"])
            bad += 1
            continue
        text = r["text"].replace(",", "")
        miss = sorted(n for n in nums(a["summary"]) if n.strip(".") not in text)
        if miss:
            print(f"- {a['title'][:60]}: чисел нет в тексте: {miss}")
            bad += 1
    print(f"проверено {len(arts)}, к ручной проверке {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
