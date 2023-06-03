import os
import datetime
import time
import concurrent.futures
if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../sublime.txt')):
	from Urtext.urtext.directive import UrtextDirective
	from Urtext.urtext.buffer import UrtextBuffer
else:
	from urtext.directive import UrtextDirective
	from urtext.buffer import UrtextBuffer

class UrtextClock(UrtextDirective):

	name = ["CLOCK"]
	phase = 350
	executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)  

	def dynamic_output(self, nodes):
		if 'get_buffer' in self.project.editor_methods:
			for target_id in self.dynamic_definition.target_ids:
				buffer_contents = self.project.editor_methods['get_buffer'](target_id)
				if buffer_contents:
					buffer = UrtextBuffer(self.project)
					buffer.lex_and_parse(buffer_contents)
					node = None
					for node in buffer.nodes:
						if node.id == target_id:
							break
					if node:
						time.sleep(1)
						now = datetime.datetime.now()
						if 'replace' in self.project.editor_methods:
							buffer.update_node_contents(node.id, ''.join([ 
			                    node.id,
			                    '\n',
			                    now.strftime('%A, %B %-d, %Y %I:%M:%S')
			                    ]))
						self.executor.submit(self.dynamic_output, nodes)
						return ''
		return ''

