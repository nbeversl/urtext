from urtext.extensions.extension import UrtextExtensionWithInteger

class Limit(UrtextExtensionWithInteger):

	name = "LIMIT"
	phase = 150

	def dynamic_output(self,nodes):
		if self.number:
			return nodes[:self.number]
		return nodes
