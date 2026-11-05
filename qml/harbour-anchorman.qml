import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.WebEngine 1.0
import Nemo.Configuration 1.0
import io.thp.pyotherside 1.5
import "components"
import "pages"

ApplicationWindow {
    id: app

    property bool pythonReady: false
    // Chosen by the user; "" means Documents and all memory cards.
    readonly property string libraryFolder: libraryFolderSetting.value || ""
    readonly property string cacheFolder: StandardPaths.cache + "/books"
    readonly property string positionsFile: StandardPaths.data + "/positions.json"
    readonly property string libraryCache: StandardPaths.cache + "/library.json"
    readonly property string coversFolder: StandardPaths.cache + "/covers"
    // Text size in screen pixels, like FBReader; the frame script converts
    // it to CSS pixels.
    readonly property int minFontSize: 20
    readonly property int maxFontSize: 100
    readonly property int fontSize: Math.max(minFontSize, Math.min(maxFontSize,
                                             Number(fontSizeSetting.value) || 36))

    readonly property real minPlaybackRate: 0.5
    readonly property real maxPlaybackRate: 2.5
    readonly property real playbackRate: Math.max(minPlaybackRate, Math.min(maxPlaybackRate,
                                                  Number(playbackRateSetting.value) || 1))
    readonly property real minLineHeight: 1.0
    readonly property real maxLineHeight: 2.0
    readonly property real lineHeight: settingValue(lineHeightSetting.value, 1.3,
                                                    minLineHeight, maxLineHeight)
    // Space after each paragraph, in lines; 0 indents the first lines instead.
    readonly property real minParagraphSpacing: 0
    readonly property real maxParagraphSpacing: 2.0
    readonly property real paragraphSpacing: settingValue(paragraphSpacingSetting.value, 0.5,
                                                          minParagraphSpacing, maxParagraphSpacing)
    // How much larger the WebView shows text than the size asked for,
    // measured by the reading page and kept for the next start.
    readonly property real textScale: Number(textScaleSetting.value) > 0 ? Number(textScaleSetting.value) : 1.6

    function setTextScale(scale) {
        // Rounded: tiny differences between chapters need no write. A book
        // forcing its own size measures nonsense.
        scale = Math.round(scale * 1000) / 1000
        if (scale >= 0.5 && scale <= 4 && scale !== textScale)
            textScaleSetting.value = scale
    }
    // "sans" or "serif"; the book's own fonts are not used.
    readonly property string fontFamily: fontFamilySetting.value === "serif" ? "serif" : "sans"
    // "light" or "dark" once chosen; "" follows the ambience.
    readonly property string pageColors: pageColorsSetting.value || ""
    // A cover taken out of a book by Python's cover thread; file is "" if
    // the book has none that can be shown.
    signal coverReady(string key, string file)

    // The open ReaderPage, for the cover's play button.
    property var reader: null

    function setLibraryFolder(folder) {
        libraryFolderSetting.value = folder
    }

    function setFontFamily(family) {
        fontFamilySetting.value = family
    }

    function setPageColors(colors) {
        pageColorsSetting.value = colors
    }

    function setFontSize(size) {
        fontSizeSetting.value = size
    }

    // A stored number within [min, max]; 0 is a valid value.
    function settingValue(value, fallback, min, max) {
        var number = Number(value)
        return isFinite(number) && value !== "" && value !== undefined && value !== null
               ? Math.max(min, Math.min(max, number)) : fallback
    }

    // Slider steps of 0.05 are not exact in binary.
    function setLineHeight(height) {
        lineHeightSetting.value = Math.round(height * 100) / 100
    }

    function setParagraphSpacing(spacing) {
        paragraphSpacingSetting.value = Math.round(spacing * 100) / 100
    }

    function setPlaybackRate(rate) {
        // Slider steps of 0.05 are not exact in binary.
        playbackRateSetting.value = Math.round(rate * 100) / 100
    }

    function errorText(code) {
        switch (code) {
        case "not_zip":
        case "not_epub":
            return qsTr("This file is not an EPUB book.")
        case "too_many_files":
        case "too_large":
            return qsTr("This book is too large or damaged.")
        case "no_space":
            return qsTr("Not enough free space to open this book.")
        case "unsafe_path":
            return qsTr("This book contains unsafe file names and was not opened.")
        case "drm":
            return qsTr("This book is protected by DRM and cannot be opened.")
        case "io":
            return qsTr("The book could not be read.")
        default:
            return qsTr("This book is damaged.")
        }
    }

    function showError(text) {
        Notices.show(text, Notice.Long, Notice.Center)
    }

    initialPage: Component { LibraryPage { } }
    cover: Qt.resolvedUrl("cover/CoverPage.qml")
    allowedOrientations: defaultAllowedOrientations

    Component.onCompleted: {
        // Only our frame script may run code in the book's pages; scripts
        // that came with a book never run.
        WebEngineSettings.javascriptEnabled = false
    }

    ConfigurationValue {
        id: fontSizeSetting
        key: "/apps/harbour-anchorman/fontSize"
        defaultValue: 36
    }

    ConfigurationValue {
        id: libraryFolderSetting
        key: "/apps/harbour-anchorman/libraryFolder"
        defaultValue: ""
    }

    ConfigurationValue {
        id: fontFamilySetting
        key: "/apps/harbour-anchorman/fontFamily"
        defaultValue: "sans"
    }

    ConfigurationValue {
        id: pageColorsSetting
        key: "/apps/harbour-anchorman/pageColors"
        defaultValue: ""
    }

    ConfigurationValue {
        id: lineHeightSetting
        key: "/apps/harbour-anchorman/lineHeight"
        defaultValue: 1.3
    }

    ConfigurationValue {
        id: paragraphSpacingSetting
        key: "/apps/harbour-anchorman/paragraphSpacing"
        defaultValue: 0.5
    }

    ConfigurationValue {
        id: textScaleSetting
        key: "/apps/harbour-anchorman/textScale"
        defaultValue: 0
    }

    ConfigurationValue {
        id: playbackRateSetting
        key: "/apps/harbour-anchorman/playbackRate"
        defaultValue: 1
    }

    MediaControls { }

    Python {
        id: py

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl("../python"))
            importModule("anchorman.bridge", function () {
                setHandler("cover", app.coverReady)
                app.pythonReady = true
            })
        }

        onError: {
            console.warn(traceback)
            app.showError(qsTr("Internal error. Please report it with the log."))
        }
    }
}
