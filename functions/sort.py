from .function import  UrtextFunctionWithKeysFlags
from urtext.timestamp import UrtextTimestamp
import datetime

class Sort(UrtextFunctionWithKeysFlags):

	name = ["SORT","S"]
	phase = 120
		
	def execute(self, nodes, projects, format):
		self.project=projects[0]
		if self.keys:
			return sorted(
				nodes,
				key= lambda node: self.sort_values(node, self.keys),
				reverse=self.have_flags(['-reverse','-r'])
				)
		return nodes

	def sort_values(self, node, keys):
		t = []
		for k in keys:
			k, ext = k, ''
			if '.' in k:
				k, ext = k.split('.')
			value = node.metadata.get_first_value(k, return_type=True)
			if isinstance(value, str):
				value=value.lower()
			t.append(value)
		return tuple(t)				