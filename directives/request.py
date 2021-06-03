from urtext.directive import  UrtextDirective
import urllib

class Request(UrtextDirective):

	name = ["REQUEST"]
	phase = 300
		
	def dynamic_output(self, nodes):

		with urllib.request.urlopen(self.argument_string) as f:
			t = f.read().decode('utf-8')
		return '%%-JSON\n'+ t +'\n%%-JSON-END\n'
