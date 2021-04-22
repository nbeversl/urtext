from .function import  UrtextFunctionWithKeysFlags

class Sort(UrtextFunctionWithKeysFlags):

	name = ["SORT","S"]
	phase = 120
		
	def execute(self, nodes, projects, format):
		self.project=projects[0]
			
		return sorted(
			nodes,
			key= lambda node: self.sort_by_multi(node, self.keys),
			reverse=self.have_flags(['-reverse','-r'])
			)

	def sort_by_multi(self, node, keys):
		return tuple([node.metadata.get_first_value(k) for k in keys])

