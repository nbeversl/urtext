import re

# Units

pattern_break =                         r'($|(?=[\s|\r|]))'

# Syntax Elements

node_opening_wrapper =                  '{'
node_closing_wrapper =                  '}'
link_opening_wrapper =                  '| '
link_opening_character =                r'\|'
link_modifiers = {
    'file'          : r'\/',
    'http'          : r'\/\/',    
    'action'        : r'\!',
    'no_modifier'   : '',
    'missing'       : r'\?'
}
link_modifier_group =                   r'(' + '|'.join(['(' + m + ')' for m in link_modifiers.values()]) + ')'
node_link_modifier_group =              r'(' + '|'.join(['(' + m + ')' for m in [
                                            link_modifiers['action'],
                                            link_modifiers['missing'],
                                            link_modifiers['no_modifier']
                                            ]]) + ')'
link_closing_wrapper =                  ' >'
pointer_closing_wrapper =               ' >>'
urtext_message_opening_wrapper =        '<!'
urtext_message_closing_wrapper =        '!>'
timestamp_opening_wrapper =             '<'
timestamp_closing_wrapper =             '>'
title_marker =                          ' _'
metadata_assignment_operator =          '::'
metadata_closing_marker =               ';'
metadata_separator =                    '-'
other_project_link_prefix =             '=>'
dynamic_def_opening_wrapper =           '[['
dynamic_def_closing_wrapper =           ']]'
parent_identifier =                     ' ^ '
virtual_target_marker =                 '@'
file_link_opening_wrapper =             link_opening_character + link_modifiers['file'] + ' '
http_link_opening_wrapper =             link_opening_character + link_modifiers['http'] + ' '

# Base Patterns

bullet =                                r'^([^\S\n]*?)•'
closing_wrapper =                       r'(?<!\\)' + re.escape(node_closing_wrapper)
dd_flag =                               r'((^|\s)(-[\w|_]+)|((^|\s)\*))(?=\s|$)'
dd_key =                                r'(^|\s)[\w_]+(\s|$)'
dynamic_def =                           r'(?:\[\[)([^\]]*?)(?:\]\])'
embedded_syntax_open =                  r'%%\w+'
embedded_syntax_close =                 r'%%'+pattern_break
format_key =                            r'\$_?[\.A-Za-z0-9_-]*'
hash_key =                              r'#'
node_link_opening_wrapper_match =       r''.join([
                                            link_opening_character,
                                            node_link_modifier_group,
                                            r'\s'
                                            ])
metadata_arg_delimiter =                r';|\r'
metadata_op_before =                    r'before'
metadata_op_after =                     r'after'
metadata_op_equals =                    r'='
metadata_op_not_equals =                r'!='
metadata_op_contains =                  r'\?'
metadata_op_is_like =                   r'~'
metadata_ops_or =                       r'\|'
metadata_assigner =                     r''+metadata_assignment_operator
metadata_end_marker =                   r';'
metadata_entry_modifiers =              r'[+]?\*{0,2}'
metadata_key =                          r'[\w_\?\!\#\d-]+?'
metadata_values =                       r'[^\n;]*[\n;]?'
metadata_entry =                        r''.join([
                                            metadata_entry_modifiers, 
                                            metadata_key,
                                            metadata_assigner,
                                            metadata_values
                                            ])                                           
metadata_separator_pattern =            r'\s' + metadata_separator + r'\s'
metadata_tag_self =                     r'\+'
metadata_tag_desc =                     r'\*'
meta_to_node =                          r'(\w+)\:\:\{'
opening_wrapper =                       r'(?<!\\)' + re.escape(node_opening_wrapper)
preformat =                             r'\`.*?\`'
sub_node =                              r'(?<!\\){(?!.*(?<!\\){)(?:(?!}).)*}'
virtual_target =                        r'' + virtual_target_marker + '[\w_]+'
disallowed_title_characters = [
    r'\|',
    r'>',
    r'@',
    r'\n',
    r'\r'
]
title_pattern =                         r'^([^' + r''.join(disallowed_title_characters) + ']+)'
id_pattern =                            r'([^\|>\n\r]+)'

# for syntax highlighting only:

sh_metadata_key =                       metadata_key + '(?='+metadata_assigner+')'
sh_metadata_values =                    r'(?<=::)[^\n};@\s]+;?'
sh_metadata_key_c =                     re.compile(sh_metadata_key)
sh_metadata_values_c =                  re.compile(sh_metadata_values)
metadata_flags =                        r'\+?\*{1,2}(?=' + metadata_key + ')' 
metadata_flags_c =                      re.compile(metadata_flags)

# Composite patterns

compact_node =                          bullet + r'([^\r\n]*)(?=\n|$)'
embedded_syntax_full =                  embedded_syntax_open + '.+?' + embedded_syntax_close
hash_meta =                             r'(?:^|\s)'+ hash_key + r'[A-Z,a-z].*?\b'
node_link =                             r'(\|\s)(' + id_pattern + ')\s>(?!>)'
function =                              r'([A-Z_\-\+\>]+)\((((\|\s)(([^\|>\n\r])+)\s>)?([^\)]*?))\)'

