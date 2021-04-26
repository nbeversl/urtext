from .function import  UrtextFunctionWithKeysFlags
from urtext.timestamp import UrtextTimestamp
import datetime

class Sort(UrtextFunctionWithKeysFlags):

	name = ["SORT","S"]
	phase = 120
		
	def execute(self, nodes, projects, format):
		self.project=projects[0]
		# print(self.keys[0])
		# print([n.metadata.get_first_value(self.keys[0], use_timestamp=self.have_flags('-t')) for n in nodes ])
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
			if value:
				if ext =='timestamp' and e.timestamps:  
					v = e.timestamps[0].datetime
				t.append(value)
		return tuple(t)				