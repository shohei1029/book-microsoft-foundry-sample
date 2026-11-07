import re


def grade(sample: dict, item: dict) -> float:
    if "response" in item:
        response = item["response"]
    elif isinstance(item.get("sample"), dict) and "output_text" in item["sample"]:
        response = item["sample"]["output_text"]
    elif "sample.output_text" in item:
        response = item["sample.output_text"]
    elif "output_text" in sample:
        response = sample["output_text"]
    else:
        raise ValueError("The evaluation input has no generated response text.")
    if not isinstance(response, str):
        raise TypeError("The generated response must be a string.")

    text = response.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?ms)^[ \t]*```.*?^[ \t]*```[ \t]*$", "", text)
    pattern = (
        r"(?m)^[ \t]*(?:#{1,6}[ \t]+|■[ \t]*)?(?:\*\*)?"
        r"(結論|手順|参照資料|確認事項)(?:\*\*)?[ \t]*[:：]?[ \t]*$"
    )
    headings = list(re.finditer(pattern, text))
    if [heading.group(1) for heading in headings] != [
        "結論", "手順", "参照資料", "確認事項"
    ]:
        return 0.0
    sections = [
        text[heading.end():headings[index + 1].start()
             if index + 1 < len(headings) else len(text)].strip()
        for index, heading in enumerate(headings)
    ]
    if not all(sections):
        return 0.0
    steps = re.findall(r"(?m)^[ \t]{0,3}([1-9][0-9]*)[.)][ \t]+\S", sections[1])
    if not 1 <= len(steps) <= 3:
        return 0.0
    return float(steps == [str(number) for number in range(1, len(steps) + 1)])
