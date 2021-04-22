from urtext.functions.function import UrtextFunction

class UrtextHeader(UrtextFunction):

    name = ["HEADER"]
    phase = 500
    def execute(self, contents, project, format):
        if not self.argument_string:
            self.argument_string = ''
        header = bytes(self.argument_string, "utf-8").decode("unicode_escape")
        if header and header[-1] != '\n':
            header += '\n'
        return ''.join([header, contents])

class UrtextFooter(UrtextFunction):

    name = ["FOOTER"]
    phase = 500

    def execute(self, contents, project, format):
        
        footer = bytes(self.argument_string, "utf-8").decode("unicode_escape") + '\n'

        return ''.join([contents, footer])
