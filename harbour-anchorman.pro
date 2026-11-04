TARGET = harbour-anchorman

CONFIG += sailfishapp_qml sailfishapp_i18n

# Only the module files, so local __pycache__ or tests never end up in the package.
python.files = python/anchorman/*.py
python.path = /usr/share/$${TARGET}/python/anchorman

SAILFISHAPP_ICONS = 86x86 108x108 128x128 172x172

INSTALLS += python

DISTFILES += \
    qml/harbour-anchorman.qml \
    qml/pages/*.qml \
    qml/cover/*.qml \
    qml/components/*.qml \
    qml/js/*.js \
    python/anchorman/*.py \
    rpm/harbour-anchorman.spec \
    harbour-anchorman.desktop
