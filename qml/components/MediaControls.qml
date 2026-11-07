import QtQuick 2.0
import Amber.Mpris 1.0

// Controls on the lock screen, in the notifications and on headphones,
// for the open book: a ReaderPage or an AudiobookPage. The Audio
// permission lets the app own the name.
MprisPlayer {
    readonly property var reader: app.reader

    // The lock screen shows these as rich text, outside the sandbox; a tag
    // in a book's title could load an image from the net.
    function plain(text) {
        return String(text).replace(/</g, "\u2039")
    }

    serviceName: "bookfish"
    identity: "Bookfish"
    desktopEntry: "harbour-bookfish"

    // Fixed: Amber does not pass a later change of CanControl on, and false
    // also turns off CanPlay and CanPause (seen on the device).
    canControl: true
    canPlay: reader !== null && reader.hasAudio
    canPause: reader !== null && reader.hasAudio
    canGoNext: reader !== null && reader.hasAudio
    canGoPrevious: reader !== null && reader.hasAudio
    // No position: the lock screen shows none (tried on the device), and a
    // readaloud is a sequence of sentences across several files.
    canSeek: false
    playbackStatus: reader === null ? Mpris.Stopped
                  : reader.playing ? Mpris.Playing : Mpris.Paused

    // The lock screen shows only the title and the artist (Sailfish.Media
    // MprisManagerControls): the book above its chapter. Album and album
    // artist for players that show them.
    metaData {
        title: reader !== null ? plain(reader.book.title) : ""
        // A list would be shown as "A,B".
        contributingArtist: reader !== null ? [plain(reader.chapterTitle)] : []
        albumTitle: reader !== null ? plain(reader.book.title) : ""
        albumArtist: reader !== null ? [plain(reader.book.authors.join("; "))] : []
        artUrl: reader !== null ? reader.coverUrl : ""
    }

    onPlayRequested: if (reader) reader.play()
    // A stop that forgot the place would help nobody listening to a book.
    onPauseRequested: if (reader) reader.pause()
    onStopRequested: if (reader) reader.pause()
    onPlayPauseRequested: {
        if (!reader)
            return
        if (reader.playing)
            reader.pause()
        else
            reader.play()
    }
    // A sentence in a readaloud, 30 s in an audiobook.
    onNextRequested: if (reader) reader.forward()
    onPreviousRequested: if (reader) reader.back()
}
