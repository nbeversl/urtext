from .function import UrtextFunctionWithParamsFlags

class Sort(UrtextFunctionWithParamsFlags):

	name = ["SORT","S"]
	phase = 120

	def __init__(self, string):
		super().__init__(string)
		self.sort_numeric = self.have_flags(['-n','-num'])
		self.use_timestamp = self.have_flags(['-timestamp','-t'])
		self.sort_reverse = self.have_flags(['-reverse','-r'])
		
	def execute(self, nodes, project, format):

		if self.params and self.use_timestamp:
			sort_order = lambda node: ( node.metadata.get_date(self.params[0]), node.id)

		elif self.params:        
			if self.params[0] in ['_newest_timestamp', '_oldest_timestamp']:
				sort_order = lambda node: ( node.metadata.get_date(self.params), node.id)            
			else:
				sort_order = lambda node: ( node.metadata.get_first_value(self.params[0]), node.id)            
		else:
			sort_order = lambda node: node.id

		return sorted(
			nodes,
			key=sort_order,
			reverse=self.sort_reverse)
