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
				key= lambda node: node.metadata.get_first_value(self.keys[0], use_timestamp=self.have_flags('-t')),
				reverse=self.have_flags(['-reverse','-r'])
				)
		return nodes

	def sort_values(self, node, keys):
		t = []
		for k in keys:
			k, ext = k, ''
			if '.' in k:
				k, ext = k.split('.')
			values = node.metadata.get_values(k, substitute_timestamp=True)
			print(value)
			replacement = ''
			if ext =='timestamp' and e.timestamps:  
				v = e.timestamps[0].datetime
			else:
				v = node.metadata.get_first_value(k)
			t.append(v)
		print(t)
		return tuple(t)				