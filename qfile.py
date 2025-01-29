import json

def question_file(way):
    with open(f'{way}', encoding='utf-8') as quest:
        temp = json.load(quest)
        return temp

