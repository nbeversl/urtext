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
import re
import os

node_id_regex = r'>[0-9,a-z]{3}\b'
function_regex = re.compile('([A-Z_\-\+]+)\((.*?)\)', re.DOTALL)
from urtext.extensions.extension import UrtextExtension
from urtext.utils import force_list
from urtext.extensions.list import NodeList

class UrtextDynamicDefinition:

	def __init__(self, contents, project):

		self.target_id = None
		self.used_functions = []
		self.operations = []
		self.spaces = 0
		self.project = project
		self.preformat = False
		self.projects = [project]
		self.show = None
		self.multiline_meta = True

		self.init_self(contents)
		if not self.show:
			self.show = '$title $link\n'
			
	def add_projects(self, projects):
		self.projects.extend(force_list(projects))

	def init_self(self, contents):

		for match in re.findall(function_regex,contents):

			func = match[0]
			argument_string = match[1]
			if func and func in self.project.extensions:
				self.operations.append((func, argument_string))
			
			# target
			if func =='ID':
				node_id_match = re.search(node_id_regex, argument_string)
				if node_id_match:
					self.target_id = node_id_match.group(0)[1:]
					continue

			# #output
			# if func == "FORMAT":
			# 	if has_flags(['-multiline-meta','-mm'], flags):
			# 		self.multiline_meta = True
				
			# 	if has_flags(['-preformat','-p'], flags):
			# 		self.preformat = True

			if func == "SHOW":
				self.show = argument_string
			
		if 'LIST' not in [o[0] for o in self.operations] and 'TREE' not in [o[0] for o in self.operations] and 'COLLECT' not in [o[0] for o in self.operations]:
			self.operations.append(('LIST', '1'))
		if 'SORT' not in [o[0] for o in self.operations] :
			self.operations.append(('SORT', ''))

	def process_output(self):
		outcome = []		
		for operation, argument_string in sorted(self.operations, key = lambda op: self.project.extensions[op[0]].phase) :	
			e = self.project.extensions[operation]					
			e.set_dynamic_definition(self)
			e.parse_argument_string(argument_string)			
			outcome = e.dynamic_output(outcome)
		return outcome

class Export:
	def __init__(self):
		self.output_type = '-plaintext'
		self.to_nodes = []
		self.to_files = []
		self.flags = []
		self.preformat = False


