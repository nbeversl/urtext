from urtext.timestamp import UrtextTimestamp
import urtext.syntax as syntax
import urtext.utils as utils
import os

class MetadataValue:

    def __init__(self, value_string):

        self.timestamp = None
        self.unparsed_text = value_string
        for ts in syntax.timestamp_c.finditer(value_string):
            dt_string = ts.group(0).strip()
            value_string = value_string.replace(dt_string, '').strip()
            t = UrtextTimestamp(
                dt_string[1:-1],
                start_position=ts.start())
            if t.datetime:
                self.timestamp = t
        self.text = value_string
        self.text_lower = value_string.lower()
        self.is_node = False

    def num(self):
        try:
            return float(self.text)
        except:
            return float('inf')

    def links(self):
        urtext_links, replaced_contents = utils.get_all_links_from_string(self.text)
        for urtext_link in urtext_links:
            if urtext_link.is_file:
                urtext_link.path = os.path.join(
                    os.path.dirname(self.entry.node.filename),
                    urtext_link.path)
        return urtext_links

    def __lt__(self, other):
        if self.text:
            return self.text < other.text
        return self.num() < other.num()

    def true(self):
        if self.text:
            if self.text.lower() in [
                'yes', 'true', 'y', 'on']:
                return True
        return False

    def log(self):
        print('text: %s' % ( 
            self.text if self.text else '' ))
        print('timestamp: %s' % (
            self.timestamp.unwrapped_string if self.timestamp else ''))
        print('-')