node_link_or_pointer =                  node_link_opening_wrapper_match + '(' + id_pattern + ')\s>{1,2}(?!>)'
node_action_link =                      link_opening_character + link_modifiers['action'] + '\s' '(' + id_pattern + ')\s>{1,2}(?!>)'

node_pointer =                          r'(\|\s)(' + id_pattern + ')\s>>(?!>)'
node_title =                            r'^'+ title_pattern +r'(?=' + title_marker  + pattern_break + ')'
timestamp =                             r''.join([
                                            timestamp_opening_wrapper,
                                            r'([^-/<\s][^=<]+?)',
                                            timestamp_closing_wrapper])
file_link =                             r''.join([
                                            link_opening_character,
                                            link_modifiers['file'],
                                            ' '
                                            r'([^;]+)',
                                            link_closing_wrapper])

http_link =                             r''.join([
                                            http_link_opening_wrapper,
                                            r'([^>]+)',
                                            link_closing_wrapper
                                            ])
urtext_messages =                       r''.join([
                                            urtext_message_opening_wrapper,
                                            '.*?',
                                            urtext_message_closing_wrapper
                                            ])
# Compiled Patterns

bullet_c =                      re.compile(bullet)
compact_node_c =                re.compile(compact_node, flags=re.MULTILINE)
closing_wrapper_c =             re.compile(closing_wrapper)
dd_flag_c =                     re.compile(dd_flag)
dd_key_c =                      re.compile(dd_key)
dynamic_def_c =                 re.compile(dynamic_def, flags=re.DOTALL)
file_link_c =                   re.compile(file_link)
embedded_syntax_open_c =        re.compile(embedded_syntax_open, flags=re.DOTALL)
embedded_syntax_c =             re.compile(embedded_syntax_full, flags=re.DOTALL)
embedded_syntax_close_c =       re.compile(embedded_syntax_close, flags=re.DOTALL)
urtext_messages_c =             re.compile(urtext_messages, flags=re.DOTALL)
format_key_c =                  re.compile(format_key, flags=re.DOTALL)
function_c =                    re.compile(function, flags=re.DOTALL)
hash_key_c =                    re.compile(hash_key)
hash_meta_c =                   re.compile(hash_meta)
metadata_arg_delimiter_c =      re.compile(metadata_arg_delimiter)
metadata_entry_c =              re.compile(metadata_entry, flags=re.DOTALL)
metadata_ops =                  re.compile(r'(' + r'|'.join([
                                        metadata_op_before,
                                        metadata_op_after,
                                        metadata_op_equals,
                                        metadata_op_not_equals,
                                        metadata_op_contains,
                                        metadata_op_is_like
                                    ]) + r')')

metadata_ops_or_c =             re.compile(metadata_ops_or)
metadata_separator_pattern_c =  re.compile(metadata_separator_pattern)
meta_to_node_c =                re.compile(meta_to_node, flags=re.DOTALL)
metadata_tag_self_c =           re.compile(metadata_tag_self)
metadata_tag_desc_c =           re.compile(metadata_tag_desc)
node_action_link_c =            re.compile(node_action_link, flags=re.DOTALL)
node_pointer_c =                re.compile(node_pointer)
node_title_c =                  re.compile(node_title, flags=re.MULTILINE)
metadata_assigner_c =           re.compile(metadata_assigner)
node_link_c =                   re.compile(node_link)
node_link_or_pointer_c =        re.compile(node_link_or_pointer)
opening_wrapper_c =             re.compile(opening_wrapper)
pointer_closing_wrapper_c =     re.compile(pointer_closing_wrapper)
preformat_c =                   re.compile(preformat, flags=re.DOTALL)
subnode_regexp_c =              re.compile(sub_node, flags=re.DOTALL)
timestamp_c =                   re.compile(timestamp)
title_regex_c =                 re.compile(title_pattern)
http_link_c =                   re.compile(http_link)             
virtual_target_match_c =        re.compile(virtual_target, flags=re.DOTALL)
metadata_replacements = re.compile("|".join([
    r'(?:<)([^-/<\s`][^=<]+?)(?:>)',        # timestamp
    r'\*{2}\w+\:\:([^\n};]+);?',            # inline_meta
    r'(?:^|\s)#[A-Z,a-z].*?(\b|$)',         # shorthand_meta
    ]))

compiled_symbols = {
    opening_wrapper_c :                 'opening_wrapper',
    closing_wrapper_c :                 'closing_wrapper',
    re.compile(node_pointer) :          'pointer',
    compact_node_c :                    'compact_node',
    meta_to_node_c :                    'meta_to_node'
    }

embedded_syntax_symbols = {
    re.compile(embedded_syntax_open) :  'embedded_syntax_open', 
    re.compile(embedded_syntax_close) : 'embedded_syntax_close',

}
