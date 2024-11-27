import os
import re
import urtext.syntax as syntax
from urtext.url import url_match_c
from urtext.link import UrtextLink
from urtext.target import UrtextTarget

def strip_backtick_escape(contents):
    ranges = []
    for e in syntax.preformat_c.finditer(contents):
        contents = contents.replace(e.group(),' '*len(e.group()))
        ranges.append([e.start(), e.end()])
    return ranges, contents

def force_list(thing):
	if not isinstance(thing, list):
		thing = [thing]
	return thing

def match_compact_node(selection):
    return True if syntax.compact_node_c.match(selection) else False

def strip_illegal_file_characters(filename):
    for c in [
        '<', '>', '\:', '"', '/', '\\', '|', '?','*', '.', ';', '%']:
        filename = filename.replace(c,' ')
    return filename

def get_id_from_link(target):
    match = syntax.node_link_or_pointer_c.search(target)
    if match:
        return match.group(5)
    return target

def make_project_link(project_name):
    return ''.join([
        syntax.other_project_link_prefix,
        '"%s"' % project_name
        ])

def write_file_contents(filename, contents):
    with open(filename, 'w', encoding='utf-8' ) as f:
        f.write(contents)

def get_path_from_link(link):
    match = syntax.file_link_c.match(link)
    if match:
        return match.group(2)
    return link

def make_file_link(path):
    return ''.join([
        syntax.file_link_opening_wrapper,
        path,
        syntax.link_closing_wrapper])

def make_node_link(node_id, position=0):
    position_str = ''
    if position != 0:
        position_str = str(position)
    if position_str:
        position_str = ":" + position_str
    return ''.join([
        syntax.link_opening_wrapper,
        node_id,
        syntax.link_closing_wrapper,
        position_str])

def make_node_pointer(node_id):
    return ''.join([
        syntax.link_opening_wrapper,
        node_id,
        syntax.pointer_closing_wrapper])

def get_all_targets_from_string(string):
    targets = []
    links, replaced_contents = get_all_links_from_string(string)
    for link in links:
        target = UrtextTarget(link.matching_string)
        target.is_link = True
        target.link = link
        target.is_node = link.is_node
        target.filename = link.filename
        target.path = link.path
        target.node_id = link.node_id
        target.is_file = link.is_file
        target.is_missing = link.is_missing
        targets.append(target)
    for match in syntax.virtual_target_match_c.finditer(replaced_contents):
        target = UrtextTarget(match.group())
        target.is_virtual = True
        targets.append(target)
        replaced_contents = replaced_contents.replace(match.group(),'', 1)
    if replaced_contents.strip():
        target = UrtextTarget(replaced_contents.strip())
        target.is_raw_string = True
        target.is_node = True
        target.node_id = replaced_contents.strip()
        targets.append(target)
    return targets

def get_all_links_from_string(string, include_http=False):
    links = []
    replaced_contents = string
    
    for match in syntax.cross_project_link_with_node_c.finditer(replaced_contents):
        link = UrtextLink(match.group())
        link.project_name = match.group(2)
        link.node_id = match.group(6)
        link.is_node = True
        if match.group(9):
            try:
                link.dest_node_position = int(match.group(9)[1:])
            except:
                pass
        link.position_in_string = match.start()
        links.append(link)
        replaced_contents = replaced_contents.replace(match.group(),' ', 1)

    for match in syntax.file_link_c.finditer(replaced_contents):
        link = UrtextLink(match.group())
        if match.group(1) == syntax.file_link_modifiers['missing']:
            link.is_missing = True
        link.path = match.group(2)
        link.is_file = True
        link.position_in_string = match.start()
        if match.group(4):
            if match.group(4)[0] == ":":
               link.character_number = int(match.group(4)[1:])
            if match.group(4)[0] == ".":
               link.line_number = int(match.group(4)[1:])
            link.suffix = match.group(4)
        links.append(link)
        replaced_contents = replaced_contents.replace(match.group(),' ', 1)
    
    for match in syntax.node_link_or_pointer_c.finditer(replaced_contents):
        link = UrtextLink(match.group())
        kind = None
        if match.group(1) in syntax.node_link_modifiers.values():
            for kind in syntax.node_link_modifiers:
                if match.group(1) == syntax.node_link_modifiers[kind]:
                    kind = kind.upper()
                    break

        if kind == 'ACTION':
            link.is_action = True

        if kind == 'MISSING':
            link.is_missing = True

        link.node_id = match.group(5).strip()
        link.is_node = True
        if match.group(7):
            try:
                link.dest_node_position = int(match.group(7)[1:])
            except:
                pass
        if match.group(6) == syntax.pointer_closing_wrapper:
            link.is_pointer = True  
        link.position_in_string = match.start()
        links.append(link)
        replaced_contents = replaced_contents.replace(match.group(),' ', 1)
    
    for match in syntax.project_link_c.finditer(replaced_contents):
        link = UrtextLink(match.group())        
        link.project_name = match.group(2)      
        link.position_in_string = match.start()
        links.append(link)
        replaced_contents = replaced_contents.replace(match.group(),' ', 1)

    if include_http:
        for match in url_match_c.finditer(replaced_contents):
            if match.group(1):
                http_link = match.group(1)
            else:
                http_link = match.group(3)
            link = UrtextLink(http_link)          
            link.is_http = True
            link.url = http_link
            link.position_in_string = match.start()
            links.append(link)
            replaced_contents = replaced_contents.replace(http_link,' ', 1)

    return links, replaced_contents

def get_link_from_position_in_string(string, position, include_http=True):
    if not string.strip():
        return None
    links, r = get_all_links_from_string(string, include_http=include_http)
    if links:
        links = sorted(links, key=lambda l: l.position_in_string)
        for link in links:
            if position in range(link.position_in_string, link.position_in_string+len(link.matching_string)):
                return link
        return link

def get_file_extension(filename):
    if len(os.path.splitext(filename)) == 2:
        return os.path.splitext(filename)[1].lstrip('.')

def strip_errors(contents):
    for match in syntax.urtext_message_c.findall(contents):
        contents = match.sub('', contents)
    return contents
