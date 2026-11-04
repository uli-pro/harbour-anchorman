"""Entry points called from QML. The only module that imports pyotherside."""

import sys

import pyotherside


def version_info():
    return "Python {}.{}.{} via PyOtherSide {}".format(
        *sys.version_info[:3], pyotherside.version)
