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
from whoosh.writing import AsyncWriter
from whoosh.qparser import QueryParser
from whoosh.highlight import UppercaseFormatter
import concurrent.futures
from concurrent.futures import ALL_COMPLETED

def rebuild_search_index(self):
    
    writer = AsyncWriter(self.ix)

    for node_id in self.nodes:
        node = self.nodes[node_id]
        fs = []
        try:
            fs.append(self.aux_executor.submit(writer.update_document, 
                            title=node.title,
                            path=node.id,
                            content=node.content_only()))
        except:
            print('ERROR in '+node_id)

    concurrent.futures.wait(fs, timeout=None, return_when=ALL_COMPLETED)
    writer.commit()
    
def search_term(self, string, exclude=[]):

    self.ix.refresh()
    with self.ix.searcher() as searcher:
        if not searcher.up_to_date():
            seacher = searcher.refresh()
        qp = QueryParser("content", self.ix.schema)
        query = qp.parse(string)
        results = searcher.search(query, limit=1000)
        results.formatter = UppercaseFormatter()
        final_results = ''
        for result in results:
            node_id = result['path']
            if node_id in exclude:
                 continue
            final_results += '| ' + self.nodes[node_id].title + ' >'+node_id +'\n\n' + result.highlights("content").strip() + '\n'
    final_results = final_results.replace('\x0d', '\n')
    final_results = final_results.replace('\t', '')
    real_final_results = ''
    for line in final_results.split('\n'):
        real_final_results += line.strip()  + '\n'
    return real_final_results

search_functions = [ rebuild_search_index, search_term ]