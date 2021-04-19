from .function import UrtextFunction
from .tree import Tree

class NodeList(UrtextFunction):

	name = ["LIST"]    
	phase = 200
	
	def execute(self, node_list, projects, m_format):
		contents = []
		for n in node_list:
			added_contents = Tree('depth='+self.argument_string).execute(n, projects[0], m_format)
			contents.append(added_contents)
		return '\n'.join(contents)
