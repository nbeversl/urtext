from urtext.directive import UrtextDirective

class Log(UrtextDirective):

	name = ["LOG"]    
	phase = 500
			
	def dynamic_output(self, node_list):
		output = []
		for k in self.project.messages:
			if k:
				file = 'f>'+k+'; '
			else:
				file = '(no file) '
			output.append(file + ":" + self.project.messages[k])

		return '\n'.join(output) + '\n'
