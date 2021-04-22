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

parent_dir = os.path.dirname(__file__)
node_id_regex = r'>[0-9,a-z]{3}\b'
filename_regex = r'f>[^;]*'
function_regex = re.compile('([A-Z_\-\+]+)\((.*?)\)', re.DOTALL)
key_value_regex = re.compile('([^\s]+?):([^\s"]+)')
string_meta_regex = re.compile('([^\s]+?):("[^"]+?")')
entry_regex = re.compile('\w+\:\:[^\n;]+[\n;]?')
from urtext.functions.function import UrtextFunction
from urtext.utils import force_list
import urtext.functions.collect
import urtext.functions.include
import urtext.functions.list
import urtext.functions.sort
import urtext.functions.tree
from urtext.functions.list import NodeList
from importlib import import_module

for i in os.listdir(os.path.join(os.path.dirname(__file__),'functions')):
	if '.py' in i:
		i = os.path.basename(os.path.splitext(i)[0])
		import_module('urtext.functions.'+i)

def all_subclasses(cls):
	return set(cls.__subclasses__()).union(
		[s for c in cls.__subclasses__() for s in all_subclasses(c)])

print("FUNCTIONS LOADED")
all_functions = all_subclasses(UrtextFunction)
print(all_functions)

class UrtextDynamicDefinition:
	""" Urtext Dynamic Definition """
	def __init__(self, contents):

		self.memo = None       
		self.target_id = None
		self.used_functions = []
		self.operations = []
		
		# FORMAT
		self.spaces = 0
		self.preformat = False
		self.projects = []
		# SHOW
		self.show = None
		self.use_timestamp = False
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
			for function in all_subclasses(UrtextFunction):
				if function.name and func in function.name:		
					self.used_functions.append(func)	
					self.operations.append(function(argument_string))
			
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
			
		if 'LIST' not in self.used_functions and 'COLLECT' not in self.used_functions:
			self.operations.append(NodeList('1'))

class Export:
	def __init__(self):
		self.output_type = '-plaintext'
		self.to_nodes = []
		self.to_files = []
		self.flags = []
		self.preformat = False

def assign_as_int(value, default):
	try:
		number = int(value)
		return number
	except ValueError:
		return default

def parse_group(definition, group, other_params, inside_parentheses, flags=[]):

	new_group = []

	for param in separate(inside_parentheses):

		key, value, delimiter = key_value(param, ['before','after','=','?','~', '!='])
		if value:
			for v in value:
				new_group.append((key,v,delimiter))
		else:
			other_params.append(param)
		
	group.append(new_group)

def has_flags(flags, flag_list):
	for f in flag_list:
		if f in flags:
			return True
	return False

def key_value(param, delimiters=[':']):
	if isinstance(delimiters, str):
		delimiters = [delimiters]
	for delimiter in delimiters:
		if delimiter in param:
			key,value = param.split(delimiter,1)
			key = key.lower().strip()
			value = [v.strip() for v in value.split('|')]
			return key, value, delimiter
	return None, None, None

def get_flags(contents):
	this_flags = []
	flag_regx = re.compile(r'[\s|\b]*-[\w|_]+(?=\s|$)')
	for m in flag_regx.finditer(contents):
		flag = m.group().strip()
		if flag not in this_flags:
			this_flags.append(flag)
		contents=contents[:m.start()] + ';' + contents[m.end():]
	return contents, this_flags

def get_export_kind(flgs):

	kinds = {   'markdown' :    ['-markdown','-md'],
				'html' :        ['-html'],
				'plaintext' :   ['-plaintext','-txt']}

	for k in kinds:
		for v in kinds[k]:
			if v in flgs:
				return k

	return None

def separate(param, delimiter=';'):
	return [r.strip() for r in re.split(delimiter+'|\n', param)]
