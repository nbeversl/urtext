"""
Methods used with watchdog
"""

def on_created(self, filename):
    unlocked, lock_name = self.check_lock()
    if not unlocked:
        return (False, lock_name)
    if os.path.isdir(filename):
        return (True,'')
    filename = os.path.basename(filename)
    if filename in self.files:
        return (True,'')
    self._parse_file(filename, re_index=True)
    self._log_item(filename +' modified. Updating the project object')
    self.update()
    return (True,'')

def on_moved(self, filename):
    unlocked, lock_name = self.check_lock()
    if not unlocked:
        return (False, lock_name)
    old_filename = os.path.basename(filename)
    new_filename = os.path.basename(filename)
    if old_filename in self.files:
        self.log.info('RENAMED ' + old_filename + ' to ' +
                                new_filename)
        self._handle_renamed(old_filename, new_filename)
    return (True,'')

watchdog_functions = [on_created, on_moved]