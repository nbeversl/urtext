import imp
import os

MainModule = "__init__"

def getPlugins(plugin_folder):
    plugins = []
   
    possibleplugins = os.listdir(plugin_folder)
    for i in possibleplugins:
        print(i)
        location = os.path.join(plugin_folder, i)
        if not os.path.isdir(location) or not MainModule + ".py" in os.listdir(location):
            continue
        info = imp.find_module(MainModule, [location])
        plugins.append({"name": i, "info": info})
    return plugins

def loadPlugin(plugin):
    return imp.load_module(MainModule, *plugin["info"])


