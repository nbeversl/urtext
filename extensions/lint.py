import os
if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../sublime.txt')):
	from Urtext.urtext.extension import UrtextExtension
	from Urtext.urtext.buffer import UrtextBuffer
else:
	from urtext.extension import UrtextExtension
	from urtext.buffer import UrtextBuffer

class UrtextLint(UrtextExtension):

	name = ["LINT"]

	def run(self, node_id):
		if 'get_buffer' in self.project.editor_methods:
			if node_id in self.project.nodes:
				buffer_contents = self.project.editor_methods['get_buffer'](node_id)
				if buffer_contents:
					buffer = UrtextBuffer(self.project)
					buffer.lex_and_parse(buffer_contents)

					linted_contents = []
					buffer_ranges = []

					for node in buffer.nodes:
						buffer_ranges.extend(node.ranges)

					buffer_ranges = sorted(buffer_ranges, key = lambda r: r[0])
					for index, r in enumerate(buffer_ranges):
						nested = None
						for node in buffer.nodes:
							if r in node.ranges or [r[0],r[1]+1] in node.ranges:
								nested = node.nested
								break

						if not node.compact and not node.root_node:
							r[0] -= 1
							if index < len(buffer_ranges) - 1:
								buffer_ranges[index+1][1] -= 1

						linted_contents.append(strip_and_indent(
							buffer_contents[r[0]:r[1]],
							nested))
	
				buffer.update_node_contents(node.id, '\n'.join(linted_contents))

def strip_and_indent(text, indent):
	stripped_text = []
	for line in text.split('\n'):
		if line.strip() == "":
			continue
		indented_line = ('\t' * indent) + line.strip()
		stripped_text.append(indented_line)
	return '\n'.join(stripped_text)

