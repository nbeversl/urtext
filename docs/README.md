# Installation Instructions

The decision has been made not to include Urtext or its dependencies in the Urtext package for Sublime. This is to simplify developing Urtext independently for other contexts. As such, it is necessary to install everything manually into Sublime's Python environment, and to update them independently when desired.

To use Urtext in Sublime Text:

- Clone or download Sublime Urtext ( https://github.com/nbeversl/urtext_sublime ). Place it in your Packages folder (Sublime Text 3/Packages).

- The following must then be manually added to Sublime's library folder (`Sublime Text 3/Lib/python3.3`):

    - anytree
        https://github.com/c0fec0de/anytree
        The folder needed is `anytree` inside this download; add it to `Sublime Text 3/Lib/python3.3`.

    - whoosh
        https://bitbucket.org/mchaput/whoosh/downloads/
        The folder needed is `src/whoosh`; add it to `Sublime Text 3/Lib/python3.3`.

    - pytz
        https://pypi.org/project/pytz/
        The folder neded is `pytz`; add it to `Sublime Text 3/Lib/python3.3`.

    - six
        https://pypi.org/project/six/
        The only FILE needed is `six.py`, nothing else; add this directly to `Sublime Text 3/Lib/python3.3`.

    - urtext 
        https://github.com/nbeversl/urtext
        (This is Urtext itself.) Put the entire folder (`urtext`) into `Sublime Text 3/Lib/python3.3`.

In the future a script may be provided to install/update these dependencies, but for now it is a manual process.

Close and reopen Sublime Text. At this point, Sublime Text will automatically install `watchdog`, an additional dependency.

To begin reading this documentation using Urtext in Sublime, navigate to its folder and select Urtext: Home from the Sublime Command Palette. 