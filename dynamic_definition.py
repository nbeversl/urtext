import datetime
from urtext.utils import get_id_from_link, get_all_targets_from_string
import urtext.syntax as syntax

class UrtextDynamicDefinition:

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
        self.sorted = False
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

            elif func in ['WHEN']:
                flags = syntax.dd_flags_c.match(argument_string)
                if flags:
                    flags = flags.group().split(' ')
                    flags = [f.strip() for f in flags if f]
                    for flag in flags:
                        if flag[0] == '-':
                            flag = flag[1:]
                        self.flags.append(flag)
                continue

            else:
                directive = self.project.get_directive(func)
                if directive:
                    op = directive(self.project)
                    op.argument_string = argument_string
                    op.dynamic_definition = self
                    op.parse_argument_string(argument_string)
                    self.operations.append(op)
                elif self.project.compiled:
                    self.system_contents.append('directive "%s" not found' % func)

    def is_manual(self):
        for op in self.operations:
            if op.is_manual:
                return True
        return False

    def preserve_title_if_present(self, target):
        if target.is_virtual and target.matching_string == '@self' and self.source_node.id in self.project.nodes:
            return ' ' + self.project.nodes[self.source_node.id].title + syntax.title_marker + '\n'
        if target.is_node and target.node_id in self.project.nodes and (
                self.project.nodes[target.node_id].first_line_title):
            return ' ' + self.project.nodes[target.node_id].title + syntax.title_marker + '\n'
        return ''

    def preserve_timestamp_if_present(self, target):
        if target.is_virtual and target.matching_string == '@self' and self.source_node.id in self.project.nodes:
            oldest_timestamp = self.project.nodes[self.source_node.id].metadata.get_oldest_timestamp()
            if oldest_timestamp:
                return oldest_timestamp.wrapped_string
        if target.is_node and target.node_id in self.project.nodes:
            oldest_timestamp = self.project.nodes[target.node_id].metadata.get_oldest_timestamp()
            if oldest_timestamp:
                return oldest_timestamp.wrapped_string
        return ''

    def process_output(self, target):
        if not len(self.operations):
            return False
        if target.is_node and target.node_id in self.project.nodes:
            existing_contents = self.project.nodes[target.node_id].contents_with_contained_nodes()
            if existing_contents.strip() and existing_contents.strip()[0] == '~':
                existing_contents = existing_contents[1:]
        else:
            existing_contents = ''
        self.included_nodes = []
        self.excluded_nodes = []
        self.sorted = False
        self.project.run_hook('on_dynamic_def_process_started', self)
        accumulated_text = ''

        for operation in self.operations:

            # if not self.sorted:
            #     # TODO this should not happen on every iteration.
            #     self.included_nodes = sorted(
            #         self.included_nodes,
            #         key=lambda node: node.title)
            #     self.included_nodes = sorted(
            #         self.included_nodes,
            #         key=lambda node: node.metadata.get_first_value(
            #             '_oldest_timestamp').timestamp.datetime if (
            #             node.metadata.get_first_value('_oldest_timestamp')) else (
            #             datetime.datetime(
            #                 1, 1, 1,
            #                 tzinfo=datetime.timezone.utc)),
            #         reverse=True)

            current_text = accumulated_text
            try:
                transformed_text = operation.dynamic_output(current_text)
            except Exception as e:
                accumulated_text += ''.join([
                    'error in ',
                    str(operation.name),
                    ': ',
                    str(e),
                    '\n'
                ])
                continue
            if transformed_text is False:  # not None
                return existing_contents
            if transformed_text is None:
                accumulated_text = current_text
                continue
            accumulated_text = transformed_text
        self.flags = []
        self.project.run_hook('on_dynamic_def_process_ended', self)
        if self.system_contents:
            accumulated_text += '\n'.join(self.system_contents)
        return accumulated_text

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
        target_ids = [t.node_id for t in self.targets if t.is_node and t.node_id is not None]
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
        if target.is_node and target.node_id not in self.project.nodes:
            # if self.source_node.id not in self.project.nodes:
            #     continue # ?? <Fri., Sep. 06, 2024, 12:29 PM CEST>
            filename = self.project.nodes[self.source_node.id].filename
            self.project.log_item(filename, {
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
        output = '~' + ''.join([
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
