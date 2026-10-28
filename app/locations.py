import re


def normalize_location(value: str) -> str:
    text = ' '.join((value or '').strip().replace('_', ' ').split())
    if not text:
        return ''
    if re.fullmatch(r'\d+[A-Za-zА-Яа-я]*', text):
        return f'Номер {text}'
    if re.fullmatch(r'(?:номер|room)\s*[-#№]?\s*\d+[A-Za-zА-Яа-я]*', text, re.I):
        number = re.sub(r'^(?:номер|room)\s*[-#№]?\s*', '', text, flags=re.I)
        return f'Номер {number}'
    if text.casefold() == 'сауна':
        return 'Сауна'
    return text[:1].upper() + text[1:]
