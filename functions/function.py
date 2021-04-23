import re
from urtext.utils import force_list
flag_regx = re.compile(r'((^|\s)(-[\w|_]+)|((^|\s)\*))(?=\s|$)')

## Base function class
class UrtextFunction():

    name = None

    def __init__(self, argument_string):
        self.argument_string = argument_string

    def execute(self):
        return ''

class UrtextFunctionWithKeysFlags(UrtextFunction):
    
    phase = 100

    def __init__(self, argument_string):
        super().__init__(argument_string)
        self.keys = []
        self.flags = []
        no_keys = self._parse_flags(argument_string)
        self._parse_keys(no_keys)
        
    def _parse_keys(self, argument_string):
        for word in argument_string.split(' '):
            if word and word[0] != '-':
                self.keys.append(word)

    def _parse_flags(self, argument_string):
        flag_regx = re.compile(r'(^|\s)-[\w|_]+(?=\s|$)')
        for f in flag_regx.finditer(argument_string):
            self.flags.append(f.group().strip())
            argument_string = argument_string.replace(f.group(),' ')
        return argument_string
    
    def have_flags(self, flags):
        for f in force_list(flags):
            if f in self.flags:
                return True
        return False

    def have_keys(self, keys):
        for f in force_list(keys):
            if f in self.keys:
                return True
        return False


class UrtextFunctionWithParamsFlags(UrtextFunction):

    phase = 100

    def __init__(self, argument_string):
        super().__init__(argument_string)
        self.params = []
        self.params_dict = {}
        self.flags = []
        no_flags = self._parse_flags(argument_string)
        self._parse_params(no_flags)
        
    def _parse_params(self, argument_string):

        def separate(string, delimiter=';'):
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
                key, value, delimiter = key_value(param, ['before','after','=','?','~', '!='])
                if value:
                    for v in value:
                        self.params.append((key,v,delimiter))
                        
        for param in self.params:
            self.params_dict[param[0]] = param[1:]

    def _parse_flags(self, argument_string):

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

