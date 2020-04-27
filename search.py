# -*- coding: utf-8 -*-
"""
This file is part of Urtext.

Urtext is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Urtext is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Urtext.  If not, see <https://www.gnu.org/licenses/>.

"""
import concurrent.futures

def search_term(self, term):
	return UrtextSearchResult(self, term)

class UrtextSearchResult:

	def __init__(self, project, term):
		self.project = project
		self.term = term
		self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
		self.complete = False
		self.result = []
	
	def initiate_search(self):
		#self.executor.submit(self._search_for, self.term)
		self._search_for(self.term)
		
	def _search_for(self, term):
		for filename in self.project.files:
			contents = self.project._full_file_contents(filename)
			if term.lower() in contents.lower():
				self.result.append(filename)
		self.complete = True

search_functions  = [ search_term ]