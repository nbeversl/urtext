from .extension import UrtextExtension
from .tree import Tree

class NodeList(UrtextExtension):

	name = ["LIST"]    
	phase = 200
	
	def dynamic_output(self, node_list):
		contents = []
		for n in node_list:
			t = Tree(self.project)
			t.set_dynamic_definition(self.dynamic_definition)
			t.parse_argument_string(self.argument_string)
			try:
				t.depth = int(self.argument_string)
			except:
				pass
			added_contents = t.dynamic_output(n)
			contents.append(added_contents)
		return ''.join(contents)
