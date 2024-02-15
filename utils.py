import os
import re
if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sublime.txt')):
    import Urtext.urtext.syntax as syntax
else:
    import urtext.syntax as syntax

def strip_backtick_escape(contents):
    for e in syntax.preformat_c.findall(contents):
        contents = contents.replace(e,' '*len(e))
    return contents

def force_list(thing):
	if not isinstance(thing, list):
		thing = [thing]
	return thing

def get_id_from_link(target):
    match = syntax.any_link_or_pointer_c.search(target)
    if match:
        return match.group(6).strip()
    return target

def write_file_contents(filename, contents):
    if os.path.exists(filename):
        os.remove(filename)    
    with open(filename, 'w', encoding='utf-8' ) as f:
        f.write(contents)    