from .extension import UrtextExtension
from .tree import Tree

class NodeList(UrtextExtension):

	name = ["LIST"]    
	phase = 200
	
	def __init__(self, project):
		super().__init__(project)
		self.tree = Tree(self.project)
		
	def dynamic_output(self, node_list):

		self.tree.set_dynamic_definition(self.dynamic_definition)
		self.tree.parse_argument_string(self.argument_string)

		contents = []
		for n in node_list:		
			if self.tree.have_flags('*'):
				self.tree.depth = 99999
			else:
				try:
					self.tree.depth = int(self.argument_string)
				except:
					print(self.argument_string)
			added_contents = self.tree.dynamic_output(n)
			contents.append(added_contents)
		return ''.join(contents)

	def on_file_modified(self, filename):
		#return
		self.tree.on_file_modified(filename)
