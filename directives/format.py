class Format:

	phase = 800
	name = ["FORMAT"]

	def dynamic_output(self, contents):

		self.parse_argument_string(self.argument_string)
		if self.have_keys('indent'):
			try:
				indent = int(self.params_dict['indent'][0][0]) #temporary fix
			except:
				print(indent + ' is not a number')
				return contents
			indentation = '\t' * indent
			lines = contents.split('\n')
			indented_contents = []
			for l in lines:				
				indented_contents.append(indentation + l)
			contents = '\n'.join(indented_contents)
		return contents

urtext_directives=[Format]