# Urtext Core Library

## This repository

This repository is the core Urtext library in Python. It has no user interface and requires an implementation in a text editor (see [Implementations](https://github.com/nbeversl/urtext?tab=readme-ov-file#sublime-text)).

## What Urtext Is

Urtext /ˈʊrtekst/ is an open-source syntax and interpreter for plaintext writing, research, documentation, knowledge bases, journaling, Zettelkasten, project/personal organization, note taking, a lightweight database substitute, or any other writing or information management that can be done in text format. See https://urtext.co for more information.

## Implementations

Currently there are implementations for Desktop (Windows/Mac/Linux) using [Sublime Text](https://www.sublimetext.com/) and iOS using [Pythonista](https://omz-software.com/pythonista/).

### Sublime Text 

The implementation in Sublime Text is a [Sublime Text Package](https://www.sublimetext.com/docs/packages.html), with all dependencies, that also includes a syntax definition, themes, and default keybindings. Its repository is [https://github.com/nbeversl/UrtextSublime](https://github.com/nbeversl/UrtextSublime).

It can be installed using Package Control, **though it has its own package control channel**.

Installation instructions are here: [https://urtext.co/setup/sublime-text/](https://urtext.co/setup/sublime-text/).

### iOS

There is an implementation for iOS using [Pythonista](https://omz-software.com/pythonista/). The repository for this implementation is at [urtext_pythonista](https://github.com/nbeversl/urtext_pythonista) and utilizes [Sublemon](https://github.com/nbeversl/sublemon), a simple custom editor created just for this implementation that provides syntax highlighting and a custom keyboard.

An [install script](https://github.com/nbeversl/urtext_pythonista_install_or_update) is available that downloads all dependencies in a single step. For instructions, see that repository or [https://urtext.co/setup/ios-using-pythonista/](https://urtext.co/setup/ios-using-pythonista/).

## Questions and Issues

All questions and support requests may be submitted to the webform https://urtext.co/support/ (no login needed).

Developer questions and issues with this core library may be submitted to [the issues tab](https://github.com/nbeversl/urtext/issues). For issues with specifical implementations, please submit to the issues tabs of the those repositories. 