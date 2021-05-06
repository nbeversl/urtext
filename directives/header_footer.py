from urtext.directive import UrtextDirective

class UrtextHeader(UrtextDirective):

    name = ["HEADER"]
    phase = 500
    
    def dynamic_output(self, contents):
        if not self.argument_string:
            self.argument_string = ''
        header = bytes(self.argument_string, "utf-8").decode("unicode_escape")
        if header and header[-1] != '\n':
            header += '\n'
        return ''.join([header, contents])

class UrtextFooter(UrtextDirective):

    name = ["FOOTER"]
    phase = 500

    def dynamic_output(self, contents):
        
        footer = bytes(self.argument_string, "utf-8").decode("unicode_escape") + '\n'
        return ''.join([contents, footer])
