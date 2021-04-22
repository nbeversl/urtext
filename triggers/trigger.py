"""base class for Urtext Trigger """

class UrtextTrigger():

    name = None

    def __init__(self, argument_string):
        self.argument_string = argument_string

    def execute(self):
        return None