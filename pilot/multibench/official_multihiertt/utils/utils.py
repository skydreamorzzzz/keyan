"""Subset of official MultiHiertt `utils/utils.py` used by evaluation.

Source: https://github.com/psunlpgroup/MultiHiertt/blob/main/utils/utils.py
Only the functions needed by `evaluate.py` are vendored here.
"""


def str_to_num(text):
    text = text.replace("$", "")
    text = text.replace(",", "")
    text = text.replace("-", "")
    text = text.replace("%", "")
    try:
        num = float(text)
    except ValueError:
        if "const_" in text:
            text = text.replace("const_", "")
            if text == "m1":
                text = "-1"
            num = float(text)
        else:
            num = "n/a"
    return num
