import re

preformat_syntax = re.compile('\`.*?\`', flags=re.DOTALL)

def strip_backtick_escape(contents):
    for e in preformat_syntax.findall(contents):
        contents = contents.replace(e,' '*len(e))
    return contents

