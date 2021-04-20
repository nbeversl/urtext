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
from .function import UrtextFunctionWithParamsFlags, UrtextFunctionWithInteger
from urtext.utils import force_list

class NodeQuery(UrtextFunctionWithParamsFlags):

	name = "QUERY"
	phase = 100

	def build_list(self, nodes, projects):
		
		for project in projects:

			if '-all' in self.flags:
				added_nodes = set([node_id for node_id in project.nodes])
			
			else: 
				added_nodes = set([])
				if self.have_flags('-blank'):
					added_nodes = set([node_id for node_id in project.nodes if project.nodes[node_id].blank])

				for project in projects:
					added_nodes = added_nodes.union(
						_build_group_and(
							project, 
							self.params, 
							include_dynamic=self.have_flags('-include_dynamic'))
						)
			passed_nodes = set(nodes)
			included_nodes = list(passed_nodes.union(set(project.nodes[node_id] for node_id in added_nodes)))
		return list(included_nodes)

	def execute(self, nodes, projects, m_format):
		return self.build_list(nodes ,projects)

class Exclude(NodeQuery):
	
	name = ["EXCLUDE","-"]
	phase = 105


	def execute(self, nodes, projects, m_format):

		excluded_nodes = set(self.build_list([], projects))

		return list(set(nodes) - excluded_nodes)

class Include(NodeQuery):

	name = ["INCLUDE","+"] 	
	phase = 100


class Limit(UrtextFunctionWithInteger):

	name = "LIMIT"
	phase = 110


	def execute(self, nodes, project, m_format):
		if self.number:
			return nodes[:self.number]
		return nodes


def _build_group_and(project, params, include_dynamic=False):
	
	found_sets = []
	new_group = set([])
	for group in params:
		key, value, operator = group
		if key.lower() == 'id' and operator == '=':
			new_group = set([value])
		else:
			new_group = set(project.get_by_meta(key, value, operator))
		found_sets.append(new_group)

	for this_set in found_sets:
		new_group = new_group.intersection(this_set)

	if not include_dynamic:
		new_group = [f for f in new_group if f in project.nodes and not project.nodes[f].dynamic and not project.nodes[f].errors]

	return new_group

