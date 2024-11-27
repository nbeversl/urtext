from urtext.utils import get_id_from_link, get_all_targets_from_string
import urtext.syntax as syntax
import traceback
import datetime

class UrtextFrame:

    def __init__(self, param_string, project, position):

        self.position = position
        self.contents = None
        self.targets = []
        self.included_nodes = []
        self.excluded_nodes = []
        self.flags = []
        self.operations = []
        self.project = project
        self.preformat = False
        self.show = None
        self.enabled = True
        self.param_string = param_string
        self.system_contents = []
        self.init_self(param_string)
        self.source_node = None  # set by node once compiled
        if not self.show:
            self.show = '$_link\n'
        self.ran = False

    def init_self(self, contents):
        self.contents = contents

        for match in syntax.function_c.finditer(contents):

            func, argument_string = match.group(1), match.group().strip(match.group(1)).replace(')(', '')
            argument_string = match.group(2)

            if func in ['TARGET', '>']:    
                self.targets = get_all_targets_from_string(argument_string)
                continue

            else:
                call = self.project.get_call(func)
                if call:
                    op = call(self.project)
                    op.argument_string = argument_string
                    op.frame = self
                    op.parse_argument_string(argument_string)
                    self.operations.append(op)
                elif self.project.compiled:
                    self.system_contents.append('call "%s" not found' % func)

    def is_manual(self):
        for op in self.operations:
            if op.is_manual:
                return True
        return False

    def preserve_title_if_present(self, target):
        if target.is_virtual and target.matching_string == '@self':
            source_node = self.project.get_node(self.source_node.id)
            if source_node:
                return ' ' + source_node.title + syntax.title_marker + '\n'
        if target.is_node:
            target_node = self.project.get_node(target.node_id)
            if target_node and target_node.first_line_title:
                return ' ' + target_node.title + syntax.title_marker + '\n'
        return ''

    def preserve_timestamp_if_present(self, target):
        if target.is_virtual and target.matching_string == '@self':
            source_node = self.project.get_node(self.source_node.id)
            if source_node:
                oldest_timestamp = source_node.metadata.get_oldest_timestamp()
                if oldest_timestamp:
                    return oldest_timestamp.wrapped_string
        if target.is_node:
            target_node = self.project.get_node(target.node_id)
            oldest_timestamp = target_node.metadata.get_oldest_timestamp()
            if oldest_timestamp:
                return oldest_timestamp.wrapped_string
        return ''

    def process_output(self, target):
        if not len(self.operations):
            return False
        if target.is_node:
            target_node = self.project.get_node(target.node_id)
            if target_node:
                existing_contents = target_node.contents_with_contained_nodes()
                if existing_contents.strip() and existing_contents.strip()[0] == '~':
                    existing_contents = existing_contents[1:]
        else:
            existing_contents = ''
        self.included_nodes = []
        self.excluded_nodes = []
        self.project.run_hook('on_frame_process_started', self)
        accumulated_text = ''
        
        for operation in self.operations:
            if operation.should_continue() is False:
                return
            current_text = accumulated_text
            try:
                transformed_text = operation.dynamic_output(current_text)
            except Exception as e:
                accumulated_text += '`' + ''.join([
                    'error in ',
                    str(operation.name),
                    ': ',
                    traceback.format_exc(),
                    '\n'
                ]) + '`'
                break
            if transformed_text is False:  # not None
                return existing_contents
            if transformed_text is None:
                accumulated_text = current_text
                continue
            accumulated_text = transformed_text

        if accumulated_text is '':
            accumulated_text = self.default_output()

        self.flags = []
        self.project.run_hook('on_dynamic_def_process_ended', self)
        if self.system_contents:
            accumulated_text += '\n'.join(self.system_contents)
        return accumulated_text

    def default_output(self):
        for operation in list(reversed(self.operations)):
            if operation.should_continue() is False:
                return '%s specifies no text' % operation.name[0]
            try:
                transformed_text = operation.default_output()
            except Exception as e:
                transformed_text = '`' + ''.join([
                    'error in ',
                    str(operation.name),
                    ': ',
                    traceback.format_exc(),
                    '\n'
                ]) + '`'
                continue
            if transformed_text is None:
                continue
            if transformed_text is False:
                return 'False'
            if transformed_text != '':
                return transformed_text
        return 'No call has text output'

    def have_flags(self, flag):
        if flag and flag[0] == '-':
            flag = flag[1:]
        if flag in self.flags:
            return True
        return False

    def get_definition_text(self):
        return '\n' + ''.join([
            syntax.dynamic_def_opening_wrapper,
            '\n'.join([line.strip() for line in self.contents.split('\n')]),
            syntax.dynamic_def_closing_wrapper
        ])

    def target_ids(self):
        target_ids = [t.node_id for t in self.targets if t.is_node]
        for t in self.targets:
            if t.is_virtual and t.matching_string == "@self":
                target_ids.append(self.source_node.id)
                break
        return target_ids

    def target_files(self):
        return [t.filename for t in self.targets if t.is_file and t.filename is not None]

    def process(self, target, flags=None):
        if flags is None:
            flags = []
        self.flags = flags
        if target.is_node:
            target_node = self.project.get_node(target.node_id)
            if not target_node:
                self.project.log_item(self.source_node.filename, {
                    'top_message': ''.join([
                        'Dynamic node definition in ',
                        self.source_node.link(),
                        '\n',
                        'points to nonexistent node ',
                        syntax.missing_node_link_opening_wrapper,
                        target.node_id,
                        syntax.link_closing_wrapper])
                })
        output = self.process_output(target)
        self.ran = True
        return output

    def post_process(self, target, output):
        output = ''.join([
            # self.preserve_timestamp_if_present(target),
            self.preserve_title_if_present(target),
            output])
        if target.is_virtual and target.matching_string == '@self':
            output += self.get_definition_text()
        return output

    def indent(self, contents, spaces=4):
        content_lines = contents.split('\n')
        content_lines[0] = content_lines[0].strip()
        for index, line in enumerate(content_lines):
            if line.strip() != '':
                content_lines[index] = '\t' * spaces + line
        return '\n' + '\n'.join(content_lines)
