import os
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "jawed",
    version = "0.1",
    author = "Tim Mann",
    author_email = "tdmann@whaba.mn",
    description = ("A basic python wrapper for the JODConverter CLI"),
    license = "MIT",
    keywords = "JODConverter PyODConverter pdf odt openoffice libreoffice libre office convert open document opendocument adobe",
    url = "https://github.com/tdmann/jawed",
    packages=['jawed'],
    long_description=read('README'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "Programming Language :: Python :: 2.6",
        "License :: OSI Approved :: MIT License",
    ],
)