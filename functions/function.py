import re
node_id_regex = r'>[0-9,a-z]{3}\b'
filename_regex = r'f>[^;]*'
key_value_regex = re.compile('([^\s]+?):([^\s"]+)')
string_meta_regex = re.compile('([^\s]+?):("[^"]+?")')
entry_regex = re.compile('\w+\:\:[^\n;]+[\n;]?')
from urtext.utils import force_list

## Base function class
class UrtextFunction():

    name = ["FUNCTION"]

    def __init__(self, argument_string):
        self.argument_string = argument_string
        
    def execute(self):
        return ''

class UrtextFunctionWithParamsFlags(UrtextFunction):

    name = ["FUNCTION_WITH_PARAMS_FLAGS"]
    phase = 100

    def __init__(self, argument_string):
        super().__init__(argument_string)
        self.params = []
        self.flags = []
        no_flags = self._parse_flags(argument_string)
        self._parse_params(no_flags)
        
    def _parse_params(self, argument_string):

        def separate(string, delimiter='\;'):
            return [r.strip() for r in re.split(delimiter+'|\n', string)]

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

        if argument_string:
            for param in separate(argument_string):
                key, value, delimiter = key_value(argument_string, ['before','after','=','?','~', '!='])
                if value:
                    for v in value:
                        self.params.append((key,v,delimiter))

    def _parse_flags(self, argument_string):
        flag_regx = re.compile(r'[\s|\b]*-[\w|_]+(?=\s|$)')
        for f in flag_regx.finditer(argument_string):
            self.flags.append(f.group().strip())
            argument_string = argument_string.replace(f.group(),' ')
        return argument_string
    
    def have_flags(self, flags):
        for f in force_list(flags):
            if f in self.flags:
                return True
        return False

class UrtextFunctionWithInteger(UrtextFunction):

    name = ["FUNCTION_WITH_INT"]
    phase = 100
    def __init__(self, argument_string):
        try:
            self.number = int(argument_string)
        except:
            self.number = None        

class UrtextHeader(UrtextFunction):

    name = ["HEADER"]
    phase = 500
    def execute(self, contents, project, format):
    
        header = bytes(self.argument_string, "utf-8").decode("unicode_escape")
        if header[-1] != '\n':
            header += '\n'
        return ''.join([header, contents])

class UrtextFooter(UrtextFunction):

    name = ["FOOTER"]
    phase = 500

    def execute(self, contents, project, format):
        
        footer = bytes(self.argument_string, "utf-8").decode("unicode_escape") + '\n'

        return ''.join([contents, footer])

