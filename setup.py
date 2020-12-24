"""
This is a setup.py script generated by py2applet

Usage:
    python setup.py py2app
"""

from setuptools import setup


APP = ['Tell My.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': '/Users/coltenwebb/stalk/AppIcon.icns',
    'includes': ['keyring.backends.kwallet', 'keyring.backends.OS_X', 'keyring.backends.SecretService', 'keyring.backends.Windows', 'pyicloud']
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
